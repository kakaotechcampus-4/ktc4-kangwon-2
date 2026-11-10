"""같은 원 다른 반 열람 요청 · 승인과 반 요약. 계약은 docs/api-spec.md §2-2 다 (ADR-059)."""

import calendar
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods

from app.db import get_session
from app.features.auth.models import User
from app.features.centers.models import Class, ClassAccessRequest
from app.features.class_access.schemas import (
    AccessRequestOut,
    AccessRequestPatch,
    ArchiveItem,
    ArchiveSummary,
    ReceivedList,
    ReceivedRequest,
)
from app.features.documents.models import Document
from app.features.notifications.service import NotificationKind, mark_request_read, notify
from app.features.plans.models import Plan
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import _not_found

router = APIRouter(tags=["class-access"])

DbSession = Annotated[Session, Depends(get_session)]

_ALREADY_EXISTS = HTTPException(
    status.HTTP_409_CONFLICT,
    detail={
        "code": "ALREADY_EXISTS",
        "message": "이미 볼 수 있거나 승인을 기다리는 반입니다.",
        "fields": ["class_id"],
    },
)
_STALE_WRITE = HTTPException(
    status.HTTP_409_CONFLICT,
    detail={
        "code": "STALE_WRITE",
        "message": "그 사이 다른 화면에서 요청이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.",
        "fields": ["status"],
    },
)
# 지금 상태 -> 주인이 바꿀 수 있는 상태. 거절 · 취소된 줄은 요청하는 쪽이 다시 PENDING 으로 돌린다.
_TRANSITIONS = {"PENDING": {"APPROVED", "REJECTED"}, "APPROVED": {"REVOKED"}}
# 주인의 결정 -> 요청자에게 가는 알림 (ADR-097)
_DECISION_KIND: dict[str, NotificationKind] = {
    "APPROVED": "ACCESS_APPROVED",
    "REJECTED": "ACCESS_REJECTED",
    "REVOKED": "ACCESS_REVOKED",
}
# UNIQUE(class_id, requester_id) 의 제약 이름. app/db.py 의 NAMING_CONVENTION 이 정했다.
_REQUEST_UNIQUE = "uq_class_access_requests_class_id_requester_id"


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _plan_period(kind: str, school_year: int, target_month: str | None, week_id: str | None):
    """계획안 한 줄의 (start, end). 못 읽는 행은 None 이라 요약에서 빠진다."""
    if kind == "annual":
        return date(school_year, 3, 1), _month_end(school_year + 1, 2)
    if target_month is None:
        return None
    year, month = int(target_month[:4]), int(target_month[5:7])
    if kind == "monthly":
        return date(year, month, 1), _month_end(year, month)
    # 주간: 월간 칸이 쓰는 주 규칙(canonical_week_periods)에서 같은 week_id 를 찾는다.
    for period in canonical_week_periods(YearMonth(year, month)):
        if period.week_id.value == week_id:
            return period.start_date, period.end_date
    return None


@router.get("/classes/{class_id}/archive-summary", response_model=ArchiveSummary)
def archive_summary(class_id: int, session: DbSession, user: CurrentUser) -> ArchiveSummary:
    """반에 어떤 자료가 몇 건 있는지만 준다. 열람 권한이 없어도 같은 원이면 본다.

    승인을 청하기 전에 「볼 만한 자료가 있나」를 가늠하는 용도라, 제목 · 아이 이름 · id 는 없다.
    """
    classroom = session.get(Class, class_id)
    if classroom is None or user.center_id is None or classroom.center_id != user.center_id:
        raise _not_found("반", "class_id")
    items = []
    plans = session.execute(
        select(Plan.kind, Plan.school_year, Plan.target_month, Plan.week_id, Plan.status).where(
            Plan.center_id == user.center_id, Plan.classroom_ref == str(class_id)
        )
    )
    for kind, school_year, target_month, week_id, plan_status in plans:
        period = _plan_period(kind, school_year, target_month, week_id)
        if period is not None:
            items.append(ArchiveItem(kind=kind, start=period[0], end=period[1], status=plan_status))
    documents = session.execute(
        select(Document.kind, Document.start_date, Document.end_date, Document.status).where(
            Document.class_id == class_id
        )
    )
    for kind, start, end, document_status in documents:
        items.append(ArchiveItem(kind=kind, start=start, end=end, status=document_status))
    items.sort(key=lambda item: item.start, reverse=True)
    return ArchiveSummary(items=items)


