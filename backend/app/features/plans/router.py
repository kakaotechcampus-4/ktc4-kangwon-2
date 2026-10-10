"""연간계획안 API. 계약은 docs/api-spec.md §4~§7 이다.

**여기에 생성 규칙이 없다.** 12개월 주제를 고르고 근거를 다는 일은 전부
`p0-planning` 이 한다. 이 파일은 HTTP 요청을 그 쪽 명령으로 바꾸고, 돌아온
도메인 객체를 계약 형식으로 옮길 뿐이다. 규칙이 여기 새면 같은 규칙이 두 군데
생기고 둘이 갈라진다.
"""

import copy
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository

# **`ssuksak.planning` 이 공개 창구다.** 안쪽 파일 위치를 우리가 외우면 하민이 정리할 때마다
# 이쪽이 깨진다. `__all__` 이 「backend 가 써도 되는 것」의 계약이다.
# `YearlyRuleError` 만 아직 공개 목록에 없어 안쪽에서 가져온다 — code 가 없어 계약 코드로
# 못 가르는 것이라, Core 가 감싸주면 그때 여기도 빠진다.
from ssuksak.planning import (
    ActorId,
    CatalogSelector,
    ConfirmYearlyPlan,
    ConfirmYearlyPlanCommand,
    EditYearlyPlanItem,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlan,
    GenerateYearlyPlanCommand,
    InvalidDomainValueError,
    InvalidStateTransitionError,
    PlanId,
    RegenerateYearlyPlanItem,
    RegenerateYearlyPlanItemCommand,
    YearlyApplicationError,
    YearlyPlan,
)
from ssuksak.planning.rules.errors import YearlyRuleError
from ssuksak.planning.rules.yearly_reference_rules import (
    CATALOG_APPROVAL_RULE_ID,
    CATALOG_RESOLUTION_RULE_ID,
)
from ssuksak.planning.rules.yearly_theme_selection import RULE_ID as THEME_SELECTION_RULE_ID

from app.db import get_session
from app.features.auth.models import User

# forms 모델을 직접 import 하지 않는다 — 창구 함수를 쓴다(structure.md).
from app.features.forms.service import find_own_form
from app.features.plans.llm import theme_text_generator
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.rules import verify
from app.features.plans.runtime import SystemClock, UuidGenerator
from app.features.plans.schemas import (
    AnnualPlanListOut,
    AnnualPlanOut,
    AnnualPlanSummary,
    AuditEventOut,
    AuditOut,
    CheckOut,
    ConfirmOut,
    CreateAnnualPlan,
    EvidenceOut,
    GenerationChangeOut,
    GenerationOut,
    MonthOut,
    UpdateMonth,
    ValueChangeOut,
)
from app.shared.auth.dependency import CurrentUser
from app.shared.auth.ownership import require_own_class
from app.shared.llm import LlmBudgetExceeded, LlmUnavailable

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


def _row(session: Session, user: User, plan_id: int, *, lock: bool = False) -> Plan:
    """남의 원 계획안은 없는 것과 같다 (shared/auth/ownership.py 와 같은 이유).

    **쓰는 요청은 `lock=True` 로 읽는다**(`SELECT … FOR UPDATE`). 본문 전체를 읽고 고쳐서 통째로
    저장하므로, 잠그지 않으면 겹친 두 요청 중 나중 것이 먼저 것을 지운다 — 확정과 겹친 PUT 이
    옛 DRAFT 본문을 저장해 확정이 되돌아가는 일도 생긴다. 잠금은 이 요청의 transaction 이 끝날
    때(commit · 오류) 풀린다. 행 하나만 잡으므로 서로 기다리다 막히는 일은 없다.
    """
    query = select(Plan).where(
        Plan.id == plan_id, Plan.center_id == user.center_id, Plan.kind == "annual"
    )
    row = session.scalar(query.with_for_update() if lock else query)
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
    months = _months(plan, row.sub_themes)
    return AnnualPlanOut(
        id=row.id,
        class_id=int(plan.classroom_ref),
        school_year=plan.school_year,
        status=plan.status.value,
        months=months,
        **_checks(months),
    )


