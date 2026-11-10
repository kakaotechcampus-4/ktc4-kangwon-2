"""notifications 표를 만든다 — 상단바 알림함 (ADR-097)

새 표 하나를 더하기만 한다(ADR-073 롤백 한 칸). 직전 코드는 이 표를 모른다 —
알림이 안 만들어질 뿐 열람 요청 · 승인은 그대로 돈다.

Revision ID: b5dee31c5ce0
Revises: a93f0e1d7c52
Create Date: 2026-11-11 04:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5dee31c5ce0"
down_revision: str | None = "a93f0e1d7c52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="알림을 받는 계정"),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            comment=(
                "ACCESS_REQUESTED(반 주인에게 · 열람 요청이 왔다) | "
                "ACCESS_APPROVED · ACCESS_REJECTED · ACCESS_REVOKED(요청자에게 · 주인의 결정)"
            ),
        ),
        sa.Column(
            "request_id", sa.Integer(), nullable=False, comment="이 알림이 가리키는 열람 요청 줄"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="알림이 생긴 시각",
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="읽은 시각. NULL 이면 안 읽음",
        ),
        sa.CheckConstraint(
            "kind IN ('ACCESS_REQUESTED','ACCESS_APPROVED','ACCESS_REJECTED','ACCESS_REVOKED')",
            name=op.f("ck_notifications_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["class_access_requests.id"],
            name=op.f("fk_notifications_request_id_class_access_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"])


def downgrade() -> None:
    # 쌓인 알림이 지워진다. 열람 요청 · 승인 상태는 class_access_requests 에 그대로 남는다.
    op.drop_table("notifications")
