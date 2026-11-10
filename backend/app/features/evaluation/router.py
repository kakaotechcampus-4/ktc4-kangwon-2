"""평가제 체크리스트 조회·체크 저장 (api-spec.md §12 · ADR-074)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.evaluation.auto import judge_auto
from app.features.evaluation.catalog import load_catalog
from app.features.evaluation.schemas import (
    DIRECTOR_KEYS,
    DOC_KEYS,
    AutoItem,
    CheckedElement,
    ChecksRequest,
    DirectorCheck,
    DirectorRequest,
    DocumentMark,
    DocumentsRequest,
    EvaluationChecklist,
    FolderResult,
    Period,
    Progress,
    SelfCheckItem,
)
from app.features.evaluation.service import (
    FolderScanRow,
    InvalidChecks,
    read_checks,
    read_director_checks,
    read_doc_marks,
    save_checks,
    save_director_checks,
    save_doc_marks,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_center_creator, require_own_center
from app.shared.school_year import school_year_of

router = APIRouter(prefix="/centers", tags=["evaluation"])
DbSession = Annotated[Session, Depends(get_session)]


def _documents(
    session: Session, center_id: int, school_year: int, user_id: int
) -> list[DocumentMark]:
    marks = read_doc_marks(session, center_id, school_year, user_id)
    documents = []
    for doc in DOC_KEYS:
        mark = marks.get(doc)
        folder = (
            FolderResult(
                status=mark.folder_status,
                scanned_at=mark.folder_scanned_at,
                period=Period(from_=mark.folder_from, to=mark.folder_to),
                files=mark.folder_files,
                gaps=mark.folder_gaps,
            )
            if mark and mark.folder_status
            else None
        )
        checked_at = mark.checked_at if mark else None
        documents.append(
            DocumentMark(
                doc=doc, checked=checked_at is not None, checked_at=checked_at, folder=folder
            )
        )
    return documents


def _checklist(
    session: Session, center_id: int, user_id: int, now: datetime
) -> EvaluationChecklist:
    school_year = school_year_of(now)
    checks = read_checks(session, center_id, school_year)
    director = read_director_checks(session, center_id, school_year)
    auto = judge_auto(session, center_id, now)
    items: list[AutoItem | SelfCheckItem] = []
    for indicator in load_catalog().indicators:
        if indicator.kind == "EXCLUDED":
            continue
        common = {
            "indicator": indicator.indicator,
            "area": indicator.area_title,
            "title": indicator.title,
            "content": indicator.content,
        }
        if indicator.kind == "AUTO":
            result = auto[indicator.indicator]
            items.append(
                AutoItem(
                    **common,
                    verdict=result.verdict,
                    required=result.required,
                    count=result.count,
                    children=result.children,
                    classes=result.classes,
                    plan_ids=result.plan_ids,
                    document_ids=result.document_ids,
                    period=Period(from_=result.period.start, to=result.period.end),
                    journal_classes=result.journal_classes,
                    plan_classes=result.plan_classes,
                )
            )
        else:
            elements = [
                CheckedElement(
                    element=element.element,
                    text=element.text,
                    checked=element.element in checks,
                    checked_at=checks.get(element.element),
                )
                for element in indicator.elements
            ]
            checked, total = sum(element.checked for element in elements), len(elements)
            items.append(
                SelfCheckItem(
                    **common,
                    elements=elements,
                    progress=Progress(checked=checked, total=total),
                    complete=total > 0 and checked == total,
                )
            )
    return EvaluationChecklist(
        school_year=school_year,
        items=items,
        documents=_documents(session, center_id, school_year, user_id),
        director=[
            DirectorCheck(item=item, checked=item in director, checked_at=director.get(item))
            for item in DIRECTOR_KEYS
        ],
    )


@router.get("/{center_id}/evaluation-checklist", response_model=EvaluationChecklist)
def get_checklist(center_id: int, session: DbSession, user: CurrentUser) -> EvaluationChecklist:
    require_own_center(user, center_id)
    now = datetime.now(UTC)
    return _checklist(session, center_id, user.id, now)


@router.put("/{center_id}/evaluation-checklist/checks", response_model=EvaluationChecklist)
def put_checks(
    center_id: int, body: ChecksRequest, session: DbSession, user: CurrentUser
) -> EvaluationChecklist:
    require_own_center(user, center_id)
    now = datetime.now(UTC)
    allowed = {
        element.element
        for indicator in load_catalog().indicators
        if indicator.kind == "SELF_CHECK"
        for element in indicator.elements
    }
    try:
        save_checks(session, center_id, now, [(c.element, c.checked) for c in body.checks], allowed)
    except InvalidChecks as error:
        session.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "체크할 수 없는 평가요소가 있습니다.",
                "fields": [f"checks.{element}" for element in error.elements],
            },
        ) from error
    response = _checklist(session, center_id, user.id, now)
    session.commit()
    return response


@router.put("/{center_id}/evaluation-checklist/documents", response_model=EvaluationChecklist)
def put_documents(
    center_id: int, body: DocumentsRequest, session: DbSession, user: CurrentUser
) -> EvaluationChecklist:
    """로그인한 교사의 직접확인 · 폴더 검사 결과.

    다른 교사의 줄은 건드리지 않는다(ADR-074 결정 4).
    """
    require_own_center(user, center_id)
    now = datetime.now(UTC)
    scan = (
        [
            FolderScanRow(
                doc=r.doc,
                status=r.status,
                period_from=r.period.from_,
                period_to=r.period.to,
                files=r.files,
                gaps=r.gaps,
            )
            for r in body.folder_scan.results
        ]
        if body.folder_scan
        else None
    )
    save_doc_marks(
        session, center_id, user.id, now, [(c.doc, c.checked) for c in body.checks], scan
    )
    response = _checklist(session, center_id, user.id, now)
    session.commit()
    return response


@router.put("/{center_id}/evaluation-checklist/director", response_model=EvaluationChecklist)
def put_director(
    center_id: int, body: DirectorRequest, session: DbSession, user: CurrentUser
) -> EvaluationChecklist:
    """원장 서류 체크 — 같은 원 교사 누구나 같은 체크를 본다(ADR-074 결정 4).

    바꾸기는 원을 만든 교사만이다 (ADR-087). 읽기(GET)는 그대로 누구나다.
    """
    require_own_center(user, center_id)
    require_center_creator(session, user, center_id)
    now = datetime.now(UTC)
    save_director_checks(session, center_id, now, [(c.item, c.checked) for c in body.checks])
    response = _checklist(session, center_id, user.id, now)
    session.commit()
    return response
