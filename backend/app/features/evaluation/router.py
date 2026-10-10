"""평가제 체크리스트 조회·체크 저장 (api-spec.md §12)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.evaluation.auto import judge_auto
from app.features.evaluation.catalog import load_catalog
from app.features.evaluation.schemas import (
    AutoItem,
    CheckedElement,
    ChecksRequest,
    EvaluationChecklist,
    Period,
    Progress,
    SelfCheckItem,
)
from app.features.evaluation.service import InvalidChecks, read_checks, save_checks
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_center
from app.shared.school_year import school_year_of

router = APIRouter(prefix="/centers", tags=["evaluation"])
DbSession = Annotated[Session, Depends(get_session)]


def _checklist(session: Session, center_id: int, now: datetime) -> EvaluationChecklist:
    school_year = school_year_of(now)
    checks = read_checks(session, center_id, school_year)
    auto = judge_auto(session, center_id, now)
    items = []
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
    return EvaluationChecklist(school_year=school_year, items=items)


@router.get("/{center_id}/evaluation-checklist", response_model=EvaluationChecklist)
def get_checklist(center_id: int, session: DbSession, user: CurrentUser) -> EvaluationChecklist:
    require_own_center(user, center_id)
    now = datetime.now(UTC)
    return _checklist(session, center_id, now)


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
    response = _checklist(session, center_id, now)
    session.commit()
    return response
