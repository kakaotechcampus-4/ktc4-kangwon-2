"""Canonical Monday-start week columns for a target calendar month."""

from __future__ import annotations

from datetime import date, timedelta

from ..domain.week_period import WeekId, WeekPeriod
from ..domain.year_month import YearMonth
from .errors import MonthlyRuleError

RULE_ID = "monthly.week_periods.ssuksak_p0_canonical"
RULE_VERSION = "v1"
MIN_WEEKDAYS_IN_TARGET_MONTH = 3


def _month_bounds(target: YearMonth) -> tuple[date, date]:
    first = date(target.calendar_year, target.calendar_month, 1)
    next_month = (
        date(target.calendar_year + 1, 1, 1)
        if target.calendar_month == 12
        else date(target.calendar_year, target.calendar_month + 1, 1)
    )
    return first, next_month - timedelta(days=1)


def _weekdays_inside(monday: date, target: YearMonth) -> int:
    return sum(
        1
        for offset in range(5)
        if YearMonth(
            (monday + timedelta(days=offset)).year,
            (monday + timedelta(days=offset)).month,
        )
        == target
    )


def canonical_week_periods(target: YearMonth) -> tuple[WeekPeriod, ...]:
    """Return weeks whose Monday-Friday span has at least three target-month days."""
    if not isinstance(target, YearMonth):
        raise MonthlyRuleError(RULE_ID, "target must be YearMonth")
    first, last = _month_bounds(target)
    monday = first - timedelta(days=first.weekday())
    periods: list[WeekPeriod] = []
    while monday <= last:
        if _weekdays_inside(monday, target) >= MIN_WEEKDAYS_IN_TARGET_MONTH:
            ordinal = len(periods) + 1
            periods.append(
                WeekPeriod(
                    week_id=WeekId.of(target, ordinal),
                    start_date=monday,
                    end_date=monday + timedelta(days=4),
                    display_label=f"{target.calendar_month}월 {ordinal}주",
                )
            )
        monday += timedelta(days=7)
    return tuple(periods)


def deactivate(
    periods: tuple[WeekPeriod, ...], week_ids: frozenset[WeekId]
) -> tuple[WeekPeriod, ...]:
    """Deactivate overrides without deleting or renumbering canonical addresses."""
    known = {period.week_id for period in periods}
    unknown = week_ids - known
    if unknown:
        raise MonthlyRuleError(
            RULE_ID,
            f"unknown canonical week ids: {sorted(str(item) for item in unknown)}",
        )
    return tuple(
        period.with_active(False) if period.week_id in week_ids else period
        for period in periods
    )
