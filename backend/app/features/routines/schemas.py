"""일과 기록 API 의 요청·응답 모델. 계약은 docs/api-spec.md §10-1 이다.

`import datetime` 을 쓴다 — 칸 이름이 `date` 라 models.py 와 같은 이유다.
"""

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.features.routines.models import SKIES

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class RoutineUpdate(BaseModel):
    """`PUT /api/routines/{id}`. 통째로 바꾼다 — 시간을 안 보내면 지워진다.

    `class_id` 를 보내면 조용히 버리지 않고 422 로 드러낸다 — 반이 바뀌면 다른 기록이다.
    """

    model_config = ConfigDict(extra="forbid")

    date: datetime.date
    position: Annotated[int, Field(ge=0)] = 0
    start: datetime.time | None = None
    end: datetime.time | None = None
    name: Name
    plan: Body = ""
    execution: Body = ""

    @model_validator(mode="after")
    def _time_range(self):
        if self.start and self.end and self.start >= self.end:
            raise ValueError("시작은 끝보다 앞이어야 합니다")
        return self


class RoutineCreate(RoutineUpdate):
    """`POST /api/routines`."""

    class_id: int


class RoutineResponse(BaseModel):
    id: int
    class_id: int
    class_name: str
    date: datetime.date
    position: int
    start: datetime.time | None
    end: datetime.time | None
    name: str
    plan: str
    execution: str
    reflected: bool = False
    activities: list[str] = []
    created_at: datetime.datetime


class DayWeatherResponse(BaseModel):
    """그날 날씨 (ADR-089). `source` 는 `sky` 의 출처다 — 미세먼지는 늘 자동이거나 없다."""

    date: datetime.date
    sky: str | None
    dust: str | None
    source: Literal["auto", "teacher", "none"]
    indoor_hint: Literal["rain", "dust"] | None


class DraftRow(BaseModel):
    """임시본 한 줄 — 화면 줄 그대로다 (ADR-084).

    이름이 비어도 받는다. 쓰다 만 줄이 있어도 임시본은 남아야 한다 — 올릴 때만 막는다.
    """

    model_config = ConfigDict(extra="forbid")

    # 이 줄이 이미 올라간 일과 기록이면 그 번호. 아직이면 null.
    id: Annotated[int, Field(gt=0)] | None = None
    start: datetime.time | None = None
    end: datetime.time | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""
    plan: Body = ""
    execution: Body = ""
    # 깔아 둔 줄은 교사가 손대기 전까지 올리지 않는다.
    touched: bool = False
    # 어제 지원을 반영한 줄 · 계획안에서 맞다고 한 활동 이름. 사실 칸이 아니다 (ADR-086).
    reflected: bool = False
    activities: Annotated[list[Name], Field(max_length=10)] = []


class DraftSave(BaseModel):
    """`PUT /api/routines/draft`. 하루치 화면을 통째로 둔다.

    `promote` 면 같은 요청에서 근거로 올린다.
    """

    model_config = ConfigDict(extra="forbid")

    class_id: int
    date: datetime.date
    # 마지막으로 받은 판 번호. 처음이면 0. 다르면 409 STALE_WRITE.
    expected_revision: Annotated[int, Field(ge=0)]
    # 하루 줄 수. 공식 양식이 10~13행이라 넉넉히 잡았다 — JSONB 라 맞출 칸 길이가 없다.
    rows: Annotated[list[DraftRow], Field(max_length=40)]
    removed: Annotated[list[Annotated[int, Field(gt=0)]], Field(max_length=40)] = []
    promote: bool = False


class DraftResponse(BaseModel):
    class_id: int
    date: datetime.date
    revision: int
    rows: list[DraftRow]
    removed: list[int]
    promoted: bool
    updated_at: datetime.datetime


class RoutineReviewImpact(BaseModel):
    """직접 영향을 받은 확정 일일 보육일지 ID. 기존 stale과 새 stale을 구분한다."""

    affected_document_ids: list[int]
    newly_stale_document_ids: list[int]


class DraftSaveResponse(BaseModel):
    draft: DraftResponse
    # 올렸을 때만 온다 — 그날 일과 기록 전부와, 이번에 바뀐 근거가 걸린 확정 일지.
    items: list[RoutineResponse] | None = None
    review_impact: RoutineReviewImpact | None = None


class TemplateRow(BaseModel):
    """반 기본 일과표 한 줄. `weekday` 가 있으면 그 요일에만 더한다 (0=월 … 5=토)."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    start: datetime.time | None = None
    end: datetime.time | None = None
    weekday: Annotated[int, Field(ge=0, le=5)] | None = None

    @model_validator(mode="after")
    def _time_range(self):
        if self.start and self.end and self.start >= self.end:
            raise ValueError("시작은 끝보다 앞이어야 합니다")
        return self


class TemplateSave(BaseModel):
    """`PUT /api/routines/template`. 표를 통째로 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    class_id: int
    rows: Annotated[list[TemplateRow], Field(max_length=40)]


class TemplateResponse(BaseModel):
    class_id: int
    rows: list[TemplateRow]
    updated_at: datetime.datetime


class PresetRow(BaseModel):
    name: str
    start: datetime.time | None
    end: datetime.time | None


class DayPreset(BaseModel):
    """그날 적은 줄이 없을 때 깔 줄. 반 기본 일과표 → 지난주 같은 요일 → 가장 최근 기록일."""

    source: Literal["template", "last_week", "recent"]
    # 일과 기록에서 가져왔으면 그 날. 기본 일과표면 null.
    from_date: datetime.date | None
    rows: list[PresetRow]


class RoutineListResponse(BaseModel):
    items: list[RoutineResponse]
    # 아래 둘은 반 하나 · 하루 하나(`class_id` · `from == to`)로 불렀을 때만 온다. 그 밖은 null.
    weather: DayWeatherResponse | None = None
    draft: DraftResponse | None = None
    # 그날 적은 줄이 없을 때만 온다. 깔 것도 없으면 null — 화면이 표준 일과를 깐다.
    preset: DayPreset | None = None


class WeatherChoice(BaseModel):
    """`PUT /api/routines/weather`. 교사가 고른 그날 날씨.

    `sky: null` 이면 고른 것을 지워 자동 값으로 돌린다.
    """

    model_config = ConfigDict(extra="forbid")

    class_id: int
    date: datetime.date
    sky: Literal[SKIES] | None


class RoutineMutationResponse(RoutineResponse):
    review_impact: RoutineReviewImpact


class RoutineDeleteResponse(BaseModel):
    review_impact: RoutineReviewImpact
