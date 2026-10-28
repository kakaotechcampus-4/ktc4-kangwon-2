"""PLAY_MONTHLY layout v0.2.0 cells (2026-10-28 D-1 ~ D-10): the copied play direction, the
display strings, and the special-activity timetable that the teacher splits, removes and resizes."""

from __future__ import annotations

import pytest

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.planning.application.generate_play_monthly_plan import (
    PLAY_MONTHLY_LAYOUT_V0_2,
    SPECIAL_ACTIVITY_START_SIZE,
)
from ssuksak.planning.application.play_monthly_document import play_monthly_document
from ssuksak.planning.application.play_monthly_lifecycle import (
    ConfirmPlayMonthlyPlanCommand,
    PlayMonthlyLifecycleError,
    RemovePlayMonthlyTimetableCell,
    RemovePlayMonthlyTimetableCellCommand,
    ResizePlayMonthlyTimetable,
    ResizePlayMonthlyTimetableCommand,
    SplitPlayMonthlyTimetableCell,
    SplitPlayMonthlyTimetableCellCommand,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError, InvalidStateTransitionError
from ssuksak.planning.domain.identifiers import ItemId
from ssuksak.planning.domain.play_monthly_plan import (
    DIRECTION_COPY_RULE_ID,
    MAX_SPLIT_DEPTH,
    TimetableSize,
)
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
    SplitAxis,
    TimetableOperation,
)
from tests.application.test_play_monthly_generation import DAILY, _run
from tests.application.test_play_monthly_lifecycle import NOW, TEACHER, _draft, _edit

MON, TUE, WED, THU, FRI = range(5)


def _timetable(plans):
    clock = FixedClock(NOW)
    return (
        SplitPlayMonthlyTimetableCell(plan_repository=plans, id_generator=DeterministicIdGenerator("split"), clock=clock),
        RemovePlayMonthlyTimetableCell(plan_repository=plans, clock=clock),
        ResizePlayMonthlyTimetable(plan_repository=plans, clock=clock),
    )


def _change(plan):
    event = plan.audit.events[-1]
    assert (event.event_type, event.actor_id, event.item_id) == (AuditEventType.TIMETABLE_CHANGED, TEACHER, None)
    return event.timetable_change


def _keys(plan, day):
    return [c.semantic_key.rsplit(".", 1)[1] for c in plan.special_activity[day].leaves()]


def test_generation_lays_out_the_template_timetable_blank_and_copies_the_theme_once():
    use_case, command, *_ = _run(class_name=" 햇살\n 반 ")
    plan = use_case.execute(command)

    shape = [(d.axis, d.ratio, len(d.leaves())) for d in plan.special_activity]
    assert shape == [
        (SplitAxis.VERTICAL, 48, 4),
        (SplitAxis.HORIZONTAL, 36, 2),
        (SplitAxis.VERTICAL, 48, 4),
        (None, None, 1),
        (SplitAxis.HORIZONTAL, 33, 2),
    ]
    assert [(b.axis, b.ratio) for b in plan.special_activity[MON].children] == [(SplitAxis.HORIZONTAL, 36)] * 2
    assert _keys(plan, MON) == ["1", "2", "3", "4"] and _keys(plan, THU) == ["1"]
    assert plan.special_activity_size == SPECIAL_ACTIVITY_START_SIZE == TimetableSize((20,) * 5, 24)
    blank = [*plan.specialized_timetable, *(c for d in plan.special_activity for c in d.leaves())]
    assert len(plan.specialized_timetable) == 10
    assert {(c.value, c.generation) for c in blank} == {("", None)}
    assert all([e.event_type for e in c.audit.events] == [AuditEventType.CREATED] for c in blank)

    direction = plan.direction
    assert direction.value == plan.theme.value
    assert (direction.generation.method, direction.generation.rule_id) == (GenerationMethod.RULE_ONLY, DIRECTION_COPY_RULE_ID)
    assert direction.generation.rule_version == PLAY_MONTHLY_LAYOUT_V0_2.layout_version
    assert {e.source_type for e in direction.evidence} == {EvidenceSourceType.PARENT_PLAN}

    display = plan.display
    ages = "·".join(str(a) for a in sorted(plan.target_ages))
    assert (display.title.value, display.age.value, display.class_name.value, display.period.value) == (
        "4월 놀이계획안",
        f"만 {ages}세",
        "햇살 반",
        "2027.04.01 ~ 2027.04.30",
    )


