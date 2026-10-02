"""Provider-neutral Planning Core.

This module is the public caller API: the names in ``__all__`` are the
contract a caller (the Backend) may import from ``ssuksak.planning``. They are
re-exports of the existing objects, not wrappers. Ports stay in their own
modules and are not part of this surface.
"""

from .application.confirm_monthly_plan import ConfirmMonthlyPlan
from .application.confirm_yearly_plan import ConfirmYearlyPlan
from .application.edit_monthly_plan_item import EditMonthlyPlanItem
from .application.edit_yearly_plan_item import EditYearlyPlanItem
from .application.generate_monthly_plan import GenerateMonthlyPlan
from .application.generate_yearly_plan import GenerateYearlyPlan
from .application.monthly_dto import (
    ActivityCatalogSelector,
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    GenerateMonthlyPlanResult,
    RegenerateMonthlyPlanItemCommand,
    RegenerateMonthlyPlanItemResult,
    SafetyPlacementSelector,
    SafetyRuleSelector,
)
from .application.monthly_errors import MonthlyApplicationError
from .application.regenerate_monthly_plan_item import RegenerateMonthlyPlanItem
from .application.regenerate_yearly_plan_item import RegenerateYearlyPlanItem
from .application.yearly_dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
    GenerateYearlyPlanResult,
    RegenerateYearlyPlanItemCommand,
    RegenerateYearlyPlanItemResult,
)
from .application.yearly_errors import YearlyApplicationError
from .domain.errors import InvalidDomainValueError, InvalidStateTransitionError
from .domain.identifiers import ActorId, ItemId, PlanId
from .domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from .domain.monthly_template_profile import TemplateProfileRef
from .domain.year_month import YearMonth
from .domain.yearly_plan import YearlyPlan

__all__ = (
    # Yearly use cases, commands and results
    "GenerateYearlyPlan",
    "EditYearlyPlanItem",
    "RegenerateYearlyPlanItem",
    "ConfirmYearlyPlan",
    "GenerateYearlyPlanCommand",
    "EditYearlyPlanItemCommand",
    "RegenerateYearlyPlanItemCommand",
    "ConfirmYearlyPlanCommand",
    "GenerateYearlyPlanResult",
    "RegenerateYearlyPlanItemResult",
    "CatalogSelector",
    # Monthly use cases, commands and results
    "GenerateMonthlyPlan",
    "EditMonthlyPlanItem",
    "RegenerateMonthlyPlanItem",
    "ConfirmMonthlyPlan",
    "GenerateMonthlyPlanCommand",
    "EditMonthlyPlanItemCommand",
    "RegenerateMonthlyPlanItemCommand",
    "ConfirmMonthlyPlanCommand",
    "GenerateMonthlyPlanResult",
    "RegenerateMonthlyPlanItemResult",
    "SafetyRuleSelector",
    "SafetyPlacementSelector",
    "ActivityCatalogSelector",
    "TemplateProfileRef",
    "MonthlyGenerationMode",
    "YearMonth",
    # Identifiers every mutation command takes
    "PlanId",
    "ItemId",
    "ActorId",
    # Aggregates a PlanRepository implementation stores and returns
    "YearlyPlan",
    "MonthlyPlan",
    # Errors a caller maps to its own responses
    "YearlyApplicationError",
    "MonthlyApplicationError",
    "InvalidStateTransitionError",
    "InvalidDomainValueError",
)
