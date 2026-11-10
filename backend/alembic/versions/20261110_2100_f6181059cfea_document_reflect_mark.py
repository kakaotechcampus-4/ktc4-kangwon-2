"""확정한 일일 보육일지의 「반영」 표기 사본 (ADR-086 결정 7)

documents 에 NULL 을 받는 열 하나를 더하기만 한다(ADR-073 롤백 한 칸).
직전 코드가 확정한 문서는 NULL 로 남고, 새 코드는 NULL 을 「지금 원 설정을 읽는다」로 다룬다.

Revision ID: f6181059cfea
Revises: 257732bf88ab
Create Date: 2026-11-10 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6181059cfea"
down_revision: str | None = "257732bf88ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "reflect_mark",
            sa.String(length=10),
            nullable=True,
            comment=(
                "일일 보육일지를 확정할 때 원이 쓰던 「반영」 표기(ADR-086 결정 7). "
                "확정본 종이는 이 값을 쓴다 — 확정 뒤 원 설정을 바꿔도 그대로다. "
                "NULL 은 초안이거나 이 칸이 생기기 전에 확정한 옛 문서다(지금 원 설정을 읽는다)"
            ),
        ),
    )


def downgrade() -> None:
    # 확정 때 박은 표기가 지워진다. 옛 코드는 종이를 지금 원 설정으로 만든다.
    op.drop_column("documents", "reflect_mark")
