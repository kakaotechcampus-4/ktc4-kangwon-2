"""GenerateWeeklyPlan — W3a: gates, parent monthly context and the RULE_ONLY path.

docs/weekly-plan-contract.md (W1). The LLM path (W3b) and the weekly evidence
classification (W3c, after W2-E approval) come later; until then LLM_PLANNER is
refused rather than silently answered by rules (§10-1).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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
from ..domain.weekly_plan import (
    WEEKLY_INSTITUTION_INPUT_SECTION_KEYS,
    OperatingDay,
    WeeklyCell,
    WeeklyPlan,
    WeeklyTemplateSnapshot,
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
    deduplicate_evidence,
    load_activity_catalog,
    load_safety_rule,
    optional_context_results,
    require_approved_template,
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
    activity_selection: ActivitySelectionTrace | None


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
    ) -> None:
        self._parents = parent_plan_repository
        self._plans = plan_repository
        self._templates = template_repository
        self._safety = safety_repository
        self._clock = clock
        self._ids = id_generator
        self._activities = activity_repository
        self._optional_context = optional_context

    def execute(self, command: GenerateWeeklyPlanCommand) -> GenerateWeeklyPlanResult:
        if command.generation_mode is not MonthlyGenerationMode.RULE_ONLY:
            raise WeeklyApplicationError(
                "weekly_generation_mode_unsupported",
                "Only RULE_ONLY is wired; the weekly LLM path is not available yet",
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
        parent_evidence = EvidenceSource(
            EvidenceSourceType.PARENT_PLAN, parent.plan_id.value, parent.target_month.value
        )
        theme_cell = _only_cell(parent, THEME_KEY)
        theme_snapshot = _cited(lineage, theme_cell)
        selection: ActivitySelectionTrace | None = None
        cells = []
        for section in snapshot.sections:
            key = section.section_key
            value, evidence, snapshots = "", (), ()
            generation: GenerationMethodDetail | None = GenerationMethodDetail(
                GenerationMethod.RULE_ONLY, EMPTY_RULE_ID, WEEKLY_RULE_VERSION
            )
            if key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS:
                generation = None  # teacher input only (§6-2, §10-2)
            elif key == THEME_KEY:
                value = theme_cell.value
                evidence, snapshots = (parent_evidence,), (theme_snapshot,)
                generation = GenerationMethodDetail(GenerationMethod.RULE_ONLY, THEME_RULE_ID, WEEKLY_RULE_VERSION)
            elif key == SAFETY_KEY:
                # RULE_ONLY writes no safety text: empty-first, and writing the parent's
                # teacher sentence is the LLM path (§8). No placement is claimed.
                generation = GenerationMethodDetail(GenerationMethod.RULE_ONLY, SAFETY_RULE_ID, SAFETY_RULE_VERSION)
            elif key == OUTDOOR_PLAY_SLOT and catalog is not None:
                eligible = catalog.eligible_candidates(
                    section_key=OUTDOOR_PLAY_SLOT,
                    calendar_month=command.week_id.target_month.calendar_month,
                    ages=parent.target_ages,
                )
                parent_cells = _section_cells(parent, OUTDOOR_PLAY_SLOT)
                same_week = next((c for c in parent_cells if c.week_id == command.week_id), None)
                preferred = _parent_activity(same_week, eligible)
                other_weeks = tuple(
                    cell for cell in parent_cells
                    if cell.week_id != command.week_id and cell.value.strip()
                )
                picked = _rank_outdoor(
                    eligible,
                    calendar_month=command.week_id.target_month.calendar_month,
                    used_activity_ids=frozenset(
                        source.source_id
                        for cell in other_weeks
                        for source in cell.evidence
                        if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
                    ),
                    parent_theme_id=theme_reference_id(theme_cell.evidence),
                    preferred_id=preferred.activity_id if preferred is not None else None,
                )
                # Cite every parent Cell the ranking read: the same week (가점) and the others (repeat).
                cited_cells: tuple[MonthlyCell, ...] = (
                    (same_week,) if preferred is not None else ()
                ) + other_weeks
                generation = GenerationMethodDetail(
                    GenerationMethod.RULE_ONLY, OUTDOOR_RULE_ID, WEEKLY_RULE_VERSION
                )
                selection = picked.trace
                if picked.candidate is not None:
                    value = picked.candidate.label
                    evidence = deduplicate_evidence((
                        parent_evidence,
                        EvidenceSource(
                            EvidenceSourceType.ACTIVITY_REFERENCE,
                            picked.candidate.activity_id,
                            catalog.catalog_version,
                            display_name=picked.candidate.label,
                        ),
                    ))
                    snapshots = (theme_snapshot, *(_cited(lineage, cell) for cell in cited_cells))
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
        blocked = sorted(
            finding.code
            for finding in plan.verification_report.findings
            if finding.rule_id == SAFETY_GROUNDING_RULE_ID and finding.finding_kind is FindingKind.VIOLATION
        )
        if blocked:  # safety grounding errors block saving (§8, ADR-037)
            raise WeeklyApplicationError(
                "weekly_safety_verification_failed",
                "Safety grounding verification failed before the Plan was saved: " + ", ".join(blocked),
            )
        self._plans.save(plan.plan_id, plan)
        return GenerateWeeklyPlanResult(plan, optional_context, selection)


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


def _rank_outdoor(
    eligible: tuple[ActivityCandidate, ...],
    *,
    calendar_month: int,
    used_activity_ids: frozenset[str],
    parent_theme_id: str | None,
    preferred_id: str | None,
) -> ActivitySelection:
    def key(candidate: ActivityCandidate) -> tuple[object, ...]:
        base = monthly_sort_key(
            candidate,
            calendar_month=calendar_month,
            used_activity_ids=used_activity_ids,
            current_activity_id=None,
            parent_theme_id=parent_theme_id,
            used_curriculum_domains={},
        )
        bonus = int(preferred_id is not None and candidate.activity_id != preferred_id)
        return (*base[:2], bonus, *base[2:])

    ids = tuple(sorted(candidate.activity_id for candidate in eligible))
    if not eligible:
        trace = ActivitySelectionTrace(OUTDOOR_RULE_ID, WEEKLY_RULE_VERSION, (), None, None, ("NO_ELIGIBLE_CANDIDATE",))
        return ActivitySelection(None, trace)
    selected = min(eligible, key=key)
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
    return ActivitySelection(selected, trace)


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
