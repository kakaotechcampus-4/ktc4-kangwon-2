"""Strict JSON parsers for provider output."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..domain.errors import InvalidDomainValueError
from ..domain.week_period import WeekId
from ..domain.year_month import YearMonth
from ..domain.monthly_template import RepeatBy
from .contracts import (
    MonthlyCellPlanningRequest,
    MonthlyCellProposal,
    MonthlyPlanningRequest,
    generation_target_sections,
    MonthlyPlanProposal,
    ProposalParseError,
    ProposedSectionValue,
    ProposedWeek,
)

_log = logging.getLogger(__name__)


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    """A strict object: every property required, no additional properties."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_STRING = {"type": "string"}
_NULLABLE_STRING = {"type": ["string", "null"]}
# One schema per response object. The parser reads its exact key sets from these,
# so the provider-level Structured Output schema cannot drift from the parser.
_SECTION_SCHEMA = _object_schema(
    {
        "section_key": _STRING,
        "value": _STRING,
        "unresolved": {"type": "boolean"},
        "reference_id": _NULLABLE_STRING,
        "grounding_refs": {"type": "array", "items": _STRING},
    }
)
_WEEK_SCHEMA = _object_schema(
    {"week_id": _STRING, "sections": {"type": "array", "items": _SECTION_SCHEMA}}
)
MONTHLY_RESPONSE_SCHEMA = _object_schema(
    {
        "target_month": _STRING,
        "month_sections": {"type": "array", "items": _SECTION_SCHEMA},
        "weeks": {"type": "array", "items": _WEEK_SCHEMA},
    }
)
CELL_RESPONSE_SCHEMA = _object_schema(
    {"target_month": _STRING, "target_week_id": _NULLABLE_STRING, "section": _SECTION_SCHEMA}
)


def _keys(schema: dict[str, Any]) -> frozenset[str]:
    return frozenset(schema["properties"])


def _refs_schema(refs: tuple[str, ...]) -> dict[str, Any]:
    return (
        {"type": "array", "items": {"type": "string", "enum": list(refs)}}
        if refs
        # No allowed ref: only an empty list, never the Packet-wide refs.
        else {"type": "array", "items": _STRING, "maxItems": 0}
    )


def _section_branches(
    section_key: str,
    refs: tuple[str, ...],
    reference_sections: frozenset[str] | None = None,
    reference_pairs: tuple[tuple[str, str], ...] | None = None,
) -> list[dict[str, Any]]:
    """The static Section schema for one section_key and only the refs it may cite.

    With reference_pairs (Monthly proposals only, possibly empty) each supplied reference
    is one branch that fixes its reference_id and its canonical value together, so an id
    can only be returned with its own label. Theme has its one locked pair; outdoor_play
    may instead be free text with a null reference_id. A non-safety free-text branch
    mirrors the validator: it is never unresolved and cites at least one ref.
    """
    properties = dict(_SECTION_SCHEMA["properties"])
    properties["section_key"] = {"type": "string", "enum": [section_key]}
    properties["grounding_refs"] = _refs_schema(refs)
    if section_key == "safety_education" or (
        reference_sections is not None and section_key not in reference_sections
    ):
        # No supplied Reference catalog for this section: reference_id is null.
        # Safety grounding goes in grounding_refs.
        properties["reference_id"] = {"type": "null"}
    if reference_pairs is None:
        return [_object_schema(properties)]
    pairs = [
        _object_schema(dict(
            properties,
            value={"type": "string", "enum": [label]},
            unresolved={"type": "boolean", "enum": [False]},
            reference_id={"type": "string", "enum": [reference_id]},
            # A reference cell is grounded by its reference (OD-N13); it cites no refs.
            grounding_refs=_refs_schema(()),
        ))
        for reference_id, label in reference_pairs
    ]
    if section_key == "theme":
        return pairs
    free = {"reference_id": {"type": "null"}} if reference_pairs else {}
    if section_key != "safety_education":
        # UNRESOLVED_NOT_ALLOWED and RESOLVED_REQUIRES_GROUNDING, enforced at decode (C019/C021).
        free["unresolved"] = {"type": "boolean", "enum": [False]}
        if refs:
            free["grounding_refs"] = dict(properties["grounding_refs"], minItems=1)
    return [*pairs, _object_schema(dict(properties, **free))]


def _section_schema(
    section_keys: set[str],
    request,
    reference_sections: frozenset[str] | None = None,
    reference_pairs: dict[str, tuple[tuple[str, str], ...]] | None = None,
) -> dict[str, Any]:
    """One branch per target Section; the parser and validator stay the final check."""
    allowed = dict(request.allowed_grounding_refs_by_section)
    branches = [
        branch
        for key in sorted(section_keys)
        for branch in _section_branches(
            key,
            allowed.get(key, ()),
            reference_sections,
            None if reference_pairs is None else reference_pairs.get(key, ()),
        )
    ]
    return branches[0] if len(branches) == 1 else {"anyOf": branches}