def _checks(months: list[MonthOut]) -> dict:
    """법정 안전교육을 검사한다 (ADR-014).

    **무엇을 검사했는지(`checked_rules`)를 결과와 따로 준다.** 빈 배열 하나로는
    「문제없다」와 「아무것도 안 봤다」가 구분되지 않는다 — 화면이 둘을 같게 그리면
    교사가 검사 0건짜리 계획안을 초록불로 보고 확정한다.

    검사기가 터지면 통과로 넘기지 않는다. 「검사할 수 없다」와 「검사가 깨졌다」는
    다르고, 깨진 것을 UNVERIFIED 로 바꾸면 아무도 모른다.
    """
    payload = [
        {
            "month": m.month,
            "safety_education": m.safety_education,
            "safety_education_state": m.safety_education_state,
        }
        for m in months
    ]
    found = verify.legal_hours(payload)
    return {
        "checked_rules": ["legal_hours"],
        "checks": [
            CheckOut(rule=v.rule, severity=v.severity, detail=v.detail, month=v.month)
            for v in found
        ],
    }


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
    if isinstance(cause, LlmBudgetExceeded):
        return _503("LLM_BUDGET_EXCEEDED", "생성 한도에 걸렸습니다. 운영에 문의해주세요.")
    if isinstance(cause, LlmUnavailable):
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
    # 연간은 반 하나에 하나다. 막지 않으면 교사가 새로고침하고 다시 눌렀을 때 두 개가
    # 생기고, 둘 중 어느 쪽이 진짜인지 아무도 모른다. **동시 요청은 이 조회로 못 막는다** —
    # 둘 다 「없다」를 보고 지나간다. 최종 보장은 models.py 의 부분 유니크 인덱스다.
    duplicate = session.scalar(
        select(Plan).where(
            Plan.center_id == user.center_id,
            Plan.kind == "annual",
            Plan.classroom_ref == str(klass.id),
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_EXISTS",
                "message": "이 반의 연간계획안이 이미 있습니다.",
                "fields": ["class_id"],
            },
        )
    if body.form_id is not None and find_own_form(session, user.center_id, body.form_id) is None:
        # 남의 원 양식 번호를 넣어도 통과하면 안 된다. 없는 것과 남의 것을 가르지 않는다(ADR-017).
        # forms 모델을 직접 import 하지 않는다 — 창구 함수를 쓴다(structure.md).
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "message": "양식을 찾을 수 없습니다.",
                "fields": ["form_id"],
            },
        )
    repo = _repo(session, user)
    try:
        generator = theme_text_generator()
    except LlmUnavailable as error:
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
    # **응답을 다 만든 뒤에 확정한다.** 먼저 commit 하면 아래에서 터졌을 때 DB 에는
    # 계획안이 남고 교사는 500 을 본다 — 실패한 줄 알고 다시 눌러 두 개가 생긴다.
    # 저장소가 이미 flush 해두어 commit 전에도 행을 읽을 수 있다.
    row = session.scalar(select(Plan).where(Plan.plan_ref == result.plan.plan_id.value))
    # 어느 양식에서 나왔는지 남긴다. 도메인은 양식을 모르므로 서버가 칸에 넣는다.
    row.form_id = body.form_id
    detail = _detail(row, result.plan)
    session.commit()
    return detail


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
    row = _row(session, user, plan_id, lock=True)
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
    months = _months(updated, row.sub_themes)
    answer = next(item for item in months if item.month == month)
    session.commit()
    return answer


@router.post("/{plan_id}/confirm", response_model=ConfirmOut)
def confirm_annual_plan(plan_id: int, session: DbSession, user: CurrentUser):
    row = _row(session, user, plan_id, lock=True)
    # **재호출은 멱등이다(§7).** 이미 확정이면 저장된 그대로 200 — Core 확정을 다시 부르지 않고
    # (부르면 409) 저장 · commit 도 하지 않는다. 소유 검사(_row) 뒤라 남의 원 것은 여전히 404 다.
    if row.status == "CONFIRMED":
        return ConfirmOut(id=row.id, status=row.status, confirmed_at=row.confirmed_at)
    repo = _repo(session, user)
    try:
        confirmed = ConfirmYearlyPlan(plan_repository=repo, clock=SystemClock()).execute(
            ConfirmYearlyPlanCommand(
                plan_id=PlanId(row.plan_ref), actor_id=ActorId(f"user_{user.id}")
            )
        )
    except (YearlyApplicationError, InvalidStateTransitionError, InvalidDomainValueError) as error:
        raise _domain_error(error) from error
    # 저장소가 감사 기록에서 꺼내 칸에 넣어둔 값을 그대로 쓴다.
    answer = ConfirmOut(id=row.id, status=confirmed.status.value, confirmed_at=row.confirmed_at)
    session.commit()
    return answer


