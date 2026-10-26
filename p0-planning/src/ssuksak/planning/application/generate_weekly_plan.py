"""GenerateWeeklyPlan — gates, parent monthly context, the RULE_ONLY path (W3a) and the
LLM_PLANNER path (W3b).

docs/weekly-plan-contract.md (W1). The LLM path never falls back to rule output (§10-1).
On the LLM path, indoor_play · group_activity · indoor_alternative are written from the
approved weekly evidence classification (W3c, §7) when it has evidence for the month and
ages; otherwise, and always on the RULE_ONLY path, they stay empty (§7-4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta

from ..domain.activity_reference import OUTDOOR_PLAY_SLOT, ActivityCandidate
from ..domain.errors import InvalidDomainValueError
from ..domain.identifiers import PlanId
from ..domain.lineage import ParentLineage
from ..domain.monthly_plan import ActivityCatalogRef, MonthlyCell, MonthlyGenerationMode, MonthlyPlan
from ..domain.monthly_template import MonthlyTemplate, TemplateRef
from ..domain.monthly_verification import FindingKind
from ..domain.plan import PlanStatus
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ..domain.week_period import WeekId
from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from ..domain.weekly_plan import (
    WEEKLY_INSTITUTION_INPUT_SECTION_KEYS,
    OperatingDay,
    WeeklyCell,
    WeeklyPlan,
    WeeklyTemplateSnapshot,
)
from ..evidence.classification import grounding_class_for
from ..evidence.ports import InstitutionEvidenceRepository, WeeklyEvidenceClassificationRepository
from ..evidence.weekly_classification import WEEKLY_GROUNDING_SCOPE
from ..retrieval.models import RetrievedEvidence
from ..retrieval.weekly import weekly_section_evidence
from ..planner.weekly import (
    OUTDOOR_KEY,
    PARENT_GROUNDABLE_KEYS,
    WeeklyPlanner,
    WeeklyPlanningRequest,
    WeeklyTarget,
    build_weekly_request,
)
from ..rules.monthly_activity_selection import (
    ActivitySelection,
    ActivitySelectionTrace,
    _sort_key as monthly_sort_key,
)
from ..rules.monthly_cell_state import resolve_cell_state
from ..rules.monthly_safety import (
    RULE_ID as SAFETY_RULE_ID,
    RULE_VERSION as SAFETY_RULE_VERSION,
    assess_safety_education,
)
from ..rules.weekly_verification import SAFETY_GROUNDING_RULE_ID, verify_weekly_plan
from .monthly_dto import ActivityCatalogSelector, SafetyRuleSelector
from .monthly_errors import MonthlyApplicationError
from .monthly_support import (
    MonthlyContextPipeline,
    deduplicate_evidence,
    load_activity_catalog,
    load_safety_rule,
    optional_context_results,
    packet_evidence,
    require_approved_template,
    snapshot_grounding_classes,
    theme_reference_id,
)
from .ports import (
    ActivityReferenceRepository,
    Clock,
    IdGenerator,
    MonthlyTemplateRepository,
    OptionalContextProvider,
    OptionalContextResult,
    PlanRepository,
    SafetyLegalRuleRepository,
)

SYSTEM_ACTOR = "weekly_application"
THEME_RULE_ID = "weekly.theme.parent_theme"
# A placed parent safety Cell already reads as the week's line (「[교통안전] - 내용」 or a
# supplemental topic), so the week takes it as is (Human Decision 2026-10-22, §8).
SAFETY_COPY_RULE_ID = "weekly.safety.parent_placement"
EMPTY_RULE_ID = "weekly.cell.rule_only_empty"
# Outdoor ranking = the monthly ranking with one weekly key: §4-2 「가점」 for the parent's
# same-week activity, placed after repeat-avoidance and the parent-theme link — a bonus,
# not a copy: a theme-linked candidate still beats an unlinked parent activity.
OUTDOOR_RULE_ID = "weekly.activity.reference_candidate_selection"
PARENT_ACTIVITY_REASON = "PARENT_SAME_WEEK_ACTIVITY"
_OUTDOOR_REASONS = (
    "AVOIDED_REPEAT_IN_MONTH",
    "MATCHED_PARENT_THEME",
    PARENT_ACTIVITY_REASON,
    "AVOIDED_CONFIRMED_DISPLAY_QUALITY_ISSUE",
    "AVOIDED_CURRICULUM_DOMAIN_REPEAT",
    "STRONGER_MONTH_EVIDENCE",
)
WEEKLY_RULE_VERSION = "v1"
LLM_RULE_ID = "weekly.llm.planner"  # rule_version = the prompt that wrote the value
OUTDOOR_CANDIDATE_LIMIT = 12  # same size as the monthly reference block
THEME_KEY = "theme"
SAFETY_KEY = "safety_education"


class WeeklyApplicationError(MonthlyApplicationError):
    """Expected weekly failures. Shared loaders (Template approval, Activity Catalog,
    Safety Rule) raise the MonthlyApplicationError base with their own codes."""


@dataclass(frozen=True, slots=True)
class GenerateWeeklyPlanCommand:
    parent_monthly_plan_id: PlanId
    week_id: WeekId
    operating_days: tuple[OperatingDay, ...]  # center setting snapshot (§3-5); validated by WeeklyPlan
    template_ref: TemplateRef  # exact weekly Template version; weekly has no Profile (§13)
    safety_rule: SafetyRuleSelector
    generation_mode: MonthlyGenerationMode
    activity_catalog: ActivityCatalogSelector | None = None
    optional_context_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        checks = (
            (self.parent_monthly_plan_id, PlanId, "parent_monthly_plan_id"),
            (self.week_id, WeekId, "week_id"),
            (self.template_ref, TemplateRef, "template_ref"),
            (self.safety_rule, SafetyRuleSelector, "safety_rule"),
            (self.generation_mode, MonthlyGenerationMode, "generation_mode"),
        )
        for value, kind, name in checks:
            if not isinstance(value, kind):
                raise InvalidDomainValueError(f"GenerateWeeklyPlanCommand.{name} is invalid")
        if self.activity_catalog is not None and not isinstance(self.activity_catalog, ActivityCatalogSelector):
            raise InvalidDomainValueError("GenerateWeeklyPlanCommand.activity_catalog is invalid")


@dataclass(frozen=True, slots=True)
class GenerateWeeklyPlanResult:
    plan: WeeklyPlan
    optional_context: tuple[OptionalContextResult, ...]
    activity_selection: ActivitySelectionTrace | None  # the rule ranking; None on the LLM path
    context_packet_fingerprint: str | None = None


class GenerateWeeklyPlan:
    def __init__(
        self,
        *,
        parent_plan_repository: PlanRepository[MonthlyPlan],
        plan_repository: PlanRepository[WeeklyPlan],
        template_repository: MonthlyTemplateRepository,
        safety_repository: SafetyLegalRuleRepository,
        clock: Clock,
        id_generator: IdGenerator,
        activity_repository: ActivityReferenceRepository | None = None,
        optional_context: OptionalContextProvider | None = None,
        context_pipeline: MonthlyContextPipeline | None = None,
        planner: WeeklyPlanner | None = None,
        evidence_repository: InstitutionEvidenceRepository | None = None,
        weekly_classification_repository: WeeklyEvidenceClassificationRepository | None = None,
    ) -> None:
        self._parents = parent_plan_repository
        self._plans = plan_repository
        self._templates = template_repository
        self._safety = safety_repository
        self._clock = clock
        self._ids = id_generator
        self._activities = activity_repository
        self._optional_context = optional_context
        self._context = context_pipeline
        self._planner = planner
        # Both or neither: without them the three classified Sections stay empty (§7-4).
        self._evidence = evidence_repository
        self._weekly_classification = weekly_classification_repository

    def execute(self, command: GenerateWeeklyPlanCommand) -> GenerateWeeklyPlanResult:
        llm = command.generation_mode is MonthlyGenerationMode.LLM_PLANNER
        if llm and (self._context is None or self._planner is None):
            raise WeeklyApplicationError(
                "weekly_llm_dependencies_required",
                "LLM_PLANNER mode requires a Context Pipeline and a Weekly Planner",
            )
        parent = self._parents.get(command.parent_monthly_plan_id)
        if parent is None:
            raise WeeklyApplicationError(
                "parent_monthly_plan_not_found",
                f"Parent Monthly Plan not found: {command.parent_monthly_plan_id}",
            )
        if not isinstance(parent, MonthlyPlan):
            raise WeeklyApplicationError(
                "parent_repository_contract_violation",
                "Parent repository returned a non-MonthlyPlan value",
            )
        if parent.status is not PlanStatus.CONFIRMED:  # G3
            raise WeeklyApplicationError(
                "parent_monthly_plan_must_be_confirmed",
                "Weekly generation requires an explicitly CONFIRMED Monthly Plan",
            )
        # G4: the week address and its span come from the parent, never recomputed (§3-1).
        period = next((p for p in parent.week_periods if p.week_id == command.week_id), None)
        if period is None:
            raise WeeklyApplicationError(
                "weekly_week_not_in_parent",
                f"Week {command.week_id} is not a week of the parent Monthly Plan",
            )
        if not period.active:
            raise WeeklyApplicationError(
                "weekly_week_inactive", f"Week {command.week_id} is inactive in the parent Monthly Plan"
            )
        require_approved_template(self._templates, command.template_ref)  # G6 (ADR-027)
        snapshot = _snapshot(
            self._templates.get_template(command.template_ref.template_id, command.template_ref.template_version),
            parent,
        )
        safety_rule = load_safety_rule(self._safety, command.safety_rule)
        catalog = load_activity_catalog(self._activities, command.activity_catalog)
        optional_context = optional_context_results(command.optional_context_names, self._optional_context)
        lineage = _plan_lineage(parent)
        keys = {section.section_key for section in snapshot.sections}
        safety_assessment = assess_safety_education(
            safety_rule, safety_section_active=SAFETY_KEY in keys, has_placement_source=False
        )

        plan_id = self._ids.new_plan_id()
        now = self._clock.now()
        parent_evidence = _parent_evidence(parent)
        theme_cell = _only_cell(parent, THEME_KEY)
        theme_snapshot = _cited(lineage, theme_cell)
        outdoor = _outdoor_ranking(parent, command.week_id, catalog, theme_cell)
        outcome, fingerprint, context = None, None, None
        if llm:
            context = llm_context(
                self._context, self._evidence, self._weekly_classification,
                parent=parent, period=period, operating_days=command.operating_days, snapshot=snapshot,
                catalog=catalog, constraint_assessments=(safety_assessment,), outdoor=outdoor,
            )
            fingerprint = context.fingerprint
            try:
                outcome = self._planner.plan(context.request)
            except Exception as exc:  # never answered by the rule path instead (§10-1)
                raise WeeklyApplicationError(
                    "weekly_llm_planning_failed", "Weekly LLM planning failed before any Plan was saved"
                ) from exc
        selection: ActivitySelectionTrace | None = None
        cells = []
        for section in snapshot.sections:
            key = section.section_key
            value, evidence, snapshots = "", (), ()
            generation: GenerationMethodDetail | None = GenerationMethodDetail(
                GenerationMethod.RULE_ONLY, EMPTY_RULE_ID, WEEKLY_RULE_VERSION
            )
            proposed = outcome.value(key) if outcome is not None else None
            if key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS:
                generation = None  # teacher input only (§6-2, §10-2)
            elif proposed is not None:
                if not proposed.unresolved:
                    value = proposed.value
                    generation = GenerationMethodDetail(
                        GenerationMethod.RULE_LLM, LLM_RULE_ID, outcome.prompt_version_for(key)
                    )
                    evidence, snapshots = llm_cell_sources(
                        proposed, context, parent=parent, lineage=lineage, outdoor=outdoor, catalog=catalog
                    )
            elif key == THEME_KEY:
                value = theme_cell.value
                evidence, snapshots = (parent_evidence,), (theme_snapshot,)
                generation = GenerationMethodDetail(GenerationMethod.RULE_ONLY, THEME_RULE_ID, WEEKLY_RULE_VERSION)
            elif key == SAFETY_KEY:
                # Writing the parent's teacher sentence is the LLM path (§8); a placed parent
                # Cell is copied and cited. The week claims no placement of its own.
                generation = GenerationMethodDetail(GenerationMethod.RULE_ONLY, SAFETY_RULE_ID, SAFETY_RULE_VERSION)
                placed = _parent_cell(parent, key, period.week_id)
                if placed is not None and placed.safety is not None and placed.value.strip():
                    value = placed.value
                    evidence, snapshots = (parent_evidence,), (_cited(lineage, placed),)
                    generation = GenerationMethodDetail(
                        GenerationMethod.RULE_ONLY, SAFETY_COPY_RULE_ID, WEEKLY_RULE_VERSION
                    )
            elif key == OUTDOOR_PLAY_SLOT and catalog is not None and not llm:
                picked = outdoor.selection
                generation = GenerationMethodDetail(
                    GenerationMethod.RULE_ONLY, OUTDOOR_RULE_ID, WEEKLY_RULE_VERSION
                )
                selection = picked.trace
                if picked.candidate is not None:
                    value = picked.candidate.label
                    evidence, snapshots = rule_outdoor_sources(
                        picked.candidate, parent=parent, lineage=lineage, outdoor=outdoor, catalog=catalog
                    )
            item_id = self._ids.new_item_id()
            cells.append(WeeklyCell(
                item_id=item_id,
                section_key=key,
                value=value,
                cell_state=resolve_cell_state(
                    section_key=key,
                    value=value,
                    assessment=safety_assessment if key == SAFETY_KEY else None,
                ),
                generation=generation,
                evidence=evidence,
                audit=AuditHistory((
                    AuditEvent(AuditEventType.CREATED, now, plan_id, item_id=item_id, system_actor=SYSTEM_ACTOR),
                )),
                parent_snapshots=snapshots,
                source_label=section.source_label,
            ))

        plan = WeeklyPlan(
            plan_id=plan_id,
            school_year=parent.school_year,
            week_id=command.week_id,
            week_period=period,
            operating_days=command.operating_days,
            daycare_ref=parent.daycare_ref,
            classroom_ref=parent.classroom_ref,
            target_ages=parent.target_ages,
            status=PlanStatus.DRAFT,
            parent_lineage=lineage,
            template_snapshot=snapshot,
            cells=tuple(cells),
            constraint_assessments=(safety_assessment,),
            audit=AuditHistory((AuditEvent(AuditEventType.CREATED, now, plan_id, system_actor=SYSTEM_ACTOR),)),
            activity_catalog_ref=(
                ActivityCatalogRef(catalog.catalog_id, catalog.catalog_version) if catalog is not None else None
            ),
            generation_mode=command.generation_mode,
        )
        try:
            plan = replace(plan, verification_report=verify_weekly_plan(plan, catalog, parent))
        except Exception as exc:  # a verifier that cannot run is not a finding (§11-2)
            raise WeeklyApplicationError(
                "weekly_verification_failed", "Weekly rule verification failed before the Plan was saved"
            ) from exc
        require_safe_grounding(plan)
        self._plans.save(plan.plan_id, plan)
        return GenerateWeeklyPlanResult(plan, optional_context, selection, fingerprint)


def _snapshot(template: MonthlyTemplate, parent: MonthlyPlan) -> WeeklyTemplateSnapshot:
    snapshot = WeeklyTemplateSnapshot.from_template(
        template, institution_ref=parent.daycare_ref, classroom_ref=parent.classroom_ref
    )
    # F1: weekly focus speaks in the parent monthly focus variant.
    parent_focus = next((s for s in parent.template_snapshot.sections if s.section_key == "focus"), None)
    if parent_focus is None:
        return snapshot
    return replace(snapshot, sections=tuple(
        replace(s, semantic_variant=parent_focus.semantic_variant) if s.section_key == "focus" else s
        for s in snapshot.sections
    ))


def _plan_lineage(parent: MonthlyPlan) -> ParentLineage:
    confirmation = next(
        (e for e in reversed(parent.audit.events) if e.event_type is AuditEventType.CONFIRMED),
        None,
    )
    if confirmation is None or confirmation.actor_id is None:
        raise WeeklyApplicationError(
            "parent_monthly_confirmation_missing",
            "Confirmed Monthly Plan lacks a teacher confirmation audit event",
        )
    return ParentLineage(parent.plan_id, confirmation.occurred_at, confirmation.actor_id)


def _cited(lineage: ParentLineage, cell: MonthlyCell) -> ParentLineage:
    # F2: the Application records which parent Cell (and its value then) a value used.
    return replace(lineage, parent_item_id=cell.item_id, snapshot_value=cell.value)


def require_safe_grounding(plan: WeeklyPlan) -> None:
    """AI output with a safety grounding error is never saved (§8, ADR-037) — generation and
    regeneration alike; confirmation does not filter AI errors."""
    blocked = sorted(
        finding.code
        for finding in plan.verification_report.findings
        if finding.rule_id == SAFETY_GROUNDING_RULE_ID and finding.finding_kind is FindingKind.VIOLATION
    )
    if blocked:
        raise WeeklyApplicationError(
            "weekly_safety_verification_failed",
            "Safety grounding verification failed before the Plan was saved: " + ", ".join(blocked),
        )


def _parent_evidence(parent: MonthlyPlan) -> EvidenceSource:
    return EvidenceSource(EvidenceSourceType.PARENT_PLAN, parent.plan_id.value, parent.target_month.value)


@dataclass(frozen=True, slots=True)
class WeeklyLlmContext:
    """What the Rule fixed for one week's LLM request (shared by generation and W4b)."""

    packet: MonthlyContextPacket
    fingerprint: str
    classified: dict[str, tuple[RetrievedEvidence, ...]]
    store_version: str | None
    request: WeeklyPlanningRequest


