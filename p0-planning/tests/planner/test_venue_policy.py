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
from tests.planner.test_monthly_planner import ScriptedMonthlyLlm, monthly_payload

VENUE = "배산유아숲터"


@pytest.mark.parametrize("text,blocked", [
    ("배산유아숲터 숲 체험", True), ("배산 유아숲터에서 자연 살펴보기", True),
    ("부산시민공원으로 가을 소풍", True), ("국립중앙박물관 관람", True),
    ("주변 도서관 놀이", False), ("친구와 공원에서 산책하기", False),
    ("어린이도서관 놀이", False), ("블록으로 동물원 만들기", False),
    ("우리반박물관 놀이", False),
    ("자연물로 겨울나무 꾸미기", False),
])
def test_specific_venues_are_distinct_from_generic_play_spaces(text, blocked):
    assert bool(named_venues(text)) is blocked
    assert ("UNREQUESTED_VENUE" in visible_text_violations(text)) is blocked


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
    packet = replace(packet, section_evidence=tuple(replace(item, text=VENUE) for item in packet.section_evidence))
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
        reference_candidates=(), packet_fingerprint="packet")
    value = ProposedSectionValue("theme", text, False, (), None)
    assert any("UNREQUESTED_VENUE" in issue.detail for issue in validate_weekly((value,), request))
    narrowed = cell_request(request, "theme", current_values=(("theme", text),), teacher_facts=())
    assert any("UNREQUESTED_VENUE" in issue.detail for issue in validate_weekly((value,), narrowed))
    teacher = cell_request(request, "theme", current_values=(("theme", text),), teacher_facts=(text,))
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
