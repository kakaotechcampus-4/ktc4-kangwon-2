"""Teacher-written tables of the monthly v1 document (Human Decision 2026-11-05, 하민).

The approved v1 form (``monthly_v1_*weeks.hwpx``) ends with three tables the teacher writes:
행사 일정, 특성화 시간표 and 특별활동 시간표. They are document areas, not Template A Sections —
Template A keeps ``event_schedule`` / ``special_program`` inactive with ``repeat_by`` pending, and
the Plan's Sections must keep matching its TemplateSnapshot. Like the play monthly
``TEACHER_TABLE`` nothing here is generated: a cell has no generation until its first write, and
every write is ``MANUAL`` (CLAUDE.md §5 — no event is made up).

A table is columns of split trees, the play monthly special-activity model (ADR-047) reused as
is: ``TimetableNode`` over ``PlayMonthlyCell``. A split keeps the cell (id, value, history) as
the first part and adds one new cell; a removed cell stays whole in the Plan. The 특성화 table
also has one editable title per column (the form's blank title row); titles never split.

A Plan written before this decision stores no tables. ``blank_teacher_tables`` gives the same
blank tables every time, with ids made from the plan id, so the first write keeps the ids the
screen already saw.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

from .errors import InvalidDomainValueError
from .identifiers import ItemId, PlanId
from .play_monthly_plan import (
    CELL_MIN_WIDTH_PERCENT,
    COLUMN_MIN_PERCENT,
    MAX_SPLIT_DEPTH,
    SPLIT_RATIO_RANGE,
    PlayMonthlyCell,
    TimetableNode,
    TimetableTooNarrowError,
)
from .provenance import GenerationMethod, SplitAxis

EVENT_SCHEDULE_KEY = "event_schedule"
SPECIALIZED_KEY = "specialized_timetable"
SPECIAL_ACTIVITY_KEY = "special_activity_timetable"
# (key, form label, columns, titled, start height mm). Heights are the v1 form's rows
# (3500 · 4000 · 6000 HWPUNIT), rounded down to whole mm.
TABLE_SHAPES = (
    (EVENT_SCHEDULE_KEY, "행사 일정", 1, False, 12),
    (SPECIALIZED_KEY, "특성화 시간표", 5, True, 14),
    (SPECIAL_ACTIVITY_KEY, "특별활동 시간표", 5, False, 21),
)
TEACHER_TABLE_KEYS = tuple(shape[0] for shape in TABLE_SHAPES)
# The v1 form rows start lower than the play monthly 16 mm minimum.
HEIGHT_MM_RANGE = (10, 80)


@dataclass(frozen=True, slots=True)
class MonthlyTeacherTable:
    table_key: str
    source_label: str
    titles: tuple[PlayMonthlyCell, ...]  # one per column, or () when the form prints its own
    columns: tuple[TimetableNode, ...]
    column_widths: tuple[int, ...]  # percent of the table width
    height_mm: int

    def __post_init__(self) -> None:
        for name in ("table_key", "source_label"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"MonthlyTeacherTable.{name} must be non-blank")
        columns, widths = self.columns, self.column_widths
        if not isinstance(columns, tuple) or not columns or not all(isinstance(c, TimetableNode) for c in columns):
            raise InvalidDomainValueError("MonthlyTeacherTable.columns must be TimetableNode values")
        if not isinstance(self.titles, tuple) or self.titles and (
            len(self.titles) != len(columns) or not all(isinstance(t, PlayMonthlyCell) for t in self.titles)
        ):
            raise InvalidDomainValueError("MonthlyTeacherTable.titles are one cell per column, or none")
        if (
            not isinstance(widths, tuple)
            or len(widths) != len(columns)
            or not all(type(w) is int and w >= COLUMN_MIN_PERCENT for w in widths)
            or sum(widths) != 100
        ):
            raise InvalidDomainValueError(
                f"MonthlyTeacherTable needs one int percent of at least {COLUMN_MIN_PERCENT} per column, summing to 100"
            )
        low, high = HEIGHT_MM_RANGE
        if type(self.height_mm) is not int or not low <= self.height_mm <= high:
            raise InvalidDomainValueError(f"MonthlyTeacherTable.height_mm must be {low}~{high}")
        if any(c.depth > MAX_SPLIT_DEPTH for c in columns):
            raise InvalidDomainValueError(f"A table column splits at most {MAX_SPLIT_DEPTH} deep")
        if any(c.narrowest(Fraction(w)) < CELL_MIN_WIDTH_PERCENT for c, w in zip(columns, widths, strict=True)):
            raise TimetableTooNarrowError(
                f"A table cell keeps at least {float(CELL_MIN_WIDTH_PERCENT)}% of the table width"
            )
        for cell in self.cells():
            if not cell.semantic_key.startswith(f"{self.table_key}."):
                raise InvalidDomainValueError("A table cell's key starts with its table key")
            if cell.generation is not None and cell.generation.method is not GenerationMethod.MANUAL:
                raise InvalidDomainValueError("Teacher table cells are written by a teacher only")

    def cells(self) -> tuple[PlayMonthlyCell, ...]:
        return (*self.titles, *(c for column in self.columns for c in column.leaves()))

    def boundaries(self) -> tuple[TimetableNode, ...]:
        return tuple(b for column in self.columns for b in column.boundaries())

    def column_of(self, item_id: ItemId) -> int | None:
        """The column holding this content cell (titles excluded), or ``None``."""
        return next(
            (i for i, c in enumerate(self.columns) if any(leaf.item_id == item_id for leaf in c.leaves())),
            None,
        )

    def depth_of(self, item_id: ItemId) -> int:
        def walk(node: TimetableNode, depth: int) -> int | None:
            if node.cell is not None:
                return depth if node.cell.item_id == item_id else None
            return next((d for c in node.children if (d := walk(c, depth + 1)) is not None), None)

        return next(d for c in self.columns if (d := walk(c, 0)) is not None)

    def next_key(self, column: int, removed: tuple[PlayMonthlyCell, ...]) -> str:
        """A key never used in that column: removed cells keep theirs, so numbers only grow."""
        prefix = f"{self.table_key}.{column + 1}."
        used = [
            int(c.semantic_key.removeprefix(prefix))
            for c in (*self.columns[column].leaves(), *removed)
            if c.semantic_key.startswith(prefix)
        ]
        return f"{prefix}{max(used, default=0) + 1}"

    def replace_cell(self, updated: PlayMonthlyCell) -> MonthlyTeacherTable:
        def swap(cell: PlayMonthlyCell) -> PlayMonthlyCell:
            if cell.item_id != updated.item_id:
                return cell
            if cell.semantic_key != updated.semantic_key:
                raise InvalidDomainValueError("A table cell keeps its semantic_key")
            return updated

        return replace(
            self,
            titles=tuple(swap(t) for t in self.titles),
            columns=tuple(
                c.rebuilt(lambda n: TimetableNode(cell=swap(n.cell)) if n.cell is not None else None)
                for c in self.columns
            ),
        )

    def split(self, item_id: ItemId, axis: SplitAxis, split_id: ItemId, new_cell: PlayMonthlyCell) -> MonthlyTeacherTable:
        def visit(node: TimetableNode) -> TimetableNode | None:
            if node.cell is None or node.cell.item_id != item_id:
                return None
            return TimetableNode(split_id=split_id, axis=axis, ratio=50, children=(node, TimetableNode(cell=new_cell)))

        return replace(self, columns=tuple(c.rebuilt(visit) for c in self.columns))

    def parent_of(self, item_id: ItemId) -> TimetableNode | None:
        return next(
            (b for b in self.boundaries() if any(c.cell is not None and c.cell.item_id == item_id for c in b.children)),
            None,
        )

    def without(self, parent: TimetableNode, item_id: ItemId) -> MonthlyTeacherTable:
        """Drop a cell; its sibling takes the boundary's place."""
        sibling = next(c for c in parent.children if c.cell is None or c.cell.item_id != item_id)
        return replace(self, columns=tuple(c.rebuilt(lambda n: sibling if n is parent else None) for c in self.columns))

    def with_ratio(self, split_id: ItemId, ratio: int) -> MonthlyTeacherTable:
        low, high = SPLIT_RATIO_RANGE
        if type(ratio) is not int or not low <= ratio <= high:
            raise InvalidDomainValueError(f"ratio must be an int {low}~{high}")
        return replace(
            self,
            columns=tuple(
                c.rebuilt(lambda n: replace(n, ratio=ratio) if n.split_id == split_id else None) for c in self.columns
            ),
        )


def blank_teacher_tables(plan_id: PlanId) -> tuple[MonthlyTeacherTable, ...]:
    """The blank form tables, the same every time for one plan id."""

    def cell(key: str) -> PlayMonthlyCell:
        return PlayMonthlyCell(item_id=ItemId(f"{plan_id.value}.{key}"), semantic_key=key)

    return tuple(
        MonthlyTeacherTable(
            table_key=key,
            source_label=label,
            titles=tuple(cell(f"{key}.title.{i}") for i in range(1, count + 1)) if titled else (),
            columns=tuple(TimetableNode(cell=cell(f"{key}.{i}.1")) for i in range(1, count + 1)),
            column_widths=(100 // count,) * count,
            height_mm=height,
        )
        for key, label, count, titled, height in TABLE_SHAPES
    )
