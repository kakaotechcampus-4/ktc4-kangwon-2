"""원 API. 계약은 docs/api-spec.md §1 · §2 다."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.auth.models import User
from app.features.centers import registry
from app.features.centers.greetings import default_greetings
from app.features.centers.models import (
    Center,
    Child,
    Class,
    ClassAccessRequest,
    Greetings,
)
from app.features.centers.schemas import (
    CenterCreate,
    CenterCreated,
    CenterResponse,
    CenterSettings,
    CenterSettingsUpdate,
    ClassCreate,
    ClassListResponse,
    ClassResponse,
    ClassUpdate,
    DaycareItem,
    DaycareList,
    GreetingsSettings,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_center, require_own_class
from app.shared.school_year import school_year_of

router = APIRouter(prefix="/centers", tags=["centers"])
# 반 하나를 가리키는 경로. 원 아래가 아니라서 prefix 가 다르다 (main.py 가 `/api` 를 붙인다).
classes_router = APIRouter(prefix="/classes", tags=["classes"])
# 정부 어린이집 목록 찾기 (ADR-068). 원이 생기기 전 첫 설정에서 부른다.
daycares_router = APIRouter(prefix="/daycares", tags=["daycares"])

# Annotated 로 주입한다. 기본값 자리에서 Depends() 를 호출하면 ruff 의 B008 에 걸린다.
DbSession = Annotated[Session, Depends(get_session)]


def _class_response(
    classroom: Class, user: User, requests: dict[int, str] | None = None
) -> ClassResponse:
    """`my_access` 는 저장된 값이 아니라 로그인한 계정과 반 주인을 견줘 낸다 (ADR-059).

    주인이 없는 옛 반은 OPEN. 남의 반은 이 계정의 요청 상태(`requests`: 반 id -> status)이고,
    줄이 없으면 NONE 이다. 목록이 요청을 한 번에 읽어 넘긴다 — 반마다 읽으면 N+1 이다.
    """
    if classroom.teacher_id == user.id:
        access = "OWNER"
    elif classroom.teacher_id is None:
        access = "OPEN"
    else:
        access = (requests or {}).get(classroom.id, "NONE")
    # from_attributes 와 같이 getattr 로 읽는다. 가짜 세션을 쓰는 테스트도 그대로 돈다.
    fields = {
        name: getattr(classroom, name) for name in ClassResponse.model_fields if name != "my_access"
    }
    return ClassResponse(**fields, my_access=access)


# UNIQUE(center_id, name, school_year) 의 제약 이름. app/db.py 의 NAMING_CONVENTION 이
# 정하고 첫 마이그레이션이 이 이름으로 만들었다.
CLASS_NAME_UNIQUE = "uq_classes_center_id_name_school_year"


def _violated_constraint(error: IntegrityError) -> str | None:
    """psycopg 가 알려주는 위반 제약 이름. 알 수 없으면 None 이다.

    이름을 보지 않고 IntegrityError 를 전부 「반 이름 중복」으로 바꾸면, 연령 CHECK 나
    외래키 위반까지 409 ALREADY_EXISTS 로 나가 원인을 숨긴다.
    """
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _commit_class(session: Session) -> None:
    """반을 커밋한다. 같은 원 · 학년도에 같은 이름이 있으면 409 로 바꾼다 (생성 · 수정 공통)."""
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


def _teachers(session: Session, center_ids: list[int]) -> dict[int, int]:
    """원마다 가입한 교사 수. 이름은 세지 않는다."""
    if not center_ids:
        return {}
    rows = session.execute(
        select(User.center_id, func.count())
        .where(User.center_id.in_(center_ids))
        .group_by(User.center_id)
    )
    return dict(rows.all())


def _center_out(session: Session, center: Center) -> dict:
    """원 응답 — 정부 목록의 유형 · 주소와 교사 수를 붙인다."""
    found = registry.find(center.registry_key) if center.registry_key else None
    return {
        **CenterResponse.model_validate(center).model_dump(),
        "kind": found.kind if found else None,
        "address": found.address if found else None,
        "teacher_count": _teachers(session, [center.id]).get(center.id, 0),
    }


@daycares_router.get("", response_model=DaycareList)
def search_daycares(sido: str, sigungu: str, session: DbSession, q: str = "") -> DaycareList:
    """그 시군구 정부 어린이집 목록에서 이름으로 찾는다. 쌤플에 있는 원이면 교사 수를 붙인다."""
    hits = registry.search(sido, sigungu, q)
    centers = dict(
        session.execute(
            select(Center.registry_key, Center.id).where(
                Center.registry_key.in_([d.key for d in hits])
            )
        ).all()
    )
    counts = _teachers(session, list(centers.values()))
    return DaycareList(
        items=[
            DaycareItem(
                key=d.key,
                name=d.name,
                kind=d.kind,
                status=d.status,
                address=d.address,
                teacher_count=counts.get(centers.get(d.key, -1), 0),
            )
            for d in hits
        ]
    )


_ALREADY_EXISTS = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail={"code": "ALREADY_EXISTS", "message": "이미 등록한 원이 있습니다.", "fields": []},
)


def _join(session: Session, user: User, center: Center, response: Response) -> dict:
    user.center_id = center.id
    session.commit()
    response.status_code = status.HTTP_200_OK
    return {**_center_out(session, center), "joined": True}


@router.post("", response_model=CenterCreated, status_code=status.HTTP_201_CREATED)
def create_center(
    body: CenterCreate,
    response: Response,
    session: DbSession,
    user: CurrentUser,
) -> dict:
    """원을 만들거나, 정부 목록에서 고른 원이 이미 있으면 그 원으로 들어간다 (ADR-068).

    - `registry_key` 가 있으면 정부 목록에 있어야 한다. 이름 · 지역은 **목록 값으로** 저장한다 —
      그래야 다음 교사가 같은 원을 찾는다. 같은 열쇠의 원이 있으면 그리로 들어가고(200,
      `joined`), 원장 이름은 받지 않아도 되고 보내도 쓰지 않는다. 합류 승인은 없다(PM 결정).
    - 새로 만드는 원이면 원장 이름이 있어야 한다 — 없으면 422.
    - 없으면 직접 적은 원이다. 이름 중복을 막지 않는다 — 다른 지역에 같은 이름의 원이 있다.
    - **한 계정은 원 하나다** — 원이 있는 교사의 두 번째 요청은 409 다.
    """
    if user.center_id is not None:
        raise _ALREADY_EXISTS
    picked = registry.find(body.registry_key) if body.registry_key else None
    if body.registry_key and picked is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "어린이집 목록에 없는 원입니다. 다시 찾아 주세요.",
                "fields": ["registry_key"],
            },
        )
    if picked is not None:
        existing = session.scalar(select(Center).where(Center.registry_key == picked.key))
        if existing is not None:
            return _join(session, user, existing, response)
    if body.director_name is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "원장 이름을 적어 주세요.",
                "fields": ["director_name"],
            },
        )
    center = Center(
        name=picked.name if picked else body.name,
        director_name=body.director_name,
        region_sido=picked.sido if picked else body.region_sido,
        region_sigungu=picked.sigungu if picked else body.region_sigungu,
        registry_key=picked.key if picked else None,
    )
    session.add(center)
    try:
        session.flush()
    except IntegrityError:
        # 두 교사가 같은 원을 동시에 처음 골랐다. UNIQUE 가 한 줄만 남겼다 — 늦은 쪽은 그리로.
        session.rollback()
        existing = session.scalar(select(Center).where(Center.registry_key == picked.key))
        return _join(session, session.merge(user), existing, response)
    # 같은 트랜잭션에서 주인을 붙인다. 나눠 커밋하면 원은 생겼는데 주인이 없는 행이 남는다.
    user.center_id = center.id
    session.commit()
    session.refresh(center)
    return {**_center_out(session, center), "joined": False}


@router.get("/{center_id}", response_model=CenterResponse)
def get_center(center_id: int, session: DbSession, user: CurrentUser) -> dict:
    """내 원 정보 (§1). 초대로 들어온 교사는 브라우저에 원 정보가 없어 여기서 읽는다.

    남의 원과 없는 원은 같은 404 다 (shared/auth/ownership.py).
    """
    require_own_center(user, center_id)
    return _center_out(session, session.get(Center, center_id))


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
) -> ClassResponse:
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
        teacher_id=user.id,
        consent_confirmed_at=now if body.consent_confirmed else None,
    )
    session.add(classroom)
    _commit_class(session)
    session.refresh(classroom)
    return _class_response(classroom, user)


@classes_router.patch("/{class_id}", response_model=ClassResponse)
def patch_class(
    class_id: int, body: ClassUpdate, session: DbSession, user: CurrentUser
) -> ClassResponse:
    """등록한 반의 이름 · 연령 · 담임 이름 · 동의를 고친다 (§2 반 수정). **보낸 칸만 바꾼다.**

    반 주인(`teacher_id`)은 바뀌지 않는다 — `teacher_name` 은 화면에 보이는 글자다.
    """
    require_own_class(session, user, class_id)
    # 아이 등록(children/router.py)과 같은 행을 잠근다. 동의를 끄는 요청과 아이를 넣는 요청이
    # 겹쳐도 「아이가 있는데 동의가 꺼진 반」이 생기지 않는다.
    classroom = session.get(Class, class_id, with_for_update=True, populate_existing=True)
    if body.consent_confirmed is False:
        has_child = session.scalar(select(func.count()).where(Child.class_id == class_id))
        if has_child:
            # 다른 칸도 적용하지 않는다 — 한 요청이 반쯤만 먹으면 화면이 무엇이 바뀌었는지 모른다.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "GATE_BLOCKED",
                    "message": "아이 명단이 있는 반은 동의를 끌 수 없습니다.",
                    "fields": ["consent_confirmed"],
                },
            )
    if body.name is not None:
        classroom.name = body.name
    if body.age_min is not None:  # 스키마가 두 칸을 함께 받는다
        classroom.age_min = body.age_min
        classroom.age_max = body.age_max
    if body.teacher_name is not None:
        classroom.teacher_name = body.teacher_name
    if body.consent_confirmed is False:
        classroom.consent_confirmed_at = None
    elif body.consent_confirmed and classroom.consent_confirmed_at is None:
        # 이미 있으면 처음 시각을 둔다 — 이 칸은 체크박스 복원용이다.
        classroom.consent_confirmed_at = datetime.now(UTC)
    _commit_class(session)
    session.refresh(classroom)
    return _class_response(classroom, user)


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
    # dict(result) 는 Result 의 keys() 를 보고 매핑으로 착각한다 — 쌍으로 풀어 만든다.
    requests = {
        class_id: request_status
        for class_id, request_status in session.execute(
            select(ClassAccessRequest.class_id, ClassAccessRequest.status).where(
                ClassAccessRequest.requester_id == user.id
            )
        )
    }
    return ClassListResponse(items=[_class_response(c, user, requests) for c in classes])


@router.get("/{center_id}/settings", response_model=CenterSettings)
def get_center_settings(center_id: int, session: DbSession, user: CurrentUser) -> Center:
    """설정한 적 없어도 기본값이 담긴 행을 준다 — 빈 객체를 주지 않는다 (§3-1)."""
    require_own_center(user, center_id)
    return _center(session, center_id)


@router.put("/{center_id}/settings", response_model=CenterSettings)
def put_center_settings(
    center_id: int, body: CenterSettingsUpdate, session: DbSession, user: CurrentUser
) -> Center:
    require_own_center(user, center_id)
    center = _center(session, center_id, lock=True)
    # **보낸 칸만 바꾼다.** 안 보낸 칸은 건드리지 않는다 (§3-1).
    if body.trends_enabled is not None:
        center.trends_enabled = body.trends_enabled
    if body.weekly_saturday_enabled is not None:
        center.weekly_saturday_enabled = body.weekly_saturday_enabled
    if body.observation_axis is not None:
        center.observation_axis = body.observation_axis
    session.commit()
    session.refresh(center)
    return center


def _center(session: Session, center_id: int, *, lock: bool = False) -> Center:
    """원 한 줄. 잠글 때는 세션 캐시를 비우고 다시 읽는다.

    require_own_center 는 DB 를 안 읽지만, 같은 요청에서 먼저 읽은 적이 있으면
    잠금 뒤 읽기가 옛 값을 돌려준다 (children/router.py 와 같은 이유).
    """
    query = select(Center).where(Center.id == center_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
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
