"""Select, edit and confirm a DRAFT play-project yearly plan (ADR-042 PLAY_PROJECT).

2026-10-26 decisions: a selection save records one plan-level CANDIDATES_SELECTED per changed
period (who · when · which period · kept row_keys before and after, in document order); a DRAFT
may keep 0..N candidates per period so the teacher can stop and come back; confirm needs exactly
N in every layout period. Only kept candidates are editable, and ``learning`` is not free text —
it renders the curriculum Reference its CURRICULUM evidence cites. Swapping unkept candidates
("다른 놀이") is a later slice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..domain.errors import DomainError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.play_project_plan import PlayProjectLayout, PlayProjectYearlyPlan
from .generate_play_project_plan import PLAY_PROJECT_LAYOUT_V0_2
from .ports import Clock, PlanRepository

PLAY_PROJECT_LAYOUTS = {PLAY_PROJECT_LAYOUT_V0_2.layout_version: PLAY_PROJECT_LAYOUT_V0_2}
EDITABLE_FIELDS = ("play_name", "materials", "support_direction")


class PlayProjectApplicationError(DomainError):
    def __init__(self, code: str, detail: str, problems: tuple[str, ...] = ()) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.problems = problems


@dataclass(frozen=True, slots=True)
class SavePlayProjectSelectionCommand:
    plan_id: PlanId
    actor_id: ActorId
    # period_key -> kept row_keys in document order; periods left out stay as they are
    selections: Mapping[str, Sequence[str]]


@dataclass(frozen=True, slots=True)
class EditPlayProjectItemCommand:
    plan_id: PlanId
    actor_id: ActorId
    item_id: ItemId
    new_value: str


@dataclass(frozen=True, slots=True)
class ConfirmPlayProjectPlanCommand:
    plan_id: PlanId
    actor_id: ActorId


class SavePlayProjectSelection:
    def __init__(
        self, *, plan_repository: PlanRepository[PlayProjectYearlyPlan], clock: Clock
    ) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: SavePlayProjectSelectionCommand) -> PlayProjectYearlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("select")
        actor_id = _require_actor(command.actor_id)
        layout = _layout(plan)
        # Check every period before applying any: one bad period saves nothing.
        selections: dict[str, tuple[str, ...]] = {}
        problems: list[str] = []
        for period_key, keys in command.selections.items():
            period = next((p for p in plan.periods if p.period.key == period_key), None)
            kept = tuple(keys) if not isinstance(keys, str) else (keys,)
            if period is None:
                problems.append(f"{period_key}: unknown period")
                continue
            candidates = {row.row_key for row in period.candidates}
            if len(kept) != len(set(kept)):
                problems.append(f"{period_key}: duplicate candidate")
            if not set(kept) <= candidates:
                problems.append(f"{period_key}: unknown candidate")
            if len(kept) > layout.selected_per_period:
                problems.append(f"{period_key}: more than {layout.selected_per_period}")
            selections[period_key] = kept
        if problems:
            raise PlayProjectApplicationError(
                "invalid_selection", "Play-project selection rejected", tuple(problems)
            )
        updated = plan.select(selections, actor_id=actor_id, occurred_at=self._clock.now())
        if updated.audit == plan.audit:
            return plan  # same selection and order: no event, no write
        self._plans.save(updated.plan_id, updated)
        return updated


class EditPlayProjectItem:
    def __init__(
        self, *, plan_repository: PlanRepository[PlayProjectYearlyPlan], clock: Clock
    ) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: EditPlayProjectItemCommand) -> PlayProjectYearlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("edit")
        actor_id = _require_actor(command.actor_id)
        if not isinstance(command.item_id, ItemId):
            raise PlayProjectApplicationError("invalid_item_id", "Edit requires ItemId")
        found = plan.find_item(command.item_id)
        if found is None:
            raise PlayProjectApplicationError(
                "play_project_item_not_found", f"Play-project item not found: {command.item_id}"
            )
        period, row, name = found
        if name not in EDITABLE_FIELDS:
            raise PlayProjectApplicationError(
                "field_not_editable", f"{name} renders the curriculum Reference"
            )
        if row.row_key not in period.selected:
            raise PlayProjectApplicationError(
                "candidate_not_selected", "Only a kept candidate can be edited"
            )
        edited = getattr(row, name).edit_by_teacher(
            plan_id=plan.plan_id,
            new_value=command.new_value,
            actor_id=actor_id,
            occurred_at=self._clock.now(),
        )
        updated = plan.replace_item(command.item_id, edited)
        self._plans.save(updated.plan_id, updated)
        return updated


class ConfirmPlayProjectPlan:
    def __init__(
        self, *, plan_repository: PlanRepository[PlayProjectYearlyPlan], clock: Clock
    ) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: ConfirmPlayProjectPlanCommand) -> PlayProjectYearlyPlan:
        plan = _require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("confirm")
        actor_id = _require_actor(command.actor_id)
        layout = _layout(plan)
        present = {p.period.key: p for p in plan.periods}
        problems: list[str] = []
        for period in layout.periods:
            rows = present.get(period.key)
            if rows is None:
                problems.append(f"{period.key}: missing period")
            elif len(rows.selected) != layout.selected_per_period:
                problems.append(
                    f"{period.key}: {len(rows.selected)} kept, needs {layout.selected_per_period}"
                )
        if problems:
            raise PlayProjectApplicationError(
                "selection_incomplete", "Play-project plan cannot be confirmed", tuple(problems)
            )
        confirmed = plan.confirm(actor_id=actor_id, occurred_at=self._clock.now())
        self._plans.save(confirmed.plan_id, confirmed)
        return confirmed


def _require_plan(
    repository: PlanRepository[PlayProjectYearlyPlan], plan_id: object
) -> PlayProjectYearlyPlan:
    if not isinstance(plan_id, PlanId):
        raise PlayProjectApplicationError("invalid_plan_id", "Play-project use cases require PlanId")
    plan = repository.get(plan_id)
    if not isinstance(plan, PlayProjectYearlyPlan):
        raise PlayProjectApplicationError(
            "play_project_plan_not_found", f"Play-project Plan not found: {plan_id}"
        )
    return plan


def _require_actor(actor_id: object) -> ActorId:
    if not isinstance(actor_id, ActorId):
        raise PlayProjectApplicationError(
            "opaque_actor_required", "Play-project mutation requires ActorId"
        )
    return actor_id


def _layout(plan: PlayProjectYearlyPlan) -> PlayProjectLayout:
    layout = PLAY_PROJECT_LAYOUTS.get(plan.layout_version)
    if layout is None:
        raise PlayProjectApplicationError(
            "unknown_layout", f"Unknown play-project layout: {plan.layout_version}"
        )
    return layout
