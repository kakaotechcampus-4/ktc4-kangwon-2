"""놀이 중심 월간계획안 — 조회 · 목록 · 삭제 · 생성 게이트. 계약은 docs/api-spec.md §9-7 이다.

**이 파일에 생성 규칙이 없다.** 본문은 p0-planning 이 만든 `PlayMonthlyPlan` 이고, 여기는 읽어서
응답 모양으로 옮긴다. 오류 · 상수 · 학년도 계산은 기존 월간(`monthly_router`)의 것을 쓴다.

`play` 는 고정 글자 경로라 `monthly_router` 의 `GET /{plan_id}` 보다 먼저 등록한다(main.py).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.planning import InvalidDomainValueError, ItemId, PlanId
from ssuksak.planning.application.play_monthly_lifecycle import (
    AddPlayMonthlyActivity,
    AddPlayMonthlyActivityCommand,
    CopyPlayMonthlyDrillCandidate,
    CopyPlayMonthlyDrillCandidateCommand,
    EditPlayMonthlyCell,
    EditPlayMonthlyCellCommand,
    EditPlayMonthlyContentIds,
    EditPlayMonthlyContentIdsCommand,
    PlacePlayMonthlySafety,
    PlacePlayMonthlySafetyCommand,
    PlayMonthlyLifecycleError,
    RemovePlayMonthlyActivity,
    RemovePlayMonthlyActivityCommand,
    play_monthly_notices,
)
from ssuksak.planning.domain.errors import InvalidStateTransitionError
from ssuksak.planning.domain.play_monthly_plan import (
    PlayActivity,
    PlayMonthlyCell,
    PlayMonthlyPlan,
)
from ssuksak.planning.domain.play_project_plan import PLAY_PROJECT_FORMAT  # 공개 창구에 없다
from ssuksak.planning.domain.week_period import WeekId

from app.db import get_session
from app.features.plans import play_monthly_schemas as s
from app.features.plans import play_project
from app.features.plans.models import Plan
from app.features.plans.monthly_router import (
    _ALREADY_CONFIRMED,
    _ALREADY_EXISTS,
    _CELL_NOT_FOUND,
    _NOT_DELETABLE,
    _NOT_FOUND,
    _STALE_WRITE,
    _actor,
    _error,
    _existing,
    _gate,
    _is_play_monthly,
    _target_month,
)
from app.features.plans.monthly_schemas import RevisionIn
from app.features.plans.play_project import format_of
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import EvidenceOut, GenerationOut
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/plans/monthly/play", tags=["plans"])

DbSession = Annotated[Session, Depends(get_session)]

_LEGACY_MONTHLY = _error(
    409, "GATE_BLOCKED", "기존 월간계획안은 /api/plans/monthly 경로로 다룹니다.", []
)
_UNAVAILABLE = _error(
    503,
    "DEPENDENCY_UNAVAILABLE",
    "지금은 이 반의 놀이 중심 월간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요.",
    [],
)


@router.post("", response_model=s.PlayMonthlyPlanOut, status_code=status.HTTP_201_CREATED)
def create_play_monthly_plan(body: s.CreatePlayMonthlyPlan, session: DbSession, user: CurrentUser):
    """게이트까지만 한다. 생활 문장 자료 · AI 호출부가 없어 Core 생성을 안 부르고 503 이다."""
    klass = require_own_class(session, user, body.class_id)
    month = _target_month(klass.school_year, body.month)
    if _existing(session, user.center_id, klass.id, month) is not None:
        raise _ALREADY_EXISTS
    parent_row = session.scalar(
        select(Plan).where(
            Plan.center_id == user.center_id,
            Plan.kind == "annual",
            Plan.classroom_ref == str(klass.id),
        )
    )
    if parent_row is None:
        raise _gate("연간계획안을 먼저 만들어 확정해주세요.")
    # 월별 주제형 본문은 읽기 전에 막는다. 확정 여부와 관계없다.
    if format_of(parent_row) != PLAY_PROJECT_FORMAT:
        raise _gate("월별 주제형 연간계획안으로는 놀이 중심 월간계획안을 만들 수 없습니다.")
    if parent_row.status != "CONFIRMED":
        raise _gate("연간계획안을 먼저 확정해주세요.")
    # 생성이 열릴 때: 「강조가 그 구간에서 고른 놀이가 아니면 422」는 Core 가 검사한다.
    raise _UNAVAILABLE


@router.get("", response_model=s.PlayMonthlyListOut)
def list_play_monthly_plans(session: DbSession, user: CurrentUser, class_id: int | None = None):
    query = select(Plan).where(Plan.center_id == user.center_id, Plan.kind == "monthly")
    if class_id is not None:
        require_own_class(session, user, class_id)
        query = query.where(Plan.classroom_ref == str(class_id))
    rows = session.scalars(query.order_by(Plan.target_month, Plan.id)).all()
    return s.PlayMonthlyListOut(
        items=[
            s.PlayMonthlySummary(
                id=row.id,
                class_id=int(row.classroom_ref),
                school_year=row.school_year,
                month=int(row.target_month[5:]),
                target_month=row.target_month,
                status=row.status,
                revision=row.revision,
                created_at=row.created_at,
                confirmed_at=row.confirmed_at,
            )
            for row in rows
            if _is_play_monthly(row)
        ]
    )


@router.get("/{plan_id}", response_model=s.PlayMonthlyPlanOut)
def get_play_monthly_plan(plan_id: int, session: DbSession, user: CurrentUser):
    row = _own_row(session, user, plan_id)
    return _out(session, user, row, _repo(session, user).get(PlanId(row.plan_ref)))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_play_monthly_plan(plan_id: int, session: DbSession, user: CurrentUser) -> Response:
    """확정 전만 지운다. revision 을 받지 않는다 — 기존 월간 삭제와 같다."""
    row = _own_row(session, user, plan_id)
    if row.status == "CONFIRMED":
        raise _NOT_DELETABLE
    # 상태 확인과 삭제를 한 SQL 로 한다 — 읽은 뒤 확정되면 확정본이 사라지지 않게 DRAFT 조건을 건다.
    deleted = session.execute(
        delete(Plan).where(
            Plan.id == row.id,
            Plan.center_id == user.center_id,
            Plan.kind == "monthly",
            Plan.status == "DRAFT",
        )
    ).rowcount
    if not deleted:  # 그 사이 바뀌었다 — 없어졌으면 404, 확정됐으면 409
        _own_row(session, user, plan_id)
        raise _NOT_DELETABLE
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 변경 (§9-7) ────────────────────────────────────────────────────────────

_REFERENCE_UNAVAILABLE = _error(
    503,
    "DEPENDENCY_UNAVAILABLE",
    "지금은 누리과정 연결을 바꿀 수 없습니다. 관리자에게 문의해 주세요.",
    [],
)


def _invalid(*fields: str):
    return _error(422, "VALIDATION_FAILED", "입력값을 확인해주세요.", list(fields))


# Core 오류 → 계약 코드. 여기 없는 코드(invalid_item_id · opaque_actor_required)는 서버 버그라 500.
_LIFECYCLE_ERRORS = {
    "play_monthly_plan_not_found": _NOT_FOUND,
    "play_monthly_cell_not_found": _CELL_NOT_FOUND,
    "play_monthly_activity_not_found": _error(
        404, "NOT_FOUND", "그 행을 찾을 수 없습니다.", ["item_id"]
    ),
    "play_monthly_week_not_found": _error(
        404, "NOT_FOUND", "그 주를 찾을 수 없습니다.", ["week_id"]
    ),
    "play_monthly_drill_candidate_not_found": _error(
        404, "NOT_FOUND", "그 훈련 후보를 찾을 수 없습니다.", ["item_id"]
    ),
    "play_monthly_safety_candidate_not_found": _invalid("candidate_item_id"),
    "invalid_content_ids": _invalid("content_ids"),
    "play_monthly_drill_candidate_blank": _invalid("item_id"),
    "curriculum_reference_unavailable": _REFERENCE_UNAVAILABLE,
}


def _item(value: str, field: str = "item_id") -> ItemId:
    try:
        return ItemId(value)
    except InvalidDomainValueError as error:
        raise _invalid(field) from error


def _week(value: str) -> WeekId:
    try:
        return WeekId(value)
    except InvalidDomainValueError as error:
        raise _invalid("week_id") from error


def _mutate(session: Session, user, plan_id: int, expected_revision: int, run):
    """소유 → 형식 → 확정됨 → revision → Core → 조건부 UPDATE. `run` 이 Core 를 부른다.

    Core 가 같은 계획안을 돌려주면(무변경) 쓰지 않고 그대로 200 이다.
    """
    row = _own_row(session, user, plan_id)
    if row.status == "CONFIRMED":
        raise _ALREADY_CONFIRMED
    if row.revision != expected_revision:
        raise _STALE_WRITE
    repo = _repo(session, user)
    plan = repo.get(PlanId(row.plan_ref))
    if plan is None:  # _own_row 와 get 사이에 지워졌다
        raise _NOT_FOUND
    drafts: InMemoryPlanRepository[PlayMonthlyPlan] = InMemoryPlanRepository()
    drafts.save(plan.plan_id, plan)
    try:
        changed = run(drafts, plan)
    except InvalidStateTransitionError as error:
        raise _ALREADY_CONFIRMED from error
    except PlayMonthlyLifecycleError as error:
        known = _LIFECYCLE_ERRORS.get(error.code)
        _log.warning("play monthly edit rejected code=%s plan_id=%s", error.code, plan_id)
        if known is None:
            raise
        raise known from error
    if changed is plan:
        return _out(session, user, row, plan)
    written = repo.update_if_revision(changed.plan_id, changed, expected_revision=expected_revision)
    if written is None:  # 그 사이 바뀌었다 — 없어졌으면 404, 확정됐으면 409, 아니면 revision
        session.rollback()
        if _own_row(session, user, plan_id).status == "CONFIRMED":
            raise _ALREADY_CONFIRMED
        raise _STALE_WRITE
    session.refresh(row)
    detail = _out(session, user, row, changed)
    session.commit()
    return detail


@router.put("/{plan_id}/cells/{item_id}", response_model=s.PlayMonthlyPlanOut)
def edit_cell(
    plan_id: int, item_id: str, body: s.EditCellIn, session: DbSession, user: CurrentUser
):
    item = _item(item_id)

    def run(drafts, plan):
        cell = plan.find_cell(item)
        # Core 는 같은 값을 무변경으로 돌려주지만 API 가 막는다(§9-7). Core 와 같은 기준이다.
        if cell is not None and (
            body.value == cell.value or not (body.value or cell.value.strip())
        ):
            raise _invalid("value")
        return EditPlayMonthlyCell(plan_repository=drafts, clock=SystemClock()).execute(
            EditPlayMonthlyCellCommand(plan.plan_id, _actor(user), item, body.value)
        )

    return _mutate(session, user, plan_id, body.expected_revision, run)


@router.put("/{plan_id}/activities/{item_id}/content-ids", response_model=s.PlayMonthlyPlanOut)
def edit_content_ids(
    plan_id: int, item_id: str, body: s.ContentIdsIn, session: DbSession, user: CurrentUser
):
    item = _item(item_id)
    return _mutate(
        session,
        user,
        plan_id,
        body.expected_revision,
        lambda drafts, plan: EditPlayMonthlyContentIds(
            plan_repository=drafts,
            curriculum_repository=play_project.curriculum_repository(),  # 테스트가 바꿔 끼운다
            clock=SystemClock(),
        ).execute(
            EditPlayMonthlyContentIdsCommand(plan.plan_id, _actor(user), item, body.content_ids)
        ),
    )


@router.post(
    "/{plan_id}/activities",
    response_model=s.PlayMonthlyPlanOut,
    # 계약 §9-7: 모든 변경이 200 이다.
    status_code=status.HTTP_200_OK,
)
def add_activity(plan_id: int, body: s.AddActivityIn, session: DbSession, user: CurrentUser):
    return _mutate(
        session,
        user,
        plan_id,
        body.expected_revision,
        lambda drafts, plan: AddPlayMonthlyActivity(
            plan_repository=drafts, id_generator=UuidGenerator(), clock=SystemClock()
        ).execute(AddPlayMonthlyActivityCommand(plan.plan_id, _actor(user), body.section)),
    )


@router.delete("/{plan_id}/activities/{item_id}", response_model=s.PlayMonthlyPlanOut)
def remove_activity(
    plan_id: int,
    item_id: str,
    session: DbSession,
    user: CurrentUser,
    expected_revision: Annotated[int, Query(ge=1)],  # 쿼리는 문자열로 오므로 strict 가 아니다
):
    item = _item(item_id)
    return _mutate(
        session,
        user,
        plan_id,
        expected_revision,
        lambda drafts, plan: RemovePlayMonthlyActivity(
            plan_repository=drafts, clock=SystemClock()
        ).execute(RemovePlayMonthlyActivityCommand(plan.plan_id, _actor(user), item)),
    )


@router.put("/{plan_id}/safety-weeks/{week_id}", response_model=s.PlayMonthlyPlanOut)
def place_safety(
    plan_id: int, week_id: str, body: s.SafetyWeekIn, session: DbSession, user: CurrentUser
):
    week = _week(week_id)
    candidate = (
        None
        if body.candidate_item_id is None
        else _item(body.candidate_item_id, "candidate_item_id")
    )
    return _mutate(
        session,
        user,
        plan_id,
        body.expected_revision,
        lambda drafts, plan: PlacePlayMonthlySafety(
            plan_repository=drafts, clock=SystemClock()
        ).execute(PlacePlayMonthlySafetyCommand(plan.plan_id, _actor(user), week, candidate)),
    )


@router.post("/{plan_id}/drill-candidates/{item_id}/copy", response_model=s.PlayMonthlyPlanOut)
def copy_drill_candidate(
    plan_id: int, item_id: str, body: RevisionIn, session: DbSession, user: CurrentUser
):
    item = _item(item_id)
    return _mutate(
        session,
        user,
        plan_id,
        body.expected_revision,
        lambda drafts, plan: CopyPlayMonthlyDrillCandidate(
            plan_repository=drafts, clock=SystemClock()
        ).execute(CopyPlayMonthlyDrillCandidateCommand(plan.plan_id, _actor(user), item)),
    )


def _repo(session: Session, user) -> PostgresPlanRepository[PlayMonthlyPlan]:
    return PostgresPlanRepository(
        session, center_id=user.center_id, kind="monthly", plan_type=PlayMonthlyPlan
    )


def _out(session: Session, user, row: Plan, plan: PlayMonthlyPlan) -> s.PlayMonthlyPlanOut:
    annual_id = session.scalar(
        select(Plan.id).where(
            Plan.plan_ref == plan.parent.lineage.parent_plan_id.value,
            Plan.center_id == user.center_id,
            Plan.kind == "annual",
        )
    )
    return _detail(row, plan, annual_id)


def _own_row(session: Session, user, plan_id: int) -> Plan:
    """이 원의 놀이 월간 행. 없거나 남의 원이면 404, 기존 월간이면 409."""
    row = session.scalar(
        select(Plan)
        .where(Plan.id == plan_id, Plan.center_id == user.center_id, Plan.kind == "monthly")
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise _NOT_FOUND
    if not _is_play_monthly(row):
        raise _LEGACY_MONTHLY
    return row


def _cell(cell: PlayMonthlyCell) -> s.CellOut:
    generation = cell.generation
    return s.CellOut(
        item_id=cell.item_id.value,
        value=cell.value,
        evidence=[
            EvidenceOut(
                source_type=e.source_type.value,
                source_id=e.source_id,
                source_version=e.source_version,
                effective_date=e.effective_date,
                display_name=e.display_name,
            )
            for e in cell.evidence
        ],
        generation=None
        if generation is None
        else GenerationOut(
            method=generation.method.value,
            rule_id=generation.rule_id,
            rule_version=generation.rule_version,
        ),
    )


def _activity(activity: PlayActivity) -> s.ActivityOut:
    parent = activity.parent_snapshot
    return s.ActivityOut(
        activity_id=activity.cell.item_id.value,
        name=_cell(activity.cell),
        description=_cell(activity.description),
        content_ids=list(activity.content_ids),
        parent_item_id=None if parent is None else parent.parent_item_id.value,
    )


def _detail(row: Plan, plan: PlayMonthlyPlan, annual_id: int | None) -> s.PlayMonthlyPlanOut:
    parent = plan.parent
    return s.PlayMonthlyPlanOut(
        id=row.id,
        class_id=int(plan.classroom_ref),
        school_year=plan.school_year,
        month=plan.target_month.calendar_month,
        target_month=plan.target_month.value,
        status=row.status,
        revision=row.revision,
        format=plan.format,
        format_version=plan.layout.layout_version,
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
        target_ages=sorted(plan.target_ages),
        weeks=[
            s.WeekOut(
                week_id=w.week_id.value,
                label=w.display_label,
                start_date=w.start_date,
                end_date=w.end_date,
                active=w.active,
            )
            for w in plan.weeks
        ],
        parent=s.ParentOut(
            annual_plan_id=annual_id,
            period_key=parent.period_key,
            layout_version=parent.layout_version,
            confirmed_at=parent.lineage.confirmed_at,
            plays=[
                s.ParentPlayOut(
                    row_key=p.row_key,
                    play_name_item_id=p.play_name_item_id.value,
                    play_name=p.play_name,
                    materials=p.materials,
                    support_direction=p.support_direction,
                    emphasized=p.row_key in parent.emphasized,
                )
                for p in parent.plays
            ],
        ),
        theme=_cell(plan.theme),
        rationale=_cell(plan.rationale),
        together=[_activity(a) for a in plan.together],
        free_play=[_activity(a) for a in plan.free_play],
        habits=[
            s.HabitOut(week_id=h.week_id.value, entry_id=h.habit.entry_id, cell=_cell(h.habit.cell))
            for h in plan.habits
        ],
        safety_candidates=[
            s.SafetyCandidateOut(
                kind=c.kind.value,
                category_id=c.category_id,
                topic_group=c.topic_group,
                cell=_cell(c.cell),
            )
            for c in plan.safety_candidates
        ],
        safety_weeks=[
            s.SafetyWeekOut(
                week_id=w.week_id.value,
                candidate_item_id=None
                if w.candidate_item_id is None
                else w.candidate_item_id.value,
            )
            for w in plan.safety_weeks
        ],
        health=s.EntryOut(entry_id=plan.health.entry_id, cell=_cell(plan.health.cell)),
        nutrition=s.EntryOut(entry_id=plan.nutrition.entry_id, cell=_cell(plan.nutrition.cell)),
        drill_candidates=[
            s.DrillCandidateOut(topic_id=d.topic_id, label=d.label, cell=_cell(d.cell))
            for d in plan.drill_candidates
        ],
        teacher_inputs=[
            s.TeacherInputOut(key=t.semantic_key, cell=_cell(t)) for t in plan.teacher_inputs
        ],
        notices=[
            s.NoticeOut(code=n.code, week_id=None if n.week_id is None else n.week_id.value)
            for n in play_monthly_notices(plan)
        ],
    )
