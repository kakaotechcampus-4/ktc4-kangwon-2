"""class_access_requests 표를 만든다 — 남의 반 열람 요청 (ADR-059)

Revision ID: a4e7c1d92b58
Revises: 5b8d2f6a9c13
Create Date: 2026-11-04 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4e7c1d92b58"
down_revision: str | Sequence[str] | None = "5b8d2f6a9c13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "class_access_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False, comment="보고 싶은 반"),
        sa.Column("requester_id", sa.Integer(), nullable=False, comment="요청한 계정"),
        sa.Column(
            "status",
            sa.String(length=10),
            nullable=False,
            comment="PENDING | APPROVED | REJECTED | REVOKED. 승인은 보기만 허락한다",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','REVOKED')",
            name=op.f("ck_class_access_requests_status"),
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_class_access_requests_class_id_classes")
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"], ["users.id"], name=op.f("fk_class_access_requests_requester_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_access_requests")),
        sa.UniqueConstraint(
            "class_id", "requester_id", name=op.f("uq_class_access_requests_class_id_requester_id")
        ),
    )
    op.create_index(op.f("ix_class_access_requests_class_id"), "class_access_requests", ["class_id"])
    op.create_index(
        op.f("ix_class_access_requests_requester_id"), "class_access_requests", ["requester_id"]
    )


def downgrade() -> None:
    op.drop_table("class_access_requests")
