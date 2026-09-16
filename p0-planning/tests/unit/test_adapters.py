from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.stub_optional_context_provider import StubOptionalContextProvider
from ssuksak.planning.application.ports import (
    Clock,
    IdGenerator,
    OptionalContextProvider,
    OptionalContextResult,
    OptionalContextStatus,
    PlanRepository,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ItemId, PlanId


def test_in_memory_repository_saves_and_reads_by_domain_id():
    repository: InMemoryPlanRepository[dict[str, str]] = InMemoryPlanRepository()
    plan_id = PlanId("plan_001")
    plan = {"status": "DRAFT"}

    repository.save(plan_id, plan)

    assert repository.get(plan_id) is plan
    assert repository.get(PlanId("missing")) is None
    assert repository.save_count == 1
    assert len(repository) == 1
    assert isinstance(repository, PlanRepository)


def test_in_memory_repository_rejects_raw_string_keys():
    repository = InMemoryPlanRepository()
    with pytest.raises(InvalidDomainValueError):
        repository.save("plan_001", object())


def test_fixed_clock_always_returns_the_injected_aware_time():
    value = datetime(2026, 9, 16, 9, 30, tzinfo=UTC)
    clock = FixedClock(value)

    assert clock.now() is value
    assert clock.now() is value
    assert isinstance(clock, Clock)


def test_fixed_clock_rejects_naive_time():
    with pytest.raises(InvalidDomainValueError):
        FixedClock(datetime(2026, 9, 16, 9, 30))  # noqa: DTZ001 - intentionally naive


def test_deterministic_id_generator_uses_independent_counters():
    generator = DeterministicIdGenerator("fixture")

    assert generator.new_plan_id() == PlanId("fixture_plan_001")
    assert generator.new_plan_id() == PlanId("fixture_plan_002")
    assert generator.new_item_id() == ItemId("fixture_item_001")
    assert isinstance(generator, IdGenerator)


def test_optional_context_stub_returns_configured_success():
    result = OptionalContextResult(
        name="weather",
        status=OptionalContextStatus.AVAILABLE,
        value={"condition": "rain"},
    )
    provider = StubOptionalContextProvider({"weather": result})

    assert provider.fetch("weather") is result
    assert provider.fetch("weather").is_usable
    assert isinstance(provider, OptionalContextProvider)


def test_optional_context_stub_turns_missing_context_into_result():
    result = StubOptionalContextProvider().fetch("trend")

    assert result.status is OptionalContextStatus.UNAVAILABLE
    assert result.status.is_failure
    assert not result.is_usable


def test_available_optional_context_requires_value():
    with pytest.raises(InvalidDomainValueError):
        OptionalContextResult("weather", OptionalContextStatus.AVAILABLE)
