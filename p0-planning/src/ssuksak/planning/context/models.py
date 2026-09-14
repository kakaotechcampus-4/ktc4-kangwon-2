"""Monthly Context Packet Contract (L3).

L2는 "무엇이 근거인가"를 골랐다. L3는 그것을 **Monthly Planning Context**로
조립한다. 여전히 **Prompt 문자열을 만들지 않는다** — Prompt Rendering은 L4다.

세 가지를 구조로 보장한다.

1. **Planner-visible과 Audit-only를 나눈다.** `rank_score`·`source_diversity_group`
   같은 Retrieval 내부 점수는 GPT에게 의미가 없고 Token만 먹는다. 각 항목의
   `audit` 하위 model에 넣고 planner payload에서 제외한다.
2. **주차 번호를 만들지 않는다.** `WeekExperienceCandidate`에는 week 필드가
   아예 없다. 값을 None으로 두는 것이 아니라 **자리 자체를 두지 않는다**.
3. **재사용 정책이 사라지지 않는다.** 모든 Evidence 항목이 `reuse_policy`를
   들고 다니고, Constraint가 `source_text_copy_allowed = False`를 명시한다.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ...ingestion.models import ReusePolicy
from ..retrieval.models import AgeMatchKind

__all__ = [
    "PACKET_VERSION",
    "RETRIEVAL_CONTRACT_VERSION",
    "ActivityOrigin",
    "AgeContext",
    "AgeContrastGroup",
    "AgeContrastObservation",
    "AgeEvidenceStrength",
    "AgeEvidenceSummary",
    "EvidenceAudit",
    "EvidenceItem",
    "MonthlyContextPacket",
    "OfficialCaseContext",
    "PackedBlock",
    "ParentThemeContext",
    "PlannerConstraints",
    "PlanningRequestContext",
    "ReferenceActivityCandidate",
    "SafetyContext",
    "SourceLineage",
    "WeekExperienceCandidate",
    "WeekSlot",
]

PACKET_VERSION = "monthly-context-packet-v0.1.0"

RETRIEVAL_CONTRACT_VERSION = "monthly-evidence-retrieval-v0.1.0"
"""L2가 자기 version 상수를 publish하지 않아 L3에서 이름을 붙인 값.

