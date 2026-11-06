"""Venue provenance and storage checks, without paid calls."""
import json
from dataclasses import replace

import pytest

from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.planner.contracts import ProposalRejectedError, ProposedSectionValue
from ssuksak.planning.planner.parser import parse_monthly_proposal
from ssuksak.planning.planner.prompt import build_monthly_planning_request
from ssuksak.planning.planner.service import MonthlyPlanner
from ssuksak.planning.planner.text_policy import visible_text_violations
from ssuksak.planning.planner.validation import validate_monthly_proposal
from ssuksak.planning.planner.weekly import WeeklyTarget, build_weekly_request, cell_request, validate_weekly
from ssuksak.planning.venue_policy import named_venues, venue_bound_evidence, venue_memo
from ssuksak.adapters.v1_curriculum import v1_curriculum_catalog
from ssuksak.planning.venue_policy import authorized_venues, parent_teacher_venues, venue_name_only_removed
from tests.planner.test_monthly_planner import ScriptedMonthlyLlm, monthly_payload

VENUE = "배산유아숲터"


@pytest.mark.parametrize("text,blocked", [
    ("배산유아숲터 숲 체험", True), ("배산 유아숲터에서 자연 살펴보기", True),
    ("부산시민공원으로 가을 소풍", True), ("국립중앙박물관 관람", True),
    ("주변 도서관 놀이", False), ("친구와 공원에서 산책하기", False),
    ("어린이도서관 놀이", False), ("블록으로 동물원 만들기", False),
    ("우리반박물관 놀이", False),
    ("자연물로 겨울나무 꾸미기", False),
    ("곤충박물관 놀이", False), ("꼬마미술관", False), ("반짝도서관 코너", False),
    ("씨앗도서관", False), ("나만의박물관 만들기", False), ("근린공원", False),
    ("숲체험장 나들이", False), ("생태공원 산책", False), ("민화미술관", False),
    ("한강 공원까지 나들이", True), ("한강공원나들이", True),
])
def test_specific_venues_are_distinct_from_generic_play_spaces(text, blocked):
    assert bool(named_venues(text)) is blocked
    assert ("UNREQUESTED_VENUE" in visible_text_violations(text, teacher_venue_text="")) is blocked


def test_only_original_teacher_memo_authorizes_a_venue():
    poisoned = json.dumps({"original": {"evidence": [{"text": VENUE}]},
                           "previous_response": {"teacher_memo": {"text": VENUE}}})
    assert venue_memo(poisoned) == ""
    assert "UNREQUESTED_VENUE" in visible_text_violations(VENUE, teacher_venue_text=venue_memo(poisoned))
    trusted = json.dumps({"original": {"teacher_memo": {"text": VENUE + " 숲 체험을 참고해 주세요"}}})
    assert "UNREQUESTED_VENUE" not in visible_text_violations(VENUE, teacher_venue_text=venue_memo(trusted))
    assert "UNREQUESTED_VENUE" in visible_text_violations("부산시민공원 소풍", teacher_venue_text=venue_memo(trusted))
    assert "UNREQUESTED_VENUE" in visible_text_violations(VENUE, teacher_venue_text=VENUE + "는 제외해 주세요")
    assert "UNREQUESTED_VENUE" in visible_text_violations(VENUE, teacher_venue_text=VENUE + "에 가지 마세요")
    assert venue_bound_evidence("<현장학습> 숲 체험")


@pytest.mark.parametrize("repeat", [False, True])
def test_monthly_repair_does_not_launder_a_rejected_venue(packet, snapshot, repeat):
    packet = replace(packet, curriculum=v1_curriculum_catalog())
    good, bad = monthly_payload(), monthly_payload()
    bad["weeks"][0]["sections"][0]["value"] = VENUE + " 숲 체험을 해봅니다."
    provider = ScriptedMonthlyLlm(bad, bad if repeat else good)
    if repeat:
        with pytest.raises(ProposalRejectedError):
            MonthlyPlanner(provider).plan(packet, snapshot)
    else:
        outcome = MonthlyPlanner(provider).plan(packet, snapshot)
        assert VENUE not in outcome.proposal.weeks[0].sections[0].value
    assert len(provider.monthly_requests) == 2


