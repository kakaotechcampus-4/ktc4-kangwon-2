"""Stub OptionalContextProvider.

CLAUDE.md §7: Optional Dependency 실패가 Core 생성을 실패시키지 않는다.
이 Stub은 실패를 **예외가 아니라 결과 객체로** 표현한다.
Golden case 4가 `trend_provider: {"result": "TIMEOUT"}`을 주입한다.
"""

from __future__ import annotations

from ..planning.application.ports import (
    OptionalContextBundle,
    OptionalContextResult,
    OptionalContextStatus,
)


class StubOptionalContextProvider:
    def __init__(self, outcomes: dict[str, object] | None = None) -> None:
        """Args:
        outcomes: 이름 → `"TIMEOUT"` / `"ERROR"` / `"UNAVAILABLE"` 같은 상태 문자열,
            또는 사용 가능한 payload 객체.
        """
        self._outcomes = dict(outcomes or {})
        self.fetch_count = 0

    def fetch(self, requested: dict[str, object]) -> OptionalContextBundle:
        self.fetch_count += 1
        results: list[OptionalContextResult] = []

        for name in requested:
            outcome = self._outcomes.get(name, None)

            if outcome is None:
                results.append(
                    OptionalContextResult(name=name, status=OptionalContextStatus.NOT_REQUESTED)
                )
                continue

            if isinstance(outcome, str):
                try:
                    status = OptionalContextStatus(outcome.upper())
                except ValueError:
                    status = OptionalContextStatus.ERROR
                results.append(
                    OptionalContextResult(name=name, status=status, detail=outcome)
                )
                continue

            results.append(
                OptionalContextResult(
                    name=name, status=OptionalContextStatus.AVAILABLE, payload=outcome
                )
            )

        return OptionalContextBundle(results=tuple(results))
