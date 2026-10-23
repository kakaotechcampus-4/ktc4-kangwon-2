"""다른 기능의 문서 읽기 창구(structure.md) — 확정 문서만, 원 단위 확인(ADR-017)."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.centers.models import Class
from app.features.documents.models import Document


@dataclass(frozen=True)
class ConfirmedDocument:
    id: int
    class_id: int
    child_id: int | None
    end_date: date


def _list_confirmed(session, center_id, kind, id_column, ids, start, end):
    if not ids:
        return []
    rows = session.execute(
        select(Document.id, Document.class_id, Document.child_id, Document.end_date)
        .join(Class, Document.class_id == Class.id)
        .where(
            Class.center_id == center_id,
            Document.status == "CONFIRMED",
            Document.kind == kind,
            Document.end_date.between(start, end),
            id_column.in_(ids),
        )
        .order_by(Document.end_date, Document.id)
    )
    return [ConfirmedDocument(*row) for row in rows]


def list_confirmed_by_class(
    session: Session,
    center_id: int,
    *,
    kind: str,
    class_ids: Collection[int],
    start: date,
    end: date,
) -> list[ConfirmedDocument]:
    return _list_confirmed(session, center_id, kind, Document.class_id, class_ids, start, end)


def list_confirmed_by_child(
    session: Session,
    center_id: int,
    *,
    kind: str,
    child_ids: Collection[int],
    start: date,
    end: date,
) -> list[ConfirmedDocument]:
    return _list_confirmed(session, center_id, kind, Document.child_id, child_ids, start, end)