def llm_context(
    context_pipeline: MonthlyContextPipeline,
    evidence_repository: InstitutionEvidenceRepository | None,
    classification_repository: WeeklyEvidenceClassificationRepository | None,
    *,
    parent: MonthlyPlan,
    period,
    operating_days: tuple[OperatingDay, ...],
    snapshot: WeeklyTemplateSnapshot,
    catalog,
    constraint_assessments,
    outdoor,
) -> WeeklyLlmContext:
    theme_cell = _only_cell(parent, THEME_KEY)
    packet = context_pipeline.build(
        target_month=period.week_id.target_month,
        ages=parent.target_ages,
        parent_theme_id=theme_reference_id(theme_cell.evidence),
        parent_theme_value=theme_cell.value,
        week_periods=(period,),
        activity_catalog=catalog,
        constraint_assessments=constraint_assessments,
        grounding_classes=snapshot_grounding_classes(snapshot),
    )
    fingerprint = packet_fingerprint(packet)
    classified: dict[str, tuple[RetrievedEvidence, ...]] = {}
    store_version = None
    if evidence_repository is not None and classification_repository is not None:
        store = evidence_repository.get_store()
        store_version = store.ingestion_version
        keys = {section.section_key for section in snapshot.sections}
        classified = _classified_evidence(
            store, classification_repository.get_classification(), parent, period.week_id, keys
        )
    request = _weekly_request(
        parent, period, operating_days, snapshot, packet, theme_cell, outdoor, fingerprint, classified
    )
    return WeeklyLlmContext(packet, fingerprint, classified, store_version, request)


