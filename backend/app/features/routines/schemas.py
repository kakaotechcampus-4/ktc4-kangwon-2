"""일과 기록 API 의 요청·응답 모델. 계약은 docs/api-spec.md §10-1 이다.

`import datetime` 을 쓴다 — 칸 이름이 `date` 라 models.py 와 같은 이유다.
"""

import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class RoutineListResponse(BaseModel):
    items: list[RoutineResponse]
