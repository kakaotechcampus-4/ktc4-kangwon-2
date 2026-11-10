"""상단바 알림함 표. 계약은 docs/api-spec.md §2-2 「알림함」 · ADR-097 이다."""

from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

NotificationKind = Literal[
    "ACCESS_REQUESTED", "ACCESS_APPROVED", "ACCESS_REJECTED", "ACCESS_REVOKED"
]


class Notification(Base):
    """화면 안 알림 한 줄. 외부로 보내지 않는다(ADR-097).

    반 이름 · 요청자 이름 칸은 두지 않는다 — 읽을 때 request 에서 JOIN 한다.
    반 주인은 바뀌지 않고 요청 줄은 지워지지 않아서, 사본을 따로 들고 있을 까닭이 없다.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ACCESS_REQUESTED','ACCESS_APPROVED','ACCESS_REJECTED','ACCESS_REVOKED')",
            name="kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, comment="알림을 받는 계정"
    )
    kind: Mapped[str] = mapped_column(
        String(20),
        comment=(
            "ACCESS_REQUESTED(반 주인에게 · 열람 요청이 왔다) | "
            "ACCESS_APPROVED · ACCESS_REJECTED · ACCESS_REVOKED(요청자에게 · 주인의 결정)"
        ),
    )
    request_id: Mapped[int] = mapped_column(
        ForeignKey("class_access_requests.id"), comment="이 알림이 가리키는 열람 요청 줄"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="알림이 생긴 시각"
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="읽은 시각. NULL 이면 안 읽음"
    )
