"""W4b RegenerateWeeklyPlanCell (docs/weekly-plan-contract.md §10-3 · §10-1 · §8 · §11).

The FakeLLM answers from the request; scripted edits break one thing at a time. These
tests pin what the Application does with a proposal, never what a model writes.
"""

from __future__ import annotations

import json

import pytest

from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.planning.application import weekly_lifecycle
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.application.weekly_lifecycle import (
    ConfirmWeeklyPlan,
    ConfirmWeeklyPlanCommand,
    EditWeeklyPlanCell,
    EditWeeklyPlanCellCommand,
)
from ssuksak.planning.domain.errors import InvalidStateTransitionError
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.provenance import AuditEventType, EvidenceSourceType, GenerationMethod
from ssuksak.planning.planner.contracts import MONTHLY_MODEL, RawLlmResponse
from ssuksak.planning.planner.weekly import (
    WEEKLY_CELL_PROMPT_VERSION,
    WEEKLY_CELL_REPAIR_PROMPT_VERSION,
    WEEKLY_PROMPT_VERSION,
)

from tests.finalization.harness import TEACHER
from tests.finalization.weekly_harness import WEEK, WeeklyHarness

LLM = MonthlyGenerationMode.LLM_PLANNER
SAFETY_TEXT = "불이 나면 선생님을 따라 대피하는 길을 익혀요"


class Scripted:
    """RequestAwareWeeklyLlm, then one scripted edit per call (None = untouched)."""

    def __init__(self, *edits):
        self.edits, self.requests, self._base = list(edits), [], RequestAwareWeeklyLlm()

    def generate_weekly(self, request):
        self.requests.append(request)
        answer = json.loads(self._base.generate_weekly(request).content)
        edit = self.edits.pop(0) if self.edits else None
        if edit is not None:
            edit(answer)
        return RawLlmResponse(json.dumps(answer, ensure_ascii=False), MONTHLY_MODEL)


def _set(key, **fields):
    def edit(answer):
        next(s for s in answer["sections"] if s["section_key"] == key).update(fields)
    return edit


def _llm_weekly(harness, *, safety_text: str | None = None):
    draft = harness.monthly_parent(confirm=False, mode=LLM)
    if safety_text is not None:
        cell = draft.section("safety_education").cell_for_week(WEEK)
        draft = harness.edit_monthly(draft, item_id=cell.item_id, value=safety_text)
    return harness.generate_weekly(harness.confirm_monthly(draft), mode=LLM).plan


def _failure(call):
    with pytest.raises(MonthlyApplicationError) as excinfo:
        call()
    return excinfo.value.code


def _unchanged(harness, before):
    assert harness.weekly_plans.get(before.plan_id) == before  # nothing saved


def test_only_the_chosen_cell_changes_and_its_address_and_history_carry_over():
    harness = WeeklyHarness()
    before = _llm_weekly(harness)
    target = before.cell("goals")

    after = harness.regenerate_weekly(before, section_key="goals")

    cell = after.cell("goals")
    assert cell.item_id == target.item_id and cell.value != target.value
    assert cell.generation.method is GenerationMethod.RULE_LLM
    assert cell.generation.rule_version == WEEKLY_CELL_PROMPT_VERSION
    event = cell.audit.events[-1]
    assert event.event_type is AuditEventType.REGENERATED and event.actor_id == TEACHER
    assert (event.value_change.before, event.value_change.after) == (target.value, cell.value)
    assert event.generation_change.before == target.generation
    assert event.generation_change.before.rule_version == WEEKLY_PROMPT_VERSION
    assert event.generation_change.after == cell.generation
    assert cell.audit.events[:-1] == target.audit.events
    for other, previous in zip(after.cells, before.cells):
        if other.item_id != target.item_id:
            assert other == previous  # value, evidence, parent snapshots and audit untouched
    assert harness.weekly_plans.get(after.plan_id) == after


