"""월간계획안 API 의 요청 · 응답 모양. 계약은 docs/api-spec.md §9-1 이다.

**칸 수를 정하지 않는다.** 주 · Section · 칸은 서버가 준 만큼이다. 출처는 연간(§4)과 같은
`EvidenceOut` · `GenerationOut` 을 쓴다 — 세 축을 한 값에 섞지 않는다.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, StrictStr

from app.features.plans.schemas import EvidenceOut, GenerationOut, MemoIn, MemoNoticeOut


class ProfileRefIn(BaseModel):
    profile_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)


class CreateMonthlyPlan(BaseModel):
    class_id: int
    month: int = Field(ge=1, le=12)
    profile_ref: ProfileRefIn
    memo: MemoIn = ""


class ProfileRefOut(BaseModel):
    profile_id: str
    profile_version: str


class TemplateRefOut(BaseModel):
    template_id: str
    template_version: str


class ParentOut(BaseModel):
    annual_plan_id: int
    theme: str | None
    confirmed_at: datetime


class WeekOut(BaseModel):
    week_id: str
    label: str
    start_date: date
    end_date: date
    active: bool


class CellOut(BaseModel):
    item_id: str
    week_id: str | None
    value: str
    state: str
    evidence: list[EvidenceOut]
    # 훈련 문서 칸은 교사가 쓰거나 후보를 복사하기 전까지 생성 방식이 없다. 다른 칸은 늘 있다.
    generation: GenerationOut | None


class SectionOut(BaseModel):
    section_key: str
    label: str | None
    role: str
    repeat_by: str | None
    visible: bool
    order: int
    semantic_variant: str | None
    cells: list[CellOut]


class ConstraintOut(BaseModel):
    code: str
    verification: str
    affected_section_keys: list[str]
    required_source_kinds: list[str]
    rule_version: str
    detail: str


class RuleRefOut(BaseModel):
    rule_id: str
    rule_version: str


class FindingOut(BaseModel):
    code: str
    kind: str
    severity: str
    section_key: str | None
    week_id: str | None
    message: str


class VerificationOut(BaseModel):
    executed_rules: list[RuleRefOut]
    findings: list[FindingOut]


class SafetyCandidateOut(BaseModel):
    kind: str
    category_id: str | None
    topic_group: str | None
    cell: CellOut


class DrillCandidateOut(BaseModel):
    topic_id: str
    label: str
    cell: CellOut


class SafetyWeekOut(BaseModel):
    week_id: str
    candidate_item_id: str | None
    display_value: str


class NoticeOut(BaseModel):
    code: str
    week_id: str


class TableCellOut(BaseModel):
    """교사 표 칸 하나 — 놀이 월간 `CellOut` 과 같은 모양. 처음 쓰기 전에는 generation 이 null."""

    item_id: str
    value: str
    evidence: list[EvidenceOut]
    generation: GenerationOut | None


class TablePartOut(BaseModel):
    """한 열의 나눔 트리 — 놀이 월간 `TimetablePartOut` 과 같은 모양(ADR-047)."""

    cell: TableCellOut | None = None
    split_id: str | None = None
    axis: Literal["VERTICAL", "HORIZONTAL"] | None = None
    ratio: int | None = None
    children: list["TablePartOut"] = Field(default_factory=list)


class TeacherTableOut(BaseModel):
    """한글 양식 끝의 교사가 적는 표(Human Decision 2026-11-05). 계획안이 만들지 않는다."""

    table_key: Literal["event_schedule", "specialized_timetable", "special_activity_timetable"]
    label: str  # 양식의 이름(source_label)
    titles: list[TableCellOut]  # 특성화 시간표의 열 제목 칸. 다른 표는 빈 목록
    columns: list[TablePartOut]
    column_widths: list[int]  # 표 폭의 %
    height_mm: int


class MonthlyPlanOut(BaseModel):
    id: int
    class_id: int
    school_year: int
    month: int
    target_month: str
    status: str
    revision: int
    generation_mode: str
    profile_ref: ProfileRefOut
    base_template_ref: TemplateRefOut
    parent: ParentOut
    parent_changed: bool = Field(
        description="부모 연간이 지금 확정이 아니거나 확정 시각이 parent.confirmed_at 과 다르다"
    )
    weeks: list[WeekOut]
    sections: list[SectionOut]
    safety_candidates: list[SafetyCandidateOut]
    safety_weeks: list[SafetyWeekOut]
    drill_candidates: list[DrillCandidateOut]
    teacher_tables: list[TeacherTableOut] = []
    notices: list[NoticeOut]
    constraints: list[ConstraintOut]
    verification: VerificationOut
    memo: str = ""
    memo_notices: list[MemoNoticeOut] = []
    created_at: datetime
    confirmed_at: datetime | None


class MonthlyPlanSummary(BaseModel):
    id: int
    class_id: int
    school_year: int
    month: int
    target_month: str
    status: str
    revision: int
    profile_ref: ProfileRefOut
    created_at: datetime
    confirmed_at: datetime | None


class MonthlyPlanListOut(BaseModel):
    items: list[MonthlyPlanSummary]


class RevisionIn(BaseModel):
    """읽을 때 받은 revision. 서버 값과 다르면 409 `STALE_WRITE` (결정 문서 12.4 D-3)."""

    expected_revision: int = Field(ge=1, strict=True)


class SafetyWeekIn(RevisionIn):
    # 키는 필수 · 값만 null 일 수 있다(null 이면 그 주를 비운다)
    candidate_item_id: StrictStr | None


class TableSizeIn(RevisionIn):
    table_key: Literal["event_schedule", "specialized_timetable", "special_activity_timetable"]
    column_widths: list[StrictInt]
    height_mm: StrictInt


class EditMonthlyCell(RevisionIn):
    value: str = Field(strict=True)


# ── 변경 이력 (§9-5) ──────────────────────────────────────────────────────


class ValueChangeOut(BaseModel):
    before: str
    after: str


class GenerationChangeOut(BaseModel):
    before: GenerationOut
    after: GenerationOut


class ArrangementChangeOut(BaseModel):
    """배치가 바뀐 범위(scope)와 그 앞뒤 id. 안전 배치면 scope 는 주 id 다."""

    scope: str
    before: list[str]
    after: list[str]


class MonthlyAuditEventOut(BaseModel):
    """저장된 Core `AuditEvent` 하나. 저장되지 않은 것(이전 근거 · 이벤트별 revision)은 없다."""

    type: str
    occurred_at: datetime
    scope: str = Field(description="PLAN(계획안 단위) | CELL(칸 단위)")
    item_id: str | None = Field(description="CELL 이면 그 칸. PLAN 이면 null")
    section_key: str | None = Field(description="CELL 이면 그 칸의 Section. PLAN 이면 null")
    week_id: str | None = Field(description="주마다 있는 칸이면 그 주. 한 달 칸 · PLAN 이면 null")
    day: str | None = Field(
        default=None, description="주간 요일 칸이면 그 요일(MON…SAT). 그 밖 · 월간 · PLAN 이면 null"
    )
    actor: str | None = Field(description="사람이면 opaque id(user_7). 시스템이면 null")
    system_actor: str | None = Field(description="시스템이면 그 표시. 사람이면 null")
    value_change: ValueChangeOut | None = Field(
        description="TEACHER_EDITED · REGENERATED · CANDIDATE_COPIED 만"
    )
    generation_change: GenerationChangeOut | None = Field(
        description="REGENERATED · CANDIDATE_COPIED(덮은 칸에 생성 방식이 있었을 때) 만"
    )
    arrangement_change: ArrangementChangeOut | None = Field(
        default=None, description="ARRANGEMENT_CHANGED 만"
    )
    copied_from: str | None = Field(default=None, description="CANDIDATE_COPIED 만")


class MonthlyAuditOut(BaseModel):
    items: list[MonthlyAuditEventOut]
