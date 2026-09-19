from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ssuksak.adapters.deterministic_monthly_llm import DeterministicMonthlyLlm
from ssuksak.planning.planner.cell_prompt import build_monthly_cell_request
from ssuksak.planning.planner.cell_service import MonthlyCellPlanner
from ssuksak.planning.planner.cell_validation import validate_monthly_cell_proposal
from ssuksak.planning.planner.contracts import (
    FOCUS_SECTION_KEY,
    MONTHLY_MODEL,
    OUTDOOR_SECTION_KEY,
    MonthlyCellSnapshot,
    ProposalParseError,
    ProposalRejectedError,
    ProposedActivityOrigin,
)
from ssuksak.planning.planner.parser import (
    parse_monthly_cell_proposal,
    parse_monthly_proposal,
)
from ssuksak.planning.planner.prompt import build_monthly_planning_request
from ssuksak.planning.planner.service import MonthlyPlanner
from ssuksak.planning.planner.validation import validate_monthly_proposal


def monthly_payload() -> dict[str, object]:
    return {
        "target_month": "2026-09",
        "theme_id": "theme-autumn",
        "month_flow_rationale": "가을 자연을 다양한 감각으로 탐색한다.",
        "weeks": [
            {
                "week_id": "2026-09-W1",
                "experience": "바람과 빛의 변화를 몸으로 살펴본다.",
                "activity": {
                    "value": "바람개비 놀이",
                    "origin": "REFERENCE",
                    "reference_activity_id": "act-1",
                    "grounding_refs": [],
                },
            },
            {
                "week_id": "2026-09-W2",
                "experience": "주변의 색과 모양을 새롭게 발견한다.",
                "activity": {
                    "value": "색 그림자 찾기",
                    "origin": "LLM_SYNTHESIZED",
                    "reference_activity_id": None,
                    "grounding_refs": ["ev-1"],
                },
            },
        ],
    }


def cell_payload(section: str = FOCUS_SECTION_KEY) -> dict[str, object]:
    if section == FOCUS_SECTION_KEY:
        return {
            "target_month": "2026-09",
            "target_week_id": "2026-09-W1",
            "target_section_key": section,
            "value": "바람과 빛의 변화를 탐색한다.",
            "activity_origin": None,
            "reference_activity_id": None,
            "grounding_refs": ["ev-1"],
        }
    return {
        "target_month": "2026-09",
        "target_week_id": "2026-09-W1",
        "target_section_key": section,
        "value": "바람개비 놀이",
        "activity_origin": "REFERENCE",
        "reference_activity_id": "act-1",
        "grounding_refs": [],
    }


def snapshots() -> tuple[MonthlyCellSnapshot, ...]:
    return (
        MonthlyCellSnapshot("2026-09-W1", "기존 초점 1", "기존 놀이 1"),
        MonthlyCellSnapshot("2026-09-W2", "기존 초점 2", "기존 놀이 2"),
    )


def test_prompt_uses_context_without_recomputing_rules(packet):
    first = build_monthly_planning_request(packet)
    second = build_monthly_planning_request(packet)

    assert first == second
    assert first.target_month == "2026-09"
    assert first.expected_week_ids == ("2026-09-W1", "2026-09-W2")
    assert first.valid_grounding_refs == frozenset({"ev-1", "ev-2"})
    assert "Do not make legal decisions" in first.system_prompt
    assert "STATUTORY_SAFETY_EDUCATION" in first.user_content


def test_parser_accepts_exact_contract_and_rejects_extra_fields():
    payload = monthly_payload()
    proposal = parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))
    assert proposal.weeks[1].activity.grounding_refs == ("ev-1",)

    payload["safety_education"] = "금지"
    with pytest.raises(ProposalParseError, match="extra"):
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))


def test_valid_monthly_proposal_passes_deterministic_validation(packet):
    request = build_monthly_planning_request(packet)
    proposal = parse_monthly_proposal(json.dumps(monthly_payload(), ensure_ascii=False))
    assert validate_monthly_proposal(proposal, packet, request).is_valid


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda body: body.update(target_month="2026-10"), "TARGET_MONTH_MISMATCH"),
        (lambda body: body.update(theme_id="invented"), "THEME_ID_MISMATCH"),
        (
            lambda body: body["weeks"].reverse(),
            "WEEK_STRUCTURE_MISMATCH",
        ),
    ],
)
def test_validator_locks_period_theme_and_week_structure(packet, mutate, code):
    body = monthly_payload()
    mutate(body)
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(body, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet),
    )
    assert code in result.codes


