"""Evidence for one Weekly Section from the approved Weekly classification (W1 §7).

The same steps as a Monthly section block, without touching the Monthly retriever
(ADR-033): same calendar month, quality-eligible, exactly that class, age-verifiable
only (2026-10-21 decision B: no AGE_UNKNOWN), age-balanced, source-diverse.
"""

from __future__ import annotations

import collections
import re

from ..venue_policy import venue_bound_evidence

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
    prefer_explicit_indoor_methods,
)

WEEKLY_SECTION_TOP_K = 10  # the Monthly section block default

# shortcut: only reviewed sources are filtered; extend after reviewing new unclear candidates (ADR-054).
# Match both id and text so a revised source does not inherit this decision.
REVIEWED_UNCLEAR_ACTIVITY_SOURCES = frozenset({
    ("ev_1ece5ba592aa_p01_r00281_c02_i01", "어떤 놀잇감일까요?"),  # no activity type or action
    ("ev_010245b6472d_p01_r00208_c05_i02", "우리 반에서 지켜야 할 약속"),  # no specific situation
    ("ev_e5e84e83db52_p01_r00216_c02_i01", "새로운 놀잇감으로 놀이해요"),  # no role or play situation
    ("ev_e5e84e83db52_p01_r00428_c01_i02", "파랑새반 약속!"),  # no activity type or situation
    ("ev_5d3e713585b1_p01_r00603_c06_i01", "우리반 미술 도구"),  # no expression activity
    ("ev_5d3e713585b1_p01_r00603_c07_i01", "누구의 얼굴일까?"),  # no expression activity
    ("ev_5d3e713585b1_p01_r00603_c08_i01", "우리반 놀잇감을 탐색해요"),  # no art expression method
    ("ev_010245b6472d_p01_r00208_c03_i01", "‘ㄱ, ㄴ, ㄷ’ 낱말을 배워요"),  # no play method
    ("ev_010245b6472d_p01_r00208_c04_i01", "같은 신발 다른 신발"),  # no language activity method
    ("ev_5d3e713585b1_p01_r00252_c04_i01", "새로운 우리반, 새로운 선생님"),  # topic heading only
    ("ev_5d3e713585b1_p01_r00252_c07_i01", "이럴땐 이렇게"),  # no situation or activity
})


def candidate_activity_basis(record) -> tuple[str, tuple[str, ...]]:
    """Select a literal source span; never invent an activity from a broad topic."""
    text = (record.text or "").strip()
    if (record.record_id, record.text) == (
        "ev_e5e84e83db52_p01_r00428_c01_i01", "<이야기 나누기> 편지 발표, 함께 지켜요"
    ):
        return "편지 발표", ("편지", "발표")
    if re.fullmatch(r"동화\s*[\[<【(].+[\]>】)]\s*듣기", text):
        return text, ("듣기",)
    tags = list(re.finditer(
        r"[\[<【(]\s*(이야기\s*나누기|동화|동시|동요|새노래|음률|음악|미술|신체|게임|과학|요리|동극|명화)\s*[\]>】)]",
        text,
    ))
    if tags and not text[:tags[0].start()].strip():
        basis = text[tags[0].start():tags[1].start() if len(tags) > 1 else len(text)].strip()
        return basis, ("감상",) if tags[0].group(1) == "명화" else ()
    return text, ()


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


def indoor_play_type(record) -> str:
    """Use explicit source areas only; do not infer a play area from an activity."""
    areas = {
        "역할": "역할놀이", "쌓기": "쌓기놀이", "언어": "언어놀이",
        "수조작": "수·조작놀이", "수·조작": "수·조작놀이", "수ㆍ조작": "수·조작놀이",
        "미술": "미술놀이", "음률": "음률놀이", "과학": "과학놀이", "신체": "신체놀이",
    }
    for text in (record.source_label, record.text):
        compact = re.sub(r"\s+", "", text)
        tag = re.match(r"^[\[<【(]([^\]>】)]+)[\]>】)]", compact)
        label = tag.group(1) if tag else compact if text == record.source_label else ""
        label = re.sub(r"(?:놀이|영역)$", "", label)
        if label in areas:
            return areas[label]
    return "기타"


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
    preferred_refs: tuple[str, ...] = (),
    explicit_indoor_methods: bool = False,
    exclude_venue_bound: bool = False,
) -> tuple[RetrievedEvidence, ...]:
    """query_text: the parent theme and this week's focus, for the Korean 2-gram score."""
    classification.require_bound_to(store.content_sha256)
    records = [
        record for record in store.by_month(calendar_month)
        if record.general_grounding_eligible and classification.class_of(record) is weekly_class
        and (not exclude_venue_bound or not venue_bound_evidence(record.text))
    ]
    if by_activity_type and weekly_class in {WeeklySemanticClass.INDOOR_PLAY, WeeklySemanticClass.GROUP_ACTIVITY}:
        records = [record for record in records
                   if (record.record_id, record.text) not in REVIEWED_UNCLEAR_ACTIVITY_SOURCES]
    grams = ngrams(query_text)
    if focus_text.strip():
        shared = collections.Counter(gram for focus in sibling_focuses for gram in ngrams(focus))
        common = {gram for gram, count in shared.items() if len(sibling_focuses) > 1 and count * 2 > len(sibling_focuses)}
        # Shared month words do not distinguish this week's experience; keep the old query if none remain.
        grams = (ngrams(focus_text) - common) or grams
    ranked = rank_records(
        records, requested_ages=ages, query_grams=grams, allowed_tiers=AGE_VERIFIABLE_TIERS
    )
    if explicit_indoor_methods and weekly_class is WeeklySemanticClass.INDOOR_ALTERNATIVE:
        ranked = prefer_explicit_indoor_methods(ranked)
    ordered = balance_by_age(ranked, ages)
    # Keep a valid parent citation ahead of the top-k cutoff; never bypass the filters above.
    if preferred_refs:
        preferred = frozenset(preferred_refs)
        ordered.sort(key=lambda item: item.record_id not in preferred)
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
            kind = indoor_play_type(item.record) if weekly_class is WeeklySemanticClass.INDOOR_PLAY else activity_type(item.record)
            groups.setdefault(kind, []).append(item)
        ordered = []
        while any(groups.values()):
            for group in groups.values():
                if group:
                    ordered.append(group.pop(0))
    # Human Decision 2026-11-05(하민): for candidate pools the source cap orders, it does not cut (ADR-054).
    return apply_source_diversity(ordered, top_k=top_k, institution_cap=institution_cap, fill=by_activity_type)
