"""Provider-neutral commands and results for Monthly application use cases."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import InvalidDomainValueError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from ..domain.monthly_template_profile import TemplateProfileRef
from ..domain.year_month import YearMonth
from ..planner.contracts import MonthlyCellPlanningOutcome
from ..rules.monthly_activity_selection import ActivitySelectionTrace
from .ports import OptionalContextResult


def _non_blank(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{name} must be a non-blank string")


@dataclass(frozen=True, slots=True)
class SafetyRuleSelector:
    legal_rule_version: str

    def __post_init__(self) -> None:
        _non_blank(self.legal_rule_version, "SafetyRuleSelector.legal_rule_version")


@dataclass(frozen=True, slots=True)
class SafetyPlacementSelector:
    policy_version: str

    def __post_init__(self) -> None:
        _non_blank(self.policy_version, "SafetyPlacementSelector.policy_version")


@dataclass(frozen=True, slots=True)
class ActivityCatalogSelector:
    catalog_id: str
    catalog_version: str

    def __post_init__(self) -> None:
        _non_blank(self.catalog_id, "ActivityCatalogSelector.catalog_id")
        _non_blank(self.catalog_version, "ActivityCatalogSelector.catalog_version")


@dataclass(frozen=True, slots=True)
class GenerateMonthlyPlanCommand:
    parent_yearly_plan_id: PlanId
    target_month: YearMonth
    daycare_ref: str
    profile_ref: TemplateProfileRef
    safety_rule: SafetyRuleSelector
    generation_mode: MonthlyGenerationMode
    activity_catalog: ActivityCatalogSelector | None = None
    optional_context_names: tuple[str, ...] = ()
    # None keeps safety_education on the source-required path (OD-M04).
    safety_placement: SafetyPlacementSelector | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.parent_yearly_plan_id, PlanId):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.parent_yearly_plan_id must be PlanId"
            )
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.target_month must be YearMonth"
            )
        _non_blank(self.daycare_ref, "GenerateMonthlyPlanCommand.daycare_ref")
        if not isinstance(self.profile_ref, TemplateProfileRef):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.profile_ref must be TemplateProfileRef"
            )
        if not isinstance(self.safety_rule, SafetyRuleSelector):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.safety_rule must be SafetyRuleSelector"
            )
        if not isinstance(self.generation_mode, MonthlyGenerationMode):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.generation_mode is invalid"
            )
        if self.activity_catalog is not None and not isinstance(
            self.activity_catalog, ActivityCatalogSelector
        ):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.activity_catalog is invalid"
            )
        if not isinstance(self.optional_context_names, tuple) or any(
            not isinstance(name, str) or not name.strip()
            for name in self.optional_context_names
        ):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.optional_context_names are invalid"
            )
        if len(set(self.optional_context_names)) != len(self.optional_context_names):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.optional_context_names must be unique"
            )
        if self.safety_placement is not None and not isinstance(
            self.safety_placement, SafetyPlacementSelector
        ):
            raise InvalidDomainValueError(
                "GenerateMonthlyPlanCommand.safety_placement is invalid"
            )


@dataclass(frozen=True, slots=True)
class EditMonthlyPlanItemCommand:
    plan_id: PlanId
    item_id: ItemId
    new_value: str
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class RegenerateMonthlyPlanItemCommand:
    plan_id: PlanId
    item_id: ItemId
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class ConfirmMonthlyPlanCommand:
    plan_id: PlanId
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class MonthlyActivitySelectionResult:
    week_id: str
    trace: ActivitySelectionTrace


@dataclass(frozen=True, slots=True)
class GenerateMonthlyPlanResult:
    plan: MonthlyPlan
    optional_context: tuple[OptionalContextResult, ...]
    activity_selections: tuple[MonthlyActivitySelectionResult, ...] = ()
    context_packet_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class RegenerateMonthlyPlanItemResult:
    plan: MonthlyPlan
    activity_selection: MonthlyActivitySelectionResult | None = None
    planner_outcome: MonthlyCellPlanningOutcome | None = None
