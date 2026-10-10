"""add template profile draft revision

DRAFT 임시 저장의 충돌 감지(M2-B). 저장할 때마다 revision 을 올리고, 본 revision 과 다르면 덮어쓰지
않는다. 기존 행은 revision 1 이 된다. body 는 그대로다.

Revision ID: 1e5f8d9c3b44
Revises: 6eab3767534d
Create Date: 2026-10-08 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1e5f8d9c3b44'
down_revision: Union[str, None] = '6eab3767534d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('template_profiles', sa.Column('revision', sa.Integer(), server_default='1', nullable=False, comment='DRAFT 를 저장할 때마다 +1. 본 것과 다르면 충돌'))
    op.add_column('template_profiles', sa.Column('updated_by', sa.Integer(), nullable=True, comment='DRAFT 를 마지막으로 저장하거나 확정한 계정'))
    op.create_foreign_key(op.f('fk_template_profiles_updated_by_users'), 'template_profiles', 'users', ['updated_by'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_template_profiles_updated_by_users'), 'template_profiles', type_='foreignkey')
    op.drop_column('template_profiles', 'updated_by')
    op.drop_column('template_profiles', 'revision')
