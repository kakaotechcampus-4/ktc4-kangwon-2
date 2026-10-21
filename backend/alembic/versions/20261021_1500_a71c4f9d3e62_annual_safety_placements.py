"""Teacher-entered annual safety placements and their audit.

Revision ID: a71c4f9d3e62
Revises: 0211f5ffef6b
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a71c4f9d3e62"
down_revision = "0211f5ffef6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column(
            "annual_safety",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="교사 안전교육 배치. months(월→구분 배열)와 audit(변경 전후·행위자·UTC 시각)",
        ),
    )


def downgrade() -> None:
    op.drop_column("plans", "annual_safety")
