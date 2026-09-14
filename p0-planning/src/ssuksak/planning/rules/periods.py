"""학년도 기간 산출 Rule.

docs/demo-source-of-truth.md §14: `school_year`는 3월부터 다음 해 2월까지의
학년도를 뜻한다. 1·2월은 school_year + 1이다.
"""

from __future__ import annotations

from ..domain.identifiers import PeriodKey
from ..domain.plan import ACADEMIC_MONTH_ORDER

RULE_ID = "yearly.periods.academic_year_march_to_february"
RULE_VERSION = "v1"


def academic_period_keys(school_year: int) -> tuple[PeriodKey, ...]:
    """학년도 12개 기간을 3월 → 다음 해 2월 순서로 만든다."""
    keys: list[PeriodKey] = []
    for calendar_month in ACADEMIC_MONTH_ORDER:
        calendar_year = school_year if calendar_month >= 3 else school_year + 1
        keys.append(PeriodKey.of(calendar_year, calendar_month))
    return tuple(keys)


def expected_period_key_values(school_year: int) -> tuple[str, ...]:
    return tuple(k.value for k in academic_period_keys(school_year))
