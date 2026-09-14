"""Monthly Plan Aggregate.

2026-09-11 승인 구조:

    MonthlyPlan
    ├─ plan_id / school_year / target_month
    ├─ daycare_ref / classroom_ref / classroom_ages / age_mode
    ├─ status
    ├─ parent_lineage          immutable snapshot. anchor 불변
    ├─ template_ref
    ├─ week_periods[]          Plan 직속 **독립 축**
    ├─ sections[]              Section이 상위 구조
    ├─ constraint_assessments[]
    └─ audit

`week_periods`를 Section에 종속시키지 않은 이유: `MONTHLY_MERGED_SUMMARY`
Section의 Cell은 어느 week에도 속하지 않는다(실측 시립새봄·아이들세상).
Week가 하위였다면 표현할 수 없다. 대신 MonthlyPlanItem이 `week_id`로 축을 참조하고
`week_id is None`이 monthly merged cell을 뜻한다.

**공용 PlanItem을 수정하지 않는다.** `source_label`·`label_variant`·
`mapping_confidence`·`week_id`·`cell_state` 5개가 Monthly 전용이므로
MonthlyPlanItem을 별도 타입으로 둔다(OD-M03). `GenerationMethodDetail` /
`EvidenceSource` / `AuditTrail`은 공용 타입을 composition으로 재사용한다.

주소는 `semantic_key`에 주차 위치를 인코딩하지 않는다. Section 의미와 Week 위치를
분리한다(2026-09-11 Cell Address 결정 B안).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from .constraint import CellState, ConstraintAssessment, ConstraintKind
from .errors import FailureCategory, blocked
from .identifiers import ItemId, PeriodKey, PlanId, SemanticKey
from .monthly_template import DisplayMode, EmptyValuePolicy, SectionRole, TemplateRef
from .parent_lineage import ParentYearlyLineage
from .plan import PlanStatus
from .provenance import AuditEvent, AuditTrail, EvidenceSource, GenerationMethodDetail
from .week_period import WeekId, WeekPeriod


class LabelVariant(str, Enum):
    """중립 슬롯을 어떤 원본 Label이 점유했는지(OD-M03).

    두 Label을 같은 문자열 의미로 정규화하지 않기 위한 구분자다.
    """

    SUBTHEME_LABELED = "SUBTHEME_LABELED"
    EXPECTED_PLAY_LABELED = "EXPECTED_PLAY_LABELED"
    UNLABELED = "UNLABELED"


class MappingConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(slots=True)
class MonthlyPlanItem:
    """편집·재생성의 단위(Cell).

    `week_id is None`이면 monthly merged cell이다.
    `value`는 빈 문자열일 수 있고 그때 `cell_state`가 이유를 구분한다.
    """

    item_id: ItemId
    semantic_key: SemanticKey
    value: str
    generation: GenerationMethodDetail
    cell_state: CellState = CellState.EMPTY_VALID
    week_id: WeekId | None = None
    source_label: str | None = None
    label_variant: LabelVariant | None = None
    mapping_confidence: MappingConfidence | None = None
    evidence: list[EvidenceSource] = field(default_factory=list)
    audit: AuditTrail = field(default_factory=AuditTrail)

    def __post_init__(self) -> None:
        if self.week_id is not None and not isinstance(self.week_id, WeekId):
            raise TypeError(
                "MonthlyPlanItem.week_id는 WeekId여야 한다. "
                "문자열 순번을 주소로 쓰지 않는다."
            )
        if self.value.strip() and self.cell_state is not CellState.FILLED:
            raise ValueError(
                f"값이 있는 Cell의 cell_state는 FILLED여야 한다: "
                f"{self.semantic_key} / {self.cell_state.value}"
            )
        if not self.value.strip() and self.cell_state is CellState.FILLED:
            raise ValueError(
                f"값이 없는 Cell의 cell_state는 FILLED일 수 없다: {self.semantic_key}"
            )

    @property
    def is_merged_cell(self) -> bool:
        return self.week_id is None

    def evidence_of_type(self, source_type) -> list[EvidenceSource]:
        return [e for e in self.evidence if e.source_type is source_type]

    def snapshot(self) -> "MonthlyPlanItem":
        """비교용 얕은 복사. 보존 검증 테스트에서 사용한다."""
        return replace(
            self,
            evidence=list(self.evidence),
            audit=AuditTrail(list(self.audit.events)),
        )


@dataclass(slots=True)
class MonthlySection:
    """Template이 정의한 의미 Section 하나.

    `display_mode`는 Template instance가 지정한 값을 그대로 보존한다.
    코드가 전역 기본값으로 채우지 않는다(OD-M01).
    """

    semantic_key: SemanticKey
    section_key: str
    role: SectionRole
    display_mode: DisplayMode | None
    empty_value_policy: EmptyValuePolicy
    activated: bool = True
    parent_section_key: str | None = None
    source_label: str | None = None
    items: list[MonthlyPlanItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.role is SectionRole.AXIS and self.items:
            raise ValueError(
                f"AXIS Section은 Item을 갖지 않는다: {self.section_key}"
            )

    def item_for_week(self, week_id: str | None) -> MonthlyPlanItem | None:
        for item in self.items:
            current = item.week_id.value if item.week_id else None
            if current == week_id:
                return item
        return None


@dataclass(slots=True)
class ActivityCatalogLineage:
    """Plan을 생성할 때 실제로 사용한 Activity Catalog의 고정 주소.

    Regenerate는 이 값을 그대로 다시 해소해야 한다. 나중에 새 version이
    Production default가 되어도 기존 Plan의 재생성은 생성 당시 version을
    쓴다. `latest` 자동 승격이나 default fallback 경로를 만들지 않는다.

    `ParentYearlyLineage`의 `reference_catalog_id`는 **Theme** Catalog다.
    두 Reference는 서로 다른 축이므로 한 필드에 합치지 않는다.
    """

    catalog_id: str
    catalog_version: str

    def __post_init__(self) -> None:
        if not self.catalog_id.strip():
            raise ValueError("ActivityCatalogLineage.catalog_id는 필수다")
        if not self.catalog_version.strip():
            raise ValueError("ActivityCatalogLineage.catalog_version은 필수다")


@dataclass(slots=True)
class MonthlyPlan:
    """Monthly Plan Aggregate Root.

    Plan 소유 단위는 classroom이다(OD-Y03). 혼합연령도 classroom당 하나를 가진다.

    구조 불변식은 이 Aggregate가 아니라 Validation이 검사한다. Yearly와 같은
    이유로, 검증 테스트가 변형된 Fixture를 만들 수 있어야 하기 때문이다.
    상태 Gate(CONFIRMED read-only)는 이 Aggregate가 직접 막는다.
    """

    plan_id: PlanId
    school_year: int
    target_month: PeriodKey
    daycare_ref: str
    classroom_ref: str
    classroom_ages: frozenset[int]
    age_mode: str
    status: PlanStatus
    parent_lineage: ParentYearlyLineage
    template_ref: TemplateRef
    week_periods: tuple[WeekPeriod, ...] = ()
    sections: list[MonthlySection] = field(default_factory=list)
    constraint_assessments: tuple[ConstraintAssessment, ...] = ()
    audit: AuditTrail = field(default_factory=AuditTrail)
    activity_catalog: ActivityCatalogLineage | None = None
    """생성 시 사용한 Activity Catalog. **Optional이다.**

    M1 Plan과 Activity Reference 없이 생성한 Plan은 None이며, 그 Plan은
    outdoor Regenerate 대상이 아니다. 지금의 default Catalog를 임의로
    붙여 과거 Plan을 업그레이드하지 않는다. Migration은 별도 주제다.
    """

    # ------------------------------------------------------------- 조회

    @property
    def items(self) -> list[MonthlyPlanItem]:
        return [item for section in self.sections for item in section.items]

    @property
    def active_week_periods(self) -> tuple[WeekPeriod, ...]:
        """활성 WeekPeriod만. canonical 목록 자체는 그대로 보존된다."""
        return tuple(w for w in self.week_periods if w.active)

    def week_period(self, week_id: str) -> WeekPeriod | None:
        for week in self.week_periods:
            if week.week_id.value == week_id:
                return week
        return None

    def section(self, section_key: str) -> MonthlySection | None:
        for section in self.sections:
            if section.section_key == section_key:
                return section
        return None

    def find_cell(
        self,
        *,
        section_key: str | None = None,
        week_id: str | None = None,
        item_id: str | None = None,
    ) -> tuple[MonthlySection, MonthlyPlanItem] | None:
        """안정 주소로 Cell을 찾는다.

        `item_id` 우선. 없으면 `(section_key, week_id)`로 찾는다.
        `week_id=None`은 monthly merged cell을 뜻하며 "지정하지 않음"이 아니다.
        배열 순번은 주소로 받지 않는다.
        """
        for section in self.sections:
            for item in section.items:
                if item_id is not None:
                    if item.item_id.value == item_id:
                        return section, item
                    continue
                if section_key is not None and section.section_key == section_key:
                    current = item.week_id.value if item.week_id else None
                    if current == week_id:
                        return section, item
        return None

    def constraint(self, kind: ConstraintKind) -> ConstraintAssessment | None:
        for assessment in self.constraint_assessments:
            if assessment.kind is kind:
                return assessment
        return None

    @property
    def unresolved_constraints(self) -> tuple[ConstraintAssessment, ...]:
        return tuple(a for a in self.constraint_assessments if a.is_unresolved)

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
                "confirmed_monthly_plan_is_read_only",
                FailureCategory.PLAN_STATE_GATE,
                f"{operation}은 CONFIRMED Plan에서 허용되지 않는다",
            )

    # ------------------------------------------------------------- 변경

    def record(self, event: AuditEvent) -> None:
        """Plan-level Audit Event."""
        self.audit.append(event)

    def confirm(self, event: AuditEvent) -> None:
        """DRAFT를 CONFIRMED로 전이한다.

        **Confirm이 바꾸는 것은 status와 Plan-level Audit뿐이다.**
        parent_lineage / template_ref / week_periods / sections / Cell의 값·상태·
        generation·evidence / constraint_assessments는 건드리지 않는다.
        Confirm은 content transformation이 아니다.

        docs/screen-spec.md §8 / 2026-09-11 Product Contract:

            status = CONFIRMED
            = 교사가 해당 Monthly Plan의 작성 결과를 확정했다

            != 법정 안전교육 충족 / Safety placement 검증 완료 / 법률 준수 판정

        따라서 `ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED`와
        `PlanStatus.CONFIRMED`가 동시에 존재할 수 있다.
        """
        self.status = PlanStatus.CONFIRMED
        self.audit.append(event)
