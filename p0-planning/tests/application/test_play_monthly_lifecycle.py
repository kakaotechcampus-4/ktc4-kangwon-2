"""PLAY_MONTHLY lifecycle: L1 edit one cell and confirm (M2-D09 · M2-D13 · I-6), L2 change a
play's curriculum links (M2-D18 · I-1 · I-2). Decisions 2026-10-27.

Plans come from the real generation use case with the Fake provider of the generation tests.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ssuksak.adapters.deterministic import FixedClock
from ssuksak.planning.application.play_monthly_lifecycle import (
    ConfirmPlayMonthlyPlan,
    ConfirmPlayMonthlyPlanCommand,
    EditPlayMonthlyCell,
    EditPlayMonthlyCellCommand,
    EditPlayMonthlyContentIds,
    EditPlayMonthlyContentIdsCommand,
    PlayMonthlyLifecycleError,
    PlayMonthlyNotice,
    play_monthly_notices,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError, InvalidStateTransitionError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType, GenerationMethod, LinkChange
from ssuksak.planning.domain.theme_reference import ActivationStatus
from tests.application.test_play_monthly_generation import CURRICULUM, _Catalogs, _run

NOW = datetime(2027, 2, 21, tzinfo=UTC)
TEACHER = ActorId("teacher-1")


def _draft():
    use_case, command, plans, *_ = _run()
    plan = use_case.execute(command)
    clock = FixedClock(NOW)
    edit = EditPlayMonthlyCell(plan_repository=plans, clock=clock)
    confirm = ConfirmPlayMonthlyPlan(plan_repository=plans, clock=clock)
    return plan, plans, edit, confirm


def _edit(edit, plan, cell, value, actor=TEACHER):
    return edit.execute(EditPlayMonthlyCellCommand(plan.plan_id, actor, cell.item_id, value))


def _others(plan, item_id):
    return [c for c in plan.cells() if c.item_id != item_id]


def _teacher_input(plan, key):
    return next(t for t in plan.teacher_inputs if t.semantic_key == key)


@pytest.mark.parametrize(
    "pick",
    [
        lambda p: p.theme,
        lambda p: p.together[0].cell,
        lambda p: p.free_play[2].description,
        lambda p: p.safety_candidates[6].cell,
        lambda p: p.habits[0].habit.cell,
        lambda p: p.drill_candidates[0].cell,
    ],
)
def test_an_edit_changes_one_value_and_keeps_its_generation_and_evidence(pick):
    plan, plans, edit, _ = _draft()
    cell = pick(plan)
    saves = plans.save_count

    updated = _edit(edit, plan, cell, "교사가 고친 문장")

    after = updated.find_cell(cell.item_id)
    assert after.value == "교사가 고친 문장"
    assert (after.semantic_key, after.generation, after.evidence) == (
        cell.semantic_key,
        cell.generation,
        cell.evidence,
    )
    assert after.generation.method is GenerationMethod.RULE_LLM
    event = after.audit.events[-1]
    assert event.event_type is AuditEventType.TEACHER_EDITED
    assert (event.actor_id, event.item_id, event.occurred_at) == (TEACHER, cell.item_id, NOW)
    assert (event.value_change.before, event.value_change.after) == (cell.value, "교사가 고친 문장")
    assert _others(updated, cell.item_id) == _others(plan, cell.item_id)
    assert plans.save_count == saves + 1 and plans.get(plan.plan_id) == updated


def test_a_habit_edit_keeps_the_entry_it_was_generated_from():
    plan, _, edit, _ = _draft()

    updated = _edit(edit, plan, plan.habits[1].habit.cell, "손을 깨끗이 씻어요")

    assert updated.habits[1].habit.entry_id == plan.habits[1].habit.entry_id


def test_a_teacher_input_becomes_manual_on_its_first_write_and_stays_manual():
    plan, _, edit, _ = _draft()
    notice = _teacher_input(plan, "class_notice")
    assert notice.generation is None and notice.value == ""

    first = _edit(edit, plan, notice, "현장학습 안내")
    second = _edit(edit, first, _teacher_input(first, "class_notice"), "현장학습 안내 (변경)")

    cell = _teacher_input(second, "class_notice")
    assert cell.generation.method is GenerationMethod.MANUAL and cell.evidence == ()
    created, *edits = cell.audit.events
    assert created.event_type is AuditEventType.CREATED and created.system_actor
    assert [(e.event_type, e.value_change.before, e.value_change.after) for e in edits] == [
        (AuditEventType.TEACHER_EDITED, "", "현장학습 안내"),
        (AuditEventType.TEACHER_EDITED, "현장학습 안내", "현장학습 안내 (변경)"),
    ]


def test_clearing_a_generated_cell_keeps_its_generation():
    plan, _, edit, _ = _draft()

    updated = _edit(edit, plan, plan.health.cell, "")

    cell = updated.health.cell
    assert cell.value == "" and cell.generation == plan.health.cell.generation
    assert cell.audit.events[-1].value_change.after == ""


@pytest.mark.parametrize("value", ["same", "  "])
def test_saving_the_same_value_or_blank_over_blank_writes_nothing(value):
    plan, plans, edit, _ = _draft()
    cell = plan.together[0].cell if value == "same" else _teacher_input(plan, "class_notice")
    saves = plans.save_count

    result = _edit(edit, plan, cell, cell.value if value == "same" else value)

    assert result == plan and plans.save_count == saves


@pytest.mark.parametrize(
    ("command", "code"),
    [
        (lambda p: EditPlayMonthlyCellCommand(p.plan_id, TEACHER, ItemId("nope"), "x"), "play_monthly_cell_not_found"),
        (lambda p: EditPlayMonthlyCellCommand(p.plan_id, TEACHER, p.theme.item_id, None), "invalid_value"),
        (lambda p: EditPlayMonthlyCellCommand(p.plan_id, "teacher-1", p.theme.item_id, "x"), "opaque_actor_required"),
        (lambda p: EditPlayMonthlyCellCommand(p.plan_id, TEACHER, "theme", "x"), "invalid_item_id"),
        (lambda p: EditPlayMonthlyCellCommand(PlanId("missing"), TEACHER, p.theme.item_id, "x"), "play_monthly_plan_not_found"),
    ],
)
def test_a_bad_edit_is_rejected_and_saves_nothing(command, code):
    plan, plans, edit, _ = _draft()
    saves = plans.save_count

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        edit.execute(command(plan))

    assert error.value.code == code and plans.save_count == saves


def test_confirm_records_the_actor_and_allows_the_blanks_it_only_notices():
    plan, plans, edit, confirm = _draft()
    plan = _edit(edit, plan, plan.nutrition.cell, "")

    confirmed = confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER))

    assert confirmed.status is PlanStatus.CONFIRMED and plans.get(plan.plan_id) == confirmed
    event = confirmed.audit.events[-1]
    assert (event.event_type, event.actor_id, event.occurred_at) == (AuditEventType.CONFIRMED, TEACHER, NOW)
    assert confirmed.cells() == plan.cells()  # teacher inputs and nutrition stay blank
    assert PlayMonthlyNotice("NUTRITION_BLANK") in play_monthly_notices(confirmed)


def test_notices_name_unplaced_safety_weeks_and_blank_habits_health_nutrition():
    plan, _, edit, _ = _draft()
    assert play_monthly_notices(plan) == tuple(
        PlayMonthlyNotice("SAFETY_UNPLACED", s.week_id) for s in plan.safety_weeks
    )

    plan = _edit(edit, plan, plan.habits[0].habit.cell, "")
    plan = _edit(edit, plan, plan.health.cell, " ")

    notices = play_monthly_notices(plan)
    assert PlayMonthlyNotice("HABIT_BLANK", plan.habits[0].week_id) in notices
    assert PlayMonthlyNotice("HEALTH_BLANK") in notices
    assert PlayMonthlyNotice("NUTRITION_BLANK") not in notices


def _with_content_ids(activity, count):
    return replace(activity, content_ids=tuple(f"c{n}" for n in range(count)))


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda p: replace(p, theme=replace(p.theme, value=" ")), "theme: blank"),
        (lambda p: replace(p, rationale=replace(p.rationale, value="")), "rationale: blank"),
        (lambda p: replace(p, together=()), "together: no rows"),
        (
            lambda p: replace(p, free_play=(replace(p.free_play[0], cell=replace(p.free_play[0].cell, value="")),)),
            "free_play:{free}: blank name",
        ),
        (lambda p: replace(p, together=(_with_content_ids(p.together[0], 0),)), "together:{together}: 0 content ids"),
        (lambda p: replace(p, together=(_with_content_ids(p.together[0], 4),)), "together:{together}: 4 content ids"),
    ],
)
def test_confirm_is_refused_without_the_required_content_and_saves_nothing(change, problem):
    plan, plans, _, confirm = _draft()
    broken = change(plan)
    plans.save(broken.plan_id, broken)
    saves = plans.save_count

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER))

    expected = problem.format(
        together=plan.together[0].cell.item_id.value, free=plan.free_play[0].cell.item_id.value
    )
    assert error.value.code == "play_monthly_incomplete" and expected in error.value.problems
    assert plans.save_count == saves and plans.get(plan.plan_id).status is PlanStatus.DRAFT


def test_one_to_three_content_ids_and_a_single_row_per_section_are_enough():
    plan, plans, _, confirm = _draft()
    plan = replace(
        plan,
        together=(_with_content_ids(plan.together[0], 1),),
        free_play=(_with_content_ids(plan.free_play[0], 3),),
    )
    plans.save(plan.plan_id, plan)

    confirmed = confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER))

    assert confirmed.status is PlanStatus.CONFIRMED


def test_a_confirmed_plan_refuses_edit_and_reconfirm():
    plan, plans, edit, confirm = _draft()
    confirmed = confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER))
    saves = plans.save_count

    with pytest.raises(InvalidStateTransitionError):
        _edit(edit, confirmed, confirmed.theme, "바꾼 주제")
    with pytest.raises(InvalidStateTransitionError):
        confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER))
    with pytest.raises(InvalidStateTransitionError):
        confirmed.replace_cell(replace(confirmed.theme, value="x"))

    assert plans.save_count == saves


def test_confirm_requires_an_opaque_actor():
    plan, plans, _, confirm = _draft()

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, "담임"))

    assert error.value.code == "opaque_actor_required"
    assert plans.get(plan.plan_id).status is PlanStatus.DRAFT


def test_replace_cell_refuses_an_unknown_cell_or_a_moved_semantic_key():
    plan, *_ = _draft()

    with pytest.raises(InvalidDomainValueError):
        plan.replace_cell(replace(plan.theme, item_id=ItemId("nope")))
    with pytest.raises(InvalidDomainValueError):
        plan.replace_cell(replace(plan.theme, semantic_key="rationale"))


# --- L2: curriculum links -------------------------------------------------------------------


def _links(plans, *catalogs):
    return EditPlayMonthlyContentIds(
        plan_repository=plans,
        curriculum_repository=_Catalogs(*(catalogs or (CURRICULUM,))),
        clock=FixedClock(NOW),
    )


def _link(use_case, plan, activity, ids):
    return use_case.execute(EditPlayMonthlyContentIdsCommand(plan.plan_id, TEACHER, activity.cell.item_id, ids))


def _unlinked(activity, count):
    """Catalog ids the play does not link yet, so the change is never a no-op."""
    return tuple(c.content_id for c in CURRICULUM.contents if c.content_id not in activity.content_ids)[:count]


@pytest.mark.parametrize("count", [1, 3])
def test_a_link_change_keeps_generation_evidence_and_is_not_a_text_edit(count):
    plan, plans, _, confirm = _draft()
    activity = plan.free_play[1]
    ids = _unlinked(activity, count)
    saves = plans.save_count

    updated = _link(_links(plans), plan, activity, ids)

    after = updated.activity(activity.cell.item_id)
    assert after.content_ids == ids
    assert (after.cell.value, after.cell.evidence, after.cell.generation) == (
        activity.cell.value,
        activity.cell.evidence,
        activity.cell.generation,
    )
    assert after.description == activity.description
    event = after.cell.audit.events[-1]
    assert (event.event_type, event.actor_id, event.item_id, event.value_change) == (
        AuditEventType.TEACHER_EDITED,
        TEACHER,
        activity.cell.item_id,
        None,
    )
    assert event.link_change == LinkChange(activity.content_ids, ids, CURRICULUM.catalog_version)
    assert not after.cell.audit.current_value_teacher_edited()
    assert [a for a in (*updated.together, *updated.free_play) if a is not after] == [
        a for a in (*plan.together, *plan.free_play) if a != activity
    ]
    assert plans.save_count == saves + 1
    assert confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER)).status is PlanStatus.CONFIRMED


def test_a_text_edit_stays_teacher_edited_after_a_later_link_change():
    plan, plans, edit, _ = _draft()
    plan = _edit(edit, plan, plan.together[0].cell, "교사가 바꾼 놀이명")

    updated = _link(_links(plans), plan, plan.together[0], _unlinked(plan.together[0], 2))

    cell = updated.together[0].cell
    assert cell.value == "교사가 바꾼 놀이명" and cell.audit.current_value_teacher_edited()


@pytest.mark.parametrize(
    ("ids", "problem"),
    [
        ((), "0 content ids, needs 1~3"),
        (("t.1", "t.2", "t.3", "t.4"), "4 content ids, needs 1~3"),
        (("t.5", "t.5"), "duplicate content id"),
        (("t.99",), "t.99: not in test-curriculum-v1"),
    ],
)
def test_bad_links_are_rejected_and_save_nothing(ids, problem):
    plan, plans, _, _ = _draft()
    saves = plans.save_count

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        _link(_links(plans), plan, plan.together[2], ids)

    assert error.value.code == "invalid_content_ids" and problem in error.value.problems
    assert plans.save_count == saves


@pytest.mark.parametrize(
    "catalogs",
    [
        (),
        (replace(CURRICULUM, activation_status=ActivationStatus.PENDING_HUMAN_REVIEW),),
        (replace(CURRICULUM, catalog_version="test-curriculum-v2"),),
    ],
    ids=["missing", "not-approved", "other-version-only"],
)
def test_links_are_checked_only_against_the_plans_own_approved_catalog_version(catalogs):
    plan, plans, _, _ = _draft()
    use_case = EditPlayMonthlyContentIds(
        plan_repository=plans, curriculum_repository=_Catalogs(*catalogs), clock=FixedClock(NOW)
    )

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        _link(use_case, plan, plan.together[0], _unlinked(plan.together[0], 1))

    assert error.value.code == "curriculum_reference_unavailable"


@pytest.mark.parametrize(
    ("command", "code"),
    [
        (lambda p: EditPlayMonthlyContentIdsCommand(p.plan_id, TEACHER, p.together[0].description.item_id, ("t.1",)), "play_monthly_activity_not_found"),
        (lambda p: EditPlayMonthlyContentIdsCommand(p.plan_id, TEACHER, p.theme.item_id, ("t.1",)), "play_monthly_activity_not_found"),
        (lambda p: EditPlayMonthlyContentIdsCommand(p.plan_id, TEACHER, p.together[0].cell.item_id, "t.1"), "invalid_content_ids"),
        (lambda p: EditPlayMonthlyContentIdsCommand(p.plan_id, "teacher-1", p.together[0].cell.item_id, ("t.1",)), "opaque_actor_required"),
    ],
)
def test_a_link_change_needs_a_play_name_a_list_and_an_actor(command, code):
    plan, plans, _, _ = _draft()

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        _links(plans).execute(command(plan))

    assert error.value.code == code


def test_the_same_links_write_nothing_and_a_confirmed_plan_refuses_links():
    plan, plans, _, confirm = _draft()
    activity = plan.together[0]
    saves = plans.save_count

    assert _link(_links(plans), plan, activity, list(activity.content_ids)) == plan
    assert plans.save_count == saves

    confirmed = confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER))
    with pytest.raises(InvalidStateTransitionError):
        _link(_links(plans), confirmed, confirmed.together[0], _unlinked(activity, 1))
