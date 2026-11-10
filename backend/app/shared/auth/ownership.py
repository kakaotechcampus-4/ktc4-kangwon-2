"""자기 원 · 자기 반 것만 볼 수 있게 한다 (docs/api-spec.md 「인증」 · §2-2, ADR-059).

로그인만 확인하면 반쪽이다 — 토큰이 있는 사람이 `class_id` 를 1, 2, 3 으로 바꿔가며
남의 원 아동 명단을 다 읽을 수 있다.

**남의 원 것이면 403 이 아니라 404 다.** 403 은 「그건 있는데 너는 못 본다」라서 그 id 가
존재한다는 사실을 알려준다. 없는 id 와 남의 원 id 를 같은 응답으로 돌려준다.

**같은 원 안에서는 반 주인이 정한다.** 반을 만든 계정(`classes.teacher_id`)이 주인이고,
주인이 없는 옛 반(NULL)은 원 안 누구나 쓴다. 남의 반은 주인이 승인한 요청(APPROVED)이
있어야 **보기만** 한다. 승인이 없으면 403 `CLASS_ACCESS_REQUIRED`, 승인받고 쓰려 하면
403 `CLASS_READ_ONLY` — 같은 원의 반이라는 사실은 숨기지 않는다(목록에 이미 보인다).
"""

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, Select, String, and_, cast, or_, select
from sqlalchemy.orm import Session

from app.features.auth.models import User
from app.features.centers.models import Center, Child, Class, ClassAccessRequest


def _not_found(what: str, field: str) -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": f"{what}을 찾을 수 없습니다.", "fields": [field]},
    )


def _forbidden(code: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail={"code": code, "message": message, "fields": ["class_id"]},
    )


def require_own_center(user: User, center_id: int) -> None:
    """이 교사의 원인가. 온보딩 전(center_id 가 None)이면 어떤 원도 자기 것이 아니다."""
    if user.center_id is None or user.center_id != center_id:
        raise _not_found("원", "center_id")


def is_center_creator(session: Session, user: User, center_id: int) -> bool:
    """원을 만든 교사인가 (ADR-087). 교사가 없는 원(NULL)은 아무도 아니다."""
    created_by = session.scalar(select(Center.created_by).where(Center.id == center_id))
    return created_by is not None and created_by == user.id


def require_center_creator(session: Session, user: User, center_id: int) -> None:
    """원 전체에 걸리는 것을 바꾸는 교사인가 — 원을 만든 교사만이다 (ADR-087).

    합류 승인이 없어(ADR-068) 원 이름만 알면 누구나 그 원 교사가 된다. 같은 원 다른 교사는
    읽기만 한다. 같은 원이라는 사실은 숨기지 않으므로 404 가 아니라 403 이다.
    `require_own_center` 다음에 부른다 — 남의 원은 그쪽이 404 로 먼저 막는다.
    """
    if not is_center_creator(session, user, center_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CENTER_CREATOR_ONLY",
                "message": "원을 처음 등록한 선생님만 바꿀 수 있습니다.",
                "fields": ["center_id"],
            },
        )


def require_own_class(
    session: Session, user: User, class_id: int, read_only: bool = False
) -> Class:
    """이 교사가 쓸 수 있는 반인가. `read_only=True` 인 곳(읽기)만 승인받은 반을 들인다.

    기본값이 쓰기다 — 표시를 빠뜨린 곳이 새는 쪽이 아니라 막히는 쪽으로 틀린다.
    """
    classroom = session.get(Class, class_id)
    if classroom is None or user.center_id is None or classroom.center_id != user.center_id:
        raise _not_found("반", "class_id")
    if classroom.teacher_id is None or classroom.teacher_id == user.id:
        return classroom
    approved = session.scalar(
        select(ClassAccessRequest.id).where(
            ClassAccessRequest.class_id == class_id,
            ClassAccessRequest.requester_id == user.id,
            ClassAccessRequest.status == "APPROVED",
        )
    )
    if approved is None:
        raise _forbidden("CLASS_ACCESS_REQUIRED", "이 반 담임 선생님의 승인이 필요합니다.")
    if not read_only:
        raise _forbidden("CLASS_READ_ONLY", "승인받은 반은 보기만 할 수 있습니다.")
    return classroom


def require_own_child(
    session: Session, user: User, child_id: int, *, read_only: bool = False
) -> Child:
    child = session.get(Child, child_id)
    if child is None:
        raise _not_found("아동", "child_id")
    # 아동 -> 반 -> 원 순으로 따라간다. 반이 없어질 수 없으므로(FK) 한 번만 더 본다.
    require_own_class(session, user, child.class_id, read_only=read_only)
    return child


def own_class_clause(user: User) -> ColumnElement[bool]:
    """반을 지정하지 않는 목록이 쓰는 조건 — 내 반과 주인 없는 옛 반만 (승인받은 반은 뺀다)."""
    return and_(
        Class.center_id == user.center_id,
        or_(Class.teacher_id.is_(None), Class.teacher_id == user.id),
    )


def foreign_class_refs(user: User) -> Select:
    """같은 원의 **남의 반** id 를 문자열로 — 계획안이 반을 `classroom_ref` 문자열로 갖는다.

    목록은 `classroom_ref NOT IN (이것)` 으로 거른다. 「내 반만 IN」으로 하면 반 id 로 못 읽는
    행(옛 데이터)이 조용히 사라져, 목록이 그런 행을 건너뛰며 남기는 경고가 없어진다.
    """
    return select(cast(Class.id, String)).where(
        Class.center_id == user.center_id,
        Class.teacher_id.is_not(None),
        Class.teacher_id != user.id,
    )
