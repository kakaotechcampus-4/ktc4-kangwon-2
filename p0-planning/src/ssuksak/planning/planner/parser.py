"""Strict JSON parsers for provider output."""

from __future__ import annotations

import json
from typing import Any

from ..domain.errors import InvalidDomainValueError
from ..domain.week_period import WeekId
from ..domain.year_month import YearMonth
from .contracts import (
    MonthlyCellProposal,
    MonthlyPlanProposal,
    ProposalParseError,
    ProposedSectionValue,
    ProposedWeek,
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


def _section_value(value: object, *, path: str) -> ProposedSectionValue:
    item = _object(
        value,
        path=path,
        keys=frozenset(
            {
                "section_key",
                "value",
                "unresolved",
                "reference_id",
                "grounding_refs",
            }
        ),
    )
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
            grounding_refs=_strings(
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
        keys=frozenset({"target_month", "month_sections", "weeks"}),
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
            keys=frozenset({"week_id", "sections"}),
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
        keys=frozenset({"target_month", "target_week_id", "section"}),
    )
    return MonthlyCellProposal(
        target_month=_year_month(root["target_month"], path="target_month"),
        target_week_id=_week_id(root["target_week_id"], path="target_week_id"),
        section=_section_value(root["section"], path="section"),
    )
