"""원을 만든 교사 · 양식을 올린 교사 칸 (ADR-087)

원 설정 · 성품인사 바꾸기와 남의 양식 지우기를 원을 만든 교사만 하게 한다.
옛 원은 그 원 교사 중 id 가 가장 작은 교사로 채운다 —
ADR-068 §6 의 옛 반 주인 채우기와 같은 규칙이다.
옛 양식은 올린 교사를 모른다. NULL 로 두고, 원을 만든 교사만 지운다.

Revision ID: 8c924b13d7c4
Revises: 257732bf88ab
Create Date: 2026-11-10 02:07:06.754998

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c924b13d7c4"
down_revision: str | None = "257732bf88ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "centers",
        sa.Column(
            "created_by",
            sa.Integer(),
            nullable=True,
            comment=(
                "원을 만든 계정(ADR-087). 원 설정 · 성품인사를 바꾸고 남의 양식을 지울 수 있는 "
                "유일한 교사다. NULL 은 교사가 없는 원"
            ),
        ),
    )
    op.create_foreign_key(
        op.f("fk_centers_created_by_users"), "centers", "users", ["created_by"], ["id"]
    )
    op.add_column(
        "forms",
        sa.Column(
            "uploaded_by",
            sa.Integer(),
            nullable=True,
            comment=(
                "올린 계정(ADR-087). 이 교사와 원을 만든 교사만 지운다. NULL 은 이 결정 전 양식"
            ),
        ),
    )
    op.create_foreign_key(
        op.f("fk_forms_uploaded_by_users"), "forms", "users", ["uploaded_by"], ["id"]
    )
    op.execute(
        """
        UPDATE centers c
        SET created_by = first.id
        FROM (
            SELECT center_id, MIN(id) AS id FROM users
            WHERE center_id IS NOT NULL GROUP BY center_id
        ) AS first
        WHERE c.created_by IS NULL AND c.id = first.center_id
        """
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_forms_uploaded_by_users"), "forms", type_="foreignkey")
    op.drop_column("forms", "uploaded_by")
    op.drop_constraint(op.f("fk_centers_created_by_users"), "centers", type_="foreignkey")
    op.drop_column("centers", "created_by")
