"""Deterministic hybrid retrieval over Evidence Store and Activity Reference."""

from __future__ import annotations

import collections

from ..domain.activity_reference import ActivityCatalog, OUTDOOR_PLAY_SLOT
from ..evidence.classification import EvidenceSemanticClassification, SemanticClass
from ..evidence.models import EvidenceRecord, SourceSection
from ..evidence.safety_classification import SafetyEvidenceClassification, SafetyReferenceKind
from ..evidence.safety_quality import SafetyReferenceQuality
from ..evidence.store import InstitutionEvidenceStore
from .models import (
    AGE_VERIFIABLE_TIERS,
    CLASS_BLOCKS,
    AgeMatchKind,
    BlockName,
    EvidenceBlock,
    MonthlyEvidenceRetrievalResult,
    ReferenceCandidate,
    RetrievalRequest,
)
from .ranking import apply_source_diversity, balance_by_age, ngrams, rank_records

RETRIEVAL_VERSION = "monthly-evidence-retrieval-v0.3.0"
# Versioned apart so packets without safety placement keep their lineage.
SAFETY_RETRIEVAL_VERSION = "monthly-safety-retrieval-v0.4.0"
DEFAULT_TOP_K = {
    BlockName.INSTITUTION_MONTHLY_EVIDENCE: 12,
    BlockName.AGE_CONTRAST_EVIDENCE: 6,
    **{name: 10 for name in CLASS_BLOCKS.values()},
    BlockName.REFERENCE_ACTIVITIES: 12,
    BlockName.OTHER_OUTDOOR_EVIDENCE: 10,
    BlockName.SAFETY_EDUCATION_EVIDENCE: 12,
    BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE: 12,
    BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE: 12,
}
_GROUNDING_TIERS = AGE_VERIFIABLE_TIERS
_EXPANSION_TIERS = _GROUNDING_TIERS + (AgeMatchKind.AGE_UNKNOWN,)


