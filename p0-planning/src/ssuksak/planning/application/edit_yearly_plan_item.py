"""EditYearlyPlanItem Use Case.

CLAUDE.md §13.2·§13.3 / docs/screen-spec.md §6.1:
- 교사 수정은 Evidence Source를 만들지 않는다. `TEACHER_EDIT`은 Evidence가 아니다.
- 기존 Evidence를 제거하지 않는다.
- Generation Method를 MANUAL로 덮어쓰지 않는다.
- `TEACHER_EDITED` Audit Event를 추가한다.

**Mutation Atomicity**
Actor Validation과 AuditEvent 생성을 모두 Mutation보다 **먼저** 수행한다.
Repository가 같은 객체를 보유하므로, 변경 후 예외가 나면 실패했는데도
Plan 변경이 누출된다. 그래서 실패할 수 있는 모든 검사를 앞으로 옮겼다.
"""

from __future__ import annotations

from ..domain.errors import FailureCategory, validation_failed
from ..domain.plan import YearlyPlan
from ..domain.provenance import AuditEvent, AuditEventType
from .confirm_yearly_plan import require_opaque_actor
from .dto import EditYearlyPlanItemCommand, YearlyPlanResult
from .ports import Clock, PlanRepository


class EditYearlyPlanItem:
    def __init__(self, *, plan_repository: PlanRepository, clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: EditYearlyPlanItemCommand) -> YearlyPlanResult:
        plan = _require_plan(self._plans, command.plan_id)

        # ---- 실패 가능한 검사는 전부 Mutation 이전에 수행한다 ----

        # CONFIRMED는 read-only.
        plan.ensure_mutable("EditYearlyPlanItem")

        # Actor Validation을 Mutation 전에.
        actor = require_opaque_actor(
            command.actor_id, rule="edit_requires_opaque_actor_id"
        )

        found = plan.find_item(
            item_id=command.address.item_id,
            period_key=command.address.period_key,
            semantic_key=command.address.semantic_key,
        )
        if found is None:
            raise validation_failed(
                "edit_target_item_must_exist",
                FailureCategory.INPUT_VALIDATION,
                f"대상 Item을 찾을 수 없다: {command.address}",
            )
        _, item = found

        if not command.new_value or not command.new_value.strip():
            raise validation_failed(
                "theme_is_required_and_non_blank_for_every_period",
                FailureCategory.REQUIRED_VALUE_VALIDATION,
                "교사 편집 값이 공백이다",
            )

        # AuditEvent를 Mutation 전에 만들어 둔다. 여기서 실패하면 Plan은 그대로다.
        event = AuditEvent(
            event_type=AuditEventType.TEACHER_EDITED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id.value,
            item_id=item.item_id.value,
            actor_id=actor,
            previous_value=item.value,
            new_value=command.new_value,
            previous_method=item.generation.method,
            new_method=item.generation.method,
        )

        # ---------------------- 여기서부터 Mutation ----------------------
        # generation을 넘기지 않으므로 Generation Method가 유지된다.
        plan.replace_item_value(item, command.new_value)
        item.audit.append(event)

        self._plans.save(plan)
        return YearlyPlanResult(plan=plan)


def _require_plan(plans: PlanRepository, plan_id: str) -> YearlyPlan:
    plan = plans.get(plan_id)
    if plan is None:
        raise validation_failed(
            "target_plan_must_exist",
            FailureCategory.INPUT_VALIDATION,
            f"Plan을 찾을 수 없다: {plan_id}",
        )
    return plan
