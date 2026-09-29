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
)
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.models import SourceSection
from ssuksak.planning.planner.parser import (
    parse_monthly_cell_proposal,
    parse_monthly_proposal,
)
from ssuksak.planning.planner.prompt import build_monthly_planning_request
from ssuksak.planning.planner.service import MonthlyPlanner
from ssuksak.planning.planner.validation import (
    validate_monthly_proposal,
    validate_monthly_proposal_schema,
)


def monthly_payload() -> dict[str, object]:
    return {
        "target_month": "2026-09",
        "month_sections": [
            {
                "section_key": "theme",
                "value": "가을과 자연",
                "unresolved": False,
                "reference_id": "theme-autumn",
                "grounding_refs": [],
            }
        ],
        "weeks": [
            {
                "week_id": "2026-09-W1",
                "sections": [
                    {
                        "section_key": "focus",
                        "value": "바람과 빛의 변화를 몸으로 살펴본다.",
                        "unresolved": False,
                        "reference_id": None,
                        "grounding_refs": ["ev-1"],
                    },
                    {
                        "section_key": "outdoor_play",
                        "value": "바람개비 놀이",
                        "unresolved": False,
                        "reference_id": "act-1",
                        "grounding_refs": [],
                    },
                    {
                        "section_key": "safety_education",
                        "value": "",
                        "unresolved": True,
                        "reference_id": None,
                        "grounding_refs": [],
                    },
                ],
            },
            {
                "week_id": "2026-09-W2",
                "sections": [
                    {
                        "section_key": "focus",
                        "value": "주변의 색과 모양을 새롭게 발견한다.",
                        "unresolved": False,
                        "reference_id": None,
                        "grounding_refs": ["ev-1"],
                    },
                    {
                        "section_key": "outdoor_play",
                        "value": "색 그림자 찾기",
                        "unresolved": False,
                        "reference_id": None,
                        "grounding_refs": ["ev-1"],
                    },
                    {
                        "section_key": "safety_education",
                        "value": "",
                        "unresolved": True,
                        "reference_id": None,
                        "grounding_refs": [],
                    },
                ],
            },
        ],
    }


def cell_payload(section: str = FOCUS_SECTION_KEY) -> dict[str, object]:
    value = "바람과 빛의 변화를 탐색한다."
    reference_id = None
    grounding_refs = ["ev-1"]
    if section == OUTDOOR_SECTION_KEY:
        value = "바람개비 놀이"
        reference_id = "act-1"
        grounding_refs = []
    return {
        "target_month": "2026-09",
        "target_week_id": "2026-09-W1",
        "section": {
            "section_key": section,
            "value": value,
            "unresolved": False,
            "reference_id": reference_id,
            "grounding_refs": grounding_refs,
        },
    }


def snapshots() -> tuple[MonthlyCellSnapshot, ...]:
    return (
        MonthlyCellSnapshot(
            WeekId("2026-09-W1"),
            (("focus", "기존 초점 1"), ("outdoor_play", "기존 놀이 1")),
        ),
        MonthlyCellSnapshot(
            WeekId("2026-09-W2"),
            (("focus", "기존 초점 2"), ("outdoor_play", "기존 놀이 2")),
        ),
    )


def test_prompt_uses_snapshot_and_context_without_recomputing_rules(packet, snapshot):
    first = build_monthly_planning_request(packet, snapshot)
    second = build_monthly_planning_request(packet, snapshot)

    assert first == second
    assert first.target_month == YearMonth(2026, 9)
    assert first.expected_week_ids == (
        WeekId("2026-09-W1"),
        WeekId("2026-09-W2"),
    )
    assert first.valid_grounding_refs == frozenset({"ev-1", "ev-2"})
    assert "Do not make legal decisions" in first.system_prompt
    assert "STATUTORY_SAFETY_EDUCATION" in first.user_content
    assert '"semantic_variant": "SUBTHEME"' in first.user_content
    response_contract = json.loads(first.user_content)["response_contract"]
    assert "display_label" not in json.dumps(response_contract)


def test_parser_accepts_exact_contract_and_rejects_extra_fields():
    payload = monthly_payload()
    proposal = parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))
    assert proposal.weeks[1].section("outdoor_play").grounding_refs == ("ev-1",)

    payload["display_label"] = "금지"
    with pytest.raises(ProposalParseError, match="extra"):
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))


def test_parser_rejects_legacy_experience_activity_contract():
    payload = {
        "target_month": "2026-09",
        "theme_id": "theme-autumn",
        "month_flow_rationale": "legacy",
        "weeks": [],
    }
    with pytest.raises(ProposalParseError, match="fields mismatch"):
        parse_monthly_proposal(json.dumps(payload))


