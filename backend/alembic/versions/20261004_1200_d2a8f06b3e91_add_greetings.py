"""원별 성품인사 저장 (api-spec.md §3 · ADR-012).

Revision ID: d2a8f06b3e91
Revises: c1d4e7a92f31
Create Date: 2026-10-04 12:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d2a8f06b3e91"
down_revision = "c1d4e7a92f31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "greetings",
        sa.Column("center_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["center_id"], ["centers.id"], name=op.f("fk_greetings_center_id_centers")
        ),
        sa.PrimaryKeyConstraint("center_id", name=op.f("pk_greetings")),
    )


def downgrade() -> None:
    op.drop_table("greetings")
