"""원 API. 계약은 docs/api-spec.md §1 · §2 다."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.centers.models import Center, Class
from app.features.centers.schemas import (
    CenterCreate,
    CenterResponse,
    ClassCreate,
    ClassListResponse,
    ClassResponse,
)
from app.shared.school_year import school_year_of

router = APIRouter(prefix="/centers", tags=["centers"])

# Annotated 로 주입한다. 기본값 자리에서 Depends() 를 호출하면 ruff 의 B008 에 걸린다.
DbSession = Annotated[Session, Depends(get_session)]

# UNIQUE(center_id, name, school_year) 의 제약 이름. app/db.py 의 NAMING_CONVENTION 이
# 정하고 첫 마이그레이션이 이 이름으로 만들었다.
CLASS_NAME_UNIQUE = "uq_classes_center_id_name_school_year"


def _violated_constraint(error: IntegrityError) -> str | None:
    """psycopg 가 알려주는 위반 제약 이름. 알 수 없으면 None 이다.

    이름을 보지 않고 IntegrityError 를 전부 「반 이름 중복」으로 바꾸면, 연령 CHECK 나
    외래키 위반까지 409 ALREADY_EXISTS 로 나가 원인을 숨긴다.
    """
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


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


@router.post(
    "/{center_id}/classes",
    response_model=ClassResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_class(
    center_id: int,
    body: ClassCreate,
    session: DbSession,
) -> Class:
    """반을 만든다 (docs/api-spec.md §2).

    `school_year` 는 요청 시각으로 서버가 채우고, `consent_confirmed` 가 `true` 일 때만
    `consent_confirmed_at` 에 시각을 남긴다. `false` 는 검증 실패가 아니라 `null` 이다.
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

    now = datetime.now(UTC)
    classroom = Class(
        center_id=center_id,
        name=body.name,
        school_year=school_year_of(now),
        age_min=body.age_min,
        age_max=body.age_max,
        child_count=body.child_count,
        teacher_name=body.teacher_name,
        consent_confirmed_at=now if body.consent_confirmed else None,
    )
    session.add(classroom)
    try:
        session.commit()
    except IntegrityError as error:
        # 되돌리지 않으면 이 세션의 다음 질의가 전부 InFailedSqlTransaction 으로 죽는다.
        session.rollback()
        if _violated_constraint(error) != CLASS_NAME_UNIQUE:
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_EXISTS",
                "message": "같은 이름의 반이 이미 있습니다.",
                "fields": ["name"],
            },
        ) from error
    session.refresh(classroom)
    return classroom


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
