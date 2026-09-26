from __future__ import annotations

from datetime import timedelta

import pytest

from ssuksak.adapters.deterministic import FixedClock
from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.edit_yearly_plan_item import EditYearlyPlanItem
from ssuksak.planning.application.monthly_dto import (
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.application.yearly_dto import EditYearlyPlanItemCommand
from ssuksak.planning.domain.errors import InvalidStateTransitionError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_constraint import (
    CellState,
    ConstraintVerification,
)
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.monthly_verification import VerificationSourceRef
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.rules.monthly_verification import AGE_FREE_TEXT_NOT_VERIFIED_CODE, AGE_RULE_REF

from .harness import ACTIVITY_CATALOG, NOW, PlanningHarness, TEACHER


def _assert_fresh_age_report(plan, previous=None):
    """Only the implemented age rule runs; deferred rules never appear in coverage."""
    report = plan.verification_report
    assert report is not None
    assert report is not getattr(previous, "verification_report", None)
    assert report.target_plan_id == plan.plan_id
    assert report.executed_rules == (AGE_RULE_REF,)
    assert report.source_refs == (
        VerificationSourceRef(ACTIVITY_CATALOG.catalog_id, ACTIVITY_CATALOG.catalog_version),
    )


def test_full_yearly_to_monthly_core_flow_and_final_locks():
    harness = PlanningHarness()

    yearly_generated = harness.generate_yearly().plan
    first_evidence = yearly_generated.periods[0].theme.evidence
    yearly_edited = harness.edit_yearly(
        yearly_generated,
        index=0,
        value="Teacher-authored March theme",
    )
    edited_item = yearly_edited.periods[0].theme
    assert edited_item.generation == yearly_generated.periods[0].theme.generation
    assert edited_item.evidence == first_evidence
    assert edited_item.audit.events[-1].event_type is AuditEventType.TEACHER_EDITED

    yearly_regenerated = harness.regenerate_yearly(yearly_edited, index=2).plan
    regenerated_item = yearly_regenerated.periods[2].theme
    generation_change = regenerated_item.audit.events[-1].generation_change
    assert regenerated_item.audit.events[-1].event_type is AuditEventType.REGENERATED
    assert generation_change is not None
    assert generation_change.before.rule_id and generation_change.after.rule_id

    with pytest.raises(MonthlyApplicationError) as gate_error:
        harness.generate_monthly(
            yearly_regenerated, MonthlyGenerationMode.LLM_PLANNER
        )
    assert gate_error.value.code == "parent_yearly_plan_must_be_confirmed"
    assert harness.monthly_plans.save_count == 0
    assert harness.provider.monthly_requests == []

    yearly_confirmed = harness.confirm_yearly(yearly_regenerated)
    assert yearly_confirmed.status is PlanStatus.CONFIRMED
    assert yearly_confirmed.audit.events[-1].actor_id == TEACHER

    monthly_result = harness.generate_monthly(
        yearly_confirmed, MonthlyGenerationMode.LLM_PLANNER
    )
    monthly_generated = monthly_result.plan
    assert monthly_generated.status is PlanStatus.DRAFT
    assert monthly_generated.template_ref.template_version == (
        "monthly-template-a-v0.2.0"
    )
    assert len(monthly_generated.active_week_periods) == 5
    assert monthly_result.context_packet_fingerprint
    assert harness.provider.monthly_requests[0].reference_labels
    assert monthly_generated.parent_lineage.parent_plan_id == yearly_confirmed.plan_id
    assert monthly_generated.parent_lineage.snapshot_value == (
        monthly_generated.section("theme").cells[0].value
    )
    _assert_fresh_age_report(monthly_generated)
    # Free-text outdoor weeks are explicitly NOT_VERIFIED; the reference week has no finding.
    free_text = [c for c in monthly_generated.section("outdoor_play").cells
                 if not any(e.source_type is EvidenceSourceType.ACTIVITY_REFERENCE for e in c.evidence)]
    assert [(f.code, f.location.week_id) for f in monthly_generated.verification_report.findings] == [
        (AGE_FREE_TEXT_NOT_VERIFIED_CODE, c.week_id) for c in free_text]

    theme_cell = monthly_generated.section("theme").cells[0]
    assert {source.source_type for source in theme_cell.evidence} == {
        EvidenceSourceType.PARENT_PLAN,
        EvidenceSourceType.THEME_REFERENCE,
    }
    first_outdoor = monthly_generated.section("outdoor_play").cells[0]
    assert any(
        source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
        for source in first_outdoor.evidence
    )

    safety = monthly_generated.section("safety_education")
    assert all(cell.cell_state is CellState.EMPTY_UNRESOLVED for cell in safety.cells)
    assessment = monthly_generated.constraint("STATUTORY_SAFETY_EDUCATION")
    assert assessment is not None
    assert (
        assessment.verification
        is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    )

    outdoor_evidence = first_outdoor.evidence
    monthly_edited = harness.edit_monthly(
        monthly_generated,
        item_id=first_outdoor.item_id,
        value="Teacher-authored outdoor play",
    )
    edited_outdoor = monthly_edited.find_cell(first_outdoor.item_id)[3]
    assert edited_outdoor.generation == first_outdoor.generation
    assert edited_outdoor.evidence == outdoor_evidence
    assert edited_outdoor.audit.events[-1].event_type is AuditEventType.TEACHER_EDITED
    _assert_fresh_age_report(monthly_edited, monthly_generated)

    first_focus = monthly_edited.section("focus").cells[0]
    monthly_regeneration = harness.regenerate_monthly(
        monthly_edited, item_id=first_focus.item_id
    )
    monthly_regenerated = monthly_regeneration.plan
    regenerated_focus = monthly_regenerated.find_cell(first_focus.item_id)[3]
    change = regenerated_focus.audit.events[-1].generation_change
    assert change is not None
    assert change.before.rule_version != change.after.rule_version
    assert any(
        source.source_type is EvidenceSourceType.INSTITUTION_SAMPLE
        for source in regenerated_focus.evidence
    )
    assert all(
        cell.cell_state is CellState.EMPTY_UNRESOLVED
        for cell in monthly_regenerated.section("safety_education").cells
    )
    _assert_fresh_age_report(monthly_regenerated, monthly_edited)

    monthly_confirmed = harness.confirm_monthly(monthly_regenerated)
    assert monthly_confirmed.status is PlanStatus.CONFIRMED
    assert monthly_confirmed.audit.events[-1].actor_id == TEACHER
    _assert_fresh_age_report(monthly_confirmed, monthly_regenerated)
    assert monthly_confirmed.constraint(
        "STATUTORY_SAFETY_EDUCATION"
    ).verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    assert harness.yearly_plans.save_count == 4
    assert harness.monthly_plans.save_count == 4
    assert len(harness.provider.monthly_requests) == 1
    assert len(harness.provider.cell_requests) == 1

    with pytest.raises(InvalidStateTransitionError):
        EditYearlyPlanItem(
            plan_repository=harness.yearly_plans, clock=harness.clock
        ).execute(
            EditYearlyPlanItemCommand(
                yearly_confirmed.plan_id,
                yearly_confirmed.periods[0].theme.item_id,
                "locked",
                TEACHER,
            )
        )
    with pytest.raises(InvalidStateTransitionError):
        EditMonthlyPlanItem(
            plan_repository=harness.monthly_plans,
            clock=harness.clock,
            activity_repository=harness.activities,
        ).execute(
            EditMonthlyPlanItemCommand(
                monthly_confirmed.plan_id,
                regenerated_focus.item_id,
                "locked",
                TEACHER,
            )
        )
    with pytest.raises(InvalidStateTransitionError):
        RegenerateMonthlyPlanItem(
            plan_repository=harness.monthly_plans,
            clock=harness.clock,
            activity_repository=harness.activities,
            context_pipeline=harness.context,
        ).execute(
            RegenerateMonthlyPlanItemCommand(
                monthly_confirmed.plan_id,
                regenerated_focus.item_id,
                TEACHER,
            )
        )
    saves_before_retry = harness.monthly_plans.save_count
    retried = ConfirmMonthlyPlan(
        plan_repository=harness.monthly_plans,
        clock=FixedClock(NOW + timedelta(days=1)),
        activity_repository=harness.activities,
    ).execute(ConfirmMonthlyPlanCommand(monthly_confirmed.plan_id, ActorId("teacher_002")))
    confirmations = [
        event for event in retried.audit.events
        if event.event_type is AuditEventType.CONFIRMED
    ]
    assert retried is monthly_confirmed
    assert harness.monthly_plans.get(monthly_confirmed.plan_id) is monthly_confirmed
    assert harness.monthly_plans.save_count == saves_before_retry
    assert [(event.actor_id, event.occurred_at) for event in confirmations] == [(TEACHER, NOW)]
    assert retried.verification_report is monthly_confirmed.verification_report


def test_safety_cells_are_never_llm_regeneration_targets():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    plan = harness.generate_monthly(
        parent, MonthlyGenerationMode.LLM_PLANNER
    ).plan
    safety_cell = plan.section("safety_education").cells[0]
    calls_before = len(harness.provider.cell_requests)

    with pytest.raises(MonthlyApplicationError) as error:
        harness.regenerate_monthly(plan, item_id=safety_cell.item_id)

    assert error.value.code == "monthly_cell_not_regeneratable"
    assert len(harness.provider.cell_requests) == calls_before
    assert harness.monthly_plans.get(plan.plan_id) is plan
