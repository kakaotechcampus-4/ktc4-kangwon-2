"""Monthly Context Packet 조립 (L3).

    Planning Request + 확정 Theme + canonical Week + L2 Retrieval Result
      → 연령 근거 통계
      → Block 간 중복 제거
      → 출처 익명화
      → Budget
      → MonthlyContextPacket

**Activity를 만들지 않는다.** L3는 근거를 배열할 뿐이고, 근거가 부족하면 부족한
채로 넘긴다. 빈 Block을 `"근거 없음"` 같은 문자열로 채우지 않는다.
"""

from __future__ import annotations

import collections
from collections.abc import Sequence
from dataclasses import dataclass

from ...ingestion.models import EvidenceRecord
from ..domain.activity_reference import ActivityCatalog
from ..domain.identifiers import PeriodKey
from ..domain.parent_lineage import ParentYearlyLineage
from ..retrieval.evidence_repository import EXPECTED_STORE_ID, InstitutionEvidenceStore
from ..retrieval.models import (
    BlockName,
    MonthlyEvidenceRetrievalResult,
    RetrievalRequest,
    RetrievedEvidence,
)
from ..retrieval.retriever import MonthlyEvidenceRetriever
from ..rules import monthly_activity_selection as rule_v2
from ..rules.monthly_week_periods import (
    POLICY_NAME as WEEK_POLICY_NAME,
)
from ..rules.monthly_week_periods import (
    RULE_VERSION as WEEK_POLICY_VERSION,
)
from ..rules.monthly_week_periods import canonical_week_periods
from .budget import DEFAULT_CHAR_BUDGET, trim_to_budget
from .models import (
    PACKET_VERSION,
    RETRIEVAL_CONTRACT_VERSION,
    ActivityOrigin,
    AgeContext,
    AgeContrastGroup,
    AgeContrastObservation,
    AgeEvidenceStrength,
    AgeEvidenceSummary,
    EvidenceAudit,
    EvidenceItem,
    MonthlyContextPacket,
    ParentThemeContext,
    PlannerConstraints,
    PlanningRequestContext,
    ReferenceActivityCandidate,
    SafetyContext,
    SourceLineage,
    WeekExperienceCandidate,
    WeekSlot,
)

__all__ = [
    "AGE_CRITERIA_ID",
    "BLOCK_DEDUP_PRIORITY",
    "SAFETY_REQUIRED_SOURCE_KINDS",
    "MonthlyContextPacketBuilder",
    "MonthlyContextRequest",
    "age_evidence_summary",
]

AGE_CRITERIA_ID = "new-reference-evidence-impact-2026-09#4.1"
"""연령 근거 강도 기준의 출처.

Packet 안에 남겨 둔다. 나중에 누가 값을 보고 "이 등급은 어디서 왔나"를 물을 때
답이 Packet 자체에 있어야 한다.
"""

BLOCK_DEDUP_PRIORITY: tuple[BlockName, ...] = (
    BlockName.AGE_CONTRAST_EVIDENCE,
    BlockName.INSTITUTION_MONTHLY_EVIDENCE,
    BlockName.OTHER_OUTDOOR_EVIDENCE,
)
"""같은 record가 두 Block에 들어갈 때 어느 쪽을 남기는가.

Age Contrast가 가장 앞인 이유: 같은 record라도 대조 Group 안에서는 **어느
연령의 면에서 나왔는지**까지 함께 보인다. 정보가 더 많은 쪽을 남기고 평탄한
목록에서 뺀다. Token도 절약된다.

Week Experience는 section이 달라 이 Block들과 겹치지 않는다.
L2가 이미 Institution ∩ Other Outdoor를 제거한다(`used_ids`).
"""

SAFETY_REQUIRED_SOURCE_KINDS = ("INSTITUTION_ANNUAL_SAFETY_PLAN", "TEACHER_INPUT")
"""`generate_monthly_plan.SAFETY_SOURCE_KINDS`와 같은 값.

Rule/Use Case를 import하면 L3가 Generate에 의존하게 되므로 값을 복제하고
테스트로 두 상수의 일치를 고정한다.
"""

SAFETY_DETAIL = (
    "안전교육 배치 source가 없어 값을 생성하지 않는다. "
    "LLM Planner는 안전교육 내용을 제안하지 않는다."
)