# ── 선택 월 재생성 (잠정 — docs/provisional-policy-decisions.md PROV-Y-A · B · E · F) ─────────

_ALREADY_CONFIRMED = HTTPException(
    status.HTTP_409_CONFLICT,
    detail={
        "code": "ALREADY_CONFIRMED",
        "message": "확정된 계획안은 수정할 수 없습니다.",
        "fields": [],
    },
)
_STALE_WRITE = HTTPException(
    status.HTTP_409_CONFLICT,
    detail={
        "code": "STALE_WRITE",
        "message": "그 사이 다른 화면에서 계획안이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.",
        "fields": [],
    },
)
_HAS_SUB_THEMES = HTTPException(
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail={
        "code": "VALIDATION_FAILED",
        "message": "소주제가 있는 달은 주제를 다시 만들 수 없습니다. 소주제를 비운 뒤 해주세요.",
        "fields": ["sub_themes"],
    },
)
_NO_OTHER_THEME = HTTPException(
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail={
        "code": "VALIDATION_FAILED",
        "message": "이 달에 쓸 수 있는 주제 후보가 없습니다.",
        "fields": ["month"],
    },
)
_REGENERATION_FAILED = HTTPException(
    status.HTTP_500_INTERNAL_SERVER_ERROR,
    detail={
        "code": "GENERATION_FAILED",
        "message": "주제를 다시 만들지 못했습니다. 다시 시도해주세요.",
        "fields": [],
    },
)


def _has_sub_themes(sub_themes: dict, month: int) -> bool:
    """앞뒤 공백을 뺀 값이 하나라도 있으면 「있다」. `[]` · `["", "  "]` 은 없는 것과 같다."""
    return any(isinstance(item, str) and item.strip() for item in sub_themes.get(str(month), []))


def _regeneration_error(error: Exception) -> HTTPException:
    """재생성이 실패한 이유를 계약 코드로 가른다. **Core 문구를 그대로 내보내지 않는다.**"""
    if isinstance(error, InvalidStateTransitionError):
        return _ALREADY_CONFIRMED
    if isinstance(error, YearlyRuleError):
        if error.rule_id in (CATALOG_RESOLUTION_RULE_ID, CATALOG_APPROVAL_RULE_ID):
            # 서버의 승인 참조자료를 쓸 수 없다 — 재시도해도 같다(월간 _REFERENCE_UNAVAILABLE).
            return _503(
                "DEPENDENCY_UNAVAILABLE",
                "계획안 생성 기능을 지금 쓸 수 없습니다. 운영에 문의해주세요.",
            )
        if error.rule_id == THEME_SELECTION_RULE_ID:
            return _NO_OTHER_THEME
        return _REGENERATION_FAILED
    if isinstance(error, YearlyApplicationError):
        cause = error.__cause__
        if isinstance(cause, LlmBudgetExceeded):
            return _503("LLM_BUDGET_EXCEEDED", "생성 한도에 걸렸습니다. 운영에 문의해주세요.")
        if isinstance(cause, LlmUnavailable):
            return _503(
                "DEPENDENCY_UNAVAILABLE",
                "계획안 생성 기능을 지금 쓸 수 없습니다. 운영에 문의해주세요.",
            )
    # LLM 호출이 깨졌다 · 결과가 계약을 어겼다
    # (theme_text_generation_failed · invalid_theme_text_result)
    # · 그 밖의 Core 거절. 아무것도 저장되지 않았다.
    return _REGENERATION_FAILED


