"""Application DTO와 GenerationRun.

CLAUDE.md §13·§15·§17:
- Application DTO를 물리 DB 모델과 직접 결합하지 않는다.
- 공개 HTTP 요청/응답 형태는 OD-N08에서 확정한다. 여기 있는 것은 Application 경계다.

`activation_status`는 이 DTO에 **없다**. 외부 요청자가 Catalog 승인 상태를
지정할 수 없고, ThemeReferenceRepository가 반환하는 metadata로만 판단한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..domain.identifiers import ActorId
from ..domain.plan import YearlyPlan
from .ports import OptionalContextResult

__all__ = [
    "AgeMode",
    "CatalogSelector",
    "ClassroomContext",
    "ConfirmYearlyPlanCommand",
    "DaycareContext",
    "EditYearlyPlanItemCommand",
    "EventInput",
    "GenerateYearlyPlanCommand",
    "GenerationRun",
    "ItemAddress",
    "PlanningSetup",
    "RegenerateYearlyPlanItemCommand",
    "ThemeSelectionTrace",
    "YearlyPlanResult",
    "yearly_plan_to_contract_dict",
]


class AgeMode(str, Enum):
    SINGLE = "SINGLE"
    MIXED = "MIXED"


@dataclass(frozen=True, slots=True)
class ClassroomContext:
    """반 Context.

    CLAUDE.md §9·§11: 혼합연령을 단일 age_group 숫자로 표현하지 않는다.
    논리 표현은 연령 Set이며 물리 저장 방식은 OD-N02에서 확정한다.
    `teacher_name`은 표시 문자열이며 소유권·Confirm Actor 식별자가 아니다.
    """

    classroom_ref: str
    ages: frozenset[int]
    name: str | None = None
    teacher_name: str | None = None
    age_mode: AgeMode | None = None

    @property
    def effective_age_mode(self) -> AgeMode:
        """명시되지 않으면 연령 개수에서 파생한다."""
        if self.age_mode is not None:
            return self.age_mode
        return AgeMode.MIXED if len(self.ages) >= 2 else AgeMode.SINGLE


@dataclass(frozen=True, slots=True)
class DaycareContext:
    """원 Context.

    지역은 저장·표시용이며 교육 목표를 자동 결정하는 근거로 쓰지 않는다.
    """

    daycare_ref: str
    name: str | None = None
    director_name: str | None = None
    region_ref: str | None = None


@dataclass(frozen=True, slots=True)
class PlanningSetup:
    completed: bool
    start_mode: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogSelector:
    """어떤 Catalog를 쓸지 가리키기만 한다. 승인 상태는 담지 않는다."""

    catalog_id: str
    catalog_version: str


@dataclass(frozen=True, slots=True)
class EventInput:
    """입력으로 명시된 행사.

    입력되지 않은 행사를 생성하지 않는다(CLAUDE.md §5).
    """

    event_id: str
    label: str
    starts_on: str
    status: str = "CONFIRMED"

    @property
    def period_key(self) -> str:
        return self.starts_on[:7]


@dataclass(frozen=True, slots=True)
class GenerateYearlyPlanCommand:
    school_year: int
    daycare: DaycareContext
    classroom: ClassroomContext
    planning_setup: PlanningSetup
    catalog: CatalogSelector
    events: tuple[EventInput, ...] = ()
    optional_context_requested: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ItemAddress:
    """편집·재생성 대상의 안정 주소.

    `item_id` 또는 `(period_key, semantic_key)`. 배열 순번은 받지 않는다.
    """

    item_id: str | None = None
    period_key: str | None = None
    semantic_key: str | None = None

    def __post_init__(self) -> None:
        if self.item_id is None and not (self.period_key and self.semantic_key):
            raise ValueError(
                "ItemAddress는 item_id 또는 (period_key, semantic_key)를 가져야 한다"
            )


@dataclass(frozen=True, slots=True)
class EditYearlyPlanItemCommand:
    plan_id: str
    address: ItemAddress
    new_value: str
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class RegenerateYearlyPlanItemCommand:
    plan_id: str
    address: ItemAddress
    actor_id: ActorId
    catalog: CatalogSelector


@dataclass(frozen=True, slots=True)
class ConfirmYearlyPlanCommand:
    """Confirm 명령.

    `catalog`는 **필수**다. Confirm에서 Reference Validation을 생략하는 경로를
    만들지 않기 위해 기본값을 두지 않는다.
    """

    plan_id: str
    actor_id: ActorId | None
    catalog: CatalogSelector


# ------------------------------------------------------------ GenerationRun


@dataclass(frozen=True, slots=True)
class ThemeSelectionTrace:
    """Theme 하나가 왜 선택되었는지에 대한 추적 기록.

    2026-09-10 결정: "가능하면 선택 이유와 적용된 Rule을
    GenerationRun metadata에서 추적 가능하게 해주세요."
    """

    period_key: str
    selected_theme_id: str
    reason: str
    rule_id: str
    rule_version: str
    eligible_theme_ids: tuple[str, ...] = ()
    evidence_strength: int = 0
    avoided_adjacent_repeat: bool = False
    excluded_theme_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class GenerationRun:
    """생성 1회의 실행 metadata.

    docs/demo-source-of-truth.md §25: Fallback 사용 여부는 Generation Run에서
    확인 가능해야 한다.
    """

    run_id: str
    started_at: datetime
    catalog_id: str
    catalog_version: str
    llm_invoked: bool = False
    llm_call_count: int = 0
    """실제 Provider 요청 수. Batch 1회로 12개월을 처리하면 1이다."""
    llm_item_count: int = 0
    """LLM이 다듬은 항목 수. 12개월 Batch면 12다."""
    optional_context: tuple[OptionalContextResult, ...] = ()
    fallbacks_used: tuple[str, ...] = ()
    selection_traces: tuple[ThemeSelectionTrace, ...] = ()

    @property
    def used_fallback(self) -> bool:
        return bool(self.fallbacks_used)

    def trace_for(self, period_key: str) -> ThemeSelectionTrace | None:
        for t in self.selection_traces:
            if t.period_key == period_key:
                return t
        return None


@dataclass(slots=True)
class YearlyPlanResult:
    plan: YearlyPlan
    run: GenerationRun | None = None


# --------------------------------------------------------- Contract 직렬화


def yearly_plan_to_contract_dict(plan: YearlyPlan) -> dict:
    """docs/demo-source-of-truth.md §14 예시 형태의 의미 구조로 직렬화한다.

    `academic_index`는 derived helper이므로 **포함하지 않는다**.
    최종 HTTP·DB Contract가 아니다.
    """
    return {
        "school_year": plan.school_year,
        "classroom_ref": plan.classroom_ref,
        "status": plan.status.value,
        "month_periods": [
            {
                "period_key": mp.period_key.value,
                "theme": {
                    "item_id": mp.theme.item_id.value,
                    "semantic_key": mp.theme.semantic_key.value,
                    "value": mp.theme.value,
                },
            }
            for mp in plan.month_periods
        ],
    }
