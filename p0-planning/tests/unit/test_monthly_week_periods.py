from datetime import date

import pytest

from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.errors import MonthlyRuleError
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods, deactivate


@pytest.mark.parametrize(
    ("target", "expected_count", "first", "last"),
    [
        (YearMonth(2021, 10), 4, date(2021, 10, 4), date(2021, 10, 29)),
        (YearMonth(2022, 2), 4, date(2022, 1, 31), date(2022, 2, 25)),
        (YearMonth(2024, 2), 4, date(2024, 2, 5), date(2024, 3, 1)),
        (YearMonth(2024, 12), 4, date(2024, 12, 2), date(2024, 12, 27)),
    ],
)
def test_canonical_week_boundary_cases(target, expected_count, first, last):
    periods = canonical_week_periods(target)

    assert len(periods) == expected_count
    assert periods[0].start_date == first
    assert periods[-1].end_date == last
    assert tuple(item.week_id.ordinal for item in periods) == tuple(range(1, expected_count + 1))


def test_friday_month_start_excludes_one_day_week():
    periods = canonical_week_periods(YearMonth(2021, 10))
    assert all(period.start_date != date(2021, 9, 27) for period in periods)


def test_deactivate_preserves_addresses_and_order():
    periods = canonical_week_periods(YearMonth(2026, 9))
    result = deactivate(periods, frozenset({WeekId("2026-09-W2")}))

    assert tuple(item.week_id for item in result) == tuple(item.week_id for item in periods)
    assert [item.active for item in result] == [True, False, True, True, True]


def test_deactivate_rejects_unknown_week():
    with pytest.raises(MonthlyRuleError):
        deactivate(
            canonical_week_periods(YearMonth(2026, 9)),
            frozenset({WeekId("2026-09-W9")}),
        )
