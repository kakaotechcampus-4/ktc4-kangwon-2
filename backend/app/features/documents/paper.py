"""확정한 종이는 확정 뒤 바뀌지 않는다 — 확정할 때 종이에만 쓰는 값을 문서 쪽에 박는다.

날씨(ADR-081 결정 9)와 일과 줄의 「반영」 · 맞다고 한 활동(ADR-086)이다. 셋 다 3층 사실이 아니라
근거 사본(`text`)에 들어가지 않지만 종이에는 나간다. 확정 · 재확정 때 박고, 확정을 풀면 푼다.
박은 뒤 일과 기록의 반영 · 활동이 바뀌면 그 확정본은 `stale` 이다(`routines/drafts.py`).
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.features.documents.models import Document, DocumentSource
from app.features.routines.models import RoutineRecord
from app.features.routines.weather import stamp_confirmed_weather


def stamp_confirmed(session: Session, doc: Document) -> None:
    """확정 · 재확정 때 부른다. 일일 · 주간만 박을 것이 있다."""
    if doc.kind not in ("dailyLog", "weeklyLog"):
        return
    stamp_confirmed_weather(session, doc)
    copies = session.scalars(select(DocumentSource).where(DocumentSource.document_id == doc.id))
    copies = list(copies)
    routines = {
        r.id: r
        for r in session.scalars(
            select(RoutineRecord).where(
                RoutineRecord.id.in_([c.source_id for c in copies if c.source_kind == "routine"])
            )
        )
    }
    for copy in copies:
        if copy.source_kind == "routine" and copy.source_id in routines:
            record = routines[copy.source_id]
            copy.reflected, copy.activities = record.reflected, list(record.activities)
        elif copy.source_kind == "document":
            copy.activities = _daily_activities(session, copy.source_id)


def _daily_activities(session: Session, daily_id: int) -> list[str]:
    """주간이 근거로 쓴 일일 일지의 그날 활동 — 그 일일이 확정 때 박은 사본, 없으면 지금 원본."""
    names: list[str] = []
    for copy in session.scalars(
        select(DocumentSource)
        .where(DocumentSource.document_id == daily_id, DocumentSource.source_kind == "routine")
        .order_by(DocumentSource.id)
    ):
        if copy.activities is not None:
            names += copy.activities
        else:
            record = session.get(RoutineRecord, copy.source_id)
            names += record.activities if record else []
    return list(dict.fromkeys(names))


def clear_confirmed(session: Session, doc: Document) -> None:
    """확정을 풀면 박은 값을 푼다 — 초안 종이는 원본을 읽고, 다시 확정할 때 그때 값을 박는다."""
    doc.weather = None
    session.execute(
        update(DocumentSource)
        .where(DocumentSource.document_id == doc.id)
        .values(reflected=None, activities=None)
    )