def test_without_a_class_name_the_class_cell_starts_blank():
    plan, *_ = _draft()

    assert (plan.display.class_name.value, plan.display.class_name.generation) == ("", None)


def test_the_direction_is_independent_of_the_theme_and_a_cleared_one_stays_blank():
    plan, plans, edit, _ = _draft()
    theme = plan.theme.value

    plan = _edit(edit, plan, plan.direction, "")
    plan = _edit(edit, plan, plan.theme, "바꾼 주제")

    assert (plan.theme.value, plan.direction.value) == ("바꾼 주제", "")
    assert plan.direction.generation.method == GenerationMethod.RULE_ONLY  # an edit never rewrites how it was made
    assert [e.value_change.before for e in plan.direction.audit.events[1:]] == [theme]
    assert play_monthly_document(plan, DAILY).direction == ""


def test_a_display_edit_prints_but_never_moves_the_month_ages_or_weeks():
    plan, plans, edit, _ = _draft()
    month, ages, weeks = plan.target_month, plan.target_ages, plan.weeks

    plan = _edit(edit, plan, plan.display.title, "사월 계획")
    plan = _edit(edit, plan, plan.display.age, "만 5세")
    plan = _edit(edit, plan, plan.display.class_name, "새싹반")
    plan = _edit(edit, plan, plan.display.period, "4월 한 달")

    assert (plan.target_month, plan.target_ages, plan.weeks) == (month, ages, weeks)
    assert plan.display.class_name.generation.method == GenerationMethod.MANUAL
    doc = play_monthly_document(plan, DAILY)
    assert (doc.title, doc.age, doc.class_name, doc.period) == ("사월 계획", "만 5세", "새싹반", "4월 한 달")


def test_a_split_keeps_the_first_cell_whole_and_adds_one_blank_cell_with_a_new_id():
    plan, plans, edit, _ = _draft()
    split, _, _ = _timetable(plans)
    plan = _edit(edit, plan, plan.special_activity[THU].cell, "체육")
    cell = plan.special_activity[THU].cell
    before = {c.item_id for c in plan.cells()}

    plan = split.execute(SplitPlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, cell.item_id, SplitAxis.VERTICAL))

    root = plan.special_activity[THU]
    first, second = (c.cell for c in root.children)
    assert (root.axis, root.ratio) == (SplitAxis.VERTICAL, 50)
    assert first == cell  # id, key, value, generation and history unchanged
    assert (second.value, second.generation, second.semantic_key) == ("", None, "special_activity_timetable.thu.2")
    assert second.item_id not in before and root.split_id not in before
    assert [(e.event_type, e.actor_id) for e in second.audit.events] == [(AuditEventType.CREATED, TEACHER)]
    change = _change(plan)
    assert (change.operation, change.split_id, change.axis, change.cell_id, change.new_cell_id) == (
        TimetableOperation.SPLIT, root.split_id, SplitAxis.VERTICAL, cell.item_id, second.item_id
    )
    assert play_monthly_document(plan, DAILY).special_activity[THU].parts[0].text == "체육"


