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
    from ssuksak.planning.planner.play_monthly import SYSTEM_PROMPT as PLAY_MONTHLY_PROMPT
    from ssuksak.planning.planner.v1_guidance import NATURAL_PLAY_GUIDANCE
    from ssuksak.planning.planner.weekly import CANDIDATE_DESCRIPTION_TONE, LINKED_OUTDOOR_INSTRUCTION, LINKED_WRITING_GUIDANCE

    assert NATURAL_PLAY_GUIDANCE in PLAY_MONTHLY_PROMPT
    for request in provider.requests:
        body = json.loads(request.user_content)
        body = body.get("original_request", body)
        texts = dict(request.evidence_texts)
        for target in body["targets"]:
            if target.get("activity_type"):
                assert any(target["activity_basis"] in texts[ref] for ref in target["allowed_grounding_refs"])
                assert target["required_name_terms"] == list(request.target(target["section_key"]).required_name_terms)
        assert "+monthly-linked-v8" in request.prompt_version
        assert "설명의 대상과 실제 행동을 남겨 문서용 활동명을 쓴다" in request.system_prompt
        assert "유형과 활동명만 읽어도 할 일이 떠올라야 한다" in request.system_prompt
        assert "서로 섞어 새 활동을 만들지 않는다" in request.system_prompt
        assert "+activity-candidates-v5" in request.prompt_version
        assert "+activity-candidates-v5" in request.repair_prompt_version
        assert request.system_prompt.count(NATURAL_PLAY_GUIDANCE) == 1
        assert request.system_prompt.count(CANDIDATE_DESCRIPTION_TONE) == 1
        assert "소리는 듣는 대상이며" not in request.system_prompt
        assert LINKED_OUTDOOR_INSTRUCTION in request.system_prompt
        assert LINKED_WRITING_GUIDANCE.replace(
            "허용 근거로 이어갈 수 없으면 빈칸으로 두고 관계없는 놀이로 채우지 않는다. ", ""
        ) in request.system_prompt
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
    assert row.value == f"[{candidates[0].activity_type}] {candidates[0].name}"
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
    from ssuksak.planning.planner.v1_guidance import NATURAL_PLAY_GUIDANCE
    from ssuksak.planning.planner.weekly import CANDIDATE_DESCRIPTION_TONE

    assert NATURAL_PLAY_GUIDANCE in request.system_prompt
    assert CANDIDATE_DESCRIPTION_TONE in request.system_prompt

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


# ── ADR-072: 트렌드봇 자료를 주간 활동 후보에 ─────────────────────────────────

def _trend_items():
    from datetime import date

    from ssuksak.planning.domain.trend import TrendItem, TrendKind

    return tuple(TrendItem(f"youtube:t{n}", kind, f"{kind.value} 자료 {n}", "자료 설명", "테스트 채널", "2026-W44",
                           date(2026, 10, 28)) for n, kind in enumerate(TrendKind))


class _Trends:
    def __init__(self, items=(), *, fail=False):
        self.items, self.fail = items, fail

    def fetch(self, name):
        from ssuksak.planning.application.ports import OptionalContextResult, OptionalContextStatus

        if self.fail:
            return OptionalContextResult(name, OptionalContextStatus.ERROR, detail="unreadable")
        if not self.items:
            return OptionalContextResult(name, OptionalContextStatus.UNAVAILABLE, detail="none")
        return OptionalContextResult(name, OptionalContextStatus.AVAILABLE, self.items)


def _trend_generate(provider, trends, memo=""):
    from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
    from ssuksak.adapters.weekly_composition import weekly_generation

    harness = WeeklyHarness()
    parent = harness.monthly_parent(mode=MonthlyGenerationMode.LLM_PLANNER)
    use_case = weekly_generation(
        parent_plan_repository=harness.monthly_plans, plan_repository=harness.weekly_plans, provider=provider,
        clock=harness.clock, id_generator=harness.weekly_ids, optional_context=trends,
        template_repository=JsonMonthlyTemplateRepository(
            paths=(Path(__file__).parents[2] / "data/templates/weekly_template_a_v0_2_0.json",)),
    )
    command = replace(_day_command(parent), activity_candidates=True, indoor_play_candidates=True, teacher_memo=memo,
                      optional_context_names=() if trends is None else ("trend",))
    return harness, use_case.execute(command).plan


def _trend_source(cell):
    from ssuksak.planning.domain.provenance import EvidenceSourceType

    return [s for s in cell.evidence if s.source_type is EvidenceSourceType.TREND]


