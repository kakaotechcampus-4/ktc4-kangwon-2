"""centers.trends_enabled — 트렌드봇을 원마다 끈다 (FR-808)

기본값은 거짓이다. 부가 기능은 원하는 원이 켜는 것이고, 지금은 수집 키가 비어 있어
켜짐이 기본이면 모든 원에서 「수집 실패」만 쌓인다 (docs/api-spec.md §3-1).

Revision ID: b4f1c2d7e9a3
Revises: d7c6da04c909
Create Date: 2026-10-17 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4f1c2d7e9a3"
down_revision: str | None = "d7c6da04c909"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default 를 둔다 — 이미 있는 원에도 값이 채워져야 NOT NULL 이 선다.
    # 뒤에 지우지 않는다. 지우면 이 마이그레이션만 돌린 DB 와 모델이 어긋난다.
    op.add_column(
        "centers",
        sa.Column(
            "trends_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="트렌드봇을 켤지 (FR-808). **기본은 꺼짐**",
        ),
    )


def downgrade() -> None:
    op.drop_column("centers", "trends_enabled")
