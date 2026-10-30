import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p0-planning"))

from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from tests.finalization.harness import LLM_PROFILE, PlanningHarness

from app.features.plans.codec import from_jsonable, to_jsonable


def test_confirmed_parent_subtheme_snapshot_survives_storage_and_old_bodies():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    original = harness.generate_monthly(
        parent, MonthlyGenerationMode.LLM_PLANNER, profile=LLM_PROFILE
    ).plan
    plan = replace(original, parent_subthemes=("교사가 확정한 월별 소주제", "서로 다른 모양"))
    body = json.loads(json.dumps(to_jsonable(plan)))
    assert from_jsonable(MonthlyPlan, body) == plan
    del body["parent_subthemes"]
    assert from_jsonable(MonthlyPlan, body) == original
