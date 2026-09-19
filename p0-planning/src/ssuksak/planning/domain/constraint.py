"""A minimal, rule-neutral representation of a planning constraint.

This module describes a requirement only. It does not evaluate legal rules,
place content in a plan, or claim that a requirement has been satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidDomainValueError


@dataclass(frozen=True, slots=True)
class Constraint:
    """A named requirement that a later rule or validator may interpret."""

    code: str
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise InvalidDomainValueError("Constraint.code must be a non-blank string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise InvalidDomainValueError(
                "Constraint.description must be a non-blank string"
            )
