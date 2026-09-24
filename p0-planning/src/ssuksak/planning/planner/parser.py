"""Strict JSON parsers for provider output."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..domain.errors import InvalidDomainValueError
from ..domain.week_period import WeekId
from ..domain.year_month import YearMonth
from ..domain.monthly_template import DisplayMode
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


def _section_branch(section_key: str, refs: tuple[str, ...]) -> dict[str, Any]:
    """The static Section schema for one section_key and only the refs it may cite."""
    properties = dict(_SECTION_SCHEMA["properties"])
    properties["section_key"] = {"type": "string", "enum": [section_key]}
    properties["grounding_refs"] = (
        {"type": "array", "items": {"type": "string", "enum": list(refs)}}
        if refs
        # No allowed ref: only an empty list, never the Packet-wide refs.
        else {"type": "array", "items": _STRING, "maxItems": 0}
    )
    return _object_schema(properties)


def _section_schema(section_keys: set[str], request) -> dict[str, Any]:
    """One branch per target Section; the parser and validator stay the final check."""
    allowed = dict(request.allowed_grounding_refs_by_section)
    branches = [_section_branch(key, allowed.get(key, ())) for key in sorted(section_keys)]
    return branches[0] if len(branches) == 1 else {"anyOf": branches}


def monthly_response_schema(request: MonthlyPlanningRequest) -> dict[str, Any]:
    """MONTHLY_RESPONSE_SCHEMA scoped to the request's target Sections and their allowed refs."""
    targets = generation_target_sections(request.template_snapshot)
    month = _section_schema(
        {s.section_key for s in targets if s.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY}, request
    )
    week = _section_schema(
        {s.section_key for s in targets if s.display_mode is DisplayMode.WEEKLY_CELLS}, request
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
            "section": _section_schema({request.target_section_key}, request),
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
