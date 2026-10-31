"""놀이 중심 월간계획안 — 생성 · 조회 · 목록 · 삭제 · 고치기. 계약은 docs/api-spec.md §9-7 이다.

**이 파일에 생성 규칙이 없다.** 본문은 p0-planning 이 만든 `PlayMonthlyPlan` 이고, 여기는 읽어서
응답 모양으로 옮긴다. 오류 · 상수 · 학년도 계산은 기존 월간(`monthly_router`)의 것을 쓴다.

`play` 는 고정 글자 경로라 `monthly_router` 의 `GET /{plan_id}` 보다 먼저 등록한다(main.py).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.adapters.elice_openai_monthly import (
    MonthlyLlmConfigurationError,
    MonthlyLlmProviderError,
)
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.play_monthly_composition import (
    play_monthly_command,
    play_monthly_generation,
)
from ssuksak.planning import InvalidDomainValueError, ItemId, PlanId
from ssuksak.planning.application.generate_play_monthly_plan import PlayMonthlyGenerationError
from ssuksak.planning.application.play_monthly_lifecycle import (
    AddPlayMonthlyActivity,
    AddPlayMonthlyActivityCommand,
    ConfirmPlayMonthlyPlan,
    ConfirmPlayMonthlyPlanCommand,
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
from ssuksak.planning.domain.play_project_plan import (  # 공개 창구에 없다
    PLAY_PROJECT_FORMAT,
    PlayProjectYearlyPlan,
)
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.planner.contracts import ProposalParseError, ProposalRejectedError

from app.db import get_session
from app.features.plans import monthly_llm, play_project
from app.features.plans import play_monthly_schemas as s
from app.features.plans.models import Plan
from app.features.plans.monthly_router import (
    _ALREADY_CONFIRMED,
    _ALREADY_EXISTS,
    _CELL_NOT_FOUND,
    _NOT_DELETABLE,
    _NOT_FOUND,
    _STALE_WRITE,
    MONTHLY_UNIQUE,
    _actor,
    _error,
    _existing,
    _gate,
    _generation,
    _is_play_monthly,
    _target_month,
)
from app.features.plans.monthly_schemas import GenerationChangeOut, RevisionIn, ValueChangeOut
from app.features.plans.play_project import ConfirmIn, format_of
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.router import _exception_chain
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import EvidenceOut, GenerationOut
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable

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
_BUDGET_EXCEEDED = _error(
    503, "LLM_BUDGET_EXCEEDED", "생성 한도에 걸렸습니다. 운영에 문의해주세요.", []
)
_GENERATION_FAILED = _error(
    500, "GENERATION_FAILED", "월간계획안을 만들지 못했습니다. 다시 시도해주세요.", []
)
# 자료 계열 Core 코드만 503 이다(api-spec §9-7 구현 경계). 앞부분으로 가른다.
_REFERENCE_CODES = (
    "CURRICULUM_REFERENCE_",
    "DAILY_LIFE_",
    "DRILL_",
    "SAFETY_",
    "LIFE_SAFETY_GROUNDING_INSUFFICIENT",
)
# 서버가 읽은 행과 Core 가 읽은 본문이 어긋날 때만 난다. 행 게이트와 같은 문구다.
_PARENT_GATES = {
    "PARENT_NOT_FOUND": "연간계획안을 먼저 만들어 확정해주세요.",
    "PARENT_NOT_CONFIRMED": "연간계획안을 먼저 확정해주세요.",
    "PARENT_NOT_PLAY_PROJECT": (
        "월별 주제형 연간계획안으로는 놀이 중심 월간계획안을 만들 수 없습니다."
    ),
}


def _generation_error(error: Exception):
    """계약 오류로 바꾼다. **None 이면 표에 없는 것** — 그대로 올려 공통 500 INTERNAL_ERROR 다.

    Core 코드는 서버 기록에만 남긴다. 부모 확정 기록 누락 · 구간 미완성 같은
    운영 확인 상태가 None 이다.
    """
    if isinstance(error, PlayMonthlyGenerationError):
        _log.warning("play monthly generation rejected code=%s", error.code)
        if error.code == "EMPHASIS_NOT_SELECTED":
            return _invalid("emphasized_row_keys")
        if error.code.startswith(_REFERENCE_CODES):
            return _UNAVAILABLE
        if error.code in _PARENT_GATES:
            return _gate(_PARENT_GATES[error.code])
        return None
    chain = tuple(_exception_chain(error))
    _log.warning(
        "play monthly generation failed types=%s",
        ",".join(type(item).__name__ for item in chain),
    )
    if any(isinstance(item, LlmBudgetExceeded) for item in chain):
        return _BUDGET_EXCEEDED
    if any(isinstance(item, (LlmUnavailable, MonthlyLlmConfigurationError)) for item in chain):
        return _UNAVAILABLE
    # 호출이 깨졌다(시간 초과 포함) · 수리 뒤에도 계약 위반. 재시도할 수 있다.
    failed = (MonthlyLlmProviderError, LlmFailed, ProposalParseError, ProposalRejectedError)
    if any(isinstance(item, failed) for item in chain):
        return _GENERATION_FAILED
    return None


@router.post("", response_model=s.PlayMonthlyPlanOut, status_code=status.HTTP_201_CREATED)
def create_play_monthly_plan(body: s.CreatePlayMonthlyPlan, session: DbSession, user: CurrentUser):
    """한 달치를 만들어 DRAFT 로 저장한다. 실패하면 아무것도 남지 않는다(기존 월간과 같다)."""
    # ── A. 짧은 읽기 ──────────────────────────────────────────────────────
    klass = require_own_class(session, user, body.class_id)
    center_id, class_id, class_name = user.center_id, klass.id, klass.name
    school_year = klass.school_year
    month = _target_month(school_year, body.month)
    if _existing(session, center_id, class_id, month) is not None:
        raise _ALREADY_EXISTS
    parent_row = session.scalar(
        select(Plan).where(
            Plan.center_id == center_id,
            Plan.kind == "annual",
            Plan.classroom_ref == str(class_id),
        )
    )
    if parent_row is None:
        raise _gate("연간계획안을 먼저 만들어 확정해주세요.")
    # 월별 주제형 본문은 읽기 전에 막는다. 확정 여부와 관계없다.
    if format_of(parent_row) != PLAY_PROJECT_FORMAT:
        raise _gate("월별 주제형 연간계획안으로는 놀이 중심 월간계획안을 만들 수 없습니다.")
    if parent_row.status != "CONFIRMED":
        raise _gate("연간계획안을 먼저 확정해주세요.")
    parent_id = parent_row.id
    parent = PostgresPlanRepository(
        session, center_id=center_id, kind="annual", plan_type=PlayProjectYearlyPlan
    ).get(PlanId(parent_row.plan_ref))
    try:
        provider = monthly_llm.play_monthly_provider()
    except LlmUnavailable as error:
        raise _UNAVAILABLE from error
    # 읽기를 여기서 끝낸다. LLM 을 기다리는 동안 transaction · 연결을 잡지 않는다.
    session.commit()

    # ── B. Core 실행 — DB 없음 ────────────────────────────────────────────
    # 부모 확정 기록 · 강조 · 자료 승인은 Core 가 본다. 자료 판은 조립부가 정한다(ADR-046 질문 4).
    parents: InMemoryPlanRepository[PlayProjectYearlyPlan] = InMemoryPlanRepository()
    parents.save(parent.plan_id, parent)
    use_case = play_monthly_generation(
        parent_repository=parents,
        plan_repository=InMemoryPlanRepository(),  # 운영 저장은 C 에서 한다
        provider=provider,
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )
    try:
        plan = use_case.execute(
            play_monthly_command(
                parent_plan_id=parent.plan_id,
                classroom_ref=str(class_id),
                school_year=school_year,
                target_month=month,
                emphasized_row_keys=tuple(body.emphasized_row_keys),
                class_name=class_name,
            )
        )
    except Exception as error:
        mapped = _generation_error(error)
        if mapped is None:
            raise
        raise mapped from error

    # ── C. 짧은 쓰기 ──────────────────────────────────────────────────────
    if _existing(session, center_id, class_id, month) is not None:
        raise _ALREADY_EXISTS
    try:
        _repo(session, user).save(plan.plan_id, plan)
    except IntegrityError as error:
        session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == MONTHLY_UNIQUE:
            raise _ALREADY_EXISTS from error
        raise
    row = session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))
    # **응답을 다 만든 뒤에 확정한다**(기존 월간과 같다). 저장소가 flush 해 두어 commit 전에도
    # 읽힌다.
    detail = _detail(row, plan, parent_id)
    session.commit()
    return detail


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


# ── 확정 · 변경 이력 (§9-7) ────────────────────────────────────────────────


def _problem_field(problem: str) -> str:
    """Core 의 `together:item_3: 5 content ids` → `together.item_3.content_ids`."""
    key = problem.split(": ", 1)
    where, what = key[0].replace(":", "."), key[1] if len(key) > 1 else ""
    return f"{where}.content_ids" if "content ids" in what else where


@router.post("/{plan_id}/confirm", response_model=s.PlayMonthlyPlanOut)
def confirm_play_monthly_plan(
    plan_id: int,
    session: DbSession,
    user: CurrentUser,
    body: Annotated[ConfirmIn | None, Body()] = None,
):
    row = _own_row(session, user, plan_id)
    repo = _repo(session, user)
    if row.status == "CONFIRMED":  # 멱등. Core 도 쓰기도 없다. expected_revision 과 무관하다
        return _out(session, user, row, _plan(repo, row))
    expected = None if body is None else body.expected_revision
    if expected is None:
        raise _invalid("expected_revision")
    if row.revision != expected:
        raise _STALE_WRITE
    plan = _plan(repo, row)
    drafts: InMemoryPlanRepository[PlayMonthlyPlan] = InMemoryPlanRepository()
    drafts.save(plan.plan_id, plan)
    try:
        confirmed = ConfirmPlayMonthlyPlan(plan_repository=drafts, clock=SystemClock()).execute(
            ConfirmPlayMonthlyPlanCommand(plan.plan_id, _actor(user))
        )
    except InvalidStateTransitionError as error:
        raise _ALREADY_CONFIRMED from error
    except PlayMonthlyLifecycleError as error:
        if error.code != "play_monthly_incomplete":
            raise
        _log.warning("play monthly confirm rejected plan_id=%s %s", plan_id, error.problems)
        raise _invalid(*(_problem_field(p) for p in error.problems)) from error
    plan_id = row.id  # rollback 이 row 를 만료시킨다
    written = repo.update_if_revision(confirmed.plan_id, confirmed, expected_revision=expected)
    if written is None:  # 그 사이 바뀌었다 — 먼저 확정했으면 재호출과 같다(200)
        session.rollback()
        row = _own_row(session, user, plan_id)
        if row.status != "CONFIRMED":
            raise _STALE_WRITE
        return _out(session, user, row, _plan(repo, row))
    session.refresh(row)
    detail = _out(session, user, row, confirmed)
    session.commit()
    return detail


@router.get("/{plan_id}/audit", response_model=s.PlayMonthlyAuditOut)
def get_play_monthly_audit(plan_id: int, session: DbSession, user: CurrentUser):
    """저장된 이벤트를 읽기만 한다. 지운 행의 칸 이벤트도 싣는다."""
    row = _own_row(session, user, plan_id)
    plan = _plan(_repo(session, user), row)
    removed = [
        c for r in plan.removed_activities for c in (r.activity.cell, r.activity.description)
    ]
    keyed = [
        ((e.occurred_at, 0, 0, i), _audit_event(e, False)) for i, e in enumerate(plan.audit.events)
    ]
    # 활성 칸(응답 순서) → 지운 행의 칸(쌓인 순서). 한 칸 안에서는 저장 순서다.
    for position, cell in enumerate((*plan.cells(), *removed)):
        keyed += [
            ((e.occurred_at, 1, position, i), _audit_event(e, True))
            for i, e in enumerate(cell.audit.events)
        ]
    keyed.sort(key=lambda pair: pair[0])
    return s.PlayMonthlyAuditOut(items=[out for _, out in keyed])


def _plan(repo, row: Plan) -> PlayMonthlyPlan:
    plan = repo.get(PlanId(row.plan_ref))
    if plan is None:  # _own_row 와 get 사이에 지워졌다
        raise _NOT_FOUND
    return plan


def _audit_event(e, is_cell: bool) -> s.PlayMonthlyAuditEventOut:
    value, gen, link, arr = e.value_change, e.generation_change, e.link_change, e.arrangement_change
    return s.PlayMonthlyAuditEventOut(
        type=e.event_type.value,
        occurred_at=e.occurred_at,
        scope="CELL" if is_cell else "PLAN",
        item_id=None if e.item_id is None else e.item_id.value,
        actor=None if e.actor_id is None else e.actor_id.value,
        system_actor=e.system_actor,
        value_change=None
        if value is None
        else ValueChangeOut(before=value.before, after=value.after),
        generation_change=None
        if gen is None
        else GenerationChangeOut(before=_generation(gen.before), after=_generation(gen.after)),
        link_change=None
        if link is None
        else s.LinkChangeOut(
            before=list(link.before), after=list(link.after), catalog_version=link.catalog_version
        ),
        arrangement_change=None
        if arr is None
        else s.ArrangementChangeOut(
            scope=arr.scope, before=list(arr.before), after=list(arr.after)
        ),
        copied_from=None if e.copied_from is None else e.copied_from.value,
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