def llm_cell_sources(
    proposed, context: WeeklyLlmContext, *, parent: MonthlyPlan, lineage: ParentLineage, outdoor, catalog
) -> tuple[tuple[EvidenceSource, ...], tuple[ParentLineage, ...]]:
    """F2: parent citations and the Activity Reference come from the Rule, not the LLM."""
    key = proposed.section_key
    theme_cell = _only_cell(parent, THEME_KEY)
    if key == THEME_KEY:
        cited: tuple[MonthlyCell, ...] = (theme_cell,)
        extra: tuple[EvidenceSource, ...] = ()
    elif key == OUTDOOR_KEY:
        cited = outdoor.cited_cells
        extra = (EvidenceSource(
            EvidenceSourceType.ACTIVITY_REFERENCE, proposed.reference_id,
            catalog.catalog_version, display_name=proposed.value,
        ),)
    elif key in context.classified:
        # No parent counterpart (§7): only the chosen institution records.
        labels = {item.record_id: item.record.source_label for item in context.classified[key]}
        cited = ()
        extra = tuple(
            EvidenceSource(
                EvidenceSourceType.INSTITUTION_SAMPLE, ref, context.store_version, display_name=labels[ref]
            )
            for ref in proposed.grounding_refs
        )
    else:
        parent_cell = _parent_cell(parent, key, context.request.week_id)
        cited = (parent_cell,) if parent_cell is not None and parent_cell.value.strip() else ()
        extra = packet_evidence(context.packet, proposed.grounding_refs)
    evidence = deduplicate_evidence((_parent_evidence(parent), *extra))
    snapshots = tuple(
        dict.fromkeys(
            ((_cited(lineage, theme_cell),) if key == OUTDOOR_KEY else ())
            + tuple(_cited(lineage, cell) for cell in cited)
        )
    )
    return evidence, snapshots


