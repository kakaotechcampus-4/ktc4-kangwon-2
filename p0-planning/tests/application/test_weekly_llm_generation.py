"""W3b GenerateWeeklyPlan LLM_PLANNER path (W1 §10-1 · §11 and the 2026-10-21 decisions).

The FakeLLM answers from the request; scripted edits break one thing at a time. These
tests pin what the Application does with a proposal, never what a model writes.
"""

from __future__ import annotations

import json

import pytest

from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.planning.application.generate_weekly_plan import (
    GenerateWeeklyPlan,
    GenerateWeeklyPlanCommand,
)
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.provenance import EvidenceSourceType, GenerationMethod
from ssuksak.planning.domain.weekly_plan import WEEKDAYS
from ssuksak.planning.planner.contracts import MONTHLY_MODEL, RawLlmResponse
from ssuksak.planning.planner.weekly import (
    WEEKLY_PROMPT_VERSION,
    WEEKLY_REPAIR_PROMPT_VERSION,
    unsupported_facts,
)
from ssuksak.planning.rules.weekly_verification import FACT_SCOPE_NOT_VERIFIED

from tests.finalization.harness import ACTIVITY_CATALOG, SAFETY_RULE
from tests.finalization.weekly_harness import WEEK, WEEKLY_TEMPLATE, WeeklyHarness

LLM = MonthlyGenerationMode.LLM_PLANNER
SAFETY_TEXT = "10월 2일 소방서 견학 전에 불이 나면 대피하는 길을 익혀요"


class Scripted:
    """RequestAwareWeeklyLlm, then one scripted edit per call (None = untouched)."""

    def __init__(self, *edits):
        self.edits, self.requests, self._base = list(edits), [], RequestAwareWeeklyLlm()

    def generate_weekly(self, request):
        self.requests.append(request)
        answer = json.loads(self._base.generate_weekly(request).content)
        edit = self.edits.pop(0) if self.edits else None
        if isinstance(edit, Exception):
            raise edit
        if edit is not None:
            edit(answer)
        return RawLlmResponse(json.dumps(answer, ensure_ascii=False), MONTHLY_MODEL)


def _set(key, **fields):
    def edit(answer):
        next(s for s in answer["sections"] if s["section_key"] == key).update(fields)
    return edit


def _add(section):
    return lambda answer: answer["sections"].append(section)


def _parent(harness, *, safety_text: str | None = None):
    """LLM monthly parent (it has a focus); optionally the teacher wrote this week's safety cell."""
    draft = harness.monthly_parent(confirm=False, mode=LLM)
    if safety_text is not None:
        cell = draft.section("safety_education").cell_for_week(WEEK)
        draft = harness.edit_monthly(draft, item_id=cell.item_id, value=safety_text)
    return harness.confirm_monthly(draft)


def _failed(harness, parent, provider):
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(parent, mode=LLM, provider=provider)
    assert excinfo.value.code == "weekly_llm_planning_failed"
    assert len(harness.weekly_plans) == 0  # nothing saved, no rule fallback (§10-1)
    return excinfo.value.__cause__


def test_request_carries_what_the_rule_fixed():
    harness = WeeklyHarness()
    parent = _parent(harness, safety_text=SAFETY_TEXT)
    harness.generate_weekly(parent, mode=LLM)
    request = harness.weekly_provider.requests[0]

    keys = [t.section_key for t in request.targets]
    assert keys[0] == "theme" and {"outdoor_play", "safety_education", "focus"} <= set(keys)
    assert not set(keys) & request.teacher_input_keys  # teacher input is never a target
    assert not {"indoor_play", "group_activity", "indoor_alternative"} & set(keys)  # W3c
    focus = request.target("focus")
    parent_focus = next(s for s in parent.template_snapshot.sections if s.section_key == "focus")
    assert focus.semantic_variant == parent_focus.semantic_variant.value  # F1
    assert request.reference_candidates and len(request.reference_candidates) <= 12
    assert SAFETY_TEXT in request.allowed_fact_text


def test_safety_teacher_text_row_cites_exactly_that_parent_cell():
    harness = WeeklyHarness()
    parent = _parent(harness, safety_text=SAFETY_TEXT)
    safety = harness.generate_weekly(parent, mode=LLM).plan.cell("safety_education")

    parent_cell = parent.section("safety_education").cell_for_week(WEEK)
    assert safety.generation.method is GenerationMethod.RULE_LLM
    assert [(s.parent_item_id, s.snapshot_value) for s in safety.parent_snapshots] == [
        (parent_cell.item_id, SAFETY_TEXT)
    ]
    assert [s.source_type for s in safety.evidence] == [EvidenceSourceType.PARENT_PLAN]
    assert safety.safety is None  # no placement or legal category is claimed


def test_parent_value_alone_grounds_focus_and_inheriting_its_wording_is_no_copy():
    harness = WeeklyHarness()
    parent = _parent(harness)
    parent_focus = parent.section("focus").cell_for_week(WEEK).value
    provider = Scripted(_set("focus", value=parent_focus, grounding_refs=[]))

    focus = harness.generate_weekly(parent, mode=LLM, provider=provider).plan.cell("focus")

    assert focus.value == parent_focus  # Q1
    assert [s.source_type for s in focus.evidence] == [EvidenceSourceType.PARENT_PLAN]
    assert len(provider.requests) == 1


