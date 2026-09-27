"""Provider-neutral commands and results for Yearly application use cases."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import InvalidDomainValueError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.yearly_plan import YearlyPlan
from ..rules.yearly_theme_selection import ThemeSelectionTrace
from .ports import OptionalContextResult


def _non_blank(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{name} must be a non-blank string")


@dataclass(frozen=True, slots=True)
class CatalogSelector:
    catalog_id: str
    catalog_version: str

    def __post_init__(self) -> None:
        _non_blank(self.catalog_id, "CatalogSelector.catalog_id")
        _non_blank(self.catalog_version, "CatalogSelector.catalog_version")


@dataclass(frozen=True, slots=True)
class GenerateYearlyPlanCommand:
    school_year: int
    classroom_ref: str
    target_ages: frozenset[int]
    catalog: CatalogSelector
    optional_context_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_blank(self.classroom_ref, "GenerateYearlyPlanCommand.classroom_ref")
        if not isinstance(self.target_ages, frozenset):
            raise InvalidDomainValueError(
                "GenerateYearlyPlanCommand.target_ages must be frozenset"
            )
        if not isinstance(self.catalog, CatalogSelector):
            raise InvalidDomainValueError(
                "GenerateYearlyPlanCommand.catalog must be CatalogSelector"
            )
        if not isinstance(self.optional_context_names, tuple):
            raise InvalidDomainValueError(
                "optional_context_names must be a tuple"
            )
        for name in self.optional_context_names:
            _non_blank(name, "optional context name")
        if len(set(self.optional_context_names)) != len(
            self.optional_context_names
        ):
            raise InvalidDomainValueError(
                "optional_context_names must not contain duplicates"
            )


@dataclass(frozen=True, slots=True)
class EditYearlyPlanItemCommand:
    plan_id: PlanId
    item_id: ItemId
    new_value: str
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class RegenerateYearlyPlanItemCommand:
    plan_id: PlanId
    item_id: ItemId
    actor_id: ActorId
    catalog: CatalogSelector


@dataclass(frozen=True, slots=True)
class ConfirmYearlyPlanCommand:
    plan_id: PlanId
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class GenerateYearlyPlanResult:
    plan: YearlyPlan
    selection_traces: tuple[ThemeSelectionTrace, ...]
    optional_context: tuple[OptionalContextResult, ...] = ()


@dataclass(frozen=True, slots=True)
class RegenerateYearlyPlanItemResult:
    plan: YearlyPlan
    selection_trace: ThemeSelectionTrace