def _reference_pairs(request: MonthlyPlanningRequest) -> dict[str, tuple[tuple[str, str], ...]]:
    """(reference_id, canonical value) each reference Section may return: the locked theme
    and the supplied catalog."""
    pairs = {"theme": ((request.expected_theme_id, request.expected_theme_value),)}
    if "outdoor_play" in request.reference_section_keys:
        pairs["outdoor_play"] = request.reference_labels
    return pairs


def repair_patch_schema(request: MonthlyPlanningRequest) -> dict[str, Any]:
    """A repair returns patches for its repair_targets only: one branch per target cell.

    Each branch fixes the cell address and allows exactly the fields that target may
    change, so no other cell, reference_id or unresolved can be expressed at all.
    """
    allowed = dict(request.allowed_grounding_refs_by_section)
    branches = []
    for week_id, section_key, fields in request.repair_targets:
        properties: dict[str, Any] = {
            "week_id": {"type": "null"} if week_id is None else {"type": "string", "enum": [week_id]},
            "section_key": {"type": "string", "enum": [section_key]},
        }
        if "value" in fields:
            properties["value"] = _STRING
        if "grounding_refs" in fields:
            properties["grounding_refs"] = _refs_schema(allowed.get(section_key, ()))
        branches.append(_object_schema(properties))
    item = branches[0] if len(branches) == 1 else {"anyOf": branches}
    return _object_schema({"patches": {"type": "array", "items": item}})


def monthly_response_schema(request: MonthlyPlanningRequest) -> dict[str, Any]:
    """MONTHLY_RESPONSE_SCHEMA scoped to the request's target Sections and their allowed refs.

    A repair request instead gets repair_patch_schema.
    """
    if request.repair_targets:
        return repair_patch_schema(request)
    allowed = dict(request.allowed_grounding_refs_by_section)
    pairs = _reference_pairs(request)
    targets = [
        s for s in generation_target_sections(request.template_snapshot) if s.section_key in allowed
    ]
    month = _section_schema(
        {s.section_key for s in targets if s.repeat_by is RepeatBy.NONE},
        request,
        request.reference_section_keys,
        pairs,
    )
    week = _section_schema(
        {s.section_key for s in targets if s.repeat_by is RepeatBy.WEEK},
        request,
        request.reference_section_keys,
        pairs,
    )
    return _object_schema(
        {
            "target_month": _STRING,
            "month_sections": {"type": "array", "items": month},
            "weeks": {
                "type": "array",
                "items": _object_schema(
                    {"week_id": _STRING, "sections": {"type": "array", "items": week}}
                ),
            },
        }
    )


def cell_response_schema(request: MonthlyCellPlanningRequest) -> dict[str, Any]:
    """CELL_RESPONSE_SCHEMA with the target section and its allowed refs as enums."""
    return _object_schema(
        {
            "target_month": _STRING,
            "target_week_id": _NULLABLE_STRING,
            "section": _section_schema(
                {request.target_section_key}, request, request.reference_section_keys
            ),
        }
    )


