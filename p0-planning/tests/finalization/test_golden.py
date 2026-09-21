from __future__ import annotations

import json
from pathlib import Path

from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode

from .harness import PlanningHarness
from .snapshots import (
    cell_regeneration_snapshot,
    monthly_snapshot,
    yearly_snapshot,
)

GOLDEN = Path(__file__).with_name("golden")


def _expected(name: str):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _confirmed_parent(harness: PlanningHarness):
    return harness.confirm_yearly(harness.generate_yearly().plan)


def test_yearly_product_contract_matches_golden():
    harness = PlanningHarness()
    plan = _confirmed_parent(harness)

    assert yearly_snapshot(plan) == _expected("yearly.json")


def test_monthly_rule_only_product_contract_matches_golden():
    harness = PlanningHarness()
    parent = _confirmed_parent(harness)
    result = harness.generate_monthly(parent, MonthlyGenerationMode.RULE_ONLY)

    assert monthly_snapshot(result) == _expected("monthly_rule.json")


def test_monthly_llm_product_contract_matches_golden():
    harness = PlanningHarness()
    parent = _confirmed_parent(harness)
    result = harness.generate_monthly(parent, MonthlyGenerationMode.LLM_PLANNER)

    assert monthly_snapshot(result) == _expected("monthly_llm.json")


def test_cell_regeneration_contract_matches_golden():
    harness = PlanningHarness()
    parent = _confirmed_parent(harness)
    before = harness.generate_monthly(
        parent, MonthlyGenerationMode.LLM_PLANNER
    ).plan
    target = before.section("focus").cells[0]
    result = harness.regenerate_monthly(before, item_id=target.item_id)

    assert cell_regeneration_snapshot(
        before, result, target.item_id
    ) == _expected("cell_regeneration.json")
