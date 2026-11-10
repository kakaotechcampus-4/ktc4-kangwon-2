"""children.call_name — 외자 아이를 부르는 이름 (ADR-004 보완)

Revision ID: b7d2e9a4c1f3
Revises: 7ee95b0e8ac0
Create Date: 2026-11-09 13:00:00.000000

열을 더하기만 한다. 비어 있어도 되는 열이라 이 판 직전 코드도 그대로 돈다(ADR-073).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e9a4c1f3"
down_revision: str | Sequence[str] | None = "7ee95b0e8ac0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "children",
        sa.Column(
            "call_name",
            sa.String(length=50),
            nullable=True,
            comment="외자 아이를 부르는 이름(김민 -> 민이). 가명표에 넣는다. ADR-004 보완",
        ),
    )


def downgrade() -> None:
    op.drop_column("children", "call_name")