@router.post("/{plan_id}/months/{month}/regenerate", response_model=MonthOut)
def regenerate_month(plan_id: int, month: int, session: DbSession, user: CurrentUser):
    """그 달 주제만 다시 만든다. 다른 11개월은 그대로다. **잠정 계약이다**(PM 확인 전).

    LLM 을 기다리는 동안 행을 잠그지 않는다 — PUT · 확정이 30초씩 막히지 않게. 대신 저장을 「DRAFT
    이고 본문 · 소주제가 읽은 그대로일 때만」 한 문장으로 한다. 그 사이 PUT · 확정 · 다른 재생성이
    있었으면 아무것도 쓰지 않고 409 다. 교사가 고친 주제도 바뀐다 — 이전 값은 Audit 에 남는다.
    """
    # ── 1. 짧은 읽기 ───────────────────────────────────────────────────────
    row = _row(session, user, plan_id)
    repo = _repo(session, user)
    plan = repo.get(PlanId(row.plan_ref))
    period = next((p for p in plan.periods if p.period.calendar_month == month), None)
    if period is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "그 달이 없습니다.", "fields": ["month"]},
        )
    if row.status == "CONFIRMED":
        raise _ALREADY_CONFIRMED
    if _has_sub_themes(row.sub_themes, month):
        raise _HAS_SUB_THEMES
    seen_body, seen_sub_themes = copy.deepcopy(row.body), copy.deepcopy(row.sub_themes)
    try:
        generator = theme_text_generator()
    except LlmUnavailable as error:
        raise _503(
            "DEPENDENCY_UNAVAILABLE", "계획안 생성 기능을 지금 쓸 수 없습니다. 운영에 문의해주세요."
        ) from error
    # 읽기를 여기서 끝낸다. LLM 을 기다리는 동안 transaction · 행을 잡지 않는다.
    session.commit()

    # ── 2. Core — DB 없음 ──────────────────────────────────────────────────
    drafts: InMemoryPlanRepository[YearlyPlan] = InMemoryPlanRepository()
    drafts.save(plan.plan_id, plan)
    try:
        regenerated = (
            RegenerateYearlyPlanItem(
                theme_repository=JsonThemeReferenceRepository(),
                plan_repository=drafts,
                text_generator=generator,
                clock=SystemClock(),
            )
            .execute(
                RegenerateYearlyPlanItemCommand(
                    plan_id=plan.plan_id,
                    item_id=period.theme.item_id,
                    actor_id=ActorId(f"user_{user.id}"),
                    catalog=CATALOG,
                )
            )
            .plan
        )
    except (
        InvalidStateTransitionError,
        YearlyRuleError,
        YearlyApplicationError,
        InvalidDomainValueError,
    ) as error:
        raise _regeneration_error(error) from error

    # ── 3. 조건부 쓰기 ─────────────────────────────────────────────────────
    written = repo.update_if_unchanged(
        plan.plan_id,
        regenerated,
        expected_body=seen_body,
        expected_sub_themes=seen_sub_themes,
    )
    if not written:
        session.rollback()
        # 왜 못 썼는지 가른다. 그 사이 또 바뀌어 코드가 어긋날 수는 있어도 쓴 것은 없다.
        raise (
            _ALREADY_CONFIRMED
            if _row(session, user, plan_id).status == "CONFIRMED"
            else _STALE_WRITE
        )
    answer = next(m for m in _months(regenerated, seen_sub_themes) if m.month == month)
    session.commit()
    return answer


@router.get("/{plan_id}/audit", response_model=AuditOut)
def get_audit(plan_id: int, session: DbSession, user: CurrentUser):
    """누가 언제 뭘 바꿨나. 되돌리기(P1)와 평가제(P2)가 이걸 본다(§4).

    **계획안 단위와 칸 단위를 같이 준다.** 생성·확정은 계획안에 남고 교사 수정은
    그 칸에 남는다. 계획안 것만 주면 "교사가 뭘 고쳤나"가 통째로 빠진다.
    """
    row = _row(session, user, plan_id)
    plan = _repo(session, user).get(PlanId(row.plan_ref))

    def generation(detail) -> GenerationOut:
        return GenerationOut(
            method=detail.method.value, rule_id=detail.rule_id, rule_version=detail.rule_version
        )

    def out(event, month=None):
        # 값 · 생성 방식 변화는 Core 이벤트에 저장된 것만 옮긴다. 현재 값에서 거꾸로 만들지 않는다.
        values, methods = event.value_change, event.generation_change
        return AuditEventOut(
            type=event.event_type.value,
            occurred_at=event.occurred_at,
            month=month,
            actor=event.actor_id.value if event.actor_id is not None else None,
            system_actor=event.system_actor,
            value_change=(
                None if values is None else ValueChangeOut(before=values.before, after=values.after)
            ),
            generation_change=(
                None
                if methods is None
                else GenerationChangeOut(
                    before=generation(methods.before), after=generation(methods.after)
                )
            ),
        )

    items = [out(event) for event in plan.audit.events]
    for period in plan.periods:
        items += [out(event, period.period.calendar_month) for event in period.theme.audit.events]
    # 시간순. 어느 쪽에 담겼는지가 아니라 언제 일어났는지로 읽어야 한다.
    items.sort(key=lambda item: item.occurred_at)
    return AuditOut(items=items)
