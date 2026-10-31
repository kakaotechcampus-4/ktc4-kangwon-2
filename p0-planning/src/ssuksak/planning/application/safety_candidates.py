"""The eight monthly safety candidate slots (statutory 6 + 생활안전 2), shared by v1 and v2.

The Rule fixes each slot's kind and allowed refs before any LLM call; the LLM only words
one sentence per slot. A failure carries an internal ``code`` the caller maps to its own error.
"""

from __future__ import annotations

from ..domain.errors import DomainError, InvalidDomainValueError
from ..domain.provenance import EvidenceSource, EvidenceSourceType
from ..domain.safety_placement import SafetyCandidateSlot, SafetyKind
from ..domain.safety_rule import SafetyLegalRule
from ..evidence.models import SourceSection
from ..evidence.safety_classification import (
    SafetyEvidenceClassification,
    SafetyReferenceKind,
)
from ..evidence.safety_quality import SafetyReferenceQuality
from ..evidence.store import InstitutionEvidenceStore
from ..rules.safety_placement import (
    STATUTORY_SHORT_LABELS,
    official_ref,
    select_supplemental_primaries,
)

LIFE_SAFETY_LABEL = "life_safety"
LIFE_SAFETY_SLOTS = ("life_safety_1", "life_safety_2")


class SafetyCandidateError(DomainError):
    """Internal gate failure; ``code`` is not a public API error code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def safety_candidate_slots(
    rule: SafetyLegalRule,
    store: InstitutionEvidenceStore,
    classification: SafetyEvidenceClassification,
    quality: SafetyReferenceQuality,
    *,
    month: int,
    classification_version: str,
    quality_version: str,
) -> tuple[tuple[SafetyCandidateSlot, ...], dict]:
    """All eight slots, or fail: the set never shrinks to six. Returns (slots, records by ref)."""
    if any(not category.content_items for category in rule.categories):
        raise SafetyCandidateError("SAFETY_RULE_INCOMPLETE")
    if not (classification.runtime_active and quality.runtime_active):
        raise SafetyCandidateError("SAFETY_EVIDENCE_NOT_ACTIVE")
    if (classification.classification_version, quality.quality_version) != (
        classification_version,
        quality_version,
    ):
        raise SafetyCandidateError("SAFETY_EVIDENCE_VERSION_MISMATCH")
    try:
        classification.require_bound_to(store.content_sha256)
        classification.require_legal_rule(rule)
        quality.require_bound_to(store.content_sha256, classification.classification_version)
    except InvalidDomainValueError:
        raise SafetyCandidateError("SAFETY_EVIDENCE_STORE_MISMATCH") from None

    statutory = tuple(
        SafetyCandidateSlot(
            slot=category.category_id,
            kind=SafetyKind.STATUTORY,
            label=STATUTORY_SHORT_LABELS.get(category.category_id, category.official_label),
            allowed=tuple(
                (official_ref(category.category_id, i), item) for i, item in enumerate(category.content_items, 1)
            ),
            category_id=category.category_id,
        )
        for category in rule.categories
    )

    records = {}
    candidates = []
    # Target month first (tier 0), then other months' approved MONTH_INDEPENDENT contents.
    for record in sorted(store.records, key=lambda r: (r.month != month, r.record_id)):
        if not (
            record.general_grounding_eligible
            and record.source_section is SourceSection.SAFETY_EDUCATION
            and record.text is not None
        ):
            continue
        reference = classification.runtime_reference(record)
        if (
            reference is None
            or reference.kind is not SafetyReferenceKind.SUPPLEMENTAL_REFERENCE
            or reference.supplemental_label != LIFE_SAFETY_LABEL
        ):
            continue
        tier = 0 if record.month == month else 1
        group = quality.usable_topic_group(record) if tier == 0 else quality.month_independent_topic_group(record)
        if group is not None:
            records[record.record_id] = record
            candidates.append((record.record_id, LIFE_SAFETY_LABEL, group, tier))
    try:
        picks = select_supplemental_primaries(len(LIFE_SAFETY_SLOTS), tuple(candidates))
    except ValueError:
        raise SafetyCandidateError("LIFE_SAFETY_GROUNDING_INSUFFICIENT") from None
    groups = {ref: group for ref, _, group, _ in candidates}
    life = tuple(
        SafetyCandidateSlot(
            slot=slot,
            kind=SafetyKind.SUPPLEMENTAL,
            label="생활안전",
            allowed=tuple((ref, records[ref].text) for ref in (primary, *support)),
            topic_group=groups[primary],
        )
        for slot, (primary, support) in zip(LIFE_SAFETY_SLOTS, picks)
    )
    return statutory + life, records


def candidate_evidence(
    slot: SafetyCandidateSlot,
    refs: tuple[str, ...],
    *,
    legal_rule_version: str,
    store: InstitutionEvidenceStore,
    records: dict,
) -> tuple[EvidenceSource, ...]:
    """Statutory = the official items cited; 생활안전 = the institution samples cited."""
    if slot.kind is SafetyKind.STATUTORY:
        texts = dict(slot.allowed)
        return tuple(
            EvidenceSource(EvidenceSourceType.SAFETY_RULE, ref, legal_rule_version, display_name=texts[ref])
            for ref in refs
        )
    return tuple(
        EvidenceSource(
            EvidenceSourceType.INSTITUTION_SAMPLE,
            ref,
            store.ingestion_version,
            display_name=records[ref].source_label,
        )
        for ref in refs
    )
