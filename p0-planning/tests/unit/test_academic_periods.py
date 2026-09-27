from __future__ import annotations

import pytest

from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ItemId, PlanId
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.academic_periods import (
    ACADEMIC_MONTH_ORDER,
    academic_year_periods,
    expected_period_values,
)


def test_year_month_is_a_value_object_not_an_entity_identifier():
    period = YearMonth(2026, 3)

    assert period.value == "2026-03"
    assert str(period) == "2026-03"
    assert not isinstance(period, (PlanId, ItemId))


@pytest.mark.parametrize(
    ("year", "month"),
    [(0, 3), (10000, 3), (True, 3), (2026, 0), (2026, 13), (2026, False)],
)
def test_year_month_rejects_invalid_values(year: object, month: object):
    with pytest.raises(InvalidDomainValueError):
        YearMonth(year, month)  # type: ignore[arg-type]


def test_academic_year_is_march_through_following_february():
    periods = academic_year_periods(2026)

    assert ACADEMIC_MONTH_ORDER == (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)
    assert len(periods) == 12
    assert expected_period_values(2026) == (
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
        "2027-01",
        "2027-02",
    )


@pytest.mark.parametrize("bad_year", [0, -1, 9999, True, "2026", None])
def test_academic_year_rejects_values_that_cannot_form_twelve_periods(bad_year):
    with pytest.raises(InvalidDomainValueError):
        academic_year_periods(bad_year)
