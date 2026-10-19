"""Cell regeneration reference contract.

Two layers are checked separately for every case:
- decode: does the strict response schema sent to the provider admit the answer?
- Core:   does validate_monthly_cell_proposal accept it, and with which code if not?

The strict schema is a guard, not a replacement: the validator stays the final
check, so every invalid answer must also be rejected by Core on its own.
"""

from __future__ import annotations

import json

import pytest

from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.planner.cell_prompt import build_monthly_cell_request
from ssuksak.planning.planner.cell_service import MonthlyCellPlanner
from ssuksak.planning.planner.cell_validation import validate_monthly_cell_proposal
from ssuksak.planning.planner.contracts import (
    FOCUS_SECTION_KEY,
    MONTHLY_MODEL,
    OUTDOOR_SECTION_KEY,
    MonthlyCellSnapshot,
    ProposalRejectedError,
    RawLlmResponse,
)
from ssuksak.planning.planner.parser import (
    cell_response_schema,
    monthly_response_schema,
    parse_monthly_cell_proposal,
)
from ssuksak.planning.planner.prompt import build_monthly_planning_request

WEEK_1 = WeekId("2026-09-W1")
WEEK_2 = WeekId("2026-09-W2")
ACTIVITY_ID, ACTIVITY_LABEL = "act-1", "바람개비 놀이"  # conftest reference_activities


def _snapshots() -> tuple[MonthlyCellSnapshot, ...]:
    return (
        MonthlyCellSnapshot(WEEK_1, (("focus", "기존 초점 1"), ("outdoor_play", "기존 놀이 1"))),
        MonthlyCellSnapshot(WEEK_2, (("focus", "기존 초점 2"), ("outdoor_play", "기존 놀이 2"))),
    )


def accepts(schema: dict, value: object) -> bool:
    """The JSON-schema subset the response schemas use (strict objects, enum, anyOf,
    nullable types, array bounds). No external dependency."""
    if "anyOf" in schema:
        return any(accepts(branch, value) for branch in schema["anyOf"])
    kinds = schema.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds] if kinds else []
    checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    if kinds and not any(checks[kind](value) for kind in kinds):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, dict) and "properties" in schema:
        if set(value) != set(schema["properties"]):  # every key required, none extra
            return False
        return all(accepts(schema["properties"][key], item) for key, item in value.items())
    if isinstance(value, list) and "items" in schema:
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            return False
        return all(accepts(schema["items"], item) for item in value)
    return True


def _request(packet, snapshot, section_key=OUTDOOR_SECTION_KEY, week=WEEK_1):
    return build_monthly_cell_request(
        packet, snapshot, target_week_id=week, target_section_key=section_key,
        month_snapshot=_snapshots(),
    )


def _answer(request, **section) -> dict:
    allowed = dict(request.allowed_grounding_refs_by_section)[request.target_section_key]
    body = {
        "section_key": request.target_section_key,
        "value": "바람을 느끼며 놀아요",
        "unresolved": False,
        "reference_id": None,
        "grounding_refs": [allowed[0]],
    }
    body.update(section)
    return {
        "target_month": request.target_month.value,
        "target_week_id": None if request.target_week_id is None else request.target_week_id.value,
        "section": body,
    }


def _core_codes(packet, request, answer: dict) -> tuple[str, ...]:
    proposal = parse_monthly_cell_proposal(json.dumps(answer, ensure_ascii=False))
    return validate_monthly_cell_proposal(proposal, packet, request).codes


# ── the mismatch this PR closes ────────────────────────────────────────────


def test_reference_id_with_rewritten_text_is_rejected_by_core_and_now_by_the_schema(packet, snapshot):
    """The confirmed gap: reference_id = approved catalog id, value = a rewritten sentence.

    Core rejects it with REFERENCE_VALUE_MISMATCH (a 500 for the caller). The Monthly
    schema never lets it through; the cell schema now pairs id and label the same way.
    """
    request = _request(packet, snapshot)
    answer = _answer(request, reference_id=ACTIVITY_ID, value="바람개비를 들고 신나게 달려요",
                     grounding_refs=[])

    assert _core_codes(packet, request, answer) == ("REFERENCE_VALUE_MISMATCH",)
    assert not accepts(cell_response_schema(request), answer)


