"""일지 초안을 못 만들었을 때 남기는 표시 (ADR-093)

documents 에 NULL 을 받는 열 하나를 더하기만 한다(ADR-073 롤백 한 칸).
직전 코드는 이 열을 모른다 — 폴백 초안도 해석 · 지원이 빈 보통 초안으로 보인다.

Revision ID: a93f0e1d7c52
Revises: 5b882030359c
Create Date: 2026-11-11 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a93f0e1d7c52"
down_revision: str | None = "5b882030359c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "generation_fallback",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "초안을 못 만들어 사실만 채운 초안을 줬을 때 {reason, at} (ADR-093). "
                "해석 · 지원은 빈 칸으로 저장했다. NULL 이면 정상 초안이거나 AI 초안이 아니다"
            ),
        ),
    )


def downgrade() -> None:
    # 폴백 표시만 지워진다. 그 초안은 해석 · 지원이 빈 보통 초안으로 남는다.
    op.drop_column("documents", "generation_fallback")
