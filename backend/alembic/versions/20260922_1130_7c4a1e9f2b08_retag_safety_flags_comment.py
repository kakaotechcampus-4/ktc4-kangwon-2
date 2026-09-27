"""retag activities.safety_flags comment to ADR-014

Revision ID: 7c4a1e9f2b08
Revises: 52bd3f0c6560
Create Date: 2026-09-22 11:30:00.000000

컬럼 주석만 바꾼다. 데이터도 타입도 그대로다.

ADR-005 가 ADR-014 로 대체되면서 「선별 3순위」라는 개념이 사라졌다. 규칙 엔진은
고르지 않고 검사한다. 주석은 Postgres 가 실제로 들고 있는 값이라 models.py 만
고치면 `alembic check` 가 어긋남을 잡는다.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7c4a1e9f2b08"
down_revision: Union[str, None] = "52bd3f0c6560"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_OLD = "resources/rules/safety_flags.yaml 의 값. 선별 3순위"
_NEW = "resources/rules/safety_flags.yaml 의 값. safety 규칙이 대조한다"


def upgrade() -> None:
    op.alter_column(
        "activities",
        "safety_flags",
        existing_type=_JSONB,
        existing_nullable=False,
        existing_comment=_OLD,
        comment=_NEW,
    )


def downgrade() -> None:
    op.alter_column(
        "activities",
        "safety_flags",
        existing_type=_JSONB,
        existing_nullable=False,
        existing_comment=_NEW,
        comment=_OLD,
    )
