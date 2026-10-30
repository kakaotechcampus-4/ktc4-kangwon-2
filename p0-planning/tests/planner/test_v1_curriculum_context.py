import json
from dataclasses import replace

import pytest

from ssuksak.adapters.v1_curriculum import v1_curriculum_catalog
from ssuksak.planning.context.serialization import packet_fingerprint
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.planner.cell_prompt import build_monthly_cell_request
from ssuksak.planning.planner.parser import parse_monthly_proposal
from ssuksak.planning.planner.prompt import (
    build_monthly_planning_request,
    build_monthly_repair_request,
    valid_grounding_refs,
)
from ssuksak.planning.planner.validation import validate_monthly_proposal
from ssuksak.planning.planner.v1_guidance import curriculum_context
from ssuksak.planning.planner.weekly import (
    WeeklyTarget,
    build_weekly_request,
    cell_request,
)
from tests.planner.test_monthly_planner import monthly_payload, snapshots


def test_curriculum_is_versioned_context_without_new_allowed_cell_refs(
    packet, snapshot
):
    original = build_monthly_planning_request(packet, snapshot)
    augmented = replace(
        packet,
        curriculum=v1_curriculum_catalog(),
        parent_subthemes=("씨앗의 모양", "자라는 모습"),
    )
    request = build_monthly_planning_request(augmented, snapshot)
    body = json.loads(request.user_content)
    assert len(body["curriculum_context"]["contents"]) == 59
    assert len({c["domain"] for c in body["curriculum_context"]["contents"]}) == 5
    assert body["parent_subthemes"] == ["씨앗의 모양", "자라는 모습"]
    assert (
        request.valid_grounding_refs
        == original.valid_grounding_refs
        == valid_grounding_refs(packet)
    )
    assert (
        request.allowed_grounding_refs_by_section
        == original.allowed_grounding_refs_by_section
    )
    assert request.packet_fingerprint != original.packet_fingerprint
    assert packet_fingerprint(augmented) != packet_fingerprint(
        replace(augmented, parent_subthemes=("교사 확정값",))
    )
    assert request.prompt_version == "monthly-planner-v19"
    cell = build_monthly_cell_request(
        augmented,
        snapshot,
        target_week_id=WeekId("2026-09-W1"),
        target_section_key="focus",
        month_snapshot=snapshots(),
    )
    assert json.loads(cell.user_content)["parent_subthemes"] == body["parent_subthemes"]
    assert cell.prompt_version == "monthly-cell-planner-v11"


def test_unapproved_curriculum_is_never_sent(packet):
    pending = replace(
        v1_curriculum_catalog(), activation_status=ActivationStatus.PENDING_HUMAN_REVIEW
    )
    with pytest.raises(InvalidDomainValueError):
        curriculum_context(pending)
    with pytest.raises(InvalidDomainValueError):
        replace(packet, curriculum=pending)


def test_curriculum_ids_cannot_be_visible_or_used_as_grounding(packet, snapshot):
    packet = replace(packet, curriculum=v1_curriculum_catalog())
    request = build_monthly_planning_request(packet, snapshot)
    payload = monthly_payload()
    content_id = packet.curriculum.contents[0].content_id
    payload["weeks"][0]["sections"][0]["value"] = content_id + " 함께 움직이기"
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(payload)), packet, request
    )
    assert any(i.detail == "SOURCE_IDENTIFIER_LEAKAGE" for i in result.issues)
    repair = build_monthly_repair_request(request, json.dumps(payload), result.issues)
    assert repair.prompt_version == "monthly-planner-repair-v14"
    assert (
        json.loads(repair.user_content)["original_request"]["curriculum_context"]
        == json.loads(request.user_content)["curriculum_context"]
    )
    payload["weeks"][0]["sections"][0]["grounding_refs"] = [content_id]
    result = validate_monthly_proposal(
        parse_monthly_proposal(json.dumps(payload)), packet, request
    )
    assert "UNKNOWN_GROUNDING_REF" in result.codes


def test_weekly_and_cell_regeneration_keep_curriculum_and_parent_context():
    request = build_weekly_request(
        week_id=WeekId("2026-09-W1"),
        week={},
        ages=(3,),
        targets=(WeeklyTarget("theme", parent_value="교사 확정 월간 주제"),),
        teacher_input_keys=frozenset(),
        parent_context=(("theme", "교사 확정 월간 주제"),),
        evidence=(),
        reference_candidates=(),
        packet_fingerprint="packet",
        curriculum=v1_curriculum_catalog(),
    )
    cell = cell_request(
        request, "theme", current_values=(("theme", "현재 값"),), teacher_facts=()
    )
    for r in (request, cell):
        body = json.loads(r.user_content)
        assert len(body["curriculum_context"]["contents"]) == 59
        assert body["parent"]["theme"] == "교사 확정 월간 주제"
        assert "curriculum_context" in r.system_prompt
        assert r.context_source_refs
    assert request.prompt_version == "weekly-planner-v3"
    assert cell.prompt_version == "weekly-cell-planner-v2"
