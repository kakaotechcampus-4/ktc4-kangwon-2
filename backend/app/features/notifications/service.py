"""알림을 만들고 읽음으로 바꾼다. 다른 기능은 이 파일로만 부른다.

둘 다 커밋하지 않는다 — 알림은 그것을 만든 변경과 같은 트랜잭션에 들어간다(ADR-097).
"""

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.features.notifications.models import Notification, NotificationKind


def notify(session: Session, *, user_id: int, kind: NotificationKind, request_id: int) -> None:
    session.add(Notification(user_id=user_id, kind=kind, request_id=request_id))


def mark_request_read(session: Session, request_id: int) -> None:
    """그 요청이 PENDING 을 떠났다 — 반 주인에게 간 「요청이 왔다」를 읽은 것으로 바꾼다.

    id 로 UPDATE 한다. 요청의 상태를 하위질의로 보면 autoflush 를 끈 운영 세션과 켠 테스트
    세션이 다르게 돈다.
    """
    session.execute(
        update(Notification)
        .where(
            Notification.request_id == request_id,
            Notification.kind == "ACCESS_REQUESTED",
            Notification.read_at.is_(None),
        )
        .values(read_at=func.now())
        .execution_options(synchronize_session=False)
    )
