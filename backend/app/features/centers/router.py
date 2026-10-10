"""원 API. 계약은 docs/api-spec.md §1 · §2 다."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.auth.models import User
from app.features.centers.greetings import default_greetings
from app.features.centers.models import Center, CenterInvite, Class, Greetings
from app.features.centers.schemas import (
    CenterCreate,
    CenterResponse,
    ClassCreate,
    ClassListResponse,
    ClassResponse,
    GreetingsSettings,
    InviteResponse,
    JoinRequest,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_center
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
    user: CurrentUser,
) -> Center:
    """원을 만들고 이 교사의 원으로 등록한다.

    **중복을 막지 않는다** — 이름만으로 UNIQUE 를 걸면 다른 지역의 같은 이름 원이 막힌다
    (docs/api-spec.md §1). 대신 **한 계정은 원 하나다** — 두 번째 요청은 409 다.
    바꾸려면 기존 원을 정리해야 하는데 그 규칙(반·아동·계획안 처리)이 아직 없다.
    """
    if user.center_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_EXISTS",
                "message": "이미 등록한 원이 있습니다.",
                "fields": [],
            },
        )
    center = Center(
        name=body.name,
        director_name=body.director_name,
        region_sido=body.region_sido,
        region_sigungu=body.region_sigungu,
    )
    session.add(center)
    session.flush()
    # 같은 트랜잭션에서 주인을 붙인다. 나눠 커밋하면 원은 생겼는데 주인이 없는 행이 남는다.
    user.center_id = center.id
    session.commit()
    session.refresh(center)
    return center


# 헷갈리는 글자(0·O·1·I·L)를 뺐다. 교사가 단톡방에서 보고 옮겨 적는다.
INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_LENGTH = 10  # 31^10 ≈ 8×10^14. 7일 · 1회용이라 맞혀 볼 수 없다
INVITE_TTL = timedelta(days=7)


@router.post(
    "/{center_id}/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED
)
def create_invite(center_id: int, session: DbSession, user: CurrentUser) -> CenterInvite:
    """같은 원 교사를 들이는 1회용 코드를 만든다 (§1-1). 자기 원에만 만들 수 있다."""
    require_own_center(user, center_id)
    invite = CenterInvite(
        center_id=center_id,
        code="".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH)),
        created_by=user.id,
        expires_at=datetime.now(UTC) + INVITE_TTL,
    )
    session.add(invite)
    session.commit()
    return invite


_ALREADY_JOINED = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail={"code": "ALREADY_EXISTS", "message": "이미 등록한 원이 있습니다.", "fields": []},
)


@router.post("/join", response_model=CenterResponse)
def join_center(body: JoinRequest, session: DbSession, user: CurrentUser) -> Center:
    """초대 코드로 원에 들어간다 (§1-1). 이미 원이 있으면 `create_center` 와 같은 409 다."""
    if user.center_id is not None:
        raise _ALREADY_JOINED
    now = datetime.now(UTC)
    # 행을 잠근다. 두 교사가 같은 코드를 동시에 내면 한 명만 들어간다.
    invite = session.scalar(
        select(CenterInvite).where(CenterInvite.code == body.code.upper()).with_for_update()
    )
    # 없는 코드 · 쓴 코드 · 만료된 코드를 구분하지 않는다. 구분해 주면 맞혀 보는 쪽에 힌트다.
    if invite is None or invite.used_at is not None or invite.expires_at <= now:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "초대 코드가 없거나 만료됐습니다.",
                "fields": ["code"],
            },
        )
    # 원이 비어 있을 때만 넣는다. 같은 교사가 코드 두 개를 동시에 내면 위 검사는 둘 다
    # 통과하지만, 이 UPDATE 는 먼저 커밋한 쪽만 행을 바꾼다 — 늦은 쪽 코드는 쓰이지 않는다.
    joined = session.execute(
        update(User)
        .where(User.id == user.id, User.center_id.is_(None))
        .values(center_id=invite.center_id)
    ).rowcount
    if not joined:
        session.rollback()
        raise _ALREADY_JOINED
    invite.used_by = user.id
    invite.used_at = now
    session.commit()
    return session.get(Center, invite.center_id)


@router.post(
    "/{center_id}/classes",
    response_model=ClassResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_class(
    center_id: int,
    body: ClassCreate,
    session: DbSession,
    user: CurrentUser,
) -> Class:
    """반을 만든다 (docs/api-spec.md §2).

    `school_year` 는 요청 시각으로 서버가 채우고, `consent_confirmed` 가 `true` 일 때만
    `consent_confirmed_at` 에 시각을 남긴다. `false` 는 검증 실패가 아니라 `null` 이다.
    """
    # 없는 원과 남의 원을 같은 404 로 돌려준다 (shared/auth/ownership.py).
    require_own_center(user, center_id)

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
    user: CurrentUser,
) -> ClassListResponse:
    """원의 반 목록. 반이 없으면 `{"items": []}` 다 (docs/api-spec.md §2 의 empty state).

    없는 원은 404 `NOT_FOUND` 로 답한다 — 계약에 명시돼 있지 않아 여기서 정하고
    보고서에 계약 보강안으로 올린다. 빈 목록과 없는 원을 같은 응답으로 돌려주면
    FE 가 "반을 추가해 주세요" 를 잘못된 원에도 띄운다.
    """
    # 없는 원과 남의 원을 같은 404 로 돌려준다 (shared/auth/ownership.py).
    require_own_center(user, center_id)

    # 계약이 순서를 정하지 않았다. 정렬을 빼면 Postgres 가 행 순서를 보장하지 않아
    # 같은 요청이 다른 순서로 온다 — 화면 카드 순서가 흔들리지 않게 id 로 고정한다.
    classes = session.scalars(
        select(Class).where(Class.center_id == center_id).order_by(Class.id)
    ).all()
    return ClassListResponse(items=list(classes))


@router.get("/{center_id}/greetings", response_model=GreetingsSettings)
def get_greetings(center_id: int, session: DbSession, user: CurrentUser) -> GreetingsSettings:
    require_own_center(user, center_id)
    _greetings_center(session, center_id)
    row = session.get(Greetings, center_id)
    return default_greetings() if row is None else GreetingsSettings.model_validate(row)


@router.put("/{center_id}/greetings", response_model=GreetingsSettings)
def put_greetings(
    center_id: int, body: GreetingsSettings, session: DbSession, user: CurrentUser
) -> GreetingsSettings:
    require_own_center(user, center_id)
    # 설정 행이 아직 없어도 같은 원의 동시 PUT을 직렬화한다.
    _greetings_center(session, center_id, lock=True)
    row = session.get(Greetings, center_id)
    if row is None:
        row = Greetings(center_id=center_id, **default_greetings().model_dump())
        session.add(row)
    row.enabled = body.enabled
    # off 요청도 12개월 형식은 검증하되 기존 문구를 교체하지 않는다 (§3).
    if body.enabled:
        row.items = [item.model_dump() for item in body.items]
    session.commit()
    return GreetingsSettings.model_validate(row)


def _greetings_center(session: Session, center_id: int, *, lock: bool = False) -> Center:
    query = select(Center).where(Center.id == center_id)
    if lock:
        query = query.with_for_update()
    center = session.scalar(query)
    if center is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "원을 찾을 수 없습니다.",
                "fields": ["center_id"],
            },
        )
    return center
