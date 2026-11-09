"""일과 임시본 — 쓰는 대로 두고, 떠날 때 · 일지 만들 때 근거로 올린다 (ADR-082 · api-spec §10-1).

**임시본은 일과 기록이 아니다.** 일과 기록(`routine_records`)은 일지의 근거(사실 층)다.
올리는 일은 화면이 `promote` 를 실어 보낼 때만 한다 — 하루치를 한 트랜잭션으로 바꾼다.
그래서 줄 몇 개만 올라가고 나머지가 실패하는 일이 없다.

정리 작업(`prune_drafts`)은 **올라간 뒤 30일 지난** 임시본만 지운다. 올라가지 않은 임시본은
교사가 쓴 글이 거기에만 있어 지우지 않는다.
"""

import datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.auth.models import User
from app.features.documents.stale import SourceImpact, source_changed
from app.features.routines.models import RoutineDraft, RoutineRecord
from app.features.routines.schemas import DraftRow, DraftSave

KEEP_AFTER_PROMOTE = datetime.timedelta(days=30)


def fact_key(record: RoutineRecord) -> tuple:
    """일지 사본(`fact_text`)에 들어가는 칸. 이 중 하나가 바뀌어야 근거가 바뀐 것이다."""
    return (record.date, record.start_time, record.end_time, record.name, record.execution)


def mark_if_changed(
    session: Session, record: RoutineRecord, before: tuple, center_id: int
) -> SourceImpact:
    """고친 뒤 사실 칸이 달라졌으면 그 기록을 쓴 일지를 `stale` 로 바꾼다.

    계획 · 순서만 바뀌었으면 그대로다.
    """
    after = fact_key(record)
    if before == after:
        return SourceImpact()
    return source_changed(
        session,
        "routine",
        record.id,
        record.fact_text(),
        record.date,
        center_id=center_id,
        # 사실 사본에는 분까지만 남는다. 초만 고쳐도 시간 변경은 놓치지 않는다.
        force=before[1:3] != after[1:3],
    )


def _merge(a: SourceImpact, b: SourceImpact) -> SourceImpact:
    return SourceImpact(
        tuple(sorted({*a.affected_document_ids, *b.affected_document_ids})),
        tuple(sorted({*a.newly_stale_document_ids, *b.newly_stale_document_ids})),
    )


def _error(code: int, name: str, message: str, fields: list[str]) -> HTTPException:
    return HTTPException(code, detail={"code": name, "message": message, "fields": fields})


def filled(row: DraftRow) -> bool:
    """올릴 줄인가. 깔아 두기만 한 줄과 통째로 빈 줄은 올리지 않는다 (화면 `filled` 와 같다)."""
    return (row.touched or row.id is not None) and bool(
        row.start or row.end or row.name or row.plan.strip() or row.execution.strip()
    )


def _problems(rows: list[DraftRow]) -> list[str]:
    fields = []
    for index, row in enumerate(rows):
        if not filled(row):
            continue
        if not row.name:
            fields.append(f"rows.{index}.name")
        elif row.start and row.end and row.start >= row.end:
            fields.append(f"rows.{index}.end")
    return fields


def find_draft(session: Session, class_id: int, day: datetime.date) -> RoutineDraft | None:
    return session.scalar(
        select(RoutineDraft).where(RoutineDraft.class_id == class_id, RoutineDraft.date == day)
    )


