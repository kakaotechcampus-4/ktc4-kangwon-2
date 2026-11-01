from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ssuksak.adapters.deterministic import (
    DeterministicIdGenerator,
    FixedClock,
)
from ssuksak.adapters.deterministic_theme_text_generator import (
    DeterministicThemeTextGenerator,
)
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_theme_reference_repository import (
    JsonThemeReferenceRepository,
)
from ssuksak.planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ssuksak.planning.application.generate_yearly_plan import GenerateYearlyPlan
from ssuksak.planning.application.import_yearly_plan import (
    ImportYearlyPlan,
    ImportYearlyPlanCommand,
)
from ssuksak.planning.application.ports import PlanRepository
from ssuksak.planning.application.yearly_dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    GenerateYearlyPlanCommand,
)
from ssuksak.planning.application.yearly_errors import YearlyApplicationError
from ssuksak.planning.application.yearly_ports import (
    ThemeTextGenerator,
    ThemeTextRequest,
    ThemeTextResult,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId, PlanId
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import GenerationMethod
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.monthly_theme_derivation import derive_monthly_theme

NOW = datetime(2026, 9, 19, tzinfo=UTC)
SELECTOR = CatalogSelector(
    "ssuksak.yearly-theme-reference",
    "theme-reference-v0.1.2",
)


def _command() -> GenerateYearlyPlanCommand:
    return GenerateYearlyPlanCommand(
        school_year=2026,
        classroom_ref="classroom",
        target_ages=frozenset({3}),
        catalog=SELECTOR,
    )


def test_theme_text_generator_is_a_narrow_runtime_port():
    generator = DeterministicThemeTextGenerator(prefix="[", suffix="]")
    request = ThemeTextRequest(
        period=YearMonth(2026, 3),
        theme_id="theme",
        reference_label="우리 원과 친구",
        target_ages=(3,),
    )

    assert isinstance(generator, ThemeTextGenerator)
    assert generator.generate((request,)) == (
        ThemeTextResult(
            period=request.period,
            theme_id="theme",
            value="[우리 원과 친구]",
        ),
    )
    assert generator.call_count == 1


@pytest.mark.parametrize(
    "names",
    [("trend", "trend"), ("",), ["trend"]],
)
def test_optional_context_names_are_explicit_unique_tuple_values(names):
    with pytest.raises(InvalidDomainValueError):
        GenerateYearlyPlanCommand(
            school_year=2026,
            classroom_ref="classroom",
            target_ages=frozenset({3}),
            catalog=SELECTOR,
            optional_context_names=names,
        )


def test_plan_repository_contract_keeps_plan_id_and_plan_arguments():
    save_parameters = tuple(inspect.signature(PlanRepository.save).parameters)
    get_parameters = tuple(inspect.signature(PlanRepository.get).parameters)

    assert save_parameters == ("self", "plan_id", "plan")
    assert get_parameters == ("self", "plan_id")


def test_generation_failure_is_not_persisted():
    class ExplodingGenerator:
        def generate(self, requests):
            raise RuntimeError("provider unavailable")

    plans = InMemoryPlanRepository()
    use_case = GenerateYearlyPlan(
        theme_repository=JsonThemeReferenceRepository(),
        plan_repository=plans,
        text_generator=ExplodingGenerator(),
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    )

    with pytest.raises(YearlyApplicationError) as exc:
        use_case.execute(_command())

    assert exc.value.code == "theme_text_generation_failed"
    assert plans.save_count == 0


def test_missing_plan_uses_minimal_application_error_contract():
    plans = InMemoryPlanRepository()
    use_case = ConfirmYearlyPlan(
        plan_repository=plans,
        clock=FixedClock(NOW),
    )

    with pytest.raises(YearlyApplicationError) as exc:
        use_case.execute(
            ConfirmYearlyPlanCommand(
                plan_id=PlanId("missing"),
                actor_id=ActorId("teacher"),
            )
        )

    assert exc.value.code == "yearly_plan_not_found"


def test_raw_display_name_cannot_replace_opaque_actor_id():
    plans = InMemoryPlanRepository()
    generator = DeterministicThemeTextGenerator()
    plan = GenerateYearlyPlan(
        theme_repository=JsonThemeReferenceRepository(),
        plan_repository=plans,
        text_generator=generator,
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    ).execute(_command()).plan
    saves_before = plans.save_count

    with pytest.raises(YearlyApplicationError) as exc:
        ConfirmYearlyPlan(
            plan_repository=plans,
            clock=FixedClock(NOW),
        ).execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id,
                actor_id="담임 선생님",  # type: ignore[arg-type]
            )
        )

    assert exc.value.code == "opaque_actor_required"
    assert plans.save_count == saves_before


