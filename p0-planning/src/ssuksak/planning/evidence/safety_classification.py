"""Exact item-tag classification of Institution safety_education Evidence.

A record's item tag is the exact text inside a leading ``[...]`` of its item
text; ``source_label`` is usually only the row title (안전교육) and carries no
topic. Unlisted or untagged records are NEEDS_REVIEW. A STATUTORY_REFERENCE
never decides a legal category: the legal Rule does. It may only support a
STATUTORY placement of that same category. Nothing here is used at runtime
until the artifact is HUMAN_APPROVED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ..domain.errors import InvalidDomainValueError
from ..domain.safety_placement import SafetyKind, SafetyPlacement
from ..domain.safety_rule import SafetyLegalRule
from .models import EvidenceRecord, SourceSection

SAFETY_CLASSIFICATION_SCHEMA_VERSION = "safety-evidence-classification.schema.v0"
# v1 adds multi_tag_rule; v0 artifacts stay loadable unchanged.
SAFETY_CLASSIFICATION_SCHEMA_V1 = "safety-evidence-classification.schema.v1"
MULTI_TAG_RULE = "MULTIPLE_SQUARE_BRACKET_TAGS_NEEDS_REVIEW"
MULTI_TAG_REASON = "multi-tag record: the leading tag does not represent the whole record"
_ANY_TAG = re.compile(r"\[[^\[\]]+\]")
SAFETY_CLASSIFICATION_ID = "ssuksak.safety-evidence-classification"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEADING_TAG = re.compile(r"^\[([^\[\]]+)\]")


class SafetyReferenceKind(str, Enum):
    STATUTORY_REFERENCE = "STATUTORY_REFERENCE"
    SUPPLEMENTAL_REFERENCE = "SUPPLEMENTAL_REFERENCE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


def square_bracket_tag_count(text: str | None) -> int:
    return len(_ANY_TAG.findall(text or ""))


def item_tag_of(text: str | None) -> str | None:
    """LEADING_SQUARE_BRACKET: the exact inner text of a leading [..], or None."""
    match = _LEADING_TAG.match((text or "").lstrip())
    return match.group(1) if match else None


@dataclass(frozen=True, slots=True)
class SafetyClassificationEntry:
    item_tag: str
    kind: SafetyReferenceKind
    legal_category_id: str | None = None
    supplemental_label: str | None = None
    review_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.item_tag, str) or not self.item_tag.strip():
            raise InvalidDomainValueError("SafetyClassificationEntry.item_tag must be non-blank")
        if not isinstance(self.kind, SafetyReferenceKind):
            raise InvalidDomainValueError("SafetyClassificationEntry.kind is invalid")
        expected = {
            SafetyReferenceKind.STATUTORY_REFERENCE: ("legal_category_id",),
            SafetyReferenceKind.SUPPLEMENTAL_REFERENCE: ("supplemental_label",),
            SafetyReferenceKind.NEEDS_REVIEW: (),
        }[self.kind]
        for name in ("legal_category_id", "supplemental_label"):
            value = getattr(self, name)
            if (name in expected) != (isinstance(value, str) and bool(value.strip())) or (
                value is not None and name not in expected
            ):
                raise InvalidDomainValueError(
                    f"{self.kind.value} entry has an invalid {name}"
                )


NEEDS_REVIEW_DEFAULT = "default: untagged or unlisted item tag"


@dataclass(frozen=True, slots=True)
class SafetyEvidenceClassification:
    classification_version: str
    evidence_content_sha256: str
    legal_rule_version: str
    entries: tuple[SafetyClassificationEntry, ...]
    supplemental_labels: frozenset[str]
    runtime_active: bool = False
    # MULTI_TAG_RULE: a record with two or more [..] tags is NEEDS_REVIEW (no split).
    multi_tag_needs_review: bool = False
    _index: dict[str, SafetyClassificationEntry] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("classification_version", "legal_rule_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"SafetyEvidenceClassification.{name} must be non-blank")
        if not isinstance(self.evidence_content_sha256, str) or not _SHA256.fullmatch(self.evidence_content_sha256):
            raise InvalidDomainValueError("SafetyEvidenceClassification content_sha256 is invalid")
        if not isinstance(self.entries, tuple) or not all(
            isinstance(entry, SafetyClassificationEntry) for entry in self.entries
        ):
            raise InvalidDomainValueError("SafetyEvidenceClassification entries are invalid")
        tags = [entry.item_tag for entry in self.entries]
        if len(set(tags)) != len(tags):
            raise InvalidDomainValueError("SafetyEvidenceClassification repeats an item_tag")
        unknown = {
            entry.supplemental_label for entry in self.entries if entry.supplemental_label is not None
        } - self.supplemental_labels
        if unknown:
            raise InvalidDomainValueError(f"Unknown supplemental labels: {sorted(unknown)}")
        if type(self.runtime_active) is not bool:
            raise InvalidDomainValueError("SafetyEvidenceClassification.runtime_active must be a boolean")
        object.__setattr__(self, "_index", {entry.item_tag: entry for entry in self.entries})

    def require_bound_to(self, content_sha256: str) -> None:
        if content_sha256 != self.evidence_content_sha256:
            raise InvalidDomainValueError("Safety classification is bound to a different Evidence Store")

    def require_legal_rule(self, rule: SafetyLegalRule) -> None:
        """Statutory references may only name categories the legal Rule defines."""
        if rule.legal_rule_version != self.legal_rule_version:
            raise InvalidDomainValueError("Safety classification targets a different legal Rule")
        legal = {category.category_id for category in rule.categories}
        stray = {
            entry.legal_category_id for entry in self.entries if entry.legal_category_id is not None
        } - legal
        if stray:
            raise InvalidDomainValueError(f"Not legal categories: {sorted(stray)}")

    def classify(self, record: EvidenceRecord) -> SafetyClassificationEntry:
        """Candidate classification for review; not a runtime decision."""
        if record.source_section is not SourceSection.SAFETY_EDUCATION:
            raise InvalidDomainValueError("Only safety_education Evidence is classified here")
        tag = item_tag_of(record.text)
        if self.multi_tag_needs_review and square_bracket_tag_count(record.text) > 1:
            return SafetyClassificationEntry(
                tag or "(none)", SafetyReferenceKind.NEEDS_REVIEW, review_reason=MULTI_TAG_REASON
            )
        entry = self._index.get(tag) if tag is not None else None
        return entry or SafetyClassificationEntry(
            tag or "(none)", SafetyReferenceKind.NEEDS_REVIEW, review_reason=NEEDS_REVIEW_DEFAULT
        )

    def runtime_reference(self, record: EvidenceRecord) -> SafetyClassificationEntry | None:
        """A usable Reference only when approved and not NEEDS_REVIEW (fail-closed)."""
        if not self.runtime_active:
            return None
        entry = self.classify(record)
        return None if entry.kind is SafetyReferenceKind.NEEDS_REVIEW else entry


def reference_supports(entry: SafetyClassificationEntry | None, placement: SafetyPlacement) -> bool:
    """Whether a Reference may ground a placed Cell. It never changes the placement."""
    if entry is None or entry.kind is SafetyReferenceKind.NEEDS_REVIEW:
        return False
    if entry.kind is SafetyReferenceKind.STATUTORY_REFERENCE:
        return placement.kind is SafetyKind.STATUTORY and placement.category_id == entry.legal_category_id
    return placement.kind is SafetyKind.SUPPLEMENTAL
