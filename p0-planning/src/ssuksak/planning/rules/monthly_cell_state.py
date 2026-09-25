"""Resolve empty/filled Monthly Cell state from deterministic structure."""

from __future__ import annotations

from ..domain.monthly_constraint import CellState, ConstraintAssessment
from .errors import MonthlyRuleError

RULE_ID = "monthly.cell.structural_state"


def resolve_cell_state(
    *, section_key: str, value: str, assessment: ConstraintAssessment | None = None
) -> CellState:
    if not isinstance(section_key, str) or not section_key.strip():
        raise MonthlyRuleError(RULE_ID, "section_key must be non-blank")
    if not isinstance(value, str):
        raise MonthlyRuleError(RULE_ID, "value must be a string")
    if value.strip():
        return CellState.FILLED
    if section_key == "theme":
        raise MonthlyRuleError(RULE_ID, "theme cannot be empty")
    if assessment is not None and assessment.is_unresolved:
        if section_key in assessment.affected_section_keys:
            return CellState.EMPTY_UNRESOLVED
    return CellState.EMPTY_VALID
