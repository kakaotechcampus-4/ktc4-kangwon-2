"""Edit and confirm a DRAFT play-centred monthly plan (PLAY_MONTHLY, lifecycle L1).

2026-10-27 decisions:
- An edit changes one cell's value only. A generated cell keeps its Generation Method and
  evidence; the change is a TEACHER_EDITED event on that cell. A cell never written before (a
  teacher-input cell) becomes MANUAL on its first write. Saving the same value is a no-op.
- Confirm (M2-D09 · I-6) needs a theme, a rationale, and in each play section at least one row,
  every row named and linked to 1~3 content ids. Descriptions, teacher-input cells, habits,
  safety placement and health · nutrition may stay blank: ``play_monthly_notices`` reports the
  blank ones, and it never blocks confirm (M2-D13).

Teacher text is not checked against the AI sentence policy. Codes are internal, not public API.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.errors import DomainError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.play_monthly_plan import PlayMonthlyPlan
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    GenerationMethod,
    GenerationMethodDetail,
    ValueChange,
)
from ..domain.week_period import WeekId
from ..planner.play_monthly import CONTENT_MAX, CONTENT_MIN
from .ports import Clock, PlanRepository


class PlayMonthlyLifecycleError(DomainError):
    def __init__(self, code: str, detail: str, problems: tuple[str, ...] = ()) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.problems = problems


@dataclass(frozen=True, slots=True)
class EditPlayMonthlyCellCommand:
    plan_id: PlanId
    actor_id: ActorId
    item_id: ItemId
    new_value: str


@dataclass(frozen=True, slots=True)
class ConfirmPlayMonthlyPlanCommand:
    plan_id: PlanId
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class PlayMonthlyNotice:
    """A blank the teacher may want to fill; never a confirm failure or a legal judgement."""

    code: str  # SAFETY_UNPLACED · HABIT_BLANK · HEALTH_BLANK · NUTRITION_BLANK
    week_id: WeekId | None = None


class EditPlayMonthlyCell:
    def __init__(self, *, plan_repository: PlanRepository[PlayMonthlyPlan], clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: EditPlayMonthlyCellCommand) -> PlayMonthlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("edit")
        actor_id = _require_actor(command.actor_id)
        if not isinstance(command.item_id, ItemId):
            raise PlayMonthlyLifecycleError("invalid_item_id", "Edit requires ItemId")
        if not isinstance(command.new_value, str):
            raise PlayMonthlyLifecycleError("invalid_value", "Edit requires a string value")
        cell = plan.find_cell(command.item_id)
        if cell is None:
            raise PlayMonthlyLifecycleError(
                "play_monthly_cell_not_found", f"PlayMonthlyPlan cell not found: {command.item_id}"
            )
        if command.new_value == cell.value or not (command.new_value.strip() or cell.value.strip()):
            return plan  # same value, or blank to blank: no event, no write
        event = AuditEvent(
            event_type=AuditEventType.TEACHER_EDITED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=ValueChange(cell.value, command.new_value),
        )
        updated = plan.replace_cell(
            replace(
                cell,
                value=command.new_value,
                generation=cell.generation or GenerationMethodDetail(GenerationMethod.MANUAL),
                audit=cell.audit.append(event),
            )
        )
        self._plans.save(updated.plan_id, updated)
        return updated


class ConfirmPlayMonthlyPlan:
    def __init__(self, *, plan_repository: PlanRepository[PlayMonthlyPlan], clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: ConfirmPlayMonthlyPlanCommand) -> PlayMonthlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("confirm")
        actor_id = _require_actor(command.actor_id)
        problems = confirm_problems(plan)
        if problems:
            raise PlayMonthlyLifecycleError(
                "play_monthly_incomplete", "PlayMonthlyPlan cannot be confirmed", problems
            )
        confirmed = plan.confirm(actor_id=actor_id, occurred_at=self._clock.now())
        self._plans.save(confirmed.plan_id, confirmed)
        return confirmed


def confirm_problems(plan: PlayMonthlyPlan) -> tuple[str, ...]:
    problems: list[str] = []
    for name in ("theme", "rationale"):
        if not getattr(plan, name).value.strip():
            problems.append(f"{name}: blank")
    for section in ("together", "free_play"):
        rows = getattr(plan, section)
        if not rows:
            problems.append(f"{section}: no rows")
        for row in rows:
            where = f"{section}:{row.cell.item_id.value}"
            if not row.cell.value.strip():
                problems.append(f"{where}: blank name")
            if not CONTENT_MIN <= len(row.content_ids) <= CONTENT_MAX:
                problems.append(f"{where}: {len(row.content_ids)} content ids")
    return tuple(problems)


def play_monthly_notices(plan: PlayMonthlyPlan) -> tuple[PlayMonthlyNotice, ...]:
    notices = [
        PlayMonthlyNotice("SAFETY_UNPLACED", s.week_id)
        for s in plan.safety_weeks
        if s.candidate_item_id is None
    ]
    notices += [
        PlayMonthlyNotice("HABIT_BLANK", h.week_id) for h in plan.habits if not h.habit.cell.value.strip()
    ]
    notices += [
        PlayMonthlyNotice(code)
        for code, entry in (("HEALTH_BLANK", plan.health), ("NUTRITION_BLANK", plan.nutrition))
        if not entry.cell.value.strip()
    ]
    return tuple(notices)


def _require_plan(repository: PlanRepository[PlayMonthlyPlan], plan_id: object) -> PlayMonthlyPlan:
    if not isinstance(plan_id, PlanId):
        raise PlayMonthlyLifecycleError("invalid_plan_id", "PlayMonthlyPlan use cases require PlanId")
    plan = repository.get(plan_id)
    if not isinstance(plan, PlayMonthlyPlan):
        raise PlayMonthlyLifecycleError(
            "play_monthly_plan_not_found", f"PlayMonthlyPlan not found: {plan_id}"
        )
    return plan


def _require_actor(actor_id: object) -> ActorId:
    if not isinstance(actor_id, ActorId):
        raise PlayMonthlyLifecycleError(
            "opaque_actor_required", "PlayMonthlyPlan mutation requires ActorId"
        )
    return actor_id
