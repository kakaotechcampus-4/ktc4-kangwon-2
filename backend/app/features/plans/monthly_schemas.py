"""월간계획안 API 의 요청 · 응답 모양. 계약은 docs/api-spec.md §9-1 이다.

**칸 수를 정하지 않는다.** 주 · Section · 칸은 서버가 준 만큼이다. 출처는 연간(§4)과 같은
`EvidenceOut` · `GenerationOut` 을 쓴다 — 세 축을 한 값에 섞지 않는다.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field, StrictStr

from app.features.plans.schemas import EvidenceOut, GenerationOut


class ProfileRefIn(BaseModel):
    profile_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)


class CreateMonthlyPlan(BaseModel):
    class_id: int
    month: int = Field(ge=1, le=12)
    profile_ref: ProfileRefIn


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
    weeks: list[WeekOut]
    sections: list[SectionOut]
    safety_candidates: list[SafetyCandidateOut]
    safety_weeks: list[SafetyWeekOut]
    drill_candidates: list[DrillCandidateOut]
    notices: list[NoticeOut]
    constraints: list[ConstraintOut]
    verification: VerificationOut
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