@router.post(
    "/classes/{class_id}/access-requests",
    response_model=AccessRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def request_access(class_id: int, session: DbSession, user: CurrentUser) -> ClassAccessRequest:
    classroom = session.get(Class, class_id)
    if classroom is None or user.center_id is None or classroom.center_id != user.center_id:
        raise _not_found("반", "class_id")
    if classroom.teacher_id is None or classroom.teacher_id == user.id:
        raise _ALREADY_EXISTS  # 이미 읽고 쓸 수 있는 반이다
    # 잠그고 읽는다 — 거절 뒤 재요청 둘이 동시에 와도 하나만 PENDING 으로 돌려 알림이 하나만 간다.
    row = session.scalar(
        select(ClassAccessRequest)
        .where(ClassAccessRequest.class_id == class_id, ClassAccessRequest.requester_id == user.id)
        .with_for_update()
    )
    if row is None:
        row = ClassAccessRequest(class_id=class_id, requester_id=user.id, status="PENDING")
        session.add(row)
    elif row.status in ("PENDING", "APPROVED"):
        raise _ALREADY_EXISTS
    else:
        # 거절 · 취소 뒤 다시 청한다 — UNIQUE 라 새 줄이 아니라 같은 줄을 되돌린다.
        # updated_at 은 모델의 onupdate 가 갱신한다.
        row.status = "PENDING"
    try:
        # 새 줄은 flush 해야 id 가 생긴다 — 알림이 그 id 를 가리킨다. 두 요청이 동시에 처음 넣은
        # UNIQUE 위반도 여기서 터지므로 flush 도 try 안이다.
        session.flush()
        notify(session, user_id=classroom.teacher_id, kind="ACCESS_REQUESTED", request_id=row.id)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        # UNIQUE 만 「이미 보냄」이다. 알림의 외래키 · CHECK 위반까지 409 로 덮으면 화면이
        # 그 코드를 조용히 삼켜(ClassAccessPanels) 원인이 묻힌다.
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint != _REQUEST_UNIQUE:
            raise
        raise _ALREADY_EXISTS from error
    session.refresh(row)
    return row


def _received(row: ClassAccessRequest, class_name: str, requester_name: str) -> ReceivedRequest:
    return ReceivedRequest(
        id=row.id,
        class_id=row.class_id,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        class_name=class_name,
        requester_name=requester_name,
    )


def _of_my_classes():
    """내가 주인인 반에 온 요청 + 반 이름 + 요청자 이름. JOIN 한 번이라 N+1 이 없다."""
    return (
        select(ClassAccessRequest, Class.name, User.name)
        .join(Class, Class.id == ClassAccessRequest.class_id)
        .join(User, User.id == ClassAccessRequest.requester_id)
    )


@router.get("/access-requests/received", response_model=ReceivedList)
def received_requests(session: DbSession, user: CurrentUser) -> ReceivedList:
    rows = session.execute(
        _of_my_classes()
        .where(Class.teacher_id == user.id)
        # 처리할 것(PENDING)이 위. False 가 먼저라 `!= 'PENDING'` 으로 정렬한다.
        .order_by(
            ClassAccessRequest.status != "PENDING",
            ClassAccessRequest.updated_at.desc(),
            ClassAccessRequest.id.desc(),
        )
    )
    return ReceivedList(items=[_received(*row) for row in rows])


def _mirror(session: Session, requester_id: int, approver: User, status_value: str) -> None:
    """승인은 서로다 (ADR-068). 요청한 교사의 반을 승인한 교사도 본다 · 취소하면 같이 닫힌다.

    요청을 보낸 것을 「내 반도 보여 줘도 된다」는 동의로 본다 — 요청 화면이 그렇게 알린다.
    승인할 때 요청자에게 있던 반만 연다. 그 뒤에 요청자가 새로 만든 반은 따로 청해야 한다.
    """
    theirs = session.scalars(
        select(Class.id).where(
            Class.center_id == approver.center_id, Class.teacher_id == requester_id
        )
    ).all()
    for class_id in theirs:
        back = session.scalar(
            select(ClassAccessRequest)
            .where(
                ClassAccessRequest.class_id == class_id,
                ClassAccessRequest.requester_id == approver.id,
            )
            .with_for_update()
        )
        if status_value == "APPROVED":
            if back is None:
                session.add(
                    ClassAccessRequest(
                        class_id=class_id, requester_id=approver.id, status="APPROVED"
                    )
                )
            else:
                if back.status == "PENDING":
                    # 맞승인 — 상대가 처리할 요청이 이걸로 닫힌다.
                    # 새로 열리는 줄 · 반대 줄에는 알림을 만들지 않는다.
                    mark_request_read(session, back.id)
                back.status = "APPROVED"
        elif back is not None and back.status == "APPROVED":
            back.status = "REVOKED"


@router.patch("/access-requests/{request_id}", response_model=ReceivedRequest)
def decide_request(
    request_id: int, body: AccessRequestPatch, session: DbSession, user: CurrentUser
) -> ReceivedRequest:
    # 줄을 잠근 채 전환을 본다 — 두 화면이 동시에 승인과 거절을 눌러도 하나만 이긴다.
    found = session.execute(
        _of_my_classes()
        .where(ClassAccessRequest.id == request_id, Class.teacher_id == user.id)
        .with_for_update(of=ClassAccessRequest)
        .execution_options(populate_existing=True)
    ).first()
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "요청을 찾을 수 없습니다.",
                "fields": ["id"],
            },
        )
    row, class_name, requester_name = found
    if body.status not in _TRANSITIONS.get(row.status, ()):
        raise _STALE_WRITE
    row.status = body.status
    if body.status in ("APPROVED", "REVOKED"):
        _mirror(session, row.requester_id, user, body.status)
    notify(
        session,
        user_id=row.requester_id,
        kind=_DECISION_KIND[body.status],
        request_id=row.id,
    )
    if body.status != "REVOKED":
        # 승인 · 거절은 요청이 PENDING 을 떠난 것이다 —
        # 보관함에서 처리해도 종의 「요청이 왔다」가 읽힌 것으로 바뀐다.
        mark_request_read(session, row.id)
    session.commit()
    session.refresh(row)
    return _received(row, class_name, requester_name)
