"""What a PLAY_MONTHLY plan prints: the values only, never evidence, history or ids.

The Hangul export fills its template from this. Kept rows only (a removed row stays in the
archive, not the document), names without descriptions, the safety sentence a teacher placed
in each week (blank when none), and the drill cell's own value, never its candidates. The
class notice is not printed (2026-10-28 decision). Also decided that day: a habit prints the
label of the daily-life entry it was picked from, read from the plan's own catalog version.

Layout v0.2.0 (2026-10-28 D-2 · D-6): the header strings and the centre play direction are the
plan's own cells — the teacher's text, blanks included — not values computed here. The
timetables print cell by cell: the specialized one as five titles over five contents, the
special-activity one as each weekday's parts with their boundaries and the table size.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.daily_life_reference import DailyLifeCatalog
from ..domain.errors import InvalidDomainValueError
from ..domain.play_monthly_plan import (
    DRILL_CELL_KEY,
    SPECIALIZED_COLUMNS,
    PlayMonthlyPlan,
    TimetableNode,
    TimetableSize,
)
from ..domain.provenance import SplitAxis


@dataclass(frozen=True, slots=True)
class PlayMonthlyDocumentWeek:
    habit_label: str  # blank when the habit is blank or was not picked from an entry
    habit: str
    safety: str


@dataclass(frozen=True, slots=True)
class PlayMonthlyDocumentPart:
    """A special-activity part: its text, or a boundary (``axis``, first-part ``ratio``) over two parts."""

    text: str = ""
    axis: SplitAxis | None = None
    ratio: int | None = None
    parts: tuple[PlayMonthlyDocumentPart, ...] = ()


@dataclass(frozen=True, slots=True)
class PlayMonthlyDocument:
    title: str
    age: str
    class_name: str
    period: str
    theme: str
    direction: str
    rationale: str
    together: tuple[str, ...]
    free_play: tuple[str, ...]
    weeks: tuple[PlayMonthlyDocumentWeek, ...]
    drill: str
    health: str
    nutrition: str
    birthdays: str
    home_connection: str
    specialized_titles: tuple[str, ...]  # five
    specialized_contents: tuple[str, ...]  # five, under the titles
    special_activity: tuple[PlayMonthlyDocumentPart, ...]  # Monday to Friday
    special_activity_size: TimetableSize


def _part(node: TimetableNode) -> PlayMonthlyDocumentPart:
    if node.cell is not None:
        return PlayMonthlyDocumentPart(node.cell.value)
    return PlayMonthlyDocumentPart(axis=node.axis, ratio=node.ratio, parts=tuple(_part(c) for c in node.children))


def play_monthly_document(plan: PlayMonthlyPlan, daily_life: DailyLifeCatalog) -> PlayMonthlyDocument:
    references = plan.references
    if (daily_life.catalog_id, daily_life.catalog_version) != (
        references.daily_life_catalog_id,
        references.daily_life_catalog_version,
    ):
        raise InvalidDomainValueError("The habit labels must come from the plan's own daily-life catalog")
    safety = {c.cell.item_id: c.cell.value for c in plan.safety_candidates}
    teacher = {t.semantic_key: t.value for t in plan.teacher_inputs}
    specialized = tuple(c.value for c in plan.specialized_timetable)

    def label(habit) -> str:
        if not (habit.entry_id and habit.cell.value.strip()):
            return ""
        entry = daily_life.get(habit.entry_id)
        if entry is None:  # a dropped label would print as if none was ever picked
            raise InvalidDomainValueError(f"Daily-life entry {habit.entry_id} is missing from the plan's catalog")
        return entry.label

    display = plan.display
    return PlayMonthlyDocument(
        title=display.title.value,
        age=display.age.value,
        class_name=display.class_name.value,
        period=display.period.value,
        theme=plan.theme.value,
        direction=plan.direction.value,
        rationale=plan.rationale.value,
        # A name is one list line, so a line break inside it would read as two plays.
        together=tuple(" ".join(a.cell.value.split()) for a in plan.together),
        free_play=tuple(" ".join(a.cell.value.split()) for a in plan.free_play),
        weeks=tuple(
            PlayMonthlyDocumentWeek(
                label(habit.habit),
                habit.habit.cell.value,
                safety[placed.candidate_item_id] if placed.candidate_item_id else "",
            )
            for habit, placed in zip(plan.habits, plan.safety_weeks, strict=True)
        ),
        drill=teacher[DRILL_CELL_KEY],
        health=plan.health.cell.value,
        nutrition=plan.nutrition.cell.value,
        birthdays=teacher["class_birthdays"],
        home_connection=teacher["home_connection"],
        specialized_titles=specialized[:SPECIALIZED_COLUMNS],
        specialized_contents=specialized[SPECIALIZED_COLUMNS:],
        special_activity=tuple(_part(day) for day in plan.special_activity),
        special_activity_size=plan.special_activity_size,
    )
