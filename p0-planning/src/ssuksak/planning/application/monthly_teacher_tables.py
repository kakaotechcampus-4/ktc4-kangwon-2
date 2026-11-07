"""Split · remove · resize the monthly v1 teacher tables (Human Decision 2026-11-05, 하민).

The same operations as the play monthly special-activity timetable (ADR-047), on any of the three
v1 tables (행사 일정 · 특성화 시간표 · 특별활동 시간표). Writing a cell goes through
``EditMonthlyPlanItem``. A CONFIRMED Plan refuses every one of them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace

from ..domain.errors import InvalidDomainValueError
from ..domain.identifiers import ActorId, ItemId, PlanId
from ..domain.monthly_plan import MonthlyPlan
from ..domain.play_monthly_plan import (
    MAX_SPLIT_DEPTH,
    PlayMonthlyCell,
    TimetableTooNarrowError,
)
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    SplitAxis,
    TimetableChange,
    TimetableOperation,
)
from .monthly_errors import MonthlyApplicationError
from .monthly_support import require_actor, require_monthly_plan
from .ports import Clock, IdGenerator, PlanRepository


@dataclass(frozen=True, slots=True)
class SplitMonthlyTableCellCommand:
    plan_id: PlanId
    actor_id: ActorId
    item_id: ItemId  # a content cell of a teacher table
    axis: SplitAxis


@dataclass(frozen=True, slots=True)
class RemoveMonthlyTableCellCommand:
    plan_id: PlanId
    actor_id: ActorId
    item_id: ItemId


@dataclass(frozen=True, slots=True)
class ResizeMonthlyTableCommand:
    """Exactly one target: a boundary (``split_id`` + ``ratio``) or one table's whole size."""

    plan_id: PlanId
    actor_id: ActorId
    split_id: ItemId | None = None
    ratio: int | None = None
    table_key: str | None = None
    column_widths: tuple[int, ...] | None = None
    height_mm: int | None = None


def _content_cell(plan: MonthlyPlan, item_id: object) -> tuple[int, int]:
    """(table index, column) of a content cell. Titles never split."""
    found = (
        next(((i, col) for i, t in enumerate(plan.tables) if (col := t.column_of(item_id)) is not None), None)
        if isinstance(item_id, ItemId)
        else None
    )
    if found is None:
        raise MonthlyApplicationError("monthly_table_cell_not_found", f"Table cell not found: {item_id}")
    return found


@contextmanager
def _limits() -> Iterator[None]:
    """A split or resize past the play monthly limits is the caller's request to refuse."""
    try:
        yield
    except TimetableTooNarrowError as error:
        raise MonthlyApplicationError("timetable_width_limit", str(error)) from error
    except InvalidDomainValueError as error:
        raise MonthlyApplicationError("invalid_timetable_size", str(error)) from error


