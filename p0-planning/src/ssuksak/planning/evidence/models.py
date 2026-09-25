"""Immutable Institution Evidence records used for grounding, not plan values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from ..domain.errors import InvalidDomainValueError
from ..domain.provenance import EvidenceSourceType

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceSection(str, Enum):
    OUTDOOR_PLAY = "outdoor_play"
    INDOOR_PLAY = "indoor_play"
    INDOOR_ALTERNATIVE = "indoor_alternative"
    WEEK_EXPERIENCE = "week_experience"
    SAFETY_EDUCATION = "safety_education"
    DAILY_ROUTINE = "daily_routine"
    EVENT = "event"
    THEME = "theme"
    UNKNOWN = "unknown"


class Setting(str, Enum):
    OUTDOOR = "OUTDOOR"
    INDOOR = "INDOOR"
    INDOOR_ALTERNATIVE = "INDOOR_ALTERNATIVE"
    UNKNOWN = "UNKNOWN"


class AgeEvidenceType(str, Enum):
    SINGLE_AGE_PAGE = "SINGLE_AGE_PAGE"
    MIXED_AGE_PAGE = "MIXED_AGE_PAGE"
    AGE_UNKNOWN = "AGE_UNKNOWN"


class MachineReadability(str, Enum):
    TEXT_LAYER = "TEXT_LAYER"
    IMAGE_ONLY = "IMAGE_ONLY"


class ReusePolicy(str, Enum):
    CONTEXT_ONLY = "CONTEXT_ONLY"
    PRODUCT_OUTPUT_ALLOWED = "PRODUCT_OUTPUT_ALLOWED"


class ExtractionQuality(str, Enum):
    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class CellCoordinates:
    row_top: float
    row_bottom: float
    column: int
    item_index: int

    def __post_init__(self) -> None:
        if type(self.row_top) not in {int, float} or type(self.row_bottom) not in {int, float}:
            raise InvalidDomainValueError("CellCoordinates rows must be numeric")
        if self.row_top < 0 or self.row_bottom <= self.row_top:
            raise InvalidDomainValueError("CellCoordinates row range is invalid")
        if type(self.column) is not int or self.column < 0:
            raise InvalidDomainValueError("CellCoordinates.column must be non-negative")
        if type(self.item_index) is not int or self.item_index < 1:
            raise InvalidDomainValueError("CellCoordinates.item_index must be positive")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    record_id: str
    source_type: EvidenceSourceType
    source_path: str
    source_sha256: str
    page: int
    age_scope: tuple[int, ...]
    age_evidence_type: AgeEvidenceType
    source_section: SourceSection
    source_label: str
    setting: Setting
    machine_readability: MachineReadability
    reuse_policy: ReusePolicy
    extraction_quality: ExtractionQuality
    extraction_method: str
    institution_id: str | None = None
    institution_type: str | None = None
    year: int | None = None
    month: int | None = None
    monthly_theme: str | None = None
    week_position: int | None = None
    week_label: str | None = None
    experience_text: str | None = None
    activity_text: str | None = None
    template_family: bool = False
    source_cell: CellCoordinates | None = None

    def __post_init__(self) -> None:
        for name in ("record_id", "source_path", "source_label", "extraction_method"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"EvidenceRecord.{name} must be non-blank")
        if self.source_type is not EvidenceSourceType.INSTITUTION_SAMPLE:
            raise InvalidDomainValueError(
                "Institution Evidence source_type must be INSTITUTION_SAMPLE"
            )
        if not isinstance(self.source_sha256, str) or _SHA256.fullmatch(self.source_sha256) is None:
            raise InvalidDomainValueError("EvidenceRecord.source_sha256 must be lowercase SHA-256")
        if type(self.page) is not int or self.page < 1:
            raise InvalidDomainValueError("EvidenceRecord.page must be positive")
        if not isinstance(self.age_scope, tuple):
            raise InvalidDomainValueError("EvidenceRecord.age_scope must be a tuple")
        if any(type(age) is not int or age not in {3, 4, 5} for age in self.age_scope):
            raise InvalidDomainValueError("EvidenceRecord ages must be P0 ages 3 through 5")
        if tuple(sorted(set(self.age_scope))) != self.age_scope:
            raise InvalidDomainValueError("EvidenceRecord.age_scope must be sorted and unique")
        for name, expected in (
            ("age_evidence_type", AgeEvidenceType),
            ("source_section", SourceSection),
            ("setting", Setting),
            ("machine_readability", MachineReadability),
            ("reuse_policy", ReusePolicy),
            ("extraction_quality", ExtractionQuality),
        ):
            if not isinstance(getattr(self, name), expected):
                raise InvalidDomainValueError(f"EvidenceRecord.{name} is invalid")
        if self.year is not None and (type(self.year) is not int or not 1 <= self.year <= 9999):
            raise InvalidDomainValueError("EvidenceRecord.year is invalid")
        if self.month is not None and (type(self.month) is not int or not 1 <= self.month <= 12):
            raise InvalidDomainValueError("EvidenceRecord.month is invalid")
        if self.week_position is not None and (
            type(self.week_position) is not int or not 1 <= self.week_position <= 6
        ):
            raise InvalidDomainValueError("EvidenceRecord.week_position is invalid")
        if type(self.template_family) is not bool:
            raise InvalidDomainValueError("EvidenceRecord.template_family must be boolean")
        for name in (
            "institution_id", "institution_type", "monthly_theme", "week_label",
            "experience_text", "activity_text",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise InvalidDomainValueError(f"EvidenceRecord.{name} must be non-blank when set")
        if self.source_cell is not None and not isinstance(self.source_cell, CellCoordinates):
            raise InvalidDomainValueError("EvidenceRecord.source_cell is invalid")

    @property
    def single_age(self) -> int | None:
        if self.age_evidence_type is AgeEvidenceType.SINGLE_AGE_PAGE and len(self.age_scope) == 1:
            return self.age_scope[0]
        return None

    @property
    def general_grounding_eligible(self) -> bool:
        return (
            self.machine_readability is MachineReadability.TEXT_LAYER
            and self.extraction_quality is ExtractionQuality.VALID
        )

    @property
    def outdoor_activity_eligible(self) -> bool:
        return (
            self.general_grounding_eligible
            and self.source_section is SourceSection.OUTDOOR_PLAY
            and self.setting is Setting.OUTDOOR
        )

    @property
    def text(self) -> str | None:
        return self.activity_text or self.experience_text
