"""Build a single-cell prompt without owning MonthlyPlan orchestration."""

from __future__ import annotations

import hashlib
import json

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from ..domain.monthly_template import DisplayMode, SectionRole
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..domain.week_period import WeekId
from ..evidence.classification import grounding_class_for
from .contracts import (
    MONTHLY_CELL_PROMPT_VERSION,
    MonthlyCellPlanningRequest,
    MonthlyCellSnapshot,
)
from .prompt import _generation_schema, _prompt_payload, valid_grounding_refs

MONTHLY_CELL_TASK = "monthly_cell_proposal"

CELL_SYSTEM_PROMPT = """You propose exactly one canonical monthly section value.
Use only the supplied Context Packet, Template snapshot schema, and month content snapshot.
Do not change target month, target week, target section, theme, or sibling values.
Return only section_key, value, unresolved, reference_id, and grounding_refs.
Do not return or redefine Template presentation metadata.
Do not make legal decisions or generate statutory safety education.
Every resolved value needs supplied grounding_refs or a supplied reference_id.
A section with a grounding_class may cite only evidence with that grounding_class;
a section without one must not cite evidence that has a grounding_class.
Write user-facing plan text in value fields in natural Korean.
Keep JSON keys, section_key, week ids, enum values, IDs, reference_id and
grounding_refs exactly as supplied or specified; never translate them.
Include every key required by response_contract in every object and cell;
for a nullable field with no value, include the key with null, never omit it.
Return only one JSON object matching response_contract; add no fields.
"""


def snapshot_fingerprint(
    snapshot: tuple[MonthlyCellSnapshot, ...],
) -> str:
    payload = [
        {
            "week_id": value.week_id.value,
            "sections": [
                {"section_key": key, "value": content}
                for key, content in value.section_values
            ],
        }
        for value in snapshot
    ]
    blob = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_monthly_cell_request(
    packet: MonthlyContextPacket,
    snapshot: TemplateSnapshot,
    *,
    target_week_id: WeekId | None,
    target_section_key: str,
    month_snapshot: tuple[MonthlyCellSnapshot, ...],
) -> MonthlyCellPlanningRequest:
    expected_week_ids = tuple(WeekId(week.week_id) for week in packet.weeks)
    if target_week_id is not None and target_week_id not in expected_week_ids:
        raise ValueError("target_week_id is not in the Context Packet")
    if tuple(value.week_id for value in month_snapshot) != expected_week_ids:
        raise ValueError("month snapshot must cover Context weeks in order")
    target_section = snapshot.section(target_section_key)
    if target_section is None or target_section.role is not SectionRole.CONTENT:
        raise ValueError("target section is not a Snapshot content section")
    # Placement vs target_week_id is enforced by MonthlyCellPlanningRequest.
    merged = target_section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
    target_cell: dict[str, object] = {
        "week_id": None if target_week_id is None else target_week_id.value,
        "section_key": target_section_key,
    }
    if merged:
        grounding_class = grounding_class_for(target_section)
        target_cell.update(
            placement="MONTH",
            grounding_class=None if grounding_class is None else grounding_class.value,
        )
    body = _prompt_payload(packet)
    body.update(
        {
            "generation_schema": _generation_schema(snapshot),
            "target_cell": target_cell,
            "month_snapshot": [
                {
                    "week_id": value.week_id.value,
                    "sections": [
                        {"section_key": key, "value": content}
                        for key, content in value.section_values
                    ],
                }
                for value in month_snapshot
            ],
            "response_contract": {
                "target_month": "YYYY-MM",
                "target_week_id": None if merged else "YYYY-MM-Wn",
                "section": {
                    "section_key": "string",
                    "value": "string",
                    "unresolved": "boolean",
                    "reference_id": "string | null",
                    "grounding_refs": ["string"],
                },
            },
        }
    )
    return MonthlyCellPlanningRequest(
        task=MONTHLY_CELL_TASK,
        prompt_version=MONTHLY_CELL_PROMPT_VERSION,
        system_prompt=CELL_SYSTEM_PROMPT,
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2),
        target_month=packet.target_month,
        target_week_id=target_week_id,
        target_section_key=target_section_key,
        expected_theme_id=packet.parent_theme_id,
        template_snapshot=snapshot,
        reference_labels=tuple(
            (item.activity_id, item.label) for item in packet.reference_activities
        ),
        valid_grounding_refs=valid_grounding_refs(packet),
        packet_fingerprint=packet_fingerprint(packet),
        plan_snapshot_fingerprint=snapshot_fingerprint(month_snapshot),
    )
