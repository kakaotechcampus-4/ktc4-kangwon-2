from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ssuksak.adapters.deterministic_monthly_llm import DeterministicMonthlyLlm
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
)
from ssuksak.planning.domain.monthly_template import DisplayMode
from ssuksak.planning.planner.cell_prompt import CELL_SYSTEM_PROMPT, build_monthly_cell_request
from ssuksak.planning.planner.cell_service import MonthlyCellPlanner
from ssuksak.planning.planner.cell_validation import validate_monthly_cell_proposal
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.planner.contracts import (
    BASIC_HABIT_SECTION_KEY,
    FOCUS_SECTION_KEY,
    GOALS_SECTION_KEY,
    MONTHLY_CELL_PROMPT_VERSION,
    MONTHLY_MODEL,
    MONTHLY_PROMPT_VERSION,
    is_compatible_monthly_model,
    OUTDOOR_SECTION_KEY,
    MonthlyCellSnapshot,
    ProposalParseError,
    ProposalRejectedError,
)
from ssuksak.planning.context.models import GroundingContextItem
from ssuksak.planning.domain.monthly_template import SemanticVariant
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.evidence.classification import SemanticClass
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.models import ReusePolicy, SourceSection
from ssuksak.planning.retrieval.models import AgeMatchKind
from ssuksak.planning.planner.parser import (
    parse_monthly_cell_proposal,
    parse_monthly_proposal,
)
from ssuksak.planning.planner.prompt import (
    SYSTEM_PROMPT as MONTHLY_SYSTEM_PROMPT,
    build_monthly_planning_request,
)
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
                        "grounding_refs": ["ev-3"],
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
                        "grounding_refs": ["ev-3"],
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
    grounding_refs = ["ev-3"]
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
    assert first.valid_grounding_refs == frozenset({"ev-1", "ev-2", "ev-3"})
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


@pytest.mark.parametrize("section_key", ("event_schedule", "drill"))
def test_institution_input_sections_stay_outside_the_llm_boundary(
    packet, snapshot, section_key
):
    template = JsonMonthlyTemplateRepository().get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.2.0"
    )
    assert template is not None
    snapshot = replace(
        snapshot,
        sections=(
            *snapshot.sections,
            replace(
                template.section(section_key),
                activated=True,
                display_label="Institution input",
                display_mode=DisplayMode.WEEKLY_CELLS,
                visible=True,
            ),
        ),
    )

    request = build_monthly_planning_request(packet, snapshot)
    assert section_key not in request.user_content

    payload = monthly_payload()
    payload["weeks"][0]["sections"].append(
        {
            "section_key": section_key,
            "value": "Invented institution schedule",
            "unresolved": False,
            "reference_id": None,
            "grounding_refs": ["ev-1"],
        }
    )
    fake = DeterministicMonthlyLlm(
        json.dumps(payload, ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
    )
    with pytest.raises(ProposalRejectedError) as exc:
        MonthlyPlanner(fake).plan(packet, snapshot)
    assert "INSTITUTION_INPUT_SECTION" in exc.value.validation_codes
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


def _section_item(ref: str, grounding_class: SemanticClass, label: str):
    return GroundingContextItem(
        evidence_ref=ref,
        text=f"{label} 근거 {ref}",
        source_section=SourceSection.WEEK_EXPERIENCE,
        source_label=label,
        age_scope=(3, 4),
        age_match=AgeMatchKind.MIXED_AGE_COVERING,
        institution_alias="S1",
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        grounding_class=grounding_class,
    )


def _with_focus_variant(snapshot, variant):
    return replace(
        snapshot,
        sections=tuple(
            replace(section, semantic_variant=variant) if section.section_key == "focus" else section
            for section in snapshot.sections
        ),
    )


def _validate(payload, packet, snapshot):
    return validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(payload, ensure_ascii=False)),
        packet,
        build_monthly_planning_request(packet, snapshot),
    )


def test_prompt_exposes_grounding_class_for_sections_and_evidence(packet, snapshot):
    body = json.loads(build_monthly_planning_request(packet, snapshot).user_content)
    schema = {item["section_key"]: item.get("grounding_class") for item in body["generation_schema"]["sections"]}

    assert schema["focus"] == "SUBTHEME"
    assert schema["outdoor_play"] is None
    assert {item["grounding_ref"]: item["grounding_class"] for item in body["evidence"]} == {
        "ev-1": None,
        "ev-2": None,
        "ev-3": "SUBTHEME",
    }


