"""Planning Core의 Port.

CLAUDE.md §17이 열거한 것만 둔다. 필요하지 않은 추상화는 추가하지 않는다.

    ThemeReferenceRepository
    PlanRepository
    LLMPort            (shared/llm/port.py)
    Clock
    IdGenerator
    OptionalContextProvider

GenerationRun은 Use Case 반환값에 포함하므로 별도 Port를 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol

from ..domain.plan import YearlyPlan
from ..domain.theme_reference import ThemeCatalog

__all__ = [
    "Clock",
    "IdGenerator",
    "OptionalContextProvider",
    "OptionalContextResult",
    "OptionalContextStatus",
    "PlanRepository",
    "ThemeReferenceRepository",
]


class ThemeReferenceRepository(Protocol):
    """Theme Catalog 조회.

    반환되는 ThemeCatalog의 `activation_status`가 신뢰 가능한 metadata다.
    외부 요청자가 활성화 상태를 지정할 수 없다.
    """

    def get_catalog(self, catalog_id: str, catalog_version: str) -> ThemeCatalog | None:
        """정확히 일치하는 catalog_id + catalog_version만 반환한다."""
        ...


class PlanRepository(Protocol):
    def save(self, plan: YearlyPlan) -> None: ...

    def get(self, plan_id: str) -> YearlyPlan | None: ...

    def find_yearly(self, classroom_ref: str, school_year: int) -> YearlyPlan | None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_plan_id(self) -> str: ...

    def new_item_id(self) -> str: ...

    def new_run_id(self) -> str: ...


class OptionalContextStatus(str, Enum):
    """Optional 외부 Context의 조회 결과 상태.

    CLAUDE.md §7 / docs/demo-source-of-truth.md §25:
    Optional Dependency 실패가 Core 생성 실패로 이어지면 안 된다.
    """

    AVAILABLE = "AVAILABLE"
    NOT_REQUESTED = "NOT_REQUESTED"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

    @property
    def is_failure(self) -> bool:
        return self in (
            OptionalContextStatus.UNAVAILABLE,
            OptionalContextStatus.TIMEOUT,
            OptionalContextStatus.ERROR,
        )


@dataclass(frozen=True, slots=True)
class OptionalContextResult:
    """Optional Context 하나의 조회 결과.

    실패를 **예외로 던지지 않고 결과 객체로** 표현하는 것이 이 타입의 존재 이유다.
    try/except 누락으로 CLAUDE.md §7이 깨질 여지를 구조적으로 없앤다.
    """

    name: str
    status: OptionalContextStatus
    payload: object | None = None
    detail: str = ""

    @property
    def is_usable(self) -> bool:
        return self.status is OptionalContextStatus.AVAILABLE and self.payload is not None


@dataclass(frozen=True, slots=True)
class OptionalContextBundle:
    """생성 1회에 사용되는 Optional Context 묶음."""

    results: tuple[OptionalContextResult, ...] = field(default_factory=tuple)

    def get(self, name: str) -> OptionalContextResult | None:
        for r in self.results:
            if r.name == name:
                return r
        return None

    @property
    def failures(self) -> tuple[OptionalContextResult, ...]:
        return tuple(r for r in self.results if r.status.is_failure)


class OptionalContextProvider(Protocol):
    """Trend / Weather / Climate 등 Optional Context 조회.

    구현체는 **예외를 던지지 않고** OptionalContextResult로 실패를 표현한다.
    """

    def fetch(self, requested: dict[str, object]) -> OptionalContextBundle: ...