def _object(value: object, *, path: str, keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProposalParseError(f"{path} must be an object")
    actual = frozenset(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise ProposalParseError(f"{path} fields mismatch; missing={missing}, extra={extra}")
    return value


def _string(value: object, *, path: str, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProposalParseError(f"{path} must be a non-blank string")
    return value


def _strings(value: object, *, path: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ProposalParseError(f"{path} must be an array of non-blank strings")
    return tuple(value)


def _json(content: str) -> object:
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProposalParseError("provider response is not valid JSON") from exc


def _boolean(value: object, *, path: str) -> bool:
    if type(value) is not bool:
        raise ProposalParseError(f"{path} must be a boolean")
    return value


def _year_month(value: object, *, path: str) -> YearMonth:
    raw = _string(value, path=path)
    try:
        year, month = raw.split("-", maxsplit=1)
        if len(year) != 4 or len(month) != 2:
            raise ValueError
        return YearMonth(int(year), int(month))
    except (TypeError, ValueError, InvalidDomainValueError) as exc:
        raise ProposalParseError(f"{path} must use YYYY-MM format") from exc


def _week_id(value: object, *, path: str) -> WeekId:
    try:
        return WeekId(_string(value, path=path))
    except InvalidDomainValueError as exc:
        raise ProposalParseError(str(exc)) from exc


def _canonical_refs(value: object, *, path: str) -> tuple[str, ...]:
    """grounding_refs is a set of evidence ids: drop exact repeats, keep first-seen order.

    Only this provider boundary canonicalizes; ProposedSectionValue still rejects
    duplicates, and unknown or wrong-source refs are left for the validators.
    """
    refs = _strings(value, path=path)
    canonical = tuple(dict.fromkeys(refs))
    if len(canonical) != len(refs):
        _log.info("duplicate_grounding_refs_normalized count=%d", len(refs) - len(canonical))
    return canonical


def _section_value(value: object, *, path: str) -> ProposedSectionValue:
    item = _object(value, path=path, keys=_keys(_SECTION_SCHEMA))
    raw_value = item["value"]
    if not isinstance(raw_value, str):
        raise ProposalParseError(f"{path}.value must be a string")
    try:
        return ProposedSectionValue(
            section_key=_string(item["section_key"], path=f"{path}.section_key"),
            value=raw_value,
            unresolved=_boolean(item["unresolved"], path=f"{path}.unresolved"),
            reference_id=_string(
                item["reference_id"],
                path=f"{path}.reference_id",
                nullable=True,
            ),
            grounding_refs=_canonical_refs(
                item["grounding_refs"], path=f"{path}.grounding_refs"
            ),
        )
    except InvalidDomainValueError as exc:
        raise ProposalParseError(str(exc)) from exc


def _unique_section_keys(
    values: tuple[ProposedSectionValue, ...], *, path: str
) -> None:
    keys = tuple(value.section_key for value in values)
    if len(set(keys)) != len(keys):
        raise ProposalParseError(f"{path} contains duplicate section_key values")


def parse_monthly_proposal(content: str) -> MonthlyPlanProposal:
    root = _object(
        _json(content),
        path="proposal",
        keys=_keys(MONTHLY_RESPONSE_SCHEMA),
    )
    raw_month_sections = root["month_sections"]
    if not isinstance(raw_month_sections, list):
        raise ProposalParseError("proposal.month_sections must be an array")
    month_sections = tuple(
        _section_value(value, path=f"proposal.month_sections[{index}]")
        for index, value in enumerate(raw_month_sections)
    )
    _unique_section_keys(month_sections, path="proposal.month_sections")

    raw_weeks = root["weeks"]
    if not isinstance(raw_weeks, list) or not raw_weeks:
        raise ProposalParseError("proposal.weeks must be a non-empty array")
    weeks: list[ProposedWeek] = []
    for index, value in enumerate(raw_weeks):
        raw_week = _object(
            value,
            path=f"proposal.weeks[{index}]",
            keys=_keys(_WEEK_SCHEMA),
        )
        raw_sections = raw_week["sections"]
        if not isinstance(raw_sections, list):
            raise ProposalParseError(
                f"proposal.weeks[{index}].sections must be an array"
            )
        sections = tuple(
            _section_value(
                section,
                path=f"proposal.weeks[{index}].sections[{section_index}]",
            )
            for section_index, section in enumerate(raw_sections)
        )
        _unique_section_keys(
            sections, path=f"proposal.weeks[{index}].sections"
        )
        weeks.append(
            ProposedWeek(
                week_id=_week_id(
                    raw_week["week_id"], path=f"proposal.weeks[{index}].week_id"
                ),
                sections=sections,
            )
        )
    if len({week.week_id for week in weeks}) != len(weeks):
        raise ProposalParseError("proposal.weeks contains duplicate week_id values")
    return MonthlyPlanProposal(
        target_month=_year_month(root["target_month"], path="target_month"),
        month_sections=month_sections,
        weeks=tuple(weeks),
    )


def parse_repair_patches(content: str) -> tuple[dict[str, Any], ...]:
    """The repair's {"patches": [...]} as raw cell patches.

    Only the shape is checked here: an address (week_id or null, section_key) and
    well-typed value / grounding_refs where present. Which patch may change what is
    validation.merge_repair_patches' decision, so an extra field reaches it intact.
    """
    root = _object(_json(content), path="repair", keys=frozenset({"patches"}))
    patches = root["patches"]
    if not isinstance(patches, list):
        raise ProposalParseError("repair.patches must be an array")
    for index, patch in enumerate(patches):
        path = f"repair.patches[{index}]"
        if not isinstance(patch, dict) or not {"week_id", "section_key"} <= set(patch):
            raise ProposalParseError(f"{path} must be an object with week_id and section_key")
        _string(patch["week_id"], path=f"{path}.week_id", nullable=True)
        _string(patch["section_key"], path=f"{path}.section_key")
        if "value" in patch and not isinstance(patch["value"], str):
            raise ProposalParseError(f"{path}.value must be a string")
        if "grounding_refs" in patch:
            patch["grounding_refs"] = list(_canonical_refs(patch["grounding_refs"], path=f"{path}.grounding_refs"))
    return tuple(patches)


def parse_monthly_cell_proposal(content: str) -> MonthlyCellProposal:
    root = _object(
        _json(content),
        path="cell_proposal",
        keys=_keys(CELL_RESPONSE_SCHEMA),
    )
    return MonthlyCellProposal(
        target_month=_year_month(root["target_month"], path="target_month"),
        target_week_id=(
            None
            if root["target_week_id"] is None
            else _week_id(root["target_week_id"], path="target_week_id")
        ),
        section=_section_value(root["section"], path="section"),
    )
