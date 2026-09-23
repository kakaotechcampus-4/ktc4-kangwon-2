"""문서(일지 계열) API. 계약은 docs/api-spec.md §11 이다."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# centers·classes·children 은 여러 기능이 쓰는 공유 도메인이라 features/centers 에
# 있어도 직접 import 한다 — ADR-002 가 「두 번째 규칙을 완화해서 해결했다」고 정한 지점이다.
from app.db import get_session
from app.features.centers.models import Child, Class
from app.features.documents.models import Document, DocumentSource
from app.features.documents.schemas import (
    DocumentGeneration,
    DocumentListItem,
    DocumentListResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])

DbSession = Annotated[Session, Depends(get_session)]

DocumentKind = Literal["dailyLog", "weeklyLog", "observation", "assessment"]
DocumentStatus = Literal["DRAFT", "CONFIRMED"]


@router.get("", response_model=DocumentListResponse)
def list_documents(
    session: DbSession,
    kind: DocumentKind | None = None,
    class_id: int | None = None,
    child_id: int | None = None,
    status: DocumentStatus | None = None,
    stale: bool | None = None,
) -> DocumentListResponse:
    """문서 보관함. 네 값 모두 선택이고, 없으면 전체다 (docs/api-spec.md §11).

    `sections` · `sources` 는 담지 않는다 — 상세는 단건 조회가 준다. 대신
    `sources_count` 를 붙인다. 정렬은 계약에 명시가 없어 최신 생성 우선으로 두고,
    같은 시각 생성분은 `id` 내림차순으로 동률을 깬다.
    """
    sources_count = (
        select(func.count(DocumentSource.id))
        .where(DocumentSource.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    query = (
        select(Document, Class.name, Child.name, sources_count)
        .join(Class, Class.id == Document.class_id)
        .outerjoin(Child, Child.id == Document.child_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    if kind is not None:
        query = query.where(Document.kind == kind)
    if class_id is not None:
        query = query.where(Document.class_id == class_id)
    if child_id is not None:
        query = query.where(Document.child_id == child_id)
    if status is not None:
        query = query.where(Document.status == status)
    if stale is not None:
        query = query.where(Document.stale == stale)

    rows = session.execute(query).all()
    items = [
        DocumentListItem(
            id=doc.id,
            kind=doc.kind,
            title=doc.title,
            class_id=doc.class_id,
            class_name=class_name,
            child_id=doc.child_id,
            child_name=child_name,
            start=doc.start_date,
            end=doc.end_date,
            status=doc.status,
            origin=doc.origin,
            stale=doc.stale,
            generation=DocumentGeneration(
                method=doc.generation_method,
                rule_id=doc.generation_rule_id,
                rule_version=doc.generation_rule_version,
            ),
            sources_count=sources_count_value,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc, class_name, child_name, sources_count_value in rows
    ]
    return DocumentListResponse(items=items)
