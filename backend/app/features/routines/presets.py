"""새 날에 깔 줄 — 반 기본 일과표 → 지난주 같은 요일 → 가장 최근 기록일 (ADR-084).

지난 하루를 그대로 이어받으면 그날 한 번뿐인 일(소방훈련 · 견학)까지 다음 날에 깔린다.
그래서 반이 한 번 정해 둔 기본 일과표가 먼저다. 순서 · 시간 · 이름만 깐다 — 적은 글은 옮기지 않는다.
"""

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.routines.models import ClassRoutineTemplate, RoutineRecord
from app.features.routines.schemas import DayPreset, PresetRow, TemplateRow

_LATE = datetime.time(23, 59, 59)


def _by_time(rows: list[PresetRow]) -> list[PresetRow]:
    # 시간 없는 줄은 뒤로. 같은 시간이면 표에 적힌 순서(sorted 는 안정 정렬).
    return sorted(rows, key=lambda r: r.start or _LATE)


def day_preset(session: Session, class_id: int, day: datetime.date) -> DayPreset | None:
    template = session.scalar(
        select(ClassRoutineTemplate.rows).where(ClassRoutineTemplate.class_id == class_id)
    )
    if template:
        rows = [TemplateRow.model_validate(r) for r in template]
        picked = [r for r in rows if r.weekday is None or r.weekday == day.weekday()]
        return DayPreset(
            source="template",
            from_date=None,
            rows=_by_time([PresetRow(name=r.name, start=r.start, end=r.end) for r in picked]),
        )
    last_week = day - datetime.timedelta(days=7)
    if _has_rows(session, class_id, last_week):
        return _copy(session, class_id, last_week, "last_week")
    recent = session.scalar(
        select(RoutineRecord.date)
        .where(RoutineRecord.class_id == class_id, RoutineRecord.date < day)
        .order_by(RoutineRecord.date.desc())
        .limit(1)
    )
    return _copy(session, class_id, recent, "recent") if recent else None


def _has_rows(session: Session, class_id: int, day: datetime.date) -> bool:
    return (
        session.scalar(
            select(RoutineRecord.id)
            .where(RoutineRecord.class_id == class_id, RoutineRecord.date == day)
            .limit(1)
        )
        is not None
    )


def _copy(session: Session, class_id: int, day: datetime.date, source) -> DayPreset:
    records = session.scalars(
        select(RoutineRecord)
        .where(RoutineRecord.class_id == class_id, RoutineRecord.date == day)
        .order_by(
            RoutineRecord.position, RoutineRecord.start_time.asc().nulls_last(), RoutineRecord.id
        )
    )
    return DayPreset(
        source=source,
        from_date=day,
        rows=[PresetRow(name=r.name, start=r.start_time, end=r.end_time) for r in records],
    )
