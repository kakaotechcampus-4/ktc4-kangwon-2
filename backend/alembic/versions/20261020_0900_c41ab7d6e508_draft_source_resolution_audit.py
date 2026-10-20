"""Audit trail for sources dropped or replaced while a document is still a draft.

Revision ID: c41ab7d6e508
Revises: 99de0f5d953a
"""

import sqlalchemy as sa
from alembic import op

revision = "c41ab7d6e508"
down_revision = "99de0f5d953a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_source_resolutions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_id",
            sa.Integer(),
            nullable=False,
            comment="사라진 근거. FK 없음 — 이미 지워진 행이다",
        ),
        sa.Column(
            "action", sa.String(length=10), nullable=False, comment="drop(화면의 '제외') · replace"
        ),
        sa.Column(
            "replacement_id",
            sa.Integer(),
            nullable=True,
            comment="replace 일 때 고른 일과. FK 없음",
        ),
        sa.Column("before", sa.Text(), nullable=False, comment="사라지기 전 사본 원문"),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("action IN ('drop', 'replace')", name="action"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_source_resolutions_actor_user_id"),
        "document_source_resolutions",
        ["actor_user_id"],
    )
    op.create_index(
        op.f("ix_document_source_resolutions_document_id"),
        "document_source_resolutions",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_source_resolutions_document_id"), "document_source_resolutions")
    op.drop_index(
        op.f("ix_document_source_resolutions_actor_user_id"), "document_source_resolutions"
    )
    op.drop_table("document_source_resolutions")
