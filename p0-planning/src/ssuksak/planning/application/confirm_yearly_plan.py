"""Explicit teacher confirmation of a DRAFT Yearly Plan."""

from __future__ import annotations

from ..domain.yearly_plan import YearlyPlan
from .ports import Clock, PlanRepository
from .yearly_dto import ConfirmYearlyPlanCommand
from .yearly_support import require_actor, require_plan


class ConfirmYearlyPlan:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[YearlyPlan],
        clock: Clock,
    ) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: ConfirmYearlyPlanCommand) -> YearlyPlan:
        plan = require_plan(self._plans, command.plan_id)
        actor_id = require_actor(command.actor_id)
        confirmed = plan.confirm(
            actor_id=actor_id,
            occurred_at=self._clock.now(),
        )
        self._plans.save(confirmed.plan_id, confirmed)
        return confirmed
