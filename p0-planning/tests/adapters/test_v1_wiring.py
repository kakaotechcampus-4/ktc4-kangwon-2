import json

import pytest

from ssuksak.adapters import monthly_composition
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning.application.monthly_dto import (
    GenerateMonthlyPlanCommand,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.year_month import YearMonth
from tests.finalization.harness import (
    PlanningHarness,
    ACTIVITY_CATALOG,
    LLM_PROFILE,
    SAFETY_RULE,
)


class RecordingProvider(RequestAwareMonthlyLlm):
    def __init__(self):
        self.requests = []

    def generate_monthly(self, request):
        self.requests.append(request)
        return super().generate_monthly(request)

    def generate_cell(self, request):
        self.requests.append(request)
        return super().generate_cell(request)


def _setup():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    provider = RecordingProvider()
    generate = monthly_composition.monthly_generation(
        parent_plan_repository=harness.yearly_plans,
        plan_repository=harness.monthly_plans,
        profile_repository=harness.profiles,
        template_repository=harness.generation_templates,
        provider=provider,
        clock=harness.clock,
        id_generator=harness.monthly_ids,
    )
    command = GenerateMonthlyPlanCommand(
        parent.plan_id,
        YearMonth(2026, 9),
        "daycare_001",
        LLM_PROFILE,
        SAFETY_RULE,
        MonthlyGenerationMode.LLM_PLANNER,
        activity_catalog=ACTIVITY_CATALOG,
        parent_subthemes=("교사가 확정한 가을 열매", "서로 다른 나뭇잎"),
    )
    return harness, provider, generate, command


def test_monthly_generation_and_regeneration_reuse_confirmed_annual_snapshot():
    harness, provider, generate, command = _setup()
    plan = generate.execute(command).plan
    assert plan.parent_subthemes == command.parent_subthemes
    regenerate = monthly_composition.monthly_regeneration(
        plan_repository=harness.monthly_plans, provider=provider, clock=harness.clock
    )
    plan = regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan.plan_id,
            plan.section("focus").cells[0].item_id,
            ActorId("reviewer_test"),
        )
    ).plan
    assert len(provider.requests) == 2
    for request in provider.requests:
        payload = json.loads(request.user_content)
        assert len(payload["curriculum_context"]["contents"]) == 59
        assert tuple(payload["parent_subthemes"]) == command.parent_subthemes


def test_curriculum_failure_stops_before_provider_and_storage(monkeypatch):
    def unavailable():
        raise InvalidDomainValueError("unapproved")

    monkeypatch.setattr(monthly_composition, "v1_curriculum_catalog", unavailable)
    harness, provider, generate, command = _setup()
    with pytest.raises(MonthlyApplicationError, match="curriculum") as error:
        generate.execute(command)
    assert error.value.code == "curriculum_reference_unavailable"
    assert provider.requests == []
    assert not harness.monthly_plans._plans
