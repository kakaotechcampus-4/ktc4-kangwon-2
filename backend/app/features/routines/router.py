"""일과 기록 API. 계약은 docs/api-spec.md §10-1 이다 (ADR-025).

**생성 엔드포인트가 없다.** 활동실행은 있었던 일이라 AI 가 쓰면 위조다 (CLAUDE.md 문서 5분류).
교사가 적은 그대로 저장하고 꺼낸다.

`PUT` · `DELETE` 는 이 기록을 근거로 쓴 §11 일일 보육일지를 `stale` 로 바꾼다. 판정은 문서
쪽이 갖고 있다 — `stale` 칸의 주인이 documents 다 (features/documents/stale.py).
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.auth.models import User
from app.features.centers.models import Class
from app.features.documents.stale import source_changed
from app.features.routines.models import RoutineRecord
from app.features.routines.schemas import (
    RoutineCreate,
    RoutineListResponse,
    RoutineResponse,
    RoutineUpdate,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class

router = APIRouter(prefix="/routines", tags=["routines"])

DbSession = Annotated[Session, Depends(get_session)]

_NOT_FOUND = HTTPException(
    status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "일과 기록을 찾을 수 없습니다.", "fields": ["id"]},
)


def _visible(user: User) -> Select:
    """이 교사의 원에 속한 기록 + 반 이름. JOIN 한 번이라 N+1 이 없다."""
    return (
        select(RoutineRecord, Class.name)
        .join(Class, RoutineRecord.class_id == Class.id)
        .where(Class.center_id == user.center_id)
    )


def _response(row) -> RoutineResponse:
    record, class_name = row
    return RoutineResponse(
        id=record.id,
        class_id=record.class_id,
        class_name=class_name,
        date=record.date,
        position=record.position,
        start=record.start_time,
        end=record.end_time,
        name=record.name,
        plan=record.plan,
        execution=record.execution,
        created_at=record.created_at,
    )


def _own(session: Session, user: User, record_id: int):
    """남의 원 기록도 없는 기록과 같은 404 다 (shared/auth/ownership.py 와 같은 이유)."""
    row = session.execute(_visible(user).where(RoutineRecord.id == record_id)).first()
    if row is None:
        raise _NOT_FOUND
    return row


def _apply(record: RoutineRecord, body: RoutineUpdate) -> None:
    record.date = body.date
    record.position = body.position
    record.start_time, record.end_time = body.start, body.end
    record.name, record.plan, record.execution = body.name, body.plan, body.execution


@router.post("", response_model=RoutineResponse, status_code=status.HTTP_201_CREATED)
def create_routine(body: RoutineCreate, session: DbSession, user: CurrentUser) -> RoutineResponse:
    require_own_class(session, user, body.class_id)
    record = RoutineRecord(class_id=body.class_id)
    _apply(record, body)
    session.add(record)
    session.commit()
    return _response(_own(session, user, record.id))


@router.get("", response_model=RoutineListResponse)
def list_routines(
    session: DbSession,
    user: CurrentUser,
    class_id: int | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> RoutineListResponse:
    """셋 다 선택이다. 없으면 이 교사의 원 전체다.

    **정렬은 날짜 오름차순, 하루 안에서는 `position` · 시작 시간 · id 순이다.** 종이의 행 순서다.
    """
    query = _visible(user)
    if class_id is not None:
        query = query.where(RoutineRecord.class_id == class_id)
    if date_from is not None:
        query = query.where(RoutineRecord.date >= date_from)
    if date_to is not None:
        query = query.where(RoutineRecord.date <= date_to)
    query = query.order_by(
        RoutineRecord.date,
        RoutineRecord.position,
        RoutineRecord.start_time.asc().nulls_last(),
        RoutineRecord.id,
    )
    return RoutineListResponse(items=[_response(row) for row in session.execute(query)])


@router.put("/{record_id}", response_model=RoutineResponse)
def update_routine(
    record_id: int, body: RoutineUpdate, session: DbSession, user: CurrentUser
) -> RoutineResponse:
    record = _own(session, user, record_id)[0]
    _apply(record, body)
    source_changed(session, "routine", record_id, record.fact_text(), record.date)
    session.commit()
    return _response(_own(session, user, record_id))


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routine(record_id: int, session: DbSession, user: CurrentUser) -> None:
    record = _own(session, user, record_id)[0]
    source_changed(session, "routine", record_id, None, None)
    session.delete(record)
    session.commit()
