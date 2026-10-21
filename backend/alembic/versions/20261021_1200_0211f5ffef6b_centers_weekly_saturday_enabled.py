"""centers.weekly_saturday_enabled — 주간계획안에 토요일을 넣을지 원마다 정한다

PM 결정(ADR-030 WQ-01): 주간계획안은 기본 월~금, 원 설정으로 토요일을 켤 수 있다.
기본값은 거짓이다. 주간계획안은 만들 때 이 값을 계획안 안에 복사하므로
(docs/weekly-plan-contract.md §3), 바꿔도 이미 만든 계획안은 그대로다.

Revision ID: 0211f5ffef6b
Revises: c41ab7d6e508
Create Date: 2026-10-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0211f5ffef6b"
down_revision: str | None = "c41ab7d6e508"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default 를 둔다 — 이미 있는 원에도 값이 채워져야 NOT NULL 이 선다 (trends_enabled 와 같음).
    op.add_column(
        "centers",
        sa.Column(
            "weekly_saturday_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="주간계획안에 토요일을 넣을지 (ADR-030 WQ-01). **기본은 꺼짐** — 월~금",
        ),
    )


def downgrade() -> None:
    op.drop_column("centers", "weekly_saturday_enabled")
