"""Retrieval Request / Result Contract (L2).

L2는 **구조화된 객체**만 돌려준다. Prompt 문자열을 만들지 않는다 — 그것은 L3다.

Block을 나누는 이유: 하나의 통합 Top-N 목록을 주면 L3가 "이 근거가 어떤 성격인가"를
다시 추론해야 한다. 성격이 다른 근거는 Token Budget도 Required 여부도 다르므로
retrieval 단계에서 갈라 둔다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ...ingestion.models import EvidenceRecord

__all__ = [
    "AgeMatchKind",
    "BlockName",
    "EvidenceBlock",
    "MonthlyEvidenceRetrievalResult",
    "ReferenceCandidate",
    "RetrievalRequest",
    "RetrievalTrace",
    "RetrievedEvidence",
]


class AgeMatchKind(str, Enum):
    """요청 연령과 Record 연령 근거의 관계. tier 순서가 곧 우선순위다."""

    SINGLE_AGE_EXACT = "SINGLE_AGE_EXACT"
    """요청이 단일 연령이고 Record도 그 연령의 단일연령 면이다. 가장 강하다."""

    SINGLE_AGE_IN_REQUEST = "SINGLE_AGE_IN_REQUEST"
    """혼합 요청(예: 만4·5세)에 대해 그중 한 연령의 단일연령 면이다."""

    MIXED_AGE_COVERING = "MIXED_AGE_COVERING"
    """Record가 혼합연령 면이고 요청 연령을 포함한다."""

    AGE_UNKNOWN = "AGE_UNKNOWN"
    """Record에 연령 근거가 없다. 기본적으로 쓰지 않는다."""


AGE_TIER_ORDER: tuple[AgeMatchKind, ...] = (
    AgeMatchKind.SINGLE_AGE_EXACT,
    AgeMatchKind.SINGLE_AGE_IN_REQUEST,
    AgeMatchKind.MIXED_AGE_COVERING,
    AgeMatchKind.AGE_UNKNOWN,
)


class BlockName(str, Enum):
    INSTITUTION_MONTHLY_EVIDENCE = "institution_monthly_evidence"
    AGE_CONTRAST_EVIDENCE = "age_contrast_evidence"
    WEEK_EXPERIENCE_CANDIDATES = "week_experience_candidates"
    REFERENCE_ACTIVITIES = "reference_activities"
    OTHER_OUTDOOR_EVIDENCE = "other_outdoor_evidence"


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """Retrieval에 **실제로 필요한 것만** 담는다.

    `school_year` · `daycare_ref` · `classroom_ref`는 Retrieval 결과를 바꾸지
    않으므로 넣지 않는다. 필요해지면 그때 추가한다.
    """

    target_month: str
    """`YYYY-MM`."""

    calendar_month: int
    ages: tuple[int, ...]
    age_mode: str
    confirmed_theme_id: str
    confirmed_theme_value: str
    week_count: int

    def __post_init__(self) -> None:
        if not 1 <= self.calendar_month <= 12:
            raise ValueError(f"calendar_month는 1~12여야 한다: {self.calendar_month}")
        if not self.ages:
            raise ValueError("ages가 비어 있다")
        for a in self.ages:
            if not 3 <= a <= 5:
                raise ValueError(f"P0 Target은 만3~5세다: {self.ages}")
        if self.week_count < 1:
            raise ValueError(f"week_count는 1 이상이어야 한다: {self.week_count}")

    @property
    def is_single_age(self) -> bool:
        return len(self.ages) == 1


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    """왜 선택됐는지. **Debug / Audit용**이며 Product UI 노출을 전제하지 않는다."""

    retrieval_tier: AgeMatchKind
    rank_score: int
    theme_page_match: bool
    """Record가 나온 면의 `monthly_theme`이 확정 Theme과 겹친다."""

    text_overlap: int
    """Record 본문과 확정 Theme의 2-gram 겹침 수."""

    source_diversity_group: str
    """기관 상한을 셀 때 쓴 묶음 키. Template Family는 하나로 묶인다."""


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    """Evidence Record 하나 + 선택 근거."""

    record: EvidenceRecord
    trace: RetrievalTrace

    @property
    def record_id(self) -> str:
        return self.record.record_id

    @property
    def text(self) -> str | None:
        return self.record.text


@dataclass(frozen=True, slots=True)
class ReferenceCandidate:
    """승인 Activity Reference 후보 + Rule v2 pre-ranking 위치."""

    activity_id: str
    label: str
    evidence_strength: int
    has_display_quality_issue: bool
    rank: int
    """Rule v2 정렬에서의 순위(0부터). Rule의 의미를 바꾸지 않고 위치만 기록한다."""


@dataclass(frozen=True, slots=True)
class EvidenceBlock:
    """성격이 같은 근거 묶음. 비어 있을 수 있고, 비어 있는 것도 정상이다."""

    name: BlockName
    top_k: int
    retrieval_reason: str
    items: tuple[RetrievedEvidence, ...] = ()
    reference_items: tuple[ReferenceCandidate, ...] = ()
    eligible_pool_size: int = 0
    note: str = ""

    @property
    def size(self) -> int:
        return len(self.items) or len(self.reference_items)

    @property
    def is_empty(self) -> bool:
        return self.size == 0

    @property
    def distinct_institutions(self) -> int:
        return len({i.record.institution_id for i in self.items})


@dataclass(frozen=True, slots=True)
class MonthlyEvidenceRetrievalResult:
    """L2의 산출물. Prompt가 아니라 구조화된 객체다."""

    request: RetrievalRequest
    blocks: dict[BlockName, EvidenceBlock] = field(default_factory=dict)
    evidence_store_version: str = ""
    evidence_store_sha256: str = ""
    activity_catalog_id: str = ""
    activity_catalog_version: str = ""

    def block(self, name: BlockName) -> EvidenceBlock:
        return self.blocks[name]

    @property
    def total_evidence_records(self) -> int:
        return sum(len(b.items) for b in self.blocks.values())
