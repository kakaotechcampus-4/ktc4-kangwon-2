"""Calendar year/month value used by deterministic planning rules."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidDomainValueError


@dataclass(frozen=True, order=True, slots=True)
class YearMonth:
    """A calendar period value, deliberately separate from entity identifiers."""

    calendar_year: int
    calendar_month: int

    def __post_init__(self) -> None:
        if type(self.calendar_year) is not int or not 1 <= self.calendar_year <= 9999:
            raise InvalidDomainValueError(
                "YearMonth.calendar_year must be an integer from 1 through 9999"
            )
        if type(self.calendar_month) is not int or not 1 <= self.calendar_month <= 12:
            raise InvalidDomainValueError(
                "YearMonth.calendar_month must be an integer from 1 through 12"
            )

    @property
    def value(self) -> str:
        return f"{self.calendar_year:04d}-{self.calendar_month:02d}"

    def __str__(self) -> str:
        return self.value
