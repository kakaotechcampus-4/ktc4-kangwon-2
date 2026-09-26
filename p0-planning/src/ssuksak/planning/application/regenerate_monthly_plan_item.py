"""Regenerate one supported DRAFT Monthly Cell without changing siblings."""

from __future__ import annotations

from dataclasses import replace

from ..domain.activity_reference import OUTDOOR_PLAY_SLOT
from ..domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from ..domain.monthly_template import DisplayMode
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodChange,
    GenerationMethodDetail,
    ValueChange,
)
from ..planner.cell_service import MonthlyCellPlanner
from ..planner.contracts import (
    MONTHLY_CELL_PROMPT_VERSION,
    FOCUS_SECTION_KEY,
    OUTDOOR_SECTION_KEY,
    MonthlyCellSnapshot,
)
from ..rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
    select_activity_for_cell,
)
from ..rules.monthly_cell_state import resolve_cell_state
from .generate_monthly_plan import LLM_INTEGRATION_RULE_ID
from .monthly_dto import (
    ActivityCatalogSelector,
    MonthlyActivitySelectionResult,
    RegenerateMonthlyPlanItemCommand,
    RegenerateMonthlyPlanItemResult,
)
from .monthly_errors import MonthlyApplicationError
from .monthly_support import (
    MonthlyContextPipeline,
    deduplicate_evidence,
    load_activity_catalog,
    packet_evidence,
    require_actor,
    require_item_id,
    require_monthly_plan,
    snapshot_grounding_classes,
    theme_reference_id,
    with_fresh_monthly_verification,
)
from .ports import ActivityReferenceRepository, Clock, PlanRepository

SUPPORTED_SECTIONS = frozenset({FOCUS_SECTION_KEY, OUTDOOR_SECTION_KEY})


