"""plans 에 확정 때 찍은 반 이름 · 담임 이름을 더한다 (ADR-010 결정 1 · ADR-062)

내보내기가 반 이름을 `classes` 에서 그때그때 읽고 있었다. 반 수정 API(ADR-062)가 들어오면
확정본의 이름이 바뀌므로, 확정하는 순간의 값을 `plans` 에 찍는다.

**기존 확정본을 오늘의 반 값으로 채워도 잃는 것이 없다.** 지금까지 반 이름 · 담임 이름을
바꾸는 코드가 없었고 수정 API 도 아직 배포 전이라, 오늘의 값이 확정 당시 값과 같다.
CHECK 는 백필 뒤에 건다 — 반을 못 찾는 확정본이 있으면 마이그레이션이 크게 실패한다.

Revision ID: d3b8f5a1c7e2
Revises: a4e7c1d92b58
Create Date: 2026-11-04 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3b8f5a1c7e2"
down_revision: str | Sequence[str] | None = "a4e7c1d92b58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column(
            "class_name",
            sa.String(length=50),
            nullable=True,
            comment="확정할 때 찍은 반 이름. 내보내기가 쓴다 (ADR-010 결정 1 · ADR-062)",
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "teacher_name",
            sa.String(length=50),
            nullable=True,
            comment="확정할 때 찍은 담임 이름. 지금 찍는 문서는 없다 (ADR-010 결정 1 · ADR-062)",
        ),
    )
    op.execute(
        "UPDATE plans SET class_name = classes.name, teacher_name = classes.teacher_name "
        "FROM classes WHERE plans.status = 'CONFIRMED' AND plans.classroom_ref = classes.id::text"
    )
    op.create_check_constraint(
        op.f("ck_plans_confirmed_has_class_snapshot"),
        "plans",
        "status <> 'CONFIRMED' OR (class_name IS NOT NULL AND teacher_name IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_plans_confirmed_has_class_snapshot"), "plans", type_="check")
    op.drop_column("plans", "teacher_name")
    op.drop_column("plans", "class_name")
