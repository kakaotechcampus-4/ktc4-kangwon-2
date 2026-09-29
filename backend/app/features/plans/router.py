"""연간계획안 API. 계약은 docs/api-spec.md §4~§7 이다.

**여기에 생성 규칙이 없다.** 12개월 주제를 고르고 근거를 다는 일은 전부
`p0-planning` 이 한다. 이 파일은 HTTP 요청을 그 쪽 명령으로 바꾸고, 돌아온
도메인 객체를 계약 형식으로 옮길 뿐이다. 규칙이 여기 새면 같은 규칙이 두 군데
생기고 둘이 갈라진다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository
from ssuksak.planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ssuksak.planning.application.edit_yearly_plan_item import EditYearlyPlanItem
from ssuksak.planning.application.generate_yearly_plan import GenerateYearlyPlan
from ssuksak.planning.application.yearly_dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
)
from ssuksak.planning.application.yearly_errors import YearlyApplicationError
from ssuksak.planning.domain.errors import InvalidDomainValueError, InvalidStateTransitionError
from ssuksak.planning.domain.identifiers import ActorId, PlanId
from ssuksak.planning.domain.yearly_plan import YearlyPlan
from ssuksak.planning.rules.errors import YearlyRuleError

from app.db import get_session
from app.features.auth.models import User
from app.features.plans.llm import (
    ThemeTextBudgetExceeded,
    ThemeTextUnavailable,
    theme_text_generator,
)
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import (
    AnnualPlanListOut,
    AnnualPlanOut,
    AnnualPlanSummary,
    AuditEventOut,
    AuditOut,
    ConfirmOut,
    CreateAnnualPlan,
    EvidenceOut,
    GenerationOut,
    MonthOut,
    UpdateMonth,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class

router = APIRouter(prefix="/plans/annual", tags=["plans"])

DbSession = Annotated[Session, Depends(get_session)]

# 어떤 판의 주제 참조자료를 쓰는지. 계획안마다 이 값이 근거에 박혀서 저장되므로
# 자료를 새 판으로 올릴 때 여기만 바꾸면 이후 계획안부터 새 판을 쓴다 —
# 이미 만든 계획안의 근거는 안 바뀐다.
CATALOG = CatalogSelector(
    catalog_id="ssuksak.yearly-theme-reference",
    catalog_version="theme-reference-v0.1.2",
)

# P0 에서는 안전교육 배치 입력이 없다. 「그 달엔 안 한다」가 아니라
# 「언제 할지 아직 모른다」다 — 둘을 같게 그리면 교사가 비었다고 넘어간다(§4).
SAFETY_STATE_P0 = "SOURCE_REQUIRED"

_NOT_FOUND = HTTPException(
    status.HTTP_404_NOT_FOUND,
    detail={"code": "NOT_FOUND", "message": "계획안을 찾을 수 없습니다.", "fields": ["id"]},
)


def _repo(session: Session, user: User) -> PostgresPlanRepository[YearlyPlan]:
    return PostgresPlanRepository(
        session, center_id=user.center_id, kind="annual", plan_type=YearlyPlan
    )


def _row(session: Session, user: User, plan_id: int) -> Plan:
    """남의 원 계획안은 없는 것과 같다 (shared/auth/ownership.py 와 같은 이유)."""
    row = session.scalar(
        select(Plan).where(
            Plan.id == plan_id, Plan.center_id == user.center_id, Plan.kind == "annual"
        )
    )
    if row is None:
        raise _NOT_FOUND
    return row


def _months(plan: YearlyPlan, sub_themes: dict) -> list[MonthOut]:
    """도메인 객체를 계약 형식으로. 배열은 3월부터 익년 2월 순서다(§4)."""
    return [
        MonthOut(
            month=period.period.calendar_month,
            theme=period.theme.value,
            # 계약에는 있는데 도메인이 만들지 않는다. 교사가 §6 으로 채운다.
            sub_themes=sub_themes.get(str(period.period.calendar_month), []),
            # P0 에는 배치 입력이 없어 항상 빈 배열이다. 칸은 있고 값만 빈다.
            safety_education=[],
            safety_education_state=SAFETY_STATE_P0,
            evidence=[
                EvidenceOut(
                    source_type=source.source_type.value,
                    source_id=source.source_id,
                    source_version=source.source_version,
                    effective_date=None,
                    display_name=source.display_name,
                )
                for source in period.theme.evidence
            ],
            generation=GenerationOut(
                method=period.theme.generation.method.value,
                rule_id=period.theme.generation.rule_id,
                rule_version=period.theme.generation.rule_version,
            ),
        )
        for period in plan.periods
    ]


def _detail(row: Plan, plan: YearlyPlan) -> AnnualPlanOut:
    return AnnualPlanOut(
        id=row.id,
        class_id=int(plan.classroom_ref),
        school_year=plan.school_year,
        status=plan.status.value,
        months=_months(plan, row.sub_themes),
    )


def _503(code: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": message, "fields": []},
    )


def _generation_error(error: YearlyApplicationError) -> HTTPException:
    """주제 생성이 실패한 이유를 계약 코드로 가른다.

    **p0-planning 이 생성기 오류를 자기 것으로 감싼다**(`theme_text_generation_failed`).
    그래서 원래 예외는 `__cause__` 에 들어 있다 — 재시도로 풀리는 것과 아닌 것을
    가르려면 거기를 봐야 한다. 셋을 한 코드로 뭉치면 FE 가 「운영 문의」를 띄워야 할
    자리에 「다시 시도」를 띄운다.
    """
    cause = error.__cause__
    if isinstance(cause, ThemeTextBudgetExceeded):
        return _503("LLM_BUDGET_EXCEEDED", "생성 한도에 걸렸습니다. 운영에 문의해주세요.")
    if isinstance(cause, ThemeTextUnavailable):
        return _503(
            "DEPENDENCY_UNAVAILABLE", "계획안 생성 기능을 지금 쓸 수 없습니다. 운영에 문의해주세요."
        )
    if error.code == "theme_text_generation_failed":
        # **부분 결과가 남지 않는다.** p0-planning 이 저장 전에 멈춘다.
        return HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "GENERATION_FAILED",
                "message": "계획안을 만들지 못했습니다. 다시 시도해주세요.",
                "fields": [],
            },
        )
    return _domain_error(error)


def _domain_error(error: Exception) -> HTTPException:
    """도메인이 낸 오류를 계약 봉투로. **원인은 도메인이 안다 — 여기서 다시 판단하지 않는다.**"""
    if isinstance(error, InvalidStateTransitionError):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_CONFIRMED",
                "message": "확정된 계획안은 수정할 수 없습니다.",
                "fields": [],
            },
        )
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "VALIDATION_FAILED", "message": str(error), "fields": []},
    )


@router.post("", response_model=AnnualPlanOut, status_code=status.HTTP_201_CREATED)
def create_annual_plan(body: CreateAnnualPlan, session: DbSession, user: CurrentUser):
    """12개월치를 만들어 DRAFT 로 저장한다.

    **학년도를 받지 않는다.** `class_id` 가 정한다 — `classes` 행이 학년도마다 새로
    생기므로 따로 받으면 불일치 경로만 생긴다(§4).
    """
    klass = require_own_class(session, user, body.class_id)
    repo = _repo(session, user)
    try:
        generator = theme_text_generator()
    except ThemeTextUnavailable as error:
        # 교사가 고칠 수 없다. 재시도 버튼을 띄우면 100번 눌러도 같다(api-spec 공통).
        raise _503(
            "DEPENDENCY_UNAVAILABLE", "계획안 생성 기능을 지금 쓸 수 없습니다. 운영에 문의해주세요."
        ) from error
    use_case = GenerateYearlyPlan(
        theme_repository=JsonThemeReferenceRepository(),
        plan_repository=repo,
        text_generator=generator,
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )
    try:
        result = use_case.execute(
            GenerateYearlyPlanCommand(
                school_year=klass.school_year,
                classroom_ref=str(klass.id),
                target_ages=frozenset(range(klass.age_min, klass.age_max + 1)),
                catalog=CATALOG,
            )
        )
    except YearlyApplicationError as error:
        raise _generation_error(error) from error
    except (YearlyRuleError, InvalidDomainValueError) as error:
        raise _domain_error(error) from error
    session.commit()
    row = session.scalar(select(Plan).where(Plan.plan_ref == result.plan.plan_id.value))
    return _detail(row, result.plan)


@router.get("", response_model=AnnualPlanListOut)
def list_annual_plans(session: DbSession, user: CurrentUser, class_id: int | None = None):
    """요약만 담는다. months 12개는 단건 조회가 준다(§5).

    **이 API 가 없으면 번호를 잃은 계획안을 영영 못 찾는다.** 새로고침 한 번이면
    교사는 다시 만들기를 누른다.
    """
    query = select(Plan).where(Plan.center_id == user.center_id, Plan.kind == "annual")
    if class_id is not None:
        require_own_class(session, user, class_id)
        query = query.where(Plan.classroom_ref == str(class_id))
    rows = session.scalars(query.order_by(Plan.created_at.desc(), Plan.id.desc())).all()
    return AnnualPlanListOut(
        items=[
            AnnualPlanSummary(
                id=row.id,
                class_id=int(row.classroom_ref),
                school_year=row.school_year,
                status=row.status,
                created_at=row.created_at,
                confirmed_at=row.confirmed_at,
            )
            for row in rows
        ]
    )


@router.get("/{plan_id}", response_model=AnnualPlanOut)
def get_annual_plan(plan_id: int, session: DbSession, user: CurrentUser):
    row = _row(session, user, plan_id)
    return _detail(row, _repo(session, user).get(PlanId(row.plan_ref)))


@router.put("/{plan_id}/months/{month}", response_model=MonthOut)
def update_month(
    plan_id: int, month: int, body: UpdateMonth, session: DbSession, user: CurrentUser
):
    """그 달 하나를 통째로 교체한다.

    **부분 저장이 없다.** `theme` 만 보내면 `sub_themes` 가 조용히 사라지고, 교사는
    저장됐다고 믿은 채 확정에서야 발견한다(§6).
    """
    row = _row(session, user, plan_id)
    repo = _repo(session, user)
    plan = repo.get(PlanId(row.plan_ref))
    period = next((p for p in plan.periods if p.period.calendar_month == month), None)
    if period is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 달이 없습니다.", "fields": ["month"]},
        )
    try:
        updated = EditYearlyPlanItem(plan_repository=repo, clock=SystemClock()).execute(
            EditYearlyPlanItemCommand(
                plan_id=plan.plan_id,
                item_id=period.theme.item_id,
                new_value=body.theme,
                actor_id=ActorId(f"user_{user.id}"),
            )
        )
    except (YearlyApplicationError, InvalidStateTransitionError, InvalidDomainValueError) as error:
        raise _domain_error(error) from error
    # 소주제는 도메인 밖이라 따로 넣는다. dict 를 통째로 갈아끼워야 SQLAlchemy 가
    # 바뀐 걸 알아챈다 — 안쪽만 고치면 JSONB 가 그대로 남는다.
    row.sub_themes = {**row.sub_themes, str(month): body.sub_themes}
    session.commit()
    months = _months(updated, row.sub_themes)
    return next(item for item in months if item.month == month)


@router.post("/{plan_id}/confirm", response_model=ConfirmOut)
def confirm_annual_plan(plan_id: int, session: DbSession, user: CurrentUser):
    row = _row(session, user, plan_id)
    repo = _repo(session, user)
    try:
        confirmed = ConfirmYearlyPlan(plan_repository=repo, clock=SystemClock()).execute(
            ConfirmYearlyPlanCommand(
                plan_id=PlanId(row.plan_ref), actor_id=ActorId(f"user_{user.id}")
            )
        )
    except (YearlyApplicationError, InvalidStateTransitionError, InvalidDomainValueError) as error:
        raise _domain_error(error) from error
    session.commit()
    # 저장소가 감사 기록에서 꺼내 칸에 넣어둔 값을 그대로 쓴다.
    return ConfirmOut(id=row.id, status=confirmed.status.value, confirmed_at=row.confirmed_at)


@router.get("/{plan_id}/audit", response_model=AuditOut)
def get_audit(plan_id: int, session: DbSession, user: CurrentUser):
    """누가 언제 뭘 바꿨나. 되돌리기(P1)와 평가제(P2)가 이걸 본다(§4).

    **계획안 단위와 칸 단위를 같이 준다.** 생성·확정은 계획안에 남고 교사 수정은
    그 칸에 남는다. 계획안 것만 주면 "교사가 뭘 고쳤나"가 통째로 빠진다.
    """
    row = _row(session, user, plan_id)
    plan = _repo(session, user).get(PlanId(row.plan_ref))

    def out(event, month=None):
        return AuditEventOut(
            type=event.event_type.value,
            occurred_at=event.occurred_at,
            month=month,
            actor=event.actor_id.value if event.actor_id is not None else None,
            system_actor=event.system_actor,
        )

    items = [out(event) for event in plan.audit.events]
    for period in plan.periods:
        items += [out(event, period.period.calendar_month) for event in period.theme.audit.events]
    # 시간순. 어느 쪽에 담겼는지가 아니라 언제 일어났는지로 읽어야 한다.
    items.sort(key=lambda item: item.occurred_at)
    return AuditOut(items=items)