@pytest.mark.parametrize(
    ("week", "section", "ref"),
    [(0, 0, "ev-1"), (1, 1, "ev-3")],
    ids=["focus-cites-unclassified", "outdoor-cites-subtheme"],
)
def test_wrong_source_grounding_rejects_the_whole_proposal(packet, snapshot, week, section, ref):
    payload = monthly_payload()
    payload["weeks"][week]["sections"][section].update(reference_id=None, grounding_refs=[ref])

    assert "WRONG_SOURCE_GROUNDING" in _validate(payload, packet, snapshot).codes


def test_focus_cannot_cite_another_semantic_class(packet, snapshot):
    goals_packet = replace(
        packet, section_evidence=packet.section_evidence + (_section_item("ev-4", SemanticClass.GOALS, "교사의 기대"),)
    )
    payload = monthly_payload()
    payload["weeks"][0]["sections"][0]["grounding_refs"] = ["ev-4"]

    assert "WRONG_SOURCE_GROUNDING" in _validate(payload, goals_packet, snapshot).codes


def test_expected_play_focus_uses_only_expected_play_evidence(packet, snapshot):
    expected_play = _with_focus_variant(snapshot, SemanticVariant.EXPECTED_PLAY)
    play_packet = replace(
        packet,
        section_evidence=packet.section_evidence + (_section_item("ev-5", SemanticClass.EXPECTED_PLAY, "예상놀이"),),
    )

    assert "WRONG_SOURCE_GROUNDING" in _validate(monthly_payload(), play_packet, expected_play).codes
    payload = monthly_payload()
    for week in payload["weeks"]:
        week["sections"][0]["grounding_refs"] = ["ev-5"]
    assert _validate(payload, play_packet, expected_play).is_valid


def test_weekly_theme_focus_cannot_cite_any_evidence(packet, snapshot):
    weekly_theme = _with_focus_variant(snapshot, SemanticVariant.WEEKLY_THEME)
    payload = monthly_payload()
    payload["weeks"][1]["sections"][0]["grounding_refs"] = ["ev-1"]

    assert "WRONG_SOURCE_GROUNDING" in _validate(payload, packet, weekly_theme).codes


def test_cell_validator_rejects_wrong_source_grounding(packet, snapshot):
    request = build_monthly_cell_request(
        packet,
        snapshot,
        target_week_id=WeekId("2026-09-W1"),
        target_section_key=FOCUS_SECTION_KEY,
        month_snapshot=snapshots(),
    )
    payload = cell_payload()
    payload["section"]["grounding_refs"] = ["ev-1"]
    proposal = parse_monthly_cell_proposal(json.dumps(payload, ensure_ascii=False))

    assert "WRONG_SOURCE_GROUNDING" in validate_monthly_cell_proposal(proposal, packet, request).codes


# ---------------------------------------------------------------- V1-7 PR-C3b month-level (goals) cell target

WEEK_1 = WeekId("2026-09-W1")


def _with_goals_and_basic_habit(snapshot):
    template = JsonMonthlyTemplateRepository().get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.2.0"
    )
    assert template is not None
    return replace(
        snapshot,
        sections=(
            *snapshot.sections,
            replace(template.section("goals"), activated=True, display_label="Goals", visible=True),
            replace(
                template.section("habits"),
                section_key="basic_habit",
                activated=True,
                display_label="Basic habit",
                visible=True,
            ),
        ),
    )


def _with_goals_evidence(packet):
    return replace(
        packet, section_evidence=packet.section_evidence + (_section_item("ev-4", SemanticClass.GOALS, "교사의 기대"),)
    )


def goals_cell_payload(target_week_id: str | None = None) -> dict[str, object]:
    return {
        "target_month": "2026-09",
        "target_week_id": target_week_id,
        "section": {
            "section_key": GOALS_SECTION_KEY,
            "value": "가을의 변화를 즐겁게 탐색한다.",
            "unresolved": False,
            "reference_id": None,
            "grounding_refs": ["ev-4"],
        },
    }


