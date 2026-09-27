"""문서(일지 계열) API. 계약은 docs/api-spec.md §11 이다."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

# centers·classes·children 은 여러 기능이 쓰는 공유 도메인이라 features/centers 에
# 있어도 직접 import 한다 — ADR-002 가 「두 번째 규칙을 완화해서 해결했다」고 정한 지점이다.
from app.db import get_session
from app.features.centers.models import Child, Class
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.documents.schemas import (
    DocumentDetailResponse,
    DocumentGeneration,
    DocumentListItem,
    DocumentListResponse,
    DocumentSectionItem,
    DocumentSourceItem,
    DocumentUpdateRequest,
)

router = APIRouter(prefix="/documents", tags=["documents"])

DbSession = Annotated[Session, Depends(get_session)]

DocumentKind = Literal["dailyLog", "weeklyLog", "observation", "assessment"]
DocumentStatus = Literal["DRAFT", "CONFIRMED"]

# 화면이 이미 막는 두 규칙(docs/api-spec.md §11 「거절 규칙」 마지막 두 줄) 중
# 상투어 감지는 여기서 구현하지 않는다 — "어떤 문구가 상투어인가"는 근거 없이
# 하드코딩하면 안 되는 판단(팀 판단 필요)이라, 길이 기준만 서버가 막는다.
MIN_INTERPRETATION_SUPPORT_LENGTH = 20


def _error(status_code: int, code: str, message: str, fields: list[str]) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "fields": fields},
    )


def _build_detail_response(session: Session, doc: Document) -> DocumentDetailResponse:
    """단건 상세 응답을 조립한다. `PUT` 응답과 (나중에 붙일) 단건 조회가 같이 쓴다."""
    klass = session.get(Class, doc.class_id)
    child = session.get(Child, doc.child_id) if doc.child_id else None
    sections = session.scalars(
        select(DocumentSection).where(DocumentSection.document_id == doc.id)
    ).all()
    sources = session.scalars(
        select(DocumentSource)
        .where(DocumentSource.document_id == doc.id)
        .order_by(DocumentSource.id)
    ).all()

    return DocumentDetailResponse(
        id=doc.id,
        kind=doc.kind,
        title=doc.title,
        class_id=doc.class_id,
        class_name=klass.name,
        child_id=doc.child_id,
        child_name=child.name if child else None,
        start=doc.start_date,
        end=doc.end_date,
        status=doc.status,
        origin=doc.origin,
        stale=doc.stale,
        sections=[
            DocumentSectionItem(heading=s.heading, body=s.body, source_ids=s.source_ids)
            for s in sections
        ],
        sources=[
            DocumentSourceItem(
                id=s.source_id, date=s.date, text=s.text, class_id=s.class_id, child_id=s.child_id
            )
            for s in sources
        ],
        generation=DocumentGeneration(
            method=doc.generation_method,
            rule_id=doc.generation_rule_id,
            rule_version=doc.generation_rule_version,
        ),
        review_note=doc.review_note,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


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


@router.put("/{document_id}", response_model=DocumentDetailResponse)
def update_document(
    document_id: int,
    body: DocumentUpdateRequest,
    session: DbSession,
) -> DocumentDetailResponse:
    """`title` · `sections` · `review_note` 전체 교체 (docs/api-spec.md §11).

    `PATCH` 가 아니라 `PUT` 이다 — 셋 다 매번 통째로 받는다. `사실` 항목은 근거
    원문을 그대로 이어붙인 것과 정확히 같아야 하고, 다르면 거절한다. 교사가
    사실을 고치려면 §10 에서 원본을 고쳐야 하고, 그러면 이 문서가 `stale` 이 된다.
    """
    doc = session.get(Document, document_id)
    if doc is None:
        raise _error(
            status.HTTP_404_NOT_FOUND, "NOT_FOUND", "문서를 찾을 수 없습니다.", ["document_id"]
        )

    if doc.status == "CONFIRMED":
        raise _error(
            status.HTTP_409_CONFLICT, "ALREADY_CONFIRMED", "확정된 문서는 수정할 수 없습니다.", []
        )

    if doc.updated_at != body.updated_at:
        raise _error(
            status.HTTP_409_CONFLICT,
            "STALE_WRITE",
            "다른 화면이 먼저 고쳤습니다. 최신을 불러온 뒤 다시 수정해주세요.",
            ["updated_at"],
        )

    if len(body.sections) != 3 or {s.heading for s in body.sections} != {"사실", "해석", "지원"}:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_FAILED",
            "sections 는 사실·해석·지원 셋뿐이어야 합니다.",
            ["sections"],
        )

    sources = session.scalars(
        select(DocumentSource)
        .where(DocumentSource.document_id == document_id)
        .order_by(DocumentSource.id)
    ).all()
    valid_source_ids = {s.source_id for s in sources}
    expected_fact = "\n\n".join(s.text for s in sources)

    by_heading = {s.heading: s for s in body.sections}
    fields: list[str] = []

    if by_heading["사실"].body != expected_fact:
        fields.append("sections.사실")
    for heading in ("해석", "지원"):
        text = by_heading[heading].body.strip()
        if not text or len(text) < MIN_INTERPRETATION_SUPPORT_LENGTH:
            fields.append(f"sections.{heading}")
    for section in body.sections:
        if not set(section.source_ids) <= valid_source_ids:
            fields.append(f"sections.{section.heading}.source_ids")

    if fields:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_FAILED",
            "입력값을 확인해주세요.",
            fields,
        )

    if body.title is not None:
        doc.title = body.title
    doc.review_note = body.review_note
    # sections 가 documents 와 다른 테이블이라, 그것만 바뀌어도 documents 행의
    # onupdate 가 저절로 안 걸린다 — STALE_WRITE 판정이 최신 시각을 보게 직접 찍는다.
    doc.updated_at = datetime.now(UTC)

    session.execute(delete(DocumentSection).where(DocumentSection.document_id == document_id))
    for section in body.sections:
        session.add(
            DocumentSection(
                document_id=document_id,
                heading=section.heading,
                body=section.body,
                source_ids=section.source_ids,
            )
        )

    session.commit()
    return _build_detail_response(session, doc)
