"""관찰 기록 API. 계약은 docs/api-spec.md §10 이다.

**생성 엔드포인트가 없다.** 사실기록형이라 AI 가 쓰면 위조다 (CLAUDE.md 문서 5분류).
교사가 적은 그대로 저장하고 꺼낸다.

`PUT` · `DELETE` 는 이 기록을 근거로 쓴 §11 문서를 `stale` 로 바꾼다. 판정은 문서 쪽이
갖고 있다 — `stale` 칸의 주인이 documents 다 (features/documents/stale.py).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.auth.models import User
from app.features.centers.models import Center, Child, Class
from app.features.documents.stale import SourceImpact, observation_changed
from app.features.observations import assist
from app.features.observations.models import AXES, DEFAULT_AXIS, NURI_DOMAINS, Observation
from app.features.observations.schemas import (
    DomainSuggestRequest,
    DomainSuggestResponse,
    MissingResponse,
    ObservationCreate,
    ObservationDeleteResponse,
    ObservationListResponse,
    ObservationMutationResponse,
    ObservationResponse,
    ObservationUpdate,
    ReviewImpact,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import (
    own_class_clause,
    require_own_child,
    require_own_class,
)

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


def _own(session: Session, user: User, observation_id: int, *, lock: bool = False):
    """남의 원 기록도 없는 기록과 같은 404 다 (shared/auth/ownership.py 와 같은 이유).

    `lock` 은 고치거나 지울 때다. 원본 → 문서 순으로 잠가야 refresh · reconfirm
    (review.lock_sources)과 순서가 같아 교착이 없다. 일과 PUT · DELETE 와 같은 규칙이다.
    """
    query = _visible(user).where(Observation.id == observation_id)
    if lock:
        query = query.with_for_update(of=Observation).execution_options(populate_existing=True)
    row = session.execute(query).first()
    if row is None:
        raise _NOT_FOUND
    return row


def _check_axis(session: Session, user: User, class_id: int, domain: str) -> None:
    """그 원이 쓰는 축의 값인가.

    **DB 는 두 축을 다 받는다** (models.py AXES) — 원이 축을 바꿔도 전에 쌓은 기록이
    CHECK 에 걸려 못 읽히면 안 되기 때문이다. 그래서 「지금 이 원이 쓸 수 있는 값인가」는
    여기서 본다. 5영역 원에 「놀이활동」이 들어오면 422 다.
    """
    classroom = require_own_class(session, user, class_id)
    center = session.get(Center, classroom.center_id)
    allowed = AXES.get(center.observation_axis if center else DEFAULT_AXIS, NURI_DOMAINS)
    if domain not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "우리 원이 쓰는 관찰 영역이 아닙니다. " + " · ".join(allowed),
                "fields": ["domain"],
            },
        )


@router.post("", response_model=ObservationResponse, status_code=status.HTTP_201_CREATED)
def create_observation(
    body: ObservationCreate, session: DbSession, user: CurrentUser
) -> ObservationResponse:
    _check_axis(session, user, body.class_id, body.domain)
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


@router.post("/domain-suggest", response_model=DomainSuggestResponse)
def suggest_domain(
    body: DomainSuggestRequest, session: DbSession, user: CurrentUser
) -> DomainSuggestResponse:
    """적던 사실로 영역 하나를 제안한다(ADR-082). **저장하지 않고, 고르지도 않는다.**"""
    classroom = require_own_class(session, user, body.class_id)
    center = session.get(Center, classroom.center_id)
    axis = center.observation_axis if center else DEFAULT_AXIS
    domain, confidence = assist.suggest_domain(session, classroom.id, axis, body.fact, body.context)
    return DomainSuggestResponse(domain=domain, confidence=confidence)


@router.post("/{observation_id}/missing", response_model=MissingResponse)
def check_missing(observation_id: int, session: DbSession, user: CurrentUser) -> MissingResponse:
    """저장한 기록에 상황 · 행동 · 아이 반응이 있는지 본다(ADR-082). 기록은 건드리지 않는다."""
    observation = _own(session, user, observation_id)[0]
    # 같은 원이라도 남의 반 기록으로 AI 를 부르지 못하게 반 권한을 본다. 읽기라 승인받은 반은 된다.
    require_own_class(session, user, observation.class_id, read_only=True)
    return MissingResponse(
        missing=assist.missing_parts(
            session, observation.class_id, observation.fact, observation.context
        )
    )


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
        require_own_class(session, user, class_id, read_only=True)
        query = query.where(Observation.class_id == class_id)
    else:
        # 반을 안 짚은 목록은 내 반만 — 승인받은 반은 반을 짚어야 보인다.
        query = query.where(own_class_clause(user))
    if child_id is not None:
        query = query.where(Observation.child_id == child_id)
    if date_from is not None:
        query = query.where(Observation.date >= date_from)
    if date_to is not None:
        query = query.where(Observation.date <= date_to)
    query = query.order_by(Observation.date.desc(), Observation.id.desc())
    return ObservationListResponse(items=[_response(row) for row in session.execute(query)])


def _impact(impact: SourceImpact) -> ReviewImpact:
    return ReviewImpact(
        affected_document_ids=list(impact.affected_document_ids),
        newly_stale_document_ids=list(impact.newly_stale_document_ids),
    )


@router.put("/{observation_id}", response_model=ObservationMutationResponse | ObservationResponse)
def update_observation(
    observation_id: int,
    body: ObservationUpdate,
    session: DbSession,
    user: CurrentUser,
    include_impact: bool = False,
) -> ObservationResponse | ObservationMutationResponse:
    """`include_impact=true` 면 `review_impact` 를 더한다 — 화면이 「N건 다시 검토」를 띄운다."""
    observation = _own(session, user, observation_id, lock=True)[0]
    _check_axis(session, user, observation.class_id, body.domain)
    domain_moved = observation.domain != body.domain
    for field, value in body.model_dump().items():
        setattr(observation, field, value)
    impact = observation_changed(session, observation_id, observation, domain_moved=domain_moved)
    session.commit()
    result = _response(_own(session, user, observation_id))
    if include_impact:
        return ObservationMutationResponse(**result.model_dump(), review_impact=_impact(impact))
    return result


@router.delete(
    "/{observation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={200: {"model": ObservationDeleteResponse}},
)
def delete_observation(
    observation_id: int, session: DbSession, user: CurrentUser, include_impact: bool = False
) -> Response:
    observation = _own(session, user, observation_id, lock=True)[0]
    require_own_class(session, user, observation.class_id)
    impact = observation_changed(session, observation_id, None)
    session.delete(observation)
    session.commit()
    if include_impact:
        result = ObservationDeleteResponse(review_impact=_impact(impact))
        return JSONResponse(result.model_dump(), status_code=status.HTTP_200_OK)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