_ACADEMIC = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


def _import(themes, method=GenerationMethod.MANUAL):
    plans = InMemoryPlanRepository()
    use_case = ImportYearlyPlan(
        plan_repository=plans, clock=FixedClock(NOW), id_generator=DeterministicIdGenerator()
    )
    command = ImportYearlyPlanCommand(
        school_year=2026,
        classroom_ref="classroom",
        target_ages=frozenset({3, 4}),
        method=method,
        themes=tuple(themes),
        actor_id=ActorId("teacher"),
    )
    return plans, use_case.execute(command)


@pytest.mark.parametrize("method", [GenerationMethod.MANUAL, GenerationMethod.IMPORTED])
def test_import_saves_a_reference_free_draft_that_feeds_monthly(method):
    plans, plan = _import(((m, f" {m}월 주제 ") for m in _ACADEMIC), method)

    assert plan.status is PlanStatus.DRAFT
    assert plans.get(plan.plan_id) == plan
    assert plan.periods[0].theme.value == "3월 주제"
    assert all(p.theme.evidence == () and p.theme_id is None for p in plan.periods)
    assert {p.theme.generation.method for p in plan.periods} == {method}
    assert all(p.theme.audit.events[0].actor_id == ActorId("teacher") for p in plan.periods)
    confirmed = plan.confirm(actor_id=ActorId("teacher"), occurred_at=NOW)
    # Monthly falls back to the parent plan anchor; no Theme Reference is invented.
    derived = derive_monthly_theme(confirmed, YearMonth(2026, 9))
    assert derived.value == "9월 주제"
    assert [e.source_type.value for e in derived.evidence] == ["PARENT_PLAN"]


@pytest.mark.parametrize(
    "themes",
    [
        [(m, "주제") for m in _ACADEMIC[:11]],  # missing February
        [(m, "주제") for m in (*_ACADEMIC[:11], 1)],  # duplicate January
        [(m, "주제") for m in (4, 3, *_ACADEMIC[2:])],  # out of order
        [(m, " " if m == 7 else "주제") for m in _ACADEMIC],  # blank theme
    ],
)
def test_import_rejects_a_broken_month_table(themes):
    with pytest.raises(YearlyApplicationError) as exc:
        _import(themes)
    assert exc.value.code == "invalid_import_months"


def test_import_cannot_claim_a_rule_generation_method():
    with pytest.raises(YearlyApplicationError):
        _import(((m, "주제") for m in _ACADEMIC), GenerationMethod.RULE_LLM)


def test_generated_period_still_requires_one_theme_reference():
    plan = GenerateYearlyPlan(
        theme_repository=JsonThemeReferenceRepository(),
        plan_repository=InMemoryPlanRepository(),
        text_generator=DeterministicThemeTextGenerator(),
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator(),
    ).execute(_command()).plan
    period = plan.periods[0]
    assert period.theme_id
    with pytest.raises(InvalidDomainValueError):
        replace(period, theme=replace(period.theme, evidence=()))
    with pytest.raises(InvalidDomainValueError):
        replace(
            period,
            theme=replace(
                period.theme,
                generation=replace(period.theme.generation, method=GenerationMethod.MANUAL),
            ),
        )
