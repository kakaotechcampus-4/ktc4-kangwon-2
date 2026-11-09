"""일과 기록 API. 계약은 docs/api-spec.md §10-1 이다 (ADR-025).

**생성 엔드포인트가 없다.** 활동실행은 있었던 일이라 AI 가 쓰면 위조다 (CLAUDE.md 문서 5분류).
교사가 적은 그대로 저장하고 꺼낸다.

`PUT` · `DELETE` 는 이 기록을 근거로 쓴 §11 일일 보육일지를 `stale` 로 바꾼다. 판정은 문서
쪽이 갖고 있다 — `stale` 칸의 주인이 documents 다 (features/documents/stale.py).

하루치 조회에는 그날 날씨가 붙고, 교사가 그 날씨를 고를 수 있다 (`weather.py`, ADR-089).
"""

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import get_session
from app.features.auth.models import User
from app.features.centers.models import Class
from app.features.documents.stale import SourceImpact, source_changed
from app.features.routines.drafts import (
    fact_key,
    find_draft,
    mark_if_changed,
    paper_marks,
    save_draft,
)
from app.features.routines.models import (
    ClassRoutineTemplate,
    RoutineDraft,
    RoutineRecord,
    RoutineWeather,
)
from app.features.routines.presets import day_preset
from app.features.routines.schemas import (
    DayWeatherResponse,
    DraftResponse,
    DraftSave,
    DraftSaveResponse,
    RoutineCreate,
    RoutineDeleteResponse,
    RoutineListResponse,
    RoutineMutationResponse,
    RoutineResponse,
    RoutineReviewImpact,
    RoutineUpdate,
    TemplateResponse,
    TemplateSave,
    WeatherChoice,
)
from app.features.routines.weather import DayWeather, day_weather
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import own_class_clause, require_own_class

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
        reflected=record.reflected,
        activities=record.activities,
        created_at=record.created_at,
    )


def _own(session: Session, user: User, record_id: int, *, lock: bool = False):
    """남의 원 기록도 없는 기록과 같은 404 다 (shared/auth/ownership.py 와 같은 이유)."""
    query = _visible(user).where(RoutineRecord.id == record_id)
    if lock:
        query = query.with_for_update(of=RoutineRecord).execution_options(populate_existing=True)
    row = session.execute(query).first()
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
        require_own_class(session, user, class_id, read_only=True)
        query = query.where(RoutineRecord.class_id == class_id)
    else:
        # 반을 안 짚은 목록은 내 반만 — 승인받은 반은 반을 짚어야 보인다.
        query = query.where(own_class_clause(user))
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
    items = [_response(row) for row in session.execute(query)]
    # 보육일지 화면은 반 하나 · 하루 하나로 부른다. 그때만 그날 날씨 · 임시본을 붙인다
    # (ADR-081 · ADR-084).
    one_day = class_id is not None and date_from is not None and date_from == date_to
    if not one_day:
        return RoutineListResponse(items=items)
    draft = find_draft(session, class_id, date_from)
    return RoutineListResponse(
        items=items,
        weather=_weather(day_weather(session, class_id, date_from)),
        draft=_draft(draft) if draft else None,
        preset=None if items else day_preset(session, class_id, date_from),
    )


def _draft(draft: RoutineDraft) -> DraftResponse:
    return DraftResponse.model_validate(draft, from_attributes=True)


@router.get("/template", response_model=TemplateResponse | None)
def get_template(class_id: int, session: DbSession, user: CurrentUser) -> TemplateResponse | None:
    """반 기본 일과표. 없으면 null (ADR-085)."""
    require_own_class(session, user, class_id, read_only=True)
    template = session.scalar(
        select(ClassRoutineTemplate).where(ClassRoutineTemplate.class_id == class_id)
    )
    return TemplateResponse.model_validate(template, from_attributes=True) if template else None


@router.put("/template", response_model=TemplateResponse)
def put_template(body: TemplateSave, session: DbSession, user: CurrentUser) -> TemplateResponse:
    """반 기본 일과표를 통째로 바꾼다. 이미 적은 날은 그대로다 — 새 날을 깔 때만 쓴다."""
    require_own_class(session, user, body.class_id)
    rows = [row.model_dump(mode="json", exclude_none=True) for row in body.rows]
    session.execute(
        insert(ClassRoutineTemplate)
        .values(class_id=body.class_id, rows=rows)
        .on_conflict_do_update(
            index_elements=["class_id"], set_={"rows": rows, "updated_at": func.now()}
        )
    )
    session.commit()
    return get_template(body.class_id, session, user)


