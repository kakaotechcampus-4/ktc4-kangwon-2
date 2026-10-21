"""Teacher edit and confirmation of a DRAFT Weekly Plan (docs/weekly-plan-contract.md §10-2 · §10-4).

Same flow as the monthly use cases. Verification re-runs on every change: its
findings never block a teacher value or a confirmation (§11-2, ADR-037); a verifier
that cannot run stops the save. Regenerate is W4b.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.errors import InvalidDomainValueError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_plan import MonthlyPlan
from ..domain.plan import PlanStatus
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    GenerationMethod,
    GenerationMethodDetail,
    ValueChange,
)
from ..domain.weekly_plan import WEEKLY_INSTITUTION_INPUT_SECTION_KEYS, WeeklyPlan
from ..rules.errors import MonthlyRuleError
from ..rules.monthly_cell_state import resolve_cell_state
from ..rules.weekly_verification import verify_weekly_plan
from .generate_weekly_plan import WeeklyApplicationError
from .monthly_support import load_plan_activity_catalog, require_actor, require_item_id
from .ports import ActivityReferenceRepository, Clock, PlanRepository

STATUTORY_SAFETY = "STATUTORY_SAFETY_EDUCATION"


@dataclass(frozen=True, slots=True)
class EditWeeklyPlanCellCommand:
    plan_id: PlanId
    item_id: ItemId
    new_value: str
    actor_id: ActorId


@dataclass(frozen=True, slots=True)
class ConfirmWeeklyPlanCommand:
    plan_id: PlanId
    actor_id: ActorId


class _WeeklyLifecycle:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[WeeklyPlan],
        parent_plan_repository: PlanRepository[MonthlyPlan],
        clock: Clock,
        activity_repository: ActivityReferenceRepository | None = None,
    ) -> None:
        self._plans = plan_repository
        self._parents = parent_plan_repository
        self._clock = clock
        self._activities = activity_repository

    def _plan(self, plan_id: object) -> WeeklyPlan:
        if not isinstance(plan_id, PlanId):
            raise WeeklyApplicationError("invalid_plan_id", "Weekly use cases require PlanId")
        plan = self._plans.get(plan_id)
        if plan is None:
            raise WeeklyApplicationError("weekly_plan_not_found", f"Weekly Plan not found: {plan_id}")
        if not isinstance(plan, WeeklyPlan):
            raise WeeklyApplicationError(
                "repository_contract_violation", "PlanRepository returned a non-WeeklyPlan value"
            )
        return plan

    def _verified(self, plan: WeeklyPlan) -> WeeklyPlan:
        """Fresh report against the confirmed parent; findings are guidance only (§11-2)."""
        parent = self._parents.get(plan.parent_lineage.parent_plan_id)
        if not isinstance(parent, MonthlyPlan):
            raise WeeklyApplicationError(
                "parent_monthly_plan_not_found",
                f"Parent Monthly Plan not found: {plan.parent_lineage.parent_plan_id}",
            )
        try:
            catalog = load_plan_activity_catalog(self._activities, plan)
            report = verify_weekly_plan(plan, catalog, parent)
        except Exception as exc:  # a verifier that cannot run is not a finding
            raise WeeklyApplicationError(
                "weekly_verification_failed", "Weekly rule verification failed before the Plan was saved"
            ) from exc
        return replace(plan, verification_report=report)


class EditWeeklyPlanCell(_WeeklyLifecycle):
    def execute(self, command: EditWeeklyPlanCellCommand) -> WeeklyPlan:
        plan = self._plan(command.plan_id)
        plan.ensure_mutable("edit")
        item_id = require_item_id(command.item_id)
        actor_id = require_actor(command.actor_id)
        if not isinstance(command.new_value, str):
            raise WeeklyApplicationError("invalid_weekly_cell_value", "Weekly Cell value must be a string")
        cell = plan.find_cell(item_id)
        if cell is None:
            raise WeeklyApplicationError("weekly_cell_not_found", f"Weekly Cell not found: {item_id}")
        if cell.value == command.new_value:
            raise WeeklyApplicationError(
                "weekly_cell_value_unchanged", "Teacher edit must change the Cell value"
            )
        assessment = next(
            (a for a in plan.constraint_assessments if a.constraint.code == STATUTORY_SAFETY), None
        )
        try:  # empty theme and blank -> blank are the teacher's input, so an invalid value
            value_change = ValueChange(cell.value, command.new_value)
            cell_state = resolve_cell_state(
                section_key=cell.section_key, value=command.new_value, assessment=assessment
            )
        except (InvalidDomainValueError, MonthlyRuleError) as error:
            raise WeeklyApplicationError(
                "invalid_weekly_cell_value", "Teacher edit value is not allowed for this Cell"
            ) from error
        generation = cell.generation
        # §10-2: a teacher-input Cell becomes MANUAL on its first write and stays MANUAL.
        # Decision 2026-10-21: recorded on the Cell only; TEACHER_EDITED keeps the value change.
        if generation is None and cell.section_key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS:
            generation = GenerationMethodDetail(GenerationMethod.MANUAL)
        event = AuditEvent(
            AuditEventType.TEACHER_EDITED,
            self._clock.now(),
            plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=value_change,
        )
        updated = plan.replace_cell(item_id, replace(
            cell,
            value=command.new_value,
            cell_state=cell_state,
            generation=generation,
            audit=cell.audit.append(event),
        ))
        updated = self._verified(updated)
        self._plans.save(updated.plan_id, updated)
        return updated


class ConfirmWeeklyPlan(_WeeklyLifecycle):
    """Idempotent: an already CONFIRMED Plan comes back unchanged, no event, no re-check.
    Confirm never submits or sends anything."""

    def execute(self, command: ConfirmWeeklyPlanCommand) -> WeeklyPlan:
        plan = self._plan(command.plan_id)
        actor_id = require_actor(command.actor_id)
        if plan.status is PlanStatus.CONFIRMED:
            return plan
        confirmed = self._verified(plan).confirm(actor_id=actor_id, occurred_at=self._clock.now())
        self._plans.save(confirmed.plan_id, confirmed)
        return confirmed
