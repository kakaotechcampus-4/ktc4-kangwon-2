"""Edit, arrange and confirm a DRAFT play-centred monthly plan (PLAY_MONTHLY, lifecycle L1~L3).

2026-10-27 decisions:
- An edit changes one cell's value only. A generated cell keeps its Generation Method and
  evidence; the change is a TEACHER_EDITED event on that cell. A cell never written before (a
  teacher-input cell) becomes MANUAL on its first write. Saving the same value is a no-op.
- A play's curriculum links (M2-D18, I-1 · I-2) are 1~3 unique content ids of the plan's own
  curriculum catalog version. Changing them keeps the generation-time CURRICULUM evidence and
  records a TEACHER_EDITED event with a ``link_change`` only, so the play name does not count as
  teacher-edited text. The official content text is never stored; it is read from the Reference.
- Rows (M2-D03, I-3): a teacher adds a blank row at the end of a section or deletes a row. The
  deleted row is archived whole in the plan; ids are never reused; there is no undo or reorder.
  A new row's cells start without generation and become MANUAL on their first write.
- Safety (M2-D08, I-3): each week holds at most one kept candidate; a candidate may be reused
  across weeks; ``None`` clears the week. Rows and placement are ARRANGEMENT_CHANGED events.
- Confirm (M2-D09 · I-6) needs a theme, a rationale, and in each play section at least one row,
  every row named and linked to 1~3 content ids. Descriptions, teacher-input cells, habits,
  safety placement and health · nutrition may stay blank: ``play_monthly_notices`` reports the
  blank ones, and it never blocks confirm (M2-D13).

Teacher text is not checked against the AI sentence policy. Codes are internal, not public API.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..domain.errors import DomainError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.play_monthly_plan import PLAY_SECTIONS, PlayActivity, PlayMonthlyCell, PlayMonthlyPlan
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    GenerationMethod,
    GenerationMethodDetail,
    LinkChange,
    ValueChange,
)
from ..domain.week_period import WeekId
from ..planner.play_monthly import CONTENT_MAX, CONTENT_MIN
from .generate_play_project_plan import CurriculumReferenceRepository
from .ports import Clock, IdGenerator, PlanRepository


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
class EditPlayMonthlyContentIdsCommand:
    plan_id: PlanId
    actor_id: ActorId
    item_id: ItemId  # the play's name cell
    content_ids: Sequence[str]


@dataclass(frozen=True, slots=True)
class AddPlayMonthlyActivityCommand:
    plan_id: PlanId
    actor_id: ActorId
    section: str  # together · free_play


@dataclass(frozen=True, slots=True)
class RemovePlayMonthlyActivityCommand:
    plan_id: PlanId
    actor_id: ActorId
    item_id: ItemId  # the play's name cell


@dataclass(frozen=True, slots=True)
class PlacePlayMonthlySafetyCommand:
    plan_id: PlanId
    actor_id: ActorId
    week_id: WeekId
    candidate_item_id: ItemId | None  # None clears the week


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


class EditPlayMonthlyContentIds:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[PlayMonthlyPlan],
        curriculum_repository: CurriculumReferenceRepository,
        clock: Clock,
    ) -> None:
        self._plans = plan_repository
        self._curriculum = curriculum_repository
        self._clock = clock

    def execute(self, command: EditPlayMonthlyContentIdsCommand) -> PlayMonthlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("edit")
        actor_id = _require_actor(command.actor_id)
        if not isinstance(command.item_id, ItemId):
            raise PlayMonthlyLifecycleError("invalid_item_id", "Edit requires ItemId")
        activity = plan.activity(command.item_id)
        if activity is None:
            raise PlayMonthlyLifecycleError(
                "play_monthly_activity_not_found", f"PlayMonthlyPlan play not found: {command.item_id}"
            )
        ids = command.content_ids
        if not isinstance(ids, (list, tuple)) or not all(isinstance(i, str) for i in ids):
            raise PlayMonthlyLifecycleError("invalid_content_ids", "content_ids must be a list of strings")
        ids = tuple(ids)
        if ids == activity.content_ids:
            return plan
        references = plan.references
        catalog = self._curriculum.get_catalog(
            references.curriculum_catalog_id, references.curriculum_catalog_version
        )
        if catalog is None or not catalog.is_active:
            raise PlayMonthlyLifecycleError(
                "curriculum_reference_unavailable", "The plan's curriculum catalog version is not available"
            )
        problems = []
        if not CONTENT_MIN <= len(ids) <= CONTENT_MAX:
            problems.append(f"{len(ids)} content ids, needs {CONTENT_MIN}~{CONTENT_MAX}")
        if len(ids) != len(set(ids)):
            problems.append("duplicate content id")
        problems += [f"{i}: not in {catalog.catalog_version}" for i in ids if catalog.get(i) is None]
        if problems:
            raise PlayMonthlyLifecycleError(
                "invalid_content_ids", "Curriculum links rejected", tuple(problems)
            )
        event = AuditEvent(
            event_type=AuditEventType.TEACHER_EDITED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id,
            item_id=activity.cell.item_id,
            actor_id=actor_id,
            link_change=LinkChange(activity.content_ids, ids, catalog.catalog_version),
        )
        updated = plan.replace_activity(
            replace(
                activity,
                content_ids=ids,
                cell=replace(activity.cell, audit=activity.cell.audit.append(event)),
            )
        )
        self._plans.save(updated.plan_id, updated)
        return updated


class AddPlayMonthlyActivity:
    def __init__(
        self, *, plan_repository: PlanRepository[PlayMonthlyPlan], id_generator: IdGenerator, clock: Clock
    ) -> None:
        self._plans = plan_repository
        self._ids = id_generator
        self._clock = clock

    def execute(self, command: AddPlayMonthlyActivityCommand) -> PlayMonthlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("add")
        actor_id = _require_actor(command.actor_id)
        if command.section not in PLAY_SECTIONS:
            raise PlayMonthlyLifecycleError("invalid_section", f"Unknown play section: {command.section}")
        now = self._clock.now()

        def blank(item_id: ItemId, semantic_key: str) -> PlayMonthlyCell:
            created = AuditEvent(
                event_type=AuditEventType.CREATED,
                occurred_at=now,
                plan_id=plan.plan_id,
                item_id=item_id,
                actor_id=actor_id,
            )
            return PlayMonthlyCell(item_id=item_id, semantic_key=semantic_key, audit=AuditHistory((created,)))

        name_id = self._ids.new_item_id()
        key = f"{command.section}.{name_id.value}"
        row = PlayActivity(blank(name_id, key), blank(self._ids.new_item_id(), f"{key}.description"), ())
        updated = plan.add_activity(command.section, row, actor_id=actor_id, occurred_at=now)
        self._plans.save(updated.plan_id, updated)
        return updated


class RemovePlayMonthlyActivity:
    def __init__(self, *, plan_repository: PlanRepository[PlayMonthlyPlan], clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: RemovePlayMonthlyActivityCommand) -> PlayMonthlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("remove")
        actor_id = _require_actor(command.actor_id)
        if not isinstance(command.item_id, ItemId) or plan.activity(command.item_id) is None:
            raise PlayMonthlyLifecycleError(
                "play_monthly_activity_not_found", f"PlayMonthlyPlan play not found: {command.item_id}"
            )
        updated = plan.remove_activity(command.item_id, actor_id=actor_id, occurred_at=self._clock.now())
        self._plans.save(updated.plan_id, updated)
        return updated


class PlacePlayMonthlySafety:
    def __init__(self, *, plan_repository: PlanRepository[PlayMonthlyPlan], clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: PlacePlayMonthlySafetyCommand) -> PlayMonthlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("place")
        actor_id = _require_actor(command.actor_id)
        week = next((s for s in plan.safety_weeks if s.week_id == command.week_id), None)
        if week is None:
            raise PlayMonthlyLifecycleError(
                "play_monthly_week_not_found", f"PlayMonthlyPlan week not found: {command.week_id}"
            )
        candidate = command.candidate_item_id
        if candidate is not None and candidate not in {c.cell.item_id for c in plan.safety_candidates}:
            raise PlayMonthlyLifecycleError(
                "play_monthly_safety_candidate_not_found", f"Safety candidate not found: {candidate}"
            )
        if candidate == week.candidate_item_id:
            return plan
        updated = plan.place_safety(
            command.week_id, candidate, actor_id=actor_id, occurred_at=self._clock.now()
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
