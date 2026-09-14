"""Monthly Application DTO.

기존 Yearly DTO(`ClassroomContext` / `DaycareContext` / `PlanningSetup` /
`AgeMode`)를 재사용하고 Monthly 전용만 여기 둔다.

`ItemAddress`를 Monthly 주소로 재사용하지 않는다. 2026-09-11 Cell Address
결정(B안)에 따라 Section 의미와 Week 위치를 분리한 `MonthlyCellAddress`를 쓴다.
`semantic_key` 안에 week ordinal을 인코딩하지 않는다.

Yearly `GenerationRun`을 확장하지 않는다. `MonthlyGenerationRun`은 별도 타입이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..domain.constraint import ConstraintAssessment
from ..domain.identifiers import ActorId
from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_template import TemplateRef
from .dto import CatalogSelector, ClassroomContext, DaycareContext, PlanningSetup
from .ports import OptionalContextResult

__all__ = [
    "ActivitySelectionTrace",
    "ConfirmMonthlyPlanCommand",
    "EditMonthlyPlanItemCommand",
    "GenerateMonthlyPlanCommand",
    "ActivityRegenerationOutcome",
    "MonthlyCellAddress",
    "MonthlyGenerationRun",
    "MonthlyPlanResult",
    "RegenerateMonthlyPlanItemCommand",
    "SafetyRuleSelector",
]


@dataclass(frozen=True, slots=True)
class SafetyRuleSelector:
    """어떤 법정 Rule 데이터를 쓸지 가리킨다. 승인 상태는 담지 않는다.

    `CatalogSelector`와 같은 이유로 승인 여부를 요청자가 지정할 수 없다.
    """

    legal_rule_version: str

    def __post_init__(self) -> None:
        if not self.legal_rule_version or not self.legal_rule_version.strip():
            raise ValueError("legal_rule_version은 비어 있을 수 없다")


@dataclass(frozen=True, slots=True)
class MonthlyCellAddress:
    """Monthly Cell의 안정 주소.

        WEEKLY_CELLS            target_month + section_key + week_id
        MONTHLY_MERGED_SUMMARY  target_month + section_key + week_id=None

    `week_id=None`은 "지정하지 않음"이 아니라 **monthly merged cell**을 뜻한다.
    배열 순번을 주소로 쓰지 않는다.
    """

    target_month: str
    section_key: str
    week_id: str | None = None
    item_id: str | None = None

    def __post_init__(self) -> None:
        if not self.target_month or not self.target_month.strip():
            raise ValueError("MonthlyCellAddress.target_month는 비어 있을 수 없다")
        if not self.section_key or not self.section_key.strip():
            raise ValueError("MonthlyCellAddress.section_key는 비어 있을 수 없다")

    def __str__(self) -> str:
        where = self.week_id or "merged"
        return f"{self.target_month}/{self.section_key}/{where}"


class MonthlyGenerationMode(str, Enum):
    """Monthly를 어느 경로로 생성하는가 (OD-N15).

        RULE_ONLY     Rule이 Theme·주차·활동을 모두 결정한다 (M1~M2 경로)
        LLM_PLANNER   Rule이 Gate·주차·Theme을 확정하고, 한 달 흐름과 활동
                      구성을 LLM이 한다 (L2~L5 경로)

    **Use Case가 알아서 고르지 않는다.** 환경을 보고 Mode를 바꾸거나 LLM 실패
    시 RULE_ONLY로 내려가는 경로를 만들지 않는다. Mode는 호출자가 명시한 값
    그대로 쓰인다.
    """

    RULE_ONLY = "RULE_ONLY"
    LLM_PLANNER = "LLM_PLANNER"


@dataclass(frozen=True, slots=True)
class GenerateMonthlyPlanCommand:
    """Monthly 생성 명령.

    `template_ref`와 `safety_rule`은 **필수**다. "현재 최신 Template을 알아서
    사용" 같은 숨은 default를 만들지 않는다. 어떤 template_id / template_version /
    legal_rule_version을 썼는지가 재현 가능해야 한다.
    """

    parent_yearly_plan_id: str
    school_year: int
    target_month: str
    daycare: DaycareContext
    classroom: ClassroomContext
    planning_setup: PlanningSetup
    template_ref: TemplateRef
    safety_rule: SafetyRuleSelector
    catalog: CatalogSelector
    """상위 Yearly가 사용한 Theme Reference catalog.

    Yearly Plan Aggregate와 EvidenceSource는 `catalog_id`를 저장하지 않고
    `source_version`(= catalog_version)만 보존한다. 따라서
    `ParentYearlyLineage.reference_catalog_id`를 상위 Plan만으로는 파생할 수 없다.
    추측하지 않고 요청자가 명시하게 하며, Gate가 `catalog_version`을 상위 Theme
    Evidence의 `source_version`과 대조해 거짓 값을 막는다.
    """
    generation_mode: MonthlyGenerationMode = MonthlyGenerationMode.RULE_ONLY
    """어느 경로로 생성할지. **기본값은 기존 경로다.**

    L6에서 Production/Demo default를 전환하지 않는다. LLM Planner는 호출자가
    명시적으로 고를 때만 동작한다.
    """

    optional_context_requested: dict[str, object] = field(default_factory=dict)
    activity_catalog: CatalogSelector | None = None
    """어떤 Activity Reference catalog를 쓸지 가리킨다. 승인 상태는 담지 않는다.

    **Optional이다.** 주지 않으면 outdoor_play를 채우지 않고 M1과 동일하게
    `EMPTY_VALID`로 둔다. "현재 최신 Activity catalog를 알아서 사용" 같은 숨은
    default를 만들지 않기 위해 어떤 catalog_id / catalog_version을 썼는지
    요청자가 명시하게 한다.
    """

    def __post_init__(self) -> None:
        if not self.parent_yearly_plan_id or not self.parent_yearly_plan_id.strip():
            raise ValueError("parent_yearly_plan_id는 비어 있을 수 없다")


@dataclass(slots=True)
class MonthlyGenerationRun:
    """Monthly 생성 1회의 실행 metadata.

    Yearly `GenerationRun`과 별도 타입이다. Yearly 필드에 기본값을 채워 재사용하면
    의미가 흐려지고, 필드를 추가하면 Yearly Core가 바뀐다.

    **`unresolved_requirements`와 `fallbacks_used`는 다른 개념이다.**
    Safety source 부재는 fallback이 아니다. 대체재를 쓴 것이 아니라
    **대체재를 쓰지 않기로 한 것**이므로 `unresolved_requirements`에 넣는다.
    """

    run_id: str
    started_at: datetime
    template_id: str
    template_version: str
    safety_legal_rule_version: str
    week_period_count: int = 0
    generated_cell_count: int = 0
    filled_cell_count: int = 0
    empty_valid_cell_count: int = 0
    empty_unresolved_cell_count: int = 0
    llm_invoked: bool = False
    llm_call_count: int = 0
    llm_item_count: int = 0

    generation_mode: str = MonthlyGenerationMode.RULE_ONLY.value
    """이 Plan이 어느 경로에서 나왔는지. Plan만 보고도 확인 가능해야 한다(§30)."""

    planner_model: str | None = None
    prompt_version: str | None = None
    packet_fingerprint: str | None = None
    evidence_store_version: str | None = None
    evidence_store_sha256: str | None = None
    retrieval_version: str | None = None
    context_packet_version: str | None = None
    planner_validation_repair_count: int = 0
    planner_repaired_violations: tuple[str, ...] = ()
    """repair 전에 걸렸던 L5 위반 code. 성공해도 무엇을 고쳐 왔는지 남긴다.

    **Prompt 전문·API Key·Base URL·Source 원문은 담지 않는다**(§42).
    """
    optional_context: tuple[OptionalContextResult, ...] = ()
    fallbacks_used: tuple[str, ...] = ()
    unresolved_requirements: tuple[ConstraintAssessment, ...] = ()
    activity_catalog_id: str | None = None
    activity_catalog_version: str | None = None
    activity_filled_cell_count: int = 0
    activity_unfilled_cell_count: int = 0
    """후보가 0이라 비워 둔 outdoor Cell 수.

    `unresolved_requirements`가 아니다. 그 필드는 법정 요건 미검증 전용이며
    outdoor 활동이 비어 있는 것은 법적 미충족이 아니다. `fallbacks_used`도
    아니다 — 대체재를 쓴 것이 아니기 때문이다.
    """
    activity_selection_traces: tuple["ActivitySelectionTrace", ...] = ()

    @property
    def used_fallback(self) -> bool:
        return bool(self.fallbacks_used)

    @property
    def has_unresolved_requirement(self) -> bool:
        return bool(self.unresolved_requirements)


@dataclass(slots=True)
class MonthlyPlanResult:
    plan: MonthlyPlan
    run: MonthlyGenerationRun | None = None
    cell_regeneration: object | None = None
    """LLM으로 Cell 하나를 재생성했을 때의 실행 결과.

    `MonthlyLlmCellRegenerationOutcome`이며 Application 계층 타입이라
    순환 import를 피해 느슨하게 둔다. Audit이 아니다 — 변경 이력은 Item의
    `AuditTrail`이 가진다.
    """

    activity_regeneration: "ActivityRegenerationOutcome | None" = None
    """outdoor Cell 하나를 재생성했을 때의 선택 결과.

    Audit이 아니다. 변경 이력은 여전히 Item의 `AuditTrail`이 가진다.
    여기에는 어떤 Catalog·Rule로 무엇이 선택되었는지, 무엇을 대체했는지가
    담긴다. Generate의 `MonthlyGenerationRun`과 같은 성격의 실행 결과다.
    """


@dataclass(frozen=True, slots=True)
class EditMonthlyPlanItemCommand:
    """선택한 Cell 하나만 교사가 직접 수정한다.

    `new_value`가 빈 문자열일 수 있다. 허용 여부는 Section 의미가 정하며
    rules/monthly_cell_state.py가 판정한다.
    """

    plan_id: str
    address: MonthlyCellAddress
    new_value: str
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class RegenerateMonthlyPlanItemCommand:
    """선택한 Cell 하나만 Rule로 재생성한다.

    M1에서 재생성 가능한 Cell은 `theme`뿐이고 그 값은 parent anchor에서
    파생되므로 catalog selector 같은 추가 Reference 입력이 필요하지 않다.
    필요한 최소 입력만 받는다.
    """

    plan_id: str
    address: MonthlyCellAddress
    actor_id: ActorId
    generation_mode: "MonthlyGenerationMode | None" = None
    """요청이 기대하는 생성 경로. None이면 Plan의 실제 경로를 그대로 쓴다.

    명시했는데 Plan의 경로와 다르면 **실패한다.** Mode를 자동으로 바꾸지 않는다.
    """


@dataclass(frozen=True, slots=True)
class ConfirmMonthlyPlanCommand:
    """Monthly Plan 확정.

    **Template/Safety selector를 받지 않는다.** Plan이 생성 시점의 정확한
    `template_ref`와 (ConstraintAssessment의) `rule_version`을 이미 보존하므로,
    Confirm은 그 Plan이 실제로 사용했던 Reference를 다시 검증해야 한다.
    호출자가 다른 version이나 "최신" version을 넘겨 Confirm 기준을 바꿀 수
    있으면 안 된다. 숨은 latest default도 만들지 않는다.
    """

    plan_id: str
    actor_id: ActorId | None


@dataclass(frozen=True, slots=True)
class ActivitySelectionTrace:
    """Activity 하나가 왜 선택되었는지에 대한 추적 기록.

    `ThemeSelectionTrace`와 같은 성격이다. Domain truth를 복제하는 snapshot이
    아니라 **선택 이유**만 담는다. Candidate 목록 전체나 Catalog 내용은 넣지
    않는다.

    후보가 없으면 `selected_activity_id`가 None이고 `reason`이
    `NO_ELIGIBLE_CANDIDATE`다. 이것은 오류가 아니라 정상 결과다.
    """

    target_month: str
    section_key: str
    reason: str
    rule_id: str
    rule_version: str
    week_id: str | None = None
    candidate_count: int = 0
    selected_activity_id: str | None = None
    selected_label: str | None = None
    repeat_penalty: int = 0
    """같은 월 재사용 + 현재 Activity 재선택을 합산한 penalty. 0이면 신규 배정이다."""
    reused_in_month: bool = False
    is_current_activity: bool = False
    theme_matched: bool = False
    parent_theme_id: str | None = None
    display_quality_penalty: int = 0
    """사람이 확정한 표시 품질 문제로 받은 penalty. 0이면 문제 없음 또는 미검토다.

    자동 탐지 결과(`AUTO_CANDIDATE`)와 미검토는 항상 0이다. Catalog에 필드가 없는
    legacy v0.2.0에서도 0이므로 기존 Plan의 trace 의미가 바뀌지 않는다.
    """
    curriculum_repeat_penalty: int = 0
    selected_curriculum_domains: tuple[str, ...] = ()
    evidence_strength: int = 0
    all_candidates_penalized: bool = False
    """모든 후보가 repeat penalty를 받아 회피가 불가능했는지."""

    @property
    def has_selection(self) -> bool:
        return self.selected_activity_id is not None


@dataclass(frozen=True, slots=True)
class ActivityRegenerationOutcome:
    """outdoor Cell 하나를 재생성한 결과.

    `previous_activity_id`는 대상 Cell의 기존 `ACTIVITY_REFERENCE` Evidence에서
    읽는다. label 역검색으로 만들지 않는다. 교사가 직접 쓴 Cell처럼 Evidence가
    없으면 None이다.

    선택된 Activity가 기존과 같아도 **성공**이다. M2-B에서 현재 Activity는 hard
    exclusion이 아니라 penalty이므로 대안이 없으면 같은 값이 유지된다.
    """

    address: MonthlyCellAddress
    catalog_id: str
    catalog_version: str
    previous_value: str
    previous_activity_id: str | None
    selected_value: str
    selected_activity_id: str
    trace: ActivitySelectionTrace

    @property
    def activity_changed(self) -> bool:
        return self.previous_activity_id != self.selected_activity_id

    @property
    def value_changed(self) -> bool:
        return self.previous_value != self.selected_value

    @property
    def rule_id(self) -> str:
        return self.trace.rule_id

    @property
    def rule_version(self) -> str:
        return self.trace.rule_version

    @property
    def reason(self) -> str:
        return self.trace.reason
