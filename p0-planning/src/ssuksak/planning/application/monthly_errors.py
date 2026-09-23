"""Expected failures from Monthly application use cases."""

from __future__ import annotations

from ..domain.errors import DomainError


class MonthlyApplicationError(DomainError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
