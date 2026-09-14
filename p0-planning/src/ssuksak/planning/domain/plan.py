"""Yearly Plan Aggregate.

docs/open-decisions.md OD-Y01 (RESOLVED_FOR_P0) 최소 의미 구조:

    YearlyPlan
    ├─ school_year
    ├─ classroom_ref
    └─ month_periods[12]        3월 → 다음 해 2월
       └─ theme (required)

`goals`, `rationale`, `weekly_focus`, 기관 특화 Section은 Optional이다.
모든 편집 단위는 안정적인 `item_id`와 `semantic_key`를 가진다.

구조 불변식은 이 Aggregate가 아니라 application/validate_yearly_plan.py가 검사한다.
tests/golden/yearly_cases.json의 case 10·11·12가 정상 Plan을 만든 뒤
period를 제거·중복시키고 theme을 공백으로 바꿔서 **Validator를 단독 호출**하기
때문에, 생성자가 구조를 즉시 거부하면 그 Fixture를 만들 수 없다.
반면 상태 Gate(CONFIRMED read-only)는 이 Aggregate가 직접 막는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from .errors import FailureCategory, blocked
from .identifiers import ItemId, PeriodKey, PlanId, SemanticKey
from .provenance import (
    AuditEvent,
    AuditTrail,
    EvidenceSource,
    GenerationMethodDetail,
)

ACADEMIC_MONTH_ORDER: tuple[int, ...] = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)
"""학년도 월 순서. theme_reference_v0.json > month_semantics.academic_order와 동일."""


class PlanStatus(str, Enum):
    """docs/screen-spec.md §10: Plan 상태는 이 둘만 사용한다.

    EMPTY / GENERATING / GENERATION_PARTIAL / ERROR는 Plan 상태가 아니라
    Generation/UI 상태이므로 이 Enum에 넣지 않는다.
    """

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


def academic_index_of(school_year: int, period_key: PeriodKey) -> int:
    """학년도 안에서의 1-based 순서를 계산하는 **derived helper**.

    Yearly Application Contract의 canonical field가 아니다. 내부 정렬과
    검증에만 쓰며 DTO로 내보내지 않는다. 달력 월 정렬은 학년도 순서와
    어긋나므로(1·2월이 school_year + 1) 이 helper가 필요하다.
    """
    delta = (period_key.calendar_year - school_year) * 12 + (period_key.calendar_month - 3)
    return delta + 1


@dataclass(slots=True)
class PlanItem:
    """편집·재생성의 단위.

    표시 Label, 배열 순번, DB 컬럼명을 주소로 쓰지 않는다(OD-Y01).
    """

    item_id: ItemId
    semantic_key: SemanticKey
    value: str
    generation: GenerationMethodDetail
    evidence: list[EvidenceSource] = field(default_factory=list)
    audit: AuditTrail = field(default_factory=AuditTrail)

    def evidence_of_type(self, source_type) -> list[EvidenceSource]:
        return [e for e in self.evidence if e.source_type is source_type]

    def snapshot(self) -> "PlanItem":
        """비교용 얕은 복사. 보존 검증 테스트에서 사용한다."""
        return replace(
            self,
            evidence=list(self.evidence),
            audit=AuditTrail(list(self.audit.events)),
        )


@dataclass(slots=True)
class MonthPeriod:
    """한 달 기간. `theme`은 필수이고 그 밖의 Item은 Optional이다."""

    period_key: PeriodKey
    theme: PlanItem
    optional_items: list[PlanItem] = field(default_factory=list)

    @property
    def items(self) -> list[PlanItem]:
        return [self.theme, *self.optional_items]


@dataclass(slots=True)
class YearlyPlan:
    """Yearly Plan Aggregate Root.

    Plan 소유 단위는 classroom이다(OD-Y03). 혼합연령 반도 연령별로 분할하지 않고
    classroom당 하나의 Plan을 가진다.
    """

    plan_id: PlanId
    school_year: int
    classroom_ref: str
    status: PlanStatus
    month_periods: list[MonthPeriod]
    classroom_ages: frozenset[int]
    audit: AuditTrail = field(default_factory=AuditTrail)

    # ------------------------------------------------------------- 조회

    @property
    def items(self) -> list[PlanItem]:
        return [item for mp in self.month_periods for item in mp.items]

    def period(self, period_key: str) -> MonthPeriod | None:
        for mp in self.month_periods:
            if mp.period_key.value == period_key:
                return mp
        return None

    def find_item(
        self,
        *,
        item_id: str | None = None,
        period_key: str | None = None,
        semantic_key: str | None = None,
    ) -> tuple[MonthPeriod, PlanItem] | None:
        """안정 주소로 Item을 찾는다.

        `item_id` 우선. 없으면 `(period_key, semantic_key)`로 찾는다.
        배열 순번은 주소로 받지 않는다.
        """
        for mp in self.month_periods:
            for item in mp.items:
                if item_id is not None:
                    if item.item_id.value == item_id:
                        return mp, item
                    continue
                if (
                    period_key is not None
                    and semantic_key is not None
                    and mp.period_key.value == period_key
                    and item.semantic_key.value == semantic_key
                ):
                    return mp, item
        return None

    # ------------------------------------------------------- 상태 Gate

    @property
    def is_confirmed(self) -> bool:
        return self.status is PlanStatus.CONFIRMED

    def ensure_mutable(self, operation: str) -> None:
        """DRAFT에서만 편집·재생성을 허용한다.

        CLAUDE.md §2·§19 / docs/screen-spec.md §8.2:
        P0에서 CONFIRMED Plan은 read-only다.
        """
        if self.is_confirmed:
            raise blocked(
                "confirmed_yearly_plan_is_read_only",
                FailureCategory.PLAN_STATE_GATE,
                f"{operation}은 CONFIRMED Plan에서 허용되지 않는다",
            )

    # ------------------------------------------------------------- 변경

    def replace_item_value(
        self,
        item: PlanItem,
        new_value: str,
        *,
        generation: GenerationMethodDetail | None = None,
    ) -> None:
        """Item의 현재 값을 교체한다.

        Evidence는 절대 제거하지 않는다(CLAUDE.md §13.3).
        `generation`을 주지 않으면 기존 Generation Method를 유지한다 —
        교사 편집이 Method를 MANUAL로 덮어쓰지 않도록 하는 지점이다.
        """
        item.value = new_value
        if generation is not None:
            item.generation = generation

    def record(self, event: AuditEvent) -> None:
        """Plan-level Audit Event."""
        self.audit.append(event)

    def confirm(self, event: AuditEvent) -> None:
        self.status = PlanStatus.CONFIRMED
        self.audit.append(event)
