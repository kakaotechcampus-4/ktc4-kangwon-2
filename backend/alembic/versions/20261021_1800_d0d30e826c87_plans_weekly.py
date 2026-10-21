"""plans 에 주간 — kind 'weekly' · week_id · 반 · 주당 하나

주간 계약(docs/weekly-plan-contract.md §13) · 승석 확인(2026-10-21): 주간은 월간과 같은
`plans` 테이블에 든다.

- `kind`           'weekly' 를 더한다.
- `target_month`   월간 · 주간이 가진다(주간은 그 주가 속한 달). 「월간만 있다」를
                   「연간만 없다」로 바꾼다.
- `week_id`        주간의 주 YYYY-MM-Wn. body 에서 꺼낸다. 주간만 가진다.
- 부분 유니크       주간은 반 · 주당 하나. 라우터가 먼저 보고 409 를 내도 동시 요청은 조회로
                   못 막는다(월간과 같다).

주간 행이 아직 없어 기존 행을 고치지 않는다.

Revision ID: d0d30e826c87
Revises: 0211f5ffef6b
Create Date: 2026-10-21 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0d30e826c87"
down_revision: str | None = "0211f5ffef6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_plans_kind"), "plans", type_="check")
    op.create_check_constraint(
        op.f("ck_plans_kind"), "plans", "kind IN ('annual','monthly','weekly')"
    )
    op.drop_constraint(op.f("ck_plans_target_month_kind"), "plans", type_="check")
    op.create_check_constraint(
        op.f("ck_plans_target_month_kind"), "plans", "(kind = 'annual') = (target_month IS NULL)"
    )
    op.alter_column(
        "plans",
        "target_month",
        existing_type=sa.String(length=7),
        existing_nullable=True,
        comment="월간 · 주간의 대상 월 YYYY-MM. body 의 target_month(주간은 week_id 의 달)에서 꺼낸 값이다",
        existing_comment="월간의 대상 월 YYYY-MM. body 의 target_month 에서 꺼낸 값이다",
    )
    op.alter_column(
        "plans",
        "kind",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        comment="annual | monthly | weekly",
        existing_comment="annual | monthly",
    )
    op.add_column(
        "plans",
        sa.Column(
            "week_id",
            sa.String(length=10),
            nullable=True,
            comment="주간의 주 YYYY-MM-Wn. body 의 week_id 에서 꺼낸 값이다",
        ),
    )
    op.create_check_constraint(
        op.f("ck_plans_week_id_kind"), "plans", "(kind = 'weekly') = (week_id IS NOT NULL)"
    )
    op.create_index(
        "uq_plans_weekly_per_classroom_week",
        "plans",
        ["center_id", "classroom_ref", "week_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'weekly'"),
    )


def downgrade() -> None:
    # 주간 행이 있으면 아래 CHECK 가 실패한다 — 먼저 지운다.
    op.execute("DELETE FROM plans WHERE kind = 'weekly'")
    op.drop_index("uq_plans_weekly_per_classroom_week", table_name="plans")
    op.drop_constraint(op.f("ck_plans_week_id_kind"), "plans", type_="check")
    op.drop_column("plans", "week_id")
    op.alter_column(
        "plans",
        "kind",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        comment="annual | monthly",
        existing_comment="annual | monthly | weekly",
    )
    op.alter_column(
        "plans",
        "target_month",
        existing_type=sa.String(length=7),
        existing_nullable=True,
        comment="월간의 대상 월 YYYY-MM. body 의 target_month 에서 꺼낸 값이다",
        existing_comment="월간 · 주간의 대상 월 YYYY-MM. body 의 target_month(주간은 week_id 의 달)에서 꺼낸 값이다",
    )
    op.drop_constraint(op.f("ck_plans_target_month_kind"), "plans", type_="check")
    op.create_check_constraint(
        op.f("ck_plans_target_month_kind"),
        "plans",
        "(kind = 'monthly') = (target_month IS NOT NULL)",
    )
    op.drop_constraint(op.f("ck_plans_kind"), "plans", type_="check")
    op.create_check_constraint(op.f("ck_plans_kind"), "plans", "kind IN ('annual','monthly')")
