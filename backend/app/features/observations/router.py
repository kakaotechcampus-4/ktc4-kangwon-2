"""관찰 기록 API. 계약은 docs/api-spec.md §10 이다.

**생성 엔드포인트가 없다.** 사실기록형이라 AI 가 쓰면 위조다 (CLAUDE.md 문서 5분류).
교사가 적은 그대로 저장하고 꺼낸다.

`PUT` · `DELETE` 가 이 기록을 근거로 쓴 §11 문서를 `stale` 로 바꾸는 일은 아직 없다 —
documents 테이블(PR #50)이 develop 에 들어오면 그쪽에서 붙인다.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.auth.models import User
from app.features.centers.models import Child, Class
from app.features.observations.models import Observation
from app.features.observations.schemas import (
    ObservationCreate,
    ObservationListResponse,
    ObservationResponse,
    ObservationUpdate,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_child, require_own_class

router = APIRouter(prefix="/observations", tags=["observations"])

DbSession = Annotated[Session, Depends(get_session)]

_NOT_FOUND = HTTPException(
    status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "관찰 기록을 찾을 수 없습니다.", "fields": ["id"]},
)


def _visible(user: User) -> Select:
    """이 교사의 원에 속한 기록 + 반·아이 이름. 목록·단건·저장 응답이 모두 이 조회를 쓴다.

    한 번의 JOIN 으로 이름까지 가져온다 — 행마다 반·아이를 다시 부르면 N+1 이다(§10).
    온보딩 전(center_id 가 None)이면 `IS NULL` 이 되어 아무것도 안 나온다.
    """
    return (
        select(Observation, Class.name, Child.name, Child.code)
        .join(Class, Observation.class_id == Class.id)
        .join(Child, Observation.child_id == Child.id)
        .where(Class.center_id == user.center_id)
    )


def _response(row) -> ObservationResponse:
    observation, class_name, child_name, child_code = row
    return ObservationResponse(
        id=observation.id,
        class_id=observation.class_id,
        class_name=class_name,
        child_id=observation.child_id,
        child_name=child_name,
        child_code=child_code,
        date=observation.date,
        domain=observation.domain,
        context=observation.context,
        fact=observation.fact,
        created_at=observation.created_at,
    )


def _own(session: Session, user: User, observation_id: int):
    """남의 원 기록도 없는 기록과 같은 404 다 (shared/auth/ownership.py 와 같은 이유)."""
    row = session.execute(_visible(user).where(Observation.id == observation_id)).first()
    if row is None:
        raise _NOT_FOUND
    return row


@router.post("", response_model=ObservationResponse, status_code=status.HTTP_201_CREATED)
def create_observation(
    body: ObservationCreate, session: DbSession, user: CurrentUser
) -> ObservationResponse:
    require_own_class(session, user, body.class_id)
    child = require_own_child(session, user, body.child_id)
    if child.class_id != body.class_id:
        # 같은 원의 다른 반 아이다. 404 가 아니다 — 둘 다 있고, 짝이 틀렸다.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "그 반의 아이가 아닙니다.",
                "fields": ["child_id"],
            },
        )

    observation = Observation(**body.model_dump())
    session.add(observation)
    session.commit()
    return _response(_own(session, user, observation.id))


@router.get("", response_model=ObservationListResponse)
def list_observations(
    session: DbSession,
    user: CurrentUser,
    class_id: int | None = None,
    child_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> ObservationListResponse:
    """네 값 모두 선택이다. 없으면 이 교사의 원 전체다.

    **정렬은 `date` 내림차순 고정이다**(§10). 같은 날은 나중에 쓴 것이 위 — 순서가
    흔들리면 목록이 새로고침마다 바뀐다.
    """
    query = _visible(user)
    if class_id is not None:
        query = query.where(Observation.class_id == class_id)
    if child_id is not None:
        query = query.where(Observation.child_id == child_id)
    if date_from is not None:
        query = query.where(Observation.date >= date_from)
    if date_to is not None:
        query = query.where(Observation.date <= date_to)
    query = query.order_by(Observation.date.desc(), Observation.id.desc())
    return ObservationListResponse(items=[_response(row) for row in session.execute(query)])


@router.put("/{observation_id}", response_model=ObservationResponse)
def update_observation(
    observation_id: int, body: ObservationUpdate, session: DbSession, user: CurrentUser
) -> ObservationResponse:
    observation = _own(session, user, observation_id)[0]
    for field, value in body.model_dump().items():
        setattr(observation, field, value)
    session.commit()
    return _response(_own(session, user, observation_id))


@router.delete("/{observation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_observation(observation_id: int, session: DbSession, user: CurrentUser) -> None:
    observation = _own(session, user, observation_id)[0]
    session.delete(observation)
    session.commit()