def test_a_day_splits_at_most_four_deep_and_a_refused_split_saves_nothing():
    plan, plans, _, _ = _draft()
    split, _, _ = _timetable(plans)
    cell = plan.special_activity[THU].cell.item_id
    for _ in range(MAX_SPLIT_DEPTH):
        plan = split.execute(SplitPlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, cell, SplitAxis.HORIZONTAL))
    saves = plans.save_count

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        split.execute(SplitPlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, cell, SplitAxis.HORIZONTAL))

    assert error.value.code == "timetable_split_limit" and plans.save_count == saves
    assert plan.timetable_depth(cell) == MAX_SPLIT_DEPTH


def test_a_removed_cell_is_archived_its_sibling_takes_the_place_and_numbers_never_return():
    plan, plans, edit, _ = _draft()
    split, remove, resize = _timetable(plans)
    boundary = plan.special_activity[FRI]
    plan = _edit(edit, plan, boundary.children[0].cell, "음악")
    boundary = plan.special_activity[FRI]
    gone, kept = (c.cell for c in boundary.children)

    plan = remove.execute(RemovePlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, gone.item_id))

    assert plan.special_activity[FRI].cell == kept
    assert plan.removed_timetable_cells == (gone,)
    change = _change(plan)
    assert (change.operation, change.split_id, change.axis, change.cell_id) == (
        TimetableOperation.REMOVE, boundary.split_id, SplitAxis.HORIZONTAL, gone.item_id
    )
    assert "음악" not in repr(play_monthly_document(plan, DAILY))

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        remove.execute(RemovePlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, kept.item_id))
    assert error.value.code == "timetable_last_cell"

    plan = split.execute(SplitPlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, kept.item_id, SplitAxis.HORIZONTAL))
    assert _keys(plan, FRI) == ["2", "3"]  # 1 stays with the archived cell
    assert plan.special_activity[FRI].split_id != boundary.split_id
    with pytest.raises(PlayMonthlyLifecycleError) as error:  # a vanished boundary is never resized
        resize.execute(ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, split_id=boundary.split_id, ratio=60))
    assert error.value.code == "timetable_boundary_not_found"


def test_boundaries_keep_their_ids_when_a_neighbouring_cell_is_removed():
    plan, plans, _, _ = _draft()
    _, remove, _ = _timetable(plans)
    root = plan.special_activity[MON]
    left, right = root.children

    plan = remove.execute(RemovePlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, left.children[0].cell.item_id))

    after = plan.special_activity[MON]
    assert after.split_id == root.split_id and after.children[1] == right
    assert after.children[0].cell == left.children[1].cell


def test_a_boundary_resize_records_both_ratios_and_the_same_ratio_writes_nothing():
    plan, plans, _, _ = _draft()
    _, _, resize = _timetable(plans)
    split_id = plan.special_activity[MON].split_id

    plan = resize.execute(ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, split_id=split_id, ratio=60))

    assert plan.special_activity[MON].ratio == 60
    change = _change(plan)
    assert (change.operation, change.split_id, change.before, change.after) == (
        TimetableOperation.RESIZE_SPLIT, split_id, (48,), (60,)
    )
    saves = plans.save_count
    assert resize.execute(ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, split_id=split_id, ratio=60)) == plan
    assert plans.save_count == saves


def test_a_size_change_records_one_event_per_changed_measure():
    plan, plans, _, _ = _draft()
    _, _, resize = _timetable(plans)
    events = len(plan.audit.events)
    size = TimetableSize((30, 20, 20, 15, 15), 30)

    plan = resize.execute(ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, size=size))

    changes = [e.timetable_change for e in plan.audit.events[events:]]
    assert [(c.operation, c.before, c.after) for c in changes] == [
        (TimetableOperation.RESIZE_COLUMNS, (20,) * 5, (30, 20, 20, 15, 15)),
        (TimetableOperation.RESIZE_HEIGHT, (24,), (30,)),
    ]
    assert play_monthly_document(plan, DAILY).special_activity_size == size
    saves = plans.save_count
    assert resize.execute(ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, size=size)) == plan
    assert plans.save_count == saves


