"""Strict JSON parsers for provider output."""

from __future__ import annotations

import json
from typing import Any

from ..domain.errors import InvalidDomainValueError
from .contracts import (
    MonthlyCellProposal,
    MonthlyPlanProposal,
    ProposalParseError,
    ProposedActivity,
    ProposedActivityOrigin,
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


def _origin(value: object, *, nullable: bool = False) -> ProposedActivityOrigin | None:
    if nullable and value is None:
        return None
    try:
        return ProposedActivityOrigin(value)
    except (TypeError, ValueError) as exc:
        raise ProposalParseError(f"invalid activity origin: {value!r}") from exc


def parse_monthly_proposal(content: str) -> MonthlyPlanProposal:
    root = _object(
        _json(content),
        path="proposal",
        keys=frozenset({"target_month", "theme_id", "month_flow_rationale", "weeks"}),
    )
    raw_weeks = root["weeks"]
    if not isinstance(raw_weeks, list) or not raw_weeks:
        raise ProposalParseError("proposal.weeks must be a non-empty array")
    weeks: list[ProposedWeek] = []
    for index, raw_week in enumerate(raw_weeks):
        week = _object(
            raw_week,
            path=f"proposal.weeks[{index}]",
            keys=frozenset({"week_id", "experience", "activity"}),
        )
        activity = _object(
            week["activity"],
            path=f"proposal.weeks[{index}].activity",
            keys=frozenset(
                {"value", "origin", "reference_activity_id", "grounding_refs"}
            ),
        )
        try:
            weeks.append(
                ProposedWeek(
                    week_id=_string(week["week_id"], path="week_id"),
                    experience=_string(week["experience"], path="experience"),
                    activity=ProposedActivity(
                        value=_string(activity["value"], path="activity.value"),
                        origin=_origin(activity["origin"]),
                        reference_activity_id=_string(
                            activity["reference_activity_id"],
                            path="activity.reference_activity_id",
                            nullable=True,
                        ),
                        grounding_refs=_strings(
                            activity["grounding_refs"], path="activity.grounding_refs"
                        ),
                    ),
                )
            )
        except InvalidDomainValueError as exc:
            raise ProposalParseError(str(exc)) from exc
    try:
        return MonthlyPlanProposal(
            target_month=_string(root["target_month"], path="target_month"),
            theme_id=_string(root["theme_id"], path="theme_id"),
            month_flow_rationale=_string(
                root["month_flow_rationale"], path="month_flow_rationale"
            ),
            weeks=tuple(weeks),
        )
    except InvalidDomainValueError as exc:
        raise ProposalParseError(str(exc)) from exc


def parse_monthly_cell_proposal(content: str) -> MonthlyCellProposal:
    root = _object(
        _json(content),
        path="cell_proposal",
        keys=frozenset(
            {
                "target_month",
                "target_week_id",
                "target_section_key",
                "value",
                "activity_origin",
                "reference_activity_id",
                "grounding_refs",
            }
        ),
    )
    try:
        return MonthlyCellProposal(
            target_month=_string(root["target_month"], path="target_month"),
            target_week_id=_string(root["target_week_id"], path="target_week_id"),
            target_section_key=_string(
                root["target_section_key"], path="target_section_key"
            ),
            value=_string(root["value"], path="value"),
            activity_origin=_origin(root["activity_origin"], nullable=True),
            reference_activity_id=_string(
                root["reference_activity_id"],
                path="reference_activity_id",
                nullable=True,
            ),
            grounding_refs=_strings(root["grounding_refs"], path="grounding_refs"),
        )
    except InvalidDomainValueError as exc:
        raise ProposalParseError(str(exc)) from exc
