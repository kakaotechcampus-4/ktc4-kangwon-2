"""Plan 도메인의 식별자 Value Object.

CLAUDE.md §19 / docs/open-decisions.md OD-Y03:
Confirm 행위자는 표시용 담임 이름이 아닌 opaque ActorId로 식별한다.
담임 표시 이름이 ActorId 자리에 들어가는 일을 타입 수준에서 막기 위해
ActorId를 별도 Value Object로 둔다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PERIOD_KEY_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_SECTION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidIdentifierError(ValueError):
    """식별자 형식이 잘못된 경우."""


@dataclass(frozen=True, slots=True)
class ActorId:
    """Confirm/Edit 행위자의 opaque 식별자.

    인증 계층의 user_id를 그대로 전달하거나 매핑해 넣을 수 있다(OD-Y03).
    담임 표시 이름은 이 타입으로 만들 수 없다는 점이 이 클래스의 존재 이유다.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidIdentifierError("ActorId는 비어 있을 수 없다")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PlanId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidIdentifierError("PlanId는 비어 있을 수 없다")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ItemId:
    """편집 가능한 Item 인스턴스의 안정적인 식별자(OD-Y01)."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidIdentifierError("ItemId는 비어 있을 수 없다")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SemanticKey:
    """Item 의미 위치의 안정적인 식별자(OD-Y01).

    Yearly theme의 형태는 docs/demo-source-of-truth.md §14 예시와
    tests/golden/yearly_cases.json을 따라 `yearly.month.MM.theme`이다.
    표시 Label이나 배열 순번을 주소로 쓰지 않는다.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidIdentifierError("SemanticKey는 비어 있을 수 없다")

    def __str__(self) -> str:
        return self.value

    @staticmethod
    def yearly_month_theme(calendar_month: int) -> "SemanticKey":
        if not 1 <= calendar_month <= 12:
            raise InvalidIdentifierError(f"달력 월이 1..12 범위를 벗어남: {calendar_month}")
        return SemanticKey(f"yearly.month.{calendar_month:02d}.theme")

    @staticmethod
    def monthly_section(section_key: str) -> "SemanticKey":
        """Monthly Section의 의미 식별자.

        **주차 위치를 인코딩하지 않는다**(OD-M03 / 2026-09-11 Cell Address 결정 B안).
        `monthly.week.02.outdoor_play` 같은 형태를 만들지 않으며, 주차 위치는
        MonthlyPlanItem.week_id가 따로 표현한다. 같은 Section이 Template의
        display_mode에 따라 주별 Cell이 되든 월간 병합 Cell이 되든
        semantic_key는 바뀌지 않는다.
        """
        if not isinstance(section_key, str) or not _SECTION_KEY_RE.match(section_key):
            raise InvalidIdentifierError(
                "Monthly section_key는 소문자·숫자·밑줄만 사용한다: " f"{section_key!r}"
            )
        return SemanticKey(f"monthly.section.{section_key}")


@dataclass(frozen=True, slots=True)
class PeriodKey:
    """`YYYY-MM` 형태의 기간 키.

    학년도 1·2월은 school_year + 1 이므로 달력 연도가 바뀐다.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _PERIOD_KEY_RE.match(self.value):
            raise InvalidIdentifierError(f"PeriodKey는 YYYY-MM 형식이어야 한다: {self.value!r}")

    def __str__(self) -> str:
        return self.value

    @property
    def calendar_year(self) -> int:
        return int(self.value[:4])

    @property
    def calendar_month(self) -> int:
        return int(self.value[5:7])

    @staticmethod
    def of(calendar_year: int, calendar_month: int) -> "PeriodKey":
        return PeriodKey(f"{calendar_year:04d}-{calendar_month:02d}")
