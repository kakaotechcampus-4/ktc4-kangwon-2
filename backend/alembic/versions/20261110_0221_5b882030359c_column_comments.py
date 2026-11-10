"""컬럼 설명 두 곳을 지금 동작에 맞춘다 — 반 주인 NULL 의 뜻 · 활동 위험 표시 (#370 · #22)

Revision ID: 5b882030359c
Revises: 8c924b13d7c4
Create Date: 2026-11-10 02:21:14.374216

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

NEW_OWNER = (
    "반 주인 — 반을 만든 계정(ADR-059). 옛 반은 그 원 첫 교사로 채웠다(ADR-068 §6). "
    "NULL 은 교사가 없는 원의 반이다"
)

# revision identifiers, used by Alembic.
revision: str = "5b882030359c"
down_revision: str | None = "8c924b13d7c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "activities",
        "safety_flags",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment="resources/rules/safety_flags.yaml 의 값. 아직 대조하는 규칙이 없다",
        existing_comment="resources/rules/safety_flags.yaml 의 값. safety 규칙이 대조한다",
        existing_nullable=False,
    )
    op.alter_column(
        "classes",
        "teacher_id",
        existing_type=sa.INTEGER(),
        comment=NEW_OWNER,
        existing_comment="반 주인 — 반을 만든 계정(ADR-059). NULL 은 이 결정 전에 만든 옛 반이다",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "classes",
        "teacher_id",
        existing_type=sa.INTEGER(),
        comment="반 주인 — 반을 만든 계정(ADR-059). NULL 은 이 결정 전에 만든 옛 반이다",
        existing_comment=NEW_OWNER,
        existing_nullable=True,
    )
    op.alter_column(
        "activities",
        "safety_flags",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment="resources/rules/safety_flags.yaml 의 값. safety 규칙이 대조한다",
        existing_comment="resources/rules/safety_flags.yaml 의 값. 아직 대조하는 규칙이 없다",
        existing_nullable=False,
    )