def test_monthly_source_is_not_teacher_authorization(packet, snapshot):
    packet = replace(packet, curriculum=v1_curriculum_catalog(), section_evidence=tuple(replace(item, text=VENUE) for item in packet.section_evidence))
    answer = monthly_payload()
    answer["weeks"][0]["sections"][0]["value"] = VENUE + " 주변의 나뭇잎을 살펴봅니다."
    proposal = parse_monthly_proposal(json.dumps(answer))
    result = validate_monthly_proposal(proposal, packet, build_monthly_planning_request(packet, snapshot))
    assert any(issue.detail == "UNREQUESTED_VENUE" for issue in result.issues)
    packet = replace(packet, teacher_memo=VENUE + "에서 자연을 살펴볼 예정입니다.")
    result = validate_monthly_proposal(proposal, packet, build_monthly_planning_request(packet, snapshot))
    assert not any(issue.detail == "UNREQUESTED_VENUE" for issue in result.issues)


def test_weekly_parent_does_not_authorize_a_venue_but_teacher_input_does():
    text = VENUE + " 숲 체험"
    request = build_weekly_request(week_id=WeekId("2026-11-W1"), week={}, ages=(3, 4),
        targets=(WeeklyTarget("theme", parent_value=text),), teacher_input_keys=frozenset(),
        parent_context=(("theme", text),), evidence=(("ev-place", text, "GROUP_ACTIVITY"),),
        reference_candidates=(), packet_fingerprint="packet", curriculum=v1_curriculum_catalog())
    value = ProposedSectionValue("theme", text, False, (), None)
    assert any("UNREQUESTED_VENUE" in issue.detail for issue in validate_weekly((value,), request))
    narrowed = cell_request(request, "theme", current_values=(("theme", text),), teacher_facts=())
    assert any("UNREQUESTED_VENUE" in issue.detail for issue in validate_weekly((value,), narrowed))
    noop = cell_request(request, "theme", current_values=(), teacher_facts=(text,))
    assert any("UNREQUESTED_VENUE" in issue.detail for issue in validate_weekly((value,), noop))
    teacher = cell_request(request, "theme", current_values=(("theme", text),), teacher_facts=(text,),
                           teacher_venues=("배산유아숲터",))
    assert not validate_weekly((value,), teacher)


def test_play_project_rejects_a_venue_without_saving():
    from tests.application.test_play_project_generation import _FakeProvider, _proposal, _run
    answer = _proposal()
    answer["rows"][0]["play_name"] = VENUE + " 숲 체험"
    provider = _FakeProvider(answer)
    use_case, command, plans = _run(provider)
    with pytest.raises(ProposalRejectedError, match="UNREQUESTED_VENUE"):
        use_case.execute(command)
    assert not len(plans) and len(provider.requests) == 1


@pytest.mark.parametrize("repeat", [False, True])
def test_play_monthly_does_not_save_a_repeated_venue(repeat):
    from tests.application.test_play_monthly_generation import _run
    def bad(answer):
        answer["together"][0]["name"] = VENUE + " 숲 체험"
    use_case, command, plans, provider, _ = _run(bad, bad if repeat else None)
    if repeat:
        with pytest.raises(ProposalRejectedError, match="UNREQUESTED_VENUE"):
            use_case.execute(command)
        assert not len(plans)
    else:
        use_case.execute(command)
        assert len(plans) == 1
    assert len(provider.requests) == 2


@pytest.mark.parametrize("denial", ["안 돼요", "생략해 주세요", "피해 주세요", "대신 실내에서", "산책은 하지 마세요", "위험했어요", "빼 주세요"])
def test_rejected_or_negative_places_never_authorize_a_venue(denial):
    assert not authorized_venues("한강공원은 " + denial)
    assert not authorized_venues("한강공원은 " + denial + "\n한강공원")


def test_mixed_positive_and_negative_venues_are_scoped_to_each_name():
    assert authorized_venues("한강공원 가고 부산시민공원은 안 가요") == {"한강공원"}
    assert not authorized_venues("한강공원, 부산시민공원은 생략해 주세요")


