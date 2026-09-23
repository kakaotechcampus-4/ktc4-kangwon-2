"""add documents, document_sections, document_sources

Revision ID: f903a45ea894
Revises: 52bd3f0c6560
Create Date: 2026-09-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f903a45ea894'
down_revision: Union[str, None] = '52bd3f0c6560'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False, comment='dailyLog · weeklyLog · observation · assessment 중 하나 (docs/api-spec.md §11)'),
    sa.Column('title', sa.String(length=200), nullable=False, comment="서버 생성 — '{아이 이름} {문서 종류} ({기간})'. PUT 으로 교사가 덮어쓸 수 있다"),
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('child_id', sa.Integer(), nullable=True, comment='dailyLog · weeklyLog 는 반 단위라 NULL'),
    sa.Column('start_date', sa.Date(), nullable=False, comment='계약의 `start`. 컬럼명만 다르다 — `end` 는 SQL 예약어라 피했다'),
    sa.Column('end_date', sa.Date(), nullable=False, comment='계약의 `end`'),
    sa.Column('status', sa.String(length=20), nullable=False, comment='DRAFT -> CONFIRMED. 한 방향이다. 되돌리기는 P1'),
    sa.Column('origin', sa.String(length=20), nullable=False, comment='AI · TEACHER · TEMPLATE · IMPORT'),
    sa.Column('stale', sa.Boolean(), nullable=False, comment='근거(observations · documents)가 수정·삭제된 뒤 아직 안 봤다'),
    sa.Column('generation_method', sa.String(length=20), nullable=True, comment='예: RULE_LLM. origin 이 AI 가 아니면 NULL'),
    sa.Column('generation_rule_id', sa.String(length=80), nullable=True),
    sa.Column('generation_rule_version', sa.String(length=20), nullable=True),
    sa.Column('review_note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind != 'dailyLog' OR start_date = end_date", name=op.f('ck_documents_daily_log_single_day')),
    sa.CheckConstraint("kind IN ('dailyLog', 'weeklyLog', 'observation', 'assessment')", name=op.f('ck_documents_kind')),
    sa.CheckConstraint("kind NOT IN ('observation', 'assessment') OR child_id IS NOT NULL", name=op.f('ck_documents_child_scoped_kind_requires_child')),
    sa.CheckConstraint("origin IN ('AI', 'TEACHER', 'TEMPLATE', 'IMPORT')", name=op.f('ck_documents_origin')),
    sa.CheckConstraint('start_date <= end_date', name=op.f('ck_documents_date_range')),
    sa.CheckConstraint("status IN ('DRAFT', 'CONFIRMED')", name=op.f('ck_documents_status')),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], name=op.f('fk_documents_child_id_children')),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], name=op.f('fk_documents_class_id_classes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents'))
    )
    op.create_index(op.f('ix_documents_child_id'), 'documents', ['child_id'], unique=False)
    op.create_index(op.f('ix_documents_class_id'), 'documents', ['class_id'], unique=False)
    op.create_table('document_sections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('heading', sa.String(length=10), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('source_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='이 항목이 실제로 근거로 삼은 document_sources.source_id 의 부분집합'),
    sa.CheckConstraint("heading IN ('사실', '해석', '지원')", name=op.f('ck_document_sections_heading')),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_sections_document_id_documents')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_sections')),
    sa.UniqueConstraint('document_id', 'heading', name=op.f('uq_document_sections_document_id_heading'))
    )
    op.create_index(op.f('ix_document_sections_document_id'), 'document_sections', ['document_id'], unique=False)
    op.create_table('document_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('source_kind', sa.String(length=20), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False, comment='observations.id 또는 documents.id. FK 없음 — 다형 참조라 걸 수 없다'),
    sa.Column('class_id', sa.Integer(), nullable=False, comment='무효화 판정용 스냅샷. 렌더링엔 안 쓴다 (ADR-010 결정 1)'),
    sa.Column('child_id', sa.Integer(), nullable=True),
    sa.Column('date', sa.Date(), nullable=True, comment='근거 시점 — observation 근거면 그 기록의 date, document 근거(주간->일일)면 그 문서의 start_date (리뷰 반영: PR #50, LEEseungseok-01)'),
    sa.Column('source_status', sa.String(length=20), nullable=True, comment='document 근거일 때 그 문서의 생성 시점 status 스냅샷(DRAFT/CONFIRMED). observation 근거면 NULL — 관찰 기록엔 status 가 없다 (리뷰 반영: PR #50)'),
    sa.Column('text', sa.Text(), nullable=False, comment='생성 시점 원문 복사본. 원본이 나중에 바뀌어도 이 값은 안 바뀐다'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source_kind IN ('observation', 'document')", name=op.f('ck_document_sources_source_kind')),
    sa.CheckConstraint("source_status IS NULL OR source_status IN ('DRAFT', 'CONFIRMED')", name=op.f('ck_document_sources_source_status')),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], name=op.f('fk_document_sources_child_id_children')),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], name=op.f('fk_document_sources_class_id_classes')),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_document_sources_document_id_documents')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_sources')),
    sa.UniqueConstraint('document_id', 'source_kind', 'source_id', name=op.f('uq_document_sources_document_id_source_kind_source_id'))
    )
    op.create_index(op.f('ix_document_sources_document_id'), 'document_sources', ['document_id'], unique=False)
    op.create_index('ix_document_sources_source_kind_source_id', 'document_sources', ['source_kind', 'source_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_document_sources_source_kind_source_id', table_name='document_sources')
    op.drop_index(op.f('ix_document_sources_document_id'), table_name='document_sources')
    op.drop_table('document_sources')
    op.drop_index(op.f('ix_document_sections_document_id'), table_name='document_sections')
    op.drop_table('document_sections')
    op.drop_index(op.f('ix_documents_class_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_child_id'), table_name='documents')
    op.drop_table('documents')
