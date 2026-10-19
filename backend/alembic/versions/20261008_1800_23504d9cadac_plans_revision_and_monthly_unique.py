"""plans 에 revision · 월간 대상 월 · 월간은 반 · 월당 하나

결정 문서 12.4 D-3 · 12.5 · 12.6 PR-2.

- `revision`      저장할 때마다 +1. 편집 API 가 읽은 값과 비교해 409 를 낸다(연간과 공용).
                  기존 행은 1 이 된다.
- `target_month`  월간의 대상 월 YYYY-MM. body 에서 꺼낸다. 기존 월간 행은 body 에서 채운다.
- 부분 유니크      월간은 반 · 월당 하나. 라우터가 먼저 보고 409 를 내도 동시 요청은 조회로
                  못 막는다.

**이미 같은 반 · 월 월간이 둘 이상 있으면 이 마이그레이션이 실패한다.** 연간과 같다 —
파일럿 전에 알아야 한다.

Revision ID: 23504d9cadac
Revises: 1e5f8d9c3b44
Create Date: 2026-10-08 18:00
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "23504d9cadac"
down_revision: Union[str, None] = "1e5f8d9c3b44"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column(
            "revision",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="저장할 때마다 +1. 읽은 값과 다르면 그 사이 바뀐 것",
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "target_month",
            sa.String(length=7),
            nullable=True,
            comment="월간의 대상 월 YYYY-MM. body 의 target_month 에서 꺼낸 값이다",
        ),
    )
    op.execute(
        "UPDATE plans SET target_month = "
        "lpad(body->'target_month'->>'calendar_year', 4, '0') || '-' || "
        "lpad(body->'target_month'->>'calendar_month', 2, '0') "
        "WHERE kind = 'monthly'"
    )
    op.create_check_constraint(
        op.f("ck_plans_target_month_kind"), "plans", "(kind = 'monthly') = (target_month IS NOT NULL)"
    )
    op.create_index(
        "uq_plans_monthly_per_classroom_month",
        "plans",
        ["center_id", "classroom_ref", "target_month"],
        unique=True,
        postgresql_where=sa.text("kind = 'monthly'"),
    )


def downgrade() -> None:
    op.drop_index("uq_plans_monthly_per_classroom_month", table_name="plans")
    op.drop_constraint(op.f("ck_plans_target_month_kind"), "plans", type_="check")
    op.drop_column("plans", "target_month")
    op.drop_column("plans", "revision")