def rule_outdoor_sources(
    candidate: ActivityCandidate, *, parent: MonthlyPlan, lineage: ParentLineage, outdoor, catalog
) -> tuple[tuple[EvidenceSource, ...], tuple[ParentLineage, ...]]:
    evidence = deduplicate_evidence((
        _parent_evidence(parent),
        EvidenceSource(
            EvidenceSourceType.ACTIVITY_REFERENCE,
            candidate.activity_id,
            catalog.catalog_version,
            display_name=candidate.label,
        ),
    ))
    theme_snapshot = _cited(lineage, _only_cell(parent, THEME_KEY))
    return evidence, (theme_snapshot, *(_cited(lineage, cell) for cell in outdoor.cited_cells))


@dataclass(frozen=True, slots=True)
class _OutdoorRanking:
    selection: ActivitySelection
    ranked: tuple[ActivityCandidate, ...]
    cited_cells: tuple[MonthlyCell, ...]  # every parent Cell the ranking read


def _outdoor_ranking(
    parent: MonthlyPlan, week_id: WeekId, catalog, theme_cell: MonthlyCell, current_activity_id: str | None = None
) -> _OutdoorRanking:
    if catalog is None:
        return _OutdoorRanking(_rank_outdoor((), calendar_month=0, used_activity_ids=frozenset(),
                                             parent_theme_id=None, preferred_id=None,
                                             current_activity_id=None)[0], (), ())
    eligible = catalog.eligible_candidates(
        section_key=OUTDOOR_PLAY_SLOT, calendar_month=week_id.target_month.calendar_month, ages=parent.target_ages
    )
    # Regeneration offers no way back to the current activity while another exists — a
    # last rank alone still left it among the LLM's candidates (live smoke F-1).
    if any(c.activity_id != current_activity_id for c in eligible):
        eligible = tuple(c for c in eligible if c.activity_id != current_activity_id)
    parent_cells = _section_cells(parent, OUTDOOR_PLAY_SLOT)
    same_week = next((c for c in parent_cells if c.week_id == week_id), None)
    preferred = _parent_activity(same_week, eligible)
    other_weeks = tuple(c for c in parent_cells if c.week_id != week_id and c.value.strip())
    selection, ranked = _rank_outdoor(
        eligible,
        calendar_month=week_id.target_month.calendar_month,
        used_activity_ids=frozenset(
            source.source_id
            for cell in other_weeks
            for source in cell.evidence
            if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
        ),
        parent_theme_id=theme_reference_id(theme_cell.evidence),
        preferred_id=preferred.activity_id if preferred is not None else None,
        current_activity_id=current_activity_id,
    )
    # The same week is read only when it earned the bonus; the others feed repeat-avoidance.
    return _OutdoorRanking(selection, ranked, ((same_week,) if preferred is not None else ()) + other_weeks)


