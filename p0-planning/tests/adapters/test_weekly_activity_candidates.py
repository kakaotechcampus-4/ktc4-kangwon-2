import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from ssuksak.adapters.institution_evidence_repository import (
    InMemoryInstitutionEvidenceRepository,
)
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.adapters.weekly_composition import weekly_activities
from ssuksak.planning.application.generate_weekly_plan import (
    WeeklyApplicationError,
    _classified_evidence,
)
from ssuksak.planning.domain.identifiers import ActorId, ItemId
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.provenance import AuditEventType, SplitAxis
from ssuksak.planning.domain.weekly_plan import WeeklyPlan
from ssuksak.planning.evidence.models import SourceSection
from ssuksak.planning.evidence.weekly_classification import (
    WeeklyEvidenceClassification,
    WeeklySemanticClass,
)
from tests.adapters.test_weekly_composition import _day_command, _day_generation
from tests.adapters.test_weekly_llm_adapter import MockTransport, _adapter
from tests.finalization.weekly_harness import WeeklyHarness
from tests.retrieval.test_weekly_retrieval import _record


def generated():
    harness, provider = WeeklyHarness(), RequestAwareWeeklyLlm()
    parent = harness.monthly_parent(mode=MonthlyGenerationMode.LLM_PLANNER)
    plan = _day_generation(harness, provider).execute(replace(_day_command(parent), activity_candidates=True)).plan
    use_case = weekly_activities(plan_repository=harness.weekly_plans, parent_plan_repository=harness.monthly_plans,
                                clock=harness.clock, id_generator=harness.weekly_ids)
    return harness, provider, plan, use_case


def test_candidate_ranking_uses_monthly_theme_but_not_weekly_focus_or_week_order():
    parent = WeeklyHarness().monthly_parent(mode=MonthlyGenerationMode.LLM_PLANNER)
    records = tuple(_record(f"ev_{i}", label="이야기 나누기", text=text, institution=str(i))
                    for i, text in enumerate(("가을 열매 이야기", "교통기관 자동차 이야기", "세계 여러 나라 인사"), 1))
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    classification = WeeklyEvidenceClassification("weekly-classification-test", store.content_sha256,
        ((SourceSection.INDOOR_PLAY, "이야기 나누기", WeeklySemanticClass.GROUP_ACTIVITY),))
    week = _day_command(parent).week_id
    other_week = next(w.week_id for w in parent.week_periods if w.active and w.week_id != week)

    def selected(theme, focus, selected_week=week):
        values = {"theme": theme, "focus": focus}
        changed = replace(parent, sections=tuple(
            replace(section, cells=tuple(replace(cell, value=values[section.section_key]) for cell in section.cells))
            if section.section_key in values else section for section in parent.sections))
        items = _classified_evidence(store, classification, changed, selected_week, {"group_activity"},
                                     focus_aware=True, activity_candidates=True)["group_activity"]
        return tuple(item.record_id for item in items)

    autumn = selected("가을 열매", "교통기관")
    assert autumn[0] == "ev_1"
    assert selected("교통기관", "가을 열매")[0] == "ev_2"
    assert selected("가을 열매", "세계 여러 나라 인사") == autumn
    assert selected("가을 열매", "세계 여러 나라 인사", other_week) == autumn


