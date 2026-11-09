"""관찰일지 입력 사본(ADR-088)과 일지 날씨(ADR-089) 두 갈래를 하나로 잇는다

스키마를 바꾸지 않는다. 두 리비전이 같은 부모(7ee95b0e8ac0)에서 갈라져 head 가 둘이라
`alembic upgrade head` 가 하나로 정해지지 않는다. 이 리비전이 둘을 묶어 head 를 하나로 만든다.
`alembic_version` 에는 이 리비전 한 줄만 남는다 —
deploy.sh 의 「12자리 16진수 하나」 판정을 지킨다(ADR-073).
두 갈래 리비전 파일은 고치지 않는다(ADR-073 결정 1).

Revision ID: b54babf0bf03
Revises: 6aca7868e15a, 463ecc68c630
Create Date: 2026-11-10 01:42:06.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b54babf0bf03"
down_revision: str | Sequence[str] | None = ("6aca7868e15a", "463ecc68c630")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
