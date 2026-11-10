"""확정한 종이는 확정 뒤 바뀌지 않는다 — 확정할 때 종이에만 쓰는 값을 문서 쪽에 박는다.

날씨(ADR-089 결정 9)와 일과 줄 종이 한 줄 전부 — 순서 · 이름 · 시간 · 활동계획 · 활동실행 ·
「반영」 · 맞다고 한 활동(ADR-086 결정 5 · 7), 그리고 원이 고른 「반영」 표기 글자다.
확정본 종이는 일과 기록 원본을 읽지 않는다.
확정 · 재확정 때 박고, 확정을 풀면 푼다. 박은 뒤 일과 기록의 사실 · 활동계획 · 반영 · 활동이
바뀌면 그 확정본은 `stale` 이다(`routines/drafts.py`).
"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.features.centers.models import Center, Class
from app.features.documents.models import Document, DocumentSource
from app.features.routines.models import RoutineRecord
from app.features.routines.weather import stamp_confirmed_weather


def stamp_confirmed(session: Session, doc: Document) -> None:
    """확정 · 재확정 때 부른다. 일일 · 주간만 박을 것이 있다."""
    if doc.kind not in ("dailyLog", "weeklyLog"):
        return
    stamp_confirmed_weather(session, doc)
    if doc.kind == "dailyLog":
        # 「반영」 표기도 종이 글자다. 원 설정을 나중에 바꿔도 확정본 종이는 그대로다(결정 7).
        doc.reflect_mark = current_reflect_mark(session, doc.class_id)
    rows = session.scalars(select(DocumentSource).where(DocumentSource.document_id == doc.id))
    copies = list(rows)
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
            copy.position, copy.name, copy.plan = record.position, record.name, record.plan
            copy.start_time, copy.end_time = record.start_time, record.end_time
            copy.execution = record.execution
        elif copy.source_kind == "document":
            copy.activities = _daily_activities(session, copy.source_id)


def current_reflect_mark(session: Session, class_id: int) -> str | None:
    """그 반 원이 지금 쓰는 「반영」 표기. 초안 종이 · 박기 전에 확정한 옛 문서가 쓴다."""
    return session.scalar(
        select(Center.reflect_mark).where(Center.id == Class.center_id).where(Class.id == class_id)
    )


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
    doc.reflect_mark = None
    session.execute(
        update(DocumentSource)
        .where(DocumentSource.document_id == doc.id)
        .values(
            reflected=None,
            activities=None,
            position=None,
            name=None,
            start_time=None,
            end_time=None,
            plan=None,
            execution=None,
        )
    )
