"""Deterministic validation for one-cell LLM proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from .contracts import (
    MonthlyCellPlanningRequest,
    MonthlyCellProposal,
)
from .text_policy import normalize_visible_text, visible_text_violations
from .validation import outdoor_age_unverifiable_refs, wrong_source_refs


class CellValidationCode(str, Enum):
    PACKET_FINGERPRINT_MISMATCH = "PACKET_FINGERPRINT_MISMATCH"
    TARGET_MONTH_MISMATCH = "TARGET_MONTH_MISMATCH"
    TARGET_WEEK_MISMATCH = "TARGET_WEEK_MISMATCH"
    TARGET_SECTION_MISMATCH = "TARGET_SECTION_MISMATCH"
    UNRESOLVED_NOT_SUPPORTED = "UNRESOLVED_NOT_SUPPORTED"
    UNKNOWN_GROUNDING_REF = "UNKNOWN_GROUNDING_REF"
    WRONG_SOURCE_GROUNDING = "WRONG_SOURCE_GROUNDING"
    OUTDOOR_GROUNDING_AGE_MISMATCH = "OUTDOOR_GROUNDING_AGE_MISMATCH"
    RESOLVED_REQUIRES_GROUNDING = "RESOLVED_REQUIRES_GROUNDING"
    UNKNOWN_REFERENCE_ID = "UNKNOWN_REFERENCE_ID"
    REFERENCE_VALUE_MISMATCH = "REFERENCE_VALUE_MISMATCH"
    SOURCE_TEXT_COPY = "SOURCE_TEXT_COPY"
    TEXT_POLICY = "TEXT_POLICY"


@dataclass(frozen=True, slots=True)
class CellValidationIssue:
    code: CellValidationCode
    field: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MonthlyCellValidationResult:
    issues: tuple[CellValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(item.code.value for item in self.issues)


def validate_monthly_cell_proposal(
    proposal: MonthlyCellProposal,
    packet: MonthlyContextPacket,
    request: MonthlyCellPlanningRequest,
) -> MonthlyCellValidationResult:
    issues: list[CellValidationIssue] = []

    def fail(
        code: CellValidationCode, field: str, detail: str = ""
    ) -> None:
        issues.append(CellValidationIssue(code, field, detail))

    if request.packet_fingerprint != packet_fingerprint(packet):
        fail(
            CellValidationCode.PACKET_FINGERPRINT_MISMATCH,
            "packet_fingerprint",
        )
        return MonthlyCellValidationResult(tuple(issues))
    if proposal.target_month != request.target_month:
        fail(CellValidationCode.TARGET_MONTH_MISMATCH, "target_month")
    if proposal.target_week_id != request.target_week_id:
        fail(CellValidationCode.TARGET_WEEK_MISMATCH, "target_week_id")
    value = proposal.section
    if value.section_key != request.target_section_key:
        fail(CellValidationCode.TARGET_SECTION_MISMATCH, "section_key")
    if value.unresolved:
        fail(CellValidationCode.UNRESOLVED_NOT_SUPPORTED, "unresolved")
        return MonthlyCellValidationResult(tuple(issues))

    for code in visible_text_violations(
        value.value, evidence_refs=request.valid_grounding_refs
    ):
        fail(CellValidationCode.TEXT_POLICY, "value", code)
    unknown = tuple(
        ref for ref in value.grounding_refs if ref not in request.valid_grounding_refs
    )
    if unknown:
        fail(
            CellValidationCode.UNKNOWN_GROUNDING_REF,
            "grounding_refs",
            repr(unknown),
        )
    target_section = request.template_snapshot.section(request.target_section_key)
    if target_section is not None:
        wrong = wrong_source_refs(
            target_section,
            value.grounding_refs,
            {item.evidence_ref: item for item in packet.grounding_items},
        )
        if wrong:
            fail(
                CellValidationCode.WRONG_SOURCE_GROUNDING,
                "grounding_refs",
                repr(wrong),
            )
    unverifiable = outdoor_age_unverifiable_refs(
        request.target_section_key,
        value.grounding_refs,
        {item.evidence_ref: item for item in packet.grounding_items},
        packet.ages,
        set(packet.safety.official_by_ref) if packet.safety is not None else set(),
    )
    if unverifiable:
        fail(
            CellValidationCode.OUTDOOR_GROUNDING_AGE_MISMATCH,
            "grounding_refs",
            repr(tuple(ref for ref, _ in unverifiable)),
        )

    reference_labels = request.reference_label_map
    if value.reference_id is not None:
        expected = reference_labels.get(value.reference_id)
        if request.target_section_key not in request.reference_section_keys:
            # Same capability contract as the full-month proposal.
            fail(CellValidationCode.UNKNOWN_REFERENCE_ID, "reference_id", "REFERENCE_FORBIDDEN_FOR_SECTION")
        elif expected is None:
            fail(CellValidationCode.UNKNOWN_REFERENCE_ID, "reference_id")
        elif normalize_visible_text(value.value) != normalize_visible_text(expected):
            fail(CellValidationCode.REFERENCE_VALUE_MISMATCH, "value")
    elif not value.grounding_refs:
        fail(
            CellValidationCode.RESOLVED_REQUIRES_GROUNDING,
            "grounding_refs",
        )

    evidence_texts = {
        normalize_visible_text(item.text) for item in packet.grounding_items
    }
    if (
        value.reference_id is None
        and normalize_visible_text(value.value) in evidence_texts
    ):
        fail(CellValidationCode.SOURCE_TEXT_COPY, "value")
    return MonthlyCellValidationResult(tuple(issues))
