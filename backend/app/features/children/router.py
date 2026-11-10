"""아동 명단 API. 계약은 docs/api-spec.md §2-1 이다.

경로가 `/classes/{class_id}/children` 과 `/children/{id}` 둘로 갈려 공통 prefix 가 없다.
main.py 가 `/api` 만 붙인다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.centers.models import Center, Child, Class
from app.features.children.schemas import (
    ChildCreate,
    ChildListResponse,
    ChildResponse,
    ChildTracking,
    ChildTrackingResponse,
    ChildUpdate,
)
from app.features.documents.models import Document, DocumentSource
from app.features.observations.models import AXES, DEFAULT_AXIS, NURI_DOMAINS, Observation
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_child, require_own_class
from app.shared.childCode import (
    SubstitutionError,
    call_suffix,
    has_final,
    load_pool,
    one_syllable,
)
from app.shared.childCode.allocation import allocate_for_class, check_class

router = APIRouter(tags=["children"])

# Annotated 로 주입한다. 기본값 자리에서 Depends() 를 호출하면 ruff 의 B008 에 걸린다.
DbSession = Annotated[Session, Depends(get_session)]


_UNSAFE_ROSTER = HTTPException(
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail={
        "code": "VALIDATION_FAILED",
        "message": "반 명단의 이름과 가명을 안전하게 구분할 수 없거나 가명이 부족합니다. "
        "명단을 확인해주세요. 기존 가명은 변경하지 않습니다.",
        "fields": ["name"],
    },
)


def _check_call_name(name: str, call_name: str | None) -> None:
    """부르는 이름은 외자 아이만, 그 글자나 등록 이름으로 시작해야 받는다(ADR-004 보완).

    가명에 같은 꼴을 붙여 보내야 해서다 — 김민 · 민이 · 가람 -> 가람이.
    """
    if call_name is None:
        return
    syllable = one_syllable(name)
    if syllable is None:
        message = "부르는 이름은 성을 빼면 한 글자인 이름에만 적어요."
    else:
        try:
            call_suffix(name, call_name)
            return
        except ValueError:
            example = f" 예: {syllable}이" if has_final(syllable) else ""
            message = (
                f"부르는 이름은 『{syllable}』 또는 『{name}』 뒤에 이어 적어 주세요.{example}"
            )
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "VALIDATION_FAILED", "message": message, "fields": ["call_name"]},
    )


def _rows(children: list[Child]) -> list[tuple[str, str, str | None]]:
    return [(child.name, child.code, child.call_name) for child in children]


def _children_of(session: Session, class_id: int) -> list[Child]:
    """그 반에 **지금 남아 있는** 아동. 목록 응답과 code 발급이 같은 조회를 쓴다.

    정렬을 빼면 Postgres 가 행 순서를 보장하지 않아 명단 번호가 흔들린다.
    """
    return list(
        session.scalars(select(Child).where(Child.class_id == class_id).order_by(Child.id)).all()
    )


@router.post(
    "/classes/{class_id}/children",
    response_model=ChildResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_child(
    class_id: int,
    body: ChildCreate,
    session: DbSession,
    user: CurrentUser,
) -> Child:
    """아동을 등록하고 가명 `code` 를 발급한다 (docs/api-spec.md §2-1).

    **발급은 등록 시점이다.** 나중에 발급하면 이미 쌓인 기록을 다시 훑어야 한다.
    반 행을 잠근 뒤 현재 명단으로 검증한다. 기존 code는 바꾸지 않는다.
    """
    # 없는 반과 남의 반을 같은 404 로 돌려준다 (shared/auth/ownership.py).
    require_own_class(session, user, class_id)

    # 빈 반도 같은 행을 잠근다. READ COMMITTED에서 대기 후 다음 명단 조회는
    # 선행 등록의 커밋을 보므로 code 중복과 양방향 이름 충돌을 함께 막는다.
    classroom = session.get(Class, class_id, with_for_update=True, populate_existing=True)
    # 잠근 행으로 본다 — 동의 끄기(PATCH /api/classes/{id})와 겹쳐도 어긋나지 않는다.
    if classroom.consent_confirmed_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "GATE_BLOCKED",
                "message": "법정대리인 동의를 확인한 반에만 아이를 넣을 수 있습니다.",
                "fields": ["class_id"],
            },
        )
    _check_call_name(body.name, body.call_name)
    try:
        code = allocate_for_class(
            load_pool(), body.name, _rows(_children_of(session, class_id)), body.call_name
        )
    except SubstitutionError as exc:
        raise _UNSAFE_ROSTER from exc
    child = Child(class_id=class_id, name=body.name, code=code, call_name=body.call_name)
    session.add(child)
    session.commit()
    session.refresh(child)
    return child


@router.get("/classes/{class_id}/children", response_model=ChildListResponse)
def list_children(
    class_id: int,
    session: DbSession,
    user: CurrentUser,
) -> ChildListResponse:
    """반의 아동 명단. 아동이 없으면 `{"items": []}` 다 (§2-1 의 empty state).

    **아동 실명이 내려오는 자리다.** 로그인만으로는 부족해서 자기 원인지까지 본다.
    """
    require_own_class(session, user, class_id, read_only=True)
    return ChildListResponse(items=_children_of(session, class_id))


@router.get("/classes/{class_id}/children/tracking", response_model=ChildTrackingResponse)
def track_children(class_id: int, session: DbSession, user: CurrentUser) -> ChildTrackingResponse:
    """반 아이들의 관찰 기록 수를 아이 · 영역별로 센다 (§2-1 발달 추적).

    GROUP BY 한 번이다. 기록 본문은 내려주지 않는다 — 한 아이의 기록은
    `GET /api/observations?child_id=` 로 따로 받는다. 반 전체 기록을 받아 화면에서 나누면
    아이 수 × 기록 수만큼 실명 · 본문이 한꺼번에 내려온다.
    """
    classroom = require_own_class(session, user, class_id, read_only=True)
    # 영역 칸은 **그 원이 쓰는 축**만 센다 (observations/models.py AXES). 축을 바꾼 원이면
    # 옛 축으로 쌓은 기록도 그대로 남아 있다 — 지금 축에 없는 이름은 뒤에 따로 붙인다.
    center = session.get(Center, classroom.center_id)
    axis = AXES.get(center.observation_axis if center else DEFAULT_AXIS, NURI_DOMAINS)
    rows = session.execute(
        select(
            Observation.child_id,
            Observation.domain,
            func.count(),
            func.max(Observation.date),
        )
        .where(Observation.class_id == class_id)
        .group_by(Observation.child_id, Observation.domain)
    ).all()
    counts: dict[int, dict[str, int]] = {}
    last: dict[int, object] = {}
    for child_id, domain, count, latest in rows:
        counts.setdefault(child_id, {})[domain] = count
        last[child_id] = max(latest, last.get(child_id, latest))
    items = []
    for child in _children_of(session, class_id):
        mine = counts.get(child.id, {})
        by_domain = {domain: mine.get(domain, 0) for domain in axis}
        # 축을 바꾸기 전에 쓴 기록. 0 이면 안 붙인다 — 빈 칸을 늘리지 않는다.
        for domain, count in mine.items():
            if domain not in by_domain and count:
                by_domain[domain] = count
        items.append(
            ChildTracking(
                child_id=child.id,
                name=child.name,
                code=child.code,
                total=sum(by_domain.values()),
                last_date=last.get(child.id),
                by_domain=by_domain,
            )
        )
    return ChildTrackingResponse(items=items)


@router.patch("/children/{child_id}", response_model=ChildResponse)
def update_child(
    child_id: int,
    body: ChildUpdate,
    session: DbSession,
    user: CurrentUser,
) -> Child:
    """부르는 이름만 고친다(§2-1). 등록과 같이 반 행을 잠그고 반 전체 표로 검증한다."""
    child = require_own_child(session, user, child_id)
    _check_call_name(child.name, body.call_name)
    session.get(Class, child.class_id, with_for_update=True, populate_existing=True)
    rows = [
        (c.name, c.code, body.call_name if c.id == child.id else c.call_name)
        for c in _children_of(session, child.class_id)
    ]
    try:
        check_class(rows)
    except SubstitutionError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_FAILED",
                "message": "반의 다른 아이 이름과 겹쳐 이 부르는 이름은 쓸 수 없어요.",
                "fields": ["call_name"],
            },
        ) from exc
    child.call_name = body.call_name
    session.commit()
    session.refresh(child)
    return child


@router.delete("/children/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_child(
    child_id: int,
    session: DbSession,
    user: CurrentUser,
) -> None:
    """아동을 지운다. 오타 수정은 삭제 후 재등록이다 — 이름 수정(PATCH)은 P1 이다(§2-1).

    행이 사라지면 `UNIQUE(class_id, code)` 가 풀려 그 code 를 다시 발급할 수 있다.
    발급 이력을 따로 남기지 않는다.
    """
    child = require_own_child(session, user, child_id)
    # 기록 · 문서가 이 아이를 가리키면 FK 에 걸려 500 이 났다. 무엇 때문인지 말해 준다.
    # 기록째 지우는 길은 아직 없다 — 지우면 확정한 일지의 근거가 사라진다.
    referenced = any(
        session.scalar(select(model.id).where(model.child_id == child_id).limit(1)) is not None
        for model in (Observation, Document, DocumentSource)
    )
    if referenced:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "GATE_BLOCKED",
                "message": "이 아이의 관찰 기록이나 문서가 있어 지울 수 없어요. "
                "기록과 문서를 먼저 지워주세요.",
                "fields": ["child_id"],
            },
        )
    session.delete(child)
    session.commit()
