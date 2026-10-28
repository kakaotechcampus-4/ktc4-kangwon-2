"""놀이 중심 월간계획안 — 조회 · 목록 · 삭제 · 생성 게이트. 계약은 docs/api-spec.md §9-7 이다.

**이 파일에 생성 규칙이 없다.** 본문은 p0-planning 이 만든 `PlayMonthlyPlan` 이고, 여기는 읽어서
응답 모양으로 옮긴다. 오류 · 상수 · 학년도 계산은 기존 월간(`monthly_router`)의 것을 쓴다.

`play` 는 고정 글자 경로라 `monthly_router` 의 `GET /{plan_id}` 보다 먼저 등록한다(main.py).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ssuksak.planning import PlanId
from ssuksak.planning.application.play_monthly_lifecycle import play_monthly_notices
from ssuksak.planning.domain.play_monthly_plan import (
    PlayActivity,
    PlayMonthlyCell,
    PlayMonthlyPlan,
)
from ssuksak.planning.domain.play_project_plan import PLAY_PROJECT_FORMAT  # 공개 창구에 없다

from app.db import get_session
from app.features.plans import play_monthly_schemas as s
from app.features.plans.models import Plan
from app.features.plans.monthly_router import (
    _ALREADY_EXISTS,
    _NOT_DELETABLE,
    _NOT_FOUND,
    _error,
    _existing,
    _gate,
    _is_play_monthly,
    _target_month,
)
from app.features.plans.play_project import format_of
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.schemas import EvidenceOut, GenerationOut
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class

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
    plan = PostgresPlanRepository(
        session, center_id=user.center_id, kind="monthly", plan_type=PlayMonthlyPlan
    ).get(PlanId(row.plan_ref))
    annual_id = session.scalar(
        select(Plan.id).where(
            Plan.plan_ref == plan.parent.lineage.parent_plan_id.value,
            Plan.center_id == user.center_id,
            Plan.kind == "annual",
        )
    )
    return _detail(row, plan, annual_id)


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