@pytest.mark.parametrize("week_count", [4, 5])
def test_parser_and_schema_support_dynamic_four_and_five_week_proposals(
    packet, snapshot, week_count
):
    payload = monthly_payload()
    source_week = payload["weeks"][0]
    payload["weeks"] = [
        {**source_week, "week_id": f"2026-09-W{index}"}
        for index in range(1, week_count + 1)
    ]
    proposal = parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))
    assert len(proposal.weeks) == week_count
    request = replace(
        build_monthly_planning_request(packet, snapshot),
        expected_week_ids=tuple(
            WeekId(f"2026-09-W{index}")
            for index in range(1, week_count + 1)
        ),
    )
    assert validate_monthly_proposal_schema(proposal, request).is_valid


def test_parser_rejects_template_metadata_and_legacy_alias():
    payload = monthly_payload()
    payload["weeks"][0]["sections"][0]["semantic_variant"] = "SUBTHEME"
    with pytest.raises(ProposalParseError, match="extra"):
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))

    payload = monthly_payload()
    payload["weeks"][0]["sections"][0]["section_key"] = "habits"
    with pytest.raises(ProposalParseError, match="canonical"):
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))


def test_valid_monthly_proposal_passes_structural_validation(packet, snapshot):
    request = build_monthly_planning_request(packet, snapshot)
    proposal = parse_monthly_proposal(json.dumps(monthly_payload(), ensure_ascii=False))
    assert validate_monthly_proposal(proposal, packet, request).is_valid


def test_optional_focus_can_be_omitted_but_required_weekly_sections_cannot(
    packet, snapshot
):
    payload = monthly_payload()
    for week in payload["weeks"]:
        week["sections"] = [
            section
            for section in week["sections"]
            if section["section_key"] != "focus"
        ]
    proposal = parse_monthly_proposal(json.dumps(payload, ensure_ascii=False))
    request = build_monthly_planning_request(packet, snapshot)
    assert validate_monthly_proposal_schema(proposal, request).is_valid

    payload["weeks"][0]["sections"] = [
        section
        for section in payload["weeks"][0]["sections"]
        if section["section_key"] != "outdoor_play"
    ]
    result = validate_monthly_proposal_schema(
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False)), request
    )
    assert "REQUIRED_SECTION_MISSING" in result.codes


def test_snapshot_grounding_rejects_axis_unknown_and_wrong_placement(packet, snapshot):
    request = build_monthly_planning_request(packet, snapshot)
    for section_key, code in (
        ("week_axis", "AXIS_CONTENT"),
        ("unknown", "UNKNOWN_SECTION"),
        ("outdoor_play", "SECTION_PLACEMENT_MISMATCH"),
    ):
        payload = monthly_payload()
        payload["month_sections"].append(
            {
                "section_key": section_key,
                "value": "invalid placement",
                "unresolved": False,
                "reference_id": None,
                "grounding_refs": ["ev-1"],
            }
        )
        result = validate_monthly_proposal_schema(
            parse_monthly_proposal(json.dumps(payload, ensure_ascii=False)), request
        )
        assert code in result.codes


def test_safety_requires_approved_safety_grounding_or_explicit_unresolved(
    packet, snapshot
):
    payload = monthly_payload()
    safety = payload["weeks"][0]["sections"][2]
    safety.update(
        value="Invented safety content",
        unresolved=False,
        grounding_refs=["ev-1"],
    )
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet, snapshot),
    )
    assert "SAFETY_GROUNDING_REQUIRED" in result.codes

    safety_evidence = replace(
        packet.institution_evidence[0],
        evidence_ref="safety-1",
        text="교통 안전 규칙 자료",
        source_section=SourceSection.SAFETY_EDUCATION,
    )
    grounded_packet = replace(
        packet,
        institution_evidence=(packet.institution_evidence[0], safety_evidence),
    )
    payload = monthly_payload()
    payload["weeks"][0]["sections"][2].update(
        value="교통안전 규칙을 놀이로 익힌다.",
        unresolved=False,
        grounding_refs=["safety-1"],
    )
    grounded_request = build_monthly_planning_request(grounded_packet, snapshot)
    assert validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False)),
        grounded_packet,
        grounded_request,
    ).is_valid


def test_non_safety_required_section_cannot_use_unresolved(packet, snapshot):
    payload = monthly_payload()
    outdoor = payload["weeks"][0]["sections"][1]
    outdoor.update(
        value="",
        unresolved=True,
        reference_id=None,
        grounding_refs=[],
    )
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet, snapshot),
    )
    assert "UNRESOLVED_NOT_ALLOWED" in result.codes


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda body: body.update(target_month="2026-10"), "TARGET_MONTH_MISMATCH"),
        (
            lambda body: body["month_sections"][0].update(
                reference_id="invented"
            ),
            "THEME_REFERENCE_MISMATCH",
        ),
        (
            lambda body: body["weeks"].reverse(),
            "WEEK_STRUCTURE_MISMATCH",
        ),
    ],
)
def test_validator_locks_period_theme_and_week_structure(
    packet, snapshot, mutate, code
):
    body = monthly_payload()
    mutate(body)
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(body, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet, snapshot),
    )
    assert code in result.codes