@router.put("/draft", response_model=DraftSaveResponse)
def put_draft(body: DraftSave, session: DbSession, user: CurrentUser) -> DraftSaveResponse:
    """하루치 임시본을 둔다. `promote` 면 같은 요청에서 그날 일과 기록으로 올린다 (ADR-084).

    `/{record_id}` 보다 먼저 둔다 — 뒤에 두면 「draft」를 기록 id 로 읽고 422 를 낸다.
    """
    require_own_class(session, user, body.class_id)
    draft, impact = save_draft(session, user, body)
    session.commit()
    if impact is None:
        return DraftSaveResponse(draft=_draft(draft))
    day = (
        _visible(user)
        .where(RoutineRecord.class_id == body.class_id, RoutineRecord.date == body.date)
        .order_by(
            RoutineRecord.position,
            RoutineRecord.start_time.asc().nulls_last(),
            RoutineRecord.id,
        )
    )
    return DraftSaveResponse(
        draft=_draft(draft),
        items=[_response(row) for row in session.execute(day)],
        review_impact=_impact_response(impact),
    )


def _weather(value: DayWeather) -> DayWeatherResponse:
    return DayWeatherResponse(**asdict(value))


@router.put("/weather", response_model=DayWeatherResponse)
def choose_weather(
    body: WeatherChoice, session: DbSession, user: CurrentUser
) -> DayWeatherResponse:
    """교사가 그날 날씨를 고른다. 자동 값과 따로 남기고, 있으면 그것이 이긴다 (ADR-089).

    `/{record_id}` 보다 먼저 둔다 — 뒤에 두면 「weather」를 기록 id 로 읽고 422 를 낸다.
    """
    require_own_class(session, user, body.class_id)
    where = (RoutineWeather.class_id == body.class_id, RoutineWeather.date == body.date)
    if body.sky is None:
        session.execute(delete(RoutineWeather).where(*where))
    else:
        session.execute(
            insert(RoutineWeather)
            .values(class_id=body.class_id, date=body.date, sky=body.sky)
            .on_conflict_do_update(
                index_elements=["class_id", "date"],
                set_={"sky": body.sky, "updated_at": func.now()},
            )
        )
    session.commit()
    return _weather(day_weather(session, body.class_id, body.date))


def _impact_response(impact: SourceImpact) -> RoutineReviewImpact:
    return RoutineReviewImpact(
        affected_document_ids=list(impact.affected_document_ids),
        newly_stale_document_ids=list(impact.newly_stale_document_ids),
    )


@router.put("/{record_id}", response_model=RoutineMutationResponse | RoutineResponse)
def update_routine(
    record_id: int,
    body: RoutineUpdate,
    session: DbSession,
    user: CurrentUser,
    include_impact: bool = False,
) -> RoutineResponse | RoutineMutationResponse:
    record = _own(session, user, record_id, lock=True)[0]
    require_own_class(session, user, record.class_id)
    # 자리만 고친 요청은 근거 변경이 아니다. 계획은 확정 때 박은 사본과 비교한다(ADR-086).
    before, before_marks = fact_key(record), paper_marks(record)
    _apply(record, body)
    impact = mark_if_changed(session, record, before, user.center_id, before_marks)
    session.commit()
    result = _response(_own(session, user, record_id))
    if include_impact:
        return RoutineMutationResponse(
            **result.model_dump(), review_impact=_impact_response(impact)
        )
    return result


@router.delete(
    "/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={200: {"model": RoutineDeleteResponse}},
)
def delete_routine(
    record_id: int,
    session: DbSession,
    user: CurrentUser,
    include_impact: bool = False,
) -> Response:
    record = _own(session, user, record_id, lock=True)[0]
    require_own_class(session, user, record.class_id)
    impact = source_changed(session, "routine", record_id, None, None, center_id=user.center_id)
    session.delete(record)
    session.commit()
    if include_impact:
        result = RoutineDeleteResponse(review_impact=_impact_response(impact))
        return JSONResponse(result.model_dump(), status_code=status.HTTP_200_OK)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
