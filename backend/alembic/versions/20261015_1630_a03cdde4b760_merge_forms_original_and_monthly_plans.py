"""양식 원본(#121) 과 월간 계획안(#123 · #126) 두 갈래를 잇는다

두 갈래 모두 `2652c5dee127` 에서 나왔다.

- `2e6a7c82308e`  forms.content · forms.hidden_at (ADR-026, #121)
- `23504d9cadac`  template_profiles · plans.revision · 월간 대상 월 (월간 스택 마지막)

**스키마를 바꾸지 않는다.** 두 head 를 하나로 묶기만 한다. 이미 적용된 마이그레이션 ·
리비전 ID 는 그대로 둔다 — 어느 쪽을 먼저 올린 DB 에서도 남은 쪽만 적용된다.

Revision ID: a03cdde4b760
Revises: 2e6a7c82308e, 23504d9cadac
Create Date: 2026-10-15 16:30:11.023469
"""

from typing import Sequence, Union

revision: str = "a03cdde4b760"
down_revision: Union[str, Sequence[str], None] = ("2e6a7c82308e", "23504d9cadac")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
