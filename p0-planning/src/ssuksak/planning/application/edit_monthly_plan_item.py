"""EditMonthlyPlanItem Use Case.

CLAUDE.md §13.2·§13.3 / docs/screen-spec.md §6.1 — Yearly와 같은 Provenance 원칙:
- 교사 수정은 Evidence Source를 만들지 않는다. `TEACHER_EDIT`은 Evidence가 아니다.
- 기존 Evidence를 제거하지 않는다.
- **Generation Method를 MANUAL로 덮어쓰지 않는다.**
- `TEACHER_EDITED` Audit Event를 추가한다.

**Mutation Atomicity**
Yearly `edit_yearly_plan_item.py`는 실패 가능한 검사를 모두 Mutation 앞에 두는
것으로 충분했다. Monthly는 Mutation **이후** `validate_monthly_plan`을 다시
돌리므로 그것만으로는 부족하다. Repository가 같은 객체를 보유하므로 검증이
실패하면 저장하지 않아도 in-memory Plan에 변경이 남는다.

그래서 변경 대상 Cell의 가변 필드를 스냅샷으로 잡아 두고, 검증이 실패하면
**원상 복구한 뒤 예외를 전파**한다. 바뀌는 Cell이 정확히 하나이므로 복구 범위가
닫혀 있다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.constraint import CellState
from ..domain.errors import FailureCategory, validation_failed
from ..domain.monthly_plan import MonthlyPlan, MonthlyPlanItem
from ..domain.monthly_template import MonthlyTemplate
from ..domain.provenance import AuditEvent, AuditEventType, AuditTrail
from ..rules.monthly_cell_state import require_value_allowed, resolve_cell_state
from .confirm_yearly_plan import require_opaque_actor
from .monthly_cell_resolution import resolve_cell
from .monthly_dto import EditMonthlyPlanItemCommand, MonthlyPlanResult
from .monthly_ports import (
    MonthlyPlanRepository,
    MonthlyTemplateRepository,
)
from .ports import Clock
from .validate_monthly_plan import validate_monthly_plan

__all__ = ["EditMonthlyPlanItem", "require_monthly_plan"]


@dataclass(slots=True)
class _CellSnapshot:
    """복구에 필요한 가변 필드만 담는다."""

    item: MonthlyPlanItem
    value: str
    cell_state: CellState
    audit_events: list[AuditEvent]

    @staticmethod
    def of(item: MonthlyPlanItem) -> "_CellSnapshot":
        return _CellSnapshot(
            item=item,
            value=item.value,
            cell_state=item.cell_state,
            audit_events=list(item.audit.events),
        )

    def restore(self) -> None:
        self.item.value = self.value
        self.item.cell_state = self.cell_state
        self.item.audit = AuditTrail(list(self.audit_events))


class EditMonthlyPlanItem:
    def __init__(
        self,
        *,
        monthly_plan_repository: MonthlyPlanRepository,
        template_repository: MonthlyTemplateRepository,
        clock: Clock,
    ) -> None:
        self._plans = monthly_plan_repository
        self._templates = template_repository
        self._clock = clock

    def execute(self, command: EditMonthlyPlanItemCommand) -> MonthlyPlanResult:
        # ---- 실패 가능한 검사는 전부 Mutation 이전에 수행한다 ----
        plan = require_monthly_plan(self._plans, command.plan_id)

        # CONFIRMED는 read-only.
        plan.ensure_mutable("EditMonthlyPlanItem")

        # Actor Validation을 Mutation 전에.
        actor = require_opaque_actor(
            command.actor_id, rule="edit_requires_opaque_actor_id"
        )

        section, item = resolve_cell(plan, command.address)

        # Section 의미상 빈 문자열이 허용되는지.
        require_value_allowed(section.section_key, command.new_value)

        new_state = resolve_cell_state(plan, section.section_key, command.new_value)

        template = _require_template(self._templates, plan)

        # AuditEvent를 Mutation 전에 만들어 둔다. 여기서 실패하면 Plan은 그대로다.
        event = AuditEvent(
            event_type=AuditEventType.TEACHER_EDITED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id.value,
            item_id=item.item_id.value,
            actor_id=actor,
            previous_value=item.value,
            new_value=command.new_value,
            # 교사 수정이 Generation Method를 바꾸지 않는다.
            previous_method=item.generation.method,
            new_method=item.generation.method,
        )

        # ---------------------- 여기서부터 Mutation ----------------------
        snapshot = _CellSnapshot.of(item)
        item.value = command.new_value
        item.cell_state = new_state
        item.audit.append(event)

        try:
            validate_monthly_plan(
                plan,
                template=template,
                expected_school_year=plan.school_year,
                expected_classroom_ref=plan.classroom_ref,
            )
        except Exception:
            snapshot.restore()
            raise

        self._plans.save(plan)
        return MonthlyPlanResult(plan=plan)


def require_monthly_plan(
    plans: MonthlyPlanRepository, plan_id: str
) -> MonthlyPlan:
    plan = plans.get(plan_id)
    if plan is None:
        raise validation_failed(
            "target_monthly_plan_must_exist",
            FailureCategory.INPUT_VALIDATION,
            f"Monthly Plan을 찾을 수 없다: {plan_id}",
        )
    return plan


def _require_template(
    templates: MonthlyTemplateRepository, plan: MonthlyPlan
) -> MonthlyTemplate:
    """Plan이 생성될 때 쓴 Template을 다시 해석한다.

    Validation이 활성 Section 집합을 Template과 대조하므로 필요하다.
    Plan의 `template_ref`만 쓰고 요청자가 다른 Template을 지정할 수 없다.
    """
    template = templates.get_template(
        plan.template_ref.template_id, plan.template_ref.template_version
    )
    if template is None:
        raise validation_failed(
            "template_id_and_version_must_resolve_exactly",
            FailureCategory.REFERENCE_VALIDATION,
            f"Plan이 참조하는 Template을 찾을 수 없다: {plan.template_ref}",
        )
    return template
