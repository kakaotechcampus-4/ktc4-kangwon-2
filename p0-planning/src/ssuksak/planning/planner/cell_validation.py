"""Deterministic validation for one-cell LLM proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from .contracts import (
    FOCUS_SECTION_KEY,
    MonthlyCellPlanningRequest,
    MonthlyCellProposal,
    ProposedActivityOrigin,
)
from .text_policy import normalize_visible_text, visible_text_violations


class CellViolationCode(str, Enum):
    PACKET_FINGERPRINT_MISMATCH = "PACKET_FINGERPRINT_MISMATCH"
    TARGET_MONTH_MISMATCH = "TARGET_MONTH_MISMATCH"
    TARGET_WEEK_MISMATCH = "TARGET_WEEK_MISMATCH"
    TARGET_SECTION_MISMATCH = "TARGET_SECTION_MISMATCH"
    FOCUS_ACTIVITY_METADATA = "FOCUS_ACTIVITY_METADATA"
    FOCUS_REQUIRES_GROUNDING = "FOCUS_REQUIRES_GROUNDING"
    OUTDOOR_REQUIRES_ORIGIN = "OUTDOOR_REQUIRES_ORIGIN"
    REFERENCE_REQUIRES_ID = "REFERENCE_REQUIRES_ID"
    UNKNOWN_REFERENCE_ID = "UNKNOWN_REFERENCE_ID"
    REFERENCE_VALUE_MISMATCH = "REFERENCE_VALUE_MISMATCH"
    SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE = "SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE"
    SYNTHESIZED_REQUIRES_GROUNDING = "SYNTHESIZED_REQUIRES_GROUNDING"
    UNKNOWN_GROUNDING_REF = "UNKNOWN_GROUNDING_REF"
    SOURCE_TEXT_COPY = "SOURCE_TEXT_COPY"
    TEXT_POLICY = "TEXT_POLICY"


@dataclass(frozen=True, slots=True)
class CellViolation:
    code: CellViolationCode
    field: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MonthlyCellValidationResult:
    violations: tuple[CellViolation, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(item.code.value for item in self.violations)


def validate_monthly_cell_proposal(
    proposal: MonthlyCellProposal,
    packet: MonthlyContextPacket,
    request: MonthlyCellPlanningRequest,
) -> MonthlyCellValidationResult:
    violations: list[CellViolation] = []

    def fail(code: CellViolationCode, field: str, detail: str = "") -> None:
        violations.append(CellViolation(code, field, detail))

    if request.packet_fingerprint != packet_fingerprint(packet):
        fail(CellViolationCode.PACKET_FINGERPRINT_MISMATCH, "packet_fingerprint")
        return MonthlyCellValidationResult(tuple(violations))
    if proposal.target_month != request.target_month:
        fail(CellViolationCode.TARGET_MONTH_MISMATCH, "target_month")
    if proposal.target_week_id != request.target_week_id:
        fail(CellViolationCode.TARGET_WEEK_MISMATCH, "target_week_id")
    if proposal.target_section_key != request.target_section_key:
        fail(CellViolationCode.TARGET_SECTION_MISMATCH, "target_section_key")
    for code in visible_text_violations(
        proposal.value, evidence_refs=request.valid_grounding_refs
    ):
        fail(CellViolationCode.TEXT_POLICY, "value", code)

    unknown = tuple(
        ref for ref in proposal.grounding_refs if ref not in request.valid_grounding_refs
    )
    if unknown:
        fail(CellViolationCode.UNKNOWN_GROUNDING_REF, "grounding_refs", repr(unknown))

    reference_labels = request.reference_label_map
    if request.target_section_key == FOCUS_SECTION_KEY:
        if proposal.activity_origin is not None or proposal.reference_activity_id is not None:
            fail(CellViolationCode.FOCUS_ACTIVITY_METADATA, "activity_origin")
        if not proposal.grounding_refs:
            fail(CellViolationCode.FOCUS_REQUIRES_GROUNDING, "grounding_refs")
    else:
        if proposal.activity_origin is None:
            fail(CellViolationCode.OUTDOOR_REQUIRES_ORIGIN, "activity_origin")
        elif proposal.activity_origin is ProposedActivityOrigin.REFERENCE:
            reference_id = proposal.reference_activity_id
            if reference_id is None:
                fail(CellViolationCode.REFERENCE_REQUIRES_ID, "reference_activity_id")
            elif reference_id not in reference_labels:
                fail(CellViolationCode.UNKNOWN_REFERENCE_ID, "reference_activity_id")
            elif normalize_visible_text(proposal.value) != normalize_visible_text(
                reference_labels[reference_id]
            ):
                fail(CellViolationCode.REFERENCE_VALUE_MISMATCH, "value")
        else:
            if proposal.reference_activity_id is not None:
                fail(
                    CellViolationCode.SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE,
                    "reference_activity_id",
                )
            if not proposal.grounding_refs:
                fail(CellViolationCode.SYNTHESIZED_REQUIRES_GROUNDING, "grounding_refs")

    evidence_texts = {
        normalize_visible_text(item.text)
        for item in (
            packet.institution_evidence
            + packet.age_contrast_evidence
            + packet.week_experience_candidates
            + packet.other_outdoor_evidence
        )
    }
    is_reference = proposal.activity_origin is ProposedActivityOrigin.REFERENCE
    if not is_reference and normalize_visible_text(proposal.value) in evidence_texts:
        fail(CellViolationCode.SOURCE_TEXT_COPY, "value")
    return MonthlyCellValidationResult(tuple(violations))