def save_draft(
    session: Session, user: User, body: DraftSave
) -> tuple[RoutineDraft, SourceImpact | None]:
    """하루치 임시본을 판 번호를 맞춰 보고 저장한다. `promote` 면 같은 트랜잭션에서 근거로 올린다.

    부르는 쪽이 반 권한을 먼저 본다. 커밋도 부르는 쪽이 한다.
    """
    if body.promote and (fields := _problems(body.rows)):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_FAILED",
            "일과 이름이 비었거나 끝나는 시간이 시작보다 빠른 줄이 있습니다.",
            fields,
        )
    draft = session.scalar(
        select(RoutineDraft)
        .where(RoutineDraft.class_id == body.class_id, RoutineDraft.date == body.date)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    current = draft.revision if draft else 0
    if current != body.expected_revision:
        raise _stale()
    if draft is None:
        draft = RoutineDraft(class_id=body.class_id, date=body.date, revision=0, rows=[])
        session.add(draft)
        try:
            session.flush()
        except IntegrityError:
            # 처음 저장이 두 기기에서 동시에 왔다. 뒤에 온 쪽은 먼저 저장된 판을 모른다.
            session.rollback()
            raise _stale() from None
    rows, removed = list(body.rows), list(body.removed)
    impact = None
    if body.promote:
        impact = _promote(session, user, body, rows, removed)
        removed = []
    draft.revision = current + 1
    draft.rows = [row.model_dump(mode="json") for row in rows]
    draft.removed = removed
    draft.promoted = body.promote
    if body.promote:
        draft.promoted_at = datetime.datetime.now(datetime.UTC)
    session.flush()
    return draft, impact


def _stale() -> HTTPException:
    return _error(
        status.HTTP_409_CONFLICT,
        "STALE_WRITE",
        "다른 화면에서 먼저 고쳤습니다. 다시 불러와 주세요.",
        ["expected_revision"],
    )


def _keep_seconds(saved: datetime.time | None, sent: datetime.time | None):
    """화면은 분까지만 다룬다. 분이 같으면 서버에 있던 초를 그대로 둔다(지난 데이터 09:16:25)."""
    if saved and sent and saved.replace(second=0, microsecond=0) == sent:
        return saved
    return sent


def _promote(
    session: Session, user: User, body: DraftSave, rows: list[DraftRow], removed: list[int]
) -> SourceImpact:
    """임시본을 그날 일과 기록으로 만든다. 새 줄은 만들고, 고친 줄은 바꾸고, 지운 줄은 지운다.

    **이 반 · 이 날의 기록만 건드린다.** 임시본에 적힌 번호가 다른 날 · 다른 반 기록이면
    그 줄은 새로 만든다 — 남의 기록을 바꾸지 않는다. 순서(`position`)는 화면 순서다.
    """
    ids = [row.id for row in rows if row.id is not None] + removed
    records = {
        r.id: r
        for r in session.scalars(
            select(RoutineRecord)
            .where(
                RoutineRecord.id.in_(ids),
                RoutineRecord.class_id == body.class_id,
                RoutineRecord.date == body.date,
            )
            .with_for_update()
        )
    }
    impact = SourceImpact()
    center = user.center_id
    for record_id in removed:
        record = records.pop(record_id, None)
        if record is None:
            continue
        impact = _merge(
            impact,
            source_changed(session, "routine", record_id, None, None, center_id=center),
        )
        session.delete(record)

    position = 0
    for index, row in enumerate(rows):
        if not filled(row):
            continue
        record = records.get(row.id) if row.id is not None else None
        if record is None:
            record = RoutineRecord(class_id=body.class_id, date=body.date)
            session.add(record)
            before = None
        else:
            before = fact_key(record)
        record.position = position
        record.start_time = _keep_seconds(record.start_time, row.start)
        record.end_time = _keep_seconds(record.end_time, row.end)
        record.name, record.plan, record.execution = row.name, row.plan, row.execution
        session.flush()
        if before is not None:
            impact = _merge(impact, mark_if_changed(session, record, before, center))
        rows[index] = row.model_copy(update={"id": record.id})
        position += 1
    return impact


def prune_drafts(session: Session, now: datetime.datetime) -> int:
    """올라간 뒤 30일 지난 임시본을 지운다. 지운 수를 돌려준다. 커밋은 부르는 쪽이 한다."""
    result = session.execute(
        delete(RoutineDraft).where(
            RoutineDraft.promoted.is_(True),
            RoutineDraft.promoted_at < now - KEEP_AFTER_PROMOTE,
        )
    )
    return result.rowcount
