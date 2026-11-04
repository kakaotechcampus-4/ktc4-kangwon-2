"""classes.teacher_id 에 users.id FK 와 인덱스를 건다 — 반 주인 (ADR-059)

컬럼은 처음부터 있었고 지금까지 항상 NULL 이었다. 값을 채우는 단계는 없다 —
이 결정 전에 만든 옛 반은 주인이 없는 채로 둔다(NULL = 누구나 쓰는 반).

Revision ID: 5b8d2f6a9c13
Revises: c7a9e1b35d42
Create Date: 2026-11-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b8d2f6a9c13"
down_revision: str | Sequence[str] | None = "c7a9e1b35d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_COMMENT = "담임 계정. users.id 예정. FK 와 인덱스는 인증 PR(8주차)에서"
NEW_COMMENT = "반 주인 — 반을 만든 계정(ADR-059). NULL 은 이 결정 전에 만든 옛 반이다"


def upgrade() -> None:
    op.create_foreign_key("fk_classes_teacher_id_users", "classes", "users", ["teacher_id"], ["id"])
    op.create_index("ix_classes_teacher_id", "classes", ["teacher_id"])
    # 컬럼 comment 도 모델과 맞춘다. 안 맞추면 `alembic check` 가 차이로 잡는다.
    op.alter_column(
        "classes",
        "teacher_id",
        existing_type=sa.INTEGER(),
        comment=NEW_COMMENT,
        existing_comment=OLD_COMMENT,
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "classes",
        "teacher_id",
        existing_type=sa.INTEGER(),
        comment=OLD_COMMENT,
        existing_comment=NEW_COMMENT,
        existing_nullable=True,
    )
    op.drop_index("ix_classes_teacher_id", table_name="classes")
    op.drop_constraint("fk_classes_teacher_id_users", "classes", type_="foreignkey")
