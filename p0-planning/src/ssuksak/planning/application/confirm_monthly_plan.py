"""Explicit teacher confirmation of a DRAFT Monthly Plan.

Confirm is idempotent at this use-case boundary: a retry on an already
CONFIRMED Plan returns the stored Plan unchanged. A CONFIRMED Plan is
immutable, so the retry re-runs no verification and adds no audit event.
``MonthlyPlan.confirm`` itself still rejects a second transition.
"""

from __future__ import annotations

from ..domain.monthly_plan import MonthlyPlan
from ..domain.plan import PlanStatus
from .monthly_dto import ConfirmMonthlyPlanCommand
from .monthly_support import (
    load_plan_activity_catalog,
    require_actor,
    require_monthly_plan,
    with_fresh_monthly_verification,
)
from .ports import ActivityReferenceRepository, Clock, PlanRepository


class ConfirmMonthlyPlan:
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

    def execute(self, command: ConfirmMonthlyPlanCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        actor_id = require_actor(command.actor_id)
        if plan.status is PlanStatus.CONFIRMED:
            return plan
        catalog = load_plan_activity_catalog(self._activities, plan)
        verified = with_fresh_monthly_verification(plan, catalog)
        confirmed = verified.confirm(
            actor_id=actor_id, occurred_at=self._clock.now()
        )
        self._plans.save(confirmed.plan_id, confirmed)
        return confirmed
