"""document_sections.heading 에 「첨부 원문」을 더한다 — 증빙 등록

교사가 원에서 쓰던 서류를 증빙으로 올리는 길(`POST /api/documents/import`, api-spec §11)이
열린다. 그 문서는 **우리가 만든 것이 아니라** 사실 · 해석 · 지원 3층이 없다. 계약도
「`IMPORT` 는 `sources` 가 비고 `sections` 는 `첨부 원문` 하나뿐이다」라고 적는다.

3층 규격(사실 · 해석 · 지원)은 그대로 둔다. 값 하나를 더할 뿐이고, 어느 heading 을 쓸지는
origin 이 가른다 — AI 가 만든 문서에 「첨부 원문」이 들어갈 길은 없다.

Revision ID: c7a9e1b35d42
Revises: e3c7b2a40f19
Create Date: 2026-10-28 15:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7a9e1b35d42"
down_revision: str | Sequence[str] | None = "e3c7b2a40f19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("heading", "document_sections", type_="check")
    op.create_check_constraint(
        "heading",
        "document_sections",
        "heading IN ('사실', '해석', '지원', '첨부 원문')",
    )


def downgrade() -> None:
    # 「첨부 원문」이 남아 있으면 되돌리는 쪽이 깨진다. 증빙으로 올린 문서를 먼저 지운다.
    op.execute("DELETE FROM documents WHERE origin = 'IMPORT'")
    op.drop_constraint("heading", "document_sections", type_="check")
    op.create_check_constraint(
        "heading",
        "document_sections",
        "heading IN ('사실', '해석', '지원')",
    )