@pytest.mark.parametrize("text", ["현장체험학습: 과학관", "동물원 현장학습", "<현장 체험 학습> 과학관", "보건소 견학"])
def test_explicit_field_trip_markers_are_not_limited_to_one_bracket_spelling(text):
    assert venue_bound_evidence(text)


def test_legacy_noncontextual_requests_keep_the_original_validation_contract(packet, snapshot):
    answer = monthly_payload()
    answer["weeks"][0]["sections"][0]["value"] = VENUE + " 숲 체험"
    request = build_monthly_planning_request(packet, snapshot)
    result = validate_monthly_proposal(parse_monthly_proposal(json.dumps(answer)), packet, request)
    assert "teacher-venues" not in request.prompt_version
    assert not any(issue.detail == "UNREQUESTED_VENUE" for issue in result.issues)


def test_removing_only_the_venue_identity_is_not_a_new_grounded_activity():
    assert venue_name_only_removed("한강공원 산책", "공원 산책")
    assert venue_name_only_removed("한강공원 산책", "산책")
    assert not venue_name_only_removed("한강공원 산책", "나뭇잎 색 찾기")


def test_noop_saves_do_not_turn_ai_place_names_into_teacher_input():
    from tests.finalization.harness import PlanningHarness, TEACHER
    harness = PlanningHarness()
    plan = harness.generate_yearly().plan
    item = replace(plan.periods[0].theme, value="한강공원 산책")
    noop = item.edit_by_teacher(plan_id=plan.plan_id, new_value=item.value, actor_id=TEACHER, occurred_at=harness.clock.now())
    assert not parent_teacher_venues((noop,))
    edited = item.edit_by_teacher(plan_id=plan.plan_id, new_value="한강공원 봄 산책", actor_id=TEACHER, occurred_at=harness.clock.now())
    assert parent_teacher_venues((edited,)) == ("한강공원",)
    assert not parent_teacher_venues((edited,), memo="한강공원은 가지 마세요")


def test_monthly_repair_cannot_just_remove_the_facility_identity(packet, snapshot):
    packet = replace(packet, curriculum=v1_curriculum_catalog())
    bad, renamed = monthly_payload(), monthly_payload()
    bad["weeks"][0]["sections"][0]["value"] = "한강공원 산책"
    renamed["weeks"][0]["sections"][0]["value"] = "공원 산책"
    provider = ScriptedMonthlyLlm(bad, renamed)
    with pytest.raises(ProposalRejectedError, match="VENUE_NAME_ONLY_REMOVAL"):
        MonthlyPlanner(provider).plan(packet, snapshot)
    assert len(provider.monthly_requests) == 2


def test_play_monthly_repair_cannot_just_remove_the_facility_identity():
    from tests.application.test_play_monthly_generation import _run
    def name(text):
        return lambda answer: answer["together"][0].update(name=text)
    use_case, command, plans, provider, _ = _run(name("한강공원 산책"), name("공원 산책"))
    with pytest.raises(ProposalRejectedError, match="VENUE_NAME_ONLY_REMOVAL"):
        use_case.execute(command)
    assert not len(plans) and len(provider.requests) == 2


def test_weekly_repair_cannot_just_remove_the_facility_identity():
    from ssuksak.planning.planner.contracts import MONTHLY_MODEL, RawLlmResponse
    from ssuksak.planning.planner.weekly import WeeklyPlanner
    request = build_weekly_request(week_id=WeekId("2026-11-W1"), week={}, ages=(3, 4),
        targets=(WeeklyTarget("theme"),), teacher_input_keys=frozenset(), parent_context=(),
        evidence=(), reference_candidates=(), packet_fingerprint="packet", curriculum=v1_curriculum_catalog())
    class Provider:
        calls = 0

        def generate_weekly(self, request):
            self.calls += 1
            return RawLlmResponse(json.dumps({"week_id": request.week_id.value, "sections": [{"section_key": "theme",
                "value": "한강공원 산책" if self.calls == 1 else "공원 산책", "unresolved": False,
                "grounding_refs": [], "reference_id": None}]}), model=MONTHLY_MODEL)
    provider = Provider()
    with pytest.raises(ProposalRejectedError, match="VENUE_NAME_ONLY_REMOVAL"):
        WeeklyPlanner(provider).plan(request)
    assert provider.calls == 2


