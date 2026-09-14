"""SSUKSAK_P0_CANONICAL_WEEK_POLICY 검증.

OD-M02가 확정한 규칙을 그대로 테스트한다. 이 규칙은 국가 표준이 아니라
제품 내부 deterministic policy이므로, 여기서 고정하는 것은 "우리 제품이
이렇게 계산한다"이지 "전국이 이렇다"가 아니다.
"""

from __future__ import annotations

from datetime import date

import pytest

from ssuksak.planning.domain.identifiers import InvalidIdentifierError, PeriodKey
from ssuksak.planning.domain.week_period import WeekId, WeekPeriod
from ssuksak.planning.rules.monthly_week_periods import (
    MIN_WEEKDAYS_IN_TARGET_MONTH,
    POLICY_NAME,
    RULE_ID,
    RULE_VERSION,
    canonical_week_periods,
    deactivate,
    display_label,
)


def weeks(target: str) -> tuple[WeekPeriod, ...]:
    return canonical_week_periods(PeriodKey(target))


# ------------------------------------------------------------ 주차 개수


@pytest.mark.parametrize(
    "target,expected",
    [
        ("2026-03", 4),
        ("2026-04", 5),
        ("2026-05", 4),
        ("2026-06", 4),
        ("2026-07", 5),
        ("2026-08", 4),
        ("2026-09", 5),
        ("2026-10", 4),
        ("2026-11", 4),
        ("2026-12", 5),
        ("2027-01", 4),
        ("2027-02", 4),
    ],
)
def test_week_count_for_academic_year_2026(target: str, expected: int):
    """학년도 2026 12개월 전체. 실측 대조 기준은 2026-09=5, 2026-03=4다."""
    assert len(weeks(target)) == expected


def test_september_2026_is_five_weeks():
    assert len(weeks("2026-09")) == 5


def test_march_2026_is_four_weeks():
    assert len(weeks("2026-03")) == 4


# ------------------------------------------------------- 경계와 clip 금지


def test_april_2026_first_week_starts_in_previous_month():
    assert weeks("2026-04")[0].start_date == date(2026, 3, 30)


def test_september_2026_first_week_starts_in_previous_month():
    """실측: 시립새봄·아이들세상·엄지 3/3이 8월 31일에 시작한다."""
    assert weeks("2026-09")[0].start_date == date(2026, 8, 31)


def test_september_2026_last_week_ends_in_next_month():
    assert weeks("2026-09")[-1].end_date == date(2026, 10, 2)


def test_start_and_end_are_not_clipped_to_month():
    """대상 월 경계로 자르지 않는다."""
    for target in ("2026-04", "2026-07", "2026-09", "2026-12"):
        ws = weeks(target)
        crossing = [w for w in ws if w.crosses_month_start or w.crosses_month_end]
        assert crossing, f"{target}에 경계를 넘는 주가 있어야 한다"
        for w in crossing:
            in_month = w.start_date.strftime("%Y-%m") == target
            assert not (in_month and w.crosses_month_start)


def test_december_2026_crosses_into_next_year():
    ws = weeks("2026-12")
    assert ws[0].start_date == date(2026, 11, 30)
    assert ws[-1].end_date == date(2027, 1, 1)


def test_every_week_is_monday_to_friday():
    for target in ("2026-03", "2026-09", "2027-02"):
        for w in weeks(target):
            assert w.start_date.weekday() == 0, "월요일 시작"
            assert w.end_date.weekday() == 4, "금요일 종료"
            assert (w.end_date - w.start_date).days == 4


def test_min_weekday_threshold_is_three():
    assert MIN_WEEKDAYS_IN_TARGET_MONTH == 3


# --------------------------------------------------------- week_id 안정성


def test_same_input_produces_same_week_ids():
    a = [w.week_id.value for w in weeks("2026-09")]
    b = [w.week_id.value for w in weeks("2026-09")]
    assert a == b == [
        "2026-09-W1", "2026-09-W2", "2026-09-W3", "2026-09-W4", "2026-09-W5",
    ]


def test_week_ids_are_unique():
    for target in ("2026-03", "2026-09", "2026-12"):
        ids = [w.week_id.value for w in weeks(target)]
        assert len(ids) == len(set(ids))


