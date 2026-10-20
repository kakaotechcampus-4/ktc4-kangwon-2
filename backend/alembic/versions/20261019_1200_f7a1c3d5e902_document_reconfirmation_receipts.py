"""Store atomic reconfirmation receipts.

Revision ID: f7a1c3d5e902
Revises: d7c6da04c909
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a1c3d5e902"
down_revision = "d7c6da04c909"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_reconfirmations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("review_token", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"],
                                name=op.f("fk_document_reconfirmations_document_id_documents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_reconfirmations")),
        sa.UniqueConstraint("document_id", "review_token",
                            name=op.f("uq_document_reconfirmations_document_id_review_token")),
    )
    op.create_index(op.f("ix_document_reconfirmations_document_id"),
                    "document_reconfirmations", ["document_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_document_reconfirmations_document_id"), "document_reconfirmations")
    op.drop_table("document_reconfirmations")
