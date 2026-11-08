"""[시험 · 머지 금지] rollback compat 검사가 막는지 본다 — 옛 코드가 쓰는 users.kakao_id 를 지운다.

Revision ID: f0f0f0f0f0f0
Revises: e3b9f4a1c7d2
Create Date: 2026-11-08 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f0f0f0f0f0f0"
down_revision: str | Sequence[str] | None = "e3b9f4a1c7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("uq_users_kakao_id"), "users", type_="unique")
    op.drop_column("users", "kakao_id")


def downgrade() -> None:
    raise NotImplementedError("시험용 마이그레이션이다")