@pytest.mark.parametrize(
    "widths, height",
    [
        ((20,) * 4, 24),
        ((25, 25, 25, 25, 0), 24),
        ((21, 20, 20, 20, 20), 24),
        ((20,) * 5, 15),
        ((20,) * 5, 81),
        ((20,) * 5, 24.0),
    ],
)
def test_a_size_outside_the_limits_cannot_be_made(widths, height):
    with pytest.raises(InvalidDomainValueError):
        TimetableSize(widths, height)


def _mon(p):
    return p.special_activity[MON].split_id


@pytest.mark.parametrize(
    "command, code",
    [
        (lambda p: ResizePlayMonthlyTimetableCommand(p.plan_id, TEACHER, split_id=_mon(p), ratio=9), "invalid_timetable_size"),
        (lambda p: ResizePlayMonthlyTimetableCommand(p.plan_id, TEACHER, split_id=_mon(p), ratio=91), "invalid_timetable_size"),
        (lambda p: ResizePlayMonthlyTimetableCommand(p.plan_id, TEACHER, split_id=_mon(p), ratio=True), "invalid_timetable_size"),
        (lambda p: ResizePlayMonthlyTimetableCommand(p.plan_id, TEACHER, split_id=ItemId("nope"), ratio=50), "timetable_boundary_not_found"),
        (lambda p: ResizePlayMonthlyTimetableCommand(p.plan_id, TEACHER), "invalid_timetable_size"),
        (
            lambda p: ResizePlayMonthlyTimetableCommand(
                p.plan_id, TEACHER, split_id=_mon(p), ratio=50, size=p.special_activity_size
            ),
            "invalid_timetable_size",
        ),
        (
            lambda p: SplitPlayMonthlyTimetableCellCommand(p.plan_id, TEACHER, p.theme.item_id, SplitAxis.VERTICAL),
            "play_monthly_timetable_cell_not_found",
        ),
        (
            lambda p: SplitPlayMonthlyTimetableCellCommand(
                p.plan_id, TEACHER, p.specialized_timetable[0].item_id, SplitAxis.VERTICAL
            ),
            "play_monthly_timetable_cell_not_found",
        ),
        (
            lambda p: SplitPlayMonthlyTimetableCellCommand(
                p.plan_id, TEACHER, p.special_activity[THU].cell.item_id, "vertical"
            ),
            "invalid_axis",
        ),
        (
            lambda p: RemovePlayMonthlyTimetableCellCommand(p.plan_id, TEACHER, ItemId("nope")),
            "play_monthly_timetable_cell_not_found",
        ),
    ],
)
def test_timetable_requests_outside_the_plan_or_limits_are_refused_and_save_nothing(command, code):
    plan, plans, _, _ = _draft()
    use_cases = dict(
        zip(
            (SplitPlayMonthlyTimetableCellCommand, RemovePlayMonthlyTimetableCellCommand, ResizePlayMonthlyTimetableCommand),
            _timetable(plans),
        )
    )
    saves = plans.save_count
    request = command(plan)

    with pytest.raises(PlayMonthlyLifecycleError) as error:
        use_cases[type(request)].execute(request)

    assert error.value.code == code and plans.save_count == saves


def test_a_confirmed_plan_refuses_every_timetable_change():
    plan, plans, _, confirm = _draft()
    confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER))
    split, remove, resize = _timetable(plans)
    saves = plans.save_count

    for use_case, request in (
        (split, SplitPlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, plan.special_activity[THU].cell.item_id, SplitAxis.VERTICAL)),
        (remove, RemovePlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, plan.special_activity[FRI].children[0].cell.item_id)),
        (resize, ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, split_id=_mon(plan), ratio=60)),
        (resize, ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, size=TimetableSize((30, 20, 20, 15, 15), 24))),
    ):
        with pytest.raises(InvalidStateTransitionError):
            use_case.execute(request)

    assert plans.save_count == saves
