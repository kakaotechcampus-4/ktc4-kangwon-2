"""놀이 중심 월간계획안 API 의 요청 · 응답 모양. 계약은 docs/api-spec.md §9-7 이다.

칸(Cell)의 출처는 연간(§4)과 같은 `EvidenceOut` · `GenerationOut` 이다. 싣지 않는 것:
Reference 판(`references`) · 지운 행(`removed_activities`) · 칸의 `semantic_key` · `audit`.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StrictInt, StrictStr, StringConstraints

from app.features.plans.monthly_schemas import RevisionIn
from app.features.plans.schemas import EvidenceOut, GenerationOut


def _no_duplicates(keys: list[str]) -> list[str]:
    if len(keys) != len(set(keys)):
        raise ValueError("같은 놀이를 두 번 고를 수 없습니다")
    return keys


# row_key 는 Core 가 `cand{번호}` 로 만든다
# (generate_play_project_plan.py:150, play_project_plan.py:67).
# 구간당 후보는 10개라 가장 긴 키는 `cand10` 의 6자다. 20 은 후보 수가 바뀌어도 받는 여유다.
# 개수는 부모 구간에서 고르는 놀이 수(5)와 같다 — 그보다 많이 강조할 수 없다.
_RowKey = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=20)
]


class CreatePlayMonthlyPlan(BaseModel):
    class_id: StrictInt
    month: Annotated[int, Field(strict=True, ge=1, le=12)]
    emphasized_row_keys: Annotated[
        list[_RowKey], Field(max_length=5), AfterValidator(_no_duplicates)
    ] = []


# ── 변경 (§9-7) ────────────────────────────────────────────────────────────


class EditCellIn(RevisionIn):
    # 본문이 JSONB 라 맞출 컬럼이 없다. 600자는 ADR-046 §6 (놀이형 연간 칸과 같다).
    # 빈 값을 받는다(칸을 비운다) — min_length 를 걸지 않고 공백만 든 값은 빈 값이 된다.
    value: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, max_length=600)]


# 누리과정 내용 ID 는 지금 판에서 가장 긴 것이 14자다(`nuri2019.3.3.2`, data/curriculum).
# 20 은 영역 · 범주 · 내용 번호가 두 자리가 되어도(`nuri2019.10.10.10`, 17자) 받는 여유다.
_ContentId = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=20)
]


class ContentIdsIn(RevisionIn):
    content_ids: Annotated[
        list[_ContentId],
        Field(min_length=1, max_length=3),
        AfterValidator(_no_duplicates),
    ]


class AddActivityIn(RevisionIn):
    section: Literal["together", "free_play"]


class SafetyWeekIn(RevisionIn):
    candidate_item_id: StrictStr | None  # 키는 필수 · 값만 null 일 수 있다


class PlayMonthlySummary(BaseModel):
    id: int
    class_id: int
    school_year: int
    month: int
    target_month: str
    status: str
    revision: int
    created_at: datetime
    confirmed_at: datetime | None


class PlayMonthlyListOut(BaseModel):
    items: list[PlayMonthlySummary]


class CellOut(BaseModel):
    item_id: str
    value: str
    evidence: list[EvidenceOut]
    generation: GenerationOut | None  # 한 번도 쓰지 않은 교사 입력 칸은 null


class WeekOut(BaseModel):
    week_id: str
    label: str
    start_date: date
    end_date: date
    active: bool


class ParentPlayOut(BaseModel):
    row_key: str
    play_name_item_id: str
    play_name: str
    materials: str
    support_direction: str
    emphasized: bool


class ParentOut(BaseModel):
    annual_plan_id: int
    period_key: str
    layout_version: str
    confirmed_at: datetime
    plays: list[ParentPlayOut]


class ActivityOut(BaseModel):
    activity_id: str
    name: CellOut
    description: CellOut
    content_ids: list[str]
    parent_item_id: str | None


class HabitOut(BaseModel):
    week_id: str
    entry_id: str | None
    cell: CellOut


class SafetyCandidateOut(BaseModel):
    kind: str
    category_id: str | None
    topic_group: str | None
    cell: CellOut


class SafetyWeekOut(BaseModel):
    week_id: str
    candidate_item_id: str | None


class EntryOut(BaseModel):
    entry_id: str | None
    cell: CellOut


class DrillCandidateOut(BaseModel):
    topic_id: str
    label: str
    cell: CellOut


class TeacherInputOut(BaseModel):
    key: str
    cell: CellOut


class NoticeOut(BaseModel):
    code: str
    week_id: str | None


class PlayMonthlyPlanOut(BaseModel):
    id: int
    class_id: int
    school_year: int
    month: int
    target_month: str
    status: str
    revision: int
    format: str
    format_version: str
    created_at: datetime
    confirmed_at: datetime | None
    target_ages: list[int]
    weeks: list[WeekOut]
    parent: ParentOut
    theme: CellOut
    rationale: CellOut
    together: list[ActivityOut]
    free_play: list[ActivityOut]
    habits: list[HabitOut]
    safety_candidates: list[SafetyCandidateOut]
    safety_weeks: list[SafetyWeekOut]
    health: EntryOut
    nutrition: EntryOut
    drill_candidates: list[DrillCandidateOut]
    teacher_inputs: list[TeacherInputOut]
    notices: list[NoticeOut]
