"""Versioned Activity Reference domain used by deterministic Monthly rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError
from .theme_reference import ActivationStatus

OUTDOOR_PLAY_SLOT = "outdoor_play"
SUPPORTED_PLACEMENT_SLOTS = frozenset({OUTDOOR_PLAY_SLOT})
FORBIDDEN_PLACEMENT_SLOTS = frozenset({"safety_education"})
THEME_RELATION_OBSERVED_TOGETHER = "OBSERVED_TOGETHER"
CURRICULUM_RELATION_EDUCATIONAL_ALIGNMENT = "EDUCATIONAL_ALIGNMENT"
CURRICULUM_DOMAINS = frozenset(
    {"신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"}
)


class ActivityDisplayQuality(str, Enum):
    GOOD_STANDALONE = "GOOD_STANDALONE"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"
    TOO_SHORT = "TOO_SHORT"
    POSSIBLE_FRAGMENT = "POSSIBLE_FRAGMENT"
    SECTION_LABEL_LIKE = "SECTION_LABEL_LIKE"
    INSTITUTION_SPECIFIC = "INSTITUTION_SPECIFIC"
    TOO_GENERIC = "TOO_GENERIC"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class DisplayQualityReviewStatus(str, Enum):
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    AUTO_CANDIDATE = "AUTO_CANDIDATE"
    UNREVIEWED = "UNREVIEWED"


class ActivitySetting(str, Enum):
    OUTDOOR = "OUTDOOR"
    INDOOR = "INDOOR"
    EITHER = "EITHER"


@dataclass(frozen=True, slots=True)
class ActivityEvidence:
    origin_id: str
    page: int
    age_scope: tuple[int, ...]
    observed_month: int
    observed_label: str
    observed_section: str
    observed_source_label: str
    matched_via: str | None = None
    match_note: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "origin_id",
            "observed_label",
            "observed_section",
            "observed_source_label",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"ActivityEvidence.{name} must be non-blank"
                )
        if type(self.page) is not int or self.page < 1:
            raise InvalidDomainValueError(
                "ActivityEvidence.page must be a positive integer"
            )
        if not isinstance(self.age_scope, tuple) or any(
            type(age) is not int or age not in {3, 4, 5}
            for age in self.age_scope
        ):
            raise InvalidDomainValueError(
                "ActivityEvidence.age_scope supports P0 ages 3, 4, and 5 only"
            )
        if type(self.observed_month) is not int or not 1 <= self.observed_month <= 12:
            raise InvalidDomainValueError(
                "ActivityEvidence.observed_month must be 1 through 12"
            )
        if self.matched_via is not None and self.matched_via not in {
            "DIRECT_EXPRESSION",
            "RELATED_EXPRESSION",
        }:
            raise InvalidDomainValueError("ActivityEvidence.matched_via is invalid")
        if self.match_note is not None and not isinstance(self.match_note, str):
            raise InvalidDomainValueError(
                "ActivityEvidence.match_note must be a string when set"
            )


@dataclass(frozen=True, slots=True)
class ActivityThemeLink:
    theme_id: str
    relation: str
    theme_catalog_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.theme_id, str) or not self.theme_id.strip():
            raise InvalidDomainValueError(
                "ActivityThemeLink.theme_id must be non-blank"
            )
        if self.relation != THEME_RELATION_OBSERVED_TOGETHER:
            raise InvalidDomainValueError(
                "ActivityThemeLink.relation must be OBSERVED_TOGETHER"
            )
        if (
            not isinstance(self.theme_catalog_version, str)
            or not self.theme_catalog_version.strip()
        ):
            raise InvalidDomainValueError(
                "ActivityThemeLink.theme_catalog_version must be non-blank"
            )


@dataclass(frozen=True, slots=True)
class ActivityCurriculumLink:
    source_id: str
    domain: str
    source_page: int
    relation: str = CURRICULUM_RELATION_EDUCATIONAL_ALIGNMENT

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise InvalidDomainValueError(
                "ActivityCurriculumLink.source_id must be non-blank"
            )
        if self.domain not in CURRICULUM_DOMAINS:
            raise InvalidDomainValueError(
                "ActivityCurriculumLink.domain must be a curriculum domain"
            )
        if type(self.source_page) is not int or self.source_page < 0:
            raise InvalidDomainValueError(
                "ActivityCurriculumLink.source_page must be non-negative"
            )
        if self.relation != CURRICULUM_RELATION_EDUCATIONAL_ALIGNMENT:
            raise InvalidDomainValueError(
                "ActivityCurriculumLink.relation must be EDUCATIONAL_ALIGNMENT"
            )


@dataclass(frozen=True, slots=True)
class ActivityCandidate:
    activity_id: str
    label: str
    supported_ages: tuple[int, ...]
    allow_mixed_age: bool
    mixed_age_requires_all_supported: bool
    applicable_months: tuple[int, ...]
    placement_slots: tuple[str, ...]
    setting: ActivitySetting
    source_version: str
    origin_id: str | None = None
    label_derivation_type: str | None = None
    label_derivation: str | None = None
    aliases: tuple[str, ...] = ()
    theme_links: tuple[ActivityThemeLink, ...] = ()
    curriculum_links: tuple[ActivityCurriculumLink, ...] = ()
    evidence: tuple[ActivityEvidence, ...] = ()
    display_quality: ActivityDisplayQuality | None = None
    display_quality_review_status: DisplayQualityReviewStatus | None = None

    def __post_init__(self) -> None:
        for name in ("activity_id", "label", "source_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"ActivityCandidate.{name} must be non-blank"
                )
        if self.origin_id is not None and (
            not isinstance(self.origin_id, str) or not self.origin_id.strip()
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.origin_id must be non-blank when set"
            )
        if not isinstance(self.supported_ages, tuple) or not self.supported_ages:
            raise InvalidDomainValueError(
                "ActivityCandidate.supported_ages must be a non-empty tuple"
            )
        if any(
            type(age) is not int or age not in {3, 4, 5}
            for age in self.supported_ages
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.supported_ages supports P0 ages 3, 4, and 5 only"
            )
        if len(set(self.supported_ages)) != len(self.supported_ages):
            raise InvalidDomainValueError(
                "ActivityCandidate.supported_ages must not contain duplicates"
            )
        if type(self.allow_mixed_age) is not bool:
            raise InvalidDomainValueError(
                "ActivityCandidate.allow_mixed_age must be a boolean"
            )
        if type(self.mixed_age_requires_all_supported) is not bool:
            raise InvalidDomainValueError(
                "ActivityCandidate.mixed_age_requires_all_supported must be boolean"
            )
        if not self.mixed_age_requires_all_supported:
            raise InvalidDomainValueError(
                "ActivityCandidate.mixed_age_requires_all_supported must be true "
                "for the current P0 policy"
            )
        if not isinstance(self.applicable_months, tuple) or not self.applicable_months:
            raise InvalidDomainValueError(
                "ActivityCandidate.applicable_months must be a non-empty tuple"
            )
        if any(
            type(month) is not int or not 1 <= month <= 12
            for month in self.applicable_months
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.applicable_months must contain months 1 through 12"
            )
        if len(set(self.applicable_months)) != len(self.applicable_months):
            raise InvalidDomainValueError(
                "ActivityCandidate.applicable_months must not contain duplicates"
            )
        if not isinstance(self.placement_slots, tuple) or not self.placement_slots:
            raise InvalidDomainValueError(
                "ActivityCandidate.placement_slots must be a non-empty tuple"
            )
        if any(slot in FORBIDDEN_PLACEMENT_SLOTS for slot in self.placement_slots):
            raise InvalidDomainValueError(
                "ActivityCandidate cannot target a safety education slot"
            )
        if any(slot not in SUPPORTED_PLACEMENT_SLOTS for slot in self.placement_slots):
            raise InvalidDomainValueError(
                "ActivityCandidate placement slot is unsupported"
            )
        if len(set(self.placement_slots)) != len(self.placement_slots):
            raise InvalidDomainValueError(
                "ActivityCandidate.placement_slots must not contain duplicates"
            )
        if not isinstance(self.setting, ActivitySetting):
            raise InvalidDomainValueError("ActivityCandidate.setting is invalid")
        if self.label_derivation_type is not None and self.label_derivation_type not in {
            "DIRECT_TRANSCRIPTION",
            "NORMALIZED",
        }:
            raise InvalidDomainValueError(
                "ActivityCandidate.label_derivation_type is invalid"
            )
        if self.label_derivation is not None and not isinstance(
            self.label_derivation, str
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.label_derivation must be a string when set"
            )
        if not isinstance(self.aliases, tuple) or any(
            not isinstance(alias, str) or not alias.strip() for alias in self.aliases
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.aliases must contain non-blank strings"
            )
        if len(set(self.aliases)) != len(self.aliases):
            raise InvalidDomainValueError(
                "ActivityCandidate.aliases must not contain duplicates"
            )
        if not isinstance(self.theme_links, tuple) or not all(
            isinstance(link, ActivityThemeLink) for link in self.theme_links
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.theme_links are invalid"
            )
        if not isinstance(self.curriculum_links, tuple) or not all(
            isinstance(link, ActivityCurriculumLink)
            for link in self.curriculum_links
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.curriculum_links are invalid"
            )
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, ActivityEvidence) for item in self.evidence
        ):
            raise InvalidDomainValueError("ActivityCandidate.evidence is invalid")
        if self.display_quality is not None and not isinstance(
            self.display_quality, ActivityDisplayQuality
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.display_quality is invalid"
            )
        if self.display_quality_review_status is not None and not isinstance(
            self.display_quality_review_status, DisplayQualityReviewStatus
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.display_quality_review_status is invalid"
            )

        if self.evidence:
            observed_ages = {
                age for observation in self.evidence for age in observation.age_scope
            }
            if not set(self.supported_ages).issubset(observed_ages):
                raise InvalidDomainValueError(
                    "ActivityCandidate.supported_ages exceeds its Evidence"
                )
            observed_months = {
                observation.observed_month for observation in self.evidence
            }
            if not set(self.applicable_months).issubset(observed_months):
                raise InvalidDomainValueError(
                    "ActivityCandidate.applicable_months exceeds its Evidence"
                )

    def supports_month(self, calendar_month: int) -> bool:
        return calendar_month in self.applicable_months

    def supports_age_set(self, ages: frozenset[int]) -> bool:
        if not ages or not ages.issubset(self.supported_ages):
            return False
        if len(ages) >= 2 and not self.allow_mixed_age:
            return False
        return True

    def supports_slot(self, section_key: str) -> bool:
        return section_key in self.placement_slots

    def supports_setting(self, section_key: str) -> bool:
        if section_key == OUTDOOR_PLAY_SLOT:
            return self.setting in {ActivitySetting.OUTDOOR, ActivitySetting.EITHER}
        return True

    def links_theme(self, theme_id: str) -> bool:
        return any(link.theme_id == theme_id for link in self.theme_links)

    def evidence_strength_for_month(self, calendar_month: int) -> int:
        return sum(
            1
            for observation in self.evidence
            if observation.observed_month == calendar_month
        )

    @property
    def has_confirmed_display_issue(self) -> bool:
        return (
            self.display_quality_review_status
            is DisplayQualityReviewStatus.HUMAN_CONFIRMED
            and self.display_quality is not None
            and self.display_quality is not ActivityDisplayQuality.GOOD_STANDALONE
        )


@dataclass(frozen=True, slots=True)
class ActivityCatalog:
    catalog_id: str
    catalog_version: str
    activation_status: ActivationStatus
    activities: tuple[ActivityCandidate, ...]
    normative_status: str | None = None
    month_coverage: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        for name in ("catalog_id", "catalog_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"ActivityCatalog.{name} must be non-blank"
                )
        if not isinstance(self.activation_status, ActivationStatus):
            raise InvalidDomainValueError(
                "ActivityCatalog.activation_status is invalid"
            )
        if not isinstance(self.activities, tuple) or not self.activities:
            raise InvalidDomainValueError(
                "ActivityCatalog.activities must be a non-empty tuple"
            )
        if not all(isinstance(item, ActivityCandidate) for item in self.activities):
            raise InvalidDomainValueError(
                "ActivityCatalog.activities must contain ActivityCandidate values"
            )
        ids = tuple(item.activity_id for item in self.activities)
        if len(set(ids)) != len(ids):
            raise InvalidDomainValueError(
                "ActivityCatalog contains duplicate activity_id values"
            )
        if any(
            item.source_version != self.catalog_version for item in self.activities
        ):
            raise InvalidDomainValueError(
                "ActivityCandidate.source_version must match its Catalog version"
            )
        if not isinstance(self.month_coverage, tuple) or any(
            type(month) is not int or not 1 <= month <= 12
            for month in self.month_coverage
        ):
            raise InvalidDomainValueError(
                "ActivityCatalog.month_coverage is invalid"
            )
        if self.month_coverage:
            actual = {
                month for item in self.activities for month in item.applicable_months
            }
            if set(self.month_coverage) != actual:
                raise InvalidDomainValueError(
                    "ActivityCatalog.month_coverage must match candidate coverage"
                )

    @property
    def is_active(self) -> bool:
        return self.activation_status is ActivationStatus.HUMAN_APPROVED

    def get(self, activity_id: str) -> ActivityCandidate | None:
        return next(
            (item for item in self.activities if item.activity_id == activity_id),
            None,
        )

    def eligible_candidates(
        self,
        *,
        section_key: str,
        calendar_month: int,
        ages: frozenset[int],
    ) -> tuple[ActivityCandidate, ...]:
        if not self.is_active or section_key in FORBIDDEN_PLACEMENT_SLOTS:
            return ()
        return tuple(
            sorted(
                (
                    item
                    for item in self.activities
                    if item.supports_slot(section_key)
                    and item.supports_setting(section_key)
                    and item.supports_month(calendar_month)
                    and item.supports_age_set(ages)
                ),
                key=lambda item: item.activity_id,
            )
        )
