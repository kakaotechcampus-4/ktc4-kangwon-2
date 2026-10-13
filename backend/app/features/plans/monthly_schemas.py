"""월간계획안 API 의 요청 · 응답 모양. 계약은 docs/api-spec.md §9-1 이다.

**칸 수를 정하지 않는다.** 주 · Section · 칸은 서버가 준 만큼이다. 출처는 연간(§4)과 같은
`EvidenceOut` · `GenerationOut` 을 쓴다 — 세 축을 한 값에 섞지 않는다.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

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
    generation: GenerationOut


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


class EditMonthlyCell(RevisionIn):
    value: str = Field(strict=True)