def test_validator_rejects_unknown_grounding_and_source_copy(packet, snapshot):
    body = monthly_payload()
    activity = body["weeks"][1]["sections"][1]
    activity["grounding_refs"] = ["invented-ref"]
    activity["value"] = "나뭇잎 색을 관찰한다."
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(body, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet, snapshot),
    )
    assert "UNKNOWN_GROUNDING_REF" in result.codes
    assert "SOURCE_TEXT_COPY" in result.codes


def test_validator_rejects_legal_or_safety_claims(packet, snapshot):
    body = monthly_payload()
    body["weeks"][0]["sections"][0]["value"] = (
        "법적 기준에 맞는 안전교육을 의무적으로 한다."
    )
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(body, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet, snapshot),
    )
    details = tuple(item.detail for item in result.issues)
    assert "OFFICIAL_OR_LEGAL_CLAIM" in details
    assert "SAFETY_CONTENT_LEAKAGE" in details


def test_monthly_planner_calls_provider_once_and_returns_validated_outcome(
    packet, snapshot
):
    fake = DeterministicMonthlyLlm(
        json.dumps(monthly_payload(), ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
    )
    outcome = MonthlyPlanner(fake).plan(packet, snapshot)
    assert outcome.model == MONTHLY_MODEL
    assert outcome.proposal.value_for("theme", None).reference_id == "theme-autumn"
    assert len(fake.monthly_requests) == 1


def test_monthly_planner_rejects_invalid_provider_model(packet, snapshot):
    fake = DeterministicMonthlyLlm(
        json.dumps(monthly_payload(), ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
        model="other-model",
    )
    with pytest.raises(ProposalRejectedError, match="UNEXPECTED_MODEL"):
        MonthlyPlanner(fake).plan(packet, snapshot)


def test_cell_prompt_covers_snapshot_and_only_target_cell(packet, snapshot):
    request = build_monthly_cell_request(
        packet,
        snapshot,
        target_week_id=WeekId("2026-09-W1"),
        target_section_key=FOCUS_SECTION_KEY,
        month_snapshot=snapshots(),
    )
    assert request.target_week_id == WeekId("2026-09-W1")
    assert request.plan_snapshot_fingerprint
    assert "existing" not in request.system_prompt.lower()
    assert "기존 초점 2" in request.user_content


def test_cell_builder_rejects_non_context_week(packet, snapshot):
    with pytest.raises(ValueError, match="target_week_id"):
        build_monthly_cell_request(
            packet,
            snapshot,
            target_week_id=WeekId("2026-09-W9"),
            target_section_key=FOCUS_SECTION_KEY,
            month_snapshot=snapshots(),
        )


@pytest.mark.parametrize("section", [FOCUS_SECTION_KEY, OUTDOOR_SECTION_KEY])
def test_cell_validator_accepts_focus_and_reference_outdoor(
    packet, snapshot, section
):
    request = build_monthly_cell_request(
        packet,
        snapshot,
        target_week_id=WeekId("2026-09-W1"),
        target_section_key=section,
        month_snapshot=snapshots(),
    )
    proposal = parse_monthly_cell_proposal(
        json.dumps(cell_payload(section), ensure_ascii=False)
    )
    assert validate_monthly_cell_proposal(proposal, packet, request).is_valid


def test_cell_validator_rejects_target_change(packet, snapshot):
    request = build_monthly_cell_request(
        packet,
        snapshot,
        target_week_id=WeekId("2026-09-W1"),
        target_section_key=FOCUS_SECTION_KEY,
        month_snapshot=snapshots(),
    )
    proposal = parse_monthly_cell_proposal(
        json.dumps(cell_payload(), ensure_ascii=False)
    )
    proposal = replace(
        proposal,
        target_week_id=WeekId("2026-09-W2"),
    )
    result = validate_monthly_cell_proposal(proposal, packet, request)
    assert "TARGET_WEEK_MISMATCH" in result.codes


def test_cell_planner_does_not_mutate_snapshot_or_persist(packet, snapshot):
    month_snapshot = snapshots()
    fake = DeterministicMonthlyLlm(
        json.dumps(monthly_payload(), ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
    )
    outcome = MonthlyCellPlanner(fake).plan(
        packet,
        snapshot,
        target_week_id=WeekId("2026-09-W1"),
        target_section_key=FOCUS_SECTION_KEY,
        month_snapshot=month_snapshot,
    )
    assert month_snapshot == snapshots()
    assert outcome.proposal.section.value == "바람과 빛의 변화를 탐색한다."
    assert len(fake.cell_requests) == 1