def test_trend_goes_only_to_fitting_candidates_and_leaves_trend_evidence():
    from ssuksak.planning.planner.trend import TREND_PROMPT, TREND_PROMPT_TAG
    from ssuksak.planning.planner.weekly import (
        INDOOR_AREA_TREND_KINDS,
        INDOOR_PLAY_TREND_KINDS,
        TREND_KINDS_BY_ACTIVITY_TYPE,
        WeeklyTarget,
        trend_options,
        weekly_response_schema,
    )

    provider = RequestAwareWeeklyLlm()
    _, plan = _trend_generate(provider, _Trends(_trend_items()))
    request = provider.requests[0]
    assert request.trend_options and TREND_PROMPT_TAG in request.prompt_version
    assert TREND_PROMPT in request.system_prompt and "trend_applied" in weekly_response_schema(request)["properties"]
    kinds = {i.trend_id: i.kind for i in request.trends}
    for address, ids in request.trend_options:  # Rule: the kind fits the candidate's type; candidates only
        target = request.target(address)
        fits = INDOOR_AREA_TREND_KINDS.get(target.activity_type, INDOOR_PLAY_TREND_KINDS) if address.startswith(
            "indoor_play.candidate.") else {
            TREND_KINDS_BY_ACTIVITY_TYPE[w] for w in target.activity_type.split("·") if w in TREND_KINDS_BY_ACTIVITY_TYPE}
        assert target.activity_type and ids and {kinds[i] for i in ids} <= fits
    body = json.loads(request.user_content)
    assert all("trend_ids" not in t for t in body["targets"] if not t.get("activity_type"))
    trended = [c for c in plan.activity_candidates if _trend_source(c.cell)]
    assert len(trended) == 1
    source = _trend_source(trended[0].cell)[0]
    assert (source.source_id, source.source_version) == (request.trend_options[0][1][0], "2026-W44")
    assert TREND_PROMPT_TAG in trended[0].cell.generation.rule_version
    assert not any(s.source_type.value == "INSTITUTION_SAMPLE" for s in trended[0].cell.evidence)
    role, play = (next(i for i in request.trends if i.kind.value == k) for k in ("역할", "놀이"))
    assert trend_options((WeeklyTarget("indoor_play.candidate.1", activity_type="역할놀이"),
                          WeeklyTarget("indoor_play.candidate.2", activity_type="쌓기놀이")), (role, play)) == (
        ("indoor_play.candidate.1", (role.trend_id, play.trend_id)), ("indoor_play.candidate.2", (play.trend_id,)))
    story = next(i for i in request.trends if i.kind.value == "동화")  # 그림책: 언어놀이 영역 · 이야기나누기에도 (2026-11-10)
    assert trend_options((WeeklyTarget("indoor_play.candidate.1", activity_type="언어놀이"),
                          WeeklyTarget("group_activity.candidate.1", activity_type="이야기나누기")), (story, play)) == (
        ("indoor_play.candidate.1", (story.trend_id, play.trend_id)), ("group_activity.candidate.1", (story.trend_id,)))


@pytest.mark.parametrize("case", ["written", "repaired", "fallback"])
def test_picture_book_is_assigned_to_one_story_candidate_and_repaired_once_or_kept_without_it(case):
    from datetime import date

    from ssuksak.planning.domain.trend import TrendItem, TrendKind
    from ssuksak.planning.planner.contracts import RawLlmResponse
    from ssuksak.planning.planner.weekly import BOOK_SLOT_TAG, WEEKLY_BOOK_PROMPT

    book = TrendItem("data4library:9790000000001", TrendKind.STORY, "숲속 친구들 :겨울 이야기", "", "도서관 정보나루",
                     "2026-W44", date(2026, 10, 28))

    class NoTitle(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            if case == "written" or (request.repair_targets and case == "repaired"):
                return response
            answer = json.loads(response.content)
            slot = self.requests[0].trend_required[0]
            section = next(s for s in answer["sections"] if s["section_key"] == slot)
            section["value"] = "겨울 이야기: 겨울 이야기를 나눕니다."
            if request.repair_targets:  # fallback: the repair writes the slot from its own institution basis
                section["grounding_refs"] = list(request.target(slot).allowed_grounding_refs[:1])
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), response.model)

    provider = NoTitle()
    _, plan = _trend_generate(provider, _Trends((*_trend_items(), book)))
    first = provider.requests[0]
    slot, assigned = first.trend_required
    assert assigned == book and dict(first.trend_options)[slot] == (book.trend_id,)
    assert BOOK_SLOT_TAG in first.prompt_version and WEEKLY_BOOK_PROMPT in first.system_prompt
    target = next(t for t in json.loads(first.user_content)["targets"] if t["section_key"] == slot)
    assert target["trend_required"] == {"trend_id": book.trend_id, "title": "숲속 친구들"}  # subtitle off: no 「:」 clash
    assert len(provider.requests) == (1 if case == "written" else 2)
    if case != "written":
        fix = json.loads(provider.requests[1].user_content)["fix_sections"]
        assert [(f["section_key"], f["issue"]) for f in fix] == [(slot, "TREND_REQUIRED_MISSING")]
        assert "『숲속 친구들』" in fix[0]["reason"]
    books = [s for c in plan.activity_candidates for s in _trend_source(c.cell) if s.source_id == book.trend_id]
    assert len(books) == (0 if case == "fallback" else 1)  # §7: a missing book never fails the generation


