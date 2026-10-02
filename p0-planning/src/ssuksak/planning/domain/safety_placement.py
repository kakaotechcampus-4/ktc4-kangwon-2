"""Product safety placement policy values, kept apart from the statutory Rule."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError

PRODUCT_POLICY = "PRODUCT_POLICY"
FOCUS_RULE = "OFFICIAL_ORDER_ROTATING_BY_SCHOOL_YEAR"


class SafetyKind(str, Enum):
    """STATUTORY counts toward the six legal categories; SUPPLEMENTAL never does."""

    STATUTORY = "STATUTORY"
    SUPPLEMENTAL = "SUPPLEMENTAL"


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{name} must be non-blank")


@dataclass(frozen=True, slots=True)
class SafetyPlacementEntry:
    month: int
    category_id: str
    week_ordinal: int

    def __post_init__(self) -> None:
        if type(self.month) is not int or not 1 <= self.month <= 12:
            raise InvalidDomainValueError("SafetyPlacementEntry.month must be 1..12")
        _require_text("SafetyPlacementEntry.category_id", self.category_id)
        if type(self.week_ordinal) is not int or self.week_ordinal < 1:
            raise InvalidDomainValueError(
                "SafetyPlacementEntry.week_ordinal must be a positive integer"
            )


@dataclass(frozen=True, slots=True)
class SafetyPlacementPolicy:
    policy_id: str
    policy_version: str
    legal_rule_version: str
    entries: tuple[SafetyPlacementEntry, ...]
    runtime_active: bool = False
    # v2: one official content focus per statutory placement (see rules.safety_placement).
    focus_rule: str | None = None
    base_school_year: int | None = None
    school_year_start_month: int = 3

    def __post_init__(self) -> None:
        if (self.focus_rule is None) != (self.base_school_year is None) or (
            self.focus_rule is not None and (self.focus_rule != FOCUS_RULE or type(self.base_school_year) is not int)
        ):
            raise InvalidDomainValueError(f"SafetyPlacementPolicy focus_rule must be {FOCUS_RULE} with a base_school_year")
        for name in ("policy_id", "policy_version", "legal_rule_version"):
            _require_text(f"SafetyPlacementPolicy.{name}", getattr(self, name))
        if not isinstance(self.entries, tuple) or not self.entries or not all(
            isinstance(entry, SafetyPlacementEntry) for entry in self.entries
        ):
            raise InvalidDomainValueError(
                "SafetyPlacementPolicy requires SafetyPlacementEntry values"
            )
        for key in ("category_id", "week_ordinal"):
            pairs = [(entry.month, getattr(entry, key)) for entry in self.entries]
            if len(set(pairs)) != len(pairs):
                raise InvalidDomainValueError(
                    f"SafetyPlacementPolicy repeats a {key} within one month"
                )
        if type(self.runtime_active) is not bool:
            raise InvalidDomainValueError(
                "SafetyPlacementPolicy.runtime_active must be a boolean"
            )

    def for_month(self, calendar_month: int) -> tuple[SafetyPlacementEntry, ...]:
        return tuple(
            sorted(
                (entry for entry in self.entries if entry.month == calendar_month),
                key=lambda entry: entry.week_ordinal,
            )
        )


@dataclass(frozen=True, slots=True)
class SafetyPlacement:
    """Why a safety_education Cell holds what it holds; independent of CellState."""

    kind: SafetyKind
    category_id: str | None
    policy_version: str
    legal_rule_version: str
    official_content_focus_ref: str | None = None

    def __post_init__(self) -> None:
        if self.official_content_focus_ref is not None and (
            self.kind is not SafetyKind.STATUTORY or not str(self.official_content_focus_ref).strip()
        ):
            raise InvalidDomainValueError("Only a STATUTORY SafetyPlacement has an official content focus")
        if not isinstance(self.kind, SafetyKind):
            raise InvalidDomainValueError("SafetyPlacement.kind is invalid")
        if self.kind is SafetyKind.STATUTORY:
            _require_text("SafetyPlacement.category_id", self.category_id)
        elif self.category_id is not None:
            raise InvalidDomainValueError(
                "A SUPPLEMENTAL SafetyPlacement has no legal category"
            )
        _require_text("SafetyPlacement.policy_version", self.policy_version)
        _require_text("SafetyPlacement.legal_rule_version", self.legal_rule_version)
