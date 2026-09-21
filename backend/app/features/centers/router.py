"""원 API. 계약은 docs/api-spec.md §1 · §2 다."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.centers.models import Center, Class
from app.features.centers.schemas import (
    CenterCreate,
    CenterResponse,
    ClassListResponse,
)

router = APIRouter(prefix="/centers", tags=["centers"])

# Annotated 로 주입한다. 기본값 자리에서 Depends() 를 호출하면 ruff 의 B008 에 걸린다.
DbSession = Annotated[Session, Depends(get_session)]


@router.post("", response_model=CenterResponse, status_code=status.HTTP_201_CREATED)
def create_center(
    body: CenterCreate,
    session: DbSession,
) -> Center:
    """원을 만든다.

    **중복을 막지 않는다** — 이름만으로 UNIQUE 를 걸면 다른 지역의 같은 이름 원이 막힌다
    (docs/api-spec.md §1). 계정 단위 판단은 인증이 붙는 P1 이다.
    """
    center = Center(
        name=body.name,
        director_name=body.director_name,
        region_sido=body.region_sido,
        region_sigungu=body.region_sigungu,
    )
    session.add(center)
    session.commit()
    session.refresh(center)
    return center


@router.get("/{center_id}/classes", response_model=ClassListResponse)
def list_classes(
    center_id: int,
    session: DbSession,
) -> ClassListResponse:
    """원의 반 목록. 반이 없으면 `{"items": []}` 다 (docs/api-spec.md §2 의 empty state).

    없는 원은 404 `NOT_FOUND` 로 답한다 — 계약에 명시돼 있지 않아 여기서 정하고
    보고서에 계약 보강안으로 올린다. 빈 목록과 없는 원을 같은 응답으로 돌려주면
    FE 가 "반을 추가해 주세요" 를 잘못된 원에도 띄운다.
    """
    if session.get(Center, center_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "원을 찾을 수 없습니다.",
                "fields": ["center_id"],
            },
        )

    # 계약이 순서를 정하지 않았다. 정렬을 빼면 Postgres 가 행 순서를 보장하지 않아
    # 같은 요청이 다른 순서로 온다 — 화면 카드 순서가 흔들리지 않게 id 로 고정한다.
    classes = session.scalars(
        select(Class).where(Class.center_id == center_id).order_by(Class.id)
    ).all()
    return ClassListResponse(items=list(classes))