def test_trend_not_allowed_for_that_candidate_is_rejected_and_nothing_saved():
    from ssuksak.planning.planner.contracts import ProposalParseError, RawLlmResponse

    class WrongTrend(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            answer = json.loads(response.content)
            address, ids = request.trend_options[0]
            other = next(i.trend_id for i in request.trends if i.trend_id not in ids)
            answer["trend_applied"] = [{"address": address, "trend_id": other}]
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), response.model)

    provider = WrongTrend()
    with pytest.raises(WeeklyApplicationError) as error:
        _trend_generate(provider, _Trends(_trend_items()))
    assert isinstance(error.value.__cause__, ProposalParseError) and len(provider.requests) == 1


def test_third_trend_in_one_list_is_repaired_once_without_its_mark():
    from ssuksak.planning.planner.contracts import RawLlmResponse
    from ssuksak.planning.planner.weekly import weekly_response_schema

    class ThreeIndoor(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            if request.repair_targets:
                return response
            answer = json.loads(response.content)
            indoor = [(a, ids) for a, ids in request.trend_options if a.startswith("indoor_play.")][:3]
            answer["trend_applied"] = [{"address": a, "trend_id": ids[0]} for a, ids in indoor]
            for section in answer["sections"]:
                if section["section_key"] in dict(indoor):
                    section["grounding_refs"] = []
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), response.model)

    provider = ThreeIndoor()
    _, plan = _trend_generate(provider, _Trends(_trend_items()))
    assert len(provider.requests) == 2
    repair = provider.requests[1]
    third = [a for a, _ in provider.requests[0].trend_options if a.startswith("indoor_play.")][2]
    assert json.loads(repair.user_content)["fix_sections"] == [{"section_key": third, "issue": "TREND_SHARE_EXCEEDED"}]
    assert "trend_applied" not in weekly_response_schema(repair)["properties"]
    indoor = [c for c in plan.activity_candidates if c.cell.section_key == "indoor_play"]
    assert [bool(_trend_source(c.cell)) for c in indoor[:3]] == [True, True, False]
    assert indoor[2].cell.generation.rule_version == provider.requests[0].repair_prompt_version


@pytest.mark.parametrize("fixed", [True, False])
def test_trend_candidate_citing_an_institution_record_is_repaired_once_or_rejected(fixed):
    from ssuksak.planning.planner.contracts import ProposalRejectedError, RawLlmResponse

    class Mixed(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            answer = json.loads(response.content)
            address = self.requests[0].trend_options[0][0]
            section = next(s for s in answer["sections"] if s["section_key"] == address)
            refs = list(request.target(address).allowed_grounding_refs[:1])
            section["grounding_refs"] = [] if request.repair_targets and fixed else refs
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), response.model)

    provider = Mixed()
    if not fixed:
        with pytest.raises(WeeklyApplicationError) as error:
            _trend_generate(provider, _Trends(_trend_items()))
        assert "TREND_GROUNDING_MIXED" in error.value.__cause__.validation_codes
        assert isinstance(error.value.__cause__, ProposalRejectedError) and len(provider.requests) == 2
        return
    _, plan = _trend_generate(provider, _Trends(_trend_items()))
    assert len(provider.requests) == 2
    address = provider.requests[0].trend_options[0][0]
    assert json.loads(provider.requests[1].user_content)["fix_sections"] == [
        {"section_key": address, "issue": "TREND_GROUNDING_MIXED"}]
    trended = next(c for c in plan.activity_candidates if _trend_source(c.cell))
    assert not any(s.source_type.value == "INSTITUTION_SAMPLE" for s in trended.cell.evidence)
    assert trended.cell.generation.rule_version == provider.requests[0].repair_prompt_version


