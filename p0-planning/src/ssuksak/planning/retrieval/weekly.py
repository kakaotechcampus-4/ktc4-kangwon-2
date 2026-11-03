"""Evidence for one Weekly Section from the approved Weekly classification (W1 §7).

The same steps as a Monthly section block, without touching the Monthly retriever
(ADR-033): same calendar month, quality-eligible, exactly that class, age-verifiable
only (2026-10-21 decision B: no AGE_UNKNOWN), age-balanced, source-diverse.
"""

from __future__ import annotations

import collections
import re

from ..evidence.store import InstitutionEvidenceStore
from ..evidence.weekly_classification import (
    WeeklyEvidenceClassification,
    WeeklySemanticClass,
)
from .models import AGE_VERIFIABLE_TIERS, RetrievedEvidence
from .ranking import (
    DEFAULT_INSTITUTION_CAP,
    apply_source_diversity,
    balance_by_age,
    ngrams,
    rank_records,
)

WEEKLY_SECTION_TOP_K = 10  # the Monthly section block default


def activity_type(record) -> str:
    """Keep explicit source tags; an untyped record is not assigned a guessed genre."""
    kinds = ("이야기나누기", "동화", "동시", "동요", "새노래", "음률", "음악", "미술", "신체", "게임", "과학", "요리", "동극")
    for text in (record.text, record.source_label):
        tag = re.match(r"^\s*[\[<【(]\s*([^\]>】)]{1,20})[\]>】)]", text)
        if tag:
            tokens = re.split(r"[·ㆍ･,/／]", re.sub(r"\s+", "", tag.group(1)))
            matched = [kind for kind in kinds if kind in tokens]
            if matched:
                return "·".join(matched)
    label = re.sub(r"\s+", "", record.source_label)
    matched = [kind for kind in kinds if kind in label]
    return "·".join(matched) if matched else "기타"


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
    focus_text: str = "",
    sibling_focuses: tuple[str, ...] = (),
    by_activity_type: bool = False,
) -> tuple[RetrievedEvidence, ...]:
    """query_text: the parent theme and this week's focus, for the Korean 2-gram score."""
    classification.require_bound_to(store.content_sha256)
    records = [
        record for record in store.by_month(calendar_month)
        if record.general_grounding_eligible and classification.class_of(record) is weekly_class
    ]
    grams = ngrams(query_text)
    if focus_text.strip():
        shared = collections.Counter(gram for focus in sibling_focuses for gram in ngrams(focus))
        common = {gram for gram, count in shared.items() if len(sibling_focuses) > 1 and count * 2 > len(sibling_focuses)}
        # Shared month words do not distinguish this week's experience; keep the old query if none remain.
        grams = (ngrams(focus_text) - common) or grams
    ranked = rank_records(
        records, requested_ages=ages, query_grams=grams, allowed_tiers=AGE_VERIFIABLE_TIERS
    )
    ordered = balance_by_age(ranked, ages)
    if by_activity_type:
        groups = {}
        seen = set()
        for item in ordered:
            title = " ".join(item.record.text.split()).casefold()
            if title in seen:
                continue
            seen.add(title)
            if re.match(r"^\s*[【\[<][^】\]>]*$", item.record.text):
                continue  # an incomplete extracted tag is not an activity title
            groups.setdefault(activity_type(item.record), []).append(item)
        ordered = []
        while any(groups.values()):
            for group in groups.values():
                if group:
                    ordered.append(group.pop(0))
    return apply_source_diversity(ordered, top_k=top_k, institution_cap=institution_cap)
