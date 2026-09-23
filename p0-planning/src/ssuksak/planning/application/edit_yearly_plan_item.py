"""Teacher edit of one DRAFT Yearly item."""

from __future__ import annotations

from ..domain.yearly_plan import YearlyPlan
from .ports import Clock, PlanRepository
from .yearly_dto import EditYearlyPlanItemCommand
from .yearly_errors import YearlyApplicationError
from .yearly_support import require_actor, require_item_id, require_plan


class EditYearlyPlanItem:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[YearlyPlan],
        clock: Clock,
    ) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: EditYearlyPlanItemCommand) -> YearlyPlan:
        plan = require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("edit")
        item_id = require_item_id(command.item_id)
        actor_id = require_actor(command.actor_id)
        found = plan.find_item(item_id)
        if found is None:
            raise YearlyApplicationError(
                "yearly_item_not_found", f"Yearly item not found: {item_id}"
            )
        _, period = found
        edited = period.theme.edit_by_teacher(
            plan_id=plan.plan_id,
            new_value=command.new_value,
            actor_id=actor_id,
            occurred_at=self._clock.now(),
        )
        updated = plan.replace_item(item_id, edited)
        self._plans.save(updated.plan_id, updated)
        return updated
