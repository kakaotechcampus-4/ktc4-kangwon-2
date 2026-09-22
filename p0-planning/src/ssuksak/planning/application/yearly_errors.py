"""Expected application failures for the Yearly slice."""

from __future__ import annotations

from ..domain.errors import DomainError


class YearlyApplicationError(DomainError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
