"""Evidence for one Weekly Section from the approved Weekly classification (W1 §7).

The same steps as a Monthly section block, without touching the Monthly retriever
(ADR-033): same calendar month, quality-eligible, exactly that class, age-verifiable
only (2026-10-21 decision B: no AGE_UNKNOWN), age-balanced, source-diverse.
"""

from __future__ import annotations

from ..evidence.store import InstitutionEvidenceStore
from ..evidence.weekly_classification import WeeklyEvidenceClassification, WeeklySemanticClass
from .models import AGE_VERIFIABLE_TIERS, RetrievedEvidence
from .ranking import DEFAULT_INSTITUTION_CAP, apply_source_diversity, balance_by_age, ngrams, rank_records

WEEKLY_SECTION_TOP_K = 10  # the Monthly section block default


def weekly_section_evidence(
    store: InstitutionEvidenceStore,
    classification: WeeklyEvidenceClassification,
    *,
    weekly_class: WeeklySemanticClass,
    calendar_month: int,
    ages: frozenset[int],
    query_text: str,
    top_k: int = WEEKLY_SECTION_TOP_K,
    institution_cap: int = DEFAULT_INSTITUTION_CAP,
) -> tuple[RetrievedEvidence, ...]:
    """query_text: the parent theme and this week's focus, for the Korean 2-gram score."""
    classification.require_bound_to(store.content_sha256)
    records = [
        record for record in store.by_month(calendar_month)
        if record.general_grounding_eligible and classification.class_of(record) is weekly_class
    ]
    ranked = rank_records(
        records, requested_ages=ages, query_grams=ngrams(query_text), allowed_tiers=AGE_VERIFIABLE_TIERS
    )
    return apply_source_diversity(
        balance_by_age(ranked, ages), top_k=top_k, institution_cap=institution_cap
    )
