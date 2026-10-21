"""주간계획안 생성 · 조회 · 목록 · 삭제 API. 계약은 docs/api-spec.md §9-6 이다.

**월간 router 와 같은 세 단계다**(monthly_router.py 머리말). LLM 을 기다리는 동안 DB 를 잡지 않는다.

    A. 짧은 읽기 — 반 소유 · 주 모양 · 중복 · 부모 월간(CONFIRMED) · 원의 토요일 설정
    B. Core 실행 — DB 없이. 부모 월간은 메모리 저장소로 넘긴다
    C. 짧은 쓰기 — 중복을 다시 보고 저장 · commit. 동시 요청은 부분 유일 인덱스가 막는다

**여기에 생성 규칙이 없다.** 칸 · 근거 · 바깥놀이 후보는 p0-planning 이 정한다.
칸 편집 · 재생성 · 확정 · 이력은 W5b 다(Core W4 머지 뒤).
"""

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.adapters.weekly_composition import (
    WEEKLY_TEMPLATE_REF,
    weekly_generation,
    weekly_operating_days,
)
from ssuksak.planning import (
    GenerateWeeklyPlanCommand,
    InvalidDomainValueError,
    MonthlyApplicationError,
    MonthlyGenerationMode,
    MonthlyPlan,
    PlanId,
    WeekId,
    WeeklyPlan,
)

