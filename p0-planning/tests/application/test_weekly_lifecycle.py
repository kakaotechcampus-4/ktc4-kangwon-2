"""W4a EditWeeklyPlanCell · ConfirmWeeklyPlan (docs/weekly-plan-contract.md §10-2 · §10-4 · §11-2)."""

from __future__ import annotations

import pytest

from ssuksak.planning.application import weekly_lifecycle
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.application.weekly_lifecycle import (
    ConfirmWeeklyPlan,
    ConfirmWeeklyPlanCommand,
    EditWeeklyPlanCell,
    EditWeeklyPlanCellCommand,
)
from ssuksak.planning.domain.errors import InvalidStateTransitionError
from ssuksak.planning.domain.identifiers import ItemId
from ssuksak.planning.domain.monthly_constraint import CellState
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType, GenerationMethod
from ssuksak.planning.rules.weekly_verification import (
    FACT_SCOPE_NOT_VERIFIED,
    PARENT_CITATION_INVALID,
)

from tests.finalization.harness import TEACHER
from tests.finalization.weekly_harness import WeeklyHarness

LLM = MonthlyGenerationMode.LLM_PLANNER


def _ports(harness):
    return dict(
        plan_repository=harness.weekly_plans,
        parent_plan_repository=harness.monthly_plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    )


def _edit(harness, plan, section_key, value, actor=TEACHER):
    return EditWeeklyPlanCell(**_ports(harness)).execute(
        EditWeeklyPlanCellCommand(plan.plan_id, plan.cell(section_key).item_id, value, actor)
    )


def _confirm(harness, plan, actor=TEACHER):
    return ConfirmWeeklyPlan(**_ports(harness)).execute(ConfirmWeeklyPlanCommand(plan.plan_id, actor))


def _weekly(harness, mode=MonthlyGenerationMode.RULE_ONLY):
    return harness.generate_weekly(harness.monthly_parent(mode=mode), mode=mode).plan


def _codes(plan, section_key=None):
    return [
        f.code for f in plan.verification_report.findings
        if section_key is None or f.location.section_key == section_key
    ]


def _failure(call):
    with pytest.raises(MonthlyApplicationError) as excinfo:
        call()
    return excinfo.value.code


def test_editing_a_generated_cell_keeps_its_generation_evidence_and_address():
    harness = WeeklyHarness()
    plan = _weekly(harness)
    before = plan.cell("outdoor_play")

    edited = _edit(harness, plan, "outdoor_play", "모래놀이")

    cell = edited.cell("outdoor_play")
    assert (cell.item_id, cell.section_key, cell.value) == (before.item_id, "outdoor_play", "모래놀이")
    assert cell.generation == before.generation  # TEACHER_EDITED is audit only (§10-2)
    assert cell.evidence == before.evidence and cell.parent_snapshots == before.parent_snapshots
    event = cell.audit.events[-1]
    assert event.event_type is AuditEventType.TEACHER_EDITED and event.actor_id == TEACHER
    assert (event.value_change.before, event.value_change.after) == (before.value, "모래놀이")
    assert event.generation_change is None
    assert [c for c in edited.cells if c.section_key != "outdoor_play"] == [
        c for c in plan.cells if c.section_key != "outdoor_play"
    ]
    assert harness.weekly_plans.get(plan.plan_id) == edited


def test_a_teacher_input_cell_becomes_manual_on_its_first_write_and_stays_manual():
    harness = WeeklyHarness()
    plan = _weekly(harness)
    assert plan.cell("event_schedule").generation is None

    plan = _edit(harness, plan, "event_schedule", "10월 9일 한글날 행사")
    assert plan.cell("event_schedule").generation.method is GenerationMethod.MANUAL
    plan = _edit(harness, plan, "event_schedule", "한글날 행사")
    plan = _edit(harness, plan, "event_schedule", "")
    cell = plan.cell("event_schedule")
    assert cell.generation.method is GenerationMethod.MANUAL and cell.cell_state is CellState.EMPTY_VALID
    # Decision 2026-10-21: MANUAL lives on the Cell; the audit records value changes only.
    edits = [e for e in cell.audit if e.event_type is AuditEventType.TEACHER_EDITED]
    assert len(edits) == 3 and all(e.generation_change is None for e in edits)


