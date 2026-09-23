"""Build a single-cell prompt without owning MonthlyPlan orchestration."""

from __future__ import annotations

import hashlib
import json

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from .contracts import (
    MONTHLY_CELL_PROMPT_VERSION,
    MonthlyCellPlanningRequest,
    MonthlyCellSnapshot,
)
from .prompt import _prompt_payload, valid_grounding_refs

MONTHLY_CELL_TASK = "monthly_cell_proposal"

CELL_SYSTEM_PROMPT = """You propose exactly one monthly planning cell.
Use only the supplied Context Packet and month snapshot.
Do not change target month, target week, target section, theme, or any sibling cell.
Do not make legal decisions or generate statutory safety education.
Return only one JSON object matching the requested contract; add no fields.
"""


def snapshot_fingerprint(snapshot: tuple[MonthlyCellSnapshot, ...]) -> str:
    payload = [
        {
            "week_id": value.week_id,
            "focus": value.focus,
            "outdoor_play": value.outdoor_play,
        }
        for value in snapshot
    ]
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_monthly_cell_request(
    packet: MonthlyContextPacket,
    *,
    target_week_id: str,
    target_section_key: str,
    month_snapshot: tuple[MonthlyCellSnapshot, ...],
) -> MonthlyCellPlanningRequest:
    expected_week_ids = tuple(week.week_id for week in packet.weeks)
    if target_week_id not in expected_week_ids:
        raise ValueError("target_week_id is not in the Context Packet")
    if tuple(value.week_id for value in month_snapshot) != expected_week_ids:
        raise ValueError("month snapshot must cover Context weeks in order")
    body = _prompt_payload(packet)
    body.update(
        {
            "target_cell": {
                "week_id": target_week_id,
                "section_key": target_section_key,
            },
            "month_snapshot": [
                {
                    "week_id": value.week_id,
                    "focus": value.focus,
                    "outdoor_play": value.outdoor_play,
                }
                for value in month_snapshot
            ],
            "response_contract": {
                "target_month": "string",
                "target_week_id": "string",
                "target_section_key": "focus | outdoor_play",
                "value": "string",
                "activity_origin": "REFERENCE | LLM_SYNTHESIZED | null",
                "reference_activity_id": "string | null",
                "grounding_refs": ["string"],
            },
        }
    )
    return MonthlyCellPlanningRequest(
        task=MONTHLY_CELL_TASK,
        prompt_version=MONTHLY_CELL_PROMPT_VERSION,
        system_prompt=CELL_SYSTEM_PROMPT,
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2),
        target_month=packet.target_month.value,
        target_week_id=target_week_id,
        target_section_key=target_section_key,
        expected_theme_id=packet.parent_theme_id,
        reference_labels=tuple(
            (item.activity_id, item.label) for item in packet.reference_activities
        ),
        valid_grounding_refs=valid_grounding_refs(packet),
        packet_fingerprint=packet_fingerprint(packet),
        plan_snapshot_fingerprint=snapshot_fingerprint(month_snapshot),
    )
