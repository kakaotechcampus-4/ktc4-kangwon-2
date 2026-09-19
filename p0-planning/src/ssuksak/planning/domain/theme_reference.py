"""Pure domain model for the versioned Yearly Theme Reference catalog."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError


def _require_non_blank(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{name} must be a non-blank string")


def _require_non_negative_int(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise InvalidDomainValueError(f"{name} must be a non-negative integer")


def _require_month(value: object, name: str) -> None:
    if type(value) is not int or not 1 <= value <= 12:
        raise InvalidDomainValueError(f"{name} must be an integer from 1 through 12")


class ActivationStatus(str, Enum):
    """Human-review state used to decide whether a catalog may be selected."""

    HUMAN_APPROVED = "HUMAN_APPROVED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class ThemeEvidence:
    """One observation of a theme label in an upstream planning sample."""

    origin_id: str
    page: int
    age_scope: tuple[int, ...]
    observed_month: int
    observed_label: str

    def __post_init__(self) -> None:
        _require_non_blank(self.origin_id, "ThemeEvidence.origin_id")
        _require_non_negative_int(self.page, "ThemeEvidence.page")
        if not isinstance(self.age_scope, tuple):
            raise InvalidDomainValueError("ThemeEvidence.age_scope must be a tuple")
        if any(type(age) is not int or not 0 <= age <= 7 for age in self.age_scope):
            raise InvalidDomainValueError(
                "ThemeEvidence.age_scope values must be integers from 0 through 7"
            )
        _require_month(self.observed_month, "ThemeEvidence.observed_month")
        if not isinstance(self.observed_label, str):
            raise InvalidDomainValueError(
                "ThemeEvidence.observed_label must be a string"
            )


@dataclass(frozen=True, slots=True)
class CurriculumLink:
    """Domain-level educational alignment, not a mandated monthly theme."""

    source_id: str
    domain: str
    source_page: int
    relation: str

    def __post_init__(self) -> None:
        _require_non_blank(self.source_id, "CurriculumLink.source_id")
        _require_non_blank(self.domain, "CurriculumLink.domain")
        _require_non_negative_int(self.source_page, "CurriculumLink.source_page")
        _require_non_blank(self.relation, "CurriculumLink.relation")


@dataclass(frozen=True, slots=True)
class ThemeCandidate:
    """A versioned candidate that deterministic selection rules may choose."""

    theme_id: str
    label: str
    applicable_months: tuple[int, ...]
    supported_ages: tuple[int, ...]
    allow_mixed_age: bool
    mixed_age_requires_all_supported: bool
    source_version: str
    origin_id: str | None = None
    curriculum_links: tuple[CurriculumLink, ...] = ()
    evidence: tuple[ThemeEvidence, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank(self.theme_id, "ThemeCandidate.theme_id")
        _require_non_blank(self.label, "ThemeCandidate.label")
        _require_non_blank(self.source_version, "ThemeCandidate.source_version")
        if self.origin_id is not None:
            _require_non_blank(self.origin_id, "ThemeCandidate.origin_id")

        if not isinstance(self.applicable_months, tuple) or not self.applicable_months:
            raise InvalidDomainValueError(
                "ThemeCandidate.applicable_months must be a non-empty tuple"
            )
        for month in self.applicable_months:
            _require_month(month, "ThemeCandidate.applicable_months item")
        if len(set(self.applicable_months)) != len(self.applicable_months):
            raise InvalidDomainValueError(
                "ThemeCandidate.applicable_months must not contain duplicates"
            )

        if not isinstance(self.supported_ages, tuple) or not self.supported_ages:
            raise InvalidDomainValueError(
                "ThemeCandidate.supported_ages must be a non-empty tuple"
            )
        if any(type(age) is not int or not 0 <= age <= 7 for age in self.supported_ages):
            raise InvalidDomainValueError(
                "ThemeCandidate.supported_ages values must be integers from 0 through 7"
            )
        if len(set(self.supported_ages)) != len(self.supported_ages):
            raise InvalidDomainValueError(
                "ThemeCandidate.supported_ages must not contain duplicates"
            )
        if type(self.allow_mixed_age) is not bool:
            raise InvalidDomainValueError(
                "ThemeCandidate.allow_mixed_age must be a boolean"
            )
        if type(self.mixed_age_requires_all_supported) is not bool:
            raise InvalidDomainValueError(
                "ThemeCandidate.mixed_age_requires_all_supported must be a boolean"
            )
        if not isinstance(self.curriculum_links, tuple):
            raise InvalidDomainValueError(
                "ThemeCandidate.curriculum_links must be a tuple"
            )
        if not isinstance(self.evidence, tuple):
            raise InvalidDomainValueError("ThemeCandidate.evidence must be a tuple")

    def supports_month(self, calendar_month: int) -> bool:
        return calendar_month in self.applicable_months

    def supports_age_set(self, ages: frozenset[int]) -> bool:
        if not ages or not ages.issubset(self.supported_ages):
            return False
        if len(ages) >= 2 and not self.allow_mixed_age:
            return False
        if len(ages) >= 2 and self.mixed_age_requires_all_supported:
            return ages.issubset(self.supported_ages)
        return True

    def evidence_strength_for_month(self, calendar_month: int) -> int:
        return sum(
            1 for item in self.evidence if item.observed_month == calendar_month
        )


@dataclass(frozen=True, slots=True)
class ThemeCatalog:
    """An exact, versioned set of Yearly Theme candidates."""

    catalog_id: str
    catalog_version: str
    activation_status: ActivationStatus
    themes: tuple[ThemeCandidate, ...]
    normative_status: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.catalog_id, "ThemeCatalog.catalog_id")
        _require_non_blank(self.catalog_version, "ThemeCatalog.catalog_version")
        if not isinstance(self.activation_status, ActivationStatus):
            raise InvalidDomainValueError(
                "ThemeCatalog.activation_status must be an ActivationStatus"
            )
        if not isinstance(self.themes, tuple) or not self.themes:
            raise InvalidDomainValueError("ThemeCatalog.themes must be a non-empty tuple")
        if self.normative_status is not None and not isinstance(
            self.normative_status, str
        ):
            raise InvalidDomainValueError(
                "ThemeCatalog.normative_status must be a string or None"
            )

        ids = [theme.theme_id for theme in self.themes]
        if len(set(ids)) != len(ids):
            raise InvalidDomainValueError("ThemeCatalog contains duplicate theme_id values")

    @property
    def is_active(self) -> bool:
        return self.activation_status is ActivationStatus.HUMAN_APPROVED

    def get(self, theme_id: str) -> ThemeCandidate | None:
        return next((theme for theme in self.themes if theme.theme_id == theme_id), None)

    def eligible_candidates(
        self, calendar_month: int, ages: frozenset[int]
    ) -> tuple[ThemeCandidate, ...]:
        return tuple(
            theme
            for theme in self.themes
            if theme.supports_month(calendar_month) and theme.supports_age_set(ages)
        )
