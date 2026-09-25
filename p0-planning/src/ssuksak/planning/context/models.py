"""Immutable provider-neutral Context Packet values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from ..domain.errors import InvalidDomainValueError
from ..domain.year_month import YearMonth
from ..evidence.models import ReusePolicy, SourceSection
from ..retrieval.models import AgeMatchKind

CONTEXT_PACKET_VERSION = "monthly-context-packet-v0.1.0"


@dataclass(frozen=True, slots=True)
class WeekContext:
    week_id: str
    start_date: date
    end_date: date
    display_label: str

    def __post_init__(self) -> None:
        if not isinstance(self.week_id, str) or not self.week_id.strip():
            raise InvalidDomainValueError("WeekContext.week_id must be non-blank")
        if not isinstance(self.start_date, date) or not isinstance(self.end_date, date):
            raise InvalidDomainValueError("WeekContext dates are invalid")
        if self.end_date < self.start_date:
            raise InvalidDomainValueError("WeekContext range is invalid")
        if not isinstance(self.display_label, str) or not self.display_label.strip():
            raise InvalidDomainValueError("WeekContext.display_label must be non-blank")


@dataclass(frozen=True, slots=True)
class GroundingContextItem:
    evidence_ref: str
    text: str
    source_section: SourceSection
    source_label: str
    age_scope: tuple[int, ...]
    age_match: AgeMatchKind
    institution_alias: str
    reuse_policy: ReusePolicy

    def __post_init__(self) -> None:
        for name in ("evidence_ref", "text", "source_label", "institution_alias"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"GroundingContextItem.{name} must be non-blank")
        if not isinstance(self.source_section, SourceSection):
            raise InvalidDomainValueError("GroundingContextItem.source_section is invalid")
        if not isinstance(self.age_match, AgeMatchKind):
            raise InvalidDomainValueError("GroundingContextItem.age_match is invalid")
        if not isinstance(self.reuse_policy, ReusePolicy):
            raise InvalidDomainValueError("GroundingContextItem.reuse_policy is invalid")


@dataclass(frozen=True, slots=True)
class ReferenceActivityContext:
    activity_id: str
    label: str
    rank: int

    def __post_init__(self) -> None:
        if not isinstance(self.activity_id, str) or not self.activity_id.strip():
            raise InvalidDomainValueError("ReferenceActivityContext.activity_id must be non-blank")
        if not isinstance(self.label, str) or not self.label.strip():
            raise InvalidDomainValueError("ReferenceActivityContext.label must be non-blank")
        if type(self.rank) is not int or self.rank < 0:
            raise InvalidDomainValueError("ReferenceActivityContext.rank must be non-negative")


@dataclass(frozen=True, slots=True)
class ContextConstraints:
    source_text_copy_allowed: bool = False
    corpus_direct_output_enabled: bool = False
    official_claim_allowed: bool = False
    deterministic_constraint_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source_text_copy_allowed or self.corpus_direct_output_enabled:
            raise InvalidDomainValueError(
                "CONTEXT_ONLY Institution Evidence cannot be enabled for direct output"
            )
        if not isinstance(self.deterministic_constraint_codes, tuple) or any(
            not isinstance(code, str) or not code.strip()
            for code in self.deterministic_constraint_codes
        ):
            raise InvalidDomainValueError("Context constraint codes are invalid")


@dataclass(frozen=True, slots=True)
class ContextLineage:
    evidence_store_version: str
    evidence_store_sha256: str
    retrieval_version: str
    activity_catalog_id: str = ""
    activity_catalog_version: str = ""

    def __post_init__(self) -> None:
        for name in ("evidence_store_version", "retrieval_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"ContextLineage.{name} must be non-blank")
        if re.fullmatch(r"[0-9a-f]{64}", self.evidence_store_sha256) is None:
            raise InvalidDomainValueError("ContextLineage.evidence_store_sha256 is invalid")
        if bool(self.activity_catalog_id) != bool(self.activity_catalog_version):
            raise InvalidDomainValueError("ContextLineage Activity Catalog identity is incomplete")


@dataclass(frozen=True, slots=True)
class MonthlyContextPacket:
    packet_version: str
    target_month: YearMonth
    ages: tuple[int, ...]
    parent_theme_id: str
    parent_theme_value: str
    weeks: tuple[WeekContext, ...]
    institution_evidence: tuple[GroundingContextItem, ...]
    age_contrast_evidence: tuple[GroundingContextItem, ...]
    week_experience_candidates: tuple[GroundingContextItem, ...]
    reference_activities: tuple[ReferenceActivityContext, ...]
    other_outdoor_evidence: tuple[GroundingContextItem, ...]
    constraints: ContextConstraints
    lineage: ContextLineage
    trimmed_blocks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.packet_version != CONTEXT_PACKET_VERSION:
            raise InvalidDomainValueError("Context Packet version is invalid")
        if not isinstance(self.target_month, YearMonth):
            raise InvalidDomainValueError("Context Packet target_month must be YearMonth")
        if (
            not self.ages
            or tuple(sorted(set(self.ages))) != self.ages
            or any(type(age) is not int or age not in {3, 4, 5} for age in self.ages)
        ):
            raise InvalidDomainValueError("Context Packet ages are invalid")
        if not self.weeks:
            raise InvalidDomainValueError("Context Packet requires week structure")
        all_evidence = (
            self.age_contrast_evidence
            + self.institution_evidence
            + self.week_experience_candidates
            + self.other_outdoor_evidence
        )
        ids = tuple(item.evidence_ref for item in all_evidence)
        if len(set(ids)) != len(ids):
            raise InvalidDomainValueError("Context evidence records cannot appear in multiple blocks")
        if any(item.reuse_policy is not ReusePolicy.CONTEXT_ONLY for item in all_evidence):
            raise InvalidDomainValueError(
                "Institution Context currently permits CONTEXT_ONLY evidence only"
            )
