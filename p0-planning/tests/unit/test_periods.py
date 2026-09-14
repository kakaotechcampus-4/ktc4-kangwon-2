"""학년도 기간 산출 Rule 단위 테스트 (CLAUDE.md §20 'Academic month order')."""

from __future__ import annotations

import pytest

from ssuksak.planning.domain.identifiers import (
    InvalidIdentifierError,
    PeriodKey,
    SemanticKey,
)
from ssuksak.planning.domain.plan import ACADEMIC_MONTH_ORDER, academic_index_of
from ssuksak.planning.rules.periods import (
    academic_period_keys,
    expected_period_key_values,
)


def test_academic_order_starts_in_march_and_ends_in_february():
    assert ACADEMIC_MONTH_ORDER == (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)


def test_twelve_periods_for_school_year():
    keys = academic_period_keys(2026)
    assert len(keys) == 12


def test_january_and_february_roll_into_next_calendar_year():
    values = expected_period_key_values(2026)
    assert values[0] == "2026-03"
    assert values[9] == "2026-12"
    assert values[10] == "2027-01"
    assert values[11] == "2027-02"


def test_no_duplicate_periods():
    values = expected_period_key_values(2026)
    assert len(set(values)) == 12


@pytest.mark.parametrize("school_year", [2024, 2025, 2026, 2030])
def test_boundary_holds_for_multiple_school_years(school_year: int):
    values = expected_period_key_values(school_year)
    assert values[0] == f"{school_year}-03"
    assert values[-1] == f"{school_year + 1}-02"


def test_academic_index_is_derived_and_one_based():
    """academic_index는 derived helper다. canonical field가 아니다."""
    assert academic_index_of(2026, PeriodKey("2026-03")) == 1
    assert academic_index_of(2026, PeriodKey("2026-12")) == 10
    assert academic_index_of(2026, PeriodKey("2027-01")) == 11
    assert academic_index_of(2026, PeriodKey("2027-02")) == 12


def test_academic_index_orders_differently_from_calendar_month():
    """1·2월이 뒤로 가야 한다. 달력 월 정렬로는 얻을 수 없는 순서다."""
    keys = academic_period_keys(2026)
    by_calendar = sorted(keys, key=lambda k: (k.calendar_month,))
    by_academic = sorted(keys, key=lambda k: academic_index_of(2026, k))

    assert [k.value for k in by_academic] == list(expected_period_key_values(2026))
    assert [k.value for k in by_calendar] != [k.value for k in by_academic]


def test_period_key_rejects_malformed_values():
    for bad in ("2026-13", "2026-00", "26-03", "2026/03", "2026-3", ""):
        with pytest.raises(InvalidIdentifierError):
            PeriodKey(bad)


def test_semantic_key_is_zero_padded_month():
    assert SemanticKey.yearly_month_theme(3).value == "yearly.month.03.theme"
    assert SemanticKey.yearly_month_theme(10).value == "yearly.month.10.theme"


def test_semantic_key_rejects_out_of_range_month():
    for bad in (0, 13, -1):
        with pytest.raises(InvalidIdentifierError):
            SemanticKey.yearly_month_theme(bad)
