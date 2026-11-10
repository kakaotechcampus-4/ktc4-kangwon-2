"""관찰 기록 API 의 요청·응답 모델. 계약은 docs/api-spec.md §10 이다.

이 파일도 `import datetime` 을 쓴다 — 칸 이름이 `date` 라 models.py 와 같은 이유다.
"""

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.features.observations.models import DOMAINS

# 목록을 다시 적지 않는다. models.py 의 CHECK 와 같은 튜플을 본다.
Domain = Literal[DOMAINS]  # type: ignore[valid-type]

# 공백만 있으면 422 (§10 「fact 는 필수다」). 컬럼이 Text 라 맞출 길이가 없어 상한 5,000자는
# 화면 입력칸(RecordsPage 「본 대로 적기」 maxLength 5000) · 일과 기록 Body 와 같게 둔다.
# 이 글이 그대로 일지 초안 LLM 으로 간다 — 화면을 거치지 않은 긴 글이 들어오지 않게 여기서 막는다.
Fact = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
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


class ReviewImpact(BaseModel):
    """이 기록을 직접 인용한 확정 문서 ID. 이미 stale 이던 것과 이번에 stale 이 된 것을 나눈다.

    일과 기록의 `RoutineReviewImpact` 와 같은 모양이다 — 화면이 같은 문구로 센다(§10).
    """

    affected_document_ids: list[int]
    newly_stale_document_ids: list[int]


class ObservationMutationResponse(ObservationResponse):
    review_impact: ReviewImpact


class ObservationDeleteResponse(BaseModel):
    review_impact: ReviewImpact


# jev 에 보내는 사실 한 칸의 상한. 화면 입력칸(maxLength 5000)과 같은 선이다 — 저장 칸(Text)은
# 상한이 없지만 모델에 보내는 글은 길수록 값이 들고 느려진다(ADR-082).
SuggestFact = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class DomainSuggestRequest(BaseModel):
    """`POST /api/observations/domain-suggest`. 아직 저장하지 않은 글을 받는다."""

    model_config = ConfigDict(extra="forbid")

    class_id: int
    fact: SuggestFact
    context: Context = ""


class DomainSuggestResponse(BaseModel):
    """`domain` 이 있으면 화면이 그 칩에 보라 점선을 친다 — 고르는 것은 교사다.

    확신이 모자라면 `domain` 만 비고 `confidence` 는 온다.
    묻지 않았으면(mock · 2축 · 실패) 둘 다 null 이다.
    """

    domain: str | None
    confidence: float | None


class MissingResponse(BaseModel):
    """빠진 것 이름 — 「상황」 「행동」 「반응」 중에서 그 순서로. 없거나 묻지 않았으면 빈 목록."""

    missing: list[Literal["상황", "행동", "반응"]]
