"""Deterministic structural and Korean keyword ranking with source diversity."""

from __future__ import annotations

import collections
import re
from collections.abc import Iterable, Sequence

from ..evidence.models import EvidenceRecord
from .models import AGE_TIER_ORDER, AgeMatchKind, RetrievalTrace, RetrievedEvidence

DEFAULT_INSTITUTION_CAP = 2
_HANGUL = re.compile(r"[^가-힣]")


def ngrams(text: str | None, n: int = 2) -> frozenset[str]:
    normalized = _HANGUL.sub("", text or "")
    if len(normalized) < n:
        return frozenset({normalized} if normalized else ())
    return frozenset(normalized[index:index + n] for index in range(len(normalized) - n + 1))


def age_match_kind(record: EvidenceRecord, requested: frozenset[int]) -> AgeMatchKind | None:
    scope = set(record.age_scope)
    if record.single_age is not None and record.single_age in requested:
        return AgeMatchKind.SINGLE_AGE_EXACT if len(requested) == 1 else AgeMatchKind.SINGLE_AGE_IN_REQUEST
    if scope & requested:
        return AgeMatchKind.MIXED_AGE_COVERING
    if not scope:
        return AgeMatchKind.AGE_UNKNOWN
    return None


def diversity_group(record: EvidenceRecord) -> str:
    if record.template_family:
        return "TEMPLATE_FAMILY"
    return record.institution_id or "UNKNOWN_INSTITUTION"


def rank_records(
    records: Iterable[EvidenceRecord],
    *,
    requested_ages: frozenset[int],
    query_grams: frozenset[str],
    allowed_tiers: Sequence[AgeMatchKind] = AGE_TIER_ORDER,
) -> list[RetrievedEvidence]:
    tier_rank = {kind: index for index, kind in enumerate(AGE_TIER_ORDER)}
    allowed = set(allowed_tiers)
    ranked: list[RetrievedEvidence] = []
    for record in records:
        kind = age_match_kind(record, requested_ages)
        if kind is None or kind not in allowed:
            continue
        page_match = bool(ngrams(record.monthly_theme) & query_grams)
        overlap = len(ngrams(record.text) & query_grams)
        structural = (len(AGE_TIER_ORDER) - tier_rank[kind]) * 100
        score = structural + (10 if page_match else 0) + min(overlap, 9)
        ranked.append(
            RetrievedEvidence(
                record,
                RetrievalTrace(
                    age_match=kind,
                    structural_score=structural,
                    keyword_overlap=overlap,
                    theme_page_match=page_match,
                    total_score=score,
                    diversity_group=diversity_group(record),
                ),
            )
        )
    ranked.sort(
        key=lambda item: (
            tier_rank[item.trace.age_match],
            0 if item.trace.theme_page_match else 1,
            -item.trace.keyword_overlap,
            item.record_id,
        )
    )
    return ranked


def balance_by_age(
    ranked: Sequence[RetrievedEvidence], requested_ages: frozenset[int]
) -> list[RetrievedEvidence]:
    if len(requested_ages) < 2:
        return list(ranked)
    queues = {age: [] for age in sorted(requested_ages)}
    rest = []
    for item in ranked:
        if item.record.single_age in queues:
            queues[item.record.single_age].append(item)
        else:
            rest.append(item)
    result: list[RetrievedEvidence] = []
    while any(queues.values()):
        for age in sorted(queues):
            if queues[age]:
                result.append(queues[age].pop(0))
    return result + rest


def apply_source_diversity(
    ranked: Sequence[RetrievedEvidence], *, top_k: int, institution_cap: int = DEFAULT_INSTITUTION_CAP
) -> tuple[RetrievedEvidence, ...]:
    if top_k < 1:
        return ()
    used: collections.Counter[str] = collections.Counter()
    selected = []
    for item in ranked:
        group = item.trace.diversity_group
        if used[group] >= institution_cap:
            continue
        used[group] += 1
        selected.append(item)
        if len(selected) == top_k:
            break
    return tuple(selected)
