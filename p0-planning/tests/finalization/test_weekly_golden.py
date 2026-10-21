from __future__ import annotations

import json
from pathlib import Path

from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode

from .weekly_harness import WEEK, WeeklyHarness, weekly_snapshot

GOLDEN = Path(__file__).with_name("golden")


def test_weekly_rule_only_product_contract_matches_golden():
    harness = WeeklyHarness()
    result = harness.generate_weekly(harness.monthly_parent())

    expected = json.loads((GOLDEN / "weekly_rule.json").read_text(encoding="utf-8"))
    assert weekly_snapshot(result) == expected


def llm_scenario():
    """LLM monthly parent whose teacher wrote this week's safety cell; weekly LLM_PLANNER (FakeLLM)."""
    harness = WeeklyHarness()
    draft = harness.monthly_parent(confirm=False, mode=MonthlyGenerationMode.LLM_PLANNER)
    cell = draft.section("safety_education").cell_for_week(WEEK)
    draft = harness.edit_monthly(draft, item_id=cell.item_id, value="10월 2일 소방서 견학 전에 불이 나면 대피하는 길을 익혀요")
    return harness.generate_weekly(harness.confirm_monthly(draft), mode=MonthlyGenerationMode.LLM_PLANNER)


def test_weekly_llm_application_contract_matches_golden():
    expected = json.loads((GOLDEN / "weekly_llm.json").read_text(encoding="utf-8"))
    assert weekly_snapshot(llm_scenario()) == expected
