"""Deterministic conversion from a school year to calendar periods."""

from __future__ import annotations

from ..domain.errors import InvalidDomainValueError
from ..domain.year_month import YearMonth

RULE_ID = "yearly.periods.academic_year_march_to_february"
RULE_VERSION = "v1"
ACADEMIC_MONTH_ORDER = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


def academic_year_periods(school_year: int) -> tuple[YearMonth, ...]:
    """Return March through the following February for one school year."""

    if type(school_year) is not int or not 1 <= school_year <= 9998:
        raise InvalidDomainValueError(
            "school_year must be an integer from 1 through 9998"
        )

    return tuple(
        YearMonth(
            calendar_year=school_year if month >= 3 else school_year + 1,
            calendar_month=month,
        )
        for month in ACADEMIC_MONTH_ORDER
    )


def expected_period_values(school_year: int) -> tuple[str, ...]:
    return tuple(period.value for period in academic_year_periods(school_year))