class MonthlyEvidenceRetriever:
    def __init__(
        self,
        store: InstitutionEvidenceStore,
        *,
        activity_catalog: ActivityCatalog | None = None,
        classification: EvidenceSemanticClassification | None = None,
        safety_classification: SafetyEvidenceClassification | None = None,
        safety_quality: SafetyReferenceQuality | None = None,
        institution_cap: int = 2,
        top_k: dict[BlockName, int] | None = None,
    ) -> None:
        if type(institution_cap) is not int or institution_cap < 1:
            raise ValueError("institution_cap must be positive")
        if classification is not None:
            classification.require_bound_to(store.content_sha256)
        if safety_classification is not None:
            safety_classification.require_bound_to(store.content_sha256)
        self._safety_classification = safety_classification
        self._safety_quality = safety_quality
        self._store = store
        self._catalog = activity_catalog
        self._classification = classification
        self._cap = institution_cap
        self._top_k = dict(DEFAULT_TOP_K)
        if top_k:
            self._top_k.update(top_k)
        self._contrast_sources = self._find_contrast_sources()

    def _find_contrast_sources(self) -> frozenset[str]:
        ages: dict[str, set[int]] = collections.defaultdict(set)
        for record in self._store.records:
            if record.single_age is not None:
                ages[record.source_sha256].add(record.single_age)
        return frozenset(source for source, values in ages.items() if len(values) >= 2)

    @staticmethod
    def _query_grams(request: RetrievalRequest) -> frozenset[str]:
        grams = set(ngrams(request.confirmed_theme_value))
        for keyword in request.keywords:
            grams.update(ngrams(keyword))
        return frozenset(grams)

    def _ranked_block(
        self,
        *,
        name: BlockName,
        records: list[EvidenceRecord],
        request: RetrievalRequest,
        query_grams: frozenset[str],
        tiers: tuple[AgeMatchKind, ...],
        cap: int | None = None,
    ) -> EvidenceBlock:
        ranked = rank_records(
            records,
            requested_ages=request.ages,
            query_grams=query_grams,
            allowed_tiers=tiers,
        )
        ranked = balance_by_age(ranked, request.ages)
        limit = self._top_k[name]
        return EvidenceBlock(
            name=name,
            top_k=limit,
            retrieval_reason=(
                "month and section hard filters; age structural tier; Korean 2-gram "
                "keyword score; source diversity; stable record_id tie-break"
            ),
            items=apply_source_diversity(
                ranked, top_k=limit, institution_cap=self._cap if cap is None else cap
            ),
            eligible_pool_size=len(ranked),
        )

    def _institution(self, request: RetrievalRequest, grams: frozenset[str]) -> EvidenceBlock:
        records = [
            record for record in self._store.by_month(request.target_month.calendar_month)
            if record.outdoor_activity_eligible
            and record.source_section is SourceSection.OUTDOOR_PLAY
        ]
        return self._ranked_block(
            name=BlockName.INSTITUTION_MONTHLY_EVIDENCE,
            records=records,
            request=request,
            query_grams=grams,
            tiers=_GROUNDING_TIERS,
        )

    def _contrast(self, request: RetrievalRequest, grams: frozenset[str]) -> EvidenceBlock:
        records = [
            record for record in self._store.by_month(request.target_month.calendar_month)
            if record.source_sha256 in self._contrast_sources
            and record.outdoor_activity_eligible
            and record.single_age is not None
        ]
        by_source: dict[str, list[EvidenceRecord]] = collections.defaultdict(list)
        for record in records:
            by_source[record.source_sha256].append(record)
        usable = []
        for source in sorted(by_source):
            rows = by_source[source]
            source_ages = {record.single_age for record in rows}
            if len(source_ages) >= 2 and source_ages & request.ages:
                usable.extend(rows)
        return self._ranked_block(
            name=BlockName.AGE_CONTRAST_EVIDENCE,
            records=usable,
            request=request,
            query_grams=grams,
            tiers=(AgeMatchKind.SINGLE_AGE_EXACT, AgeMatchKind.SINGLE_AGE_IN_REQUEST),
            cap=self._cap + 1,
        )

    def _classified(
        self, request: RetrievalRequest, grams: frozenset[str], semantic_class: SemanticClass
    ) -> EvidenceBlock:
        name = CLASS_BLOCKS[semantic_class]
        if semantic_class not in request.grounding_classes:
            return EvidenceBlock(name, self._top_k[name], "Section/variant not active in the Template Snapshot")
        if self._classification is None:
            raise ValueError("Section-scoped retrieval requires an approved Evidence classification")
        records = [
            record for record in self._store.by_month(request.target_month.calendar_month)
            if record.general_grounding_eligible
            and self._classification.class_of(record) is semantic_class
        ]
        return self._ranked_block(
            name=name,
            records=records,
            request=request,
            query_grams=grams,
            tiers=_EXPANSION_TIERS,
        )

    def _references(self, request: RetrievalRequest) -> EvidenceBlock:
        name = BlockName.REFERENCE_ACTIVITIES
        if self._catalog is None:
            return EvidenceBlock(name, self._top_k[name], "Activity Catalog was not supplied")
        candidates = self._catalog.eligible_candidates(
            section_key=OUTDOOR_PLAY_SLOT,
            calendar_month=request.target_month.calendar_month,
            ages=request.ages,
        )
        ordered = sorted(
            candidates,
            key=lambda item: (
                0 if item.links_theme(request.confirmed_theme_id) else 1,
                1 if item.has_confirmed_display_issue else 0,
                -item.evidence_strength_for_month(request.target_month.calendar_month),
                item.activity_id,
            ),
        )
        limit = self._top_k[name]
        return EvidenceBlock(
            name,
            limit,
            "PR3 hard eligibility then deterministic theme/quality/evidence/id retrieval ranking",
            reference_items=tuple(
                ReferenceCandidate(
                    item.activity_id,
                    item.label,
                    item.evidence_strength_for_month(request.target_month.calendar_month),
                    item.has_confirmed_display_issue,
                    rank,
                )
                for rank, item in enumerate(ordered[:limit])
            ),
            eligible_pool_size=len(candidates),
        )

    def _other(
        self,
        request: RetrievalRequest,
        grams: frozenset[str],
        used_ids: frozenset[str],
    ) -> EvidenceBlock:
        records = [
            record for record in self._store.by_month(request.target_month.calendar_month)
            if record.outdoor_activity_eligible and record.record_id not in used_ids
        ]
        return self._ranked_block(
            name=BlockName.OTHER_OUTDOOR_EVIDENCE,
            records=records,
            request=request,
            query_grams=grams,
            # Outdoor grounding must be age-verifiable (Rule-owned): no AGE_UNKNOWN.
            tiers=_GROUNDING_TIERS,
        )

    def _safety(self, request: RetrievalRequest, grams: frozenset[str]) -> tuple[EvidenceBlock, ...]:
        """Approved References only; nothing without an approved safety classification."""
        statutory, supplemental = [], []
        for record in self._store.by_month(request.target_month.calendar_month):
            if not (
                record.general_grounding_eligible
                and record.source_section is SourceSection.SAFETY_EDUCATION
                and record.text is not None
                and self._safety_classification is not None
            ):
                continue
            reference = self._safety_classification.runtime_reference(record)
            if reference is None:
                continue
            if reference.kind is SafetyReferenceKind.SUPPLEMENTAL_REFERENCE:
                # Only human-reviewed USABLE contents; no quality review means none.
                if self._safety_quality is not None and self._safety_quality.usable_topic_group(record):
                    supplemental.append(record)
            elif reference.legal_category_id in request.safety_categories:
                statutory.append(record)
        safety_grams = set(grams)
        for keyword in request.safety_keywords:
            safety_grams.update(ngrams(keyword))
        return (
            self._ranked_block(
                name=BlockName.SAFETY_EDUCATION_EVIDENCE,
                records=statutory,
                request=request,
                query_grams=frozenset(safety_grams),
                tiers=_EXPANSION_TIERS,
            ),
            # ponytail: no label balancing; observe real results before adding one.
            self._ranked_block(
                name=BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE,
                records=supplemental,
                request=request,
                query_grams=grams,
                tiers=_EXPANSION_TIERS,
            ),
            self._ranked_block(
                name=BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE,
                records=self._cross_month_supplemental(request),
                request=request,
                query_grams=grams,
                tiers=_EXPANSION_TIERS,
            ),
        )

    def _cross_month_supplemental(self, request: RetrievalRequest) -> list[EvidenceRecord]:
        """Other months: approved, USABLE, human-reviewed MONTH_INDEPENDENT contents only."""
        if self._safety_classification is None or self._safety_quality is None:
            return []
        records = []
        for record in self._store.records:
            if (
                record.month != request.target_month.calendar_month
                and record.general_grounding_eligible
                and record.source_section is SourceSection.SAFETY_EDUCATION
                and record.text is not None
                and (reference := self._safety_classification.runtime_reference(record)) is not None
                and reference.kind is SafetyReferenceKind.SUPPLEMENTAL_REFERENCE
                and self._safety_quality.month_independent_topic_group(record)
            ):
                records.append(record)
        return records

    def retrieve(self, request: RetrievalRequest) -> MonthlyEvidenceRetrievalResult:
        grams = self._query_grams(request)
        institution = self._institution(request, grams)
        contrast = self._contrast(request, grams)
        classified = tuple(
            self._classified(request, grams, semantic_class) for semantic_class in CLASS_BLOCKS
        )
        references = self._references(request)
        used = frozenset(item.record_id for item in institution.items)
        other = self._other(request, grams, used)
        safety = self._safety(request, grams) if request.safety_keywords else ()
        return MonthlyEvidenceRetrievalResult(
            request=request,
            blocks=(institution, contrast, *classified, references, other, *safety),
            evidence_store_version=self._store.ingestion_version,
            evidence_store_sha256=self._store.content_sha256,
            retrieval_version=RETRIEVAL_VERSION,
            activity_catalog_id=self._catalog.catalog_id if self._catalog else "",
            activity_catalog_version=self._catalog.catalog_version if self._catalog else "",
            evidence_classification_version=(
                self._classification.classification_version if self._classification else ""
            ),
        )
