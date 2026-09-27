"""Approved six-category safety education Reference values."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidDomainValueError

STATUTORY = "STATUTORY"
LEGAL_CATEGORY_COUNT = 6


@dataclass(frozen=True, slots=True)
class SafetyCategory:
    category_id: str
    official_label: str
    interval_months: int
    annual_hours_min: int

    def __post_init__(self) -> None:
        for name in ("category_id", "official_label"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"SafetyCategory.{name} must be non-blank"
                )
        for name in ("interval_months", "annual_hours_min"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise InvalidDomainValueError(
                    f"SafetyCategory.{name} must be a positive integer"
                )


@dataclass(frozen=True, slots=True)
class SafetyLegalRule:
    legal_rule_version: str
    normative_status: str
    categories: tuple[SafetyCategory, ...]
    age_tier_label: str
    placement_policy_version: str | None = None
    runtime_active: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.legal_rule_version, str) or not self.legal_rule_version.strip():
            raise InvalidDomainValueError(
                "SafetyLegalRule.legal_rule_version must be non-blank"
            )
        if self.normative_status != STATUTORY:
            raise InvalidDomainValueError(
                f"SafetyLegalRule.normative_status must be {STATUTORY}"
            )
        if not isinstance(self.categories, tuple) or len(self.categories) != LEGAL_CATEGORY_COUNT:
            raise InvalidDomainValueError(
                f"SafetyLegalRule requires exactly {LEGAL_CATEGORY_COUNT} categories"
            )
        if not all(isinstance(item, SafetyCategory) for item in self.categories):
            raise InvalidDomainValueError(
                "SafetyLegalRule.categories must contain SafetyCategory values"
            )
        ids = tuple(item.category_id for item in self.categories)
        if len(set(ids)) != len(ids):
            raise InvalidDomainValueError(
                "SafetyLegalRule contains duplicate category_id values"
            )
        if not isinstance(self.age_tier_label, str) or not self.age_tier_label.strip():
            raise InvalidDomainValueError(
                "SafetyLegalRule.age_tier_label must be non-blank"
            )
        if self.placement_policy_version is not None:
            raise InvalidDomainValueError(
                "P0 SafetyLegalRule must not declare a placement policy"
            )
        if type(self.runtime_active) is not bool:
            raise InvalidDomainValueError(
                "SafetyLegalRule.runtime_active must be a boolean"
            )

    def category(self, category_id: str) -> SafetyCategory | None:
        return next(
            (item for item in self.categories if item.category_id == category_id),
            None,
        )

    @property
    def annual_hours_min_total(self) -> int:
        return sum(item.annual_hours_min for item in self.categories)

    @property
    def is_active(self) -> bool:
        return self.runtime_active

    @property
    def has_placement_policy(self) -> bool:
        return False
