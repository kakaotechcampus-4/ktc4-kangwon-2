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


class RelatedDocumentsResponse(BaseModel):
    """겹치는 확정 문서. 목록 항목 형식을 그대로 쓴다 — 화면이 같은 카드를 그린다."""

    items: list["DocumentListItem"]
    # 이 종류가 무엇을 짝으로 기대하는지. 비어 있어도 막지 않고 "아직 없음" 으로만 보인다.
    expected_kinds: list[str]


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
    # 관찰 기록 근거일 때만 있다. 관찰일지 종이의 영역 행을 가른다 (§11 「종이 한 장」).
    domain: str | None = None
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
    """`PUT` 요청의 섹션 하나."""

    model_config = ConfigDict(extra="forbid")

    heading: Literal["사실", "해석", "지원"]
    body: str
    source_ids: list[int] = []


class DocumentUpdateRequest(BaseModel):
    """`PUT /api/documents/{id}`. 전체 교체다 — `PATCH` 가 아니다.

    `title` 은 서버가 만들어서(docs/api-spec.md §11), 교사가 안 바꿨으면 굳이 안 보내도
    된다 — 그래서 셋 중 이것만 선택이다. `sections` · `updated_at` 은 필수다.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    sections: list[DocumentSectionUpdate]
    review_note: str = ""
    updated_at: datetime


class DocumentCreateRequest(BaseModel):
    """`POST /api/documents`. 교사가 고른 근거로 초안을 만든다 (docs/api-spec.md §11).

    `source_ids` 는 `kind` 마다 가리키는 것이 다르다 — `weeklyLog` 만 확정된 일일 보육일지 id 고,
    나머지는 관찰 기록 id 다. 순서는 교사가 고른 순서 그대로 `사실` 에 이어 붙는다.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["dailyLog", "weeklyLog", "observation", "assessment"]
    class_id: int
    child_id: int | None = None
    start: date
    end: date
    source_ids: list[int]


class DocumentChecks(BaseModel):
    """확정 전 교사 확인 3개 (docs/api-spec.md §11 「4단」). 하나라도 false 면 422 다."""

    model_config = ConfigDict(extra="forbid")

    fact: bool
    interpretation: bool
    support: bool


class DocumentConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: DocumentChecks