@pytest.mark.parametrize(
    ("section_key", "target_week_id", "valid"),
    [
        (FOCUS_SECTION_KEY, WEEK_1, True),
        (OUTDOOR_SECTION_KEY, WEEK_1, True),
        (BASIC_HABIT_SECTION_KEY, WEEK_1, True),
        (GOALS_SECTION_KEY, None, True),
        (FOCUS_SECTION_KEY, None, False),
        (OUTDOOR_SECTION_KEY, None, False),
        (BASIC_HABIT_SECTION_KEY, None, False),
        (GOALS_SECTION_KEY, WEEK_1, False),
    ],
    ids=[
        "focus-week", "outdoor-week", "basic-habit-week", "goals-null",
        "focus-null", "outdoor-null", "basic-habit-null", "goals-week",
    ],
)
def test_cell_request_target_week_follows_the_snapshot_placement(
    packet, snapshot, section_key, target_week_id, valid
):
    def build():
        return build_monthly_cell_request(
            packet,
            _with_goals_and_basic_habit(snapshot),
            target_week_id=target_week_id,
            target_section_key=section_key,
            month_snapshot=snapshots(),
        )

    if valid:
        assert build().target_week_id == target_week_id
    else:
        with pytest.raises(InvalidDomainValueError, match="MonthlyCellPlanningRequest.target_week_id"):
            build()


def test_goals_cell_prompt_states_the_month_level_target_contract(packet, snapshot):
    request = build_monthly_cell_request(
        _with_goals_evidence(packet),
        _with_goals_and_basic_habit(snapshot),
        target_week_id=None,
        target_section_key=GOALS_SECTION_KEY,
        month_snapshot=snapshots(),
    )
    body = json.loads(request.user_content)
    schema = {item["section_key"]: item for item in body["generation_schema"]["sections"]}

    assert request.prompt_version == MONTHLY_CELL_PROMPT_VERSION == "monthly-cell-planner-v6"
    assert body["target_cell"] == {
        "week_id": None,
        "section_key": "goals",
        "placement": "MONTH",
        "grounding_class": "GOALS",
    }
    assert (schema["goals"]["placement"], schema["goals"]["grounding_class"]) == ("MONTH", "GOALS")
    assert body["response_contract"]["target_week_id"] is None


def test_weekly_cell_prompt_keeps_the_weekly_target_shape(packet, snapshot):
    request = build_monthly_cell_request(
        packet, snapshot, target_week_id=WEEK_1, target_section_key=FOCUS_SECTION_KEY, month_snapshot=snapshots()
    )
    body = json.loads(request.user_content)

    assert body["target_cell"] == {"week_id": "2026-09-W1", "section_key": "focus"}
    assert body["response_contract"]["target_week_id"] == "YYYY-MM-Wn"


@pytest.mark.parametrize(
    ("section_key", "target_week_id", "response_week_id", "valid"),
    [
        (FOCUS_SECTION_KEY, WEEK_1, "2026-09-W1", True),
        (FOCUS_SECTION_KEY, WEEK_1, None, False),
        (GOALS_SECTION_KEY, None, None, True),
        (GOALS_SECTION_KEY, None, "2026-09-W1", False),
    ],
    ids=["weekly-week", "weekly-null", "goals-null", "goals-week"],
)
def test_cell_response_target_week_must_match_the_request_placement(
    packet, snapshot, section_key, target_week_id, response_week_id, valid
):
    payload = goals_cell_payload() if section_key == GOALS_SECTION_KEY else cell_payload()
    payload["target_week_id"] = response_week_id
    planner = MonthlyCellPlanner(
        DeterministicMonthlyLlm(
            json.dumps(monthly_payload(), ensure_ascii=False),
            json.dumps(payload, ensure_ascii=False),
        )
    )

    def plan():
        return planner.plan(
            _with_goals_evidence(packet),
            _with_goals_and_basic_habit(snapshot),
            target_week_id=target_week_id,
            target_section_key=section_key,
            month_snapshot=snapshots(),
        )

    if valid:
        assert plan().proposal.target_week_id == target_week_id
    else:
        with pytest.raises(ProposalRejectedError) as exc:
            plan()
        assert exc.value.validation_codes == ("TARGET_WEEK_MISMATCH",)


