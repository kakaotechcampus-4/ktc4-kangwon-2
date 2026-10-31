"""ADR-051 step 2: per-day group_activity on weekly-template-a-v0.2.0 (FakeLLM, no network).

Contract assertions, not model wording. The v0.1.0 Goldens stay the regression guard for the
unchanged path (same prompt versions, same cells).
"""

from __future__ import annotations

import json

import pytest

from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.planning.application.generate_weekly_plan import WeeklyApplicationError
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.provenance import GenerationMethod
from ssuksak.planning.domain.weekly_plan import (
    WEEKDAYS,
    WEEKDAYS_WITH_SATURDAY,
    OperatingDay,
)
from ssuksak.planning.planner.contracts import RawLlmResponse

from .weekly_harness import WEEKLY_DAY_TEMPLATE, WeeklyHarness

LLM = MonthlyGenerationMode.LLM_PLANNER


class _Edited(RequestAwareWeeklyLlm):
    """The request-aware answer with group_activity days changed by ``edit`` (first call only)."""

    def __init__(self, edit) -> None:
        super().__init__()
        self._edit = edit

    def generate_weekly(self, request):
        response = super().generate_weekly(request)
        if len(self.requests) > 1:
            return response
        body = json.loads(response.content)
        for section in body["sections"]:
            if section["section_key"] == "group_activity":
                section["days"] = self._edit(section["days"])
        return RawLlmResponse(content=json.dumps(body, ensure_ascii=False), model=response.model)


def _generate(harness, days=WEEKDAYS, provider=None):
    parent = harness.monthly_parent(mode=LLM)
    return harness.generate_weekly(
        parent, mode=LLM, operating_days=days, template_ref=WEEKLY_DAY_TEMPLATE, provider=provider
    ).plan


def _days(plan, key):
    return [cell for cell in plan.cells if cell.section_key == key]


@pytest.mark.parametrize("days", [WEEKDAYS, WEEKDAYS_WITH_SATURDAY])
def test_group_activity_is_written_per_operating_day(days):
    harness = WeeklyHarness()
    plan = _generate(harness, days)

    group = _days(plan, "group_activity")
    assert [cell.day for cell in group] == list(days)
    assert len({cell.value for cell in group}) == len(days)
    assert {cell.generation.method for cell in group} == {GenerationMethod.RULE_LLM}
    assert {cell.generation.rule_version for cell in group} == {"weekly-planner-v2+day-cells-v1"}
    assert all(cell.evidence for cell in group)
    # special_program: one blank teacher-input cell per day, never generated.
    assert [(c.day, c.value, c.generation) for c in _days(plan, "special_program")] == [(d, "", None) for d in days]
    request = harness.weekly_provider.requests[0]
    assert request.target("group_activity").days == tuple(d.value for d in days)


def test_an_unresolved_day_stays_empty_and_is_not_filled_from_another_day():
    def tuesday_unresolved(days):
        days[1] = {**days[1], "value": "", "unresolved": True, "grounding_refs": []}
        return days

    plan = _generate(WeeklyHarness(), provider=_Edited(tuesday_unresolved))

    tuesday = plan.cell("group_activity", OperatingDay.TUE)
    assert (tuesday.value, tuesday.generation.method) == ("", GenerationMethod.RULE_ONLY)
    assert plan.cell("group_activity", OperatingDay.WED).value


def test_a_missing_day_is_rejected_and_nothing_is_saved():
    harness = WeeklyHarness()
    provider = _Edited(lambda days: days[:-1])

    with pytest.raises(WeeklyApplicationError):
        _generate(harness, provider=provider)
    assert len(provider.requests) == 1  # DAY_MISMATCH is not repairable
    assert len(harness.weekly_plans) == 0


def test_a_repeated_day_value_is_repaired_for_the_whole_section():
    def tuesday_repeats_monday(days):
        days[1] = {**days[1], "value": days[0]["value"]}
        return days

    provider = _Edited(tuesday_repeats_monday)
    plan = _generate(WeeklyHarness(), provider=provider)

    assert len(provider.requests) == 2
    assert json.loads(provider.requests[1].user_content)["fix_sections"] == [
        {"section_key": "group_activity", "issue": "DAY_VALUE_REPEATED", "day": "TUE"}
    ]
    group = _days(plan, "group_activity")
    assert len({cell.value for cell in group}) == 5
    # S2-4: the Section is repaired as one answer, so every day records the repair prompt.
    assert {cell.generation.rule_version for cell in group} == {"weekly-planner-repair-v1+day-cells-v1"}


def test_regenerating_one_day_keeps_every_other_cell():
    harness = WeeklyHarness()
    before = _generate(harness)
    after = harness.regenerate_weekly(before, section_key="group_activity", day=OperatingDay.TUE)

    request = harness.weekly_provider.requests[-1]
    assert request.prompt_version == "weekly-cell-planner-v1+day-cells-v1"
    assert request.target("group_activity").days == ("TUE",)
    assert len(request.other_day_values) == 4
    target = before.cell("group_activity", OperatingDay.TUE)
    assert after.cell("group_activity", OperatingDay.TUE).item_id == target.item_id
    assert after.cell("group_activity", OperatingDay.TUE).value != target.value
    assert all(b == a for b, a in zip(before.cells, after.cells) if b.item_id != target.item_id)
