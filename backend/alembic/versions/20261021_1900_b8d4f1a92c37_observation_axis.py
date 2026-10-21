"""관찰 축이 둘이다 — centers.observation_axis 와 넓힌 domain CHECK

교사가 쓴 관찰일지 3건을 재 보니 **2건이 누리과정 5영역이 아니었다**
(docs/references/관찰일지-서술-기준.md).

    A02          신체운동·건강 · 의사소통 · 사회관계 · 예술경험 · 자연탐구
    S01 · S05    일상생활 · 놀이활동

5영역으로 박아 두면 2축을 쓰는 원은 관찰 기록을 아예 넣을 수 없다.

**CHECK 는 두 축의 값을 모두 받는다.** 「지금 이 원이 쓸 수 있는 값인가」는 라우터가 본다 —
원이 축을 바꿔도 전에 쌓은 기록이 CHECK 에 걸려 못 읽히면 교사가 쓴 사실이 사라진다.

되돌리기는 **2축 기록이 없을 때만** 된다. 있으면 CHECK 를 좁히는 순간 DB 가 거절한다.

Revision ID: b8d4f1a92c37
Revises: d0d30e826c87
Create Date: 2026-10-21 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d4f1a92c37"
down_revision: str | None = "d0d30e826c87"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NURI = "'신체운동·건강', '의사소통', '사회관계', '예술경험', '자연탐구'"
DAILY_PLAY = "'일상생활', '놀이활동'"
# `op.f()` 로 감싼다. 안 감싸면 alembic 이름 규칙이 `ck_observations_` 를 한 번 더 붙여
# `ck_observations_ck_observations_domain` 을 찾는다 (처음 만든 마이그레이션도 op.f 를 썼다).
CHECK = "ck_observations_domain"


def upgrade() -> None:
    # server_default 를 둔다 — 이미 있는 원에도 값이 채워져야 NOT NULL 이 선다.
    op.add_column(
        "centers",
        sa.Column(
            "observation_axis",
            sa.String(length=16),
            server_default="NURI_5",
            nullable=False,
            comment=(
                "관찰 기록의 영역 축 (observations/models.py AXES). "
                "NURI_5 는 누리과정 5영역, DAILY_PLAY_2 는 일상생활·놀이활동. "
                "**기본은 NURI_5** — 교사 문서 3건 중 2건이 2축이라 둘 다 받는다"
            ),
        ),
    )
    op.drop_constraint(op.f(CHECK), "observations", type_="check")
    op.create_check_constraint(op.f(CHECK), "observations", f"domain IN ({NURI}, {DAILY_PLAY})")


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK), "observations", type_="check")
    # 2축 기록이 남아 있으면 여기서 멈춘다. 교사가 쓴 사실을 조용히 지우지 않는다.
    op.create_check_constraint(op.f(CHECK), "observations", f"domain IN ({NURI})")
    op.drop_column("centers", "observation_axis")
