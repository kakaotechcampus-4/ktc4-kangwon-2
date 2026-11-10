"""아동 명단 API 의 요청·응답 모델. 계약은 docs/api-spec.md §2-1 이다."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, computed_field

from app.shared.childCode import one_syllable

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
    # 외자 아이(김민)만 받는다. 교사가 글에 쓰는 꼴(민이)이다 — 가명표에 넣는다(ADR-004 보완).
    call_name: ChildName | None = None


class ChildUpdate(BaseModel):
    """`PATCH /api/children/{id}` 요청. 부르는 이름만 고친다 — 이름 수정은 P1 이다(§2-1).

    null 이면 지운다.
    """

    model_config = ConfigDict(extra="forbid")

    call_name: ChildName | None


class ChildResponse(BaseModel):
    """`code` 를 응답에 포함한다 — 화면이 배지로 보여준다(§2-1).

    교사가 "LLM 에는 이 이름이 나간다" 를 알아야 한다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    name: str
    code: str
    call_name: str | None
    created_at: datetime

    # pydantic 은 @computed_field 를 @property 위에 얹으라고 하는데 mypy 는 이 순서를 막는다.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def needs_call_name(self) -> bool:
        """외자 아이인가. 화면이 이 값으로 「부르는 이름」 칸을 띄운다 — 판별은 서버 한 곳."""
        return one_syllable(self.name) is not None


class ChildListResponse(BaseModel):
    """목록 봉투는 `{ items }` 하나로 통일한다 (§2-1).

    `count` 를 따로 보내지 않는다 — `items.length` 로 알 수 있고
    `child_count`(반의 목표 원아 수)와 이름이 비슷해 혼동된다.
    """

    items: list[ChildResponse]


class ChildTracking(BaseModel):
    """아이 한 명의 관찰 기록 집계 (§2-1 발달 추적).

    **수만 센다.** 발달 수준을 판정하지 않는다 — 판정은 ADR-007 이 스펙아웃한 발달평가다.
    `by_domain` 은 5영역을 늘 다 담는다. 0 인 영역이 「덜 본 영역」이다.
    """

    child_id: int
    name: str
    code: str
    total: int
    last_date: date | None
    by_domain: dict[str, int]


class ChildTrackingResponse(BaseModel):
    items: list[ChildTracking]
