"""Monthly Evidence Retriever (L2).

Planning Request 하나에 대해 성격이 다른 Block을 각각 뽑는다.

    eligibility(L1 파생) → 연령 tier → theme relevance → source diversity → Top-K

LLM · Embedding · Vector DB를 쓰지 않는다. 12,367 record 규모에서 in-memory로
충분하다는 것은 실측으로 확인했다(store load 0.09s).
"""

from __future__ import annotations

import collections
from collections.abc import Sequence

from ...ingestion.models import EvidenceRecord, SourceSection
from ..domain.activity_reference import ActivityCatalog
from ..rules import monthly_activity_selection as rule_v2
from ..rules.monthly_cell_state import OUTDOOR_SECTION_KEY
from .evidence_repository import InstitutionEvidenceStore
from .models import (
    AgeMatchKind,
    BlockName,
    EvidenceBlock,
    MonthlyEvidenceRetrievalResult,
    ReferenceCandidate,
    RetrievalRequest,
)
from .ranking import (
    DEFAULT_INSTITUTION_CAP,
    apply_source_diversity,
    balance_by_single_age,
    ngrams,
    rank_records,
)

__all__ = [
    "DEFAULT_TOP_K",
    "MonthlyEvidenceRetriever",
    "OfficialEvidencePort",
]

DEFAULT_TOP_K: dict[BlockName, int] = {
    BlockName.INSTITUTION_MONTHLY_EVIDENCE: 12,
    BlockName.AGE_CONTRAST_EVIDENCE: 6,
    BlockName.WEEK_EXPERIENCE_CANDIDATES: 10,
    BlockName.REFERENCE_ACTIVITIES: 12,
    BlockName.OTHER_OUTDOOR_EVIDENCE: 10,
}

_INSTITUTION_SECTIONS = (SourceSection.OUTDOOR_PLAY,)
"""Institution Block은 **바깥놀이 활동 근거**만 담는다.

week_experience를 여기 섞으면 두 가지가 나빠진다. ① Week Experience Block과
내용이 겹쳐 L3의 Token Budget이 낭비된다. ② week_experience 문장이 Theme 어휘를
더 많이 포함해 ranking 상위를 차지하고, 정작 활동 근거가 Top-K 밖으로 밀린다
(2026-06 만4세에서 실제로 관찰했다).
"""

_DEFAULT_TIERS = (
    AgeMatchKind.SINGLE_AGE_EXACT,
    AgeMatchKind.SINGLE_AGE_IN_REQUEST,
    AgeMatchKind.MIXED_AGE_COVERING,
)
"""`AGE_UNKNOWN`은 기본적으로 쓰지 않는다.

실측에서 exact/mixed만으로 다섯 Case 모두 Top-K가 채워졌다. 연령 근거가 없는
Record를 연령 Grounding에 섞을 이유가 없다.
"""


class OfficialEvidencePort:
    """Official Evidence 조회 경계 (L2에서는 인터페이스만 둔다).

    L1은 `INSTITUTION_SAMPLE`만 Production Evidence Store로 만들었다. 보고서·지도서
    레이아웃은 월간계획안 표 기하와 다르고, case 단위 연령 추출은 별도 Adapter가
    적합하다.

    **Raw Official PDF를 runtime에 파싱하지 않는다.** 구현체는 L3/L4 전에 별도
    Adapter 단계에서 붙인다. 그때까지 Retriever는 이 Port를 주입받지 않으며,
    Official Block을 비운 채로 동작한다.
    """

    def official_play_cases(
        self, *, ages: Sequence[int], theme_value: str, top_k: int
    ) -> tuple:
        """연령·주제에 맞는 Official Play Case. 미구현이면 빈 tuple."""
        raise NotImplementedError