@dataclass(frozen=True, slots=True)
class MonthlyContextRequest:
    """L3 입력. Retrieval Request보다 넓다 — 학년도·반 식별자를 포함한다."""

    school_year: str
    target_month: PeriodKey
    classroom_ages: tuple[int, ...]
    age_mode: str
    parent_lineage: ParentYearlyLineage
    daycare_ref: str | None = None
    classroom_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.school_year.strip():
            raise ValueError("school_year는 비어 있을 수 없다")
        if not self.classroom_ages:
            raise ValueError("classroom_ages가 비어 있다")
        for a in self.classroom_ages:
            if not 3 <= a <= 5:
                raise ValueError(f"P0 Target은 만3~5세다: {self.classroom_ages}")
        if not self.age_mode.strip():
            raise ValueError("age_mode는 비어 있을 수 없다")


# ------------------------------------------------------------------ 연령 통계


def age_evidence_summary(
    store: InstitutionEvidenceStore, *, calendar_month: int, age: int
) -> AgeEvidenceSummary:
    """`new-reference-evidence-impact-2026-09.md` §4.1 기준을 **그대로** 적용한다.

    임계값도 신호 정의도 바꾸지 않았다. 달라진 것은 세는 대상뿐이다 — 재감사는
    inventory의 면 metadata를 셌고, 여기서는 L1 Evidence Store의 실제 추출
    record를 센다. Runtime이 가진 것이 Evidence Store뿐이기 때문이다.
    따라서 같은 달·연령이라도 등급이 재감사표보다 보수적으로 나올 수 있다.
    """
    single_inst: set[str] = set()
    mixed_inst: set[str] = set()
    any_inst: set[str] = set()
    outdoor_pages: set[tuple[str, int]] = set()

    for r in store.by_month(calendar_month):
        if not r.general_grounding_eligible or age not in r.age_scope:
            continue
        inst = r.institution_id or "(기관 미상)"
        any_inst.add(inst)
        if r.single_age == age:
            single_inst.add(inst)
            if r.outdoor_activity_eligible:
                outdoor_pages.add((r.source_sha256, r.page))
        else:
            mixed_inst.add(inst)

    dan, ba = len(single_inst), len(outdoor_pages)
    if dan >= 3:
        strength = AgeEvidenceStrength.STRONG
    elif dan == 2:
        strength = AgeEvidenceStrength.MODERATE
    elif dan == 1:
        strength = (
            AgeEvidenceStrength.MODERATE if ba > 0 else AgeEvidenceStrength.WEAK
        )
    elif len(mixed_inst) >= 3:
        strength = AgeEvidenceStrength.WEAK
    else:
        strength = AgeEvidenceStrength.VERY_WEAK

    return AgeEvidenceSummary(
        age=age,
        single_age_institution_count=dan,
        age_mentioning_institution_count=len(any_inst),
        single_age_outdoor_page_count=ba,
        strength=strength,
    )


def _count_single_age(
    flat_items: Sequence[EvidenceItem],
    contrast: Sequence[AgeContrastGroup],
    requested: set[int],
) -> int:
    """요청 연령의 **단일연령 면**에서 온 근거가 Packet에 몇 건인가.

    `age_match_kind`로 세지 않는다. 대조 Block의 tier는 문서 안의 연령 기준으로
    매겨지므로 요청 기준이 아니다. `age_scope`를 직접 보는 편이 모호하지 않다.
    """

    def is_single(item: EvidenceItem) -> bool:
        return len(item.age_scope) == 1 and item.age_scope[0] in requested

    total = sum(1 for i in flat_items if is_single(i))
    total += sum(
        1
        for g in contrast
        for o in g.observations
        for i in o.items
        if is_single(i)
    )
    return total


_STRENGTH_ORDER = (
    AgeEvidenceStrength.VERY_WEAK,
    AgeEvidenceStrength.WEAK,
    AgeEvidenceStrength.MODERATE,
    AgeEvidenceStrength.STRONG,
)


# ------------------------------------------------------------------ 익명화


class _Refs:
    """`E01`, `E02`… 를 등장 순서대로 붙인다.

    같은 record가 두 번 나오면 같은 ref를 준다 — 중복 제거가 있어도 안전하다.
    """

    def __init__(self) -> None:
        self._refs: dict[str, str] = {}

    def of(self, record_id: str) -> str:
        if record_id not in self._refs:
            self._refs[record_id] = f"E{len(self._refs) + 1:02d}"
        return self._refs[record_id]


