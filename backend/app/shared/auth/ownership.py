"""자기 원 것만 볼 수 있게 한다 (docs/api-spec.md 「인증」).

로그인만 확인하면 반쪽이다 — 토큰이 있는 사람이 `class_id` 를 1, 2, 3 으로 바꿔가며
남의 원 아동 명단을 다 읽을 수 있다.

**남의 것이면 403 이 아니라 404 다.** 403 은 「그건 있는데 너는 못 본다」라서 그 id 가
존재한다는 사실을 알려준다. 없는 id 와 남의 id 를 같은 응답으로 돌려준다.

「자기 **반**만」은 여기서 하지 않는다. 원장도 봐야 하고 담임이 바뀌기도 해서 규칙을
먼저 정해야 한다. 지금은 원 단위까지다.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.features.auth.models import User
from app.features.centers.models import Child, Class


def _not_found(what: str, field: str) -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": f"{what}을 찾을 수 없습니다.", "fields": [field]},
    )


def require_own_center(user: User, center_id: int) -> None:
    """이 교사의 원인가. 온보딩 전(center_id 가 None)이면 어떤 원도 자기 것이 아니다."""
    if user.center_id is None or user.center_id != center_id:
        raise _not_found("원", "center_id")


def require_own_class(session: Session, user: User, class_id: int) -> Class:
    classroom = session.get(Class, class_id)
    if classroom is None or user.center_id is None or classroom.center_id != user.center_id:
        raise _not_found("반", "class_id")
    return classroom


def require_own_child(session: Session, user: User, child_id: int) -> Child:
    child = session.get(Child, child_id)
    if child is None:
        raise _not_found("아동", "child_id")
    # 아동 -> 반 -> 원 순으로 따라간다. 반이 없어질 수 없으므로(FK) 한 번만 더 본다.
    require_own_class(session, user, child.class_id)
    return child
