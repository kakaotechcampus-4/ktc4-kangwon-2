"""Immutable provider-neutral Context Packet values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from ..domain.errors import InvalidDomainValueError
from ..domain.safety_placement import SafetyKind
from ..domain.year_month import YearMonth
from ..evidence.classification import SemanticClass
from ..evidence.models import ReusePolicy, SourceSection
from ..evidence.safety_classification import SafetyReferenceKind
from ..retrieval.models import AgeMatchKind

CONTEXT_PACKET_VERSION = "monthly-context-packet-v0.2.0"


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
    grounding_class: SemanticClass | None = None

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
        if self.grounding_class is not None and (
            not isinstance(self.grounding_class, SemanticClass)
            or self.grounding_class is SemanticClass.EXCLUDED
        ):
            raise InvalidDomainValueError("GroundingContextItem.grounding_class is invalid")


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
    evidence_classification_version: str = ""

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
class OfficialSafetyContent:
    """One official content item of a placed legal category, citable as grounding."""

    grounding_ref: str
    category_id: str
    official_label: str
    text: str

    def __post_init__(self) -> None:
        for name in ("grounding_ref", "category_id", "official_label", "text"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"OfficialSafetyContent.{name} must be non-blank")


@dataclass(frozen=True, slots=True)
class SafetySlotContext:
    week_id: str
    kind: SafetyKind
    category_id: str | None = None
    # STATUTORY: the one official content item this week expresses.
    focus_ref: str | None = None
    # SUPPLEMENTAL: the one Reference this week expresses, plus at most one same-topic support.
    primary_ref: str | None = None
    support_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        statutory = self.kind is SafetyKind.STATUTORY
        if (self.focus_ref is not None and not statutory) or (
            (self.primary_ref is not None or self.support_refs) and statutory
        ) or (self.support_refs and self.primary_ref is None) or len(self.support_refs) > 1:
            raise InvalidDomainValueError("SafetySlotContext focus/primary fields do not match its kind")
        if not isinstance(self.week_id, str) or not self.week_id.strip():
            raise InvalidDomainValueError("SafetySlotContext.week_id must be non-blank")
        if not isinstance(self.kind, SafetyKind):
            raise InvalidDomainValueError("SafetySlotContext.kind is invalid")
        if (self.kind is SafetyKind.STATUTORY) != isinstance(self.category_id, str) or (
            self.category_id is not None and not self.category_id.strip()
        ):
            raise InvalidDomainValueError(
                "A STATUTORY slot needs a category_id and a SUPPLEMENTAL slot has none"
            )


@dataclass(frozen=True, slots=True)
class SafetyReferenceContext:
    """The approved classification of one Sample safety evidence item."""

    evidence_ref: str
    kind: SafetyReferenceKind
    legal_category_id: str | None = None
    supplemental_label: str | None = None
    topic_group: str | None = None
    # True for a MONTH_INDEPENDENT Reference found in another month (fallback tier).
    cross_month: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_ref, str) or not self.evidence_ref.strip():
            raise InvalidDomainValueError("SafetyReferenceContext.evidence_ref must be non-blank")
        statutory = self.kind is SafetyReferenceKind.STATUTORY_REFERENCE
        supplemental = self.kind is SafetyReferenceKind.SUPPLEMENTAL_REFERENCE
        if not (statutory or supplemental):
            raise InvalidDomainValueError("Only approved safety References enter the Context")
        if statutory != bool(self.legal_category_id) or supplemental != bool(self.supplemental_label):
            raise InvalidDomainValueError("SafetyReferenceContext fields do not match its kind")


@dataclass(frozen=True, slots=True)
class SafetyContext:
    """Rule-fixed safety slots, their official content, and Sample safety evidence."""

    policy_version: str
    legal_rule_version: str
    retrieval_version: str
    slots: tuple[SafetySlotContext, ...]
    official_content: tuple[OfficialSafetyContent, ...]
    evidence: tuple[GroundingContextItem, ...] = ()
    references: tuple[SafetyReferenceContext, ...] = ()

    def __post_init__(self) -> None:
        for name in ("policy_version", "legal_rule_version", "retrieval_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"SafetyContext.{name} must be non-blank")
        weeks = tuple(slot.week_id for slot in self.slots)
        if not weeks or len(set(weeks)) != len(weeks):
            raise InvalidDomainValueError("SafetyContext needs one slot per week")
        refs = tuple(item.grounding_ref for item in self.official_content)
        if len(set(refs)) != len(refs):
            raise InvalidDomainValueError("SafetyContext official refs must be unique")
        statutory = {slot.category_id for slot in self.slots if slot.kind is SafetyKind.STATUTORY}
        if {item.category_id for item in self.official_content} != statutory:
            raise InvalidDomainValueError(
                "SafetyContext official content must cover exactly the placed legal categories"
            )
        if any(
            item.source_section is not SourceSection.SAFETY_EDUCATION or item.grounding_class is not None
            for item in self.evidence
        ):
            raise InvalidDomainValueError("Safety evidence must be unclassified safety_education evidence")
        if [item.evidence_ref for item in self.evidence] != [ref.evidence_ref for ref in self.references]:
            raise InvalidDomainValueError("Every safety evidence item needs exactly its approved Reference")
        if {ref.legal_category_id for ref in self.references if ref.legal_category_id} - statutory:
            raise InvalidDomainValueError("Statutory References must belong to a placed legal category")
        official = self.official_by_ref
        references = self.reference_by_ref
        primaries = [slot.primary_ref for slot in self.slots if slot.primary_ref is not None]
        if len(set(primaries)) != len(primaries):
            raise InvalidDomainValueError("Each supplemental week needs its own primary Reference")
        for slot in self.slots:
            if slot.focus_ref is not None and (
                slot.focus_ref not in official or official[slot.focus_ref].category_id != slot.category_id
            ):
                raise InvalidDomainValueError("A statutory focus must be official content of its category")
            for ref in (slot.primary_ref, *slot.support_refs):
                if ref is not None and (
                    ref not in references or references[ref].kind is not SafetyReferenceKind.SUPPLEMENTAL_REFERENCE
                ):
                    raise InvalidDomainValueError("Supplemental primary and support refs must be supplemental References")

    def slot(self, week_id: str) -> SafetySlotContext | None:
        return next((slot for slot in self.slots if slot.week_id == week_id), None)

    @property
    def official_by_ref(self) -> dict[str, OfficialSafetyContent]:
        return {item.grounding_ref: item for item in self.official_content}

    @property
    def reference_by_ref(self) -> dict[str, SafetyReferenceContext]:
        return {ref.evidence_ref: ref for ref in self.references}

    def sample_refs_for(self, slot: SafetySlotContext) -> tuple[str, ...]:
        """Sample refs this slot may cite: same-category statutory or supplemental only."""
        if slot.kind is SafetyKind.STATUTORY:
            return tuple(r.evidence_ref for r in self.references if r.legal_category_id == slot.category_id)
        if slot.primary_ref is not None:
            return (slot.primary_ref, *slot.support_refs)
        return tuple(
            r.evidence_ref for r in self.references if r.kind is SafetyReferenceKind.SUPPLEMENTAL_REFERENCE
        )


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
    section_evidence: tuple[GroundingContextItem, ...]
    reference_activities: tuple[ReferenceActivityContext, ...]
    other_outdoor_evidence: tuple[GroundingContextItem, ...]
    constraints: ContextConstraints
    lineage: ContextLineage
    trimmed_blocks: tuple[str, ...] = ()
    safety: SafetyContext | None = None

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
        all_evidence = self.grounding_items
        ids = tuple(item.evidence_ref for item in all_evidence)
        if len(set(ids)) != len(ids):
            raise InvalidDomainValueError("Context evidence records cannot appear in multiple blocks")
        if any(item.reuse_policy is not ReusePolicy.CONTEXT_ONLY for item in all_evidence):
            raise InvalidDomainValueError(
                "Institution Context currently permits CONTEXT_ONLY evidence only"
            )
        if any(item.grounding_class is None for item in self.section_evidence):
            raise InvalidDomainValueError("Section evidence requires an approved grounding_class")
        if any(
            item.grounding_class is not None
            for item in self.institution_evidence + self.age_contrast_evidence + self.other_outdoor_evidence
        ):
            raise InvalidDomainValueError("Only section evidence may carry a grounding_class")
        if self.section_evidence and not self.lineage.evidence_classification_version:
            raise InvalidDomainValueError("Section evidence requires the Evidence classification version")
        if self.safety is not None:
            if not isinstance(self.safety, SafetyContext):
                raise InvalidDomainValueError("Context Packet safety is invalid")
            if {slot.week_id for slot in self.safety.slots} != {week.week_id for week in self.weeks}:
                raise InvalidDomainValueError("Safety slots must cover exactly the Context weeks")
            if set(self.safety.official_by_ref) & set(ids):
                raise InvalidDomainValueError("Official safety refs cannot reuse evidence refs")

    @property
    def grounding_items(self) -> tuple[GroundingContextItem, ...]:
        return (
            self.institution_evidence
            + self.age_contrast_evidence
            + self.section_evidence
            + self.other_outdoor_evidence
            + (self.safety.evidence if self.safety is not None else ())
        )
