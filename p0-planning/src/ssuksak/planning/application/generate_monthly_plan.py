"""Assemble PR2 through PR5 into one complete Monthly DRAFT."""

from __future__ import annotations

from ..domain.activity_reference import ActivityCatalog, OUTDOOR_PLAY_SLOT
from ..domain.monthly_plan import (
    ActivityCatalogRef,
    LabelVariant,
    MappingConfidence,
    MonthlyCell,
    MonthlyGenerationMode,
    MonthlyPlan,
    MonthlySection,
)
from ..domain.monthly_constraint import CellState
from ..domain.monthly_template import DisplayMode, EmptyValuePolicy, SectionRole
from ..domain.monthly_template_snapshot import TemplateSnapshot
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
from ..domain.yearly_plan import YearlyPlan
from ..planner.contracts import MONTHLY_PROMPT_VERSION
from ..planner.service import MonthlyPlanner
from ..rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
    select_activity_for_cell,
)
from ..rules.monthly_cell_state import resolve_cell_state
from ..rules.monthly_safety import (
    RULE_ID as SAFETY_RULE_ID,
    RULE_VERSION as SAFETY_RULE_VERSION,
    assess_safety_education,
)
from ..rules.monthly_template_resolver import (
    RULE_ID as TEMPLATE_RULE_ID,
    RULE_VERSION as TEMPLATE_RULE_VERSION,
    ResolvedSection,
    resolve_snapshot_sections,
)
from ..rules.monthly_theme_derivation import derive_monthly_theme
from ..rules.monthly_week_periods import canonical_week_periods
from .monthly_dto import (
    GenerateMonthlyPlanCommand,
    GenerateMonthlyPlanResult,
    MonthlyActivitySelectionResult,
)
from .monthly_errors import MonthlyApplicationError
from .monthly_support import (
    MonthlyContextPipeline,
    deduplicate_evidence,
    load_activity_catalog,
    load_safety_rule,
    load_template_profile,
    optional_context_results,
    packet_evidence,
    theme_reference_id,
)
from .ports import (
    ActivityReferenceRepository,
    Clock,
    IdGenerator,
    OptionalContextProvider,
    PlanRepository,
    SafetyLegalRuleRepository,
    TemplateProfileRepository,
)

SYSTEM_ACTOR = "monthly_application"
LLM_INTEGRATION_RULE_ID = "monthly.llm.validated_proposal"
THEME_SECTION_KEY = "theme"
FOCUS_SECTION_KEY = "focus"
OUTDOOR_SECTION_KEY = "outdoor_play"
SAFETY_SECTION_KEY = "safety_education"


