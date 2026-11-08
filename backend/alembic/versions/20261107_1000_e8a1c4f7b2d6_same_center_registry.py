"""정부 어린이집 목록으로 같은 원을 묶는다 · 옛 반에 주인을 채운다 · 초대 코드를 걷는다 (ADR-068)

1. `centers.registry_key` — 정부 목록의 열쇠(시도|시군구|이름|주소). 같은 열쇠를 고른 교사를
   같은 원으로 들인다. 직접 적은 원 · 옛 원은 NULL 이라 UNIQUE 에 걸리지 않는다.
2. **주인 없는 옛 반(`classes.teacher_id` NULL)에 주인을 한 번 채운다.** 그 원에 가입한 교사 중
   가장 먼저 가입한(id 가 가장 작은) 교사다. 반을 만든 계정 기록이 없어서 그 원의 첫 교사가
   만들었다고 본다 — 초대 코드가 없던 원은 교사가 한 명뿐이다. 교사가 없는 원의 반은 그대로 둔다.
   채우지 않으면 원 번호로 새로 들어온 교사에게 옛 반이 「내 반」처럼 열리고 고치기까지 된다.
3. 초대 코드 표(`center_invites`)를 지운다. 원 고르기가 그 길을 대신한다(ADR-029 대체).

Revision ID: e8a1c4f7b2d6
Revises: d3b8f5a1c7e2
Create Date: 2026-11-07 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8a1c4f7b2d6"
down_revision: str | Sequence[str] | None = "d3b8f5a1c7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "centers",
        sa.Column(
            "registry_key",
            sa.String(length=300),
            nullable=True,
            comment=(
                "정부 어린이집 목록의 열쇠(시도|시군구|이름|주소, ADR-068). "
                "같은 열쇠를 고른 교사는 이 원으로 든다. 직접 적은 원은 NULL"
            ),
        ),
    )
    op.create_unique_constraint(op.f("uq_centers_registry_key"), "centers", ["registry_key"])
    op.execute(
        """
        UPDATE classes c
        SET teacher_id = first.id
        FROM (
            SELECT center_id, MIN(id) AS id FROM users
            WHERE center_id IS NOT NULL GROUP BY center_id
        ) AS first
        WHERE c.teacher_id IS NULL AND c.center_id = first.center_id
        """
    )
    op.drop_index(op.f("ix_center_invites_center_id"), table_name="center_invites")
    op.drop_table("center_invites")


def downgrade() -> None:
    op.create_table(
        "center_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("center_id", sa.Integer(), nullable=False),
        sa.Column(
            "code",
            sa.String(length=20),
            nullable=False,
            comment="secrets 로 만든 10자. 추측할 수 없다",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False, comment="코드를 만든 교사"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "used_by", sa.Integer(), nullable=True, comment="코드로 들어온 교사. 쓰기 전에는 NULL"
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["center_id"], ["centers.id"], name=op.f("fk_center_invites_center_id_centers")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_center_invites_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["used_by"], ["users.id"], name=op.f("fk_center_invites_used_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_center_invites")),
        sa.UniqueConstraint("code", name=op.f("uq_center_invites_code")),
    )
    op.create_index(
        op.f("ix_center_invites_center_id"), "center_invites", ["center_id"], unique=False
    )
    # 채운 주인은 되돌리지 않는다 — 누가 원래 NULL 이었는지 남겨 두지 않았다.
    op.drop_constraint(op.f("uq_centers_registry_key"), "centers", type_="unique")
    op.drop_column("centers", "registry_key")
