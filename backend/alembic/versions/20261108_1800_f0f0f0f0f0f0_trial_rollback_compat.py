"""[시험 · 머지 금지] rollback compat 검사가 통과시키는지 본다 — 옛 코드가 모르는 nullable 칸 하나를 더한다.

Revision ID: f0f0f0f0f0f0
Revises: e3b9f4a1c7d2
Create Date: 2026-11-08 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0f0f0f0f0f0"
down_revision: str | Sequence[str] | None = "e3b9f4a1c7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("trial_note", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "trial_note")