def _parent_cell(parent: MonthlyPlan, key: str, week_id: WeekId) -> MonthlyCell | None:
    section = parent.section(key)
    if section is None:
        return None
    return section.cell_for_week(week_id) or section.cell_for_week(None)


def _classified_evidence(store, classification, parent, week_id, keys) -> dict[str, tuple[RetrievedEvidence, ...]]:
    """W3c: evidence per classified Section; a Section with none is left out (not a target)."""
    focus = _parent_cell(parent, "focus", week_id)
    query = " ".join((_only_cell(parent, THEME_KEY).value, focus.value if focus is not None else ""))
    blocks = {}
    for weekly_class, key in WEEKLY_GROUNDING_SCOPE.items():
        if key not in keys:
            continue
        items = tuple(
            item for item in weekly_section_evidence(
                store, classification, weekly_class=weekly_class,
                calendar_month=week_id.target_month.calendar_month, ages=parent.target_ages, query_text=query,
            ) if item.record.text
        )
        if items:
            blocks[key] = items
    return blocks


def _weekly_request(
    parent, period, operating_days, snapshot, packet, theme_cell, outdoor, fingerprint, classified
) -> WeeklyPlanningRequest:
    """The Rule decides what the LLM may write; anything without a basis is not a target."""
    targets = [WeeklyTarget(THEME_KEY, parent_value=theme_cell.value)]
    parent_context = [(THEME_KEY, theme_cell.value)]
    evidence = []
    for section in snapshot.sections:
        key = section.section_key
        parent_cell = _parent_cell(parent, key, period.week_id) if key != THEME_KEY else None
        parent_value = parent_cell.value if parent_cell is not None else ""
        if key in PARENT_GROUNDABLE_KEYS:
            klass = grounding_class_for(section)  # F1 variant decides the class; WEEKLY_THEME has none
            items = tuple(i for i in packet.section_evidence if klass is not None and i.grounding_class is klass)
            if items or parent_value.strip():  # Q1 / Q3: the parent value alone is a basis
                targets.append(WeeklyTarget(
                    key, tuple(i.evidence_ref for i in items), parent_value,
                    None if section.semantic_variant is None else section.semantic_variant.value,
                ))
                evidence += [(i.evidence_ref, i.text, i.grounding_class.value) for i in items]
        elif key in classified:  # W3c: grounded only by its own class (§7); no parent counterpart
            items = classified[key]
            targets.append(WeeklyTarget(key, tuple(i.record_id for i in items), parent_value))
            klass = next(c for c, k in WEEKLY_GROUNDING_SCOPE.items() if k == key)
            evidence += [(i.record_id, i.record.text, klass.value) for i in items]
        elif key == OUTDOOR_KEY and outdoor.ranked:
            targets.append(WeeklyTarget(key, (), parent_value))
        elif key == SAFETY_KEY and parent_value.strip() and parent_cell.safety is None:
            # §8 teacher-text row (the only non-empty row live today). Placement rows stay empty here.
            targets.append(WeeklyTarget(key, (), parent_value))
        else:
            continue
        if parent_value.strip():
            parent_context.append((key, parent_value))
    days = operating_days
    return build_weekly_request(
        week_id=period.week_id,
        week={
            "display_label": period.display_label,
            "start": period.start_date.isoformat(),
            "end": (period.start_date + timedelta(days=len(days) - 1)).isoformat(),
            "operating_days": [day.value for day in days],
        },
        ages=tuple(sorted(parent.target_ages)),
        targets=tuple(targets),
        teacher_input_keys=WEEKLY_INSTITUTION_INPUT_SECTION_KEYS,
        parent_context=tuple(parent_context),
        evidence=tuple(dict.fromkeys(evidence)),
        reference_candidates=tuple((c.activity_id, c.label) for c in outdoor.ranked[:OUTDOOR_CANDIDATE_LIMIT]),
        packet_fingerprint=fingerprint,
    )


