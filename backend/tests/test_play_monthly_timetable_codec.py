"""월간 v2 시간표(layout v0.2.0)가 실제 저장 변환(codec)을 지나도 그대로인지 본다.

DB 는 쓰지 않는다. 시간표는 요일마다 자기 자신을 품는 나눔 트리이고, 지운 칸은 보관되며,
나누기 · 지우기 · 크기 조절은 TIMETABLE_CHANGED 이력(전후 숫자)으로 남는다.
계획은 Core 테스트의 진짜 Use Case 로 만든다(도메인 객체를 손으로 짓지 않는다) —
Core 생성 입력이 바뀌면 그쪽 도우미만 고치면 된다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "p0-planning"))  # Core 테스트 도우미

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock  # noqa: E402
from ssuksak.planning.application.play_monthly_lifecycle import (  # noqa: E402
    ConfirmPlayMonthlyPlanCommand,
    RemovePlayMonthlyTimetableCell,
    RemovePlayMonthlyTimetableCellCommand,
    ResizePlayMonthlyTimetable,
    ResizePlayMonthlyTimetableCommand,
    SplitPlayMonthlyTimetableCell,
    SplitPlayMonthlyTimetableCellCommand,
)
from ssuksak.planning.domain.play_monthly_plan import PlayMonthlyPlan, TimetableSize  # noqa: E402
from ssuksak.planning.domain.provenance import SplitAxis  # noqa: E402
from tests.application.test_play_monthly_lifecycle import NOW, TEACHER, _draft, _edit  # noqa: E402

from app.features.plans.codec import from_jsonable, to_jsonable  # noqa: E402

MON, THU, FRI = 0, 3, 4


def _round_trip(plan: PlayMonthlyPlan) -> PlayMonthlyPlan:
    return from_jsonable(PlayMonthlyPlan, json.loads(json.dumps(to_jsonable(plan))))


def test_an_edited_split_removed_resized_and_confirmed_plan_survives_the_codec() -> None:
    plan, plans, edit, confirm = _draft()
    clock = FixedClock(NOW)
    split = SplitPlayMonthlyTimetableCell(
        plan_repository=plans, id_generator=DeterministicIdGenerator("split"), clock=clock
    )
    remove = RemovePlayMonthlyTimetableCell(plan_repository=plans, clock=clock)
    resize = ResizePlayMonthlyTimetable(plan_repository=plans, clock=clock)
    seen = [plan]

    plan = _edit(edit, plan, plan.special_activity[THU].cell, "체육")
    plan = _edit(edit, plan, plan.direction, "")
    plan = _edit(edit, plan, plan.display.class_name, "햇살반")
    plan = _edit(edit, plan, plan.specialized_timetable[0], "영어")
    thu = plan.special_activity[THU].cell.item_id
    for axis in (SplitAxis.VERTICAL, SplitAxis.HORIZONTAL):
        plan = split.execute(SplitPlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, thu, axis))
        seen.append(plan)
    gone = plan.special_activity[FRI].children[0].cell.item_id
    plan = remove.execute(RemovePlayMonthlyTimetableCellCommand(plan.plan_id, TEACHER, gone))
    boundary = plan.special_activity[MON].split_id
    plan = resize.execute(
        ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, split_id=boundary, ratio=60)
    )
    size = TimetableSize((30, 20, 20, 15, 15), 30)
    plan = resize.execute(ResizePlayMonthlyTimetableCommand(plan.plan_id, TEACHER, size=size))
    seen.append(plan)
    seen.append(confirm.execute(ConfirmPlayMonthlyPlanCommand(plan.plan_id, TEACHER)))

    assert len(seen[-2].removed_timetable_cells) == 1 and seen[-2].special_activity[THU].depth == 2
    for each in seen:
        assert _round_trip(each) == each