def test_cell_reference_branches_match_the_monthly_schema(packet, snapshot):
    """Same id/label lock and free-text rules as the full-month proposal for outdoor_play."""
    cell = cell_response_schema(_request(packet, snapshot))["properties"]["section"]["anyOf"]
    monthly = monthly_response_schema(build_monthly_planning_request(packet, snapshot))
    week_items = monthly["properties"]["weeks"]["items"]["properties"]["sections"]["items"]
    outdoor = [
        branch for branch in week_items["anyOf"]
        if branch["properties"]["section_key"]["enum"] == [OUTDOOR_SECTION_KEY]
    ]
    assert cell == outdoor


# ── decode layer and Core layer, case by case ──────────────────────────────


@pytest.mark.parametrize(
    ("case", "section_key", "section", "envelope", "schema_ok", "core_codes"),
    [
        ("reference id with its canonical label", OUTDOOR_SECTION_KEY,
         {"reference_id": ACTIVITY_ID, "value": ACTIVITY_LABEL, "grounding_refs": []}, {}, True, ()),
        ("unknown reference id", OUTDOOR_SECTION_KEY,
         {"reference_id": "act-unknown", "value": ACTIVITY_LABEL, "grounding_refs": []}, {},
         False, ("UNKNOWN_REFERENCE_ID",)),
        ("free text with valid grounding", OUTDOOR_SECTION_KEY, {}, {}, True, ()),
        ("free text without grounding", OUTDOOR_SECTION_KEY, {"grounding_refs": []}, {},
         False, ("RESOLVED_REQUIRES_GROUNDING",)),
        ("unresolved is not supported", OUTDOOR_SECTION_KEY,
         {"unresolved": True, "value": "", "grounding_refs": []}, {},
         False, ("UNRESOLVED_NOT_SUPPORTED",)),
        ("wrong target month", OUTDOOR_SECTION_KEY, {}, {"target_month": "2026-10"},
         False, ("TARGET_MONTH_MISMATCH",)),
        ("wrong target week", OUTDOOR_SECTION_KEY, {}, {"target_week_id": WEEK_2.value},
         False, ("TARGET_WEEK_MISMATCH",)),
        ("wrong target section", OUTDOOR_SECTION_KEY, {"section_key": FOCUS_SECTION_KEY}, {},
         False, ("TARGET_SECTION_MISMATCH",)),
        ("reference id in a section without a catalog", FOCUS_SECTION_KEY,
         {"reference_id": ACTIVITY_ID, "value": ACTIVITY_LABEL, "grounding_refs": []}, {},
         False, ("UNKNOWN_REFERENCE_ID",)),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value else None,
)
def test_schema_blocks_what_core_rejects(packet, snapshot, case, section_key, section, envelope,
                                         schema_ok, core_codes):
    request = _request(packet, snapshot, section_key)
    answer = _answer(request, **section)
    answer.update(envelope)

    assert accepts(cell_response_schema(request), answer) is schema_ok
    assert _core_codes(packet, request, answer) == core_codes  # Core alone still decides


def test_planner_returns_a_reference_answer_end_to_end(packet, snapshot):
    """Real parser + validator through MonthlyCellPlanner, no network."""
    request = _request(packet, snapshot)
    answer = _answer(request, reference_id=ACTIVITY_ID, value=ACTIVITY_LABEL, grounding_refs=[])

    class Provider:
        def generate_cell(self, req):
            assert accepts(cell_response_schema(req), answer)
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), MONTHLY_MODEL, "r-1")

    outcome = MonthlyCellPlanner(Provider()).plan(
        packet, snapshot, target_week_id=WEEK_1, target_section_key=OUTDOOR_SECTION_KEY,
        month_snapshot=_snapshots(),
    )
    assert (outcome.proposal.section.reference_id, outcome.proposal.section.value) == (
        ACTIVITY_ID,
        ACTIVITY_LABEL,
    )


def test_planner_still_fails_closed_on_a_rewritten_reference(packet, snapshot):
    """A provider that ignores the schema is still stopped by Core (no normalization)."""
    request = _request(packet, snapshot)
    answer = _answer(request, reference_id=ACTIVITY_ID, value="바람개비를 들고 달려요", grounding_refs=[])

    class Provider:
        def generate_cell(self, req):
            return RawLlmResponse(json.dumps(answer, ensure_ascii=False), MONTHLY_MODEL, "r-1")

    with pytest.raises(ProposalRejectedError) as excinfo:
        MonthlyCellPlanner(Provider()).plan(
            packet, snapshot, target_week_id=WEEK_1, target_section_key=OUTDOOR_SECTION_KEY,
            month_snapshot=_snapshots(),
        )
    assert excinfo.value.validation_codes == ("REFERENCE_VALUE_MISMATCH",)