def test_unsupported_date_is_repaired_once_and_only_that_cell_carries_the_repair_prompt():
    harness = WeeklyHarness()
    provider = Scripted(_set("theme", value="10월 3일 개천절 행사 준비"), None)
    plan = harness.generate_weekly(_parent(harness), mode=LLM, provider=provider).plan

    assert len(provider.requests) == 2
    assert plan.cell("theme").generation.rule_version == WEEKLY_REPAIR_PROMPT_VERSION
    assert plan.cell("goals").generation.rule_version == WEEKLY_PROMPT_VERSION


@pytest.mark.parametrize("value", ["10월 3일 개천절 행사 준비", "김민지 선생님과 함께 놀아요", "김 선생님과 요리해요"])
def test_unsupported_date_or_name_that_survives_the_repair_saves_nothing(value):
    harness = WeeklyHarness()
    provider = Scripted(_set("theme", value=value), _set("theme", value=value))
    cause = _failed(harness, _parent(harness), provider)
    assert cause.validation_codes == ("UNSUPPORTED_FACT",)
    assert len(provider.requests) == 2  # one repair, never a third call


def test_a_date_that_is_in_the_inputs_may_be_named():
    harness = WeeklyHarness()
    plan = harness.generate_weekly(_parent(harness, safety_text=SAFETY_TEXT), mode=LLM).plan
    assert "10월 2일" in plan.cell("safety_education").value


def test_common_words_are_not_taken_for_people():
    text = "오늘 날씨가 맑아요. 부모님, 원장님, 담임 선생님과 손님 놀이를 하고 씨앗을 심어요. 2시간 동안 놀아요"
    assert unsupported_facts(text, "") == ()


@pytest.mark.parametrize(
    "text",
    ["우리 선생님과 함께 산책해요", "공주님 놀이", "왕자님과 공주님", "1/2 크기로 잘라요", "박지민님 발표",
     "이 선생님께 물어봐요", "반 선생님과 인사해요", "요리 선생님"],
)
def test_nim_ssi_and_slash_numbers_are_not_blocked(text):
    # Q2 scope narrowed 2026-10-21: only dates, weekdays, clock times and a name before 선생님
    # block; the rest is left to the NOT_VERIFIED fact-scope warning.
    assert unsupported_facts(text, "") == ()


@pytest.mark.parametrize(
    ("edit", "code"),
    [
        (_add({"section_key": "event_schedule", "value": "운동회", "unresolved": False,
               "grounding_refs": [], "reference_id": None}), "TEACHER_INPUT_VALUE"),
        (_add({"section_key": "indoor_play", "value": "블록 놀이", "unresolved": False,
               "grounding_refs": [], "reference_id": None}), "SECTION_NOT_REQUESTED"),
        (_set("goals", grounding_refs=["ev_not_supplied"]), "UNKNOWN_GROUNDING_REF"),
        (_set("outdoor_play", reference_id="act_not_a_candidate"), "UNKNOWN_REFERENCE_ID"),
        (_set("theme", unresolved=True, value=""), "THEME_REQUIRED"),
    ],
)
def test_contract_breaks_fail_closed_without_a_repair(edit, code):
    harness = WeeklyHarness()
    provider = Scripted(edit)
    cause = _failed(harness, _parent(harness), provider)
    assert code in cause.validation_codes
    assert len(provider.requests) == 1


def test_other_section_ref_is_repairable_and_fails_if_it_stays():
    harness = WeeklyHarness()
    parent = _parent(harness)
    probe = WeeklyHarness()
    probe.generate_weekly(_parent(probe), mode=LLM)
    habit_ref = probe.weekly_provider.requests[0].target("basic_habit").allowed_grounding_refs[0]
    provider = Scripted(_set("goals", grounding_refs=[habit_ref]), _set("goals", grounding_refs=[habit_ref]))
    cause = _failed(harness, parent, provider)
    assert cause.validation_codes == ("WRONG_SOURCE_GROUNDING",)


def test_malformed_proposal_and_provider_failure_are_not_answered_by_rules():
    harness = WeeklyHarness()
    parent = _parent(harness)
    _failed(harness, parent, Scripted(lambda answer: answer.pop("sections")))
    _failed(harness, parent, Scripted(RuntimeError("timeout")))


def test_ai_written_cells_carry_a_fact_scope_not_verified_finding():
    harness = WeeklyHarness()
    plan = harness.generate_weekly(_parent(harness), mode=LLM).plan
    flagged = {f.location.section_key for f in plan.verification_report.findings if f.code == FACT_SCOPE_NOT_VERIFIED}
    written = {c.section_key for c in plan.cells if c.generation and c.generation.method is GenerationMethod.RULE_LLM}
    assert flagged == written and "theme" in flagged


def test_llm_mode_requires_the_planner_dependencies():
    harness = WeeklyHarness()
    parent = _parent(harness)
    use_case = GenerateWeeklyPlan(
        parent_plan_repository=harness.monthly_plans,
        plan_repository=harness.weekly_plans,
        template_repository=harness.weekly_generation_templates,
        safety_repository=harness.safety,
        clock=harness.clock,
        id_generator=harness.weekly_ids,
        activity_repository=harness.activities,
    )
    with pytest.raises(MonthlyApplicationError) as excinfo:
        use_case.execute(GenerateWeeklyPlanCommand(
            parent.plan_id, WEEK, WEEKDAYS, WEEKLY_TEMPLATE, SAFETY_RULE, LLM, ACTIVITY_CATALOG
        ))
    assert excinfo.value.code == "weekly_llm_dependencies_required"
