"""Build the full-month prompt from a PR4 Context Packet."""

from __future__ import annotations

import json

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from ..domain.monthly_template import DisplayMode, SectionRole
from ..domain.monthly_template_profile import INSTITUTION_INPUT_SECTION_KEYS
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..domain.week_period import WeekId
from .contracts import (
    MONTHLY_PROMPT_VERSION,
    MonthlyPlanningRequest,
)

MONTHLY_TASK = "monthly_plan_proposal"

SYSTEM_PROMPT = """You propose values for one monthly plan Template snapshot.
Use only the supplied Context Packet and generation_schema.
Do not add, remove, relabel, reorder, or reinterpret Template sections.
Return content only for canonical section_key addresses in response_contract.
Do not return display_label, order, semantic_variant, category, display_mode,
required_for_generation, or visible.
The locked theme must be returned exactly with its supplied reference_id.
Do not make legal decisions or claim statutory compliance.
For safety_education, use approved safety grounding from the supplied Context;
when that grounding is unavailable, return value="", unresolved=true, no refs.
Every other resolved generated value needs supplied grounding_refs or a supplied
reference_id. Do not invent facts or citations and do not copy evidence verbatim.
Return only one JSON object matching response_contract; add no fields.
"""


def _grounding_items(packet: MonthlyContextPacket) -> tuple[object, ...]:
    return (
        packet.institution_evidence
        + packet.age_contrast_evidence
        + packet.week_experience_candidates
        + packet.other_outdoor_evidence
    )


def valid_grounding_refs(packet: MonthlyContextPacket) -> frozenset[str]:
    return frozenset(item.evidence_ref for item in _grounding_items(packet))


def _prompt_payload(packet: MonthlyContextPacket) -> dict[str, object]:
    return {
        "target_month": packet.target_month.value,
        "ages": list(packet.ages),
        "locked_theme": {
            "theme_id": packet.parent_theme_id,
            "value": packet.parent_theme_value,
        },
        "weeks": [
            {
                "week_id": week.week_id,
                "start_date": week.start_date.isoformat(),
                "end_date": week.end_date.isoformat(),
                "display_label": week.display_label,
            }
            for week in packet.weeks
        ],
        "evidence": [
            {
                "grounding_ref": item.evidence_ref,
                "text": item.text,
                "source_section": item.source_section.value,
                "source_label": item.source_label,
                "age_scope": list(item.age_scope),
                "institution_alias": item.institution_alias,
                "reuse_policy": item.reuse_policy.value,
            }
            for item in _grounding_items(packet)
        ],
        "reference_activities": [
            {"activity_id": item.activity_id, "label": item.label, "rank": item.rank}
            for item in packet.reference_activities
        ],
        "deterministic_constraints": list(
            packet.constraints.deterministic_constraint_codes
        ),
        "lineage": {
            "evidence_store_version": packet.lineage.evidence_store_version,
            "evidence_store_sha256": packet.lineage.evidence_store_sha256,
            "retrieval_version": packet.lineage.retrieval_version,
            "activity_catalog_id": packet.lineage.activity_catalog_id,
            "activity_catalog_version": packet.lineage.activity_catalog_version,
        },
    }


def _generation_schema(snapshot: TemplateSnapshot) -> dict[str, object]:
    sections: list[dict[str, object]] = []
    for section in snapshot.sections:
        if section.section_key in INSTITUTION_INPUT_SECTION_KEYS:
            continue
        if section.role is SectionRole.AXIS:
            sections.append(
                {
                    "section_key": section.section_key,
                    "placement": "AXIS",
                    "required_for_generation": section.required_for_generation,
                }
            )
            continue
        placement = (
            "MONTH"
            if section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
            else "WEEK"
        )
        sections.append(
            {
                "section_key": section.section_key,
                "placement": placement,
                "semantic_variant": (
                    None
                    if section.semantic_variant is None
                    else section.semantic_variant.value
                ),
                "empty_value_policy": (
                    None
                    if section.empty_value_policy is None
                    else section.empty_value_policy.value
                ),
                "required_for_generation": section.required_for_generation,
            }
        )
    return {
        "profile_id": snapshot.profile_ref.profile_id,
        "profile_version": snapshot.profile_ref.profile_version,
        "sections": sections,
    }


def _response_contract() -> dict[str, object]:
    section = {
        "section_key": "string",
        "value": "string; empty only when unresolved=true",
        "unresolved": "boolean",
        "reference_id": "string | null",
        "grounding_refs": ["string"],
    }
    return {
        "target_month": "YYYY-MM",
        "month_sections": [section],
        "weeks": [{"week_id": "YYYY-MM-Wn", "sections": [section]}],
    }


def build_monthly_planning_request(
    packet: MonthlyContextPacket, snapshot: TemplateSnapshot
) -> MonthlyPlanningRequest:
    if not isinstance(packet, MonthlyContextPacket):
        raise TypeError("packet must be MonthlyContextPacket")
    if not isinstance(snapshot, TemplateSnapshot):
        raise TypeError("snapshot must be TemplateSnapshot")
    body = _prompt_payload(packet)
    body.update(
        {
            "generation_schema": _generation_schema(snapshot),
            "response_contract": _response_contract(),
        }
    )
    return MonthlyPlanningRequest(
        task=MONTHLY_TASK,
        prompt_version=MONTHLY_PROMPT_VERSION,
        system_prompt=SYSTEM_PROMPT,
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2),
        target_month=packet.target_month,
        expected_theme_id=packet.parent_theme_id,
        expected_theme_value=packet.parent_theme_value,
        expected_week_ids=tuple(WeekId(week.week_id) for week in packet.weeks),
        template_snapshot=snapshot,
        reference_labels=tuple(
            (item.activity_id, item.label) for item in packet.reference_activities
        ),
        valid_grounding_refs=valid_grounding_refs(packet),
        packet_fingerprint=packet_fingerprint(packet),
    )
