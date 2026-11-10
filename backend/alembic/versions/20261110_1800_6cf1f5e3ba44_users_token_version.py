"""users.token_version — 비밀번호 변경 · 카카오 잇기 때 그 전 토큰을 끊는다 (ADR-092)

Revision ID: 6cf1f5e3ba44
Revises: b7d2e9a4c1f3
Create Date: 2026-11-10 18:00:00.000000

열을 더하기만 한다. 기본값이 0 이고 옛 토큰(ver 없음)도 0 으로 읽으므로, 이 판 직전 코드와
지금 로그인해 있는 교사 모두 그대로 돈다(ADR-073).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6cf1f5e3ba44"
down_revision: str | Sequence[str] | None = "b7d2e9a4c1f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment=(
                "토큰의 ver 와 같아야 통과. 비밀번호 변경 · 카카오 잇기 때 올려 그 전 토큰을 끊는다"
                " (ADR-092)"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
