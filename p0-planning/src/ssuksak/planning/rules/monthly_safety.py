"""Deterministic safety-reference assessment without inventing placement."""

from __future__ import annotations

from ..domain.monthly_constraint import (
    SAFETY_EDUCATION_CONSTRAINT,
    ConstraintAssessment,
    ConstraintVerification,
)
from ..domain.safety_rule import SafetyLegalRule
from .errors import MonthlyRuleError

RULE_ID = "monthly.safety.source_and_placement_assessment"
RULE_VERSION = "v1"
REQUIRED_SOURCE_KINDS = ("INSTITUTION_SAFETY_PLAN", "TEACHER_INPUT")


def assess_safety_education(
    rule: SafetyLegalRule, *, safety_section_active: bool, has_placement_source: bool
) -> ConstraintAssessment:
    if not isinstance(rule, SafetyLegalRule) or not rule.is_active:
        raise MonthlyRuleError(RULE_ID, "Safety Reference must be HUMAN_APPROVED")
    if type(safety_section_active) is not bool or type(has_placement_source) is not bool:
        raise MonthlyRuleError(RULE_ID, "safety flags must be boolean")
    if not safety_section_active:
        return ConstraintAssessment(
            SAFETY_EDUCATION_CONSTRAINT,
            ConstraintVerification.NOT_APPLICABLE,
            RULE_VERSION,
        )
    if has_placement_source:
        return ConstraintAssessment(
            SAFETY_EDUCATION_CONSTRAINT,
            ConstraintVerification.VERIFIED,
            RULE_VERSION,
            affected_section_keys=("safety_education",),
            detail="A placement source is available; legal compliance is not implied.",
        )
    return ConstraintAssessment(
        SAFETY_EDUCATION_CONSTRAINT,
        ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED,
        RULE_VERSION,
        required_source_kinds=REQUIRED_SOURCE_KINDS,
        affected_section_keys=("safety_education",),
        detail="The legal reference contains no deterministic monthly placement.",
    )
