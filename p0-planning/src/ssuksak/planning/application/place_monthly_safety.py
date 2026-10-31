"""Teacher placement of one safety candidate per week in a candidate-mode Monthly Plan (S-1)."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_plan import MonthlyPlan
from ..domain.week_period import WeekId
from .monthly_errors import MonthlyApplicationError
from .monthly_support import require_actor, require_monthly_plan
from .ports import Clock, PlanRepository


@dataclass(frozen=True, slots=True)
class PlaceMonthlySafetyCommand:
    plan_id: PlanId
    week_id: WeekId
    candidate_item_id: ItemId | None  # None clears the week
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class MonthlySafetyNotice:
    """A week without safety education; it never blocks confirm."""

    code: str  # SAFETY_UNPLACED | SAFETY_BLANK
    week_id: WeekId


class PlaceMonthlySafety:
    def __init__(self, *, plan_repository: PlanRepository[MonthlyPlan], clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: PlaceMonthlySafetyCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("place_safety")
        actor_id = require_actor(command.actor_id)
        if not plan.safety_candidates:
            raise MonthlyApplicationError(
                "monthly_safety_candidates_missing", "This Monthly Plan has no safety candidates"
            )
        week = next((s for s in plan.safety_weeks if s.week_id == command.week_id), None)
        if week is None:
            raise MonthlyApplicationError("monthly_week_not_found", f"Monthly week not found: {command.week_id}")
        candidate = command.candidate_item_id
        if candidate is not None and (not isinstance(candidate, ItemId) or plan.safety_candidate(candidate) is None):
            raise MonthlyApplicationError(
                "monthly_safety_candidate_not_found", f"Safety candidate not found: {candidate}"
            )
        if candidate == week.candidate_item_id:
            return plan
        updated = plan.place_safety(command.week_id, candidate, actor_id=actor_id, occurred_at=self._clock.now())
        self._plans.save(updated.plan_id, updated)
        return updated


def monthly_safety_notices(plan: MonthlyPlan) -> tuple[MonthlySafetyNotice, ...]:
    # A placed candidate whose sentence a teacher cleared is as empty as an unplaced week.
    texts = {c.cell.item_id: c.cell.value for c in plan.safety_candidates}
    return tuple(
        MonthlySafetyNotice("SAFETY_UNPLACED" if s.candidate_item_id is None else "SAFETY_BLANK", s.week_id)
        for s in plan.safety_weeks
        if s.candidate_item_id is None or not texts[s.candidate_item_id].strip()
    )