def test_the_cell_request_carries_one_target_inside_the_generation_range():
    harness = WeeklyHarness()
    before = _llm_weekly(harness)
    generation_request = harness.weekly_provider.requests[0]
    harness.regenerate_weekly(before, section_key="goals")
    request = harness.weekly_provider.requests[-1]

    assert request.prompt_version == WEEKLY_CELL_PROMPT_VERSION
    assert [t.section_key for t in request.targets] == ["goals"]
    assert request.target("goals") == generation_request.target("goals")  # same Rule-fixed range
    body = json.loads(request.user_content)
    assert body["task"] == "weekly_cell"
    assert "goals" not in body["current_plan"] and body["current_plan"]["theme"] == before.cell("theme").value
    assert {e["grounding_ref"] for e in body["evidence"]} <= set(request.target("goals").allowed_grounding_refs)


@pytest.mark.parametrize("key", ["theme", "focus", "basic_habit", "outdoor_play",
                                 "indoor_play", "group_activity", "indoor_alternative"])
def test_every_llm_written_section_regenerates_with_rule_attached_sources(key):
    harness = WeeklyHarness()
    before = _llm_weekly(harness)
    cell = harness.regenerate_weekly(before, section_key=key).cell(key)

    types = {s.source_type for s in cell.evidence}
    assert EvidenceSourceType.PARENT_PLAN in types
    if key == "outdoor_play":
        assert EvidenceSourceType.ACTIVITY_REFERENCE in types and cell.parent_snapshots
    if key in {"indoor_play", "group_activity", "indoor_alternative"}:
        refs = harness.weekly_provider.requests[-1].target(key).allowed_grounding_refs
        samples = {s.source_id for s in cell.evidence if s.source_type is EvidenceSourceType.INSTITUTION_SAMPLE}
        assert samples and samples <= set(refs)
        assert cell.parent_snapshots == ()


def test_the_safety_teacher_text_row_regenerates_and_cites_the_parent_cell():
    harness = WeeklyHarness()
    before = _llm_weekly(harness, safety_text=SAFETY_TEXT)
    cell = harness.regenerate_weekly(before, section_key="safety_education").cell("safety_education")
    assert SAFETY_TEXT in cell.value
    assert [s.snapshot_value for s in cell.parent_snapshots] == [SAFETY_TEXT]
    assert cell.safety is None


def test_a_wording_problem_is_repaired_once_with_the_cell_repair_prompt():
    harness = WeeklyHarness()
    before = _llm_weekly(harness)
    provider = Scripted(_set("goals", value="10월 3일 개천절 행사 준비"), None)
    cell = harness.regenerate_weekly(before, section_key="goals", provider=provider).cell("goals")
    assert len(provider.requests) == 2
    assert cell.generation.rule_version == WEEKLY_CELL_REPAIR_PROMPT_VERSION


@pytest.mark.parametrize(
    "edits",
    [
        (_set("goals", value="10월 3일 개천절 행사 준비"), _set("goals", value="10월 3일 개천절 행사 준비")),
        (lambda a: a["sections"].append({**a["sections"][0], "section_key": "theme"}),),  # not requested
        (_set("goals", grounding_refs=["ev_not_supplied"]),),
        (_set("goals", unresolved=True, value="", grounding_refs=[]),),  # no new value
        (lambda a: a.pop("sections"),),
    ],
)
def test_a_failed_cell_answer_saves_nothing_and_is_never_answered_by_rules(edits):
    harness = WeeklyHarness()
    before = _llm_weekly(harness)
    provider = Scripted(*edits)
    code = _failure(lambda: harness.regenerate_weekly(before, section_key="goals", provider=provider))
    assert code == "weekly_llm_cell_planning_failed"
    assert len(provider.requests) <= 2
    _unchanged(harness, before)


