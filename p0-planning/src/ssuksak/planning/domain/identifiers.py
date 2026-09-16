"""Opaque identifiers used at the Planning Core boundary."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidIdentifierError


def _validate_identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidIdentifierError(f"{name} must be a non-blank string")


@dataclass(frozen=True, slots=True)
class PlanId:
    """Stable, storage-agnostic identity of a plan."""

    value: str

    def __post_init__(self) -> None:
        _validate_identifier(type(self).__name__, self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ItemId:
    """Stable identity of an editable item inside a plan."""

    value: str

    def __post_init__(self) -> None:
        _validate_identifier(type(self).__name__, self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ActorId:
    """Opaque identity of a human actor; never a display name."""

    value: str

    def __post_init__(self) -> None:
        _validate_identifier(type(self).__name__, self.value)

    def __str__(self) -> str:
        return self.value
