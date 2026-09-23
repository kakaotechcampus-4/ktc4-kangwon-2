"""Expected failures raised by Yearly deterministic rules."""

from __future__ import annotations

from ..domain.errors import DomainError
from ..domain.year_month import YearMonth


class YearlyRuleError(DomainError):
    """A Yearly rule could not produce or accept a deterministic result."""

    def __init__(
        self,
        rule_id: str,
        detail: str,
        *,
        period: YearMonth | None = None,
    ) -> None:
        super().__init__(detail)
        self.rule_id = rule_id
        self.detail = detail
        self.period = period


class MonthlyRuleError(DomainError):
    """A Monthly deterministic rule rejected its input or prerequisite."""

    def __init__(
        self,
        rule_id: str,
        detail: str,
        *,
        period: YearMonth | None = None,
    ) -> None:
        super().__init__(detail)
        self.rule_id = rule_id
        self.detail = detail
        self.period = period