def test_candidates_are_unplaced_and_copy_split_remove_preserve_history_and_codec():
    harness, provider, plan, actions = generated()
    assert 2 <= len(plan.activity_candidates) <= 10
    assert len({c.activity_type for c in plan.activity_candidates}) >= 2
    assert len(plan.activity_grids) == 5
    cells = [c for c in plan.cells if c.section_key == "group_activity"]
    assert all(not c.value for c in cells)
    actor = ActorId("test_teacher")
    candidate = plan.activity_candidates[0]
    copied = actions.copy(plan.plan_id, cells[0].item_id, candidate.cell.item_id, actor)
    assert copied.find_cell(cells[0].item_id).value == f"[{candidate.activity_type}] {candidate.name}"
    assert actions.copy(plan.plan_id, cells[0].item_id, candidate.cell.item_id, actor) is copied
    split = actions.split(plan.plan_id, cells[0].item_id, actor, axis=SplitAxis.VERTICAL)
    assert split.find_cell(cells[0].item_id) == copied.find_cell(cells[0].item_id)
    new_id = split.activity_grids[0].leaves()[1]
    assert split.find_cell(new_id).value == ""
    filled = actions.copy(plan.plan_id, new_id, plan.activity_candidates[1].cell.item_id, actor)
    removed = actions.remove(plan.plan_id, new_id, actor)
    assert removed.removed_activity_cells[-1] == filled.find_cell(new_id)
    assert removed.activity_grids[0].cell == cells[0].item_id
    assert removed.find_cell(cells[0].item_id).audit.events[-1].event_type is AuditEventType.CANDIDATE_COPIED
    spec = importlib.util.spec_from_file_location("weekly_activity_codec", Path(__file__).parents[3] / "backend/app/features/plans/codec.py")
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    assert codec.from_jsonable(WeeklyPlan, codec.to_jsonable(removed)) == removed
    assert len(provider.requests) == 1


def test_foreign_candidate_and_narrow_splits_do_not_save():
    harness, _, plan, actions = generated()
    cell = next(c for c in plan.cells if c.section_key == "group_activity")
    actor = ActorId("test_teacher")
    with pytest.raises(WeeklyApplicationError):
        actions.copy(plan.plan_id, cell.item_id, ItemId("foreign_candidate"), actor)
    assert harness.weekly_plans.get(plan.plan_id) is plan
    plan = actions.split(plan.plan_id, cell.item_id, actor, axis=SplitAxis.HORIZONTAL)
    plan = actions.split(plan.plan_id, cell.item_id, actor, axis=SplitAxis.HORIZONTAL)
    with pytest.raises(WeeklyApplicationError):
        actions.split(plan.plan_id, cell.item_id, actor, axis=SplitAxis.HORIZONTAL)
    assert harness.weekly_plans.get(plan.plan_id) is plan


def test_bad_candidate_format_repairs_once_and_records_the_repair_version():
    class BrokenOnce(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            if len(self.requests) != 1:
                return response
            answer = json.loads(response.content)
            candidate = next(s for s in answer["sections"] if s["section_key"].startswith("group_activity.candidate."))
            candidate["value"] = "An activity without its description"
            return replace(response, content=json.dumps(answer))

    harness, provider = WeeklyHarness(), BrokenOnce()
    parent = harness.monthly_parent(mode=MonthlyGenerationMode.LLM_PLANNER)
    plan = _day_generation(harness, provider).execute(replace(_day_command(parent), activity_candidates=True)).plan
    assert len(provider.requests) == 2
    assert plan.activity_candidates[0].cell.generation.rule_version == provider.requests[0].repair_prompt_version


def test_candidate_generation_and_repair_use_streaming_with_an_output_cap():
    def break_candidate(answer):
        next(s for s in answer["sections"] if s["section_key"].startswith("group_activity.candidate."))["value"] = "Missing description"

    class StreamingTransport(MockTransport):
        def post_stream(self, url, *, headers, payload, timeout):
            return self.post_json(url, headers=headers, payload=payload, timeout=timeout)

    harness = WeeklyHarness()
    transport = StreamingTransport(break_candidate, None)
    parent = harness.monthly_parent(mode=MonthlyGenerationMode.LLM_PLANNER)
    plan = _day_generation(harness, _adapter(transport)).execute(replace(_day_command(parent), activity_candidates=True)).plan
    assert plan.activity_candidates and len(transport.calls) == 2
    assert all(p["stream"] is True and p["max_completion_tokens"] == 6000 for p in transport.calls)
