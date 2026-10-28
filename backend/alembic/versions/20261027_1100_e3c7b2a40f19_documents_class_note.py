"""documents.class_note — 반 운영 특이사항

공식 보육일지 양식 5종 전부에 「반 운영 특이사항」 칸이 있다
(docs/references/보육일지-공식양식.md). 현장 실물(멘토 제공 2025 주간 보육일지)은
하루 블록마다 이 줄을 두고 결석 · 부모면담 · 감염병 · 안전사고를 적는다.

사실 · 해석 · 지원 세 칸과 **성격이 다르다.** 놀이 기록이 아니라 그날 반에 있었던
행정 사항이라 근거(관찰 · 일과 기록)에서 나오지 않고, 교사가 직접 적는다. 그래서
`document_sections` 의 3층 규격(heading CHECK)을 건드리지 않고 문서에 칸을 하나 둔다.

Revision ID: e3c7b2a40f19
Revises: b8d4f1a92c37
Create Date: 2026-10-27 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3c7b2a40f19"
down_revision: str | Sequence[str] | None = "b8d4f1a92c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default 를 둔다 — 이미 있는 문서에도 값이 채워져야 NOT NULL 이 선다.
    op.add_column(
        "documents",
        sa.Column(
            "class_note",
            sa.Text(),
            server_default="",
            nullable=False,
            comment=(
                "반 운영 특이사항 — 결석 · 부모면담 · 감염병 · 안전사고처럼 그날 반에 "
                "있었던 일. 교사가 직접 적는다. 근거에서 나오지 않아 stale 판정에 들어가지 않는다"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "class_note")
