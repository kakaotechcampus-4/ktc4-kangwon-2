"""Provider-neutral ports required by the Planning Core foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, Protocol, TypeVar, runtime_checkable

from ..domain.errors import InvalidDomainValueError
from ..domain.activity_reference import ActivityCatalog
from ..domain.identifiers import ItemId, PlanId
from ..domain.monthly_template import MonthlyTemplate
from ..domain.monthly_template_profile import TemplateProfile
from ..domain.safety_placement import SafetyPlacementPolicy
from ..domain.safety_rule import SafetyLegalRule
from ..domain.theme_reference import ThemeCatalog

TPlan = TypeVar("TPlan")


@runtime_checkable
class PlanRepository(Protocol, Generic[TPlan]):
    """Logical plan storage without choosing a database or schema."""

    def save(self, plan_id: PlanId, plan: TPlan) -> None: ...

    def get(self, plan_id: PlanId) -> TPlan | None: ...


@runtime_checkable
class ThemeReferenceRepository(Protocol):
    """Read an exact versioned Theme Catalog without choosing persistence."""

    def get_catalog(
        self, catalog_id: str, catalog_version: str
    ) -> ThemeCatalog | None: ...


@runtime_checkable
class ActivityReferenceRepository(Protocol):
    """Read an exact versioned Activity Catalog."""

    def get_catalog(
        self, catalog_id: str, catalog_version: str
    ) -> ActivityCatalog | None: ...


@runtime_checkable
class MonthlyTemplateRepository(Protocol):
    """Read an exact versioned Monthly Template."""

    def get_template(
        self, template_id: str, template_version: str
    ) -> MonthlyTemplate | None: ...


@runtime_checkable
class TemplateProfileRepository(Protocol):
    """Read one exact institution/class Template Profile version."""

    def get_profile(
        self, profile_id: str, profile_version: str
    ) -> TemplateProfile | None: ...


@runtime_checkable
class SafetyPlacementPolicyRepository(Protocol):
    def get_policy(self, policy_version: str) -> SafetyPlacementPolicy | None: ...


@runtime_checkable
class SafetyLegalRuleRepository(Protocol):
    """Read an exact versioned approved safety Reference."""

    def get_legal_rule(self, legal_rule_version: str) -> SafetyLegalRule | None: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class IdGenerator(Protocol):
    def new_plan_id(self) -> PlanId: ...

    def new_item_id(self) -> ItemId: ...


class OptionalContextStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

    @property
    def is_failure(self) -> bool:
        return self is not OptionalContextStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class OptionalContextResult:
    """Result object used instead of turning an optional failure into an exception."""

    name: str
    status: OptionalContextStatus
    value: object | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidDomainValueError(
                "OptionalContextResult.name must be non-blank"
            )
        if not isinstance(self.status, OptionalContextStatus):
            raise InvalidDomainValueError("OptionalContextResult.status is invalid")
        if self.status is OptionalContextStatus.AVAILABLE and self.value is None:
            raise InvalidDomainValueError("AVAILABLE optional context requires a value")
        if not isinstance(self.detail, str):
            raise InvalidDomainValueError(
                "OptionalContextResult.detail must be a string"
            )

    @property
    def is_usable(self) -> bool:
        return self.status is OptionalContextStatus.AVAILABLE


@runtime_checkable
class OptionalContextProvider(Protocol):
    """Read one non-essential external context without prescribing its provider."""

    def fetch(self, name: str) -> OptionalContextResult: ...
