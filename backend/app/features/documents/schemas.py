"""문서(일지 계열) API 의 요청·응답 모델. 계약은 docs/api-spec.md §11 이다."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DocumentGeneration(BaseModel):
    """`RULE_LLM` 처럼 어떻게 만들어졌나. origin 이 AI 가 아니면 셋 다 `None` 이다."""

    method: str | None
    rule_id: str | None
    rule_version: str | None


class DocumentListItem(BaseModel):
    """`GET /api/documents` 의 항목 하나.

    `sections` · `sources` 는 담지 않는다 — 목록이라 무거워진다(docs/api-spec.md §11).
    대신 `sources_count` 를 준다. 단건 조회(`GET /api/documents/{id}`)가 상세를 준다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    class_id: int
    class_name: str
    child_id: int | None
    child_name: str | None
    start: date
    end: date
    status: str
    origin: str
    stale: bool
    generation: DocumentGeneration
    sources_count: int
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """목록 봉투는 `{ items }` 하나로 통일한다 (docs/api-spec.md 「공통」 관례)."""

    items: list[DocumentListItem]


class DocumentSectionItem(BaseModel):
    """`사실` · `해석` · `지원` 항목 하나. 단건 조회·`PUT` 응답에 담긴다."""

    heading: Literal["사실", "해석", "지원"]
    body: str
    source_ids: list[int]


class DocumentSourceItem(BaseModel):
    """근거 원문 사본 하나. `id` 는 `document_sources.id` 가 아니라 `source_id` 다 —

    `sections[].source_ids` 가 가리키는 값과 같은 값이어야 화면이 근거를 찾을 수 있다.
    """

    id: int
    date: date | None
    text: str
    class_id: int
    child_id: int | None


class DocumentDetailResponse(BaseModel):
    """단건 조회·`PUT` 응답. 목록과 달리 `sections` · `sources` 를 담는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    class_id: int
    class_name: str
    child_id: int | None
    child_name: str | None
    start: date
    end: date
    status: str
    origin: str
    stale: bool
    sections: list[DocumentSectionItem]
    sources: list[DocumentSourceItem]
    generation: DocumentGeneration
    review_note: str
    created_at: datetime
    updated_at: datetime


class DocumentSectionUpdate(BaseModel):
    """`PUT` 요청의 섹션 하나. 계약에 없는 필드가 오면 조용히 버리지 않고 422 로 드러낸다."""

    model_config = ConfigDict(extra="forbid")

    heading: Literal["사실", "해석", "지원"]
    body: str
    source_ids: list[int] = []


class DocumentUpdateRequest(BaseModel):
    """`PUT /api/documents/{id}`. 전체 교체다 — `PATCH` 가 아니다.

    `title` 만 선택인 이유: 서버가 만든 제목을 교사가 안 바꿨으면 안 보내도 된다
    (docs/api-spec.md §11 "title 은 서버가 만든다 ... 교사가 바꾸고 싶으면 PUT 으로").
    `sections` · `updated_at` 은 필수다 — 전체 교체와 동시쓰기 감지에 둘 다 필요하다.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    sections: list[DocumentSectionUpdate]
    review_note: str = ""
    updated_at: datetime
