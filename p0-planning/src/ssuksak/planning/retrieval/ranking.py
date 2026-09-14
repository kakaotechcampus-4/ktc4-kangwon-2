"""결정론적 Ranking과 Source Diversity (L2).

**LLM도 Embedding도 쓰지 않는다.** 같은 입력이면 항상 같은 순서가 나온다.

Ranking 신호를 고르기 전에 실제 Corpus에서 변별력을 측정했다(2026-09-13).
공백 토큰만으로는 한국어 Theme이 거의 잡히지 않는다.

    Theme            eligible pool   공백 토큰 겹침   2-gram 겹침
    우리 원과 친구           75            1            66
    우리 동네               51           31            42
    여름                   65           51            59
    교통기관                51           43            43
    성장한 우리             33            0            17

`성장한 우리`가 공백 토큰으로 **0건**인 것이 결정적이다. `우리`는 흔해서 stopword로
빠지고 `성장한`은 활동명에 그대로 나오지 않는다. 그래서 2-gram을 쓴다.

대신 **동의어 사전을 만들지 않는다.** `교통기관 → 자동차/버스/탈것` 같은 전국 표준
ontology는 근거가 없고(CLAUDE.md §8) 유지 비용도 크다. 2-gram이 놓치는 것은
L3/L4의 LLM이 Context 안에서 판단한다.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Iterable, Sequence

from ...ingestion.models import EvidenceRecord
from .models import AGE_TIER_ORDER, AgeMatchKind, RetrievalTrace, RetrievedEvidence

__all__ = [
    "DEFAULT_INSTITUTION_CAP",
    "TEMPLATE_FAMILY",
    "age_match_kind",
    "apply_source_diversity",
    "balance_by_single_age",
    "diversity_group",
    "ngrams",
    "rank_records",
    "theme_signals",
]

TEMPLATE_FAMILY = frozenset(
    {"마성어린이집", "우리어린이집", "키즈로스쿨어린이집", "혜솔어린이집"}
)
"""2026-09-12 Corpus 재분석에서 확인된 Template Family.

본문 6-gram Jaccard 0.848까지 겹치므로 **한 Source로 묶어 센다.** L1 ingestion과
같은 집합이다.
"""

DEFAULT_INSTITUTION_CAP = 2
"""Block당 기관 상한.

