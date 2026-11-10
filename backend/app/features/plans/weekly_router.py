"""주간계획안 생성 · 조회 · 목록 · 삭제 API. 계약은 docs/api-spec.md §9-6 이다.

**월간 router 와 같은 세 단계다**(monthly_router.py 머리말). LLM 을 기다리는 동안 DB 를 잡지 않는다.

    A. 짧은 읽기 — 반 소유 · 주 모양 · 중복 · 부모 월간(CONFIRMED) · 원의 토요일 설정
    B. Core 실행 — DB 없이. 부모 월간은 메모리 저장소로 넘긴다
    C. 짧은 쓰기 — 중복을 다시 보고 저장 · commit. 동시 요청은 부분 유일 인덱스가 막는다

**여기에 생성 규칙이 없다.** 칸 · 근거 · 바깥놀이 후보는 p0-planning 이 정한다.

칸 편집 · 재생성 · 확정 · 이력(W5b)도 월간 §9-3 · §9-5 와 같은 세 단계다 — 다만 주간 Core 는
부모 월간으로 다시 검사하고 재생성 범위를 만들므로, A 에서 부모 월간도 읽어 메모리로 넘긴다.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak import timing
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.adapters.weekly_composition import (
    WEEKLY_DAY_TEMPLATE_REF,
    WEEKLY_TEMPLATE_REF,
    weekly_activities,
    weekly_confirmation,
    weekly_edit,
    weekly_generation,
    weekly_operating_days,
    weekly_regeneration,
)
from ssuksak.planning import (
    ConfirmWeeklyPlanCommand,
    EditWeeklyPlanCellCommand,
    GenerateWeeklyPlanCommand,
    InvalidDomainValueError,
    MonthlyApplicationError,
    MonthlyGenerationMode,
    MonthlyPlan,
    PlanId,
    RegenerateWeeklyPlanCellCommand,
    WeekId,
    WeeklyPlan,
)
from ssuksak.planning.application.weekly_lifecycle import (  # 공개 창구에 없다
    UnconfirmWeeklyPlan,
    UnconfirmWeeklyPlanCommand,
)
from ssuksak.planning.domain.identifiers import ItemId
from ssuksak.planning.domain.provenance import EvidenceSourceType, SplitAxis
from ssuksak.planning.domain.trend import TREND_CONTEXT
from ssuksak.planning.domain.weekly_plan import WEEKLY_INSTITUTION_INPUT_SECTION_KEYS

from app.config import settings
from app.db import get_session
from app.features.centers.models import Center
from app.features.evaluation.judge import today_kst
from app.features.plans.memo_privacy import (
    REGEN_MASK_FAILED,
    memo_name_table,
    raise_if_mask_failed,
    with_masked_memo,
)
from app.features.plans.models import Plan
from app.features.plans.monthly_llm import monthly_llm_provider
from app.features.plans.monthly_router import (
    _ALREADY_CONFIRMED,
    _CELL_NOT_FOUND,
    _CELL_NOT_REGENERATABLE,
    _REFERENCE_UNAVAILABLE,
    _STALE_WRITE,
    _UNAVAILABLE,
    _VALUE_INVALID,
    ACTIVITY_CATALOG,
    SAFETY_RULE,
    _actor,
    _cause_summary,
    _error,
    _gate,
    _generation,
    _is_play_monthly,
    _item_id,
    _lock_parent,
    _parent_changed,
    _target_month,
)
from app.features.plans.monthly_schemas import (
    ConstraintOut,
    EditMonthlyCell,
    FindingOut,
    GenerationChangeOut,
    RevisionIn,
    RuleRefOut,
    TemplateRefOut,
    ValueChangeOut,
    VerificationOut,
)
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import EvidenceOut, GenerationOut, memo_notices_out
from app.features.plans.weekly_schemas import (
    AddWeeklyIndoorPlayIn,
    CopyWeeklyActivityIn,
    CreateWeeklyPlan,
    OrderWeeklyIndoorPlayIn,
    ParentSnapshotOut,
    SplitWeeklyActivityIn,
    WeeklyActivityCandidateOut,
    WeeklyActivityGridOut,
    WeeklyAuditEventOut,
    WeeklyAuditOut,
    WeeklyCellOut,
    WeeklyParentOut,
    WeeklyPlanListOut,
    WeeklyPlanOut,
    WeeklyPlanSummary,
    WeeklySectionOut,
    WeekPeriodOut,
)
from app.features.trends.planning import TrendContextProvider, book_words_for
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import foreign_class_refs, require_own_class
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
    """mock 이면 요청 기반 결정적 provider. real 은 `weekly_llm_enabled` 가 켜졌을 때만 Luna-6.

    꺼져 있으면 503(결정 ②) — 실제 문장 품질을 본 적 없는 경로를 운영에 열지 않는다.
    켜지면 월간과 **같은 어댑터 · 같은 전송**이다(`generate_weekly`, W7a-1) — 키 · 주소 확인,
    오류 3종 분류, 호출마다 모델 · 시간 · 토큰 로그가 그대로 따라온다. 실패했다고 mock 으로
    갈아타지 않는다.
    """
    if is_mock():
        return RequestAwareWeeklyLlm()
    if not settings.weekly_llm_enabled:
        raise LlmUnavailable("주간 실제 LLM 은 WEEKLY_LLM_ENABLED 로 켠다 (W7)")
    return monthly_llm_provider()


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


_CANDIDATE_SECTIONS = frozenset({"group_activity", "indoor_play"})


def _prior_week_evidence(
    session: Session, center_id: int, class_id: int, week: WeekId
) -> tuple[str, ...]:
    """같은 반 · 같은 달 앞 주차 주간계획안이 후보 칸에 쓴 기관 근거.

    여러 주가 쓴 만큼 센다(2026-11-09 하민)."""
    rows = session.execute(
        select(Plan.plan_ref, Plan.week_id).where(
            Plan.center_id == center_id,
            Plan.kind == "weekly",
            Plan.classroom_ref == str(class_id),
            Plan.week_id.startswith(f"{week.target_month.value}-W"),
        )
    ).all()
    repo = _weekly_repo(session, center_id)
    refs: list[str] = []
    for plan_ref, week_value in rows:
        if WeekId(week_value).ordinal >= week.ordinal:
            continue
        plan = repo.get(PlanId(plan_ref))
        if plan is None:
            continue
        refs.extend(
            source.source_id
            for cell in plan.cells + tuple(c.cell for c in plan.activity_candidates)
            if cell.section_key in _CANDIDATE_SECTIONS
            for source in cell.evidence
            if source.source_type is EvidenceSourceType.INSTITUTION_SAMPLE
        )
    return tuple(refs)


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
        or error.code == "weekly_reference_context_unavailable"
    ):
        return _UNAVAILABLE
    if error.code in _WEEK_NOT_USABLE:
        return _WEEK_INVALID
    # LLM 호출이 깨졌다 · 수리 뒤에도 계약 위반 · 검증 실패 · 저장된 부모가 깨졌다. 저장 없음.
    return _error(
        500, "GENERATION_FAILED", "주간계획안을 만들지 못했습니다. 다시 시도해주세요.", []
    )


@router.post("", response_model=WeeklyPlanOut, status_code=status.HTTP_201_CREATED)
@timing.timed("weekly", logging.getLogger("app.server.timing").info)
def create_weekly_plan(body: CreateWeeklyPlan, session: DbSession, user: CurrentUser):
    """한 주치를 만들어 DRAFT 로 저장한다. 실패하면 아무것도 남지 않는다."""
    # ── A. 짧은 읽기 ──────────────────────────────────────────────────────
    klass = require_own_class(session, user, body.class_id)
    center_id, class_id = user.center_id, klass.id
    names = memo_name_table(session, class_id, body.memo)  # 못 바꾸면 LLM 전에 422(ADR-060)
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
    # 주간 Core 는 MonthlyPlan 만 부모로 받는다. 놀이 월간은 읽기 전에 막는다(ADR-046 §4).
    if _is_play_monthly(parent_row):
        raise _gate("놀이 중심 월간계획안 아래에서는 주간계획안을 만들 수 없습니다.")
    parent_id = parent_row.id
    parent = PostgresPlanRepository(
        session, center_id=center_id, kind="monthly", plan_type=MonthlyPlan
    ).get(PlanId(parent_row.plan_ref))
    if parent.status.value != "CONFIRMED":
        raise _gate("월간계획안을 먼저 확정해주세요.")
    prior_week_evidence = _prior_week_evidence(session, center_id, class_id, week)
    # 2026-11-10 하민: 후보 근거를 상위 20건에서 섞어 뽑는다. 다시 만들면 다른 근거가 나온다.
    # 실제로 쓴 근거는 칸 Evidence 에 남는다. seed 는 로그에만 둔다(저장 여부는 결정 전).
    candidate_seed = secrets.randbelow(2**31)
    # PR #469 review: log class · week here and the plan id after save, so a seed ties to one plan.
    _log.info("weekly candidate seed=%d class=%s week=%s", candidate_seed, class_id, body.week_id)
    # 만들 때의 원 설정을 계획안에 복사한다 — 뒤에 설정을 바꿔도 이 계획안은 그대로다(§3-5).
    center = session.get(Center, center_id)
    saturday = center.weekly_saturday_enabled
    # ADR-072: 원이 켠 경우에만 트렌드를 읽는다. 오늘 = 서버의 한국 날짜.
    # 그림책은 그 주 주제 낱말이 제목에 있는 것만(2026-11-10 보완).
    # 주 주제 = 부모 그 주 focus, 없으면 월 주제.
    week_theme = next(
        (
            cell.value
            for key in ("focus", "theme")
            if (section := parent.section(key)) is not None
            for cell in (section.cell_for_week(week), section.cell_for_week(None))
            if cell is not None and cell.value.strip()
        ),
        "",
    )
    trends = TrendContextProvider(
        enabled=center.trends_enabled,
        today=today_kst(datetime.now(UTC)),
        book_words=book_words_for(week_theme),
    )
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
        provider=with_masked_memo(provider, body.memo, names),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
        optional_context=trends,
    )
    try:
        result = use_case.execute(
            GenerateWeeklyPlanCommand(
                parent_monthly_plan_id=parent.plan_id,
                week_id=week,
                operating_days=weekly_operating_days(saturday),
                template_ref=WEEKLY_DAY_TEMPLATE_REF
                if body.activity_candidates or body.indoor_play_candidates
                else WEEKLY_TEMPLATE_REF,
                safety_rule=SAFETY_RULE,
                generation_mode=MonthlyGenerationMode.LLM_PLANNER,
                activity_catalog=ACTIVITY_CATALOG,
                activity_candidates=body.activity_candidates or body.indoor_play_candidates,
                indoor_play_candidates=body.indoor_play_candidates,
                teacher_memo=body.memo,
                optional_context_names=(TREND_CONTEXT,),
                prior_week_evidence=prior_week_evidence,
                candidate_sample_seed=candidate_seed,
            )
        )
    except MonthlyApplicationError as error:
        raise_if_mask_failed(error)
        _log.warning(
            "weekly generation failed code=%s cause=%s",
            error.code,
            type(error.__cause__).__name__ if error.__cause__ else "-",
        )
        raise _generation_error(error) from error
    plan = result.plan
    # 트렌드 상태 한 단어(AVAILABLE · UNAVAILABLE · ERROR). 제목 · 프롬프트는 남기지 않는다.
    _log.info(
        "weekly trend=%s",
        next((r.status.value for r in result.optional_context if r.name == TREND_CONTEXT), "-"),
    )

    # ── C. 짧은 쓰기 ──────────────────────────────────────────────────────
    timing.phase("save")
    _lock_parent(session, parent_id, "월간계획안을 먼저 만들어 확정해주세요.")
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
    _log.info("weekly candidate seed=%d plan=%s", candidate_seed, plan.plan_id.value)
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
        klass = require_own_class(session, user, class_id, read_only=True)
        query = query.where(Plan.classroom_ref == str(class_id))
        if month is not None:
            query = query.where(Plan.target_month == _target_month(klass.school_year, month).value)
    else:
        # 반을 안 짚은 목록은 내 반만 — 승인받은 반은 반을 짚어야 보인다.
        query = query.where(Plan.classroom_ref.not_in(foreign_class_refs(user)))
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
    return _current(session, user, plan_id)


def _current(session: Session, user, plan_id: int) -> WeeklyPlanOut:
    """지금 DB 에 저장된 그대로. 응답의 revision 도 행의 값이다.

    읽기 검사만 한다 — 쓰는 길은 모두 먼저 `_own_row`(쓰기 검사)를 지난 뒤 이걸 부른다.
    """
    row = _own_row(session, user, plan_id, read_only=True)
    plan = _weekly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    parent = session.scalar(
        select(Plan).where(
            Plan.plan_ref == plan.parent_lineage.parent_plan_id.value,
            Plan.center_id == user.center_id,
            Plan.kind == "monthly",
        )
    )
    changed = _parent_changed(parent, plan.parent_lineage.confirmed_at)
    return _detail(row, plan, None if parent is None else parent.id, parent_changed=changed)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weekly_plan(plan_id: int, session: DbSession, user: CurrentUser) -> Response:
    """주간계획안을 지운다(결정 ③). 월간과 같은 이유다 — 반 · 주당 하나라 만들기가
    409 로 막히므로, 지우기가 없으면 첫 초안이 마음에 안 들어도 그 주는 다시 못 만든다.

    **확정본도 지운다**(ADR-064, Human Decision 2026-11-05 하민). 화면의 확정 취소를 없앴다 —
    고치려면 문서 보관함에서 지우고 다시 만든다. 이력 · 근거는 본문 안에 있어 행과 함께 사라진다.
    """
    row = _own_row(session, user, plan_id)
    deleted = session.execute(
        delete(Plan).where(
            Plan.id == row.id, Plan.center_id == user.center_id, Plan.kind == "weekly"
        )
    ).rowcount
    if not deleted:  # 그 사이 사라졌다
        raise _NOT_FOUND
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _own_row(session: Session, user, plan_id: int, *, read_only: bool = False) -> Plan:
    """이 원의 주간 행. 조건부 UPDATE 뒤에도 DB 값을 다시 읽는다(populate_existing).

    남의 반 계획안이면 반 검사를 거친다(ADR-059). 기본이 쓰기다 — 읽기만 `read_only=True`.
    """
    row = session.scalar(
        select(Plan)
        .where(Plan.id == plan_id, Plan.center_id == user.center_id, Plan.kind == "weekly")
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise _NOT_FOUND
    require_own_class(session, user, int(row.classroom_ref), read_only=read_only)
    return row


def _activity_grid(node) -> WeeklyActivityGridOut:
    return WeeklyActivityGridOut(
        cell_id=None if node.cell is None else node.cell.value,
        split_id=None if node.split_id is None else node.split_id.value,
        axis=None if node.axis is None else node.axis.value,
        ratio=node.ratio,
        children=[_activity_grid(c) for c in node.children],
    )


def _detail(
    row: Plan, plan: WeeklyPlan, parent_id: int, *, parent_changed: bool = False
) -> WeeklyPlanOut:
    """도메인 객체를 계약 형식으로. 칸 순서는 Core 가 정한 Template 순서 그대로다.

    `revision` 은 DB 행의 값이다. **`safety`(배치 정보)는 내지 않는다** — 월간도 내지 않는다.
    """
    period = plan.week_period
    report = plan.verification_report
    saturday = plan.operating_days[-1].value == "SAT"
    return WeeklyPlanOut(
        id=row.id,
        memo=plan.teacher_memo,
        memo_notices=memo_notices_out(plan),
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
        parent_changed=parent_changed,
        sections=[
            WeeklySectionOut(
                section_key=section.section_key,
                label=section.display_label,
                role=section.role.value,
                repeat_by=section.repeat_by.value,
                visible=section.visible,
                order=section.order,
                semantic_variant=(
                    None if section.semantic_variant is None else section.semantic_variant.value
                ),
                cells=[_cell(c) for c in plan.cells if c.section_key == section.section_key],
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
        activity_candidates=[
            WeeklyActivityCandidateOut(
                section_key=c.cell.section_key,
                activity_type=c.activity_type,
                name=c.name,
                description=c.description,
                trend_applied=any(
                    s.source_type is EvidenceSourceType.TREND for s in c.cell.evidence
                ),
                cell=_cell(c.cell),
            )
            for c in plan.activity_candidates
        ],
        activity_grids=[_activity_grid(g) for g in plan.activity_grids],
        indoor_play_selection=plan.indoor_play_selection,
    )


def _cell(cell) -> WeeklyCellOut:
    generation = cell.generation
    return WeeklyCellOut(
        item_id=cell.item_id.value,
        day=None if cell.day is None else cell.day.value,
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
        teacher_input=cell.section_key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS,
    )


# ── 편집 · 재생성 · 확정 · 이력 (§9-6, W5b) ─────────────────────────────────

# Core 가 「이 칸은 다시 만들 수 없다」고 하는 경우들(월간 `_NOT_REGENERATABLE_CODES` 와 같은 묶음).
_NOT_REGENERATABLE_CODES = frozenset(
    {
        "weekly_cell_not_regeneratable",
        "rule_only_regeneration_unsupported",
        "weekly_cell_evidence_missing",
        "activity_catalog_required",
        "no_activity_candidate",
    }
)


#: 정상 경로에 없는 서버 버그(계약 위반). 생성 실패가 아니다 — 처리하지 않고 다시 던져
#: C2 공통 처리(500 `INTERNAL_ERROR`, 원문 비노출)로 보낸다(계획 §13-2 · Codex W5b-02).
_SERVER_BUG_CODES = frozenset({"opaque_actor_required", "repository_contract_violation"})


def _lifecycle_error(error: MonthlyApplicationError) -> HTTPException:
    if error.code in _SERVER_BUG_CODES:
        raise error
    if error.code in {"weekly_cell_not_found", "invalid_item_id"}:
        return _CELL_NOT_FOUND
    if error.code in {
        "weekly_cell_value_unchanged",
        "invalid_weekly_cell_value",
        "weekly_activity_candidate_invalid",
        "weekly_activity_layout_invalid",
    }:
        return _VALUE_INVALID
    if error.code in _NOT_REGENERATABLE_CODES:
        return _CELL_NOT_REGENERATABLE
    if error.code == "weekly_verification_failed":
        # 검사 「결과」는 막지 않는다. 검사기가 돌지 못한 것만 여기로 온다.
        return _error(
            500, "GENERATION_FAILED", "검증을 실행하지 못했습니다. 다시 시도해주세요.", []
        )
    # LLM · 수리 실패 · 안전 근거 오류 · 저장된 부모가 사라짐 → 500. 예산 · real → 503.
    return _generation_error(error)


def _with_parent(session: Session, user, row: Plan) -> tuple[WeeklyPlan, MonthlyPlan | None]:
    """부모 월간이 사라졌으면 None — Core 가 `parent_monthly_plan_not_found` 로 거절한다."""
    plan = _weekly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    parent = PostgresPlanRepository(
        session, center_id=user.center_id, kind="monthly", plan_type=MonthlyPlan
    ).get(plan.parent_lineage.parent_plan_id)
    return plan, parent


def _read_draft(
    session: Session, user, plan_id: int, expected_revision: int
) -> tuple[WeeklyPlan, MonthlyPlan | None]:
    """A. 짧은 읽기 — 확정 여부 · revision 을 보고 주간과 부모 월간을 들고 transaction 을 끝낸다."""
    row = _own_row(session, user, plan_id)
    if row.status == "CONFIRMED":
        raise _ALREADY_CONFIRMED
    if row.revision != expected_revision:
        raise _STALE_WRITE
    plan, parent = _with_parent(session, user, row)
    session.commit()
    return plan, parent


def _repos(plan: WeeklyPlan, parent: MonthlyPlan | None) -> dict:
    """B. Core 가 읽고 쓰는 메모리 저장소. DB 는 C 가 쓴다."""
    drafts: InMemoryPlanRepository[WeeklyPlan] = InMemoryPlanRepository()
    drafts.save(plan.plan_id, plan)
    parents: InMemoryPlanRepository[MonthlyPlan] = InMemoryPlanRepository()
    if parent is not None:
        parents.save(parent.plan_id, parent)
    return {"plan_repository": drafts, "parent_plan_repository": parents, "clock": SystemClock()}


def _write(
    session: Session,
    user,
    plan_id: int,
    changed: WeeklyPlan,
    expected_revision: int,
    *,
    confirming: bool = False,
) -> WeeklyPlanOut:
    """C. 조건부 쓰기. 못 썼으면 다시 읽어 왜인지 가른다(월간 `_write` 와 같다)."""
    written = _weekly_repo(session, user.center_id).update_if_revision(
        changed.plan_id, changed, expected_revision=expected_revision
    )
    if written is None:
        session.rollback()
        row = _own_row(session, user, plan_id)
        if row.status == "CONFIRMED":
            if confirming:  # 누가 먼저 확정했다 — 확정 재호출과 같다
                return _current(session, user, plan_id)
            raise _ALREADY_CONFIRMED
        raise _STALE_WRITE
    detail = _current(session, user, plan_id)
    session.commit()
    return detail


@router.put("/{plan_id}/cells/{item_id}", response_model=WeeklyPlanOut)
def edit_weekly_cell(
    plan_id: int, item_id: str, body: EditMonthlyCell, session: DbSession, user: CurrentUser
):
    """칸 하나를 교사가 고친다. 교사 입력 칸은 첫 입력에 MANUAL, 그 밖은 `TEACHER_EDITED`."""
    plan, parent = _read_draft(session, user, plan_id, body.expected_revision)
    try:
        changed = weekly_edit(**_repos(plan, parent)).execute(
            EditWeeklyPlanCellCommand(plan.plan_id, _item_id(item_id), body.value, _actor(user))
        )
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.post("/{plan_id}/cells/{item_id}/copy-activity", response_model=WeeklyPlanOut)
def copy_weekly_activity(
    plan_id: int, item_id: str, body: CopyWeeklyActivityIn, session: DbSession, user: CurrentUser
):
    plan, parent = _read_draft(session, user, plan_id, body.expected_revision)
    try:
        changed = weekly_activities(**_repos(plan, parent), id_generator=UuidGenerator()).copy(
            plan.plan_id, _item_id(item_id), _item_id(body.candidate_item_id), _actor(user)
        )
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    if changed is plan:
        return _current(session, user, plan_id)
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.post("/{plan_id}/indoor-plays", response_model=WeeklyPlanOut)
def add_weekly_indoor_play(
    plan_id: int, body: AddWeeklyIndoorPlayIn, session: DbSession, user: CurrentUser
):
    plan, parent = _read_draft(session, user, plan_id, body.expected_revision)
    try:
        candidate = None if body.candidate_item_id is None else ItemId(body.candidate_item_id)
        changed = weekly_activities(
            **_repos(plan, parent), id_generator=UuidGenerator()
        ).add_indoor(plan.plan_id, candidate, _actor(user))
    except InvalidDomainValueError as error:
        raise _VALUE_INVALID from error
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    if changed is plan:
        return _current(session, user, plan_id)
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.put("/{plan_id}/indoor-plays/order", response_model=WeeklyPlanOut)
def order_weekly_indoor_plays(
    plan_id: int, body: OrderWeeklyIndoorPlayIn, session: DbSession, user: CurrentUser
):
    plan, parent = _read_draft(session, user, plan_id, body.expected_revision)
    try:
        changed = weekly_activities(
            **_repos(plan, parent), id_generator=UuidGenerator()
        ).order_indoor(plan.plan_id, tuple(ItemId(value) for value in body.item_ids), _actor(user))
    except InvalidDomainValueError as error:
        raise _VALUE_INVALID from error
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    if changed is plan:
        return _current(session, user, plan_id)
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.delete("/{plan_id}/indoor-plays/{item_id}", response_model=WeeklyPlanOut)
def remove_weekly_indoor_play(
    plan_id: int,
    item_id: str,
    session: DbSession,
    user: CurrentUser,
    expected_revision: Annotated[int, Query(ge=1)],
):
    plan, parent = _read_draft(session, user, plan_id, expected_revision)
    try:
        changed = weekly_activities(
            **_repos(plan, parent), id_generator=UuidGenerator()
        ).remove_indoor(plan.plan_id, _item_id(item_id), _actor(user))
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, expected_revision)


@router.post("/{plan_id}/cells/{item_id}/split", response_model=WeeklyPlanOut)
def split_weekly_activity(
    plan_id: int, item_id: str, body: SplitWeeklyActivityIn, session: DbSession, user: CurrentUser
):
    plan, parent = _read_draft(session, user, plan_id, body.expected_revision)
    try:
        changed = weekly_activities(**_repos(plan, parent), id_generator=UuidGenerator()).split(
            plan.plan_id,
            _item_id(item_id),
            _actor(user),
            axis=SplitAxis(body.axis),
            ratio=body.ratio,
        )
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.delete("/{plan_id}/cells/{item_id}/split", response_model=WeeklyPlanOut)
def remove_weekly_activity_cell(
    plan_id: int,
    item_id: str,
    session: DbSession,
    user: CurrentUser,
    expected_revision: Annotated[int, Query(ge=1)],
):
    plan, parent = _read_draft(session, user, plan_id, expected_revision)
    try:
        changed = weekly_activities(**_repos(plan, parent), id_generator=UuidGenerator()).remove(
            plan.plan_id, _item_id(item_id), _actor(user)
        )
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, expected_revision)


@router.post("/{plan_id}/cells/{item_id}/regenerate", response_model=WeeklyPlanOut)
def regenerate_weekly_cell(
    plan_id: int, item_id: str, body: RevisionIn, session: DbSession, user: CurrentUser
):
    """그 칸만 다시 만든다. LLM 을 기다리는 동안 transaction 이 없다 — 그 사이 누가
    고쳤으면 결과를 버리고 409 다."""
    plan, parent = _read_draft(session, user, plan_id, body.expected_revision)
    if plan.indoor_play_selection:
        target = plan.find_cell(_item_id(item_id))
        if target is not None and target.section_key == "indoor_play":
            raise _CELL_NOT_REGENERATABLE
    # 칸 프롬프트에는 저장된 요청 사항과 이 계획안의 다른 칸 값(current_plan · 교사가 고친 값
    # 포함)이 실린다. 둘 다 생성과 같이 가린다(ADR-060).
    # Core 가 싣는 칸만 넣는다 — 다시 만들 칸 자신은 빠진다(weekly_lifecycle `current_values`).
    target_id = _item_id(item_id)
    cells = tuple(
        cell.value for cell in plan.cells if cell.item_id != target_id and cell.value.strip()
    )
    seen = "\n".join((plan.teacher_memo or "", *cells))
    names = memo_name_table(session, int(plan.classroom_ref), seen, REGEN_MASK_FAILED)
    session.commit()  # 이름표 읽기까지 끝낸다. LLM 을 기다리는 동안 transaction 을 잡지 않는다
    try:
        provider = with_masked_memo(_weekly_provider(), plan.teacher_memo, names, cells)
    except LlmUnavailable as error:
        raise _UNAVAILABLE from error
    try:
        changed = weekly_regeneration(provider=provider, **_repos(plan, parent)).execute(
            RegenerateWeeklyPlanCellCommand(plan.plan_id, _item_id(item_id), _actor(user))
        )
    except MonthlyApplicationError as error:
        raise_if_mask_failed(error, REGEN_MASK_FAILED)
        _log.warning(
            "weekly cell regeneration failed code=%s stage=%s cause=%s validation_codes=%s",
            error.code,
            *_cause_summary(error),
        )
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.post("/{plan_id}/confirm", response_model=WeeklyPlanOut)
def confirm_weekly_plan(plan_id: int, body: RevisionIn, session: DbSession, user: CurrentUser):
    """DRAFT → CONFIRMED. **제출 · 발송은 하지 않는다.**

    이미 확정이면 revision 과 무관하게 200 이고 아무것도 쓰지 않는다(월간과 같다).
    검사 결과로 막지 않는다(주간 계약 §11-2).
    """
    row = _own_row(session, user, plan_id)
    if row.status == "CONFIRMED":
        return _current(session, user, plan_id)
    if row.revision != body.expected_revision:
        raise _STALE_WRITE
    plan, parent = _with_parent(session, user, row)
    session.commit()
    try:
        changed = weekly_confirmation(**_repos(plan, parent)).execute(
            ConfirmWeeklyPlanCommand(plan.plan_id, _actor(user))
        )
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, body.expected_revision, confirming=True)


@router.post("/{plan_id}/unconfirm", response_model=WeeklyPlanOut)
def unconfirm_weekly_plan(plan_id: int, body: RevisionIn, session: DbSession, user: CurrentUser):
    """CONFIRMED → DRAFT. 값 · 근거 · 이력은 그대로 두고 계획안 단위 `UNCONFIRMED` 를 남긴다.

    이미 DRAFT 면 revision 과 무관하게 200 이고 아무것도 쓰지 않는다(월간과 같다).
    """
    row = _own_row(session, user, plan_id)
    if row.status != "CONFIRMED":
        return _current(session, user, plan_id)
    if row.revision != body.expected_revision:
        raise _STALE_WRITE
    plan = _weekly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    session.commit()
    changed = UnconfirmWeeklyPlan(**_repos(plan, None)).execute(
        UnconfirmWeeklyPlanCommand(plan.plan_id, _actor(user))
    )
    written = _weekly_repo(session, user.center_id).update_if_revision(
        changed.plan_id, changed, expected_revision=body.expected_revision, status="CONFIRMED"
    )
    if written is None:
        session.rollback()
        if _own_row(session, user, plan_id).status == "CONFIRMED":
            raise _STALE_WRITE
        # 누가 먼저 풀었다 — 이미 DRAFT 일 때와 같다
    detail = _current(session, user, plan_id)
    session.commit()
    return detail


@router.get("/{plan_id}/audit", response_model=WeeklyAuditOut)
def get_weekly_audit(
    plan_id: int, session: DbSession, user: CurrentUser, item_id: str | None = None
):
    """저장된 변경 이력. 월간 §9-5 와 같은 모양 · 순서 · `item_id` 거르기.

    주간 칸에는 주가 따로 없다 — 칸 이벤트의 `week_id` 는 계획안의 주다. 교사 입력 칸의 첫
    `MANUAL` 은 이벤트가 아니라 칸 `generation` 으로 보인다(W4 결정 ②).
    """
    row = _own_row(session, user, plan_id, read_only=True)
    plan = _weekly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    cells = (
        list(plan.cells)
        + [c.cell for c in plan.activity_candidates]
        + list(plan.removed_activity_cells)
    )
    if item_id is not None:
        cells = [c for c in cells if c.item_id.value == item_id]
        if not cells:
            raise _CELL_NOT_FOUND
    keyed = [
        ((event.occurred_at, 0, 0, index), _audit_event(event, None, None))
        for index, event in enumerate(plan.audit.events)
        if item_id is None or event.event_type.value in ("CONFIRMED", "UNCONFIRMED")
    ]
    for position, cell in enumerate(cells):
        keyed += [
            ((event.occurred_at, 1, position, index), _audit_event(event, cell, plan.week_id))
            for index, event in enumerate(cell.audit.events)
        ]
    keyed.sort(key=lambda pair: pair[0])
    return WeeklyAuditOut(items=[out for _, out in keyed])


def _audit_event(event, cell, week: WeekId | None) -> WeeklyAuditEventOut:
    change = event.timetable_change
    return WeeklyAuditEventOut(
        type=event.event_type.value,
        occurred_at=event.occurred_at,
        scope="PLAN" if cell is None else "CELL",
        item_id=None if cell is None else cell.item_id.value,
        section_key=None if cell is None else cell.section_key,
        week_id=None if week is None else week.value,
        day=None if cell is None or cell.day is None else cell.day.value,
        copied_from=None if event.copied_from is None else event.copied_from.value,
        timetable_change=None
        if change is None
        else {
            "operation": change.operation.value,
            "split_id": change.split_id.value,
            "axis": change.axis.value,
            "cell_id": change.cell_id.value,
            "new_cell_id": None if change.new_cell_id is None else change.new_cell_id.value,
        },
        actor=None if event.actor_id is None else event.actor_id.value,
        system_actor=event.system_actor,
        value_change=(
            None
            if event.value_change is None
            else ValueChangeOut(before=event.value_change.before, after=event.value_change.after)
        ),
        generation_change=(
            None
            if event.generation_change is None
            else GenerationChangeOut(
                before=_generation(event.generation_change.before),
                after=_generation(event.generation_change.after),
            )
        ),
        arrangement_change=None
        if event.arrangement_change is None
        else {
            "scope": event.arrangement_change.scope,
            "before": list(event.arrangement_change.before),
            "after": list(event.arrangement_change.after),
        },
    )