def test_cell_parser_requires_the_target_week_key_and_accepts_only_null_or_a_week_id():
    payload = goals_cell_payload()
    assert parse_monthly_cell_proposal(json.dumps(payload, ensure_ascii=False)).target_week_id is None
    payload["target_week_id"] = "2026-09-W1"
    assert parse_monthly_cell_proposal(json.dumps(payload, ensure_ascii=False)).target_week_id == WEEK_1

    for invalid in ("", " ", 1, "not-a-week"):
        payload["target_week_id"] = invalid
        with pytest.raises(ProposalParseError):
            parse_monthly_cell_proposal(json.dumps(payload, ensure_ascii=False))
    del payload["target_week_id"]
    with pytest.raises(ProposalParseError, match="fields mismatch"):
        parse_monthly_cell_proposal(json.dumps(payload, ensure_ascii=False))


# ---------------------------------------------------------------- Korean output contract


@pytest.mark.parametrize(
    ("system_prompt", "version", "expected"),
    [
        (MONTHLY_SYSTEM_PROMPT, MONTHLY_PROMPT_VERSION, "monthly-planner-v5"),
        (CELL_SYSTEM_PROMPT, MONTHLY_CELL_PROMPT_VERSION, "monthly-cell-planner-v6"),
    ],
    ids=["monthly", "cell"],
)
def test_prompts_require_korean_values_but_keep_machine_values(system_prompt, version, expected):
    assert version == expected
    assert "Write user-facing plan text in value fields in natural Korean." in system_prompt
    assert "never translate them" in system_prompt
    for machine_value in ("JSON keys", "section_key", "week ids", "enum values", "reference_id", "grounding_refs"):
        assert machine_value in system_prompt
    assert "Include every key required by response_contract in every object and cell;" in system_prompt
    assert "include the key with null, never omit it." in system_prompt


@pytest.mark.parametrize(
    ("parse", "payload", "section"),
    [
        (parse_monthly_proposal, monthly_payload, lambda body: body["weeks"][0]["sections"][0]),
        (parse_monthly_cell_proposal, cell_payload, lambda body: body["section"]),
    ],
    ids=["monthly", "cell"],
)
def test_parser_still_rejects_an_omitted_nullable_key(parse, payload, section):
    body = payload()
    del section(body)["reference_id"]

    with pytest.raises(ProposalParseError, match=r"missing=\['reference_id'\]"):
        parse(json.dumps(body, ensure_ascii=False))


def test_built_requests_carry_the_korean_contract(packet, snapshot):
    monthly = build_monthly_planning_request(packet, snapshot)
    cell = build_monthly_cell_request(
        packet, snapshot, target_week_id=WEEK_1, target_section_key=FOCUS_SECTION_KEY, month_snapshot=snapshots()
    )

    assert (monthly.prompt_version, monthly.system_prompt) == (MONTHLY_PROMPT_VERSION, MONTHLY_SYSTEM_PROMPT)
    assert (cell.prompt_version, cell.system_prompt) == (MONTHLY_CELL_PROMPT_VERSION, CELL_SYSTEM_PROMPT)


# ---------------------------------------------------------------- model identity compatibility


@pytest.mark.parametrize(
    "observed", ["openai/gpt-4.1-mini", "gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"]
)
def test_requested_family_and_its_dated_snapshot_are_compatible(observed):
    assert is_compatible_monthly_model(observed)


@pytest.mark.parametrize(
    "observed",
    [
        "gpt-4.1",
        "gpt-4.1-nano",
        "gpt-4.1-mini-preview",
        "gpt-4.1-mini-custom",
        "abc-gpt-4.1-mini",
        "gpt-4.1-mini-2025-04-14-extra",
        "gpt-4.1-mini-2025-13-40",
        "openai/gpt-4.1-nano",
        "",
        None,
    ],
)
def test_other_models_are_not_compatible(observed):
    assert not is_compatible_monthly_model(observed)


def test_planners_accept_a_dated_snapshot_and_keep_the_observed_model(packet, snapshot):
    snapshot_model = "gpt-4.1-mini-2025-04-14"
    fake = DeterministicMonthlyLlm(
        json.dumps(monthly_payload(), ensure_ascii=False),
        json.dumps(cell_payload(), ensure_ascii=False),
        model=snapshot_model,
    )
    monthly = MonthlyPlanner(fake).plan(packet, snapshot)
    cell = MonthlyCellPlanner(fake).plan(
        packet, snapshot, target_week_id=WEEK_1, target_section_key=FOCUS_SECTION_KEY, month_snapshot=snapshots()
    )

    assert monthly.model == cell.model == snapshot_model
    assert fake.monthly_requests and fake.cell_requests