from app.db import get_session
from app.features.centers.models import Center
from app.features.plans.models import Plan
from app.features.plans.monthly_router import (
    _REFERENCE_UNAVAILABLE,
    _UNAVAILABLE,
    ACTIVITY_CATALOG,
    SAFETY_RULE,
    _error,
    _gate,
    _target_month,
)
from app.features.plans.monthly_schemas import (
    ConstraintOut,
    FindingOut,
    RuleRefOut,
    TemplateRefOut,
    VerificationOut,
)
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import EvidenceOut, GenerationOut
from app.features.plans.weekly_schemas import (
    CreateWeeklyPlan,
    ParentSnapshotOut,
    WeeklyCellOut,
    WeeklyParentOut,
    WeeklyPlanListOut,
    WeeklyPlanOut,
    WeeklyPlanSummary,
    WeeklySectionOut,
    WeekPeriodOut,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class
from app.shared.llm import LlmBudgetExceeded, LlmUnavailable, is_mock

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/plans/weekly", tags=["plans"])

DbSession = Annotated[Session, Depends(get_session)]

# 주간은 반 · 주당 하나다(주간 계약 §4-1 G5). 이 이름의 충돌만 409 로 바꾼다.
WEEKLY_UNIQUE = "uq_plans_weekly_per_classroom_week"
# 주간은 Profile 이 없어 기반 Template 이 서버 상수다 — 못 쓰면 교사가 고칠 수 없다(결정 ④).
_TEMPLATE_UNAVAILABLE = frozenset({"monthly_template_not_found", "monthly_template_not_approved"})
# 고른 주가 부모 월간에 없거나 비활성이다(G4). 교사가 다른 주를 고른다.
_WEEK_NOT_USABLE = frozenset({"weekly_week_not_in_parent", "weekly_week_inactive"})

_NOT_FOUND = _error(404, "NOT_FOUND", "주간계획안을 찾을 수 없습니다.", ["id"])
_ALREADY_EXISTS = _error(
    409, "ALREADY_EXISTS", "이 반의 그 주 주간계획안이 이미 있습니다.", ["class_id", "week_id"]
)
# 문구는 요청 모양 오류(main.py validation_error)와 같다. Core 문구는 내보내지 않는다.
_WEEK_INVALID = _error(422, "VALIDATION_FAILED", "입력값을 확인해주세요.", ["week_id"])


def _weekly_repo(session: Session, center_id: int) -> PostgresPlanRepository[WeeklyPlan]:
    return PostgresPlanRepository(session, center_id=center_id, kind="weekly", plan_type=WeeklyPlan)


def _weekly_provider():
    """mock 이면 요청 기반 결정적 provider. **real 은 W7 전까지 막는다**(결정 ②) — 503.

    실제 문장 품질을 본 적 없는 경로를 운영에 열지 않는다. 실패했다고 mock 으로 갈아타지 않는다.
    """
    if is_mock():
        return RequestAwareWeeklyLlm()
    raise LlmUnavailable("주간 실제 LLM 연결은 아직 없다 (W7)")


def _week(value: str, school_year: int) -> WeekId:
    """주 모양 · 그 달이 반 학년도 안(3월 ~ 다음 해 2월)인지(G2)."""
    try:
        week = WeekId(value)
    except InvalidDomainValueError as error:
        raise _WEEK_INVALID from error
    month = week.target_month
    if _target_month(school_year, month.calendar_month) != month:
        raise _WEEK_INVALID
    return week


def _existing(session: Session, center_id: int, class_id: int, week: WeekId):
    return session.scalar(
        select(Plan.id).where(
            Plan.center_id == center_id,
            Plan.kind == "weekly",
            Plan.classroom_ref == str(class_id),
            Plan.week_id == week.value,
        )
    )


def _generation_error(error: MonthlyApplicationError):
    """원인은 `__cause__` 에 있다 — Core 가 provider 오류를 자기 것으로 감싼다(월간과 같다)."""
    cause = error.__cause__
    if isinstance(cause, LlmBudgetExceeded):
        return _error(
            503, "LLM_BUDGET_EXCEEDED", "생성 한도에 걸렸습니다. 운영에 문의해주세요.", []
        )
    if (
        isinstance(cause, LlmUnavailable)
        or error.code in _REFERENCE_UNAVAILABLE
        or error.code in _TEMPLATE_UNAVAILABLE
    ):
        return _UNAVAILABLE
    if error.code in _WEEK_NOT_USABLE:
        return _WEEK_INVALID
    # LLM 호출이 깨졌다 · 수리 뒤에도 계약 위반 · 검증 실패 · 저장된 부모가 깨졌다. 저장 없음.
    return _error(
        500, "GENERATION_FAILED", "주간계획안을 만들지 못했습니다. 다시 시도해주세요.", []
    )


@router.post("", response_model=WeeklyPlanOut, status_code=status.HTTP_201_CREATED)
def create_weekly_plan(body: CreateWeeklyPlan, session: DbSession, user: CurrentUser):
    """한 주치를 만들어 DRAFT 로 저장한다. 실패하면 아무것도 남지 않는다."""
    # ── A. 짧은 읽기 ──────────────────────────────────────────────────────
    klass = require_own_class(session, user, body.class_id)
    center_id, class_id = user.center_id, klass.id
    week = _week(body.week_id, klass.school_year)
    if _existing(session, center_id, class_id, week) is not None:
        raise _ALREADY_EXISTS
    parent_row = session.scalar(
        select(Plan).where(
            Plan.center_id == center_id,
            Plan.kind == "monthly",
            Plan.classroom_ref == str(class_id),
            Plan.target_month == week.target_month.value,
        )
    )
    if parent_row is None:
        raise _gate("월간계획안을 먼저 만들어 확정해주세요.")
    parent_id = parent_row.id
    parent = PostgresPlanRepository(
        session, center_id=center_id, kind="monthly", plan_type=MonthlyPlan
    ).get(PlanId(parent_row.plan_ref))
    if parent.status.value != "CONFIRMED":
        raise _gate("월간계획안을 먼저 확정해주세요.")
    # 만들 때의 원 설정을 계획안에 복사한다 — 뒤에 설정을 바꿔도 이 계획안은 그대로다(§3-5).
    saturday = session.get(Center, center_id).weekly_saturday_enabled
    try:
        provider = _weekly_provider()
    except LlmUnavailable as error:
        raise _UNAVAILABLE from error
    # 읽기를 여기서 끝낸다. LLM 을 기다리는 동안 transaction · 연결을 잡지 않는다.
    session.commit()

    # ── B. Core 실행 — DB 없음 ────────────────────────────────────────────
    parents: InMemoryPlanRepository[MonthlyPlan] = InMemoryPlanRepository()
    parents.save(parent.plan_id, parent)
    use_case = weekly_generation(
        parent_plan_repository=parents,
        plan_repository=InMemoryPlanRepository(),
        provider=provider,
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )
    try:
        plan = use_case.execute(
            GenerateWeeklyPlanCommand(
                parent_monthly_plan_id=parent.plan_id,
                week_id=week,
                operating_days=weekly_operating_days(saturday),
                template_ref=WEEKLY_TEMPLATE_REF,
                safety_rule=SAFETY_RULE,
                generation_mode=MonthlyGenerationMode.LLM_PLANNER,
                activity_catalog=ACTIVITY_CATALOG,
            )
        ).plan
    except MonthlyApplicationError as error:
        _log.warning(
            "weekly generation failed code=%s cause=%s",
            error.code,
            type(error.__cause__).__name__ if error.__cause__ else "-",
        )
        raise _generation_error(error) from error

    # ── C. 짧은 쓰기 ──────────────────────────────────────────────────────
    if _existing(session, center_id, class_id, week) is not None:
        raise _ALREADY_EXISTS
    try:
        _weekly_repo(session, center_id).save(plan.plan_id, plan)
    except IntegrityError as error:
        session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == WEEKLY_UNIQUE:
            raise _ALREADY_EXISTS from error
        raise
    row = session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))
    # **응답을 다 만든 뒤에 확정한다**(월간과 같다). 저장소가 flush 해 두어 commit 전에도 읽힌다.
    detail = _detail(row, plan, parent_id)
    session.commit()
    return detail


