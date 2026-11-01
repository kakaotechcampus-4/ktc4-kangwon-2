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


def fill_subtheme_gaps(
    ranked: Sequence[RetrievedEvidence],
    selected: Sequence[RetrievedEvidence],
    subthemes: Sequence[str],
    *,
    institution_cap: int = DEFAULT_INSTITUTION_CAP,
) -> tuple[RetrievedEvidence, ...]:
    """Swap in one ranked record for each subtheme no selected record matches.

    Size, institution cap and already matched subthemes are kept: the record swapped out is the
    lowest-ranked one whose removal leaves every matched subtheme matched. Matching is lexical
    (Korean 2-gram overlap, at least two or all of a short subtheme's grams) after dropping grams
    shared by more than half the subthemes, such as 나라 in 우리나라 / 세계 여러 나라. A subtheme with
    no grams left is skipped. A match is not proof the record covers the subtheme's meaning.
    """
    subthemes = [subtheme for subtheme in subthemes if ngrams(subtheme)]
    shared = collections.Counter(gram for subtheme in subthemes for gram in ngrams(subtheme))
    common = {gram for gram, count in shared.items() if count * 2 > len(subthemes)}
    grams = {subtheme: ngrams(subtheme) - common for subtheme in subthemes}

    def matches(item: RetrievedEvidence, subtheme: str) -> bool:
        wanted = grams[subtheme]
        return bool(wanted) and len(ngrams(item.record.text) & wanted) >= min(2, len(wanted))

    order = {item.record_id: index for index, item in enumerate(ranked)}
    chosen = list(selected)
    for subtheme in subthemes:
        if not grams[subtheme] or any(matches(item, subtheme) for item in chosen):
            continue
        ids = {item.record_id for item in chosen}
        candidates = [item for item in ranked if item.record_id not in ids and matches(item, subtheme)]
        if not candidates:
            continue
        add = max(
            candidates,
            key=lambda item: (len(ngrams(item.record.text) & grams[subtheme]), -order[item.record_id]),
        )
        groups = collections.Counter(item.trace.diversity_group for item in chosen)
        same_group_only = groups[add.trace.diversity_group] >= institution_cap
        matched = [other for other in subthemes if any(matches(item, other) for item in chosen)]
        for out in sorted(chosen, key=lambda item: -order[item.record_id]):
            if same_group_only and out.trace.diversity_group != add.trace.diversity_group:
                continue
            rest = [item for item in chosen if item is not out]
            if all(any(matches(item, other) for item in rest) for other in matched):
                chosen = sorted([*rest, add], key=lambda item: order[item.record_id])
                break
    return tuple(chosen)