만4세 일부 월의 Evidence가 부산광역시청어린이집 한 곳에 몰려 있다
(`docs/analysis/new-reference-evidence-impact-2026-09.md` §9). 상한이 없으면
한 기관의 문체가 Block을 독점한다.
"""

_HANGUL_ONLY = re.compile(r"[^가-힣]")


def ngrams(text: str | None, n: int = 2) -> frozenset[str]:
    """한글만 남긴 뒤 n-gram. 공백·구두점 표기 흔들림을 흡수한다.

    `우리 동네`와 `우리동네`가 같은 gram을 만든다.
    """
    s = _HANGUL_ONLY.sub("", text or "")
    if len(s) < n:
        return frozenset({s} if s else ())
    return frozenset(s[i : i + n] for i in range(len(s) - n + 1))


def theme_signals(
    record: EvidenceRecord, theme_grams: frozenset[str]
) -> tuple[bool, int]:
    """(그 면의 주제가 확정 Theme과 겹치는가, 본문 겹침 수).

    두 신호를 **합치지 않는다.** 뜻이 다르기 때문이다.

    - 면 주제 일치 = "이 Record는 같은 주제를 다룬 달의 계획안에서 나왔다"
    - 본문 겹침   = "이 활동명 자체가 Theme 어휘를 포함한다"

    합치면 `과학자가 되어 곤충 식물 관찰하기`(면 주제만 일치)가 `우리 동네 지도 보며
    산책하기`(둘 다 일치)와 같은 점수가 된다.
    """
    page_match = bool(ngrams(record.monthly_theme) & theme_grams)
    text_overlap = len(ngrams(record.text) & theme_grams)
    return page_match, text_overlap


def age_match_kind(
    record: EvidenceRecord, requested: Sequence[int]
) -> AgeMatchKind | None:
    """요청 연령과 Record 연령 근거의 관계. 맞지 않으면 None."""
    req = set(requested)
    scope = set(record.age_scope)

    if record.single_age is not None and record.single_age in req:
        return (
            AgeMatchKind.SINGLE_AGE_EXACT
            if len(req) == 1
            else AgeMatchKind.SINGLE_AGE_IN_REQUEST
        )
    if scope & req:
        return AgeMatchKind.MIXED_AGE_COVERING
    if not scope:
        return AgeMatchKind.AGE_UNKNOWN
    return None


def diversity_group(record: EvidenceRecord) -> str:
    """Source Diversity를 셀 때 쓰는 묶음 키."""
    inst = record.institution_id or "(기관 미상)"
    return "TEMPLATE_FAMILY" if inst in TEMPLATE_FAMILY else inst


def rank_records(
    records: Iterable[EvidenceRecord],
    *,
    requested_ages: Sequence[int],
    theme_grams: frozenset[str],
    allowed_tiers: Sequence[AgeMatchKind] = AGE_TIER_ORDER,
) -> list[RetrievedEvidence]:
    """결정론적 정렬.

    정렬 키는 `(연령 tier, -면주제일치, -본문겹침, record_id)`다.
    동률은 `record_id`로 갈린다 — 원문 좌표에서 나온 값이라 안정적이다.
    """
    tier_rank = {t: i for i, t in enumerate(AGE_TIER_ORDER)}
    allowed = set(allowed_tiers)
    out: list[RetrievedEvidence] = []

    for record in records:
        kind = age_match_kind(record, requested_ages)
        if kind is None or kind not in allowed:
            continue
        page_match, overlap = theme_signals(record, theme_grams)
        # rank_score는 설명용 단일 지표다. 정렬은 아래 key가 한다.
        score = (len(AGE_TIER_ORDER) - tier_rank[kind]) * 100
        score += 10 if page_match else 0
        score += min(overlap, 9)
        out.append(
            RetrievedEvidence(
                record=record,
                trace=RetrievalTrace(
                    retrieval_tier=kind,
                    rank_score=score,
                    theme_page_match=page_match,
                    text_overlap=overlap,
                    source_diversity_group=diversity_group(record),
                ),
            )
        )

    out.sort(
        key=lambda e: (
            tier_rank[e.trace.retrieval_tier],
            0 if e.trace.theme_page_match else 1,
            -e.trace.text_overlap,
            e.record_id,
        )
    )
    return out


def balance_by_single_age(
    ranked: Sequence[RetrievedEvidence], requested_ages: Sequence[int]
) -> list[RetrievedEvidence]:
    """혼합 요청에서 한 연령이 Block을 독점하지 않게 한다.

    `[4, 5]` 요청에서 만4세 근거가 record_id 순으로 앞서면 Top-K가 전부 만4세로
    채워진다. 연령별 상대 순서는 그대로 두고 **round-robin으로 번갈아** 낸다.

    단일 연령 요청이면 아무것도 하지 않는다. 연령 근거가 없는 Record와 혼합연령
    Record는 균형 대상이 아니므로 뒤에 원래 순서대로 붙인다.
    """
    if len(set(requested_ages)) < 2:
        return list(ranked)

    per_age: dict[int, list[RetrievedEvidence]] = {a: [] for a in sorted(set(requested_ages))}
    rest: list[RetrievedEvidence] = []
    for item in ranked:
        age = item.record.single_age
        if age in per_age:
            per_age[age].append(item)
        else:
            rest.append(item)

    out: list[RetrievedEvidence] = []
    queues = [per_age[a] for a in sorted(per_age)]
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    out.extend(rest)
    return out


def apply_source_diversity(
    ranked: Sequence[RetrievedEvidence],
    *,
    top_k: int,
    institution_cap: int = DEFAULT_INSTITUTION_CAP,
) -> tuple[RetrievedEvidence, ...]:
    """관련도 순서를 유지하면서 기관 상한을 적용한다.

    순서가 중요하다. `Top-K 먼저 → 중복 제거`로 하면 결과 수가 모자란다.

        eligible → relevance ranking → diversity selection → Top-K

    상한 때문에 Top-K를 못 채우면 **상한을 넘긴 것을 억지로 채우지 않고** 그대로
    적은 수를 돌려준다. 근거가 한 기관에 몰려 있다는 사실 자체가 정보다.
    """
    if top_k <= 0:
        return ()
    used: collections.Counter[str] = collections.Counter()
    picked: list[RetrievedEvidence] = []
    for item in ranked:
        group = item.trace.source_diversity_group
        if used[group] >= institution_cap:
            continue
        used[group] += 1
        picked.append(item)
        if len(picked) >= top_k:
            break
    return tuple(picked)