class SplitMonthlyTableCell:
    def __init__(self, *, plan_repository: PlanRepository[MonthlyPlan], id_generator: IdGenerator, clock: Clock) -> None:
        self._plans = plan_repository
        self._ids = id_generator
        self._clock = clock

    def execute(self, command: SplitMonthlyTableCellCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("split")
        actor_id = require_actor(command.actor_id)
        index, column = _content_cell(plan, command.item_id)
        table = plan.tables[index]
        if not isinstance(command.axis, SplitAxis):
            raise MonthlyApplicationError("invalid_axis", "Split requires a SplitAxis")
        if table.depth_of(command.item_id) >= MAX_SPLIT_DEPTH:
            raise MonthlyApplicationError("timetable_split_limit", f"A column splits at most {MAX_SPLIT_DEPTH} deep")
        now = self._clock.now()
        item_id, split_id = self._ids.new_item_id(), self._ids.new_item_id()
        created = AuditEvent(
            event_type=AuditEventType.CREATED, occurred_at=now, plan_id=plan.plan_id, item_id=item_id, actor_id=actor_id
        )
        new_cell = PlayMonthlyCell(
            item_id=item_id,
            semantic_key=table.next_key(column, plan.removed_table_cells),
            audit=AuditHistory((created,)),
        )
        change = TimetableChange(
            TimetableOperation.SPLIT,
            split_id=split_id,
            axis=command.axis,
            cell_id=command.item_id,
            new_cell_id=item_id,
            table_key=table.table_key,
        )
        with _limits():
            updated = plan.with_table(
                index,
                table.split(command.item_id, command.axis, split_id, new_cell),
                change=change,
                actor_id=actor_id,
                occurred_at=now,
            )
        self._plans.save(updated.plan_id, updated)
        return updated


class RemoveMonthlyTableCell:
    def __init__(self, *, plan_repository: PlanRepository[MonthlyPlan], clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: RemoveMonthlyTableCellCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("remove")
        actor_id = require_actor(command.actor_id)
        index, _ = _content_cell(plan, command.item_id)
        table = plan.tables[index]
        parent = table.parent_of(command.item_id)
        if parent is None:
            raise MonthlyApplicationError(
                "timetable_last_cell", "A column keeps at least one cell; clear it instead"
            )
        removed = next(c.cell for c in parent.children if c.cell is not None and c.cell.item_id == command.item_id)
        change = TimetableChange(
            TimetableOperation.REMOVE,
            split_id=parent.split_id,
            axis=parent.axis,
            cell_id=command.item_id,
            table_key=table.table_key,
        )
        with _limits():
            updated = plan.with_table(
                index,
                table.without(parent, command.item_id),
                change=change,
                actor_id=actor_id,
                occurred_at=self._clock.now(),
                removed=removed,
            )
        self._plans.save(updated.plan_id, updated)
        return updated


class ResizeMonthlyTable:
    def __init__(self, *, plan_repository: PlanRepository[MonthlyPlan], clock: Clock) -> None:
        self._plans = plan_repository
        self._clock = clock

    def execute(self, command: ResizeMonthlyTableCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        plan.ensure_mutable("resize")
        actor_id = require_actor(command.actor_id)
        boundary = command.split_id is not None or command.ratio is not None
        whole = command.table_key is not None or command.column_widths is not None or command.height_mm is not None
        if boundary == whole:
            raise MonthlyApplicationError("invalid_timetable_size", "Resize one boundary or one table's size")
        now = self._clock.now()
        if boundary:
            found = next(
                ((i, t, b) for i, t in enumerate(plan.tables) for b in t.boundaries() if b.split_id == command.split_id),
                None,
            )
            if found is None:
                raise MonthlyApplicationError(
                    "timetable_boundary_not_found", f"Table boundary not found: {command.split_id}"
                )
            index, table, current = found
            if command.ratio == current.ratio:
                return plan
            with _limits():
                resized = table.with_ratio(command.split_id, command.ratio)
                change = TimetableChange(
                    TimetableOperation.RESIZE_SPLIT,
                    split_id=command.split_id,
                    before=(current.ratio,),
                    after=(command.ratio,),
                    table_key=table.table_key,
                )
                updated = plan.with_table(index, resized, change=change, actor_id=actor_id, occurred_at=now)
        else:
            index = next((i for i, t in enumerate(plan.tables) if t.table_key == command.table_key), None)
            if index is None:
                raise MonthlyApplicationError("monthly_table_not_found", f"Table not found: {command.table_key}")
            table = plan.tables[index]
            widths = table.column_widths if command.column_widths is None else tuple(command.column_widths)
            height = table.height_mm if command.height_mm is None else command.height_mm
            updated = plan
            with _limits():
                resized = replace(table, column_widths=widths, height_mm=height)
                for operation, before, after in (
                    (TimetableOperation.RESIZE_COLUMNS, table.column_widths, widths),
                    (TimetableOperation.RESIZE_HEIGHT, (table.height_mm,), (height,)),
                ):
                    if before != after:
                        updated = updated.with_table(
                            index,
                            resized,
                            change=TimetableChange(operation, before=before, after=after, table_key=table.table_key),
                            actor_id=actor_id,
                            occurred_at=now,
                        )
        if updated is plan:
            return plan  # the same size again: no event, no write
        self._plans.save(updated.plan_id, updated)
        return updated
