from __future__ import annotations
import json

import pytest

from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.adapters.weekly_composition import (
    WEEKLY_TEMPLATE_REF,
    weekly_generation,
    weekly_operating_days,
)
from ssuksak.planning.application.generate_weekly_plan import GenerateWeeklyPlanCommand
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import EvidenceSourceType, GenerationMethod
from ssuksak.planning.domain.weekly_plan import OperatingDay
from tests.finalization.harness import ACTIVITY_CATALOG, SAFETY_RULE
from tests.finalization.weekly_harness import WEEK, WeeklyHarness

LLM = MonthlyGenerationMode.LLM_PLANNER


@pytest.mark.parametrize("saturday", [False, True])
def test_composition_generates_a_weekly_draft_from_the_approved_template(saturday):
    harness = WeeklyHarness()
    parent = harness.monthly_parent(mode=LLM)
    provider = RequestAwareWeeklyLlm()
    plan = weekly_generation(
        parent_plan_repository=harness.monthly_plans,
        plan_repository=harness.weekly_plans,
        provider=provider,
        clock=harness.clock,
        id_generator=harness.weekly_ids,
    ).execute(
        GenerateWeeklyPlanCommand(
            parent_monthly_plan_id=parent.plan_id,
            week_id=WEEK,
            operating_days=weekly_operating_days(saturday),
            template_ref=WEEKLY_TEMPLATE_REF,
            safety_rule=SAFETY_RULE,
            generation_mode=LLM,
            activity_catalog=ACTIVITY_CATALOG,
        )
    ).plan

    assert plan.status is PlanStatus.DRAFT
    assert len(json.loads(provider.requests[0].user_content)["curriculum_context"]["contents"]) == 59
    assert plan.generation_mode is LLM
    assert (OperatingDay.SAT in plan.operating_days) is saturday
    assert plan.template_snapshot.base_template_ref == WEEKLY_TEMPLATE_REF
    # W3c: the approved weekly classification is wired, so the three classified cells are written.
    for key in ("indoor_play", "group_activity", "indoor_alternative"):
        cell = plan.cell(key)
        assert cell.value and cell.generation.method is GenerationMethod.RULE_LLM
        assert EvidenceSourceType.INSTITUTION_SAMPLE in {s.source_type for s in cell.evidence}
