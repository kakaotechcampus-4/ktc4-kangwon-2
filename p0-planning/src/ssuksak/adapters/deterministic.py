"""Deterministic test adapters for time and identity."""

from __future__ import annotations

from datetime import datetime
from itertools import count

from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ItemId, PlanId


class FixedClock:
    def __init__(self, value: datetime) -> None:
        if not _is_aware(value):
            raise InvalidDomainValueError(
                "FixedClock requires a timezone-aware datetime"
            )
        self._value = value

    def now(self) -> datetime:
        return self._value


class DeterministicIdGenerator:
    """Generate reproducible opaque IDs from independent monotonic counters."""

    def __init__(self, prefix: str = "test") -> None:
        if not isinstance(prefix, str) or not prefix.strip():
            raise InvalidDomainValueError(
                "DeterministicIdGenerator.prefix must be non-blank"
            )
        self._prefix = prefix
        self._plan_counter = count(1)
        self._item_counter = count(1)

    def new_plan_id(self) -> PlanId:
        return PlanId(f"{self._prefix}_plan_{next(self._plan_counter):03d}")

    def new_item_id(self) -> ItemId:
        return ItemId(f"{self._prefix}_item_{next(self._item_counter):03d}")


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )
