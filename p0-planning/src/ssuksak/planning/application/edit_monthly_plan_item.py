"""Teacher edit of one DRAFT Monthly Cell."""

from __future__ import annotations

from dataclasses import replace

from ..domain.monthly_plan import MonthlyPlan
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    GenerationMethod,
    GenerationMethodChange,
    GenerationMethodDetail,
    ValueChange,
)
from ..rules.monthly_cell_state import resolve_cell_state
from .monthly_dto import EditMonthlyPlanItemCommand
from .monthly_errors import MonthlyApplicationError
from .monthly_support import require_actor, require_item_id, require_monthly_plan
from .ports import Clock, PlanRepository


class EditMonthlyPlanItem:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[MonthlyPlan],
        clock: Clock,
    ) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: EditMonthlyPlanItemCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("edit")
        item_id = require_item_id(command.item_id)
        actor_id = require_actor(command.actor_id)
        if not isinstance(command.new_value, str):
            raise MonthlyApplicationError(
                "invalid_monthly_cell_value", "Monthly Cell value must be a string"
            )
        found = plan.find_cell(item_id)
        if found is None:
            raise MonthlyApplicationError(
                "monthly_cell_not_found", f"Monthly Cell not found: {item_id}"
            )
        _, _, _, cell = found
        if cell.value == command.new_value:
            raise MonthlyApplicationError(
                "monthly_cell_value_unchanged", "Teacher edit must change the Cell value"
            )
        if cell.generation is None:
            raise MonthlyApplicationError(
                "monthly_cell_generation_missing",
                "Editable Monthly Cell must preserve its previous Generation Method",
            )
        generation = GenerationMethodDetail(GenerationMethod.TEACHER_EDIT)
        event = AuditEvent(
            AuditEventType.TEACHER_EDITED,
            self._clock.now(),
            plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=ValueChange(cell.value, command.new_value),
            generation_change=GenerationMethodChange(cell.generation, generation),
        )
        assessment = plan.constraint("STATUTORY_SAFETY_EDUCATION")
        updated_cell = replace(
            cell,
            value=command.new_value,
            cell_state=resolve_cell_state(
                section_key=cell.section_key,
                value=command.new_value,
                assessment=assessment,
            ),
            generation=generation,
            audit=cell.audit.append(event),
        )
        updated = plan.replace_cell(item_id, updated_cell)
        self._plans.save(updated.plan_id, updated)
        return updated
