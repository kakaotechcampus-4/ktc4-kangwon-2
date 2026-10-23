"""주간계획안 API 의 요청 · 응답 모양. 계약은 docs/api-spec.md §9-6 이다.

월간(§9-1) 응답 틀을 그대로 쓰고 주간 필드만 더한다. 주간은 Section 당 칸 하나다.
"""

from datetime import date, datetime

from pydantic import BaseModel

from app.features.plans.monthly_schemas import ConstraintOut, TemplateRefOut, VerificationOut
from app.features.plans.schemas import EvidenceOut, GenerationOut


class CreateWeeklyPlan(BaseModel):
    class_id: int
    week_id: str


class WeeklyParentOut(BaseModel):
    monthly_plan_id: int
    theme: str | None
    confirmed_at: datetime


class WeekPeriodOut(BaseModel):
    label: str
    start_date: date
    end_date: date


class ParentSnapshotOut(BaseModel):
    """이 칸이 이어받은 부모 월간 칸과 그때의 값(주간 계약 §5-3)."""

    parent_item_id: str
    snapshot_value: str


class WeeklyCellOut(BaseModel):
    item_id: str
    value: str
    state: str
    evidence: list[EvidenceOut]
    # 교사 입력 칸은 첫 입력 전에 만든 방식이 없다(주간 계약 §10-2) — null 이다.
    generation: GenerationOut | None
    parent_snapshots: list[ParentSnapshotOut]
    # 교사가 쓰는 칸(가정연계 · 행사 · 특별활동). 첫 입력 뒤 generation 이 MANUAL 이 되므로
    # generation == null 로는 가를 수 없다. 화면은 이 값으로 재생성 버튼을 숨긴다.
    teacher_input: bool


class WeeklySectionOut(BaseModel):
    section_key: str
    label: str | None
    role: str
    visible: bool
    order: int
    semantic_variant: str | None
    cells: list[WeeklyCellOut]


class WeeklyPlanOut(BaseModel):
    id: int
    class_id: int
    school_year: int
    week_id: str
    target_month: str
    status: str
    revision: int
    generation_mode: str
    week_period: WeekPeriodOut
    operating_days: list[str]
    display_end_date: date
    base_template_ref: TemplateRefOut
    parent: WeeklyParentOut
    sections: list[WeeklySectionOut]
    constraints: list[ConstraintOut]
    verification: VerificationOut
    created_at: datetime
    confirmed_at: datetime | None


class WeeklyPlanSummary(BaseModel):
    id: int
    class_id: int
    school_year: int
    week_id: str
    target_month: str
    status: str
    revision: int
    created_at: datetime
    confirmed_at: datetime | None


class WeeklyPlanListOut(BaseModel):
    items: list[WeeklyPlanSummary]
