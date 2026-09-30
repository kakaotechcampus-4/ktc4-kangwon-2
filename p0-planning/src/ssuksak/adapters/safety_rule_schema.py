"""Boundary validation for the approved six-category Safety Reference."""

from __future__ import annotations

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.domain.safety_rule import SafetyCategory, SafetyLegalRule


class SafetyLegalRuleSchemaError(ValueError):
    pass


def parse_safety_rule_payload(payload: object) -> SafetyLegalRule:
    if not isinstance(payload, dict):
        raise SafetyLegalRuleSchemaError("safety rule must be an object")
    try:
        review = payload["review"]
        scope = payload["applicable_scope"]
        month_policy = payload["month_assignment_policy"]
        categories = payload["categories"]
        if not isinstance(review, dict) or not isinstance(scope, dict) or not isinstance(month_policy, dict):
            raise SafetyLegalRuleSchemaError("safety metadata objects are required")
        if month_policy.get("has_month_assignment") is not False:
            raise SafetyLegalRuleSchemaError("the legal Reference must not assign months")
        if payload.get("placement_policy_version") is not None:
            raise SafetyLegalRuleSchemaError("P0 must not declare a safety placement policy")
        approval = review.get("domain_owner_approval")
        active = review.get("runtime_active")
        if type(active) is not bool or active != (approval == "HUMAN_APPROVED"):
            raise SafetyLegalRuleSchemaError("runtime_active must be derived from approval")
        if not isinstance(categories, list):
            raise SafetyLegalRuleSchemaError("categories must be an array")
        domain_categories = []
        for index, raw in enumerate(categories):
            if not isinstance(raw, dict):
                raise SafetyLegalRuleSchemaError(f"categories[{index}] must be an object")
            forbidden = {"month", "months", "month_assignment", "assigned_month", "placement", "week"}
            if any(key.lower() in forbidden for key in raw):
                raise SafetyLegalRuleSchemaError("safety categories cannot contain placement fields")
            domain_categories.append(
                SafetyCategory(
                    category_id=raw["category_id"],
                    official_label=raw["official_label"],
                    interval_months=raw["interval_months"],
                    annual_hours_min=raw["annual_hours_min"],
                    content_items=tuple(raw["content_items_verbatim"]),
                )
            )
        return SafetyLegalRule(
            legal_rule_version=payload["legal_rule_version"],
            normative_status=payload["normative_status"],
            categories=tuple(domain_categories),
            age_tier_label=scope["age_tier_label_verbatim"],
            placement_policy_version=None,
            runtime_active=active,
        )
    except (KeyError, InvalidDomainValueError, TypeError, ValueError) as exc:
        if isinstance(exc, SafetyLegalRuleSchemaError):
            raise
        raise SafetyLegalRuleSchemaError(f"Safety Reference violates the contract: {exc}") from exc
