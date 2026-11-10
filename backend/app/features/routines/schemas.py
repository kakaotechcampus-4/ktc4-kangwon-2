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
    created_at: datetime.datetime


class DayWeatherResponse(BaseModel):
    """그날 날씨 (ADR-089). `source` 는 `sky` 의 출처다 — 미세먼지는 늘 자동이거나 없다."""

    date: datetime.date
    sky: str | None
    dust: str | None
    source: Literal["auto", "teacher", "none"]
    indoor_hint: Literal["rain", "dust"] | None


class RoutineListResponse(BaseModel):
    items: list[RoutineResponse]
    # 반 하나 · 하루 하나(`class_id` · `from == to`)로 불렀을 때만 온다. 그 밖은 null.
    weather: DayWeatherResponse | None = None


class WeatherChoice(BaseModel):
    """`PUT /api/routines/weather`. 교사가 고른 그날 날씨.

    `sky: null` 이면 고른 것을 지워 자동 값으로 돌린다.
    """

    model_config = ConfigDict(extra="forbid")

    class_id: int
    date: datetime.date
    sky: Literal[SKIES] | None


class RoutineReviewImpact(BaseModel):
    """직접 영향을 받은 확정 일일 보육일지 ID. 기존 stale과 새 stale을 구분한다."""

    affected_document_ids: list[int]
    newly_stale_document_ids: list[int]


class RoutineMutationResponse(RoutineResponse):
    review_impact: RoutineReviewImpact


class RoutineDeleteResponse(BaseModel):
    review_impact: RoutineReviewImpact