@router.get("", response_model=WeeklyPlanListOut)
def list_weekly_plans(
    session: DbSession, user: CurrentUser, class_id: int | None = None, month: int | None = None
):
    """요약만 담는다. 주 오름차순. `month`(달력 달)는 `class_id` 와 함께만 받는다 —
    반의 학년도가 연도를 정한다(월간 생성과 같은 규칙, 결정 ⑥)."""
    query = select(Plan).where(Plan.center_id == user.center_id, Plan.kind == "weekly")
    if month is not None and (class_id is None or not 1 <= month <= 12):
        raise _error(422, "VALIDATION_FAILED", "입력값을 확인해주세요.", ["month"])
    if class_id is not None:
        klass = require_own_class(session, user, class_id)
        query = query.where(Plan.classroom_ref == str(class_id))
        if month is not None:
            query = query.where(Plan.target_month == _target_month(klass.school_year, month).value)
    rows = session.scalars(query.order_by(Plan.week_id, Plan.id)).all()
    return WeeklyPlanListOut(
        items=[
            WeeklyPlanSummary(
                id=row.id,
                class_id=int(row.classroom_ref),
                school_year=row.school_year,
                week_id=row.week_id,
                target_month=row.target_month,
                status=row.status,
                revision=row.revision,
                created_at=row.created_at,
                confirmed_at=row.confirmed_at,
            )
            for row in rows
        ]
    )


@router.get("/{plan_id}", response_model=WeeklyPlanOut)
def get_weekly_plan(plan_id: int, session: DbSession, user: CurrentUser):
    """남의 원 것 · 주간이 아닌 것은 없는 것과 같다."""
    row = _own_row(session, user, plan_id)
    plan = _weekly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    parent_id = session.scalar(
        select(Plan.id).where(
            Plan.plan_ref == plan.parent_lineage.parent_plan_id.value,
            Plan.center_id == user.center_id,
            Plan.kind == "monthly",
        )
    )
    return _detail(row, plan, parent_id)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weekly_plan(plan_id: int, session: DbSession, user: CurrentUser) -> Response:
    """확정 전 주간계획안을 지운다(결정 ③). 월간과 같은 이유다 — 반 · 주당 하나라 만들기가
    409 로 막히므로, 지우기가 없으면 첫 초안이 마음에 안 들어도 그 주는 다시 못 만든다.

    **확정본은 안 지운다.** 제출 문서다.
    """
    row = _own_row(session, user, plan_id)
    if row.status == "CONFIRMED":
        raise _error(409, "GATE_BLOCKED", "확정된 계획안은 지울 수 없습니다.", [])
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _own_row(session: Session, user, plan_id: int) -> Plan:
    row = session.scalar(
        select(Plan).where(
            Plan.id == plan_id, Plan.center_id == user.center_id, Plan.kind == "weekly"
        )
    )
    if row is None:
        raise _NOT_FOUND
    return row


