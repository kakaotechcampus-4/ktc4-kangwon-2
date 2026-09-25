"""Immutable identifiers and date ranges for Monthly week columns."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta

from .errors import InvalidDomainValueError
from .year_month import YearMonth

_WEEK_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])-W([1-9]\d?)$")


@dataclass(frozen=True, slots=True)
class WeekId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _WEEK_ID_RE.fullmatch(self.value) is None:
            raise InvalidDomainValueError("WeekId must use YYYY-MM-Wn format")

    @property
    def target_month(self) -> YearMonth:
        year, month = self.value[:7].split("-")
        return YearMonth(int(year), int(month))

    @property
    def ordinal(self) -> int:
        return int(self.value.split("-W", maxsplit=1)[1])

    @classmethod
    def of(cls, target_month: YearMonth, ordinal: int) -> WeekId:
        if not isinstance(target_month, YearMonth):
            raise InvalidDomainValueError("WeekId.of requires YearMonth")
        if type(ordinal) is not int or ordinal < 1:
            raise InvalidDomainValueError("WeekId ordinal must be a positive integer")
        return cls(f"{target_month.value}-W{ordinal}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class WeekPeriod:
    week_id: WeekId
    start_date: date
    end_date: date
    display_label: str
    active: bool = True
    display_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError("WeekPeriod.week_id must be WeekId")
        if not isinstance(self.start_date, date) or not isinstance(self.end_date, date):
            raise InvalidDomainValueError("WeekPeriod dates must be date values")
        if self.start_date.weekday() != 0:
            raise InvalidDomainValueError("WeekPeriod must start on Monday")
        if self.end_date != self.start_date + timedelta(days=4):
            raise InvalidDomainValueError("WeekPeriod must end on Friday")
        if not isinstance(self.display_label, str) or not self.display_label.strip():
            raise InvalidDomainValueError("WeekPeriod.display_label must be non-blank")
        if type(self.active) is not bool:
            raise InvalidDomainValueError("WeekPeriod.active must be a boolean")
        if self.display_group is not None and (
            not isinstance(self.display_group, str) or not self.display_group.strip()
        ):
            raise InvalidDomainValueError(
                "WeekPeriod.display_group must be non-blank when set"
            )

    @property
    def crosses_month_start(self) -> bool:
        return YearMonth(self.start_date.year, self.start_date.month) != self.week_id.target_month

    @property
    def crosses_month_end(self) -> bool:
        return YearMonth(self.end_date.year, self.end_date.month) != self.week_id.target_month

    def with_active(self, active: bool) -> WeekPeriod:
        if type(active) is not bool:
            raise InvalidDomainValueError("WeekPeriod.active must be a boolean")
        return replace(self, active=active)
