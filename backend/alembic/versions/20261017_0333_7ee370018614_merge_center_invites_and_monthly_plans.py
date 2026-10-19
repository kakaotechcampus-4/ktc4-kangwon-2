"""교사 초대 코드(#139) 와 월간 계획안 갈래(a03cdde4b760) 를 잇는다

두 head 모두 `2e6a7c82308e`(#121) 뒤에서 갈라졌다.

- `d7c6da04c909`  center_invites (ADR-029, #139)
- `a03cdde4b760`  #121 과 월간 스택(template_profiles · plans.revision · 월간 대상 월) 을 이은 merge

**스키마를 바꾸지 않는다.** 두 갈래가 건드리는 테이블이 겹치지 않는다(center_invites 와
template_profiles · plans). 이미 적용된 마이그레이션 · 리비전 ID 는 그대로 둔다 — 어느 쪽을
먼저 올린 DB 에서도 남은 쪽만 적용된다.

Revision ID: 7ee370018614
Revises: a03cdde4b760, d7c6da04c909
Create Date: 2026-10-17 03:33:53.000000
"""

from typing import Sequence, Union

revision: str = "7ee370018614"
down_revision: Union[str, Sequence[str], None] = ("a03cdde4b760", "d7c6da04c909")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
