"""Configurable test adapter for the OptionalContextProvider port."""

from __future__ import annotations

from collections.abc import Mapping

from ssuksak.planning.application.ports import (
    OptionalContextResult,
    OptionalContextStatus,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError


class StubOptionalContextProvider:
    def __init__(
        self,
        results: Mapping[str, OptionalContextResult] | None = None,
    ) -> None:
        self._results = dict(results or {})
        for name, result in self._results.items():
            if not isinstance(result, OptionalContextResult) or name != result.name:
                raise InvalidDomainValueError(
                    "Stub context keys must match OptionalContextResult.name"
                )

    def fetch(self, name: str) -> OptionalContextResult:
        if not isinstance(name, str) or not name.strip():
            raise InvalidDomainValueError("Optional context name must be non-blank")
        return self._results.get(
            name,
            OptionalContextResult(
                name=name,
                status=OptionalContextStatus.UNAVAILABLE,
                detail="No stub result configured",
            ),
        )
