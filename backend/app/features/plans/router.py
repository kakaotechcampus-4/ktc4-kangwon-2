"""연간계획안 API. 계약은 docs/api-spec.md §4~§7 이다.

**여기에 생성 규칙이 없다.** 12개월 주제를 고르고 근거를 다는 일은 전부
`p0-planning` 이 한다. 이 파일은 HTTP 요청을 그 쪽 명령으로 바꾸고, 돌아온
도메인 객체를 계약 형식으로 옮길 뿐이다. 규칙이 여기 새면 같은 규칙이 두 군데
생기고 둘이 갈라진다.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
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
    YearlyApplicationError,
    YearlyPlan,
)
from ssuksak.planning.rules.errors import YearlyRuleError
from ssuksak.planning.rules.yearly_theme_selection import RULE_ID as THEME_SELECTION_RULE_ID

from app.config import settings
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

_log = logging.getLogger("app.server")

# 반 하나에 연간 하나 — models.py 의 부분 유니크 인덱스. 동시 생성이 여기에 걸린다.
ANNUAL_UNIQUE = "uq_plans_annual_per_classroom"
_ALREADY_EXISTS = HTTPException(
    status.HTTP_409_CONFLICT,
    detail={
        "code": "ALREADY_EXISTS",
        "message": "이 반의 연간계획안이 이미 있습니다.",
        "fields": ["class_id"],
    },
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
    if error.code in ("theme_text_generation_failed", "invalid_theme_text_result"):
        # 호출이 깨졌거나 결과가 계약을 어겼다 — 둘 다 생성 실패다. 입력 오류(422)가 아니다.
        # **부분 결과가 남지 않는다.** p0-planning 이 저장 전에 멈춘다.
        _log.warning("annual generation failed code=%s", error.code)
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
    """도메인이 낸 오류를 계약 봉투로. **원인은 도메인이 안다 — 여기서 다시 판단하지 않는다.**

    **Core 문장을 교사에게 보내지 않는다.** 개발자용 영어라 고정 문구로 답하고,
    원문은 서버 기록에만 남긴다.
    """
    if isinstance(error, InvalidStateTransitionError):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "ALREADY_CONFIRMED",
                "message": "확정된 계획안은 수정할 수 없습니다.",
                "fields": [],
            },
        )
    code = getattr(error, "code", None) or getattr(error, "rule_id", None)
    _log.warning("annual domain error type=%s code=%s detail=%s", type(error).__name__, code, error)
    if isinstance(error, YearlyRuleError) and error.rule_id == THEME_SELECTION_RULE_ID:
        # 그 달 · 반 연령에 맞는 승인 주제가 없다. 교사가 고칠 수 없는 참고자료 문제다(U-20 B).
        return _503(
            "DEPENDENCY_UNAVAILABLE",
            "지금은 이 반의 연간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요.",
        )
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "VALIDATION_FAILED", "message": "입력값을 확인해주세요.", "fields": []},
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
        raise _ALREADY_EXISTS
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
    except IntegrityError as error:
        # 위 조회를 둘 다 통과한 동시 요청 — 늦은 쪽이 저장(flush)에서 인덱스에 걸린다.
        session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == ANNUAL_UNIQUE:
            raise _ALREADY_EXISTS from error
        raise
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


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annual_plan(plan_id: int, session: DbSession, user: CurrentUser) -> Response:
    """확정 전 연간계획안을 지운다.

    **지울 길이 있어야 다시 만들 수 있다.** 반 하나에 연간은 하나고(models.py 부분 유니크
    인덱스), 만들기는 409 로 막는다. 지우기가 없으면 교사가 첫 초안이 마음에 안 들어도
    영영 다시 못 만든다.

    **확정본은 안 지운다.** 제출 문서다. 다시 만들어야 하면 사람이 판단할 일이지
    버튼 한 번으로 사라지면 안 된다.

    **월간이 딸려 있으면 안 지운다.** 월간은 이 계획안을 부모로 들고 있어서(§9-1
    `parent`), 부모가 사라지면 조회가 깨진다. 월간을 먼저 지워야 한다.

    부모는 `body` 안에만 있어서 열로는 못 찾는다. 같은 반 · 같은 학년도의 월간을 본다 —
    연간이 반마다 하나뿐이라 그 월간의 부모는 이것뿐이다.

    **잠그고 읽는다.** 안 잠그면 확정과 겹쳤을 때 DRAFT 를 보고 지나간 DELETE 가 확정의
    commit 뒤에 실행돼 확정본을 지운다.
    """
    row = _row(session, user, plan_id, lock=True)
    if row.status == "CONFIRMED":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "GATE_BLOCKED",
                "message": "확정된 계획안은 지울 수 없습니다.",
                "fields": [],
            },
        )
    child = session.scalar(
        select(Plan.id).where(
            Plan.center_id == user.center_id,
            Plan.kind == "monthly",
            Plan.classroom_ref == row.classroom_ref,
            Plan.school_year == row.school_year,
        )
    )
    if child is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "IN_USE",
                "message": "이 연간계획안으로 만든 월간계획안이 있습니다. 먼저 지워주세요.",
                "fields": [],
            },
        )
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{plan_id}/test-reset", status_code=status.HTTP_204_NO_CONTENT)
def test_reset_annual_plan(plan_id: int, session: DbSession, user: CurrentUser) -> Response:
    """**시험용.** 연간계획안과 딸린 월간을 한 번에 지운다. 확정 여부를 보지 않는다.

    **파일럿 시작 전에 끈다.** `ALLOW_TEST_RESET` 가 꺼져 있으면 이 경로는 404 다 —
    있는지조차 알리지 않는다. 기본은 꺼짐이다(`config.py`).

    **왜 필요한가** — 연간을 확정하면 고칠 수도(`내용 수정` 이 꺼진다) 지울 수도
    (`DELETE` 가 확정본을 막는다) 없다. 계획안에는 일지와 달리 `unconfirm` 이 없어서
    빠져나올 구멍이 없다. 시험하는 동안 그 막다른 길을 열어 둔다.

    **진짜 지우기는 따로 둔다.** 위 `DELETE /{plan_id}` 는 그대로 확정본과 딸린 월간을
    막는다. 그쪽이 교사가 쓰는 길이고, 이건 우리가 시험할 때만 쓰는 길이다. 한 경로에
    「가끔 다르게 도는 조건」을 넣으면 어느 쪽이 도는지 아무도 모르게 된다.
    """
    if not settings.allow_test_reset:
        raise _NOT_FOUND

    row = _row(session, user, plan_id)
    children = list(
        session.scalars(
            select(Plan).where(
                Plan.center_id == user.center_id,
                Plan.kind == "monthly",
                Plan.classroom_ref == row.classroom_ref,
                Plan.school_year == row.school_year,
            )
        )
    )
    # 시험용이라도 무엇을 지웠는지는 남긴다. 「왜 사라졌지」를 뒤에서 풀 수 있어야 한다.
    _log.warning(
        "test-reset: 연간 %s(%s) · 월간 %s 개를 지웠다. 누른 사람 user_%s",
        row.id,
        row.status,
        len(children),
        user.id,
    )
    for child in children:
        session.delete(child)
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.get("/{plan_id}/audit", response_model=AuditOut)
def get_audit(plan_id: int, session: DbSession, user: CurrentUser):
    """누가 언제 뭘 바꿨나. 되돌리기(P1)와 평가제(P2)가 이걸 본다(§4).

    **계획안 단위와 칸 단위를 같이 준다.** 생성·확정은 계획안에 남고 교사 수정은
    그 칸에 남는다. 계획안 것만 주면 "교사가 뭘 고쳤나"가 통째로 빠진다.
    """
    row = _row(session, user, plan_id)
    plan = _repo(session, user).get(PlanId(row.plan_ref))

    def out(event, month=None):
        values = event.value_change
        return AuditEventOut(
            type=event.event_type.value,
            occurred_at=event.occurred_at,
            month=month,
            actor=event.actor_id.value if event.actor_id is not None else None,
            system_actor=event.system_actor,
            value_change=(
                None if values is None else ValueChangeOut(before=values.before, after=values.after)
            ),
        )

    items = [out(event) for event in plan.audit.events]
    for period in plan.periods:
        items += [out(event, period.period.calendar_month) for event in period.theme.audit.events]
    # 시간순. 어느 쪽에 담겼는지가 아니라 언제 일어났는지로 읽어야 한다.
    items.sort(key=lambda item: item.occurred_at)
    return AuditOut(items=items)
