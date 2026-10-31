"""Teacher copy of one drill candidate into the Monthly Plan's drill Cell (as v2)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_plan import DRILL_COPY_GENERATION, MonthlyPlan
from ..domain.monthly_template_profile import DRILL_SECTION_KEY
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    GenerationMethodChange,
    ValueChange,
)
from .monthly_errors import MonthlyApplicationError
from .monthly_support import (
    load_plan_activity_catalog,
    require_actor,
    require_monthly_plan,
    with_fresh_monthly_verification,
)
from .ports import ActivityReferenceRepository, Clock, PlanRepository


@dataclass(frozen=True, slots=True)
class CopyMonthlyDrillCandidateCommand:
    plan_id: PlanId
    candidate_item_id: ItemId
    actor_id: ActorId


class CopyMonthlyDrillCandidate:
    """Copies the candidate's value and evidence at that moment; later edits of either side
    do not follow each other."""

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

    def execute(self, command: CopyMonthlyDrillCandidateCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("copy")
        actor_id = require_actor(command.actor_id)
        section = plan.section(DRILL_SECTION_KEY)
        if section is None:
            raise MonthlyApplicationError("monthly_drill_section_missing", "This Monthly Plan has no drill Section")
        found = (
            plan.drill_candidate(command.candidate_item_id)
            if isinstance(command.candidate_item_id, ItemId)
            else None
        )
        if found is None:
            raise MonthlyApplicationError(
                "monthly_drill_candidate_not_found", f"Drill candidate not found: {command.candidate_item_id}"
            )
        candidate = found.cell
        if not candidate.value.strip():
            raise MonthlyApplicationError("monthly_drill_candidate_blank", "The drill candidate is blank")
        cell = section.cells[0]
        source = next(
            (e.copied_from for e in reversed(cell.audit.events) if e.event_type is AuditEventType.CANDIDATE_COPIED),
            None,
        )
        # Another candidate with the same sentence is still a new source, so it is recorded.
        if (cell.value, cell.evidence, cell.generation, source) == (
            candidate.value, candidate.evidence, DRILL_COPY_GENERATION, candidate.item_id,
        ):
            return plan  # the Cell already holds this copy
        event = AuditEvent(
            event_type=AuditEventType.CANDIDATE_COPIED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id,
            item_id=cell.item_id,
            actor_id=actor_id,
            value_change=ValueChange(cell.value, candidate.value),
            generation_change=(
                None if cell.generation is None else GenerationMethodChange(cell.generation, DRILL_COPY_GENERATION)
            ),
            copied_from=candidate.item_id,
        )
        updated = plan.replace_cell(
            cell.item_id,
            replace(
                cell,
                value=candidate.value,
                cell_state=candidate.cell_state,
                evidence=candidate.evidence,
                generation=DRILL_COPY_GENERATION,
                audit=cell.audit.append(event),
            ),
        )
        updated = with_fresh_monthly_verification(updated, load_plan_activity_catalog(self._activities, updated))
        self._plans.save(updated.plan_id, updated)
        return updated
