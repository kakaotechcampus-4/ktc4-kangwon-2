"""Deterministic validation for full-month LLM proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from .contracts import (
    MonthlyPlanProposal,
    MonthlyPlanningRequest,
    ProposedActivityOrigin,
)
from .text_policy import (
    MAX_RATIONALE_CHARS,
    normalize_visible_text,
    visible_text_violations,
)


class ProposalViolationCode(str, Enum):
    PACKET_FINGERPRINT_MISMATCH = "PACKET_FINGERPRINT_MISMATCH"
    TARGET_MONTH_MISMATCH = "TARGET_MONTH_MISMATCH"
    THEME_ID_MISMATCH = "THEME_ID_MISMATCH"
    WEEK_STRUCTURE_MISMATCH = "WEEK_STRUCTURE_MISMATCH"
    UNKNOWN_GROUNDING_REF = "UNKNOWN_GROUNDING_REF"
    REFERENCE_REQUIRES_ID = "REFERENCE_REQUIRES_ID"
    UNKNOWN_REFERENCE_ID = "UNKNOWN_REFERENCE_ID"
    REFERENCE_VALUE_MISMATCH = "REFERENCE_VALUE_MISMATCH"
    SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE = "SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE"
    SYNTHESIZED_REQUIRES_GROUNDING = "SYNTHESIZED_REQUIRES_GROUNDING"
    SOURCE_TEXT_COPY = "SOURCE_TEXT_COPY"
    DUPLICATE_EXPERIENCE = "DUPLICATE_EXPERIENCE"
    DUPLICATE_ACTIVITY = "DUPLICATE_ACTIVITY"
    TEXT_POLICY = "TEXT_POLICY"


@dataclass(frozen=True, slots=True)
class ProposalViolation:
    code: ProposalViolationCode
    field: str
    detail: str = ""
    week_id: str | None = None


@dataclass(frozen=True, slots=True)
class MonthlyProposalValidationResult:
    violations: tuple[ProposalViolation, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(item.code.value for item in self.violations)


def _evidence_texts(packet: MonthlyContextPacket) -> frozenset[str]:
    items = (
        packet.institution_evidence
        + packet.age_contrast_evidence
        + packet.week_experience_candidates
        + packet.other_outdoor_evidence
    )
    return frozenset(normalize_visible_text(item.text) for item in items)


def validate_monthly_proposal(
    proposal: MonthlyPlanProposal,
    packet: MonthlyContextPacket,
    request: MonthlyPlanningRequest,
) -> MonthlyProposalValidationResult:
    violations: list[ProposalViolation] = []

    def fail(
        code: ProposalViolationCode,
        field: str,
        detail: str = "",
        week_id: str | None = None,
    ) -> None:
        violations.append(ProposalViolation(code, field, detail, week_id))

    if request.packet_fingerprint != packet_fingerprint(packet):
        fail(
            ProposalViolationCode.PACKET_FINGERPRINT_MISMATCH,
            "packet_fingerprint",
        )
        return MonthlyProposalValidationResult(tuple(violations))
    if proposal.target_month != request.target_month:
        fail(ProposalViolationCode.TARGET_MONTH_MISMATCH, "target_month")
    if proposal.theme_id != request.expected_theme_id:
        fail(ProposalViolationCode.THEME_ID_MISMATCH, "theme_id")

    actual_weeks = tuple(item.week_id for item in proposal.weeks)
    if actual_weeks != request.expected_week_ids:
        fail(
            ProposalViolationCode.WEEK_STRUCTURE_MISMATCH,
            "weeks",
            f"expected={request.expected_week_ids!r}, actual={actual_weeks!r}",
        )

    for code in visible_text_violations(
        proposal.month_flow_rationale,
        max_chars=MAX_RATIONALE_CHARS,
        evidence_refs=request.valid_grounding_refs,
    ):
        fail(ProposalViolationCode.TEXT_POLICY, "month_flow_rationale", code)

    evidence_texts = _evidence_texts(packet)
    reference_labels = request.reference_label_map
    normalized_experiences: list[str] = []
    normalized_activities: list[str] = []
    for week in proposal.weeks:
        for field_name, text in (
            ("experience", week.experience),
            ("activity.value", week.activity.value),
        ):
            for code in visible_text_violations(
                text, evidence_refs=request.valid_grounding_refs
            ):
                fail(ProposalViolationCode.TEXT_POLICY, field_name, code, week.week_id)
        experience = normalize_visible_text(week.experience)
        activity_value = normalize_visible_text(week.activity.value)
        normalized_experiences.append(experience)
        normalized_activities.append(activity_value)
        if experience in evidence_texts:
            fail(
                ProposalViolationCode.SOURCE_TEXT_COPY,
                "experience",
                week_id=week.week_id,
            )

        unknown = tuple(
            ref
            for ref in week.activity.grounding_refs
            if ref not in request.valid_grounding_refs
        )
        if unknown:
            fail(
                ProposalViolationCode.UNKNOWN_GROUNDING_REF,
                "activity.grounding_refs",
                repr(unknown),
                week.week_id,
            )

        if week.activity.origin is ProposedActivityOrigin.REFERENCE:
            reference_id = week.activity.reference_activity_id
            if reference_id is None:
                fail(
                    ProposalViolationCode.REFERENCE_REQUIRES_ID,
                    "activity.reference_activity_id",
                    week_id=week.week_id,
                )
            elif reference_id not in reference_labels:
                fail(
                    ProposalViolationCode.UNKNOWN_REFERENCE_ID,
                    "activity.reference_activity_id",
                    week_id=week.week_id,
                )
            elif activity_value != normalize_visible_text(reference_labels[reference_id]):
                fail(
                    ProposalViolationCode.REFERENCE_VALUE_MISMATCH,
                    "activity.value",
                    week_id=week.week_id,
                )
        else:
            if week.activity.reference_activity_id is not None:
                fail(
                    ProposalViolationCode.SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE,
                    "activity.reference_activity_id",
                    week_id=week.week_id,
                )
            if not week.activity.grounding_refs:
                fail(
                    ProposalViolationCode.SYNTHESIZED_REQUIRES_GROUNDING,
                    "activity.grounding_refs",
                    week_id=week.week_id,
                )
            if activity_value in evidence_texts:
                fail(
                    ProposalViolationCode.SOURCE_TEXT_COPY,
                    "activity.value",
                    week_id=week.week_id,
                )

    if len(normalized_experiences) != len(set(normalized_experiences)):
        fail(ProposalViolationCode.DUPLICATE_EXPERIENCE, "weeks.experience")
    if len(normalized_activities) != len(set(normalized_activities)):
        fail(ProposalViolationCode.DUPLICATE_ACTIVITY, "weeks.activity.value")
    return MonthlyProposalValidationResult(tuple(violations))
