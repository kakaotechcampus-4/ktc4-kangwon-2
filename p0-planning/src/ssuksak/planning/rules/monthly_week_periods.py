"""SSUKSAK_P0_CANONICAL_WEEK_POLICY — Monthly WeekPeriod 산출 Rule.

docs/open-decisions.md OD-M02 (`RESOLVED_FOR_P0`, 2026-09-11):

    Monday-start week 중 월~금 5일 가운데 target calendar month에 속하는 날이
    3일 이상인 주를 ordered list로 산출한다.
    start_date / end_date를 target month 경계로 clip하지 않는다.
    week_id = YYYY-MM-Wn 이며 동일 입력에서 항상 동일하다.
    Override는 canonical WeekPeriod를 삭제하거나 재번호화하지 않는다.

**이 규칙은 국가·법정·어린이집 공통 주차 표준이 아니다.** 제품 내부
deterministic policy이며 기관 실제 양식이 다르면 Override 또는 후속 Template
adapter가 우선한다.

실측 근거(docs/template-a-validation.md §6.3): 명시적 날짜 범위를 표기한 3기관이
모두 월요일 시작이고 1주가 전월 8월 31일에 시작한다. 이 규칙은 2026-09 → 5주,
2026-03 → 4주를 산출해 관측 9건 중 7건과 일치한다. 불일치 2건(엄지 4주,
큰빛 p.1 헤더 4주)은 기관 운영상 절단이며 Override 대상이다.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..domain.identifiers import PeriodKey
from ..domain.week_period import WeekId, WeekPeriod

POLICY_NAME = "SSUKSAK_P0_CANONICAL_WEEK_POLICY"
RULE_ID = "monthly.week_periods.ssuksak_p0_canonical"
RULE_VERSION = "v1"

MIN_WEEKDAYS_IN_TARGET_MONTH = 3
"""월~금 5일 가운데 대상 월에 속해야 하는 최소 일수."""

WEEKDAYS_PER_WEEK = 5
"""월~금. `week_days` Override(MON_SAT 등)는 M1에서 구현하지 않는다."""


def _month_bounds(target: PeriodKey) -> tuple[date, date]:
    year, month = target.calendar_year, target.calendar_month
    first = date(year, month, 1)
    last = (
        date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    ) - timedelta(days=1)
    return first, last


def _weekdays_inside(monday: date, target: PeriodKey) -> int:
    return sum(
        1
        for offset in range(WEEKDAYS_PER_WEEK)
        if (monday + timedelta(days=offset)).month == target.calendar_month
        and (monday + timedelta(days=offset)).year == target.calendar_year
    )


def canonical_week_periods(target_month: PeriodKey) -> tuple[WeekPeriod, ...]:
    """대상 월의 canonical WeekPeriod 목록을 순서대로 만든다.

    동일 입력이면 항상 동일한 결과를 낸다. 외부 상태를 읽지 않는다.
    """
    first, last = _month_bounds(target_month)
    monday = first - timedelta(days=first.weekday())

    periods: list[WeekPeriod] = []
    ordinal = 0
    while monday <= last:
        if _weekdays_inside(monday, target_month) >= MIN_WEEKDAYS_IN_TARGET_MONTH:
            ordinal += 1
            periods.append(
                WeekPeriod(
                    week_id=WeekId.of(target_month.value, ordinal),
                    # 실제 월요일~금요일. 대상 월 경계로 clip하지 않는다.
                    start_date=monday,
                    end_date=monday + timedelta(days=WEEKDAYS_PER_WEEK - 1),
                    display_label=display_label(target_month, ordinal),
                )
            )
        monday += timedelta(days=7)

    if not periods:  # pragma: no cover - 달력상 발생할 수 없다
        raise ValueError(f"canonical WeekPeriod가 비었다: {target_month.value}")
    return tuple(periods)


def display_label(target_month: PeriodKey, ordinal: int) -> str:
    """`9월 1주` 형태의 표시 문자열.

    canonical key와 분리된 값이다. 실측에서 시립새봄이 8월에 시작하는 주를
    `9월 1주`로 표기한다.
    """
    return f"{target_month.calendar_month}월 {ordinal}주"


def deactivate(
    periods: tuple[WeekPeriod, ...], week_ids: frozenset[str]
) -> tuple[WeekPeriod, ...]:
    """지정한 주를 비활성화한다.

    canonical 목록에서 **삭제하지 않고 순번도 바꾸지 않는다**(OD-M02).
    휴원·연휴 Override가 주소 안정성을 깨뜨리지 못하게 하는 지점이다.
    """
    unknown = week_ids - {p.week_id.value for p in periods}
    if unknown:
        raise ValueError(f"canonical 목록에 없는 week_id다: {sorted(unknown)}")
    return tuple(
        p.with_active(False) if p.week_id.value in week_ids else p for p in periods
    )
