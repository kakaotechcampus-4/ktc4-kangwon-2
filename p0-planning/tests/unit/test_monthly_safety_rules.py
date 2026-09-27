from dataclasses import replace

import pytest

from ssuksak.adapters.monthly_reference_repositories import JsonSafetyLegalRuleRepository
from ssuksak.planning.domain.monthly_constraint import CellState, ConstraintVerification
from ssuksak.planning.rules.errors import MonthlyRuleError
from ssuksak.planning.rules.monthly_cell_state import resolve_cell_state
from ssuksak.planning.rules.monthly_safety import assess_safety_education


def _rule():
    return JsonSafetyLegalRuleRepository().get_legal_rule(
        "child-welfare-act-decree-annex6-2022-06-21"
    )


def test_missing_placement_source_is_unresolved_not_invented():
    assessment = assess_safety_education(
        _rule(), safety_section_active=True, has_placement_source=False
    )

    assert assessment.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    assert assessment.required_source_kinds == ("INSTITUTION_SAFETY_PLAN", "TEACHER_INPUT")
    assert resolve_cell_state(
        section_key="safety_education", value="", assessment=assessment
    ) is CellState.EMPTY_UNRESOLVED


def test_source_presence_does_not_claim_legal_confirmation():
    assessment = assess_safety_education(
        _rule(), safety_section_active=True, has_placement_source=True
    )
    assert assessment.verification is ConstraintVerification.VERIFIED
    assert "not implied" in assessment.detail


def test_inactive_safety_section_is_not_applicable():
    assessment = assess_safety_education(
        _rule(), safety_section_active=False, has_placement_source=False
    )
    assert assessment.verification is ConstraintVerification.NOT_APPLICABLE


def test_unapproved_safety_reference_is_rejected():
    with pytest.raises(MonthlyRuleError):
        assess_safety_education(
            replace(_rule(), runtime_active=False),
            safety_section_active=True,
            has_placement_source=False,
        )


def test_cell_state_keeps_optional_blank_valid_and_theme_required():
    assert resolve_cell_state(section_key="outdoor_play", value="") is CellState.EMPTY_VALID
    assert resolve_cell_state(section_key="outdoor_play", value="놀이") is CellState.FILLED
    with pytest.raises(MonthlyRuleError, match="theme"):
        resolve_cell_state(section_key="theme", value="")