def _rank_outdoor(
    eligible: tuple[ActivityCandidate, ...],
    *,
    calendar_month: int,
    used_activity_ids: frozenset[str],
    parent_theme_id: str | None,
    preferred_id: str | None,
    current_activity_id: str | None,  # W4b regeneration: avoid the Cell's current activity
) -> tuple[ActivitySelection, tuple[ActivityCandidate, ...]]:
    def key(candidate: ActivityCandidate) -> tuple[object, ...]:
        base = monthly_sort_key(
            candidate,
            calendar_month=calendar_month,
            used_activity_ids=used_activity_ids,
            current_activity_id=current_activity_id,
            parent_theme_id=parent_theme_id,
            used_curriculum_domains={},
        )
        bonus = int(preferred_id is not None and candidate.activity_id != preferred_id)
        return (*base[:2], bonus, *base[2:])

    ids = tuple(sorted(candidate.activity_id for candidate in eligible))
    if not eligible:
        trace = ActivitySelectionTrace(OUTDOOR_RULE_ID, WEEKLY_RULE_VERSION, (), None, None, ("NO_ELIGIBLE_CANDIDATE",))
        return ActivitySelection(None, trace), ()
    ranked = tuple(sorted(eligible, key=key))
    selected = ranked[0]
    selected_key = key(selected)
    if len(eligible) == 1:
        reasons: tuple[str, ...] = ("ONLY_ELIGIBLE_CANDIDATE",)
    else:
        reasons = tuple(
            label for index, label in enumerate(_OUTDOOR_REASONS)
            if (index == 2 and preferred_id is not None and selected_key[2] == 0)
            or (index != 2 and (selected_key[index] == 0 or (index == 5 and int(selected_key[index]) < 0)))
        ) + ("TIE_BREAK_STABLE_ACTIVITY_ID",)
    trace = ActivitySelectionTrace(OUTDOOR_RULE_ID, WEEKLY_RULE_VERSION, ids, selected.activity_id, selected_key, reasons)
    return ActivitySelection(selected, trace), ranked


def _parent_activity(
    cell: MonthlyCell | None, eligible: tuple[ActivityCandidate, ...]
) -> ActivityCandidate | None:
    """The parent's same-week Catalog activity, if it is still the parent's current value.

    A teacher who rewrote the monthly cell left the old ACTIVITY_REFERENCE as history;
    then the reference is no longer the parent's choice and earns no preference.
    """
    if cell is None or not cell.value.strip():
        return None
    referenced = {
        source.source_id for source in cell.evidence
        if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
    }
    return next(
        (c for c in eligible if c.activity_id in referenced and c.label == cell.value), None
    )


def _section_cells(parent: MonthlyPlan, key: str) -> tuple[MonthlyCell, ...]:
    section = parent.section(key)
    return section.cells if section is not None else ()


def _only_cell(parent: MonthlyPlan, key: str) -> MonthlyCell:
    cells = _section_cells(parent, key)
    if len(cells) != 1 or not cells[0].value.strip():
        raise WeeklyApplicationError(
            "parent_monthly_theme_missing", f"Parent Monthly Plan needs one non-empty {key} Cell"
        )
    return cells[0]
