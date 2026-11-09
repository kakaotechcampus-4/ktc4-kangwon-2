"""문서에 AI 검토 결과를 붙여 둔다 (ADR-082, ADR-071 결정 8 보완)

반 전체 초안은 아이마다 만들 때 검토도 같이 돌린다. 교사는 나중에 하나씩 열어 보므로 결과를
그때까지 들고 있어야 한다. 결과는 **검토한 글의 지문(hash)과 함께** 둔다 — 글이 바뀌면 화면에
보이지 않는다.

열을 더하기만 한다. 옛 코드는 새 열을 모르고 NULL 로 두므로 ADR-073 의 되감기를 지난다.

Revision ID: c2d8e5a7f1b3
Revises: b54babf0bf03
Create Date: 2026-11-10 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c2d8e5a7f1b3"
down_revision: str | Sequence[str] | None = "b54babf0bf03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "ai_review",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "마지막 AI 검토 결과 {state, issues, message, hash}. hash 는 검토한 사실 · 해석 · "
                "지원의 지문이고, 지금 글과 다르면 보이지 않는다 (ADR-082)"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "ai_review")
