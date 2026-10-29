"""Golden: play-project selection · edit · confirm (golden/play_project_selection.json)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_curriculum_reference_repository import (
    JsonCurriculumReferenceRepository,
)
from ssuksak.planning.application.generate_play_project_plan import (
    PLAY_PROJECT_LAYOUT_V0_2,
    GeneratePlayProjectPlan,
    GeneratePlayProjectPlanCommand,
)
from ssuksak.planning.application.play_project_lifecycle import (
    ConfirmPlayProjectPlan,
    ConfirmPlayProjectPlanCommand,
    EditPlayProjectItem,
    EditPlayProjectItemCommand,
    PlayProjectApplicationError,
    SavePlayProjectSelection,
    SavePlayProjectSelectionCommand,
)
from ssuksak.planning.domain.errors import InvalidStateTransitionError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.provenance import AuditEventType
from ssuksak.planning.planner.contracts import RawLlmResponse

GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "play_project_selection.json").read_text(encoding="utf-8")
)
TEACHER = ActorId("teacher_1")
CLOCK = FixedClock(datetime(2026, 10, 26, 9, 0, tzinfo=UTC))
FULL = [f"cand{n}" for n in range(1, 6)]


class _Provider:
    def generate_play_project(self, request):
        rows = [
            {
                "play_name": f"{request.period_key} 놀이 {n}",
                "materials": "종이 상자, 크레파스 등 준비해 볼 자료",
                "support_direction": "관심이 이어지면 자료를 더해 놀이를 넓혀 갈 수 있도록 돕는다.",
                "learning_content_ids": ["nuri2019.3.1.1", "nuri2019.3.1.2"],
            }
            for n in range(1, 11)
        ]
        content = json.dumps({"period_key": request.period_key, "rows": rows}, ensure_ascii=False)
        return RawLlmResponse(content=content, model="fake")


class _OnePlanId(DeterministicIdGenerator):
    """Every period lands in the same plan, as the backend merges them."""

    fixed = None

    def new_plan_id(self):
        return self.fixed or super().new_plan_id()


def _plan(period_keys):
    ids = _OnePlanId("pp")
    use_case = GeneratePlayProjectPlan(
        curriculum_repository=JsonCurriculumReferenceRepository(),
        plan_repository=InMemoryPlanRepository(),
        provider=_Provider(),
        clock=CLOCK,
        id_generator=ids,
    )
    results = []
    for key in period_keys:
        results.append(
            use_case.execute(
                GeneratePlayProjectPlanCommand(
                    school_year=2026,
                    classroom_ref="class_1",
                    target_ages=frozenset({4}),
                    period_key=key,
                    curriculum_catalog_id="ssuksak.nuri-curriculum-content",
                    curriculum_catalog_version="nuri-curriculum-content-v0.1.0",
                )
            )
        )
        ids.fixed = results[0].plan_id
    return replace(results[0], periods=tuple(r.periods[0] for r in results))


def _actor(step):
    return TEACHER if step.get("actor", "teacher_1") is not None else None


def _run(step, repo, plan_id):
    op = step["op"]
    if op in ("select", "select_full"):
        selections = (
            {p.key: FULL for p in PLAY_PROJECT_LAYOUT_V0_2.periods}
            if op == "select_full"
            else step["selections"]
        )
        SavePlayProjectSelection(plan_repository=repo, clock=CLOCK).execute(
            SavePlayProjectSelectionCommand(plan_id, _actor(step), selections)
        )
    elif op == "edit":
        item = _item(repo.get(plan_id), step["period"], step["row"], step["field"])
        EditPlayProjectItem(plan_repository=repo, clock=CLOCK).execute(
            EditPlayProjectItemCommand(plan_id, _actor(step), item.item_id, step["value"])
        )
    elif op == "confirm":
        ConfirmPlayProjectPlan(plan_repository=repo, clock=CLOCK).execute(
            ConfirmPlayProjectPlanCommand(plan_id, _actor(step))
        )
    else:
        raise AssertionError(op)


def _item(plan, period_key, row_key, field):
    period = next(p for p in plan.periods if p.period.key == period_key)
    return getattr(next(r for r in period.candidates if r.row_key == row_key), field)


def _selection_events(plan):
    return [
        {
            "type": e.event_type.value,
            "period_key": e.selection_change.period_key,
            "before": list(e.selection_change.before),
            "after": list(e.selection_change.after),
        }
        for e in plan.audit
        if e.event_type is AuditEventType.CANDIDATES_SELECTED
    ]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["id"])
def test_play_project_selection_golden(case):
    keys = case.get("fixture_periods") or [p.key for p in PLAY_PROJECT_LAYOUT_V0_2.periods]
    original = _plan(keys)
    repo = InMemoryPlanRepository()
    repo.save(original.plan_id, original)

    for step in case["steps"]:
        expect = step.get("expect", {})
        before, saves = repo.get(original.plan_id), repo.save_count
        if "error" in expect:
            error_type = (
                InvalidStateTransitionError if expect["error"] == "state" else PlayProjectApplicationError
            )
            with pytest.raises(error_type) as raised:
                _run(step, repo, original.plan_id)
            if error_type is PlayProjectApplicationError:
                assert raised.value.code == expect["error"]
                if "problems" in expect:
                    assert list(raised.value.problems) == expect["problems"]
            assert repo.save_count == saves and repo.get(original.plan_id) is before
        else:
            _run(step, repo, original.plan_id)
            if "saved" in expect:
                assert (repo.save_count > saves) is expect["saved"]

    plan = repo.get(original.plan_id)
    expect = case["expect"]
    if "status" in expect:
        assert plan.status.value == expect["status"]
    if "selected" in expect:
        assert {p.period.key: list(p.selected) for p in plan.periods} == expect["selected"]
    if "plan_events" in expect:
        assert _selection_events(plan) == expect["plan_events"]
        assert all(e.actor_id == TEACHER for e in plan.audit if e.selection_change)
    if expect.get("candidates_unchanged"):
        assert [p.candidates for p in plan.periods] == [p.candidates for p in original.periods]
    if "item" in expect:
        want = expect["item"]
        item = _item(plan, want["period"], want["row"], want["field"])
        assert [e.event_type.value for e in item.audit] == want["events"]
        if "value" in want:
            assert item.value == want["value"]
        if "generation_method" in want:
            assert item.generation.method.value == want["generation_method"]
            assert item.generation == _item(original, want["period"], want["row"], want["field"]).generation
            assert item.evidence == _item(original, want["period"], want["row"], want["field"]).evidence
    if "last_plan_event" in expect:
        last = plan.audit.events[-1]
        assert last.event_type.value == expect["last_plan_event"]["type"]
        assert last.actor_id.value == expect["last_plan_event"]["actor"]


def test_candidates_selected_is_a_plan_level_teacher_event_only():
    from ssuksak.planning.domain.errors import InvalidDomainValueError
    from ssuksak.planning.domain.identifiers import ItemId, PlanId
    from ssuksak.planning.domain.provenance import (
        AuditEvent,
        SelectionChange,
        ValueChange,
    )

    at, plan_id = CLOCK.now(), PlanId("p")
    change = SelectionChange("m03_m05", (), ("cand1",))
    AuditEvent(AuditEventType.CANDIDATES_SELECTED, at, plan_id, actor_id=TEACHER, selection_change=change)
    bad = [
        {"system_actor": "sys", "selection_change": change},
        {"actor_id": TEACHER},
        {"actor_id": TEACHER, "selection_change": change, "item_id": ItemId("i")},
        {"actor_id": TEACHER, "selection_change": change, "value_change": ValueChange("a", "b")},
    ]
    for kwargs in bad:
        with pytest.raises(InvalidDomainValueError):
            AuditEvent(AuditEventType.CANDIDATES_SELECTED, at, plan_id, **kwargs)
    with pytest.raises(InvalidDomainValueError):
        AuditEvent(AuditEventType.CONFIRMED, at, plan_id, actor_id=TEACHER, selection_change=change)
    for before, after in [(("cand1",), ("cand1",)), ((), ("cand1", "cand1")), (("",), ())]:
        with pytest.raises(InvalidDomainValueError):
            SelectionChange("m03_m05", before, after)
