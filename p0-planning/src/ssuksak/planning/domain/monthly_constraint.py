"""Monthly-specific assessment and Cell-state values using PR0 Constraint."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .constraint import Constraint
from .errors import InvalidDomainValueError

SAFETY_EDUCATION_CONSTRAINT = Constraint(
    code="STATUTORY_SAFETY_EDUCATION",
    description="Safety education placement requires an institution plan or teacher input",
)


class ConstraintVerification(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED_SOURCE_REQUIRED = "NOT_VERIFIED_SOURCE_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CellState(str, Enum):
    FILLED = "FILLED"
    EMPTY_VALID = "EMPTY_VALID"
    EMPTY_UNRESOLVED = "EMPTY_UNRESOLVED"

    @property
    def is_empty(self) -> bool:
        return self is not CellState.FILLED


@dataclass(frozen=True, slots=True)
class ConstraintAssessment:
    constraint: Constraint
    verification: ConstraintVerification
    rule_version: str
    required_source_kinds: tuple[str, ...] = ()
    affected_section_keys: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.constraint, Constraint):
            raise InvalidDomainValueError(
                "ConstraintAssessment.constraint must be Constraint"
            )
        if not isinstance(self.verification, ConstraintVerification):
            raise InvalidDomainValueError(
                "ConstraintAssessment.verification is invalid"
            )
        if not isinstance(self.rule_version, str) or not self.rule_version.strip():
            raise InvalidDomainValueError(
                "ConstraintAssessment.rule_version must be non-blank"
            )
        for name in ("required_source_kinds", "affected_section_keys"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise InvalidDomainValueError(
                    f"ConstraintAssessment.{name} must contain non-blank strings"
                )
            if len(set(values)) != len(values):
                raise InvalidDomainValueError(
                    f"ConstraintAssessment.{name} must not contain duplicates"
                )
        if (
            self.verification
            is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
            and not self.required_source_kinds
        ):
            raise InvalidDomainValueError(
                "An unresolved ConstraintAssessment requires source kinds"
            )
        if not isinstance(self.detail, str):
            raise InvalidDomainValueError(
                "ConstraintAssessment.detail must be a string"
            )

    @property
    def is_unresolved(self) -> bool:
        return (
            self.verification
            is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
        )
