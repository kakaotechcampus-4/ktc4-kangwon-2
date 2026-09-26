"""add observations table

Revision ID: 3e5298ab9396
Revises: 2a7c0673e027
Create Date: 2026-09-22 15:46:00.000000

docs/api-spec.md §10 의 관찰 기록. 3층 규격의 ① 사실 층이고 §11 문서가 이걸 근거로 쓴다.

CHECK 의 5영역 값은 여기 문자열로 박는다. 모델의 DOMAINS 를 import 하지 않는다 —
마이그레이션은 그때의 스키마를 고정한 스냅샷이라, 나중에 모델이 바뀌면 과거 리비전의
의미까지 같이 바뀐다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e5298ab9396'
down_revision: Union[str, None] = '2a7c0673e027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('observations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('class_id', sa.Integer(), nullable=False),
    sa.Column('child_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False, comment='관찰한 날. 목록 정렬은 이 값 내림차순 고정 (docs/api-spec.md §10)'),
    sa.Column('domain', sa.String(length=20), nullable=False, comment='누리과정 5영역 중 하나'),
    sa.Column('context', sa.String(length=50), server_default='', nullable=False, comment='상황. 선택이라 빈 문자열을 허용한다 — NULL 을 쓰지 않아 FE 가 분기하지 않는다'),
    sa.Column('fact', sa.Text(), nullable=False, comment='교사가 입력한 관찰 사실. 길이를 계약이 정하지 않아 Text 다'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("domain IN ('신체운동·건강', '의사소통', '사회관계', '예술경험', '자연탐구')", name=op.f('ck_observations_domain')),
    sa.ForeignKeyConstraint(['child_id'], ['children.id'], name=op.f('fk_observations_child_id_children')),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], name=op.f('fk_observations_class_id_classes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_observations'))
    )
    op.create_index(op.f('ix_observations_child_id'), 'observations', ['child_id'], unique=False)
    op.create_index(op.f('ix_observations_class_id'), 'observations', ['class_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_observations_class_id'), table_name='observations')
    op.drop_index(op.f('ix_observations_child_id'), table_name='observations')
    op.drop_table('observations')
