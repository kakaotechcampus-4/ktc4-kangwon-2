"""merge develop trends_enabled and task2 reconfirmation

Revision ID: 99de0f5d953a
Revises: b4f1c2d7e9a3, b6e2d4a71c38
Create Date: 2026-10-19 16:30:11.186660

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99de0f5d953a'
down_revision: Union[str, None] = ('b4f1c2d7e9a3', 'b6e2d4a71c38')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
