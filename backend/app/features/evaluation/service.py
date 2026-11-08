"""자기 점검 체크 · 평가 서류 도장 근거 저장·조회(§12 · ADR-074).

시각과 허용 키는 호출자가 정한다.
"""

from collections import Counter
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.evaluation.models import (
    EvaluationCheck,
    EvaluationDirectorCheck,
    EvaluationDocMark,
)
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


# ── 평가 서류 도장 근거 (ADR-074) ────────────────────────────────────────


@dataclass(frozen=True)
class FolderScanRow:
    """폴더 검사 결과 한 줄. 파일 이름은 받지 않는다(ADR-045)."""

    doc: str
    status: str
    period_from: date
    period_to: date
    files: int
    gaps: int


def save_doc_marks(
    session: Session,
    center_id: int,
    user_id: int,
    now: datetime,
    checks: Sequence[tuple[str, bool]],
    scan: Sequence[FolderScanRow] | None,
) -> None:
    """이 교사의 직접확인과 폴더 결과를 저장한다. flush 만 하고 커밋은 호출자에게 맡긴다.

    직접확인은 처음 누른 시각을 지킨다 — 이미 눌린 것을 다시 눌러도 시각이 바뀌지 않는다.
    `scan` 이 있으면 이 교사의 폴더 결과를 통째로 바꾼다. 거기 없는 서류의 옛 결과는 지운다.
    체크도 폴더 결과도 없는 줄은 지운다.
    """
    school_year = school_year_of(now)
    # 같은 교사의 저장을 하나씩 처리한다(save_checks 와 같은 까닭). 원 · 교사로 잠근다.
    session.execute(
        select(
            func.pg_advisory_xact_lock(func.hashtext(f"evaluation_doc_marks:{center_id}"), user_id)
        )
    )
    rows = {
        row.doc: row
        for row in session.scalars(
            select(EvaluationDocMark)
            .where(
                EvaluationDocMark.center_id == center_id,
                EvaluationDocMark.school_year == school_year,
                EvaluationDocMark.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
    }

    def row_for(doc: str) -> EvaluationDocMark:
        if doc not in rows:
            rows[doc] = EvaluationDocMark(
                center_id=center_id, school_year=school_year, user_id=user_id, doc=doc
            )
            session.add(rows[doc])
        return rows[doc]

    for doc, checked in checks:
        if checked:
            row = row_for(doc)
            row.checked_at = row.checked_at or now
        elif doc in rows:
            rows[doc].checked_at = None

    if scan is not None:
        scanned = {result.doc: result for result in scan}
        for doc in set(rows) | set(scanned):
            result = scanned.get(doc)
            row = row_for(doc)
            row.folder_status = result.status if result else None
            row.folder_scanned_at = now if result else None
            row.folder_from = result.period_from if result else None
            row.folder_to = result.period_to if result else None
            row.folder_files = result.files if result else None
            row.folder_gaps = result.gaps if result else None

    for row in rows.values():
        if row.checked_at is None and row.folder_status is None:
            if row in session.new:
                session.expunge(row)
            else:
                session.delete(row)
    session.flush()


def read_doc_marks(
    session: Session, center_id: int, school_year: int, user_id: int
) -> dict[str, EvaluationDocMark]:
    """이 교사의 올해 서류 줄을 서류 키로 읽는다."""
    return {
        row.doc: row
        for row in session.scalars(
            select(EvaluationDocMark).where(
                EvaluationDocMark.center_id == center_id,
                EvaluationDocMark.school_year == school_year,
                EvaluationDocMark.user_id == user_id,
            )
        )
    }


def save_director_checks(
    session: Session, center_id: int, now: datetime, checks: Sequence[tuple[str, bool]]
) -> None:
    """원장 서류 체크 — 원 단위.

    줄이 있으면 체크된 것이고 풀면 지운다(자체평가 체크와 같은 모양).
    """
    school_year = school_year_of(now)
    session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("evaluation_director_checks"), center_id))
    )
    existing = {
        row.item: row
        for row in session.scalars(
            select(EvaluationDirectorCheck)
            .where(
                EvaluationDirectorCheck.center_id == center_id,
                EvaluationDirectorCheck.school_year == school_year,
            )
            .execution_options(populate_existing=True)
        )
    }
    for item, checked in checks:
        row = existing.get(item)
        if row is None and checked:
            session.add(
                EvaluationDirectorCheck(
                    center_id=center_id, school_year=school_year, item=item, checked_at=now
                )
            )
        elif row is not None and not checked:
            session.delete(row)
    session.flush()


def read_director_checks(session: Session, center_id: int, school_year: int) -> dict[str, datetime]:
    """원장 서류 체크 시각을 항목 키로 읽는다."""
    return dict(
        session.execute(
            select(EvaluationDirectorCheck.item, EvaluationDirectorCheck.checked_at).where(
                EvaluationDirectorCheck.center_id == center_id,
                EvaluationDirectorCheck.school_year == school_year,
            )
        ).all()
    )