class GenerateMonthlyPlan:
    def __init__(
        self,
        *,
        parent_plan_repository: PlanRepository[YearlyPlan],
        plan_repository: PlanRepository[MonthlyPlan],
        profile_repository: TemplateProfileRepository,
        safety_repository: SafetyLegalRuleRepository,
        clock: Clock,
        id_generator: IdGenerator,
        activity_repository: ActivityReferenceRepository | None = None,
        context_pipeline: MonthlyContextPipeline | None = None,
        planner: MonthlyPlanner | None = None,
        optional_context: OptionalContextProvider | None = None,
    ) -> None:
        self._parents = parent_plan_repository
        self._plans = plan_repository
        self._profiles = profile_repository
        self._safety = safety_repository
        self._activities = activity_repository
        self._clock = clock
        self._ids = id_generator
        self._context = context_pipeline
        self._planner = planner
        self._optional_context = optional_context

    def execute(
        self, command: GenerateMonthlyPlanCommand
    ) -> GenerateMonthlyPlanResult:
        parent = self._parents.get(command.parent_yearly_plan_id)
        if parent is None:
            raise MonthlyApplicationError(
                "parent_yearly_plan_not_found",
                f"Parent Yearly Plan not found: {command.parent_yearly_plan_id}",
            )
        if not isinstance(parent, YearlyPlan):
            raise MonthlyApplicationError(
                "parent_repository_contract_violation",
                "Parent repository returned a non-YearlyPlan value",
            )
        if parent.status is not PlanStatus.CONFIRMED:
            raise MonthlyApplicationError(
                "parent_yearly_plan_must_be_confirmed",
                "Monthly generation requires an explicitly CONFIRMED Yearly Plan",
            )

        profile = load_template_profile(self._profiles, command.profile_ref)
        if profile.institution_ref != command.daycare_ref:
            raise MonthlyApplicationError(
                "monthly_template_profile_institution_mismatch",
                "Monthly Template Profile institution does not match the command",
            )
        if (
            profile.classroom_ref is not None
            and profile.classroom_ref != parent.classroom_ref
        ):
            raise MonthlyApplicationError(
                "monthly_template_profile_classroom_mismatch",
                "Monthly Template Profile classroom does not match the parent Plan",
            )
        template_snapshot = TemplateSnapshot.from_profile(profile)
        safety_rule = load_safety_rule(self._safety, command.safety_rule)
        catalog = load_activity_catalog(
            self._activities, command.activity_catalog
        )
        resolved_sections = resolve_snapshot_sections(template_snapshot)
        week_periods = canonical_week_periods(command.target_month)
        theme = derive_monthly_theme(parent, command.target_month)
        optional_context = optional_context_results(
            command.optional_context_names, self._optional_context
        )
        safety_active = any(
            section.section_key == SAFETY_SECTION_KEY
            for section in resolved_sections
        )
        safety_assessment = assess_safety_education(
            safety_rule,
            safety_section_active=safety_active,
            has_placement_source=False,
        )
        assessments = (safety_assessment,)

        packet = None
        planner_outcome = None
        if command.generation_mode is MonthlyGenerationMode.LLM_PLANNER:
            if self._context is None or self._planner is None:
                raise MonthlyApplicationError(
                    "monthly_llm_dependencies_required",
                    "LLM_PLANNER mode requires Context Pipeline and Monthly Planner",
                )
            parent_theme_id = theme_reference_id(theme.evidence)
            packet = self._context.build(
                target_month=command.target_month,
                ages=parent.target_ages,
                parent_theme_id=parent_theme_id,
                parent_theme_value=theme.value,
                week_periods=week_periods,
                activity_catalog=catalog,
                constraint_assessments=assessments,
            )
            try:
                planner_outcome = self._planner.plan(packet, template_snapshot)
            except Exception as exc:
                raise MonthlyApplicationError(
                    "monthly_llm_planning_failed",
                    "Monthly LLM planning failed before any Plan was saved",
                ) from exc

        plan_id = self._ids.new_plan_id()
        now = self._clock.now()
        selection_results: list[MonthlyActivitySelectionResult] = []
        sections: list[MonthlySection] = []
        used_activity_ids: set[str] = set()
        proposal = (
            planner_outcome.proposal if planner_outcome is not None else None
        )
        for resolved in resolved_sections:
            cells = self._build_section_cells(
                resolved=resolved,
                active_weeks=tuple(
                    period for period in week_periods if period.active
                ),
                plan_id=plan_id,
                now=now,
                theme=theme,
                target_ages=parent.target_ages,
                target_month=command.target_month,
                safety_rule_version=safety_rule.legal_rule_version,
                safety_assessment=safety_assessment,
                mode=command.generation_mode,
                catalog=catalog,
                proposal=proposal,
                packet=packet,
                used_activity_ids=used_activity_ids,
                selection_results=selection_results,
            )
            section = resolved.template_section
            sections.append(
                MonthlySection(
                    section_key=section.section_key,
                    role=section.role,
                    display_mode=section.display_mode,
                    empty_value_policy=(
                        section.empty_value_policy
                        or EmptyValuePolicy.RENDER_EMPTY_CELL
                    ),
                    activated=section.activated,
                    parent_section_key=section.parent_section_key,
                    source_label=section.source_label,
                    cells=cells,
                )
            )

        plan = MonthlyPlan(
            plan_id=plan_id,
            school_year=parent.school_year,
            target_month=command.target_month,
            daycare_ref=command.daycare_ref,
            classroom_ref=parent.classroom_ref,
            target_ages=parent.target_ages,
            status=PlanStatus.DRAFT,
            parent_lineage=theme.parent_lineage,
            template_snapshot=template_snapshot,
            week_periods=week_periods,
            sections=tuple(sections),
            constraint_assessments=assessments,
            audit=AuditHistory(
                (
                    AuditEvent(
                        AuditEventType.CREATED,
                        now,
                        plan_id,
                        system_actor=SYSTEM_ACTOR,
                    ),
                )
            ),
            activity_catalog_ref=(
                ActivityCatalogRef(catalog.catalog_id, catalog.catalog_version)
                if catalog is not None
                else None
            ),
            generation_mode=command.generation_mode,
        )
        self._require_complete(plan, resolved_sections)
        self._plans.save(plan.plan_id, plan)
        return GenerateMonthlyPlanResult(
            plan=plan,
            optional_context=optional_context,
            activity_selections=tuple(selection_results),
            context_packet_fingerprint=(
                planner_outcome.packet_fingerprint
                if planner_outcome is not None
                else None
            ),
        )

    def _build_section_cells(
        self,
        *,
        resolved: ResolvedSection,
        active_weeks,
        plan_id,
        now,
        theme,
        target_ages,
        target_month,
        safety_rule_version: str,
        safety_assessment,
        mode: MonthlyGenerationMode,
        catalog: ActivityCatalog | None,
        proposal,
        packet,
        used_activity_ids: set[str],
        selection_results: list[MonthlyActivitySelectionResult],
    ) -> tuple[MonthlyCell, ...]:
        section = resolved.template_section
        if section.role is SectionRole.AXIS:
            return ()
        week_ids = (
            (None,)
            if section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
            else tuple(period.week_id for period in active_weeks)
        )
        cells = []
        for week_id in week_ids:
            value = ""
            evidence: tuple[EvidenceSource, ...] = ()
            generation = GenerationMethodDetail(
                GenerationMethod.RULE_ONLY,
                TEMPLATE_RULE_ID,
                TEMPLATE_RULE_VERSION,
            )
            label_variant = None
            mapping_confidence = None
            proposed = (
                proposal.value_for(section.section_key, week_id)
                if proposal is not None
                else None
            )
            unresolved = False
            if mode is MonthlyGenerationMode.LLM_PLANNER and proposed is not None:
                value = proposed.value
                unresolved = proposed.unresolved
                if section.section_key == THEME_SECTION_KEY:
                    evidence = theme.evidence
                    generation = theme.generation
                elif section.section_key == SAFETY_SECTION_KEY:
                    evidence = deduplicate_evidence(
                        (
                            EvidenceSource(
                                EvidenceSourceType.SAFETY_RULE,
                                source_id=safety_rule_version,
                                source_version=SAFETY_RULE_VERSION,
                            ),
                            *(
                                packet_evidence(packet, proposed.grounding_refs)
                                if packet is not None
                                else ()
                            ),
                        )
                    )
                    generation = (
                        GenerationMethodDetail(
                            GenerationMethod.RULE_ONLY,
                            SAFETY_RULE_ID,
                            SAFETY_RULE_VERSION,
                        )
                        if unresolved
                        else GenerationMethodDetail(
                            GenerationMethod.RULE_LLM,
                            LLM_INTEGRATION_RULE_ID,
                            MONTHLY_PROMPT_VERSION,
                        )
                    )
                else:
                    generation = GenerationMethodDetail(
                        GenerationMethod.RULE_LLM,
                        LLM_INTEGRATION_RULE_ID,
                        MONTHLY_PROMPT_VERSION,
                    )
                    parent_evidence = tuple(
                        source
                        for source in theme.evidence
                        if source.source_type is EvidenceSourceType.PARENT_PLAN
                    )
                    reference_evidence: tuple[EvidenceSource, ...] = ()
                    if proposed.reference_id is not None:
                        reference_evidence = (
                            EvidenceSource(
                                EvidenceSourceType.ACTIVITY_REFERENCE,
                                source_id=proposed.reference_id,
                                source_version=(
                                    catalog.catalog_version
                                    if catalog is not None
                                    else packet.lineage.activity_catalog_version
                                ),
                                display_name=proposed.value,
                            ),
                        )
                    evidence = deduplicate_evidence(
                        (
                            *parent_evidence,
                            *reference_evidence,
                            *(
                                packet_evidence(packet, proposed.grounding_refs)
                                if packet is not None
                                else ()
                            ),
                        )
                    )
                    if section.section_key == FOCUS_SECTION_KEY:
                        label_variant = LabelVariant.UNLABELED
                        mapping_confidence = MappingConfidence.HIGH
            elif section.section_key == THEME_SECTION_KEY:
                value = theme.value
                evidence = theme.evidence
                generation = theme.generation
            elif section.section_key == SAFETY_SECTION_KEY:
                evidence = (
                    EvidenceSource(
                        EvidenceSourceType.SAFETY_RULE,
                        source_id=safety_rule_version,
                        source_version=SAFETY_RULE_VERSION,
                    ),
                )
                generation = GenerationMethodDetail(
                    GenerationMethod.RULE_ONLY,
                    SAFETY_RULE_ID,
                    SAFETY_RULE_VERSION,
                )
            elif section.section_key == OUTDOOR_SECTION_KEY and catalog is not None:
                selection = select_activity_for_cell(
                    catalog.eligible_candidates(
                        section_key=OUTDOOR_PLAY_SLOT,
                        calendar_month=target_month.calendar_month,
                        ages=target_ages,
                    ),
                    calendar_month=target_month.calendar_month,
                    used_activity_ids=frozenset(used_activity_ids),
                    parent_theme_id=theme_reference_id(theme.evidence),
                )
                generation = GenerationMethodDetail(
                    GenerationMethod.RULE_ONLY,
                    ACTIVITY_RULE_ID,
                    ACTIVITY_RULE_VERSION,
                )
                if selection.candidate is not None:
                    value = selection.candidate.label
                    used_activity_ids.add(selection.candidate.activity_id)
                    evidence = deduplicate_evidence(
                        (
                            *(
                                source
                                for source in theme.evidence
                                if source.source_type is EvidenceSourceType.PARENT_PLAN
                            ),
                            EvidenceSource(
                                EvidenceSourceType.ACTIVITY_REFERENCE,
                                selection.candidate.activity_id,
                                catalog.catalog_version,
                                display_name=selection.candidate.label,
                            ),
                        )
                    )
                selection_results.append(
                    MonthlyActivitySelectionResult(week_id.value, selection.trace)
                )

            state = (
                CellState.EMPTY_UNRESOLVED
                if unresolved
                else resolve_cell_state(
                    section_key=section.section_key,
                    value=value,
                    assessment=(
                        safety_assessment
                        if section.section_key == SAFETY_SECTION_KEY
                        else None
                    ),
                )
            )
            item_id = self._ids.new_item_id()
            cells.append(
                MonthlyCell(
                    item_id=item_id,
                    section_key=section.section_key,
                    week_id=week_id,
                    value=value,
                    cell_state=state,
                    generation=generation,
                    evidence=evidence,
                    audit=AuditHistory(
                        (
                            AuditEvent(
                                AuditEventType.CREATED,
                                now,
                                plan_id,
                                item_id=item_id,
                                system_actor=SYSTEM_ACTOR,
                            ),
                        )
                    ),
                    source_label=section.source_label,
                    label_variant=label_variant,
                    mapping_confidence=mapping_confidence,
                )
            )
        return tuple(cells)

    @staticmethod
    def _require_complete(
        plan: MonthlyPlan, resolved_sections: tuple[ResolvedSection, ...]
    ) -> None:
        expected_keys = tuple(section.section_key for section in resolved_sections)
        if tuple(section.section_key for section in plan.sections) != expected_keys:
            raise MonthlyApplicationError(
                "monthly_plan_incomplete", "Generated sections do not match Template"
            )
        active_count = len(plan.active_week_periods)
        for resolved, section in zip(
            resolved_sections, plan.sections, strict=True
        ):
            if len(section.cells) != resolved.cell_count_for(active_count):
                raise MonthlyApplicationError(
                    "monthly_plan_incomplete",
                    f"Generated cell count is incomplete for {section.section_key}",
                )
        if any(cell.generation is None or not cell.audit.events for cell in plan.cells):
            raise MonthlyApplicationError(
                "monthly_plan_incomplete",
                "Every generated Cell requires generation and CREATED audit metadata",
            )
