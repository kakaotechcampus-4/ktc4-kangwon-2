"""What a PLAY_MONTHLY plan prints (the Hangul export reads only this)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ssuksak.planning.application.play_monthly_document import (
    PlayMonthlyDocumentWeek,
    play_monthly_document,
)
from ssuksak.planning.application.play_monthly_lifecycle import (
    PlacePlayMonthlySafetyCommand,
    RemovePlayMonthlyActivityCommand,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from tests.application.test_play_monthly_generation import DAILY
from tests.application.test_play_monthly_lifecycle import (
    TEACHER,
    _arrange,
    _copy,
    _draft,
    _edit,
    _teacher_input,
)


def test_a_draft_prints_kept_names_placed_safety_and_its_own_teacher_inputs():
    plan, plans, edit, _ = _draft()
    _, remove, place = _arrange(plans)
    removed = plan.together[1]
    plan = remove.execute(RemovePlayMonthlyActivityCommand(plan.plan_id, TEACHER, removed.cell.item_id))
    plan = _edit(edit, plan, plan.free_play[0].cell, "물감\n 놀이")
    placed = plan.safety_candidates[3]
    plan = place.execute(PlacePlayMonthlySafetyCommand(plan.plan_id, TEACHER, plan.weeks[1].week_id, placed.cell.item_id))
    plan = _copy(plans, plan, plan.drill_candidates[2])
    for key, value in (("class_birthdays", "생일 안내"), ("home_connection", "가정 안내"), ("class_notice", "반 공지 문장")):
        plan = _edit(edit, plan, _teacher_input(plan, key), value)

    plan = _edit(edit, plan, plan.habits[2].habit.cell, "")

    doc = play_monthly_document(plan, DAILY)

    display = plan.display
    assert (doc.title, doc.age, doc.class_name, doc.period) == tuple(c.value for c in display.cells())
    assert doc.period == "2027.04.01 ~ 2027.04.30"
    assert (doc.theme, doc.direction, doc.rationale) == (plan.theme.value, plan.direction.value, plan.rationale.value)
    assert doc.together == tuple(a.cell.value for a in plan.together)
    assert removed.cell.value not in doc.together
    assert doc.free_play == ("물감 놀이", *(a.cell.value for a in plan.free_play[1:]))
    assert doc.weeks == tuple(
        PlayMonthlyDocumentWeek(
            DAILY.get(h.habit.entry_id).label if i != 2 else "",
            h.habit.cell.value,
            placed.cell.value if i == 1 else "",
        )
        for i, h in enumerate(plan.habits)
    )
    assert doc.weeks[0].habit_label == "습관" and doc.weeks[2].habit == ""
    assert doc.drill == plan.drill_candidates[2].cell.value
    assert (doc.health, doc.nutrition) == (plan.health.cell.value, plan.nutrition.cell.value)
    assert (doc.birthdays, doc.home_connection) == ("생일 안내", "가정 안내")
    # Descriptions, unplaced candidates, the class notice and ids are never part of it.
    printed = repr(doc)
    assert all(a.description.value not in printed for a in plan.together if a.description.value)
    assert "반 공지 문장" not in printed
    assert not any(c.item_id.value in printed for c in plan.cells())


def test_a_fresh_draft_prints_blank_safety_drill_and_teacher_inputs():
    plan, *_ = _draft()

    doc = play_monthly_document(plan, DAILY)

    assert len(doc.weeks) == len(plan.weeks)
    assert {w.safety for w in doc.weeks} == {""}
    assert (doc.drill, doc.birthdays, doc.home_connection) == ("", "", "")


def test_habit_labels_come_only_from_the_plans_own_daily_life_catalog():
    plan, *_ = _draft()

    with pytest.raises(InvalidDomainValueError):
        play_monthly_document(plan, replace(DAILY, catalog_version="other"))


def test_a_picked_entry_missing_from_the_catalog_is_refused_not_printed_without_its_label():
    plan, *_ = _draft()
    picked = plan.habits[0].habit.entry_id
    missing = replace(DAILY, entries=tuple(e for e in DAILY.entries if e.entry_id != picked))

    with pytest.raises(InvalidDomainValueError):
        play_monthly_document(plan, missing)
