"""놀이 중심 월간계획안 API 의 요청 · 응답 모양. 계약은 docs/api-spec.md §9-7 이다.

칸(Cell)의 출처는 연간(§4)과 같은 `EvidenceOut` · `GenerationOut` 이다. 싣지 않는 것:
Reference 판(`references`) · 지운 행(`removed_activities`) · 칸의 `semantic_key` · `audit`.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StrictInt, StrictStr, StringConstraints

from app.features.plans.monthly_schemas import GenerationChangeOut, RevisionIn, ValueChangeOut
from app.features.plans.schemas import EvidenceOut, GenerationOut, MemoIn, MemoNoticeOut


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
    memo: MemoIn = ""


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


class ActivityOrderIn(RevisionIn):
    """한 목록의 줄(이름 칸 item_id)을 새 순서대로. 그 목록의 줄을 빠짐없이 한 번씩."""

    section: Literal["together", "free_play"]
    item_ids: list[StrictStr]


class HabitOrderIn(RevisionIn):
    """기본생활습관 칸(item_id)을 새 주 순서대로. 습관 칸을 빠짐없이 한 번씩(2026-11-06)."""

    item_ids: list[StrictStr]


class SplitTimetableIn(RevisionIn):
    axis: Literal["VERTICAL", "HORIZONTAL"]


class TimetableRatioIn(RevisionIn):
    ratio: StrictInt


class TimetableSizeIn(RevisionIn):
    column_widths: list[StrictInt]
    height_mm: StrictInt


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


class PooledActivityOut(ActivityOut):
    """문서에 넣지 않은 AI 후보(layout v0.3.0). 고르기 전에는 고칠 수 없다."""

    section: Literal["together", "free_play"]


class HabitOut(BaseModel):
    week_id: str
    entry_id: str | None
    # 한글 문서가 「[분류]」로 찍는 일상생활 항목 이름(하민 결정 2026-11-06).
    # 문장이 비었거나 항목에서 고르지 않았으면 "".
    label: str = ""
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


class TimetablePartOut(BaseModel):
    """특별활동 시간표 한 요일의 나눔 트리(ADR-047). 칸이면 `cell` 만, 경계면 나머지 넷만 온다.

    `VERTICAL` 은 위아래, `HORIZONTAL` 은 좌우이고 `ratio` 는 첫 갈래(위 · 왼쪽)의 % 다.
    """

    cell: CellOut | None = None
    split_id: str | None = None
    axis: Literal["VERTICAL", "HORIZONTAL"] | None = None
    ratio: int | None = None
    children: list["TimetablePartOut"] = Field(default_factory=list)


class TimetableSizeOut(BaseModel):
    column_widths: list[int]  # 월~금, 표 폭의 %
    height_mm: int


class NoticeOut(BaseModel):
    code: str
    week_id: str | None


class DisplayOut(BaseModel):
    """문서 머리 표시 칸(layout v0.2.0 D-2). 생성 때 한 번 옮겨 적고 그 뒤로는 교사 글이다.
    빈 값도 된다. 고쳐도 반 · 연령 · 달 · 주는 바뀌지 않는다. 한글 내려받기가 같은 값을 쓴다."""

    title: CellOut  # 「11월 놀이계획안」
    age: CellOut  # 「만 4·5세」
    class_name: CellOut
    period: CellOut  # 「2026.11.01 ~ 2026.11.30」


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
    parent_changed: bool = Field(
        description="부모 연간이 지금 확정이 아니거나 확정 시각이 parent.confirmed_at 과 다르다"
    )
    theme: CellOut
    rationale: CellOut
    together: list[ActivityOut]
    free_play: list[ActivityOut]
    # layout v0.3.0(2026-11-06): AI 후보 8개씩 중 칸마다 정확히 `activity_pick` 개를 문서에 둔다.
    # 옛 계획안은 null · 빈 목록이다. `activity_candidates` 는 후보 이름 칸 id 의 생성 순서.
    activity_pick: int | None = None
    activity_candidates: list[str] = []
    activity_pool: list[PooledActivityOut] = []
    # 가운데 「예상되는 놀이 방향」 — 생성 때 주제를 옮겨 적은 뒤 따로 고친다(D-6).
    direction: CellOut
    display: DisplayOut
    habits: list[HabitOut]
    safety_candidates: list[SafetyCandidateOut]
    safety_weeks: list[SafetyWeekOut]
    health: EntryOut
    nutrition: EntryOut
    drill_candidates: list[DrillCandidateOut]
    teacher_inputs: list[TeacherInputOut]
    # 특성화 시간표 — 제목 5칸 다음 내용 5칸(같은 열끼리 위아래).
    specialized_timetable: list[CellOut]
    # 특별활동 시간표 — 월~금 다섯 요일의 나눔 트리와 크기.
    special_activity: list[TimetablePartOut]
    special_activity_size: TimetableSizeOut
    notices: list[NoticeOut]
    memo: str = ""
    memo_notices: list[MemoNoticeOut] = []


# ── 변경 이력 (§9-7) ───────────────────────────────────────────────────────


class LinkChangeOut(BaseModel):
    before: list[str]
    after: list[str]
    catalog_version: str


class ArrangementChangeOut(BaseModel):
    scope: str
    before: list[str]
    after: list[str]


class PlayMonthlyAuditEventOut(BaseModel):
    """키 12개가 늘 온다. 해당이 없으면 null 이다."""

    type: str
    occurred_at: datetime
    scope: str
    item_id: str | None
    actor: str | None
    system_actor: str | None
    value_change: ValueChangeOut | None
    generation_change: GenerationChangeOut | None
    link_change: LinkChangeOut | None
    arrangement_change: ArrangementChangeOut | None
    copied_from: str | None
    # 시간표 나누기 · 지우기 · 크기(TIMETABLE_CHANGED). 크기는 앞뒤 숫자다.
    timetable_change: dict | None = None


class PlayMonthlyAuditOut(BaseModel):
    items: list[PlayMonthlyAuditEventOut]
