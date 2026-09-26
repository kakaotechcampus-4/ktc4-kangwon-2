"""관찰 기록 API 의 요청·응답 모델. 계약은 docs/api-spec.md §10 이다.

이 파일도 `import datetime` 을 쓴다 — 칸 이름이 `date` 라 models.py 와 같은 이유다.
"""

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.features.observations.models import DOMAINS

# 목록을 다시 적지 않는다. models.py 의 CHECK 와 같은 튜플을 본다.
Domain = Literal[DOMAINS]  # type: ignore[valid-type]

# 공백만 있으면 422 (§10 「fact 는 필수다」). 길이는 계약이 정하지 않아 상한이 없다.
Fact = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# 선택이라 빈 문자열을 허용한다. 길이는 observations.context 컬럼(String(50))에 맞춘다.
Context = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]


class ObservationUpdate(BaseModel):
    """`PUT /api/observations/{id}`. 네 칸만 받는다.

    `class_id` · `child_id` 를 보내면 조용히 버리지 않고 422 로 드러낸다 — 대상이 바뀌면
    다른 기록이다. 삭제 후 재등록한다(§10).
    """

    model_config = ConfigDict(extra="forbid")

    date: datetime.date
    domain: Domain
    context: Context = ""
    fact: Fact


class ObservationCreate(ObservationUpdate):
    """`POST /api/observations`."""

    class_id: int
    child_id: int


class ObservationResponse(BaseModel):
    """반·아이 이름과 `child_code` 를 같이 준다 — 목록이 N+1 로 다시 부르지 않게(§10)."""

    id: int
    class_id: int
    class_name: str
    child_id: int
    child_name: str
    child_code: str
    date: datetime.date
    domain: str
    context: str
    fact: str
    created_at: datetime.datetime


class ObservationListResponse(BaseModel):
    items: list[ObservationResponse]
