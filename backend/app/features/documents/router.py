"""문서(일지 계열) API. 계약은 docs/api-spec.md §11 이다."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

# centers·classes·children 은 여러 기능이 쓰는 공유 도메인이라 features/centers 에
# 있어도 직접 import 한다 — ADR-002 가 「두 번째 규칙을 완화해서 해결했다」고 정한 지점이다.
from app.db import get_session
from app.features.auth.models import User
from app.features.centers.models import Child, Class
from app.features.documents.draft import (
    KIND_LABELS,
    RULE_VERSION,
    DraftFailed,
    draft_sections,
    rule_id,
)
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.documents.schemas import (
    DocumentConfirmRequest,
    DocumentCreateRequest,
    DocumentDetailResponse,
    DocumentGeneration,
    DocumentListItem,
    DocumentListResponse,
    DocumentSectionItem,
    DocumentSourceItem,
    DocumentUpdateRequest,
    RelatedDocumentsResponse,
)
from app.features.observations.models import Observation
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_child, require_own_class
from app.shared.gates.sections import check_sections, join_facts

router = APIRouter(prefix="/documents", tags=["documents"])

DbSession = Annotated[Session, Depends(get_session)]

DocumentKind = Literal["dailyLog", "weeklyLog", "observation", "assessment"]
DocumentStatus = Literal["DRAFT", "CONFIRMED"]

CHILD_SCOPED_KINDS = frozenset({"observation", "assessment"})

# 문서 종류마다 있어야 할 짝이 다르다 (docs/api-spec.md §11).
# 없다고 막지 않는다 — 화면에 "아직 없음" 으로 표시만 한다.
EXPECTED_PAIRS = {
    "weeklyLog": ("dailyLog",),
    "assessment": ("observation", "dailyLog"),
}
DEFAULT_EXPECTED = ("dailyLog", "observation")


def _error(status_code: int, code: str, message: str, fields: list[str]) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "fields": fields},
    )


def _invalid(fields: list[str]) -> HTTPException:
    message = (
        "sections 는 사실·해석·지원 셋뿐이어야 합니다."
        if fields == ["sections"]
        else "입력값을 확인해주세요."
    )
    return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_FAILED", message, fields)


def _own_document(session: Session, user: User, document_id: int) -> Document:
    """남의 원 문서도 없는 문서와 같은 404 다 (shared/auth/ownership.py 와 같은 이유)."""
    doc = session.scalar(
        select(Document)
        .join(Class, Class.id == Document.class_id)
        .where(Document.id == document_id, Class.center_id == user.center_id)
    )
    if doc is None:
        raise _error(
            status.HTTP_404_NOT_FOUND, "NOT_FOUND", "문서를 찾을 수 없습니다.", ["document_id"]
        )
    return doc


def _sources(session: Session, document_id: int) -> list[DocumentSource]:
    # 만든 순서 = 교사가 고른 순서다. `사실` 을 다시 이어볼 때 이 순서여야 맞는다.
    return list(
        session.scalars(
            select(DocumentSource)
            .where(DocumentSource.document_id == document_id)
            .order_by(DocumentSource.id)
        )
    )


def _period(start: date, end: date) -> str:
    if start == end:
        return f"{start.month}/{start.day}"
    if start.year == end.year and start.month == end.month:
        return f"{start.month}월"
    return f"{start.month}/{start.day}~{end.month}/{end.day}"


def _build_detail_response(session: Session, doc: Document) -> DocumentDetailResponse:
    """단건 상세 응답을 조립한다. 단건 조회 · 생성 · 수정 · 확정이 같이 쓴다."""
    klass = session.get(Class, doc.class_id)
    child = session.get(Child, doc.child_id) if doc.child_id else None
    sections = session.scalars(
        select(DocumentSection).where(DocumentSection.document_id == doc.id)
    ).all()
    sources = _sources(session, doc.id)

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
    user: CurrentUser,
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
        # **원 격리를 조회 자체에 건다.** 이게 없으면 로그인한 아무 교사나 남의 원
        # 문서를 아동 실명까지 통째로 받아간다. 라우터마다 확인하는 방식이면
        # 엔드포인트가 늘 때 반드시 하나를 빠뜨린다.
        .where(Class.center_id == user.center_id)
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


@router.post("", response_model=DocumentDetailResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    body: DocumentCreateRequest, session: DbSession, user: CurrentUser
) -> DocumentDetailResponse:
    """교사가 고른 근거로 초안을 만든다 (docs/api-spec.md §11).

    `사실` 은 서버가 근거 원문을 이어 붙인다 - LLM 이 만지지 않는다. 해석 · 지원만
    `draft.py` 가 만든다. 검사(3단 게이트 1·2단)를 통과하지 못하면 아무것도 저장하지 않는다.
    """
    fields: list[str] = []
    if body.kind in CHILD_SCOPED_KINDS and body.child_id is None:
        fields.append("child_id")
    if body.kind == "dailyLog" and body.start != body.end:
        fields.append("end")
    if body.start > body.end:
        fields.append("start")
    if not body.source_ids or len(set(body.source_ids)) != len(body.source_ids):
        fields.append("source_ids")
    if fields:
        raise _invalid(fields)

    classroom = require_own_class(session, user, body.class_id)
    child = None
    if body.child_id is not None:
        child = require_own_child(session, user, body.child_id)
        if child.class_id != body.class_id:
            raise _invalid(["child_id"])

    # 근거를 불러와 사본 행을 만든다. 순서는 교사가 고른 순서 그대로다.
    copies: list[DocumentSource] = []
    if body.kind == "weeklyLog":
        by_id = {
            d.id: d
            for d in session.scalars(
                select(Document)
                .join(Class, Class.id == Document.class_id)
                .where(Document.id.in_(body.source_ids), Class.center_id == user.center_id)
            )
        }
        for source_id in body.source_ids:
            source = by_id.get(source_id)
            if source is None or source.kind != "dailyLog":
                fields.append(f"sources.{source_id}")
                continue
            if source.status != "CONFIRMED":
                raise _error(
                    status.HTTP_409_CONFLICT,
                    "GATE_BLOCKED",
                    "확정된 일일 보육일지만 근거로 쓸 수 있습니다.",
                    [f"sources.{source_id}"],
                )
            if source.class_id != body.class_id or not (
                body.start <= source.start_date <= body.end
            ):
                fields.append(f"sources.{source_id}")
                continue
            fact = session.scalar(
                select(DocumentSection.body).where(
                    DocumentSection.document_id == source.id, DocumentSection.heading == "사실"
                )
            )
            if fact is None:
                fields.append(f"sources.{source_id}")
                continue
            copies.append(
                DocumentSource(
                    source_kind="document",
                    source_id=source.id,
                    class_id=source.class_id,
                    child_id=source.child_id,
                    date=source.start_date,
                    source_status=source.status,
                    text=fact,
                )
            )
    else:
        by_id = {
            o.id: o
            for o in session.scalars(
                select(Observation)
                .join(Class, Class.id == Observation.class_id)
                .where(Observation.id.in_(body.source_ids), Class.center_id == user.center_id)
            )
        }
        for source_id in body.source_ids:
            source = by_id.get(source_id)
            if (
                source is None
                or source.class_id != body.class_id
                or (body.child_id is not None and source.child_id != body.child_id)
                or not (body.start <= source.date <= body.end)
            ):
                fields.append(f"sources.{source_id}")
                continue
            copies.append(
                DocumentSource(
                    source_kind="observation",
                    source_id=source.id,
                    class_id=source.class_id,
                    child_id=source.child_id,
                    date=source.date,
                    text=source.fact,
                )
            )
    if fields:
        raise _invalid(fields)

    facts = [c.text for c in copies]
    children = {
        c.name: c.code
        for c in session.scalars(select(Child).where(Child.class_id == body.class_id))
    }
    try:
        drafted = draft_sections(body.kind, facts, body.source_ids, children)
    except DraftFailed as exc:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "GENERATION_FAILED", str(exc), []
        ) from exc

    sections = [
        DocumentSectionItem(heading="사실", body=join_facts(facts), source_ids=body.source_ids),
        *(
            DocumentSectionItem(heading=d.heading, body=d.body, source_ids=d.source_ids)
            for d in drafted
        ),
    ]
    if check_sections(sections, facts, set(body.source_ids)):
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "GENERATION_FAILED",
            "초안이 문서 규격을 통과하지 못했습니다. 다시 시도해주세요.",
            [],
        )

    subject = child.name if child else classroom.name
    doc = Document(
        kind=body.kind,
        title=f"{subject} {KIND_LABELS[body.kind]} ({_period(body.start, body.end)})",
        class_id=body.class_id,
        child_id=body.child_id,
        start_date=body.start,
        end_date=body.end,
        status="DRAFT",
        origin="AI",
        stale=False,
        generation_method="RULE_LLM",
        generation_rule_id=rule_id(body.kind),
        generation_rule_version=RULE_VERSION,
        review_note="",
    )
    session.add(doc)
    session.flush()
    for copy in copies:
        copy.document_id = doc.id
        session.add(copy)
    for section in sections:
        session.add(
            DocumentSection(
                document_id=doc.id,
                heading=section.heading,
                body=section.body,
                source_ids=section.source_ids,
            )
        )
    session.commit()
    return _build_detail_response(session, doc)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: int, session: DbSession, user: CurrentUser) -> DocumentDetailResponse:
    """단건 조회. 목록과 달리 `sections` · `sources` 를 담는다 (docs/api-spec.md §11)."""
    return _build_detail_response(session, _own_document(session, user, document_id))


@router.put("/{document_id}", response_model=DocumentDetailResponse)
def update_document(
    document_id: int,
    body: DocumentUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> DocumentDetailResponse:
    """`title` · `sections` · `review_note` 전체 교체 (docs/api-spec.md §11).

    `PATCH` 가 아니라 `PUT` 이다 — 셋 다 매번 통째로 받는다. `사실` 항목은 근거
    원문을 그대로 이어붙인 것과 정확히 같아야 하고, 다르면 거절한다. 교사가
    사실을 고치려면 §10 에서 원본을 고쳐야 하고, 그러면 이 문서가 `stale` 이 된다.
    """
    doc = _own_document(session, user, document_id)

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

    sources = _sources(session, document_id)
    fields = check_sections(
        body.sections, [s.text for s in sources], {s.source_id for s in sources}
    )
    if fields:
        raise _invalid(fields)

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


def _visible(user: User):
    """이 교사의 원 문서 + 반·아이 이름. 목록과 related 가 같은 조회를 쓴다."""
    sources_count = (
        select(func.count(DocumentSource.id))
        .where(DocumentSource.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    return (
        select(Document, Class.name, Child.name, sources_count)
        .join(Class, Class.id == Document.class_id)
        .where(Class.center_id == user.center_id)
        .outerjoin(Child, Child.id == Document.child_id)
    )


def _list_item(row) -> DocumentListItem:
    doc, class_name, child_name, sources_count_value = row
    return DocumentListItem(
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


@router.get("/{document_id}/related", response_model=RelatedDocumentsResponse)
def related_documents(
    document_id: int, session: DbSession, user: CurrentUser
) -> RelatedDocumentsResponse:
    """같은 반 · 같은 아이 · 기간이 겹치는 **확정** 문서를 준다 (docs/api-spec.md §11).

    교사가 "이 관찰일지가 그 주 보육일지랑 안 맞는데" 를 눈으로 대조한다.

    **DRAFT 는 빼고 준다.** 아직 쓰는 중인 글을 "안 맞는다" 고 들이밀면 방해다.
    **모델을 부르지 않는다.** 겹치는 문서를 찾아 보여줄 뿐 무엇이 맞는지는 판정하지
    않는다 — 3단 게이트의 2단이라 모델이 개입하면 판정이 흔들린다.
    """
    row = session.execute(_visible(user).where(Document.id == document_id)).first()
    if row is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "문서를 찾을 수 없습니다.", ["id"])
    doc = row[0]

    expected = EXPECTED_PAIRS.get(doc.kind, DEFAULT_EXPECTED)
    query = _visible(user).where(
        Document.id != doc.id,
        Document.class_id == doc.class_id,
        Document.status == "CONFIRMED",
        # 기간이 겹친다 = 내 시작이 상대 끝보다 앞이고, 내 끝이 상대 시작보다 뒤다.
        Document.start_date <= doc.end_date,
        Document.end_date >= doc.start_date,
    )
    # 아이 기록은 그 아이 것만 본다. 반 단위 문서(child_id 가 없는 것)는 반 전체가 짝이다.
    if doc.child_id is not None:
        query = query.where((Document.child_id == doc.child_id) | (Document.child_id.is_(None)))
    rows = session.execute(query.order_by(Document.start_date.desc(), Document.id.desc())).all()
    return RelatedDocumentsResponse(
        items=[_list_item(item) for item in rows], expected_kinds=list(expected)
    )


@router.post("/{document_id}/confirm", response_model=DocumentDetailResponse)
def confirm_document(
    document_id: int, body: DocumentConfirmRequest, session: DbSession, user: CurrentUser
) -> DocumentDetailResponse:
    """DRAFT → CONFIRMED. 교사 확인 3개와 3단 게이트 1·2단을 지나야 한다 (docs/api-spec.md §11).

    **다시 불러도 200 이다.** 더블클릭 · 네트워크 재시도로 두 번 오는 게 정상 경로라
    409 로 막으면 진짜 실패와 구분이 안 된다 (§7 연간 확정과 같은 이유).

    3단(LLM Judge, `/verify`)은 여기서 요구하지 않는다 - AI 를 못 부르는 상태여도
    확정할 수 있어야 한다. 1·2단과 교사 확인이 본선이다.
    """
    doc = _own_document(session, user, document_id)
    if doc.status == "CONFIRMED":
        return _build_detail_response(session, doc)

    unchecked = [f"checks.{name}" for name, value in body.checks.model_dump().items() if not value]
    if unchecked:
        raise _invalid(unchecked)

    if doc.stale:
        raise _error(
            status.HTTP_409_CONFLICT,
            "GATE_BLOCKED",
            "근거 기록이 바뀌었습니다. 다시 검토한 뒤 확정해주세요.",
            ["stale"],
        )

    if doc.origin != "IMPORT":
        # 증빙으로 올린 원문(IMPORT)은 우리가 만든 문서가 아니라 거절 규칙을 적용하지 않는다.
        sources = _sources(session, document_id)
        stored = list(
            session.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id))
        )
        fields = check_sections(stored, [s.text for s in sources], {s.source_id for s in sources})
        if fields:
            raise _invalid(fields)

    doc.status = "CONFIRMED"
    doc.updated_at = datetime.now(UTC)
    session.commit()
    return _build_detail_response(session, doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, session: DbSession, user: CurrentUser) -> None:
    """문서를 지운다. 자식 행을 먼저 지우고 문서를 지운다 - FK 에 CASCADE 가 없다 (ADR-010).

    이 문서를 근거로 쓴 문서(주간 보육일지)는 지우지 않고 `stale` 로 바꾼다 -
    근거가 사라진 것도 「원본 없음」이라 교사가 다시 봐야 한다 (§11 판정 기준).
    """
    doc = _own_document(session, user, document_id)
    dependents = select(DocumentSource.document_id).where(
        DocumentSource.source_kind == "document", DocumentSource.source_id == doc.id
    )
    session.execute(update(Document).where(Document.id.in_(dependents)).values(stale=True))
    session.execute(delete(DocumentSection).where(DocumentSection.document_id == doc.id))
    session.execute(delete(DocumentSource).where(DocumentSource.document_id == doc.id))
    session.delete(doc)
    session.commit()