L2 코드를 고치지 않으려고 여기 둔다. Lineage 재현성을 위해서는 L2 쪽으로
옮기는 편이 옳다 — L3 보고서 §19에 L2 minor gap으로 기록했다.
"""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgeEvidenceStrength(str, Enum):
    """연령 근거 강도.

    **기준을 새로 만들지 않았다.** `docs/analysis/new-reference-evidence-impact-2026-09.md`
    §4.1이 확정한 4단계와 임계값을 그대로 쓴다.

        STRONG      단일연령 독립기관 >= 3
        MODERATE    단일연령 독립기관 == 2, 또는 1이면서 그 면에 바깥놀이 행이 있음
        WEAK        단일연령 독립기관 == 1 (바깥놀이 행 없음), 또는 혼합 근거 기관 >= 3
        VERY_WEAK   그 외
    """

    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    VERY_WEAK = "VERY_WEAK"


class ActivityOrigin(str, Enum):
    """Activity 값이 어디서 왔는가 (OD-N13 확정 3축 중 세 번째).

    Enum을 **삭제하지 않는다.** P0에서 `CORPUS_EVIDENCE`가 쓰이지 않는 것은
    Corpus record의 `reuse_policy`가 전부 `CONTEXT_ONLY`이기 때문이지 개념이
    폐기되어서가 아니다. 그 상태는 `PlannerConstraints`가 표현한다.
    """

    REFERENCE = "REFERENCE"
    CORPUS_EVIDENCE = "CORPUS_EVIDENCE"
    LLM_SYNTHESIZED = "LLM_SYNTHESIZED"


class PackedBlock(str, Enum):
    """Packet Block 이름. Budget 우선순위와 중복 제거 우선순위의 키다."""

    AGE_CONTRAST = "age_contrast_evidence"
    REFERENCE_ACTIVITIES = "reference_activities"
    INSTITUTION_EVIDENCE = "institution_evidence"
    WEEK_EXPERIENCE = "week_experience_candidates"
    OTHER_OUTDOOR = "other_outdoor_evidence"


# ------------------------------------------------------------------ 고정 입력


class PlanningRequestContext(_Strict):
    """무슨 월, 몇 세인가.

    `daycare_ref` · `classroom_ref`는 audit 식별자이며 planner payload에서
    제외된다. LLM이 내부 ID로 할 수 있는 일이 없다.
    """

    school_year: str = Field(min_length=1)
    target_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    calendar_month: int = Field(ge=1, le=12)
    classroom_ages: tuple[int, ...]
    age_mode: str = Field(min_length=1)

    daycare_ref: str | None = None
    classroom_ref: str | None = None


class ParentThemeContext(_Strict):
    """Yearly에서 CONFIRMED된 Theme. **immutable planning input이다.**

    LLM은 `theme_id`를 고르지도 바꾸지도 않는다(CLAUDE.md §5).
    """

    theme_id: str = Field(min_length=1)
    theme_value: str = Field(min_length=1)

    parent_yearly_plan_id: str = Field(min_length=1)
    parent_yearly_period_key: str = Field(min_length=1)
    reference_catalog_id: str = Field(min_length=1)
    reference_version: str = Field(min_length=1)
    confirmed_at: datetime


class WeekSlot(_Strict):
    """canonical WeekPeriod 하나. **LLM이 주차 수나 날짜를 만들지 않는다.**"""

    week_id: str = Field(min_length=1)
    display_label: str = Field(min_length=1)
    display_order: int = Field(ge=1)
    start_date: date
    end_date: date
    active: bool = True


# ------------------------------------------------------------------ 연령


class AgeEvidenceSummary(_Strict):
    """한 연령의 근거 통계. 표기는 재감사 문서의 `(단N/전N/바N)`과 같다."""

    age: int = Field(ge=3, le=5)
    single_age_institution_count: int = Field(ge=0)
    """단 — 그 달 그 연령의 단일연령 면을 가진 독립기관 수."""

    age_mentioning_institution_count: int = Field(ge=0)
    """전 — 그 연령을 언급한 독립기관 수(혼합 포함)."""

    single_age_outdoor_page_count: int = Field(ge=0)
    """바 — 단일연령이면서 바깥놀이 행이 있는 면 수."""

    strength: AgeEvidenceStrength


class AgeContext(_Strict):
    """연령 Grounding이 얼마나 강한가.

    후속 Planner가 **연령 차이를 과장하지 않도록** 하는 신호다. 자연어 지시는
    L4에서 붙인다. L3는 값만 준다.
    """

    requested_ages: tuple[int, ...]
    per_age: tuple[AgeEvidenceSummary, ...]
    overall_strength: AgeEvidenceStrength
    """요청 연령 중 **가장 약한** 값. 혼합 요청에서 강한 쪽에 끌려가지 않게 한다."""

    single_age_grounding_count: int = Field(ge=0)
    """Packet에 실제로 담긴 바깥놀이 근거 중 **요청 연령의 단일연령 면**에서 온 수.

    등급이 아니라 사실이다. `strength`는 그 달 Corpus 전체를 보지만 Packet에
    담기는 것은 Top-K뿐이라 둘이 어긋날 수 있다. 2027-02 만5세가 그 예다 —
    단3(STRONG)인데 Packet 안의 만5세 단일연령 근거는 1건이다. 등급만 보고
    연령 차이를 강하게 말하면 근거보다 앞서게 된다.

    Institution·Age Contrast·Other Outdoor를 합쳐 센다. 중복 제거 때문에
    어느 Block에 들어갔는지는 달라지지만 **Packet 전체가 가진 양**은 같다.
    """

    age_contrast_count: int = Field(ge=0)
    age_contrast_document_count: int = Field(ge=0)
    criteria_id: str = Field(min_length=1)
    """어느 문서의 기준을 썼는지. 임의 기준이 아님을 Packet 안에서 추적 가능하게 한다."""


# ------------------------------------------------------------------ Evidence


class EvidenceAudit(_Strict):
    """Planner에게 보여주지 않는 재현·감사 정보."""

    record_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int = Field(ge=1)
    institution_id: str | None = None
    source_diversity_group: str = Field(min_length=1)
    retrieval_tier: AgeMatchKind
    rank_score: int
    theme_page_match: bool
    text_overlap: int
    extraction_quality: str = Field(min_length=1)
    machine_readability: str = Field(min_length=1)


class EvidenceItem(_Strict):
    """Corpus에서 관찰된 근거 하나. **최종 Product 값이 아니다.**"""

    ref: str = Field(pattern=r"^E\d{2,}$")
    """Packet 안에서만 쓰는 짧은 참조(`E01`…).

    Planner가 "어느 근거를 썼는지" 인용할 때 쓴다. 35자짜리 `record_id`를
    그대로 주면 두 가지가 나빠진다 — Token을 먹고, 모델이 hex를 정확히 되받아
    적지 못한다. 실제 `record_id`는 `audit`에 있고 L5가 ref로 되짚는다.
    """

    evidence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    month: int | None = None
    age_scope: tuple[int, ...] = ()
    source_group: str = Field(min_length=1)
    """익명화된 출처 묶음 라벨(`S1`, `S2`…).

    Planner에게 필요한 것은 "서로 다른 곳에서 나왔다"는 사실이지 기관 이름이
    아니다. 실제 `institution_id`는 `audit`에 남는다.
    """

    source_section: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    monthly_theme: str | None = None
    reuse_policy: ReusePolicy
    age_match_kind: AgeMatchKind
    audit: EvidenceAudit


class WeekExperienceCandidate(_Strict):
    """그 달에 관찰된 **경험 후보**. `WeekPlan`이 아니다.

    week 필드를 두지 않는 것이 이 model의 핵심이다. L1 실측에서
    `week_position` 보유 record가 0건이므로, 자리를 만들면 누군가 반드시
    추정해서 채운다.
    """

    ref: str = Field(pattern=r"^E\d{2,}$")
    evidence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    age_scope: tuple[int, ...] = ()
    source_group: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    monthly_theme: str | None = None
    reuse_policy: ReusePolicy
    audit: EvidenceAudit


class AgeContrastObservation(_Strict):
    """한 연령 면에서 관찰된 것들."""

    age: int = Field(ge=3, le=5)
    items: tuple[EvidenceItem, ...]


class AgeContrastGroup(_Strict):
    """**같은 문서·같은 월**에서 연령만 달라진 관찰.

    평탄화하면 의미가 사라진다. `만3세 A / 만4세 B` 두 줄을 따로 주면 Planner는
    그것이 같은 기관의 같은 달 기록인지 알 수 없다.
    """

    group_id: str = Field(min_length=1)
    source_group: str = Field(min_length=1)
    month: int | None = None
    monthly_theme: str | None = None
    observations: tuple[AgeContrastObservation, ...]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_path: str = Field(min_length=1)

    @property
    def size(self) -> int:
        return sum(len(o.items) for o in self.observations)

    @property
    def ages(self) -> tuple[int, ...]:
        return tuple(o.age for o in self.observations)


class ReferenceActivityCandidate(_Strict):
    """승인 Catalog의 canonical 후보.

    후속 Planner가 **그대로 선택할 수 있는 유일한 Activity 축**이다.
    """

    activity_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    supported_ages: tuple[int, ...]
    theme_link_ids: tuple[str, ...] = ()
    evidence_strength: int = Field(ge=0)
    has_display_quality_issue: bool
    rank: int = Field(ge=0)


class OfficialCaseContext(_Strict):
    """Official 자료에서 온 Case. **현재 비어 있다** — L2 Option A."""

    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    ages: tuple[int, ...] = ()
    source_document: str = Field(min_length=1)


# ------------------------------------------------------------------ 제약


class SafetyContext(_Strict):
    """안전교육은 **LLM Planner가 배치하지 않는다**(CLAUDE.md §5).

    그래서 이 Block에는 안전교육 **내용 후보를 넣지 않는다.** 상태만 전달한다.
    """

    safety_generation_allowed: bool = False
    verification: str = Field(min_length=1)
    cell_state: str = Field(min_length=1)
    required_source_kinds: tuple[str, ...]
    rule_version: str = Field(min_length=1)
    detail: str = ""


class PlannerConstraints(_Strict):
    """자연어 금지 문구가 아니라 **구조화된 Constraint**.

    L4가 이것을 읽어 Prompt 문장을 만든다. 문장을 L3에 두면 Constraint가
    바뀌었을 때 어디를 고쳐야 하는지 알 수 없게 된다.
    """

    expected_week_ids: tuple[str, ...]
    expected_week_count: int = Field(ge=1)

    theme_locked: bool = True
    safety_generation_allowed: bool = False
    duplicate_activity_allowed: bool = False
    official_claim_allowed: bool = False
    source_text_copy_allowed: bool = False
    corpus_direct_output_enabled: bool = False
    """Corpus record를 Product 값으로 직접 쓸 수 있는가.

    P0 Evidence Store 12,367건이 전부 `CONTEXT_ONLY`이므로 False다
    (`PRODUCT_OUTPUT_ALLOWED` 0건).
    """

    allowed_activity_origins: tuple[ActivityOrigin, ...]
    activity_origin_priority: tuple[ActivityOrigin, ...]
    """선호 순서. `allowed`에서 빠진 origin도 순서에는 남는다 — 개념이 폐기된
    것이 아니라 현재 Corpus의 reuse policy 때문에 비활성이기 때문이다."""


class SourceLineage(_Strict):
    """이 Packet이 무엇으로 만들어졌는가. 재현을 위한 최소 집합."""

    packet_version: str = Field(min_length=1)
    retrieval_version: str = Field(min_length=1)

    evidence_store_id: str = Field(min_length=1)
    evidence_store_schema_version: str = Field(min_length=1)
    evidence_store_ingestion_version: str = Field(min_length=1)
    evidence_store_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    activity_catalog_id: str = ""
    activity_catalog_version: str = ""
    """Catalog가 주입되지 않으면 빈 문자열이다.

    그때 `reference_activities`도 반드시 비어 있어야 한다 — Validator가 이
    대응을 고정한다. 추측으로 Catalog 이름을 채우지 않는다."""

    theme_reference_catalog_id: str = Field(min_length=1)
    theme_reference_version: str = Field(min_length=1)

    week_policy_name: str = Field(min_length=1)
    week_policy_version: str = Field(min_length=1)

    selection_rule_version: str = Field(min_length=1)


# ------------------------------------------------------------------ Packet


class MonthlyContextPacket(_Strict):
    """L3의 산출물.

    Optional Block이 비어도 유효하다. 비어 있음을 `"근거 없음"` 같은 **가짜
    Evidence 문자열로 채우지 않는다** — 구조적으로 빈 tuple이다.
    """

    packet_version: str = PACKET_VERSION

    planning_request: PlanningRequestContext
    parent_theme: ParentThemeContext
    week_slots: tuple[WeekSlot, ...]
    age_context: AgeContext

    institution_evidence: tuple[EvidenceItem, ...] = ()
    age_contrast_evidence: tuple[AgeContrastGroup, ...] = ()
    week_experience_candidates: tuple[WeekExperienceCandidate, ...] = ()
    reference_activities: tuple[ReferenceActivityCandidate, ...] = ()
    other_outdoor_evidence: tuple[EvidenceItem, ...] = ()

    official_play_context: tuple[OfficialCaseContext, ...] = ()
    official_topic_context: tuple[OfficialCaseContext, ...] = ()

    safety_context: SafetyContext
    constraints: PlannerConstraints
    source_lineage: SourceLineage

    trimmed_blocks: tuple[str, ...] = ()
    """Budget 때문에 잘린 Block. 비어 있으면 Trim이 없었다는 뜻이다."""

    def block_sizes(self) -> dict[PackedBlock, int]:
        return {
            PackedBlock.INSTITUTION_EVIDENCE: len(self.institution_evidence),
            PackedBlock.AGE_CONTRAST: sum(
                g.size for g in self.age_contrast_evidence
            ),
            PackedBlock.WEEK_EXPERIENCE: len(self.week_experience_candidates),
            PackedBlock.REFERENCE_ACTIVITIES: len(self.reference_activities),
            PackedBlock.OTHER_OUTDOOR: len(self.other_outdoor_evidence),
        }

    @property
    def all_evidence_ids(self) -> tuple[str, ...]:
        out = [i.evidence_id for i in self.institution_evidence]
        out += [
            i.evidence_id
            for g in self.age_contrast_evidence
            for o in g.observations
            for i in o.items
        ]
        out += [c.evidence_id for c in self.week_experience_candidates]
        out += [i.evidence_id for i in self.other_outdoor_evidence]
        return tuple(out)
