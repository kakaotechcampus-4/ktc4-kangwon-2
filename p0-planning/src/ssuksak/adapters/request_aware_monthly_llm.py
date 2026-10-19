"""Deterministic Monthly LLM provider for development and tests (``LLM_MODE=mock``).

Unlike ``DeterministicMonthlyLlm`` (one fixed string), every answer is derived
from the request itself: its target month, active week ids, Template Snapshot
Sections, reference labels and the grounding refs in the packet. So it keeps
passing Core validation when the month, the weeks or the Section set change.

It never calls a network and must never stand in for a failed real provider.
Behaviour follows ``tests/finalization/harness.py`` ``RequestAwareMonthlyLlm``.
"""

from __future__ import annotations

import json

from ssuksak.planning.domain.monthly_template import RepeatBy, SectionRole
from ssuksak.planning.planner.contracts import (
    MONTHLY_MODEL,
    MonthlyCellPlanningRequest,
    MonthlyPlanningRequest,
    RawLlmResponse,
)


def grounding_ref_for(request, section_key: str) -> str | None:
    """First supplied evidence ref allowed for this Section's grounding_class."""
    body = json.loads(request.user_content)
    expected = next(
        (
            section.get("grounding_class")
            for section in body["generation_schema"]["sections"]
            if section["section_key"] == section_key
        ),
        None,
    )
    refs = sorted(
        item["grounding_ref"]
        for item in body["evidence"]
        if item["grounding_class"] == expected
    )
    return refs[0] if refs else None


def _cell(section_key: str, value: str, ref: str | None) -> dict[str, object]:
    return {
        "section_key": section_key,
        "value": value,
        "unresolved": False,
        "reference_id": None,
        "grounding_refs": [ref],
    }


class RequestAwareMonthlyLlm:
    """Network-free provider whose output is derived only from each request."""

    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        reference_id, reference_label = request.reference_labels[0]
        safety_plan = json.loads(request.user_content).get("safety_plan")

        def safety_value(index: int) -> dict[str, object] | None:
            if safety_plan is None:
                return None
            slot = safety_plan["weeks"][index - 1]
            if slot["kind"] == "STATUTORY":
                refs = [slot["official_content"][0]["grounding_ref"]]
            elif slot["primary_ref"]:
                refs = [slot["primary_ref"]]
            else:
                return None
            return {
                "section_key": "safety_education",
                "value": f"{index}주 안전교육",
                "unresolved": False,
                "reference_id": None,
                "grounding_refs": refs,
            }

        def week_value(section_key: str, index: int) -> dict[str, object]:
            if section_key == "safety_education":
                # No placement plan: leave it unresolved, never invent content.
                return safety_value(index) or {
                    "section_key": section_key,
                    "value": "",
                    "unresolved": True,
                    "reference_id": None,
                    "grounding_refs": [],
                }
            if section_key == "outdoor_play" and index == 1:
                return {
                    "section_key": section_key,
                    "value": reference_label,
                    "unresolved": False,
                    "reference_id": reference_id,
                    "grounding_refs": [],
                }
            return _cell(
                section_key,
                f"{index}주 {section_key}",
                grounding_ref_for(request, section_key),
            )

        month_sections: list[dict[str, object]] = []
        weekly_keys: list[str] = []
        for section in request.template_snapshot.sections:
            if section.role is SectionRole.AXIS:
                continue
            if section.repeat_by is RepeatBy.WEEK:
                weekly_keys.append(section.section_key)
            elif section.section_key == "theme":
                month_sections.append(
                    {
                        "section_key": "theme",
                        "value": request.expected_theme_value,
                        "unresolved": False,
                        "reference_id": request.expected_theme_id,
                        "grounding_refs": [],
                    }
                )
            elif section.repeat_by is RepeatBy.NONE and section.required_for_generation:
                month_sections.append(
                    _cell(
                        section.section_key,
                        f"이달의 {section.section_key}",
                        grounding_ref_for(request, section.section_key),
                    )
                )
        weeks = [
            {
                "week_id": week_id.value,
                "sections": [
                    week_value(key, index)
                    for key in weekly_keys
                    if key == "safety_education"
                    or (key == "outdoor_play" and index == 1)
                    or grounding_ref_for(request, key) is not None
                ],
            }
            for index, week_id in enumerate(request.expected_week_ids, start=1)
        ]
        payload = {
            "target_month": request.target_month.value,
            "month_sections": month_sections,
            "weeks": weeks,
        }
        return RawLlmResponse(
            json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "request-aware-monthly"
        )

    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse:
        payload = {
            "target_month": request.target_month.value,
            "target_week_id": (
                None if request.target_week_id is None else request.target_week_id.value
            ),
            "section": _cell(
                request.target_section_key,
                f"다시 만든 {request.target_section_key}",
                grounding_ref_for(request, request.target_section_key),
            ),
        }
        return RawLlmResponse(
            json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "request-aware-cell"
        )