class RegenerateMonthlyPlanItem:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[MonthlyPlan],
        clock: Clock,
        activity_repository: ActivityReferenceRepository | None = None,
        context_pipeline: MonthlyContextPipeline | None = None,
        cell_planner: MonthlyCellPlanner | None = None,
    ) -> None:
        self._plans = plan_repository
        self._clock = clock
        self._activities = activity_repository
        self._context = context_pipeline
        self._cell_planner = cell_planner

    def execute(
        self, command: RegenerateMonthlyPlanItemCommand
    ) -> RegenerateMonthlyPlanItemResult:
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("regenerate")
        item_id = require_item_id(command.item_id)
        actor_id = require_actor(command.actor_id)
        found = plan.find_cell(item_id)
        if found is None:
            raise MonthlyApplicationError(
                "monthly_cell_not_found", f"Monthly Cell not found: {item_id}"
            )
        _, _, _, cell = found
        if cell.section_key not in SUPPORTED_SECTIONS or cell.week_id is None:
            raise MonthlyApplicationError(
                "monthly_cell_not_regeneratable",
                f"Cell section is not regeneratable: {cell.section_key}",
            )
        if cell.generation is None:
            raise MonthlyApplicationError(
                "monthly_cell_generation_missing",
                "Regeneration requires the previous Generation Method",
            )

        if plan.generation_mode is MonthlyGenerationMode.RULE_ONLY:
            result = self._regenerate_rule_only(plan, cell, actor_id)
        else:
            result = self._regenerate_with_llm(plan, cell, actor_id)
        catalog = self._catalog_for(result.plan)
        result = replace(
            result,
            plan=with_fresh_monthly_verification(result.plan, catalog),
        )
        self._plans.save(result.plan.plan_id, result.plan)
        return result

    def _catalog_for(self, plan: MonthlyPlan):
        if plan.activity_catalog_ref is None:
            return None
        return load_activity_catalog(
            self._activities,
            ActivityCatalogSelector(
                plan.activity_catalog_ref.catalog_id,
                plan.activity_catalog_ref.catalog_version,
            ),
        )

    def _regenerate_rule_only(self, plan, cell, actor_id):
        if cell.section_key != OUTDOOR_SECTION_KEY:
            raise MonthlyApplicationError(
                "rule_only_focus_regeneration_unsupported",
                "RULE_ONLY mode has no deterministic focus text generator",
            )
        catalog = self._catalog_for(plan)
        if catalog is None:
            raise MonthlyApplicationError(
                "activity_catalog_required",
                "RULE_ONLY outdoor regeneration requires its exact Activity Catalog",
            )
        current_id = _activity_reference_id(cell.evidence)
        used_ids = frozenset(
            source.source_id
            for other in plan.cells
            if other.item_id != cell.item_id
            and other.section_key == OUTDOOR_SECTION_KEY
            for source in other.evidence
            if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
        )
        theme = _theme_cell(plan)
        selection = select_activity_for_cell(
            catalog.eligible_candidates(
                section_key=OUTDOOR_PLAY_SLOT,
                calendar_month=plan.target_month.calendar_month,
                ages=plan.target_ages,
            ),
            calendar_month=plan.target_month.calendar_month,
            used_activity_ids=used_ids,
            current_activity_id=current_id,
            parent_theme_id=theme_reference_id(theme.evidence),
        )
        if selection.candidate is None:
            raise MonthlyApplicationError(
                "no_activity_candidate",
                "No eligible Activity candidate is available for regeneration",
            )
        generation = GenerationMethodDetail(
            GenerationMethod.RULE_ONLY,
            ACTIVITY_RULE_ID,
            ACTIVITY_RULE_VERSION,
        )
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
        updated = self._replace_regenerated(
            plan,
            cell,
            new_value=selection.candidate.label,
            generation=generation,
            evidence=evidence,
            actor_id=actor_id,
        )
        return RegenerateMonthlyPlanItemResult(
            updated,
            activity_selection=MonthlyActivitySelectionResult(
                cell.week_id.value, selection.trace
            ),
        )

    def _regenerate_with_llm(self, plan, cell, actor_id):
        if self._context is None or self._cell_planner is None:
            raise MonthlyApplicationError(
                "monthly_llm_dependencies_required",
                "LLM_PLANNER regeneration requires Context Pipeline and Cell Planner",
            )
        catalog = self._catalog_for(plan)
        theme = _theme_cell(plan)
        packet = self._context.build(
            target_month=plan.target_month,
            ages=plan.target_ages,
            parent_theme_id=theme_reference_id(theme.evidence),
            parent_theme_value=theme.value,
            week_periods=plan.week_periods,
            activity_catalog=catalog,
            constraint_assessments=plan.constraint_assessments,
            grounding_classes=snapshot_grounding_classes(plan.template_snapshot),
        )
        snapshot = _month_snapshot(plan)
        try:
            outcome = self._cell_planner.plan(
                packet,
                plan.template_snapshot,
                target_week_id=cell.week_id,
                target_section_key=cell.section_key,
                month_snapshot=snapshot,
            )
        except Exception as exc:
            raise MonthlyApplicationError(
                "monthly_llm_cell_planning_failed",
                "Monthly Cell planning failed before the Plan was saved",
            ) from exc
        proposal = outcome.proposal.section
        parent_evidence = tuple(
            source
            for source in theme.evidence
            if source.source_type is EvidenceSourceType.PARENT_PLAN
        )
        reference_evidence: tuple[EvidenceSource, ...] = ()
        if proposal.reference_id is not None:
            reference_evidence = (
                EvidenceSource(
                    EvidenceSourceType.ACTIVITY_REFERENCE,
                    proposal.reference_id,
                    catalog.catalog_version if catalog is not None else None,
                    display_name=proposal.value,
                ),
            )
        evidence = deduplicate_evidence(
            (
                *parent_evidence,
                *reference_evidence,
                *packet_evidence(packet, proposal.grounding_refs),
            )
        )
        generation = GenerationMethodDetail(
            GenerationMethod.RULE_LLM,
            LLM_INTEGRATION_RULE_ID,
            MONTHLY_CELL_PROMPT_VERSION,
        )
        updated = self._replace_regenerated(
            plan,
            cell,
            new_value=proposal.value,
            generation=generation,
            evidence=evidence,
            actor_id=actor_id,
        )
        return RegenerateMonthlyPlanItemResult(updated, planner_outcome=outcome)

    def _replace_regenerated(
        self,
        plan,
        cell,
        *,
        new_value,
        generation,
        evidence,
        actor_id,
    ):
        event = AuditEvent(
            AuditEventType.REGENERATED,
            self._clock.now(),
            plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=ValueChange(cell.value, new_value),
            generation_change=GenerationMethodChange(cell.generation, generation),
        )
        updated_cell = replace(
            cell,
            value=new_value,
            cell_state=resolve_cell_state(
                section_key=cell.section_key,
                value=new_value,
                assessment=plan.constraint("STATUTORY_SAFETY_EDUCATION"),
            ),
            generation=generation,
            evidence=evidence,
            audit=cell.audit.append(event),
        )
        return plan.replace_cell(cell.item_id, updated_cell)


def _theme_cell(plan: MonthlyPlan):
    section = plan.section("theme")
    if section is None or len(section.cells) != 1:
        raise MonthlyApplicationError(
            "monthly_theme_cell_required", "Monthly Plan requires one Theme Cell"
        )
    return section.cells[0]


def _activity_reference_id(evidence) -> str | None:
    return next(
        (
            source.source_id
            for source in evidence
            if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
        ),
        None,
    )


def _month_snapshot(
    plan: MonthlyPlan,
) -> tuple[MonthlyCellSnapshot, ...]:
    weekly_sections = tuple(
        section
        for section in plan.sections
        if section.display_mode is DisplayMode.WEEKLY_CELLS
    )
    return tuple(
        MonthlyCellSnapshot(
            period.week_id,
            tuple(
                (
                    section.section_key,
                    (
                        section.cell_for_week(period.week_id).value
                        if section.cell_for_week(period.week_id) is not None
                        else ""
                    ),
                )
                for section in weekly_sections
            ),
        )
        for period in plan.active_week_periods
    )
