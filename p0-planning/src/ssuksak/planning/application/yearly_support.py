"""Shared internal helpers for Yearly application use cases."""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.yearly_plan import YearlyPlan
from .ports import (
    OptionalContextProvider,
    OptionalContextResult,
    OptionalContextStatus,
    PlanRepository,
)
from .yearly_errors import YearlyApplicationError
from .yearly_ports import ThemeTextGenerator, ThemeTextRequest, ThemeTextResult


def require_plan(
    repository: PlanRepository[YearlyPlan], plan_id: object
) -> YearlyPlan:
    if not isinstance(plan_id, PlanId):
        raise YearlyApplicationError(
            "invalid_plan_id", "Yearly use cases require PlanId"
        )
    plan = repository.get(plan_id)
    if plan is None:
        raise YearlyApplicationError(
            "yearly_plan_not_found", f"Yearly Plan not found: {plan_id}"
        )
    if not isinstance(plan, YearlyPlan):
        raise YearlyApplicationError(
            "repository_contract_violation",
            "PlanRepository returned a non-YearlyPlan value",
        )
    return plan


def require_actor(actor_id: object) -> ActorId:
    if not isinstance(actor_id, ActorId):
        raise YearlyApplicationError(
            "opaque_actor_required", "Yearly mutation requires ActorId"
        )
    return actor_id


def require_item_id(item_id: object) -> ItemId:
    if not isinstance(item_id, ItemId):
        raise YearlyApplicationError(
            "invalid_item_id", "Yearly item use cases require ItemId"
        )
    return item_id


def fetch_optional_context(
    names: Iterable[str],
    provider: OptionalContextProvider | None,
) -> tuple[OptionalContextResult, ...]:
    results: list[OptionalContextResult] = []
    for name in names:
        if provider is None:
            results.append(
                OptionalContextResult(
                    name=name,
                    status=OptionalContextStatus.UNAVAILABLE,
                    detail="No OptionalContextProvider configured",
                )
            )
            continue
        try:
            result = provider.fetch(name)
            if result.name != name:
                raise ValueError("provider returned a different context name")
            results.append(result)
        except Exception:  # Optional context cannot fail core generation.
            results.append(
                OptionalContextResult(
                    name=name,
                    status=OptionalContextStatus.ERROR,
                    detail="Optional context provider raised or violated its contract",
                )
            )
    return tuple(results)


def generate_theme_text(
    generator: ThemeTextGenerator,
    requests: tuple[ThemeTextRequest, ...],
) -> tuple[ThemeTextResult, ...]:
    try:
        results = generator.generate(requests)
    except YearlyApplicationError:
        raise
    except Exception as exc:
        raise YearlyApplicationError(
            "theme_text_generation_failed",
            "Theme text generation failed before the plan was saved",
        ) from exc

    if not isinstance(results, tuple):
        raise YearlyApplicationError(
            "invalid_theme_text_result",
            "ThemeTextGenerator must return a tuple",
        )
    if len(results) != len(requests):
        raise YearlyApplicationError(
            "invalid_theme_text_result",
            "ThemeTextGenerator returned the wrong number of results",
        )

    expected = {(request.period, request.theme_id) for request in requests}
    actual: set[tuple[object, object]] = set()
    for result in results:
        if not isinstance(result, ThemeTextResult):
            raise YearlyApplicationError(
                "invalid_theme_text_result",
                "ThemeTextGenerator returned an invalid result type",
            )
        key = (result.period, result.theme_id)
        if key in actual:
            raise YearlyApplicationError(
                "invalid_theme_text_result",
                "ThemeTextGenerator returned a duplicate period/theme result",
            )
        actual.add(key)
    if actual != expected:
        raise YearlyApplicationError(
            "invalid_theme_text_result",
            "ThemeTextGenerator changed a Rule-selected period or theme",
        )
    by_key = {(result.period, result.theme_id): result for result in results}
    return tuple(by_key[(request.period, request.theme_id)] for request in requests)
