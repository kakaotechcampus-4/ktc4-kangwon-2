"""아동 명단 API. 계약은 docs/api-spec.md §2-1 이다.

경로가 `/classes/{class_id}/children` 과 `/children/{id}` 둘로 갈려 공통 prefix 가 없다.
main.py 가 `/api` 만 붙인다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.centers.models import Child, Class
from app.features.children.schemas import (
    ChildCreate,
    ChildListResponse,
    ChildResponse,
)
from app.shared.childCode import issue_code

router = APIRouter(tags=["children"])

# Annotated 로 주입한다. 기본값 자리에서 Depends() 를 호출하면 ruff 의 B008 에 걸린다.
DbSession = Annotated[Session, Depends(get_session)]


def _require_class(session: Session, class_id: int) -> None:
    """없는 반과 아동 0명인 반을 갈라 놓는다.

    같은 응답으로 돌려주면 FE 가 "아직 등록된 아동이 없어요" 를 없는 반에도 띄운다.
    봉투는 centers 가 쓰는 것과 같다 (docs/api-spec.md 「공통」).
    """
    if session.get(Class, class_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "반을 찾을 수 없습니다.",
                "fields": ["class_id"],
            },
        )


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
) -> Child:
    """아동을 등록하고 가명 `code` 를 발급한다 (docs/api-spec.md §2-1).

    **발급은 등록 시점이다.** 나중에 발급하면 이미 쌓인 기록을 다시 훑어야 한다.
    같은 반에서 쓰는 code 를 피해 고르지만, 최종 보장은 `UNIQUE(class_id, code)` 다 —
    경합 재시도는 만들지 않는다(§2-1).
    """
    _require_class(session, class_id)

    used = [child.code for child in _children_of(session, class_id)]
    child = Child(class_id=class_id, name=body.name, code=issue_code(body.name, used))
    session.add(child)
    session.commit()
    session.refresh(child)
    return child


@router.get("/classes/{class_id}/children", response_model=ChildListResponse)
def list_children(
    class_id: int,
    session: DbSession,
) -> ChildListResponse:
    """반의 아동 명단. 아동이 없으면 `{"items": []}` 다 (§2-1 의 empty state)."""
    _require_class(session, class_id)
    return ChildListResponse(items=_children_of(session, class_id))


@router.delete("/children/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_child(
    child_id: int,
    session: DbSession,
) -> None:
    """아동을 지운다. 오타 수정은 삭제 후 재등록이다 — 이름 수정(PATCH)은 P1 이다(§2-1).

    행이 사라지면 `UNIQUE(class_id, code)` 가 풀려 그 code 를 다시 발급할 수 있다.
    발급 이력을 따로 남기지 않는다.
    """
    child = session.get(Child, child_id)
    if child is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "아동을 찾을 수 없습니다.",
                "fields": ["child_id"],
            },
        )
    session.delete(child)
    session.commit()
