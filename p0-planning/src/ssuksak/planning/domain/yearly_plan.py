"""Immutable Yearly Plan aggregate built from Planning Core primitives."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from .errors import InvalidDomainValueError, InvalidStateTransitionError
from .identifiers import ActorId, ItemId, PlanId
from .plan import PlanItem, PlanStatus
from .provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
)
from .year_month import YearMonth

_ACADEMIC_MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


@dataclass(frozen=True, slots=True)
class YearlyPeriod:
    """One required monthly Theme item in a Yearly Plan."""

    period: YearMonth
    theme: PlanItem

    def __post_init__(self) -> None:
        if not isinstance(self.period, YearMonth):
            raise InvalidDomainValueError("YearlyPeriod.period must be YearMonth")
        if not isinstance(self.theme, PlanItem):
            raise InvalidDomainValueError("YearlyPeriod.theme must be PlanItem")
        if len(self.theme_references) != 1:
            raise InvalidDomainValueError(
                "YearlyPeriod.theme requires exactly one THEME_REFERENCE evidence"
            )

    @property
    def theme_references(self) -> tuple[EvidenceSource, ...]:
        return tuple(
            source
            for source in self.theme.evidence
            if source.source_type is EvidenceSourceType.THEME_REFERENCE
        )

    @property
    def theme_id(self) -> str:
        return self.theme_references[0].source_id


@dataclass(frozen=True, slots=True)
class YearlyPlan:
    """Top-level Yearly aggregate; it has no parent lineage."""

    plan_id: PlanId
    school_year: int
    classroom_ref: str
    target_ages: frozenset[int]
    status: PlanStatus
    periods: tuple[YearlyPeriod, ...]
    audit: AuditHistory = field(default_factory=AuditHistory)

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, PlanId):
            raise InvalidDomainValueError("YearlyPlan.plan_id must be PlanId")
        if type(self.school_year) is not int or not 1 <= self.school_year <= 9998:
            raise InvalidDomainValueError(
                "YearlyPlan.school_year must be an integer from 1 through 9998"
            )
        if not isinstance(self.classroom_ref, str) or not self.classroom_ref.strip():
            raise InvalidDomainValueError(
                "YearlyPlan.classroom_ref must be a non-blank string"
            )
        if not isinstance(self.target_ages, frozenset) or not self.target_ages:
            raise InvalidDomainValueError(
                "YearlyPlan.target_ages must be a non-empty frozenset"
            )
        if any(type(age) is not int or age not in {3, 4, 5} for age in self.target_ages):
            raise InvalidDomainValueError(
                "YearlyPlan.target_ages supports P0 ages 3, 4, and 5 only"
            )
        if not isinstance(self.status, PlanStatus):
            raise InvalidDomainValueError("YearlyPlan.status must be PlanStatus")
        if not isinstance(self.periods, tuple) or not all(
            isinstance(period, YearlyPeriod) for period in self.periods
        ):
            raise InvalidDomainValueError(
                "YearlyPlan.periods must be a tuple of YearlyPeriod"
            )
        if tuple(period.period.value for period in self.periods) != _expected_periods(
            self.school_year
        ):
            raise InvalidDomainValueError(
                "YearlyPlan.periods must cover March through the following February"
            )
        item_ids = tuple(period.theme.item_id for period in self.periods)
        if len(set(item_ids)) != len(item_ids):
            raise InvalidDomainValueError(
                "YearlyPlan period items must have unique ItemId values"
            )
        if not isinstance(self.audit, AuditHistory):
            raise InvalidDomainValueError("YearlyPlan.audit must be AuditHistory")
        if not any(
            event.event_type is AuditEventType.CREATED for event in self.audit
        ):
            raise InvalidDomainValueError("YearlyPlan.audit requires a CREATED event")
        for event in self.audit:
            if event.plan_id != self.plan_id or event.item_id is not None:
                raise InvalidDomainValueError(
                    "YearlyPlan audit events must belong to the aggregate"
                )
        for period in self.periods:
            if not any(
                event.event_type is AuditEventType.CREATED
                for event in period.theme.audit
            ):
                raise InvalidDomainValueError(
                    "Every Yearly theme item requires a CREATED audit event"
                )
            for event in period.theme.audit:
                if (
                    event.plan_id != self.plan_id
                    or event.item_id != period.theme.item_id
                ):
                    raise InvalidDomainValueError(
                        "Yearly item audit events must match plan_id and item_id"
                    )

    @property
    def items(self) -> tuple[PlanItem, ...]:
        return tuple(period.theme for period in self.periods)

    def find_item(self, item_id: ItemId) -> tuple[int, YearlyPeriod] | None:
        if not isinstance(item_id, ItemId):
            raise InvalidDomainValueError("YearlyPlan.find_item requires ItemId")
        for index, period in enumerate(self.periods):
            if period.theme.item_id == item_id:
                return index, period
        return None

    def ensure_mutable(self, operation: str) -> None:
        if not isinstance(operation, str) or not operation.strip():
            raise InvalidDomainValueError("operation must be non-blank")
        if not self.status.is_mutable:
            raise InvalidStateTransitionError(
                f"{operation} is not allowed for a CONFIRMED Yearly Plan"
            )

    def replace_item(self, item_id: ItemId, replacement: PlanItem) -> YearlyPlan:
        self.ensure_mutable("replace_item")
        found = self.find_item(item_id)
        if found is None:
            raise InvalidDomainValueError(f"Yearly item not found: {item_id}")
        if not isinstance(replacement, PlanItem):
            raise InvalidDomainValueError("replacement must be PlanItem")
        if replacement.item_id != item_id:
            raise InvalidDomainValueError(
                "Yearly item replacement must preserve ItemId"
            )
        index, period = found
        updated_periods = list(self.periods)
        updated_periods[index] = replace(period, theme=replacement)
        return replace(self, periods=tuple(updated_periods))

    def confirm(self, *, actor_id: ActorId, occurred_at: datetime) -> YearlyPlan:
        self.ensure_mutable("confirm")
        event = AuditEvent(
            event_type=AuditEventType.CONFIRMED,
            occurred_at=occurred_at,
            plan_id=self.plan_id,
            actor_id=actor_id,
        )
        return replace(
            self,
            status=PlanStatus.CONFIRMED,
            audit=self.audit.append(event),
        )


def _expected_periods(school_year: int) -> tuple[str, ...]:
    return tuple(
        YearMonth(
            school_year if month >= 3 else school_year + 1,
            month,
        ).value
        for month in _ACADEMIC_MONTHS
    )