def _untrended_candidate(request):
    """A candidate the mock does not write from a trend: the name check covers every candidate."""
    return next(t.section_key for t in request.targets if t.activity_type and t.section_key != request.trend_options[0][0])


@pytest.mark.parametrize("case", ["fixed", "unfixed", "memo"])
def test_channel_or_character_name_in_a_candidate_is_repaired_once_unless_the_teacher_wrote_it(case):
    from ssuksak.planning.planner.contracts import ProposalRejectedError, RawLlmResponse

    class Named(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            if request.repair_targets and case == "fixed":
                return response
            answer = json.loads(response.content)
            address = _untrended_candidate(self.requests[0])
            section = next(s for s in answer["sections"] if s["section_key"] == address)
            section["value"] = section["value"].replace(": ", ": 뽀 로로와 함께 ", 1)  # spacing is not looked at
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), response.model)

    trends = _Trends(tuple(replace(item, name_words=("뽀로로",)) for item in _trend_items()))
    provider = Named()
    memo = "뽀로로 노래로 놀이해요" if case == "memo" else ""
    if case == "unfixed":
        with pytest.raises(WeeklyApplicationError) as error:
            _trend_generate(provider, trends, memo)
        assert isinstance(error.value.__cause__, ProposalRejectedError) and len(provider.requests) == 2
        assert "TREND_NAME_IN_TEXT" in error.value.__cause__.validation_codes
        return
    _trend_generate(provider, trends, memo)
    if case == "memo":
        assert len(provider.requests) == 1
        return
    assert len(provider.requests) == 2
    address = _untrended_candidate(provider.requests[0])
    assert {"section_key": address, "issue": "TREND_NAME_IN_TEXT",
            "reason": "채널 · 프로그램 · 캐릭터 이름을 빼고 놀이 내용만 다시 쓴다"} in json.loads(
        provider.requests[1].user_content)["fix_sections"]


LYRIC = "‘산토끼 토끼야 어디를 가느냐 깡충깡충 뛰면서 어디를 가느냐’ 노래를 부르며 "


@pytest.mark.parametrize("fixed", [True, False])
def test_lyrics_in_a_candidate_are_repaired_once_then_rejected(fixed):
    """ADR-072 결정 12: 가사 꼴은 결정적 검사로 고쳐 쓰기 1회, 남으면 생성이 실패한다(저장하지 않는다)."""
    from ssuksak.planning.planner.contracts import ProposalRejectedError, RawLlmResponse
    from ssuksak.planning.planner.weekly import TREND_LYRICS_REPAIR

    class Sung(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            response = super().generate_weekly(request)
            if request.repair_targets and fixed:
                return response
            answer = json.loads(response.content)
            address = _untrended_candidate(self.requests[0])
            section = next(s for s in answer["sections"] if s["section_key"] == address)
            section["value"] = section["value"].replace(": ", ": " + LYRIC, 1)
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), response.model)

    provider = Sung()
    if not fixed:
        with pytest.raises(WeeklyApplicationError) as error:
            _trend_generate(provider, _Trends(_trend_items()))
        assert isinstance(error.value.__cause__, ProposalRejectedError) and len(provider.requests) == 2
        assert "TREND_LYRICS_IN_TEXT" in error.value.__cause__.validation_codes
        return
    _trend_generate(provider, _Trends(_trend_items()))
    assert len(provider.requests) == 2
    address = _untrended_candidate(provider.requests[0])
    assert {"section_key": address, "issue": "TREND_LYRICS_IN_TEXT", "reason": TREND_LYRICS_REPAIR} in json.loads(
        provider.requests[1].user_content)["fix_sections"]


@pytest.mark.parametrize("trends", [_Trends(fail=True), _Trends(())])
def test_no_trend_or_failed_provider_sends_the_same_request(trends):
    from ssuksak.planning.planner.weekly import weekly_response_schema

    def first(trend_provider):
        provider = RequestAwareWeeklyLlm()
        _, plan = _trend_generate(provider, trend_provider)
        assert not any(_trend_source(c.cell) for c in plan.activity_candidates)
        request = provider.requests[0]
        return (request.prompt_version, request.system_prompt, request.user_content,
                request.request_fingerprint, json.dumps(weekly_response_schema(request), sort_keys=True))

    assert first(trends) == first(None)
    assert "+trend-v1" not in first(trends)[0]
