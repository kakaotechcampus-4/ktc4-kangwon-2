"""결정론적 Clock / IdGenerator.

CLAUDE.md §20: 결정론적 Rule은 Unit Test를 작성한다.
Audit `occurred_at`과 ID가 재현 가능해야 Golden Test가 안정적으로 통과한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count


class FixedClock:
    """고정 시각 Clock. `advance_seconds`를 주면 호출마다 증가한다."""

    def __init__(
        self,
        start: datetime | None = None,
        *,
        advance_seconds: int = 0,
    ) -> None:
        self._current = start or datetime(2026, 9, 10, 9, 0, 0, tzinfo=UTC)
        self._advance = advance_seconds

    def now(self) -> datetime:
        value = self._current
        if self._advance:
            self._current = self._current + timedelta(seconds=self._advance)
        return value


class DeterministicIdGenerator:
    """접두사 + 단조 증가 카운터로 재현 가능한 ID를 만든다."""

    def __init__(self, prefix: str = "fixture") -> None:
        self._prefix = prefix
        self._plan = count(1)
        self._item = count(1)
        self._run = count(1)

    def new_plan_id(self) -> str:
        return f"{self._prefix}_plan_{next(self._plan):03d}"

    def new_item_id(self) -> str:
        return f"{self._prefix}_item_{next(self._item):03d}"

    def new_run_id(self) -> str:
        return f"{self._prefix}_run_{next(self._run):03d}"
