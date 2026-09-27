"""Build the full-month prompt from a PR4 Context Packet."""

from __future__ import annotations

import json

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from .contracts import MONTHLY_PROMPT_VERSION, MonthlyPlanningRequest

MONTHLY_TASK = "monthly_plan_proposal"

SYSTEM_PROMPT = """You propose teacher-visible monthly planning text.
Use only the supplied Context Packet. Do not invent facts or citations.
Do not change target_month, theme_id, week ids, or their order.
Do not make legal decisions or generate statutory safety education.
Reference activities must keep the supplied activity id and exact label.
Synthesized activities require at least one supplied grounding_ref and must not copy source text verbatim.
Return only one JSON object matching the requested contract; add no fields.
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
        "response_contract": {
            "target_month": "string",
            "theme_id": "string",
            "month_flow_rationale": "string",
            "weeks": [
                {
                    "week_id": "string",
                    "experience": "string",
                    "activity": {
                        "value": "string",
                        "origin": "REFERENCE | LLM_SYNTHESIZED",
                        "reference_activity_id": "string | null",
                        "grounding_refs": ["string"],
                    },
                }
            ],
        },
    }


def build_monthly_planning_request(packet: MonthlyContextPacket) -> MonthlyPlanningRequest:
    if not isinstance(packet, MonthlyContextPacket):
        raise TypeError("packet must be MonthlyContextPacket")
    return MonthlyPlanningRequest(
        task=MONTHLY_TASK,
        prompt_version=MONTHLY_PROMPT_VERSION,
        system_prompt=SYSTEM_PROMPT,
        user_content=json.dumps(
            _prompt_payload(packet), ensure_ascii=False, sort_keys=True, indent=2
        ),
        target_month=packet.target_month.value,
        expected_theme_id=packet.parent_theme_id,
        expected_week_ids=tuple(week.week_id for week in packet.weeks),
        reference_labels=tuple(
            (item.activity_id, item.label) for item in packet.reference_activities
        ),
        valid_grounding_refs=valid_grounding_refs(packet),
        packet_fingerprint=packet_fingerprint(packet),
    )
