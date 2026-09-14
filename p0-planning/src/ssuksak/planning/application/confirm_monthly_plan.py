"""ConfirmMonthlyPlan Use Case.

docs/screen-spec.md §8 / 2026-09-11 Product Contract:

    MonthlyPlan.status = CONFIRMED
    = 교사가 해당 Monthly Plan의 작성 결과를 확정했다

    != 법정 안전교육 충족
    != Safety placement 검증 완료
    != 법률 준수 판정
    != Constraint 해결 완료

따라서 `CONFIRMED`와 `NOT_VERIFIED_SOURCE_REQUIRED`가 **동시에 존재할 수 있다.**
Confirm은 `ConstraintAssessment`를 건드리지 않으며 `VERIFIED`로 바꾸지 않는다.

**Exact Reference 재검증**
Confirm은 "현재 최신 Template"을 찾지 않는다. Plan이 보존한 `template_ref`와
ConstraintAssessment의 `rule_version`으로 **생성 당시와 같은 version**을 다시
resolve한다. 호출자가 다른 version을 넘겨 Confirm 기준을 바꿀 수 없도록
Command에 selector를 두지 않았다.

**Atomicity**
실패 가능한 검사를 전부 status mutation 앞에 둔다. `validate_monthly_plan`은
생성 결과가 DRAFT인지도 검사하므로 **반드시 confirm() 이전에** 호출해야 한다.
mutation 이후 남는 실패 지점은 Repository `save`뿐이며, 그 경우 status와 Audit을
원복한다.
"""

from __future__ import annotations

from ..domain.constraint import ConstraintKind
from ..domain.errors import FailureCategory, validation_failed
from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_template import MonthlyTemplate
from ..domain.plan import PlanStatus
from ..domain.provenance import AuditEvent, AuditEventType, AuditTrail
from ..domain.safety_legal_rule import SafetyLegalRule
from ..rules import monthly_gates
from .confirm_yearly_plan import require_opaque_actor
from .edit_monthly_plan_item import require_monthly_plan
from .monthly_dto import ConfirmMonthlyPlanCommand, MonthlyPlanResult
from .monthly_ports import (
    MonthlyPlanRepository,
    MonthlyTemplateRepository,
    SafetyLegalRuleRepository,
)
from .ports import Clock
from .validate_monthly_plan import validate_monthly_plan

__all__ = ["ConfirmMonthlyPlan"]


class ConfirmMonthlyPlan:
    def __init__(
        self,
        *,
        monthly_plan_repository: MonthlyPlanRepository,
        template_repository: MonthlyTemplateRepository,
        safety_rule_repository: SafetyLegalRuleRepository,
        clock: Clock,
    ) -> None:
        if template_repository is None or safety_rule_repository is None:
            raise ValueError(
                "ConfirmMonthlyPlan은 Template과 Safety Rule Repository를 필수로 "
                "요구한다. Reference 재검증을 생략할 수 없다."
            )
        self._plans = monthly_plan_repository
        self._templates = template_repository
        self._safety_rules = safety_rule_repository
        self._clock = clock

    def execute(self, command: ConfirmMonthlyPlanCommand) -> MonthlyPlanResult:
        # ---------------------------------------------- 1. Plan 존재
        plan = require_monthly_plan(self._plans, command.plan_id)

        # ------------------------------------------ 2. Actor Validation
        actor = require_opaque_actor(
            command.actor_id, rule="confirm_requires_opaque_actor_id"
        )

        # --------------------------------------------------- 3. 상태
        if plan.status is PlanStatus.CONFIRMED:
            raise validation_failed(
                "confirmed_monthly_plan_is_read_only",
                FailureCategory.PLAN_STATE_GATE,
                "이미 확정된 Plan이다",
            )

        # ------------------------------- 4. exact Template 재검증
        template = _revalidate_template(self._templates, plan)

        # ----------------------------- 5. exact Safety Rule 재검증
        _revalidate_safety_rule(self._safety_rules, plan)

        # ------------------------------------------- 6. 전체 Validation
        # DRAFT 상태에서 호출해야 한다. validate가 생성 결과의 DRAFT 여부도 본다.
        validate_monthly_plan(
            plan,
            template=template,
            expected_school_year=plan.school_year,
            expected_classroom_ref=plan.classroom_ref,
        )

        # --------------------- 7. 성공한 경우에만 CONFIRMED로 전이
        event = AuditEvent(
            event_type=AuditEventType.CONFIRMED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id.value,
            actor_id=actor,
        )

        previous_status = plan.status
        previous_audit = list(plan.audit.events)
        plan.confirm(event)

        try:
            self._plans.save(plan)
        except Exception:
            # 저장 실패 시 DRAFT로 되돌린다. 확정되지 않은 Plan이
            # 메모리에서만 CONFIRMED로 남지 않게 한다.
            plan.status = previous_status
            plan.audit = AuditTrail(previous_audit)
            raise

        return MonthlyPlanResult(plan=plan)


def _revalidate_template(
    templates: MonthlyTemplateRepository, plan: MonthlyPlan
) -> MonthlyTemplate:
    """Plan이 사용했던 **정확한** Template version을 다시 검증한다.

    최신 version으로 자동 upgrade하지 않는다. 과거 Plan의 근거가 Confirm
    시점에 바뀌면 안 된다.
    """
    template = monthly_gates.require_resolved_template(
        templates.get_template(
            plan.template_ref.template_id, plan.template_ref.template_version
        ),
        plan.template_ref,
    )
    monthly_gates.require_active_template_instance(template)
    return template


def _revalidate_safety_rule(
    rules: SafetyLegalRuleRepository, plan: MonthlyPlan
) -> SafetyLegalRule | None:
    """Plan이 사용했던 **정확한** 법정 Rule version을 다시 검증한다.

    version은 Plan의 `ConstraintAssessment.rule_version`에서 읽는다. 호출자가
    넘긴 값을 쓰지 않으므로 Confirm 기준을 바꿀 수 없다.
    """
    assessment = plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    if assessment is None:
        if plan.section("safety_education") is None:
            # 안전교육 Section이 없는 Template이면 재검증 대상이 없다.
            return None
        raise validation_failed(
            "safety_section_requires_constraint_assessment",
            FailureCategory.STRUCTURE_VALIDATION,
            "안전교육 Section이 있는데 ConstraintAssessment가 없어 "
            "확정 시 법정 Rule version을 재검증할 수 없다",
        )

    rule = monthly_gates.require_resolved_safety_rule(
        rules.get_legal_rule(assessment.rule_version), assessment.rule_version
    )
    monthly_gates.require_active_safety_rule(rule)
    return rule
