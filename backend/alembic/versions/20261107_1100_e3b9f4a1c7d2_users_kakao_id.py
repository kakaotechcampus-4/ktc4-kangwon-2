"""users.kakao_id — 카카오 로그인 (ADR-069)

Revision ID: e3b9f4a1c7d2
Revises: e8a1c4f7b2d6
Create Date: 2026-11-06 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b9f4a1c7d2"
down_revision: str | Sequence[str] | None = "e8a1c4f7b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "kakao_id",
            sa.BigInteger(),
            nullable=True,
            comment="카카오 회원번호. 카카오로 로그인한 적이 있을 때만 채워진다 (ADR-069)",
        ),
    )
    op.create_unique_constraint(op.f("uq_users_kakao_id"), "users", ["kakao_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_users_kakao_id"), "users", type_="unique")
    op.drop_column("users", "kakao_id")
