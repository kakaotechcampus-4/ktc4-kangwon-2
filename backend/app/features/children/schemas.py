"""아동 명단 API 의 요청·응답 모델. 계약은 docs/api-spec.md §2-1 이다."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# 빈 문자열과 공백만 있는 입력을 막는다. 길이는 children.name 컬럼(String(50))에 맞춘다.
ChildName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ChildCreate(BaseModel):
    """`POST /api/classes/{class_id}/children` 요청.

    **이름 하나만 받는다** — 생년월일·성별·건강정보를 받지 않는다 (ADR-004).
    `code` 도 받지 않는다. 서버가 등록 시점에 발급한다(§2-1) — 클라이언트가 보내면
    조용히 버리지 않고 422 로 드러낸다.
    """

    model_config = ConfigDict(extra="forbid")

    name: ChildName


class ChildResponse(BaseModel):
    """`code` 를 응답에 포함한다 — 화면이 배지로 보여준다(§2-1).

    교사가 "LLM 에는 이 이름이 나간다" 를 알아야 한다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    code: str
    created_at: datetime


class ChildListResponse(BaseModel):
    """목록 봉투는 `{ items }` 하나로 통일한다 (§2-1).

    `count` 를 따로 보내지 않는다 — `items.length` 로 알 수 있고
    `child_count`(반의 목표 원아 수)와 이름이 비슷해 혼동된다.
    """

    items: list[ChildResponse]
