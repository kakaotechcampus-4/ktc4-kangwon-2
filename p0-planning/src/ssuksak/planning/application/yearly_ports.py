"""Narrow provider-neutral text generation contract used by Yearly only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..domain.errors import InvalidDomainValueError
from ..domain.year_month import YearMonth
from .ports import OptionalContextResult


@dataclass(frozen=True, slots=True)
class ThemeTextRequest:
    period: YearMonth
    theme_id: str
    reference_label: str
    target_ages: tuple[int, ...]
    optional_context: tuple[OptionalContextResult, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.period, YearMonth):
            raise InvalidDomainValueError("ThemeTextRequest.period must be YearMonth")
        for name in ("theme_id", "reference_label"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"ThemeTextRequest.{name} must be non-blank"
                )
        if not isinstance(self.target_ages, tuple) or not self.target_ages:
            raise InvalidDomainValueError(
                "ThemeTextRequest.target_ages must be a non-empty tuple"
            )
        if not isinstance(self.optional_context, tuple) or not all(
            isinstance(result, OptionalContextResult)
            for result in self.optional_context
        ):
            raise InvalidDomainValueError(
                "ThemeTextRequest.optional_context must contain OptionalContextResult"
            )


@dataclass(frozen=True, slots=True)
class ThemeTextResult:
    period: YearMonth
    theme_id: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.period, YearMonth):
            raise InvalidDomainValueError("ThemeTextResult.period must be YearMonth")
        for name in ("theme_id", "value"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"ThemeTextResult.{name} must be non-blank"
                )


@runtime_checkable
class ThemeTextGenerator(Protocol):
    def generate(
        self, requests: tuple[ThemeTextRequest, ...]
    ) -> tuple[ThemeTextResult, ...]: ...
