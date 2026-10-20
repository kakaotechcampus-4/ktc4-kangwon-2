"""Record which deleted sources were dropped or replaced on reconfirmation.

Revision ID: b6e2d4a71c38
Revises: f7a1c3d5e902
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b6e2d4a71c38"
down_revision = "f7a1c3d5e902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_reconfirmations",
        sa.Column("resolutions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_reconfirmations", "resolutions")