def test_a_date_the_teacher_wrote_in_a_teacher_input_cell_may_be_used():
    harness = WeeklyHarness()
    plan = _llm_weekly(harness)
    plan = EditWeeklyPlanCell(
        plan_repository=harness.weekly_plans, parent_plan_repository=harness.monthly_plans,
        clock=harness.clock, activity_repository=harness.activities,
    ).execute(EditWeeklyPlanCellCommand(plan.plan_id, plan.cell("event_schedule").item_id, "10월 9일 한글날 행사", TEACHER))
    provider = Scripted(_set("goals", value="10월 9일 한글날 행사를 함께 준비해요"))
    cell = harness.regenerate_weekly(plan, section_key="goals", provider=provider).cell("goals")
    assert "10월 9일" in cell.value and len(provider.requests) == 1


@pytest.mark.parametrize("key", ["family_link", "event_schedule", "special_program"])
def test_teacher_input_cells_are_not_regenerated(key):
    harness = WeeklyHarness()
    before = _llm_weekly(harness)
    assert _failure(lambda: harness.regenerate_weekly(before, section_key=key)) == "weekly_cell_not_regeneratable"
    _unchanged(harness, before)


def test_a_safety_cell_without_a_parent_teacher_sentence_is_not_regenerated():
    harness = WeeklyHarness()
    before = _llm_weekly(harness)
    code = _failure(lambda: harness.regenerate_weekly(before, section_key="safety_education"))
    assert code == "weekly_cell_not_regeneratable"


def test_a_section_without_a_rule_approved_basis_is_refused():
    harness = WeeklyHarness()
    before = harness.generate_weekly(
        harness.monthly_parent(mode=LLM), mode=LLM, weekly_classification=False
    ).plan
    code = _failure(lambda: harness.regenerate_weekly(before, section_key="indoor_play", weekly_classification=False))
    assert code == "weekly_cell_evidence_missing"
    _unchanged(harness, before)


def test_a_safety_grounding_error_in_the_new_value_blocks_the_save(monkeypatch):
    harness = WeeklyHarness()
    before = _llm_weekly(harness, safety_text=SAFETY_TEXT)
    real = weekly_lifecycle.llm_cell_sources

    def without_citation(*args, **kwargs):  # an Application bug: the parent citation is lost
        evidence, _ = real(*args, **kwargs)
        return evidence, ()

    monkeypatch.setattr(weekly_lifecycle, "llm_cell_sources", without_citation)
    code = _failure(lambda: harness.regenerate_weekly(before, section_key="safety_education"))
    assert code == "weekly_safety_verification_failed"
    _unchanged(harness, before)


def test_rule_only_outdoor_moves_to_another_candidate():
    harness = WeeklyHarness()
    before = harness.generate_weekly(harness.monthly_parent()).plan
    target = before.cell("outdoor_play")
    cell = harness.regenerate_weekly(before, section_key="outdoor_play").cell("outdoor_play")

    def activity(c):
        return next(s.source_id for s in c.evidence if s.source_type is EvidenceSourceType.ACTIVITY_REFERENCE)

    assert activity(cell) != activity(target) and cell.value != target.value
    assert cell.generation == target.generation  # RULE_ONLY, the same ranking rule
    assert cell.audit.events[-1].event_type is AuditEventType.REGENERATED


def test_rule_only_writes_no_text_so_other_sections_are_refused():
    harness = WeeklyHarness()
    before = harness.generate_weekly(harness.monthly_parent()).plan
    code = _failure(lambda: harness.regenerate_weekly(before, section_key="goals"))
    assert code == "rule_only_regeneration_unsupported"


def test_a_confirmed_plan_is_not_regenerated():
    harness = WeeklyHarness()
    plan = _llm_weekly(harness)
    ConfirmWeeklyPlan(
        plan_repository=harness.weekly_plans, parent_plan_repository=harness.monthly_plans,
        clock=harness.clock, activity_repository=harness.activities,
    ).execute(ConfirmWeeklyPlanCommand(plan.plan_id, TEACHER))
    confirmed = harness.weekly_plans.get(plan.plan_id)
    with pytest.raises(InvalidStateTransitionError):
        harness.regenerate_weekly(confirmed, section_key="goals")
