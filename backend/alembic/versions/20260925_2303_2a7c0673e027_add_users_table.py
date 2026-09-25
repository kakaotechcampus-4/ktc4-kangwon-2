"""add users table

Revision ID: 2a7c0673e027
Revises: 7c4a1e9f2b08
Create Date: 2026-09-25 23:03:10.037763


교사 계정. 아동 실명이 내려오는 API 를 막으려면 「누가 부르는가」가 먼저 있어야 한다.

center_id 는 nullable 이다 — 회원가입 시점에는 아직 원이 없고, 온보딩 1단계에서
원을 만들 때 채워진다.

비밀번호는 scrypt 해시와 계정별 salt 로 나눠 저장한다. 평문도 단순 해시도 두지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a7c0673e027'
down_revision: Union[str, None] = '7c4a1e9f2b08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False, comment='로그인 아이디. RFC 5321 의 최대 길이가 254 다'),
    sa.Column('name', sa.String(length=50), nullable=False, comment='교사 이름. 화면 인사말에 쓴다'),
    sa.Column('password_hash', sa.LargeBinary(length=64), nullable=False, comment='scrypt 해시'),
    sa.Column('password_salt', sa.LargeBinary(length=16), nullable=False, comment='계정마다 다르다'),
    sa.Column('center_id', sa.Integer(), nullable=True, comment='온보딩 1단계에서 원을 만들 때 채워진다. 회원가입 직후에는 NULL'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['center_id'], ['centers.id'], name=op.f('fk_users_center_id_centers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_index(op.f('ix_users_center_id'), 'users', ['center_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_center_id'), table_name='users')
    op.drop_table('users')
