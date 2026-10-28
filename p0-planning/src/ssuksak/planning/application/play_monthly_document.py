"""What a PLAY_MONTHLY plan prints: the values only, never evidence, history or ids.

The Hangul export fills its template from this. Kept rows only (a removed row stays in the
archive, not the document), names without descriptions, the safety sentence a teacher placed
in each week (blank when none), and the drill cell's own value, never its candidates. The
timetables and the class notice are not printed (2026-10-28 decision). Also decided that day:
the period is the whole target month, and a habit prints the label of the daily-life entry it
was picked from, read from the plan's own catalog version.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from ..domain.daily_life_reference import DailyLifeCatalog
from ..domain.errors import InvalidDomainValueError
from ..domain.play_monthly_plan import DRILL_CELL_KEY, PlayMonthlyPlan


@dataclass(frozen=True, slots=True)
class PlayMonthlyDocumentWeek:
    habit_label: str  # blank when the habit is blank or was not picked from an entry
    habit: str
    safety: str


@dataclass(frozen=True, slots=True)
class PlayMonthlyDocument:
    month: int
    target_ages: frozenset[int]
    start_date: date
    end_date: date
    theme: str
    rationale: str
    together: tuple[str, ...]
    free_play: tuple[str, ...]
    weeks: tuple[PlayMonthlyDocumentWeek, ...]
    drill: str
    health: str
    nutrition: str
    birthdays: str
    home_connection: str


def play_monthly_document(plan: PlayMonthlyPlan, daily_life: DailyLifeCatalog) -> PlayMonthlyDocument:
    references = plan.references
    if (daily_life.catalog_id, daily_life.catalog_version) != (
        references.daily_life_catalog_id,
        references.daily_life_catalog_version,
    ):
        raise InvalidDomainValueError("The habit labels must come from the plan's own daily-life catalog")
    safety = {c.cell.item_id: c.cell.value for c in plan.safety_candidates}
    teacher = {t.semantic_key: t.value for t in plan.teacher_inputs}
    year, month = plan.target_month.calendar_year, plan.target_month.calendar_month

    def label(habit) -> str:
        entry = daily_life.get(habit.entry_id) if habit.entry_id and habit.cell.value.strip() else None
        return entry.label if entry else ""

    return PlayMonthlyDocument(
        month=month,
        target_ages=plan.target_ages,
        start_date=date(year, month, 1),
        end_date=date(year, month, calendar.monthrange(year, month)[1]),
        theme=plan.theme.value,
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
    )