def test_validator_rejects_unknown_grounding_and_source_copy(packet):
    body = monthly_payload()
    activity = body["weeks"][1]["activity"]
    activity["grounding_refs"] = ["invented-ref"]
    activity["value"] = "나뭇잎 색을 관찰한다."
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(body, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet),
    )
    assert "UNKNOWN_GROUNDING_REF" in result.codes
    assert "SOURCE_TEXT_COPY" in result.codes


def test_validator_rejects_legal_or_safety_claims(packet):
    body = monthly_payload()
    body["month_flow_rationale"] = "법적 기준에 맞는 안전교육을 의무적으로 한다."
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(body, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet),
    )
    details = tuple(item.detail for item in result.violations)
    assert "OFFICIAL_OR_LEGAL_CLAIM" in details
    assert "SAFETY_CONTENT_LEAKAGE" in details


def test_monthly_planner_calls_provider_once_and_returns_validated_outcome(packet):
    fake = DeterministicMonthlyLlm(
        json.dumps(monthly_payload(), ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
    )
    outcome = MonthlyPlanner(fake).plan(packet)
    assert outcome.model == MONTHLY_MODEL
    assert outcome.proposal.theme_id == "theme-autumn"
    assert len(fake.monthly_requests) == 1


def test_monthly_planner_rejects_invalid_provider_model(packet):
    fake = DeterministicMonthlyLlm(
        json.dumps(monthly_payload(), ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
        model="other-model",
    )
    with pytest.raises(ProposalRejectedError, match="UNEXPECTED_MODEL"):
        MonthlyPlanner(fake).plan(packet)


def test_cell_prompt_covers_snapshot_and_only_target_cell(packet):
    request = build_monthly_cell_request(
        packet,
        target_week_id="2026-09-W1",
        target_section_key=FOCUS_SECTION_KEY,
        month_snapshot=snapshots(),
    )
    assert request.target_week_id == "2026-09-W1"
    assert request.plan_snapshot_fingerprint
    assert "existing" not in request.system_prompt.lower()
    assert "기존 초점 2" in request.user_content


def test_cell_builder_rejects_non_context_week(packet):
    with pytest.raises(ValueError, match="target_week_id"):
        build_monthly_cell_request(
            packet,
            target_week_id="2026-09-W9",
            target_section_key=FOCUS_SECTION_KEY,
            month_snapshot=snapshots(),
        )


@pytest.mark.parametrize("section", [FOCUS_SECTION_KEY, OUTDOOR_SECTION_KEY])
def test_cell_validator_accepts_focus_and_reference_outdoor(packet, section):
    request = build_monthly_cell_request(
        packet,
        target_week_id="2026-09-W1",
        target_section_key=section,
        month_snapshot=snapshots(),
    )
    proposal = parse_monthly_cell_proposal(
        json.dumps(cell_payload(section), ensure_ascii=False)
    )
    assert validate_monthly_cell_proposal(proposal, packet, request).is_valid


def test_cell_validator_rejects_target_change_and_activity_metadata_on_focus(packet):
    request = build_monthly_cell_request(
        packet,
        target_week_id="2026-09-W1",
        target_section_key=FOCUS_SECTION_KEY,
        month_snapshot=snapshots(),
    )
    proposal = parse_monthly_cell_proposal(
        json.dumps(cell_payload(), ensure_ascii=False)
    )
    proposal = replace(
        proposal,
        target_week_id="2026-09-W2",
        activity_origin=ProposedActivityOrigin.REFERENCE,
        reference_activity_id="act-1",
    )
    result = validate_monthly_cell_proposal(proposal, packet, request)
    assert "TARGET_WEEK_MISMATCH" in result.codes
    assert "FOCUS_ACTIVITY_METADATA" in result.codes


def test_cell_planner_does_not_mutate_snapshot_or_persist(packet):
    snapshot = snapshots()
    fake = DeterministicMonthlyLlm(
        json.dumps(monthly_payload(), ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
    )
    outcome = MonthlyCellPlanner(fake).plan(
        packet,
        target_week_id="2026-09-W1",
        target_section_key=FOCUS_SECTION_KEY,
        month_snapshot=snapshot,
    )
    assert snapshot == snapshots()
    assert outcome.proposal.value == "바람과 빛의 변화를 탐색한다."
    assert len(fake.cell_requests) == 1