class MonthlyEvidenceRetriever:
    """Evidence Store + 승인 Activity Catalog에서 Block을 뽑는다."""

    def __init__(
        self,
        store: InstitutionEvidenceStore,
        *,
        activity_catalog: ActivityCatalog | None = None,
        institution_cap: int = DEFAULT_INSTITUTION_CAP,
        top_k: dict[BlockName, int] | None = None,
    ) -> None:
        self._store = store
        self._catalog = activity_catalog
        self._cap = institution_cap
        self._top_k = dict(DEFAULT_TOP_K)
        if top_k:
            self._top_k.update(top_k)
        self._contrast_sources = self._find_contrast_sources(store)

    # ------------------------------------------------------------ 준비

    @staticmethod
    def _find_contrast_sources(store: InstitutionEvidenceStore) -> frozenset[str]:
        """한 문서 안에 서로 다른 단일연령 면이 있는 Source.

        기관 차이·양식 차이에 오염되지 않은 **순수 연령 대조**가 가능한 문서다.
        """
        ages_by_source: dict[str, set[int]] = collections.defaultdict(set)
        for r in store.records:
            if r.single_age is not None:
                ages_by_source[r.source_sha256].add(r.single_age)
        return frozenset(k for k, v in ages_by_source.items() if len(v) >= 2)

    # ------------------------------------------------------------ Block

    def _institution_monthly_evidence(
        self, req: RetrievalRequest, theme_grams: frozenset[str]
    ) -> EvidenceBlock:
        pool = [
            r
            for r in self._store.by_month(req.calendar_month)
            if r.source_section in _INSTITUTION_SECTIONS
            and r.outdoor_activity_eligible
        ]
        ranked = rank_records(
            pool,
            requested_ages=req.ages,
            theme_grams=theme_grams,
            allowed_tiers=_DEFAULT_TIERS,
        )
        ranked = balance_by_single_age(ranked, req.ages)
        k = self._top_k[BlockName.INSTITUTION_MONTHLY_EVIDENCE]
        return EvidenceBlock(
            name=BlockName.INSTITUTION_MONTHLY_EVIDENCE,
            top_k=k,
            retrieval_reason=(
                "month hard filter + grounding eligibility + 연령 tier "
                "(단일연령 exact → 단일연령 in request → 혼합 포함) + theme relevance "
                f"+ 혼합 요청이면 연령 round-robin + 기관당 {self._cap}건 상한"
            ),
            items=apply_source_diversity(
                ranked, top_k=k, institution_cap=self._cap
            ),
            eligible_pool_size=len(ranked),
            note="outdoor_play + outdoor_activity_eligible만. week_experience는 별도 Block",
        )

    def _age_contrast_evidence(
        self, req: RetrievalRequest, theme_grams: frozenset[str]
    ) -> EvidenceBlock:
        """같은 문서·같은 월에 서로 다른 단일연령 면이 있을 때만.

        **없는 대조쌍을 추론해서 만들지 않는다.** 없으면 빈 Block이다.
        """
        pool = [
            r
            for r in self._store.by_month(req.calendar_month)
            if r.source_sha256 in self._contrast_sources
            and r.outdoor_activity_eligible
            and r.single_age is not None
        ]
        by_source: dict[str, list[EvidenceRecord]] = collections.defaultdict(list)
        for r in pool:
            by_source[r.source_sha256].append(r)

        # 요청 연령이 실제로 대조에 참여하는 문서만 쓴다.
        requested = set(req.ages)
        usable: list[EvidenceRecord] = []
        for sha in sorted(by_source):
            rows = by_source[sha]
            ages = {r.single_age for r in rows}
            if len(ages) < 2 or not (ages & requested):
                continue
            usable.extend(rows)

        ranked = rank_records(
            usable,
            requested_ages=sorted({a for r in usable for a in (r.single_age,)}) or
            list(req.ages),
            theme_grams=theme_grams,
            allowed_tiers=(
                AgeMatchKind.SINGLE_AGE_EXACT,
                AgeMatchKind.SINGLE_AGE_IN_REQUEST,
            ),
        )
        k = self._top_k[BlockName.AGE_CONTRAST_EVIDENCE]
        # 대조 자체가 같은 기관 안에서 의미를 가지므로 상한을 하나 늘린다.
        return EvidenceBlock(
            name=BlockName.AGE_CONTRAST_EVIDENCE,
            top_k=k,
            retrieval_reason=(
                "같은 문서·같은 월에 서로 다른 단일연령 면이 있는 Source만. "
                f"기관당 {self._cap + 1}건 상한 (대조는 같은 기관 안에서 의미를 갖는다)"
            ),
            items=apply_source_diversity(
                ranked, top_k=k, institution_cap=self._cap + 1
            ),
            eligible_pool_size=len(ranked),
            note=f"대조 가능 문서 {len(by_source)}건",
        )

    def _week_experience_candidates(
        self, req: RetrievalRequest, theme_grams: frozenset[str]
    ) -> EvidenceBlock:
        """**주차 index를 붙이지 않는다.**

        Corpus에 주차 순서 근거가 없다(L1 실측: `week_position` 보유 0건).
        이 Block의 의미는 "이 달에 관찰된 경험 후보"이지 W1/W2/W3가 아니다.
        """
        pool = [
            r
            for r in self._store.by_month(req.calendar_month)
            if r.general_grounding_eligible
            and r.source_section is SourceSection.WEEK_EXPERIENCE
        ]
        ranked = rank_records(
            pool,
            requested_ages=req.ages,
            theme_grams=theme_grams,
            allowed_tiers=AGE_TIERS_WITH_UNKNOWN,
        )
        ranked = balance_by_single_age(ranked, req.ages)
        k = self._top_k[BlockName.WEEK_EXPERIENCE_CANDIDATES]
        return EvidenceBlock(
            name=BlockName.WEEK_EXPERIENCE_CANDIDATES,
            top_k=k,
            retrieval_reason=(
                "month hard filter + week_experience section + theme relevance "
                f"+ 기관당 {self._cap}건 상한"
            ),
            items=apply_source_diversity(
                ranked, top_k=k, institution_cap=self._cap
            ),
            eligible_pool_size=len(ranked),
            note="주차 번호를 붙이지 않는다 — Corpus에 순서 근거가 없다",
        )

    def _reference_activities(self, req: RetrievalRequest) -> EvidenceBlock:
        """승인 Catalog hard filter + Rule v2 pre-ranking → Top-K.

        **Rule v2의 의미를 바꾸지 않는다.** 최종 Cell 결정 대신 Context 후보
        pre-ranking에 같은 정렬을 재사용할 뿐이다.
        """
        k = self._top_k[BlockName.REFERENCE_ACTIVITIES]
        if self._catalog is None:
            return EvidenceBlock(
                name=BlockName.REFERENCE_ACTIVITIES,
                top_k=k,
                retrieval_reason="Activity Catalog가 주입되지 않았다",
                note="주입되지 않으면 빈 Block이다. 추측으로 채우지 않는다",
            )

        pool = self._catalog.eligible_candidates(
            section_key=OUTDOOR_SECTION_KEY,
            calendar_month=req.calendar_month,
            ages=frozenset(req.ages),
        )
        ordered = sorted(
            pool,
            key=lambda a: rule_v2.context_ranking_sort_key(
                a,
                calendar_month=req.calendar_month,
                parent_theme_id=req.confirmed_theme_id,
            ),
        )
        items = tuple(
            ReferenceCandidate(
                activity_id=a.activity_id,
                label=a.label,
                evidence_strength=a.evidence_strength_for_month(req.calendar_month),
                has_display_quality_issue=a.has_confirmed_display_issue,
                rank=i,
            )
            for i, a in enumerate(ordered[:k])
        )
        return EvidenceBlock(
            name=BlockName.REFERENCE_ACTIVITIES,
            top_k=k,
            retrieval_reason=(
                "ActivityCatalog.eligible_candidates() hard filter "
                f"+ Selection Rule {rule_v2.RULE_VERSION} pre-ranking → Top-K"
            ),
            reference_items=items,
            eligible_pool_size=len(pool),
            note="후보가 K보다 적으면 전부 반환한다. 억지로 채우지 않는다",
        )

    def _other_outdoor_evidence(
        self,
        req: RetrievalRequest,
        theme_grams: frozenset[str],
        used_ids: frozenset[str],
    ) -> EvidenceBlock:
        """Institution Block에 쓰이지 않은 추가 outdoor Grounding.

        Reference candidate scarcity를 보완한다. 전부 `CONTEXT_ONLY`이므로
        **최종 Product 값 후보가 아니다.** `reuse_policy`가 Record에 그대로 남는다.
        """
        pool = [
            r
            for r in self._store.by_month(req.calendar_month)
            if r.outdoor_activity_eligible and r.record_id not in used_ids
        ]
        ranked = rank_records(
            pool,
            requested_ages=req.ages,
            theme_grams=theme_grams,
            allowed_tiers=AGE_TIERS_WITH_UNKNOWN,
        )
        ranked = balance_by_single_age(ranked, req.ages)
        k = self._top_k[BlockName.OTHER_OUTDOOR_EVIDENCE]
        return EvidenceBlock(
            name=BlockName.OTHER_OUTDOOR_EVIDENCE,
            top_k=k,
            retrieval_reason=(
                "month + outdoor_activity_eligible + Institution Block 미사용 "
                f"+ theme relevance + 기관당 {self._cap}건 상한"
            ),
            items=apply_source_diversity(
                ranked, top_k=k, institution_cap=self._cap
            ),
            eligible_pool_size=len(ranked),
            note="전부 reuse_policy=CONTEXT_ONLY다. 최종 Product 값 후보가 아니다",
        )

    # ------------------------------------------------------------ 진입점

    def retrieve(self, req: RetrievalRequest) -> MonthlyEvidenceRetrievalResult:
        theme_grams = ngrams(req.confirmed_theme_value)

        institution = self._institution_monthly_evidence(req, theme_grams)
        contrast = self._age_contrast_evidence(req, theme_grams)
        week = self._week_experience_candidates(req, theme_grams)
        reference = self._reference_activities(req)
        used = frozenset(i.record_id for i in institution.items)
        other = self._other_outdoor_evidence(req, theme_grams, used)

        return MonthlyEvidenceRetrievalResult(
            request=req,
            blocks={
                b.name: b for b in (institution, contrast, week, reference, other)
            },
            evidence_store_version=self._store.ingestion_version,
            evidence_store_sha256=self._store.content_sha256,
            activity_catalog_id=(
                self._catalog.catalog_id if self._catalog else ""
            ),
            activity_catalog_version=(
                self._catalog.catalog_version if self._catalog else ""
            ),
        )


AGE_TIERS_WITH_UNKNOWN = (
    AgeMatchKind.SINGLE_AGE_EXACT,
    AgeMatchKind.SINGLE_AGE_IN_REQUEST,
    AgeMatchKind.MIXED_AGE_COVERING,
    AgeMatchKind.AGE_UNKNOWN,
)
"""Week Experience와 Other Outdoor는 연령 근거가 없는 Record도 허용한다.

그 Block의 목적이 연령 구분이 아니라 **그 달의 경험·활동 범위**이기 때문이다.
연령 신호는 tier 정렬로 여전히 반영되며, 단일연령 Record가 앞에 온다.
"""
