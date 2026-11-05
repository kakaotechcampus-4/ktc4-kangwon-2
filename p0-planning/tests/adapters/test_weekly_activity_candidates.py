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


def generated(*, indoor=False):
    harness, provider = WeeklyHarness(), RequestAwareWeeklyLlm()
    parent = harness.monthly_parent(mode=MonthlyGenerationMode.LLM_PLANNER)
    plan = _day_generation(harness, provider).execute(replace(_day_command(parent), activity_candidates=True, indoor_play_candidates=indoor)).plan
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


@pytest.mark.parametrize("indoor", [False, True])
def test_bad_candidate_format_repairs_once_and_records_the_repair_version(indoor):
    section = "indoor_play" if indoor else "group_activity"

    class BrokenOnce(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            if len(self.requests) != 1:
                return response
            answer = json.loads(response.content)
            candidate = next(s for s in answer["sections"] if s["section_key"].startswith(section + ".candidate."))
            candidate["value"] = "An activity without its description"
            return replace(response, content=json.dumps(answer))

    harness, provider = WeeklyHarness(), BrokenOnce()
    parent = harness.monthly_parent(mode=MonthlyGenerationMode.LLM_PLANNER)
    plan = _day_generation(harness, provider).execute(replace(
        _day_command(parent), activity_candidates=True, indoor_play_candidates=indoor,
    )).plan
    assert len(provider.requests) == 2
    repaired = next(c for c in plan.activity_candidates if c.cell.section_key == section)
    assert repaired.cell.generation.rule_version == provider.requests[0].repair_prompt_version
    from ssuksak.planning.planner.weekly import LINKED_OUTDOOR_INSTRUCTION, LINKED_WRITING_GUIDANCE
    for request in provider.requests:
        body = json.loads(request.user_content)
        body = body.get("original_request", body)
        texts = dict(request.evidence_texts)
        for target in body["targets"]:
            if target.get("activity_type"):
                assert any(target["activity_basis"] in texts[ref] for ref in target["allowed_grounding_refs"])
                assert target["required_name_terms"] == list(request.target(target["section_key"]).required_name_terms)
        assert "+monthly-linked-v7" in request.prompt_version
        assert "설명의 대상과 실제 행동을 남겨 문서용 활동명을 쓴다" in request.system_prompt
        assert "유형과 활동명만 읽어도 할 일이 떠올라야 한다" in request.system_prompt
        assert "서로 섞어 새 활동을 만들지 않는다" in request.system_prompt
        assert "+activity-candidates-v4" in request.prompt_version
        assert "+activity-candidates-v4" in request.repair_prompt_version
        assert LINKED_OUTDOOR_INSTRUCTION in request.system_prompt
        assert LINKED_WRITING_GUIDANCE in request.system_prompt
        assert "작품명과 익숙한 놀이명은 유지" in request.system_prompt
        assert "근거에 없는 재료·놀이 방법·절차·결과물을 보태지 않는다" in request.system_prompt


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


def test_indoor_candidates_choose_reorder_remove_and_keep_history():
    harness, provider, plan, actions = generated(indoor=True)
    actor = ActorId("test_teacher")
    candidates = [c for c in plan.activity_candidates if c.cell.section_key == "indoor_play"]
    assert 2 <= len(candidates) <= 10
    assert not plan.cell("indoor_play").value
    assert "합니다체 1~2문장" in provider.requests[0].system_prompt
    first = actions.add_indoor(plan.plan_id, candidates[0].cell.item_id, actor)
    row = first.cell("indoor_play")
    assert row.value == f"[{candidates[0].activity_type}] - {candidates[0].name}"
    assert row.evidence == candidates[0].cell.evidence
    assert row.audit.events[-1].copied_from == candidates[0].cell.item_id
    assert actions.add_indoor(plan.plan_id, candidates[0].cell.item_id, actor) is first
    second = actions.add_indoor(plan.plan_id, candidates[1].cell.item_id, actor)
    rows = [c for c in second.cells if c.section_key == "indoor_play"]
    assert len(rows) == 2 and rows[0].item_id == row.item_id
    ordered = actions.order_indoor(plan.plan_id, tuple(c.item_id for c in reversed(rows)), actor)
    assert ordered.cell("indoor_play").item_id == rows[1].item_id
    with pytest.raises(WeeklyApplicationError):
        actions.order_indoor(plan.plan_id, (rows[0].item_id, rows[0].item_id), actor)
    removed = actions.remove_indoor(plan.plan_id, rows[0].item_id, actor)
    empty = actions.remove_indoor(plan.plan_id, rows[1].item_id, actor)
    assert not empty.cell("indoor_play").value
    assert {c.item_id for c in empty.removed_activity_cells} >= {c.item_id for c in rows}
    assert removed.audit.events[-1].arrangement_change.scope == "indoor_play"
    group = next(c for c in empty.activity_candidates if c.cell.section_key == "group_activity")
    with pytest.raises(WeeklyApplicationError):
        actions.add_indoor(plan.plan_id, group.cell.item_id, actor)


def test_indoor_area_uses_source_labels_without_guessing():
    from types import SimpleNamespace
    from ssuksak.planning.retrieval.weekly import indoor_play_type

    for label, text, expected in [("역할 놀이", "가게 꾸미기", "역할놀이"),
                                  ("실내놀이", "[쌓기] 길 만들기", "쌓기놀이"),
                                  ("실내놀이", "가게에서 역할을 나눠요", "기타")]:
        assert indoor_play_type(SimpleNamespace(source_label=label, text=text)) == expected


def test_candidate_name_duplicates_are_checked_within_each_pool():
    from ssuksak.planning.planner.weekly import (
        WeeklyIssueCode,
        parse_weekly_proposal,
        validate_weekly,
    )

    _, provider, _, _ = generated(indoor=True)
    request = provider.requests[0]
    values = parse_weekly_proposal(provider.generate_weekly(request).content, request)
    indoor = [v for v in values if v.section_key.startswith("indoor_play.candidate.")]
    group = next(v for v in values if v.section_key.startswith("group_activity.candidate."))
    name = group.value.partition(":")[0]

    def with_name(value):
        return replace(value, value=f"{name}: {value.value.partition(':')[2]}")

    cross_pool = tuple(with_name(v) if v == indoor[0] else v for v in values)
    assert not any(i.code is WeeklyIssueCode.ACTIVITY_CANDIDATE_INVALID
                   for i in validate_weekly(cross_pool, request))
    same_pool = tuple(with_name(v) if v == indoor[1] else v for v in cross_pool)
    assert any(i.code is WeeklyIssueCode.ACTIVITY_CANDIDATE_INVALID
               and i.section_key == indoor[1].section_key for i in validate_weekly(same_pool, request))


@pytest.mark.parametrize("persistent", [False, True])
@pytest.mark.parametrize("ref,text,kind,bad,good", [
    ("ev_e5e84e83db52_p01_r00428_c01_i01", "<이야기 나누기> 편지 발표, 함께 지켜요", "이야기나누기",
     "함께 지킬 약속: 함께 생활하며 지킬 약속에는 무엇이 있을지 생각을 나누고 서로의 이야기를 듣습니다.",
     "우리 반 편지 발표하기: 편지에 담은 내용을 친구들에게 발표합니다."),
    ("ev_f1afbbe9ddcc_p02_r00589_c02_i01", "[명화] 피터브뢰겔의 ‘아이들 놀이’", "미술",
     "피터 브뢰겔의 ‘아이들 놀이’: 그림 속 아이들의 놀이 모습과 움직임을 감상하며 눈에 들어오는 장면을 이야기합니다.",
     "피터 브뢰겔의 ‘아이들 놀이’ 감상: 그림 속 아이들의 놀이 장면을 함께 감상합니다."),
])
def test_real_title_omissions_repair_once_and_persistent_omissions_are_rejected(ref, text, kind, bad, good, persistent):
    from ssuksak.planning.domain.week_period import WeekId
    from ssuksak.planning.planner.contracts import ProposalRejectedError
    from ssuksak.planning.planner.weekly import WeeklyPlanner, WeeklyTarget, build_weekly_request
    from ssuksak.planning.retrieval.weekly import candidate_activity_basis

    basis, terms = candidate_activity_basis(_record(ref, text=text))
    key = "group_activity.candidate.1"
    request = build_weekly_request(week_id=WeekId("2026-03-W1"), week={}, ages=(3, 4),
        targets=(WeeklyTarget("theme"), WeeklyTarget(key, (ref,), activity_type=kind,
            activity_basis=basis, required_name_terms=terms)),
        teacher_input_keys=frozenset(), parent_context=(("theme", "우리 원과 친구"),),
        evidence=((ref, text, "GROUP_ACTIVITY"),), reference_candidates=(), packet_fingerprint="")

    class Drift(RequestAwareWeeklyLlm):
        def generate_weekly(self, current):
            response = super().generate_weekly(current)
            answer = json.loads(response.content)
            next(v for v in answer["sections"] if v["section_key"] == key)["value"] = (
                bad if persistent or len(self.requests) == 1 else good
            )
            return replace(response, content=json.dumps(answer, ensure_ascii=False))

    provider = Drift()
    if persistent:
        with pytest.raises(ProposalRejectedError) as error:
            WeeklyPlanner(provider).plan(request)
        assert error.value.validation_codes == ("ACTIVITY_CANDIDATE_INVALID",)
    else:
        outcome = WeeklyPlanner(provider).plan(request)
        assert outcome.repaired == frozenset({key})
        assert next(v for v in outcome.values if v.section_key == key).value == good
    assert len(provider.requests) == 2
    repaired = json.loads(provider.requests[1].user_content)["original_request"]
    target = next(t for t in repaired["targets"] if t["section_key"] == key)
    assert target["activity_basis"] == basis and target["required_name_terms"] == list(terms)
    with pytest.raises(ValueError, match="allowed evidence"):
        replace(request, targets=(request.targets[0], replace(request.targets[1], activity_basis="근거에 없는 활동")))
