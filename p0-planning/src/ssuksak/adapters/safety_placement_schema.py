"""Boundary validation for the versioned safety Placement Policy artifact."""

from __future__ import annotations

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.domain.safety_placement import (
    PRODUCT_POLICY,
    SafetyPlacementEntry,
    SafetyPlacementPolicy,
)


class SafetyPlacementPolicySchemaError(ValueError):
    pass


def parse_safety_placement_payload(payload: object) -> SafetyPlacementPolicy:
    if not isinstance(payload, dict):
        raise SafetyPlacementPolicySchemaError("placement policy must be an object")
    try:
        if payload["normative_status"] != PRODUCT_POLICY:
            raise SafetyPlacementPolicySchemaError(
                f"a placement policy is a {PRODUCT_POLICY}, never statutory"
            )
        review = payload["review"]
        if not isinstance(review, dict):
            raise SafetyPlacementPolicySchemaError("review must be an object")
        active = review.get("runtime_active")
        if type(active) is not bool or active != (
            review.get("domain_owner_approval") == "HUMAN_APPROVED"
        ):
            raise SafetyPlacementPolicySchemaError("runtime_active must be derived from approval")
        placements = payload["placements"]
        if not isinstance(placements, list):
            raise SafetyPlacementPolicySchemaError("placements must be an array")
        entries = []
        for index, raw in enumerate(placements):
            if not isinstance(raw, dict) or set(raw) != {"month", "category_id", "week_ordinal"}:
                raise SafetyPlacementPolicySchemaError(
                    f"placements[{index}] must hold exactly month, category_id, week_ordinal"
                )
            entries.append(SafetyPlacementEntry(raw["month"], raw["category_id"], raw["week_ordinal"]))
        focus = payload.get("focus_rule")
        if focus is not None and (not isinstance(focus, dict) or not {"kind", "base_school_year"} <= set(focus)):
            raise SafetyPlacementPolicySchemaError("focus_rule must name kind and base_school_year")
        return SafetyPlacementPolicy(
            policy_id=payload["policy_id"],
            policy_version=payload["policy_version"],
            legal_rule_version=payload["legal_rule_version"],
            entries=tuple(entries),
            runtime_active=active,
            focus_rule=None if focus is None else focus["kind"],
            base_school_year=None if focus is None else focus["base_school_year"],
            school_year_start_month=payload.get("school_year_start_month", 3),
        )
    except (KeyError, InvalidDomainValueError, TypeError) as exc:
        raise SafetyPlacementPolicySchemaError(
            f"Safety Placement Policy violates the contract: {exc}"
        ) from exc
