"""Monthly WeekPeriod Value Object.

docs/open-decisions.md OD-M02 (`RESOLVED_FOR_P0`, 2026-09-11):
`SSUKSAK_P0_CANONICAL_WEEK_POLICY`는 국가·법정·어린이집 공통 주차 표준이 아니라
**제품 내부 deterministic policy**다. 기관 실제 양식이 다르면 Override 또는
후속 Template adapter가 우선한다.

이 모듈은 값 타입만 정의한다. 산출 규칙은 rules/monthly_week_periods.py에 있다.

`WeekPeriod`는 frozen이다. Override가 canonical WeekPeriod를 **삭제하거나
재번호화하지 못하게** 하는 것이 frozen의 존재 이유다. 비활성화는 삭제가 아니라
`week_id`·날짜·순번을 그대로 둔 새 인스턴스를 만든다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

from .identifiers import InvalidIdentifierError

_WEEK_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])-W([1-9]\d?)$")


@dataclass(frozen=True, slots=True)
class WeekId:
    """`YYYY-MM-Wn` 형태의 주차 식별자.

    `n`은 해당 target_month의 canonical ordered WeekPeriod 순번(1-based)이다.
    동일 입력에서 항상 동일한 값이어야 하며 Edit / Regenerate / Override로
    바뀌지 않는다(OD-M02).
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _WEEK_ID_RE.match(self.value):
            raise InvalidIdentifierError(
                f"WeekId는 YYYY-MM-Wn 형식이어야 한다: {self.value!r}"
            )

    def __str__(self) -> str:
        return self.value

    @property
    def target_month(self) -> str:
        return self.value[:7]

    @property
    def ordinal(self) -> int:
        return int(self.value.split("-W")[1])

    @staticmethod
    def of(target_month: str, ordinal: int) -> "WeekId":
        if ordinal < 1:
            raise InvalidIdentifierError(f"주차 순번은 1 이상이어야 한다: {ordinal}")
        return WeekId(f"{target_month}-W{ordinal}")


@dataclass(frozen=True, slots=True)
class WeekPeriod:
    """ordered WeekPeriod 하나.

    `start_date`와 `end_date`는 **실제 날짜이며 대상 월 경계로 clip하지 않는다**.
    첫 주가 전월에 시작하거나 마지막 주가 다음 월에 끝날 수 있다(OD-M02).

    `display_label`은 canonical key와 분리된 표시 문자열이다. 실측에서 시립새봄이
    8월에 시작하는 주를 `9월 1주`로 표기한다.
    """

    week_id: WeekId
    start_date: date
    end_date: date
    display_label: str
    active: bool = True
    display_group: str | None = None
    """표시 병합 그룹. Contract로만 열어 두며 M1에서 Generate가 채우지 않는다."""

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError(
                f"WeekPeriod의 end_date가 start_date보다 앞선다: "
                f"{self.start_date} ~ {self.end_date}"
            )
        if not self.display_label or not self.display_label.strip():
            raise ValueError("WeekPeriod.display_label은 비어 있을 수 없다")

    @property
    def crosses_month_start(self) -> bool:
        """첫 주가 전월에서 시작하는가."""
        return self.start_date.strftime("%Y-%m") != self.week_id.target_month

    @property
    def crosses_month_end(self) -> bool:
        """마지막 주가 다음 월에서 끝나는가."""
        return self.end_date.strftime("%Y-%m") != self.week_id.target_month

    def with_active(self, active: bool) -> "WeekPeriod":
        """활성 여부만 바꾼 새 인스턴스.

        `week_id`·날짜·`display_label`은 그대로 유지한다. Override가 canonical을
        삭제·재번호화하지 않는다는 OD-M02 규칙을 타입 수준에서 보장한다.
        """
        return replace(self, active=active)