def _detail(row: Plan, plan: WeeklyPlan, parent_id: int) -> WeeklyPlanOut:
    """도메인 객체를 계약 형식으로. 칸 순서는 Core 가 정한 Template 순서 그대로다.

    `revision` 은 DB 행의 값이다. **`safety`(배치 정보)는 내지 않는다** — 월간도 내지 않는다.
    """
    period = plan.week_period
    report = plan.verification_report
    cells = {cell.section_key: cell for cell in plan.cells}
    saturday = plan.operating_days[-1].value == "SAT"
    return WeeklyPlanOut(
        id=row.id,
        class_id=int(plan.classroom_ref),
        school_year=plan.school_year,
        week_id=plan.week_id.value,
        target_month=plan.week_id.target_month.value,
        status=plan.status.value,
        revision=row.revision,
        generation_mode=plan.generation_mode.value,
        week_period=WeekPeriodOut(
            label=period.display_label, start_date=period.start_date, end_date=period.end_date
        ),
        operating_days=[day.value for day in plan.operating_days],
        # 표시 기간(주간 계약 §3-2): 토요일이면 그 주 토요일까지. FE 가 따로 계산하지 않는다.
        display_end_date=period.start_date + timedelta(days=5) if saturday else period.end_date,
        base_template_ref=TemplateRefOut(
            template_id=plan.template_snapshot.base_template_ref.template_id,
            template_version=plan.template_snapshot.base_template_ref.template_version,
        ),
        parent=WeeklyParentOut(
            monthly_plan_id=parent_id,
            theme=plan.parent_lineage.snapshot_value,
            confirmed_at=plan.parent_lineage.confirmed_at,
        ),
        sections=[
            WeeklySectionOut(
                section_key=section.section_key,
                label=section.display_label,
                role=section.role.value,
                visible=section.visible,
                order=section.order,
                semantic_variant=(
                    None if section.semantic_variant is None else section.semantic_variant.value
                ),
                cells=[_cell(cells[section.section_key])],
            )
            for section in plan.template_snapshot.sections
        ],
        constraints=[
            ConstraintOut(
                code=assessment.constraint.code,
                verification=assessment.verification.value,
                affected_section_keys=list(assessment.affected_section_keys),
                required_source_kinds=list(assessment.required_source_kinds),
                rule_version=assessment.rule_version,
                detail=assessment.detail,
            )
            for assessment in plan.constraint_assessments
        ],
        verification=VerificationOut(
            executed_rules=[
                RuleRefOut(rule_id=rule.rule_id, rule_version=rule.rule_version)
                for rule in (report.executed_rules if report else ())
            ],
            findings=[
                FindingOut(
                    code=finding.code,
                    kind=finding.finding_kind.value,
                    severity=finding.severity.value,
                    section_key=finding.location.section_key,
                    week_id=None
                    if finding.location.week_id is None
                    else finding.location.week_id.value,
                    message=finding.message,
                )
                for finding in (report.findings if report else ())
            ],
        ),
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
    )


def _cell(cell) -> WeeklyCellOut:
    generation = cell.generation
    return WeeklyCellOut(
        item_id=cell.item_id.value,
        value=cell.value,
        state=cell.cell_state.value,
        evidence=[
            EvidenceOut(
                source_type=source.source_type.value,
                source_id=source.source_id,
                source_version=source.source_version,
                effective_date=source.effective_date,
                display_name=source.display_name,
            )
            for source in cell.evidence
        ],
        generation=None
        if generation is None
        else GenerationOut(
            method=generation.method.value,
            rule_id=generation.rule_id,
            rule_version=generation.rule_version,
        ),
        parent_snapshots=[
            ParentSnapshotOut(
                parent_item_id=snapshot.parent_item_id.value,
                snapshot_value=snapshot.snapshot_value,
            )
            for snapshot in cell.parent_snapshots
        ],
    )
