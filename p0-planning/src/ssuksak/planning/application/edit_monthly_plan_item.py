"""Teacher edit of one DRAFT Monthly Cell."""

from __future__ import annotations

from dataclasses import replace

from ..domain.errors import InvalidDomainValueError
from ..domain.monthly_plan import MonthlyPlan
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    ValueChange,
)
from ..rules.errors import MonthlyRuleError
from ..rules.monthly_cell_state import resolve_cell_state
from .monthly_dto import EditMonthlyPlanItemCommand
from .monthly_errors import MonthlyApplicationError
from .monthly_support import (
    load_plan_activity_catalog,
    require_actor,
    require_item_id,
    require_monthly_plan,
    with_fresh_monthly_verification,
)
from .ports import ActivityReferenceRepository, Clock, PlanRepository


class EditMonthlyPlanItem:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[MonthlyPlan],
        clock: Clock,
        activity_repository: ActivityReferenceRepository | None = None,
    ) -> None:
        self._plans = plan_repository
        self._clock = clock
        self._activities = activity_repository

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
        candidate = plan.safety_candidate(item_id)
        if found is None and candidate is None:
            raise MonthlyApplicationError(
                "monthly_cell_not_found", f"Monthly Cell not found: {item_id}"
            )
        cell = found[3] if found is not None else candidate.cell
        if found is not None and plan.safety_candidates and cell.section_key == "safety_education":
            # S-2: a week reads its placed candidate; edit the candidate or place another.
            raise MonthlyApplicationError(
                "monthly_safety_cell_not_editable",
                "Weekly safety Cells of a candidate-mode Plan are set by placement",
            )
        if cell.value == command.new_value:
            raise MonthlyApplicationError(
                "monthly_cell_value_unchanged", "Teacher edit must change the Cell value"
            )
        if cell.generation is None:
            raise MonthlyApplicationError(
                "monthly_cell_generation_missing",
                "Editable Monthly Cell must preserve its previous Generation Method",
            )
        assessment = plan.cell_state_assessment(cell)
        # The two checks that depend only on the new value: a theme Cell cannot
        # be empty, and a blank Cell cannot become another blank value. Both are
        # the teacher's input, so they surface as an invalid Cell value.
        try:
            value_change = ValueChange(cell.value, command.new_value)
            cell_state = resolve_cell_state(
                section_key=cell.section_key,
                value=command.new_value,
                assessment=assessment,
            )
        except (InvalidDomainValueError, MonthlyRuleError) as error:
            raise MonthlyApplicationError(
                "invalid_monthly_cell_value",
                "Teacher edit value is not allowed for this Cell",
            ) from error
        event = AuditEvent(
            AuditEventType.TEACHER_EDITED,
            self._clock.now(),
            plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=value_change,
        )
        updated_cell = replace(
            cell,
            value=command.new_value,
            cell_state=cell_state,
            audit=cell.audit.append(event),
        )
        updated = (
            plan.replace_safety_candidate(updated_cell)
            if candidate is not None
            else plan.replace_cell(item_id, updated_cell)
        )
        catalog = load_plan_activity_catalog(self._activities, updated)
        updated = with_fresh_monthly_verification(updated, catalog)
        self._plans.save(updated.plan_id, updated)
        return updated
