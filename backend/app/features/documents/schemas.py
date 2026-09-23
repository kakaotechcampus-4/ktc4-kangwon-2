"""문서(일지 계열) API 의 응답 모델. 계약은 docs/api-spec.md §11 이다."""

from datetime import date, datetime

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