def test_filling_an_empty_rule_only_cell_keeps_rule_only():
    harness = WeeklyHarness()
    plan = _weekly(harness)
    before = plan.cell("indoor_play").generation

    cell = _edit(harness, plan, "indoor_play", "블록으로 우리 동네 만들기").cell("indoor_play")

    assert cell.generation == before and cell.generation.method is GenerationMethod.RULE_ONLY
    assert cell.cell_state is CellState.FILLED


@pytest.mark.parametrize(
    ("section_key", "value", "code"),
    [
        ("outdoor_play", None, "weekly_cell_value_unchanged"),  # None = the current value
        ("theme", "  ", "invalid_weekly_cell_value"),
        ("indoor_play", "  ", "invalid_weekly_cell_value"),  # blank -> another blank
        ("theme", 3, "invalid_weekly_cell_value"),
    ],
)
def test_edits_that_change_nothing_or_break_the_cell_are_refused(section_key, value, code):
    harness = WeeklyHarness()
    plan = _weekly(harness)
    value = plan.cell(section_key).value if value is None else value
    assert _failure(lambda: _edit(harness, plan, section_key, value)) == code
    assert harness.weekly_plans.get(plan.plan_id) == plan


def test_unknown_item_and_missing_actor_are_refused():
    harness = WeeklyHarness()
    plan = _weekly(harness)
    edit = EditWeeklyPlanCell(**_ports(harness))
    assert _failure(lambda: edit.execute(
        EditWeeklyPlanCellCommand(plan.plan_id, ItemId("item_not_here"), "x", TEACHER)
    )) == "weekly_cell_not_found"
    assert _failure(lambda: _edit(harness, plan, "theme", "가을", actor="teacher_001")) == "opaque_actor_required"
    assert _failure(lambda: _confirm(harness, plan, actor="담임 선생님")) == "opaque_actor_required"


def test_a_teacher_safety_sentence_is_not_checked_as_ai_grounding():
    # Decision 2026-10-21: AI-output rules skip a value the teacher wrote (§11-2).
    harness = WeeklyHarness()
    plan = _weekly(harness)

    edited = _edit(harness, plan, "safety_education", "놀이터에서 차례를 지켜요")

    assert PARENT_CITATION_INVALID not in _codes(edited)
    assert edited.cell("safety_education").cell_state is CellState.FILLED


def test_the_fact_scope_warning_stays_on_ai_text_and_leaves_teacher_text():
    harness = WeeklyHarness()
    plan = _weekly(harness, LLM)
    assert FACT_SCOPE_NOT_VERIFIED in _codes(plan, "goals")

    edited = _edit(harness, plan, "goals", "친구와 함께 놀이를 즐긴다")

    assert FACT_SCOPE_NOT_VERIFIED not in _codes(edited, "goals")
    assert FACT_SCOPE_NOT_VERIFIED in _codes(edited, "theme")


@pytest.mark.parametrize("run", [_edit, _confirm])
def test_a_verifier_that_cannot_run_saves_nothing(monkeypatch, run):
    harness = WeeklyHarness()
    plan = _weekly(harness)

    def broken(*_):
        raise RuntimeError("verifier down")

    monkeypatch.setattr(weekly_lifecycle, "verify_weekly_plan", broken)
    args = ("theme", "가을 놀이") if run is _edit else ()
    assert _failure(lambda: run(harness, plan, *args)) == "weekly_verification_failed"
    assert harness.weekly_plans.get(plan.plan_id) == plan


def test_confirm_records_the_actor_and_is_idempotent():
    harness = WeeklyHarness()
    plan = _weekly(harness)

    confirmed = _confirm(harness, plan)

    assert confirmed.status is PlanStatus.CONFIRMED
    event = confirmed.audit.events[-1]
    assert event.event_type is AuditEventType.CONFIRMED and event.actor_id == TEACHER
    assert confirmed.verification_report is not None
    saves = harness.weekly_plans.save_count
    assert _confirm(harness, confirmed) == confirmed  # retry: stored Plan, no new event
    assert harness.weekly_plans.save_count == saves


def test_findings_do_not_block_confirmation():
    harness = WeeklyHarness()
    plan = _weekly(harness, LLM)
    assert plan.verification_report.findings  # fact-scope NOT_VERIFIED on AI text
    assert _confirm(harness, plan).status is PlanStatus.CONFIRMED


def test_a_confirmed_plan_is_read_only():
    harness = WeeklyHarness()
    confirmed = _confirm(harness, _weekly(harness))
    with pytest.raises(InvalidStateTransitionError):
        _edit(harness, confirmed, "theme", "새 주제")
    assert harness.weekly_plans.get(confirmed.plan_id) == confirmed