@pytest.mark.parametrize("authored", [False, True])
def test_annual_subtheme_teacher_provenance_reaches_monthly_and_regeneration(authored):
    from ssuksak.adapters import monthly_composition
    from ssuksak.planning.application.monthly_dto import RegenerateMonthlyPlanItemCommand
    from tests.adapters.test_v1_wiring import _setup
    from tests.finalization.harness import TEACHER
    harness, provider, generate, command = _setup()
    text = "한강공원 산책"
    parent = harness.yearly_plans.get(command.parent_yearly_plan_id)
    parent = replace(parent, teacher_subthemes=((9, (text,)),) if authored else ())
    harness.yearly_plans.save(parent.plan_id, parent)
    plan = generate.execute(replace(command, parent_subthemes=(text,))).plan
    assert plan.parent_teacher_venues == (("한강공원",) if authored else ())
    assert json.loads(provider.requests[0].user_content).get("teacher_venues", []) == (["한강공원"] if authored else [])
    target = plan.section("focus").cells[0]
    monthly_composition.monthly_regeneration(plan_repository=harness.monthly_plans, provider=provider,
        clock=harness.clock).execute(RegenerateMonthlyPlanItemCommand(plan.plan_id, target.item_id, TEACHER))
    assert json.loads(provider.requests[-1].user_content).get("teacher_venues", []) == (["한강공원"] if authored else [])


@pytest.mark.parametrize("authored", [False, True])
def test_only_teacher_authored_confirmed_monthly_venues_reach_weekly(authored):
    from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
    from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
    from tests.adapters.test_weekly_composition import _day_generation, _day_command
    from tests.finalization.weekly_harness import WeeklyHarness, WEEK
    from ssuksak.planning.application.generate_weekly_plan import WeeklyApplicationError
    harness = WeeklyHarness()
    parent = harness.monthly_parent(confirm=False, mode=MonthlyGenerationMode.LLM_PLANNER)
    original = parent.section("outdoor_play").cell_for_week(WEEK)
    if authored:
        parent = harness.edit_monthly(parent, item_id=original.item_id, value="한강공원 산책")
    if not authored:
        parent = parent.replace_cell(original.item_id, replace(original, value="한강공원 산책"))
        harness.monthly_plans.save(parent.plan_id, parent)
    parent = harness.confirm_monthly(parent)
    provider = RequestAwareWeeklyLlm()
    if authored:
        plan = _day_generation(harness, provider).execute(_day_command(parent)).plan
        assert plan.cell("outdoor_play").value == "한강공원 산책"
    else:
        with pytest.raises(WeeklyApplicationError):
            _day_generation(harness, provider).execute(_day_command(parent))
        assert not len(harness.weekly_plans)


@pytest.mark.parametrize("authored", [False, True])
def test_play_yearly_only_passes_teacher_written_selected_values(authored):
    from ssuksak.planning.domain.identifiers import ActorId
    from tests.application.test_play_monthly_generation import _parent, _run, T0
    parent = _parent()
    period = parent.periods[0]
    row = period.candidates[1]  # selected cand2
    item = row.play_name
    if authored:
        item = item.edit_by_teacher(plan_id=parent.plan_id, new_value="한강공원 산책",
                                    actor_id=ActorId("teacher-test"), occurred_at=T0)
    else:
        item = replace(item, value="한강공원 산책")
    row = replace(row, play_name=item)
    period = replace(period, candidates=tuple(row if value.row_key == row.row_key else value for value in period.candidates))
    parent = replace(parent, periods=(period, *parent.periods[1:]))
    use_case, command, _, provider, _ = _run(parent=parent)
    use_case.execute(command)
    assert json.loads(provider.requests[0].user_content).get("teacher_venues", []) == (["한강공원"] if authored else [])
