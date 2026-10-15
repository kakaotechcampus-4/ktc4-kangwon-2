"""양식 원본과 숨긴 시각을 저장한다 (ADR-026).

Revision ID: 2e6a7c82308e
Revises: 2652c5dee127
Create Date: 2026-10-08 16:53:33.365889
"""

import sqlalchemy as sa
from alembic import op

revision = "2e6a7c82308e"
down_revision = "2652c5dee127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "forms",
        sa.Column("content", sa.LargeBinary(), nullable=True, comment="업로드한 원본 바이트 (ADR-026)"),
    )
    op.add_column(
        "forms",
        sa.Column(
            "hidden_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="감춘 시각. null 이면 목록에 보인다 (ADR-026)",
        ),
    )


def downgrade() -> None:
    op.drop_column("forms", "hidden_at")
    op.drop_column("forms", "content")