class _SourceGroups:
    """`institution_id` → `S1`, `S2`… 를 **등장 순서대로** 붙인다.

    Planner에게 필요한 것은 "다른 곳에서 나왔다"는 사실이지 기관 이름이 아니다.
    등장 순서가 결정론적이므로 라벨도 결정론적이다.
    """

    def __init__(self) -> None:
        self._labels: dict[str, str] = {}

    def label(self, record: EvidenceRecord) -> str:
        key = record.institution_id or "(기관 미상)"
        if key not in self._labels:
            self._labels[key] = f"S{len(self._labels) + 1}"
        return self._labels[key]

    @property
    def count(self) -> int:
        return len(self._labels)


# ------------------------------------------------------------------ Builder


class MonthlyContextPacketBuilder:
    """L2 결과를 Packet으로 조립한다.

    Retrieval을 다시 정의하지 않는다. `store`를 함께 받는 이유는 연령 근거 강도가
    Top-K가 아니라 **그 달 Corpus 전체**에 대한 통계이기 때문이다.
    """

    def __init__(
        self,
        retriever: MonthlyEvidenceRetriever,
        store: InstitutionEvidenceStore,
        *,
        activity_catalog: ActivityCatalog | None = None,
        char_budget: int = DEFAULT_CHAR_BUDGET,
    ) -> None:
        self._retriever = retriever
        self._store = store
        self._catalog = activity_catalog
        self._budget = char_budget

    # -------------------------------------------------------------- 진입점

    def build(self, req: MonthlyContextRequest) -> MonthlyContextPacket:
        weeks = canonical_week_periods(req.target_month)
        retrieval = self._retriever.retrieve(
            RetrievalRequest(
                target_month=req.target_month.value,
                calendar_month=req.target_month.calendar_month,
                ages=tuple(req.classroom_ages),
                age_mode=req.age_mode,
                confirmed_theme_id=req.parent_lineage.parent_yearly_theme_id,
                confirmed_theme_value=req.parent_lineage.parent_yearly_value,
                week_count=len(weeks),
            )
        )
        return self.assemble(req, retrieval)

    def assemble(
        self, req: MonthlyContextRequest, retrieval: MonthlyEvidenceRetrievalResult
    ) -> MonthlyContextPacket:
        """Retrieval 결과가 주어졌을 때의 순수 조립. 같은 입력 → 같은 Packet."""
        weeks = canonical_week_periods(req.target_month)
        groups = _SourceGroups()
        refs = _Refs()

        contrast = self._contrast_groups(retrieval, groups, refs)
        used = {
            i.evidence_id for g in contrast for o in g.observations for i in o.items
        }

        institution, used = self._evidence_items(
            retrieval.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items,
            groups,
            refs,
            used,
        )
        week_candidates = self._week_candidates(
            retrieval.blocks[BlockName.WEEK_EXPERIENCE_CANDIDATES].items,
            groups,
            refs,
        )
        other, _ = self._evidence_items(
            retrieval.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE].items,
            groups,
            refs,
            used,
        )

        packet = MonthlyContextPacket(
            packet_version=PACKET_VERSION,
            planning_request=PlanningRequestContext(
                school_year=req.school_year,
                target_month=req.target_month.value,
                calendar_month=req.target_month.calendar_month,
                classroom_ages=tuple(req.classroom_ages),
                age_mode=req.age_mode,
                daycare_ref=req.daycare_ref,
                classroom_ref=req.classroom_ref,
            ),
            parent_theme=ParentThemeContext(
                theme_id=req.parent_lineage.parent_yearly_theme_id,
                theme_value=req.parent_lineage.parent_yearly_value,
                parent_yearly_plan_id=req.parent_lineage.parent_yearly_plan_id,
                parent_yearly_period_key=req.parent_lineage.parent_yearly_period_key,
                reference_catalog_id=req.parent_lineage.reference_catalog_id,
                reference_version=req.parent_lineage.reference_version,
                confirmed_at=req.parent_lineage.confirmed_at,
            ),
            week_slots=tuple(
                WeekSlot(
                    week_id=p.week_id.value,
                    display_label=p.display_label,
                    display_order=p.week_id.ordinal,
                    start_date=p.start_date,
                    end_date=p.end_date,
                    active=p.active,
                )
                for p in weeks
            ),
            age_context=self._age_context(
                req, contrast, institution + other
            ),
            institution_evidence=institution,
            age_contrast_evidence=contrast,
            week_experience_candidates=week_candidates,
            reference_activities=self._reference_activities(retrieval),
            other_outdoor_evidence=other,
            official_play_context=(),
            official_topic_context=(),
            safety_context=self._safety_context(),
            constraints=self._constraints(weeks),
            source_lineage=self._lineage(req, retrieval),
        )
        return trim_to_budget(packet, char_budget=self._budget)

    # -------------------------------------------------------------- Block

    @staticmethod
    def _audit(e: RetrievedEvidence) -> EvidenceAudit:
        r = e.record
        return EvidenceAudit(
            record_id=r.record_id,
            source_path=r.source_path,
            source_sha256=r.source_sha256,
            page=r.page,
            institution_id=r.institution_id,
            source_diversity_group=e.trace.source_diversity_group,
            retrieval_tier=e.trace.retrieval_tier,
            rank_score=e.trace.rank_score,
            theme_page_match=e.trace.theme_page_match,
            text_overlap=e.trace.text_overlap,
            extraction_quality=r.extraction_quality.value,
            machine_readability=r.machine_readability.value,
        )

    def _item(
        self, e: RetrievedEvidence, groups: _SourceGroups, refs: _Refs
    ) -> EvidenceItem:
        r = e.record
        return EvidenceItem(
            ref=refs.of(r.record_id),
            evidence_id=r.record_id,
            text=r.text or "",
            month=r.month,
            age_scope=r.age_scope,
            source_group=groups.label(r),
            source_section=r.source_section.value,
            source_label=r.source_label,
            monthly_theme=r.monthly_theme,
            reuse_policy=r.reuse_policy,
            age_match_kind=e.trace.retrieval_tier,
            audit=self._audit(e),
        )

    def _evidence_items(
        self,
        items: Sequence[RetrievedEvidence],
        groups: _SourceGroups,
        refs: _Refs,
        used: set[str],
    ) -> tuple[tuple[EvidenceItem, ...], set[str]]:
        """우선순위가 높은 Block에 이미 있는 record는 넣지 않는다(§28)."""
        out: list[EvidenceItem] = []
        seen = set(used)
        for e in items:
            if e.record_id in seen:
                continue
            seen.add(e.record_id)
            out.append(self._item(e, groups, refs))
        return tuple(out), seen

    def _contrast_groups(
        self,
        retrieval: MonthlyEvidenceRetrievalResult,
        groups: _SourceGroups,
        refs: _Refs,
    ) -> tuple[AgeContrastGroup, ...]:
        """같은 문서·같은 월의 연령 대조를 **Group 관계로** 묶는다.

        L2가 고른 record만 쓴다. **없는 대조쌍을 추론해서 만들지 않는다** —
        한 연령만 남은 문서는 대조가 아니므로 통째로 제외한다.
        """
        by_source: dict[str, list[RetrievedEvidence]] = collections.defaultdict(list)
        for e in retrieval.blocks[BlockName.AGE_CONTRAST_EVIDENCE].items:
            by_source[e.record.source_sha256].append(e)

        out: list[AgeContrastGroup] = []
        for sha in sorted(by_source):
            rows = by_source[sha]
            ages = sorted({e.record.single_age for e in rows if e.record.single_age})
            if len(ages) < 2:
                continue
            head = rows[0].record
            out.append(
                AgeContrastGroup(
                    group_id=f"contrast_{sha[:12]}",
                    source_group=groups.label(head),
                    month=head.month,
                    monthly_theme=head.monthly_theme,
                    observations=tuple(
                        AgeContrastObservation(
                            age=age,
                            items=tuple(
                                self._item(e, groups, refs)
                                for e in rows
                                if e.record.single_age == age
                            ),
                        )
                        for age in ages
                    ),
                    source_sha256=sha,
                    source_path=head.source_path,
                )
            )
        return tuple(out)

    def _week_candidates(
        self,
        items: Sequence[RetrievedEvidence],
        groups: _SourceGroups,
        refs: _Refs,
    ) -> tuple[WeekExperienceCandidate, ...]:
        return tuple(
            WeekExperienceCandidate(
                ref=refs.of(e.record.record_id),
                evidence_id=e.record.record_id,
                text=e.record.text or "",
                age_scope=e.record.age_scope,
                source_group=groups.label(e.record),
                source_label=e.record.source_label,
                monthly_theme=e.record.monthly_theme,
                reuse_policy=e.record.reuse_policy,
                audit=self._audit(e),
            )
            for e in items
        )

    def _reference_activities(
        self, retrieval: MonthlyEvidenceRetrievalResult
    ) -> tuple[ReferenceActivityCandidate, ...]:
        block = retrieval.blocks[BlockName.REFERENCE_ACTIVITIES]
        out: list[ReferenceActivityCandidate] = []
        for c in block.reference_items:
            activity = self._catalog.get(c.activity_id) if self._catalog else None
            out.append(
                ReferenceActivityCandidate(
                    activity_id=c.activity_id,
                    label=c.label,
                    supported_ages=(
                        activity.supported_ages if activity is not None else ()
                    ),
                    theme_link_ids=(
                        tuple(sorted({t.theme_id for t in activity.theme_links}))
                        if activity is not None
                        else ()
                    ),
                    evidence_strength=c.evidence_strength,
                    has_display_quality_issue=c.has_display_quality_issue,
                    rank=c.rank,
                )
            )
        return tuple(out)

    # -------------------------------------------------------------- 나머지

    def _age_context(
        self,
        req: MonthlyContextRequest,
        contrast: tuple[AgeContrastGroup, ...],
        flat_items: tuple[EvidenceItem, ...],
    ) -> AgeContext:
        per_age = tuple(
            age_evidence_summary(
                self._store,
                calendar_month=req.target_month.calendar_month,
                age=age,
            )
            for age in sorted(set(req.classroom_ages))
        )
        overall = min(per_age, key=lambda s: _STRENGTH_ORDER.index(s.strength))
        return AgeContext(
            requested_ages=tuple(sorted(set(req.classroom_ages))),
            per_age=per_age,
            overall_strength=overall.strength,
            single_age_grounding_count=_count_single_age(
                flat_items, contrast, set(req.classroom_ages)
            ),
            age_contrast_count=sum(g.size for g in contrast),
            age_contrast_document_count=len(contrast),
            criteria_id=AGE_CRITERIA_ID,
        )

    @staticmethod
    def _safety_context() -> SafetyContext:
        """안전교육 **내용 후보를 Context에 넣지 않는다.**

        현재 Production Generate가 내리는 판정과 같은 상태를 그대로 전달한다
        (`NOT_VERIFIED_SOURCE_REQUIRED` / `EMPTY_UNRESOLVED`).
        """
        return SafetyContext(
            safety_generation_allowed=False,
            verification="NOT_VERIFIED_SOURCE_REQUIRED",
            cell_state="EMPTY_UNRESOLVED",
            required_source_kinds=SAFETY_REQUIRED_SOURCE_KINDS,
            rule_version="safety-education-legal-v1",
            detail=SAFETY_DETAIL,
        )

    @staticmethod
    def _constraints(weeks) -> PlannerConstraints:
        return PlannerConstraints(
            expected_week_ids=tuple(p.week_id.value for p in weeks),
            expected_week_count=len(weeks),
            theme_locked=True,
            safety_generation_allowed=False,
            duplicate_activity_allowed=False,
            official_claim_allowed=False,
            source_text_copy_allowed=False,
            corpus_direct_output_enabled=False,
            allowed_activity_origins=(
                ActivityOrigin.REFERENCE,
                ActivityOrigin.LLM_SYNTHESIZED,
            ),
            activity_origin_priority=(
                ActivityOrigin.REFERENCE,
                ActivityOrigin.CORPUS_EVIDENCE,
                ActivityOrigin.LLM_SYNTHESIZED,
            ),
        )

    def _lineage(
        self, req: MonthlyContextRequest, retrieval: MonthlyEvidenceRetrievalResult
    ) -> SourceLineage:
        return SourceLineage(
            packet_version=PACKET_VERSION,
            retrieval_version=RETRIEVAL_CONTRACT_VERSION,
            evidence_store_id=EXPECTED_STORE_ID,
            evidence_store_schema_version=self._store.schema_version,
            evidence_store_ingestion_version=retrieval.evidence_store_version,
            evidence_store_content_sha256=retrieval.evidence_store_sha256,
            activity_catalog_id=retrieval.activity_catalog_id,
            activity_catalog_version=retrieval.activity_catalog_version,
            theme_reference_catalog_id=req.parent_lineage.reference_catalog_id,
            theme_reference_version=req.parent_lineage.reference_version,
            week_policy_name=WEEK_POLICY_NAME,
            week_policy_version=WEEK_POLICY_VERSION,
            selection_rule_version=rule_v2.RULE_VERSION,
        )
