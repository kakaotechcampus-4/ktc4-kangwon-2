"""상단바 알림함 (docs/api-spec.md §2-2 「알림함」 · ADR-097)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.auth.models import User
from app.features.centers.models import Class, ClassAccessRequest
from app.features.notifications.models import Notification
from app.features.notifications.schemas import (
    MAX_ITEMS,
    NotificationList,
    NotificationOut,
    NotificationsRead,
)
from app.shared.auth.dependency import CurrentUser

router = APIRouter(prefix="/me/notifications", tags=["notifications"])

DbSession = Annotated[Session, Depends(get_session)]


@router.get("", response_model=NotificationList)
def list_notifications(session: DbSession, user: CurrentUser) -> NotificationList:
    """내 알림 최근 30개. 원 · 반이 없어도 빈 목록이다. 안 읽은 수는 주지 않는다 — 화면이 센다."""
    rows = session.execute(
        select(Notification, ClassAccessRequest.class_id, Class.name, User.name)
        .join(ClassAccessRequest, ClassAccessRequest.id == Notification.request_id)
        .join(Class, Class.id == ClassAccessRequest.class_id)
        .join(User, User.id == ClassAccessRequest.requester_id)
        .where(Notification.user_id == user.id)
        # created_at 이 아니라 id 다 — 한 트랜잭션에서 만든 알림은 now() 가 같다.
        .order_by(Notification.id.desc())
        .limit(MAX_ITEMS)
    )
    return NotificationList(
        items=[
            NotificationOut(
                id=note.id,
                kind=note.kind,
                request_id=note.request_id,
                class_id=class_id,
                class_name=class_name,
                requester_name=requester_name,
                created_at=note.created_at,
                read_at=note.read_at,
            )
            for note, class_id, class_name, requester_name in rows
        ]
    )


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def read_notifications(body: NotificationsRead, session: DbSession, user: CurrentUser) -> Response:
    """남의 id · 없는 id 는 조용히 건너뛴다. 이미 읽은 것은 시각을 덮지 않는다."""
    session.execute(
        update(Notification)
        .where(
            Notification.id.in_(body.ids),
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=func.now())
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