def test_week_periods_are_ordered_by_start_date():
    for target in ("2026-03", "2026-09", "2026-12"):
        ws = weeks(target)
        assert list(ws) == sorted(ws, key=lambda w: w.start_date)
        assert [w.week_id.ordinal for w in ws] == list(range(1, len(ws) + 1))


def test_week_id_carries_target_month_and_ordinal():
    w = weeks("2026-09")[2]
    assert w.week_id.target_month == "2026-09"
    assert w.week_id.ordinal == 3


@pytest.mark.parametrize("bad", ["2026-09-W0", "2026-9-W1", "2026-13-W1", "2026-09W1", ""])
def test_week_id_rejects_invalid_format(bad: str):
    with pytest.raises(InvalidIdentifierError):
        WeekId(bad)


def test_week_id_rejects_non_positive_ordinal():
    with pytest.raises(InvalidIdentifierError):
        WeekId.of("2026-09", 0)


# ------------------------------------------------------------ display_label


def test_display_label_is_separate_from_canonical_key():
    """8월에 시작하는 주도 `9월 1주`로 표기된다. 실측 시립새봄과 같다."""
    w = weeks("2026-09")[0]
    assert w.display_label == "9월 1주"
    assert w.start_date.month == 8
    assert w.week_id.value == "2026-09-W1"


def test_display_label_helper():
    assert display_label(PeriodKey("2026-03"), 4) == "3월 4주"


# --------------------------------------------------------------- Override


def test_deactivate_preserves_canonical_list_and_ordinals():
    """Override는 canonical WeekPeriod를 삭제하거나 재번호화하지 않는다."""
    before = weeks("2026-09")
    after = deactivate(before, frozenset({"2026-09-W3"}))

    assert len(after) == len(before) == 5
    assert [w.week_id.value for w in after] == [w.week_id.value for w in before]
    assert [w.start_date for w in after] == [w.start_date for w in before]
    assert [w.display_label for w in after] == [w.display_label for w in before]
    assert [w.active for w in after] == [True, True, False, True, True]


def test_deactivate_rejects_unknown_week_id():
    with pytest.raises(ValueError, match="canonical 목록에 없는"):
        deactivate(weeks("2026-09"), frozenset({"2026-09-W9"}))


def test_with_active_returns_new_instance_and_keeps_identity():
    w = weeks("2026-09")[0]
    off = w.with_active(False)
    assert off is not w
    assert w.active is True
    assert off.active is False
    assert off.week_id == w.week_id
    assert off.start_date == w.start_date


def test_week_period_is_frozen():
    w = weeks("2026-09")[0]
    with pytest.raises(Exception):
        w.active = False  # type: ignore[misc]


# ----------------------------------------------------------------- 기타


def test_week_period_rejects_reversed_dates():
    with pytest.raises(ValueError, match="end_date"):
        WeekPeriod(
            week_id=WeekId("2026-09-W1"),
            start_date=date(2026, 9, 4),
            end_date=date(2026, 8, 31),
            display_label="9월 1주",
        )


def test_week_period_rejects_blank_label():
    with pytest.raises(ValueError, match="display_label"):
        WeekPeriod(
            week_id=WeekId("2026-09-W1"),
            start_date=date(2026, 8, 31),
            end_date=date(2026, 9, 4),
            display_label="   ",
        )


def test_policy_identifiers_are_stable():
    assert POLICY_NAME == "SSUKSAK_P0_CANONICAL_WEEK_POLICY"
    assert RULE_ID == "monthly.week_periods.ssuksak_p0_canonical"
    assert RULE_VERSION == "v1"


def test_display_group_is_contract_only_and_defaults_to_none():
    """M1에서 Generate가 채우지 않는다."""
    assert all(w.display_group is None for w in weeks("2026-09"))


def test_week_days_override_is_not_implemented_in_m1():
    """월~토 등 요일 폭 Override는 이번 Slice 범위가 아니다."""
    import ssuksak.planning.rules.monthly_week_periods as mod

    assert not hasattr(mod, "WeekDays")
    assert mod.WEEKDAYS_PER_WEEK == 5
