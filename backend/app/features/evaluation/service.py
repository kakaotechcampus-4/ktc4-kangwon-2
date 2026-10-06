"""자기 점검 체크 저장·조회. 시각과 허용 평가요소는 호출자가 정한다(§12)."""

from collections import Counter
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.evaluation.models import EvaluationCheck
from app.shared.school_year import school_year_of


class InvalidChecks(Exception):
    """틀린 평가요소 전부를 요청 순서로 담는다. HTTP 변환은 호출자가 한다."""

    elements: list[str]

    def __init__(self, elements: list[str]) -> None:
        self.elements = elements
        super().__init__(elements)


def save_checks(
    session: Session,
    center_id: int,
    now: datetime,
    checks: Sequence[tuple[str, bool]],
    allowed: AbstractSet[str],
) -> None:
    """전부 검사한 뒤 올해 체크를 저장한다. flush 만 하고 커밋은 호출자에게 맡긴다."""
    school_year = school_year_of(now)
    counts = Counter(element for element, _ in checks)
    invalid = list(
        dict.fromkeys(
            element for element, _ in checks if element not in allowed or counts[element] > 1
        )
    )
    if invalid:
        raise InvalidChecks(invalid)

    # 같은 원의 저장을 하나씩 처리한다.
    # READ COMMITTED 줄 잠금은 기다리는 동안 생긴 줄을 못 본다.
    # 이 advisory 잠금은 커밋·롤백 때 풀린다.
    session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("evaluation_checks"), center_id))
    )

    # 같은 세션에서 먼저 읽은 ORM 값도 잠금 뒤 최신 DB 값으로 다시 읽는다.
    existing = {
        row.element: row
        for row in session.scalars(
            select(EvaluationCheck)
            .where(
                EvaluationCheck.center_id == center_id,
                EvaluationCheck.school_year == school_year,
                EvaluationCheck.element.in_(counts),
            )
            .execution_options(populate_existing=True)
        )
    }
    for element, checked in checks:
        row = existing.get(element)
        if row is None:
            if checked:
                session.add(
                    EvaluationCheck(
                        center_id=center_id,
                        school_year=school_year,
                        element=element,
                        checked_at=now,
                    )
                )
        elif not checked:
            session.delete(row)
    session.flush()


def read_checks(session: Session, center_id: int, school_year: int) -> dict[str, datetime]:
    """해당 원·학년도에 남아 있는 체크 시각을 읽는다."""
    return dict(
        session.execute(
            select(EvaluationCheck.element, EvaluationCheck.checked_at).where(
                EvaluationCheck.center_id == center_id,
                EvaluationCheck.school_year == school_year,
            )
        ).all()
    )
