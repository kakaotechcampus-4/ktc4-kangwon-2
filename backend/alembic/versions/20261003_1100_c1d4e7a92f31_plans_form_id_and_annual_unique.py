"""plans 에 form_id · 연간은 반 하나에 하나

멘토 리뷰(PR #82) 반영.

- `form_id`  어느 양식에서 나온 계획안인지. 양식 원본은 하나만 두고 계획안은 번호만 든다.
             FK 라서 파생 계획안이 남아 있는 양식은 지워지지 않는다.
- 부분 유니크  연간은 반 하나에 하나. 라우터가 먼저 보고 409 를 내지만 동시 요청은
             조회로 못 막는다 — 둘 다 「없다」를 보고 지나간다.

**이미 중복이 있으면 이 마이그레이션이 실패한다.** 그게 맞다 — 파일럿 전에 알아야 한다.

Revision ID: c1d4e7a92f31
Revises: 0340d141da97
Create Date: 2026-10-03 11:00
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d4e7a92f31"
down_revision: Union[str, None] = "0340d141da97"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column(
            "form_id",
            sa.Integer(),
            nullable=True,
            comment="원이 올린 양식. 없으면 우리 기본 서식",
        ),
    )
    op.create_index(op.f("ix_plans_form_id"), "plans", ["form_id"])
    op.create_foreign_key("fk_plans_form_id_forms", "plans", "forms", ["form_id"], ["id"])
    op.create_index(
        "uq_plans_annual_per_classroom",
        "plans",
        ["center_id", "classroom_ref"],
        unique=True,
        postgresql_where=sa.text("kind = 'annual'"),
    )


def downgrade() -> None:
    op.drop_index("uq_plans_annual_per_classroom", table_name="plans")
    op.drop_constraint("fk_plans_form_id_forms", "plans", type_="foreignkey")
    op.drop_index(op.f("ix_plans_form_id"), table_name="plans")
    op.drop_column("plans", "form_id")
