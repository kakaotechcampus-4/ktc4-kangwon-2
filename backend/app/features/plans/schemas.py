"""연간계획안 API 의 요청·응답. 계약은 docs/api-spec.md §4~§7 이다."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceOut(BaseModel):
    """이 칸이 무엇을 근거로 만들어졌나 (§4 「출처는 세 축이다」)."""

    source_type: str
    source_id: str
    source_version: str | None = None
    effective_date: date | None = None
    display_name: str | None = None


class GenerationOut(BaseModel):
    """이 칸을 무엇이 만들었나. 근거와 다른 축이라 섞지 않는다."""

    method: str
    rule_id: str | None = None
    rule_version: str | None = None


class MonthOut(BaseModel):
    month: int
    theme: str
    sub_themes: list[str]
    safety_education: list[str]
    safety_education_state: str
    evidence: list[EvidenceOut]
    generation: GenerationOut


class CheckOut(BaseModel):
    """검사기가 찾은 한 건. `detail` 은 교사에게 그대로 보여도 되는 문장이다."""

    rule: str
    severity: str
    detail: str
    month: int | None = None


class AnnualPlanOut(BaseModel):
    id: int
    class_id: int
    school_year: int
    status: str
    months: list[MonthOut]
    # **빈 배열을 「통과」로 읽으면 안 된다.** 무엇을 검사했는지가 checked_rules 다.
    checked_rules: list[str]
    checks: list[CheckOut]


class AnnualPlanSummary(BaseModel):
    """목록용. months 12개를 넣지 않는다 — 상세는 단건 조회가 준다(§5)."""

    id: int
    class_id: int
    school_year: int
    status: str
    created_at: datetime
    confirmed_at: datetime | None = None


class AnnualPlanListOut(BaseModel):
    items: list[AnnualPlanSummary]


class CreateAnnualPlan(BaseModel):
    """`school_year` 를 받지 않는다 — class_id 가 학년도를 결정한다(§4)."""

    model_config = ConfigDict(extra="forbid")

    class_id: int
    form_id: int | None = None


class UpdateMonth(BaseModel):
    """**둘 다 필수다.** 전체 교체라 하나만 보내면 나머지가 조용히 사라진다(§6)."""

    model_config = ConfigDict(extra="forbid")

    theme: str = Field(min_length=1)
    sub_themes: list[str]


class ConfirmOut(BaseModel):
    id: int
    status: str
    confirmed_at: datetime


class AuditEventOut(BaseModel):
    type: str
    occurred_at: datetime
    month: int | None = Field(
        default=None, description="칸 단위 사건이면 그 달. 계획안 단위면 null"
    )
    actor: str | None = None
    system_actor: str | None = None


class AuditOut(BaseModel):
    items: list[AuditEventOut]
