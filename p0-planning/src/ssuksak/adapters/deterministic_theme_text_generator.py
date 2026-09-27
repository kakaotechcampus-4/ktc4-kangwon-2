"""Deterministic test adapter for the narrow ThemeTextGenerator port."""

from __future__ import annotations

from ssuksak.planning.application.yearly_ports import (
    ThemeTextRequest,
    ThemeTextResult,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError


class DeterministicThemeTextGenerator:
    """Return Reference labels with configurable fixed decoration."""

    def __init__(self, *, prefix: str = "", suffix: str = "") -> None:
        if not isinstance(prefix, str) or not isinstance(suffix, str):
            raise InvalidDomainValueError(
                "DeterministicThemeTextGenerator decoration must be strings"
            )
        self._prefix = prefix
        self._suffix = suffix
        self.batches: list[tuple[ThemeTextRequest, ...]] = []

    @property
    def call_count(self) -> int:
        return len(self.batches)

    def generate(
        self, requests: tuple[ThemeTextRequest, ...]
    ) -> tuple[ThemeTextResult, ...]:
        if not isinstance(requests, tuple) or not all(
            isinstance(request, ThemeTextRequest) for request in requests
        ):
            raise InvalidDomainValueError(
                "DeterministicThemeTextGenerator requires ThemeTextRequest tuples"
            )
        self.batches.append(requests)
        return tuple(
            ThemeTextResult(
                period=request.period,
                theme_id=request.theme_id,
                value=f"{self._prefix}{request.reference_label}{self._suffix}",
            )
            for request in requests
        )
