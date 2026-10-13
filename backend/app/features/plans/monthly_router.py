"""월간계획안 생성 · 조회 · 칸 편집 · 칸 재생성 · 확정 API.

계약은 docs/api-spec.md §9-1 · §9-3 이다.

**여기에 생성 규칙이 없다.** 주제 · 주 · 칸 · 근거는 전부 p0-planning 이 정한다. 이 파일은
HTTP 요청을 Core 명령으로 바꾸고, 돌아온 도메인 객체를 계약 형식으로 옮기고, 저장 시점을 정한다.

**LLM 을 기다리는 동안 DB 를 잡지 않는다**(결정 문서 12.9). 생성은 세 단계다.

    A. 짧은 읽기 — 반 소유 · 중복 · 부모 연간(CONFIRMED) · READY Profile 을 읽고 끝낸다
    B. Core 실행 — DB 없이. 부모 · Profile 은 메모리 저장소로 넘기고 저장도 메모리가 받는다
    C. 짧은 쓰기 — 중복을 다시 보고 Postgres 에 저장 · commit

부모 CONFIRMED 와 READY 는 바뀌지 않는 값이라 A 와 C 사이에 달라지지 않는다. 같은 반 · 같은
달 동시 요청은 C 의 부분 유일 인덱스가 최종으로 막는다.

**편집 · 재생성 · 확정도 같은 세 단계다**(결정 문서 12.10). 다른 점은 C 가 조건부 UPDATE 라는
것 — 읽은 `expected_revision` 과 DRAFT 를 한 문장으로 보고 +1 한다. 그 사이 누가 바꿨으면
저장하지 않고 409 다. 재생성 결과가 아무리 그럴듯해도 옛 계획안 위에 덮어쓰지 않는다.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.in_memory_template_profile_repository import (
    InMemoryTemplateProfileRepository,
)
from ssuksak.adapters.monthly_composition import (
    monthly_confirmation,
    monthly_edit,
    monthly_generation,
    monthly_regeneration,
)
from ssuksak.planning import (
    ActivityCatalogSelector,
    ActorId,
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    InvalidDomainValueError,
    ItemId,
    MonthlyApplicationError,
    MonthlyGenerationMode,
    MonthlyPlan,
    PlanId,
    RegenerateMonthlyPlanItemCommand,
    SafetyRuleSelector,
    TemplateProfileRef,
    YearlyPlan,
    YearMonth,
)

from app.db import get_session
from app.features.plans.models import Plan
from app.features.plans.monthly_llm import monthly_llm_provider
from app.features.plans.monthly_schemas import (
    CellOut,
    ConstraintOut,
    CreateMonthlyPlan,
    EditMonthlyCell,
    FindingOut,
    MonthlyPlanListOut,
    MonthlyPlanOut,
    MonthlyPlanSummary,
    ParentOut,
    ProfileRefOut,
    RevisionIn,
    RuleRefOut,
    SectionOut,
    TemplateRefOut,
    VerificationOut,
    WeekOut,
)
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import EvidenceOut, GenerationOut
from app.features.template_profiles import service as profile_service
from app.features.template_profiles.repository import TemplateProfileError
from app.features.template_profiles.service import ready_profile_for_generation
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/plans/monthly", tags=["plans"])

DbSession = Annotated[Session, Depends(get_session)]

# 어떤 판의 참조자료를 쓰는지. 계획안의 근거에 박혀 저장되므로 새 판으로 올릴 때 여기만 바꾼다.
ACTIVITY_CATALOG = ActivityCatalogSelector(
    "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
)
SAFETY_RULE = SafetyRuleSelector("child-welfare-act-decree-annex6-2022-06-21")
# 월간은 반 · 월당 하나다(결정 문서 12.5). 이 이름의 충돌만 409 로 바꾼다.
MONTHLY_UNIQUE = "uq_plans_monthly_per_classroom_month"

# Core 오류를 계약 코드로 가른다. **Core 코드를 그대로 내보내지 않는다**(CLAUDE.md §20).
# 고른 Profile 로는 만들 수 없다 — 재시도해도 같다. 다른 Profile 을 고른다.
_PROFILE_UNUSABLE = frozenset(
    {
        "monthly_institution_input_section_unsupported",
        "monthly_required_section_evidence_missing",
        "monthly_section_evidence_class_unavailable",
        "monthly_section_generation_policy_unsupported",
        # Core 최종 승인 검사(ADR-027). 보통은 생성 직전 검사가 먼저 막는다 — 같은 422 다.
        "monthly_template_not_found",
        "monthly_template_not_approved",
    }
)
# 서버의 승인 참조자료를 쓸 수 없다 — 운영 문의.
_REFERENCE_UNAVAILABLE = frozenset(
    {
        "activity_catalog_not_found",
        "activity_catalog_not_approved",
        "safety_rule_not_found",
        "safety_rule_not_approved",
        "evidence_classification_store_mismatch",
    }
)


def _error(code: int, error_code: str, message: str, fields: list[str]) -> HTTPException:
    return HTTPException(code, detail={"code": error_code, "message": message, "fields": fields})


_NOT_FOUND = _error(404, "NOT_FOUND", "월간계획안을 찾을 수 없습니다.", ["id"])
_ALREADY_EXISTS = _error(
    409, "ALREADY_EXISTS", "이 반의 그 달 월간계획안이 이미 있습니다.", ["class_id", "month"]
)
_PROFILE_NOT_FOUND = _error(404, "NOT_FOUND", "고른 양식 설정을 찾을 수 없습니다.", ["profile_ref"])
_PROFILE_UNUSABLE_ERROR = _error(
    422,
    "VALIDATION_FAILED",
    "고른 양식 설정으로는 월간계획안을 만들 수 없습니다. 다른 설정을 골라주세요.",
    ["profile_ref"],
)
_UNAVAILABLE = _error(
    503,
    "DEPENDENCY_UNAVAILABLE",
    "계획안 생성 기능을 지금 쓸 수 없습니다. 운영에 문의해주세요.",
    [],
)


def _monthly_repo(session: Session, center_id: int) -> PostgresPlanRepository[MonthlyPlan]:
    return PostgresPlanRepository(
        session, center_id=center_id, kind="monthly", plan_type=MonthlyPlan
    )


def _target_month(school_year: int, month: int) -> YearMonth:
    """3~12월은 그 학년도, 1~2월은 다음 해다(학년도는 3월에 바뀐다)."""
    return YearMonth(school_year if month >= 3 else school_year + 1, month)


def _existing(session: Session, center_id: int, class_id: int, month: YearMonth):
    return session.scalar(
        select(Plan.id).where(
            Plan.center_id == center_id,
            Plan.kind == "monthly",
            Plan.classroom_ref == str(class_id),
            Plan.target_month == month.value,
        )
    )


def _generation_error(error: MonthlyApplicationError) -> HTTPException:
    """원인은 `__cause__` 에 있다 — Core 가 provider 오류를 자기 것으로 감싼다(연간과 같다)."""
    cause = error.__cause__
    if isinstance(cause, LlmBudgetExceeded):
        return _error(
            503, "LLM_BUDGET_EXCEEDED", "생성 한도에 걸렸습니다. 운영에 문의해주세요.", []
        )
    if isinstance(cause, LlmUnavailable) or error.code in _REFERENCE_UNAVAILABLE:
        return _UNAVAILABLE
    if error.code in _PROFILE_UNUSABLE:
        return _PROFILE_UNUSABLE_ERROR
    if error.code == "monthly_template_profile_not_found":
        return _PROFILE_NOT_FOUND
    # LLM 호출이 깨졌다(타임아웃 포함) · 수리 뒤에도 계약 위반 · Core 검증 실패. 재시도할 수 있다.
    return _error(
        500, "GENERATION_FAILED", "월간계획안을 만들지 못했습니다. 다시 시도해주세요.", []
    )


def _gate(message: str) -> HTTPException:
    return _error(409, "GATE_BLOCKED", message, ["class_id"])


@router.post("", response_model=MonthlyPlanOut, status_code=status.HTTP_201_CREATED)
def create_monthly_plan(body: CreateMonthlyPlan, session: DbSession, user: CurrentUser):
    """한 달치를 만들어 DRAFT 로 저장한다. 실패하면 아무것도 남지 않는다."""
    # ── A. 짧은 읽기 ──────────────────────────────────────────────────────
    klass = require_own_class(session, user, body.class_id)
    center_id, class_id = user.center_id, klass.id
    month = _target_month(klass.school_year, body.month)
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
    parent_id = parent_row.id
    parent = PostgresPlanRepository(
        session, center_id=center_id, kind="annual", plan_type=YearlyPlan
    ).get(PlanId(parent_row.plan_ref))
    if parent.status.value != "CONFIRMED":
        raise _gate("연간계획안을 먼저 확정해주세요.")
    try:
        profile_ref = TemplateProfileRef(
            body.profile_ref.profile_id, body.profile_ref.profile_version
        )
        profile = ready_profile_for_generation(session, center_id, profile_ref)
    except InvalidDomainValueError as error:
        raise _error(422, "VALIDATION_FAILED", str(error), ["profile_ref"]) from error
    except TemplateProfileError as error:
        if error.code == "NOT_FOUND":
            raise _PROFILE_NOT_FOUND from error
        raise _PROFILE_UNUSABLE_ERROR from error
    try:
        provider = monthly_llm_provider()
    except LlmUnavailable as error:
        raise _UNAVAILABLE from error
    # 읽기를 여기서 끝낸다. LLM 을 기다리는 동안 transaction · 연결을 잡지 않는다.
    session.commit()

    # ── B. Core 실행 — DB 없음 ────────────────────────────────────────────
    parents: InMemoryPlanRepository[YearlyPlan] = InMemoryPlanRepository()
    parents.save(parent.plan_id, parent)
    use_case = monthly_generation(
        parent_plan_repository=parents,
        # Core 의 plans.save 는 여기로 간다. 운영 저장은 C 에서 한다.
        plan_repository=InMemoryPlanRepository(),
        profile_repository=InMemoryTemplateProfileRepository((profile,)),
        # 생성 직전 검사와 같은 Template 저장소. 부를 때 읽는다 — 테스트가 바꿔 끼운다.
        template_repository=profile_service.TEMPLATES,
        provider=provider,
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )
    try:
        plan = use_case.execute(
            GenerateMonthlyPlanCommand(
                parent_yearly_plan_id=parent.plan_id,
                target_month=month,
                daycare_ref=str(center_id),
                profile_ref=profile_ref,
                safety_rule=SAFETY_RULE,
                generation_mode=MonthlyGenerationMode.LLM_PLANNER,
                activity_catalog=ACTIVITY_CATALOG,
                # D-M4-03: 배치 정책을 넘기지 않는다 — 안전교육은 「근거 필요」 경로다.
            )
        ).plan
    except MonthlyApplicationError as error:
        _log.warning("monthly generation failed code=%s", error.code)
        raise _generation_error(error) from error

    # ── C. 짧은 쓰기 ──────────────────────────────────────────────────────
    if _existing(session, center_id, class_id, month) is not None:
        raise _ALREADY_EXISTS
    try:
        _monthly_repo(session, center_id).save(plan.plan_id, plan)
    except IntegrityError as error:
        session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == MONTHLY_UNIQUE:
            raise _ALREADY_EXISTS from error
        raise
    row = session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))
    # **응답을 다 만든 뒤에 확정한다**(연간과 같다). 저장소가 flush 해 두어 commit 전에도 읽힌다.
    detail = _detail(row, plan, parent_id)
    session.commit()
    return detail


@router.get("", response_model=MonthlyPlanListOut)
def list_monthly_plans(session: DbSession, user: CurrentUser, class_id: int | None = None):
    """요약만 담는다. 칸은 단건이 준다. 대상 달 오름차순."""
    query = select(Plan).where(Plan.center_id == user.center_id, Plan.kind == "monthly")
    if class_id is not None:
        require_own_class(session, user, class_id)
        query = query.where(Plan.classroom_ref == str(class_id))
    rows = session.scalars(query.order_by(Plan.target_month, Plan.id)).all()
    return MonthlyPlanListOut(
        items=[
            MonthlyPlanSummary(
                id=row.id,
                class_id=int(row.classroom_ref),
                school_year=row.school_year,
                month=int(row.target_month[5:]),
                target_month=row.target_month,
                status=row.status,
                revision=row.revision,
                # 목록은 본문 전체를 되돌리지 않는다 — Snapshot 의 ref 만 읽는다.
                profile_ref=ProfileRefOut(**row.body["template_snapshot"]["profile_ref"]),
                created_at=row.created_at,
                confirmed_at=row.confirmed_at,
            )
            for row in rows
        ]
    )


@router.get("/{plan_id}", response_model=MonthlyPlanOut)
def get_monthly_plan(plan_id: int, session: DbSession, user: CurrentUser):
    """남의 원 것 · 월간이 아닌 것은 없는 것과 같다."""
    return _current(session, user, plan_id)


def _own_row(session: Session, user, plan_id: int) -> Plan:
    """이 원의 월간 행. 조건부 UPDATE 뒤에도 DB 값을 다시 읽는다(populate_existing)."""
    row = session.scalar(
        select(Plan)
        .where(Plan.id == plan_id, Plan.center_id == user.center_id, Plan.kind == "monthly")
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise _NOT_FOUND
    return row


def _current(session: Session, user, plan_id: int) -> MonthlyPlanOut:
    """지금 DB 에 저장된 그대로. 응답의 revision 도 행의 값이다."""
    row = _own_row(session, user, plan_id)
    plan = _monthly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    parent_id = session.scalar(
        select(Plan.id).where(
            Plan.plan_ref == plan.parent_lineage.parent_plan_id.value,
            Plan.center_id == user.center_id,
            Plan.kind == "annual",
        )
    )
    return _detail(row, plan, parent_id)


# ── 편집 · 재생성 · 확정 (§9-3) ────────────────────────────────────────────

_ALREADY_CONFIRMED = _error(409, "ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.", [])
_STALE_WRITE = _error(
    409,
    "STALE_WRITE",
    "그 사이 다른 화면에서 계획안이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.",
    ["expected_revision"],
)
_CELL_NOT_FOUND = _error(404, "NOT_FOUND", "그 칸을 찾을 수 없습니다.", ["item_id"])
_VALUE_INVALID = _error(
    422, "VALIDATION_FAILED", "칸의 값이 바뀌지 않았거나 쓸 수 없는 값입니다.", ["value"]
)
_CELL_NOT_REGENERATABLE = _error(
    422, "VALIDATION_FAILED", "이 칸은 다시 만들 수 없습니다.", ["item_id"]
)
# Core 가 「이 칸은 다시 만들 수 없다」고 하는 경우들. 규칙은 Core 것이다 — 여기서 늘리지 않는다.
_NOT_REGENERATABLE_CODES = frozenset(
    {
        "monthly_cell_not_regeneratable",
        "rule_only_focus_regeneration_unsupported",
        "activity_catalog_required",
        "monthly_required_section_evidence_missing",
        "no_activity_candidate",
        "monthly_cell_generation_missing",
        "monthly_theme_cell_required",
    }
)


def _lifecycle_error(error: MonthlyApplicationError) -> HTTPException:
    if error.code == "monthly_cell_not_found":
        return _CELL_NOT_FOUND
    if error.code in {"monthly_cell_value_unchanged", "invalid_monthly_cell_value"}:
        return _VALUE_INVALID
    if error.code in _NOT_REGENERATABLE_CODES:
        return _CELL_NOT_REGENERATABLE
    if error.code == "monthly_verification_failed":
        # 검증 「결과」는 막지 않는다. 검증기가 돌지 못한 것만 여기로 온다.
        return _error(
            500, "GENERATION_FAILED", "검증을 실행하지 못했습니다. 다시 시도해주세요.", []
        )
    return _generation_error(error)


def _cause_summary(error: MonthlyApplicationError) -> tuple[str, str, str]:
    """(단계, 원인 예외 이름, 검증 코드) — 로그에 남겨도 되는 것만.

    Core 는 칸 거절 사유를 `__cause__` 에 둔다(`ProposalRejectedError.validation_codes`). 코드는
    고정 Enum 이름이다. **예외 메시지 · issue detail · 응답 본문 · 프롬프트는 남기지 않는다.**
    """
    cause = error.__cause__
    if cause is None:
        return "core", "-", "-"
    codes = getattr(cause, "validation_codes", None)
    if isinstance(codes, tuple) and all(isinstance(code, str) for code in codes):
        return "validation", type(cause).__name__, ",".join(codes) or "-"
    if isinstance(cause, (LlmBudgetExceeded, LlmFailed, LlmUnavailable)) or (
        type(cause).__name__ == "MonthlyLlmProviderError"  # Core 어댑터의 응답 모양 오류
    ):
        return "provider", type(cause).__name__, "-"
    stage = "parse" if type(cause).__name__ == "ProposalParseError" else "core"
    return stage, type(cause).__name__, "-"


def _actor(user) -> ActorId:
    return ActorId(f"user_{user.id}")


def _item_id(value: str) -> ItemId:
    try:
        return ItemId(value)
    except InvalidDomainValueError as error:
        raise _CELL_NOT_FOUND from error


def _read_draft(session: Session, user, plan_id: int, expected_revision: int) -> MonthlyPlan:
    """A. 짧은 읽기 — 확정 여부 · revision 을 보고 도메인 객체를 들고 transaction 을 끝낸다."""
    row = _own_row(session, user, plan_id)
    if row.status == "CONFIRMED":
        raise _ALREADY_CONFIRMED
    if row.revision != expected_revision:
        raise _STALE_WRITE
    plan = _monthly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    session.commit()
    return plan


def _drafts(plan: MonthlyPlan) -> InMemoryPlanRepository[MonthlyPlan]:
    """B. Core 가 읽고 쓰는 메모리 저장소. Core 의 plans.save 는 여기로 가고 DB 는 C 가 쓴다."""
    drafts: InMemoryPlanRepository[MonthlyPlan] = InMemoryPlanRepository()
    drafts.save(plan.plan_id, plan)
    return drafts


def _write(
    session: Session,
    user,
    plan_id: int,
    changed: MonthlyPlan,
    expected_revision: int,
    *,
    confirming: bool = False,
) -> MonthlyPlanOut:
    """C. 조건부 쓰기. 못 썼으면 다시 읽어 왜인지 가른다 — 한 가지 오류로 뭉치지 않는다."""
    written = _monthly_repo(session, user.center_id).update_if_revision(
        changed.plan_id, changed, expected_revision=expected_revision
    )
    if written is None:
        session.rollback()
        row = _own_row(session, user, plan_id)  # 없어졌거나 남의 것이면 404
        if row.status == "CONFIRMED":
            if confirming:  # 누가 먼저 확정했다 — 확정 재호출과 같다(D-M5-CONFIRM-01)
                return _current(session, user, plan_id)
            raise _ALREADY_CONFIRMED
        raise _STALE_WRITE
    detail = _current(session, user, plan_id)
    session.commit()
    return detail


@router.put("/{plan_id}/cells/{item_id}", response_model=MonthlyPlanOut)
def edit_monthly_cell(
    plan_id: int, item_id: str, body: EditMonthlyCell, session: DbSession, user: CurrentUser
):
    """칸 하나를 교사가 고친다. 근거 · 생성 방식은 그대로, `TEACHER_EDITED` 가 남는다."""
    plan = _read_draft(session, user, plan_id, body.expected_revision)
    try:
        changed = monthly_edit(plan_repository=_drafts(plan), clock=SystemClock()).execute(
            EditMonthlyPlanItemCommand(plan.plan_id, _item_id(item_id), body.value, _actor(user))
        )
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.post("/{plan_id}/cells/{item_id}/regenerate", response_model=MonthlyPlanOut)
def regenerate_monthly_cell(
    plan_id: int, item_id: str, body: RevisionIn, session: DbSession, user: CurrentUser
):
    """그 칸만 다시 만든다. 교사가 고친 칸도 명시적으로 요청하면 다시 만든다.

    LLM 을 기다리는 동안 transaction 이 없다. 그 사이 누가 고쳤으면 결과를 버리고 409 다.
    """
    plan = _read_draft(session, user, plan_id, body.expected_revision)
    try:
        provider = monthly_llm_provider()
    except LlmUnavailable as error:
        raise _UNAVAILABLE from error
    use_case = monthly_regeneration(
        plan_repository=_drafts(plan), provider=provider, clock=SystemClock()
    )
    try:
        changed = use_case.execute(
            RegenerateMonthlyPlanItemCommand(plan.plan_id, _item_id(item_id), _actor(user))
        ).plan
    except MonthlyApplicationError as error:
        _log.warning(
            "monthly cell regeneration failed code=%s stage=%s cause=%s validation_codes=%s",
            error.code,
            *_cause_summary(error),
        )
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, body.expected_revision)


@router.post("/{plan_id}/confirm", response_model=MonthlyPlanOut)
def confirm_monthly_plan(plan_id: int, body: RevisionIn, session: DbSession, user: CurrentUser):
    """DRAFT → CONFIRMED.

    **이미 확정이면 revision 과 무관하게 200 이고 아무것도 쓰지 않는다**(D-M5-CONFIRM-01) —
    더블클릭 · 재시도가 정상 경로다. 소유 검사는 그보다 먼저다.
    findings 로 막지 않는다(Core 계약). 안전교육 「근거 필요」 상태로도 확정된다.
    """
    row = _own_row(session, user, plan_id)
    if row.status == "CONFIRMED":
        return _current(session, user, plan_id)
    if row.revision != body.expected_revision:
        raise _STALE_WRITE
    plan = _monthly_repo(session, user.center_id).get(PlanId(row.plan_ref))
    session.commit()
    try:
        changed = monthly_confirmation(plan_repository=_drafts(plan), clock=SystemClock()).execute(
            ConfirmMonthlyPlanCommand(plan.plan_id, _actor(user))
        )
    except MonthlyApplicationError as error:
        raise _lifecycle_error(error) from error
    return _write(session, user, plan_id, changed, body.expected_revision, confirming=True)


def _detail(row: Plan, plan: MonthlyPlan, parent_id: int) -> MonthlyPlanOut:
    """도메인 객체를 계약 형식으로. 칸 수 · 순서는 Core 가 정한 그대로다.

    `revision` 은 DB 행의 값이다 — 도메인에는 revision 이 없다.
    """
    snapshot = plan.template_snapshot
    shown = {section.section_key: section for section in snapshot.sections}
    report = plan.verification_report
    return MonthlyPlanOut(
        id=row.id,
        class_id=int(plan.classroom_ref),
        school_year=plan.school_year,
        month=plan.target_month.calendar_month,
        target_month=plan.target_month.value,
        status=plan.status.value,
        revision=row.revision,
        generation_mode=plan.generation_mode.value,
        profile_ref=ProfileRefOut(
            profile_id=snapshot.profile_ref.profile_id,
            profile_version=snapshot.profile_ref.profile_version,
        ),
        base_template_ref=TemplateRefOut(
            template_id=snapshot.base_template_ref.template_id,
            template_version=snapshot.base_template_ref.template_version,
        ),
        parent=ParentOut(
            annual_plan_id=parent_id,
            theme=plan.parent_lineage.snapshot_value,
            confirmed_at=plan.parent_lineage.confirmed_at,
        ),
        weeks=[
            WeekOut(
                week_id=week.week_id.value,
                label=week.display_label,
                start_date=week.start_date,
                end_date=week.end_date,
                active=week.active,
            )
            for week in plan.week_periods
        ],
        sections=[
            SectionOut(
                section_key=section.section_key,
                label=shown[section.section_key].display_label,
                role=section.role.value,
                repeat_by=None if section.repeat_by is None else section.repeat_by.value,
                visible=shown[section.section_key].visible,
                order=shown[section.section_key].order,
                semantic_variant=(
                    None
                    if shown[section.section_key].semantic_variant is None
                    else shown[section.section_key].semantic_variant.value
                ),
                cells=[_cell(cell) for cell in section.cells],
            )
            for section in plan.sections
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


def _cell(cell) -> CellOut:
    return CellOut(
        item_id=cell.item_id.value,
        week_id=None if cell.week_id is None else cell.week_id.value,
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
        generation=GenerationOut(
            method=cell.generation.method.value,
            rule_id=cell.generation.rule_id,
            rule_version=cell.generation.rule_version,
        ),
    )
