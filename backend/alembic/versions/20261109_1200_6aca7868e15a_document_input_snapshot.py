"""관찰 근거 사본에 영역 · 상황, 문서에 영역 축을 더한다 (ADR-077)

종이의 영역 행이 원본 기록의 영역과 원의 지금 축을 따라 바뀌었다. 만들 때의 입력을 사본으로 남긴다.

**기존 행은 확실할 때만 채운다.** 원본이 문서보다 1분 넘게 먼저 마지막으로 고쳐졌고 사본의
글 · 날짜가 원본과 같으면, 지금 원본의 영역 · 상황이 만들 때의 값이다. 그 밖은 NULL 로 두고
「다시 확인」으로 다룬다 — 새 코드는 NULL 이면 예전처럼 원본 · 원의 축을 읽는다.

열을 더하기만 한다. 옛 코드는 새 열을 모르고 NULL 로 넣으므로 ADR-073 의 되감기를 지난다.
`backfill` 은 다시 돌려도 된다 — 비어 있는 칸만 채운다.

Revision ID: 6aca7868e15a
Revises: 7ee95b0e8ac0
Create Date: 2026-11-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6aca7868e15a"
down_revision: str | Sequence[str] | None = "7ee95b0e8ac0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 리비전은 스냅샷이라 app 코드를 import 하지 않는다 (observations/models.py AXES 와 같은 값).
NURI = "'신체운동·건강', '의사소통', '사회관계', '예술경험', '자연탐구'"
DAILY_PLAY = "'일상생활', '놀이활동'"


def backfill(bind) -> None:
    bind.execute(
        sa.text(
            "UPDATE document_sources AS ds SET domain = o.domain, context = o.context "
            "FROM observations AS o, documents AS d "
            "WHERE ds.source_kind = 'observation' AND ds.domain IS NULL "
            "AND o.id = ds.source_id AND d.id = ds.document_id "
            "AND o.updated_at < d.created_at - interval '1 minute' "
            "AND ds.text = o.fact AND ds.date = o.date"
        )
    )
    # 근거 영역을 모두 알고, 그 영역이 한 축에만 들 때만 축을 정한다.
    bind.execute(
        sa.text(
            "UPDATE documents AS d SET observation_axis = s.axis FROM ("
            "  SELECT document_id, CASE"
            f"   WHEN bool_and(domain IN ({NURI})) THEN 'NURI_5'"
            f"   WHEN bool_and(domain IN ({DAILY_PLAY})) THEN 'DAILY_PLAY_2' END AS axis"
            "  FROM document_sources WHERE source_kind = 'observation'"
            "  GROUP BY document_id HAVING count(*) = count(domain)"
            ") AS s "
            "WHERE d.id = s.document_id AND d.observation_axis IS NULL AND s.axis IS NOT NULL"
        )
    )


def upgrade() -> None:
    op.add_column(
        "document_sources",
        sa.Column(
            "domain",
            sa.String(length=20),
            nullable=True,
            comment=(
                "observation 근거일 때 생성 시점 영역 사본. 종이의 영역 행을 가른다. "
                "그 밖의 근거와 옛 사본(「다시 확인」)은 NULL (ADR-077)"
            ),
        ),
    )
    op.add_column(
        "document_sources",
        sa.Column(
            "context",
            sa.String(length=50),
            nullable=True,
            comment=(
                "observation 근거일 때 생성 시점 상황 사본. 빈 문자열은 「상황 없음」, "
                "NULL 은 그 밖의 근거와 옛 사본이다 (ADR-077)"
            ),
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "observation_axis",
            sa.String(length=20),
            nullable=True,
            comment=(
                "관찰 기록 근거 문서를 만들 때 원이 쓰던 영역 축(NURI_5 · DAILY_PLAY_2). "
                "종이의 영역 행을 정한다. NULL 이면 옛 문서라 원의 지금 축을 쓴다 (ADR-077)"
            ),
        ),
    )
    backfill(op.get_bind())


def downgrade() -> None:
    op.drop_column("documents", "observation_axis")
    op.drop_column("document_sources", "context")
    op.drop_column("document_sources", "domain")
