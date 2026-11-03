from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ssuksak.adapters import weekly_composition
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
)
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.adapters.weekly_composition import (
    WEEKLY_TEMPLATE_REF,
    weekly_generation,
    weekly_operating_days,
)
from ssuksak.planning.application.generate_weekly_plan import (
    GenerateWeeklyPlanCommand,
    WeeklyApplicationError,
)
from ssuksak.planning.application.weekly_lifecycle import (
    RegenerateWeeklyPlanCellCommand,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import EvidenceSourceType, GenerationMethod
from ssuksak.planning.domain.weekly_plan import OperatingDay
from tests.finalization.harness import ACTIVITY_CATALOG, SAFETY_RULE
from tests.finalization.weekly_harness import WEEK, WEEKLY_DAY_TEMPLATE, WeeklyHarness

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


def _day_generation(harness, provider):
    from pathlib import Path
    path = Path(__file__).parents[2] / "data/templates/weekly_template_a_v0_2_0.json"
    return weekly_generation(
        parent_plan_repository=harness.monthly_plans, plan_repository=harness.weekly_plans,
        provider=provider, clock=harness.clock, id_generator=harness.weekly_ids,
        template_repository=JsonMonthlyTemplateRepository(paths=(path,)),
    )


def _day_command(parent):
    return GenerateWeeklyPlanCommand(parent.plan_id, WEEK, weekly_operating_days(False),
                                     WEEKLY_DAY_TEMPLATE, SAFETY_RULE, LLM, activity_catalog=ACTIVITY_CATALOG)


def test_day_composition_links_approved_context_and_parent_play_through_regeneration():
    harness = WeeklyHarness()
    parent = harness.monthly_parent(confirm=False, mode=LLM)
    original = parent.section("outdoor_play").cell_for_week(WEEK)
    parent = harness.edit_monthly(parent, item_id=original.item_id, value="모래로 우리나라 음식 상을 차려요")
    parent = harness.confirm_monthly(parent)
    provider = RequestAwareWeeklyLlm()
    before = _day_generation(harness, provider).execute(_day_command(parent)).plan
    request = provider.requests[-1]
    body = json.loads(request.user_content)
    assert len(body["curriculum_context"]["contents"]) == 59
    assert len(body["daily_life_context"]["entries"]) == 15
    assert body["daily_life_context"]["purpose"] == "WORDING_CONTEXT_ONLY"
    assert request.target("outdoor_play").parent_groundable
    assert request.target("outdoor_play").allowed_grounding_refs
    from ssuksak.planning.planner.weekly import (
        parse_weekly_proposal,
        validate_weekly,
        weekly_response_schema,
    )
    branches = weekly_response_schema(request)["properties"]["sections"]["items"]["anyOf"]
    assert any(b["properties"]["section_key"]["enum"] == ["outdoor_play"]
               and b["properties"]["reference_id"] == {"type": "null"} for b in branches)
    answer = json.loads(provider.generate_weekly(request).content)
    offered = next(s for s in answer["sections"] if s["section_key"] == "outdoor_play")
    offered["grounding_refs"] = list(request.target("basic_habit").allowed_grounding_refs[:1])
    assert any(i.code.value == "WRONG_SOURCE_GROUNDING"
               for i in validate_weekly(parse_weekly_proposal(json.dumps(answer), request), request))
    offered["reference_id"], offered["value"] = request.reference_candidates[0]
    offered["grounding_refs"] = list(request.target("outdoor_play").allowed_grounding_refs[:1])
    assert any(i.code.value == "WRONG_SOURCE_GROUNDING"
               for i in validate_weekly(parse_weekly_proposal(json.dumps(answer), request), request))
    offered["reference_id"], offered["value"] = None, body["parent"]["outdoor_play"]
    offered["grounding_refs"] = []
    next(s for s in answer["sections"] if s["section_key"] == "basic_habit")["value"] = body["daily_life_context"]["entries"][0]["text"]
    assert any(i.code.value == "SOURCE_TEXT_COPY"
               for i in validate_weekly(parse_weekly_proposal(json.dumps(answer), request), request))
    outdoor = before.cell("outdoor_play")
    assert outdoor.value == "모래로 우리나라 음식 상을 차려요"
    assert all(e.source_type is not EvidenceSourceType.ACTIVITY_REFERENCE for e in outdoor.evidence)
    assert any(p.parent_item_id == original.item_id and p.snapshot_value == outdoor.value
               for p in outdoor.parent_snapshots)
    after = weekly_composition.weekly_regeneration(
        plan_repository=harness.weekly_plans, parent_plan_repository=harness.monthly_plans,
        provider=provider, clock=harness.clock,
    ).execute(RegenerateWeeklyPlanCellCommand(before.plan_id, outdoor.item_id, ActorId("test_reviewer")))
    assert after.cell("outdoor_play").item_id == outdoor.item_id
    assert after.cell("outdoor_play").generation.rule_version == "weekly-cell-planner-v2+monthly-linked-v4+day-cells-v1"
    assert any(e.source_type is EvidenceSourceType.INSTITUTION_SAMPLE for e in after.cell("outdoor_play").evidence)
    assert all(a == b for a, b in zip(before.cells, after.cells) if a.item_id != outdoor.item_id)
    assert json.loads(provider.requests[-1].user_content)["daily_life_context"] == body["daily_life_context"]


@pytest.mark.parametrize("mismatched", [False, True])
def test_day_reference_failure_stops_before_provider_and_storage(monkeypatch, mismatched):
    real = weekly_composition._daily_life_catalog()
    value = replace(real, curriculum_catalog_version="wrong-version") if mismatched else None
    monkeypatch.setattr(weekly_composition, "_daily_life_catalog", lambda: value)
    harness, provider = WeeklyHarness(), RequestAwareWeeklyLlm()
    parent = harness.monthly_parent(mode=LLM)
    with pytest.raises(WeeklyApplicationError) as error:
        _day_generation(harness, provider).execute(_day_command(parent))
    assert error.value.code == "weekly_reference_context_unavailable"
    assert not provider.requests and len(harness.weekly_plans) == 0


@pytest.mark.parametrize("changed, cited", [(False, False), (True, False), (True, True)])
def test_day_outdoor_needs_institution_grounding_unless_inheriting_parent(changed, cited):
    from ssuksak.planning.planner.weekly import parse_weekly_proposal, validate_weekly

    harness, provider = WeeklyHarness(), RequestAwareWeeklyLlm()
    parent = harness.monthly_parent(mode=LLM)
    _day_generation(harness, provider).execute(_day_command(parent))
    request = provider.requests[-1]
    target = request.target("outdoor_play")
    answer = json.loads(provider.generate_weekly(request).content)
    outdoor = next(s for s in answer["sections"] if s["section_key"] == "outdoor_play")
    outdoor["reference_id"] = None
    outdoor["value"] = "물총 놀이" if changed else f"  {target.parent_value}  "
    outdoor["grounding_refs"] = list(target.allowed_grounding_refs[:1]) if cited else []
    issues = validate_weekly(parse_weekly_proposal(json.dumps(answer), request), request)
    missing = any(i.section_key == "outdoor_play" and i.code.value == "RESOLVED_REQUIRES_GROUNDING" for i in issues)
    assert missing is (changed and not cited)


def test_day_unrelated_request_error_is_not_reported_as_unavailable_reference(monkeypatch):
    import importlib

    generation = importlib.import_module("ssuksak.planning.application.generate_weekly_plan")
    failure = InvalidDomainValueError("unrelated request invariant")

    def broken_request(*args, **kwargs):
        raise failure

    monkeypatch.setattr(generation, "_weekly_request", broken_request)
    harness, provider = WeeklyHarness(), RequestAwareWeeklyLlm()
    parent = harness.monthly_parent(mode=LLM)
    with pytest.raises(InvalidDomainValueError) as error:
        _day_generation(harness, provider).execute(_day_command(parent))
    assert error.value is failure
    assert not provider.requests and len(harness.weekly_plans) == 0
