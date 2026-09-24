"""Deterministic validation for full-month LLM proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..context.models import GroundingContextItem, MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from ..domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    SectionRole,
    TemplateSection,
)
from ..domain.monthly_template_profile import INSTITUTION_INPUT_SECTION_KEYS
from ..evidence.classification import CLASS_SCOPED_SECTION_KEYS, grounding_class_for
from ..evidence.models import SourceSection
from .contracts import (
    MonthlyPlanProposal,
    MonthlyPlanningRequest,
    ProposedSectionValue,
)
from .text_policy import normalize_visible_text, visible_text_violations


class ProposalValidationCode(str, Enum):
    PACKET_FINGERPRINT_MISMATCH = "PACKET_FINGERPRINT_MISMATCH"
    TARGET_MONTH_MISMATCH = "TARGET_MONTH_MISMATCH"
    WEEK_STRUCTURE_MISMATCH = "WEEK_STRUCTURE_MISMATCH"
    DUPLICATE_SECTION = "DUPLICATE_SECTION"
    UNKNOWN_SECTION = "UNKNOWN_SECTION"
    AXIS_CONTENT = "AXIS_CONTENT"
    INSTITUTION_INPUT_SECTION = "INSTITUTION_INPUT_SECTION"
    SECTION_PLACEMENT_MISMATCH = "SECTION_PLACEMENT_MISMATCH"
    REQUIRED_SECTION_MISSING = "REQUIRED_SECTION_MISSING"
    UNRESOLVED_NOT_ALLOWED = "UNRESOLVED_NOT_ALLOWED"
    UNKNOWN_GROUNDING_REF = "UNKNOWN_GROUNDING_REF"
    WRONG_SOURCE_GROUNDING = "WRONG_SOURCE_GROUNDING"
    RESOLVED_REQUIRES_GROUNDING = "RESOLVED_REQUIRES_GROUNDING"
    UNKNOWN_REFERENCE_ID = "UNKNOWN_REFERENCE_ID"
    REFERENCE_VALUE_MISMATCH = "REFERENCE_VALUE_MISMATCH"
    THEME_REFERENCE_MISMATCH = "THEME_REFERENCE_MISMATCH"
    THEME_VALUE_MISMATCH = "THEME_VALUE_MISMATCH"
    SAFETY_GROUNDING_REQUIRED = "SAFETY_GROUNDING_REQUIRED"
    SOURCE_TEXT_COPY = "SOURCE_TEXT_COPY"
    TEXT_POLICY = "TEXT_POLICY"


@dataclass(frozen=True, slots=True)
class ProposalValidationIssue:
    code: ProposalValidationCode
    field: str
    detail: str = ""
    week_id: str | None = None


@dataclass(frozen=True, slots=True)
class MonthlyProposalValidationResult:
    issues: tuple[ProposalValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(item.code.value for item in self.issues)


def is_safety_grounding(item: GroundingContextItem) -> bool:
    """Evidence that SAFETY_GROUNDING_REQUIRED accepts for a resolved safety_education value."""
    return item.source_section is SourceSection.SAFETY_EDUCATION


def wrong_source_refs(
    section: TemplateSection,
    refs: tuple[str, ...],
    evidence_by_ref: dict[str, GroundingContextItem],
) -> tuple[str, ...]:
    """Refs whose approved grounding_class does not belong to this Section."""
    expected = grounding_class_for(section)
    scoped = section.section_key in CLASS_SCOPED_SECTION_KEYS
    wrong = []
    for ref in refs:
        item = evidence_by_ref.get(ref)
        if item is None:
            continue
        if scoped:
            if expected is None or item.grounding_class is not expected:
                wrong.append(ref)
        elif item.grounding_class is not None:
            wrong.append(ref)
    return tuple(wrong)


def _canonical_values(
    proposal: MonthlyPlanProposal,
) -> tuple[tuple[ProposedSectionValue, str | None], ...]:
    return tuple((value, None) for value in proposal.month_sections) + tuple(
        (value, week.week_id.value)
        for week in proposal.weeks
        for value in week.sections
    )


def validate_monthly_proposal_schema(
    proposal: MonthlyPlanProposal,
    request: MonthlyPlanningRequest,
) -> MonthlyProposalValidationResult:
    issues: list[ProposalValidationIssue] = []

    def fail(
        code: ProposalValidationCode,
        field: str,
        detail: str = "",
        week_id: str | None = None,
    ) -> None:
        issues.append(ProposalValidationIssue(code, field, detail, week_id))

    if proposal.target_month != request.target_month:
        fail(ProposalValidationCode.TARGET_MONTH_MISMATCH, "target_month")
    actual_weeks = tuple(week.week_id for week in proposal.weeks)
    if actual_weeks != request.expected_week_ids:
        fail(
            ProposalValidationCode.WEEK_STRUCTURE_MISMATCH,
            "weeks",
            f"expected={request.expected_week_ids!r}, actual={actual_weeks!r}",
        )

    snapshot = request.template_snapshot
    snapshot_sections = {section.section_key: section for section in snapshot.sections}
    month_keys = tuple(value.section_key for value in proposal.month_sections)
    if len(set(month_keys)) != len(month_keys):
        fail(ProposalValidationCode.DUPLICATE_SECTION, "month_sections")

    for value in proposal.month_sections:
        section = snapshot_sections.get(value.section_key)
        if section is None:
            fail(
                ProposalValidationCode.UNKNOWN_SECTION,
                value.section_key,
            )
        elif section.role is SectionRole.AXIS:
            fail(ProposalValidationCode.AXIS_CONTENT, value.section_key)
        elif value.section_key in INSTITUTION_INPUT_SECTION_KEYS:
            fail(ProposalValidationCode.INSTITUTION_INPUT_SECTION, value.section_key)
        elif section.display_mode is not DisplayMode.MONTHLY_MERGED_SUMMARY:
            fail(
                ProposalValidationCode.SECTION_PLACEMENT_MISMATCH,
                value.section_key,
            )

    for week in proposal.weeks:
        keys = tuple(value.section_key for value in week.sections)
        if len(set(keys)) != len(keys):
            fail(
                ProposalValidationCode.DUPLICATE_SECTION,
                "weeks.sections",
                week_id=week.week_id.value,
            )
        for value in week.sections:
            section = snapshot_sections.get(value.section_key)
            if section is None:
                fail(
                    ProposalValidationCode.UNKNOWN_SECTION,
                    value.section_key,
                    week_id=week.week_id.value,
                )
            elif section.role is SectionRole.AXIS:
                fail(
                    ProposalValidationCode.AXIS_CONTENT,
                    value.section_key,
                    week_id=week.week_id.value,
                )
            elif value.section_key in INSTITUTION_INPUT_SECTION_KEYS:
                fail(
                    ProposalValidationCode.INSTITUTION_INPUT_SECTION,
                    value.section_key,
                    week_id=week.week_id.value,
                )
            elif section.display_mode is not DisplayMode.WEEKLY_CELLS:
                fail(
                    ProposalValidationCode.SECTION_PLACEMENT_MISMATCH,
                    value.section_key,
                    week_id=week.week_id.value,
                )

    required_month = {
        section.section_key
        for section in snapshot.sections
        if section.role is SectionRole.CONTENT
        and section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
        and section.required_for_generation
    }
    missing_month = required_month - set(month_keys)
    for key in sorted(missing_month):
        fail(ProposalValidationCode.REQUIRED_SECTION_MISSING, key)

    # Without approved safety grounding safety_education is not an LLM target;
    # the Core safety assessment builds its EMPTY_UNRESOLVED cells instead.
    targets = {key for key, _ in request.allowed_grounding_refs_by_section}
    required_weekly = {
        section.section_key
        for section in snapshot.sections
        if section.role is SectionRole.CONTENT
        and section.display_mode is DisplayMode.WEEKLY_CELLS
        and section.required_for_generation
        and (section.section_key != "safety_education" or section.section_key in targets)
    }
    for week in proposal.weeks:
        missing = required_weekly - {value.section_key for value in week.sections}
        for key in sorted(missing):
            fail(
                ProposalValidationCode.REQUIRED_SECTION_MISSING,
                key,
                week_id=week.week_id.value,
            )
    return MonthlyProposalValidationResult(tuple(issues))


def validate_monthly_proposal_grounding(
    proposal: MonthlyPlanProposal,
    packet: MonthlyContextPacket,
    request: MonthlyPlanningRequest,
) -> MonthlyProposalValidationResult:
    issues: list[ProposalValidationIssue] = []

    def fail(
        code: ProposalValidationCode,
        field: str,
        detail: str = "",
        week_id: str | None = None,
    ) -> None:
        issues.append(ProposalValidationIssue(code, field, detail, week_id))

    if request.packet_fingerprint != packet_fingerprint(packet):
        fail(
            ProposalValidationCode.PACKET_FINGERPRINT_MISMATCH,
            "packet_fingerprint",
        )
        return MonthlyProposalValidationResult(tuple(issues))

    evidence_items = packet.grounding_items
    evidence_by_ref = {item.evidence_ref: item for item in evidence_items}
    evidence_texts = {
        normalize_visible_text(item.text) for item in evidence_items
    }
    reference_labels = request.reference_label_map
    snapshot_sections = {
        section.section_key: section for section in request.template_snapshot.sections
    }

    for value, week_id in _canonical_values(proposal):
        section = snapshot_sections.get(value.section_key)
        if section is None or section.role is SectionRole.AXIS:
            continue
        if value.unresolved:
            if (
                value.section_key != "safety_education"
                or section.empty_value_policy
                is not EmptyValuePolicy.RENDER_EMPTY_CELL
            ):
                fail(
                    ProposalValidationCode.UNRESOLVED_NOT_ALLOWED,
                    value.section_key,
                    week_id=week_id,
                )
            continue

        safety_grounded = value.section_key == "safety_education" and bool(
            value.grounding_refs
        ) and all(
            evidence_by_ref.get(ref) is not None
            and is_safety_grounding(evidence_by_ref[ref])
            for ref in value.grounding_refs
        )
        for code in visible_text_violations(
            value.value, evidence_refs=request.valid_grounding_refs
        ):
            if code == "SAFETY_CONTENT_LEAKAGE" and safety_grounded:
                continue
            fail(
                ProposalValidationCode.TEXT_POLICY,
                value.section_key,
                code,
                week_id,
            )
        unknown = tuple(
            ref for ref in value.grounding_refs if ref not in evidence_by_ref
        )
        if unknown:
            fail(
                ProposalValidationCode.UNKNOWN_GROUNDING_REF,
                value.section_key,
                repr(unknown),
                week_id,
            )
        wrong = wrong_source_refs(section, value.grounding_refs, evidence_by_ref)
        if wrong:
            fail(
                ProposalValidationCode.WRONG_SOURCE_GROUNDING,
                value.section_key,
                repr(wrong),
                week_id,
            )

        if value.section_key == "theme":
            if value.reference_id != request.expected_theme_id:
                fail(
                    ProposalValidationCode.THEME_REFERENCE_MISMATCH,
                    value.section_key,
                )
            if normalize_visible_text(value.value) != normalize_visible_text(
                request.expected_theme_value
            ):
                fail(
                    ProposalValidationCode.THEME_VALUE_MISMATCH,
                    value.section_key,
                )
            continue

        if value.reference_id is not None:
            expected = reference_labels.get(value.reference_id)
            if expected is None:
                fail(
                    ProposalValidationCode.UNKNOWN_REFERENCE_ID,
                    value.section_key,
                    week_id=week_id,
                )
            elif normalize_visible_text(value.value) != normalize_visible_text(expected):
                fail(
                    ProposalValidationCode.REFERENCE_VALUE_MISMATCH,
                    value.section_key,
                    week_id=week_id,
                )
        elif not value.grounding_refs:
            fail(
                ProposalValidationCode.RESOLVED_REQUIRES_GROUNDING,
                value.section_key,
                week_id=week_id,
            )

        if value.section_key == "safety_education" and not safety_grounded:
            fail(
                ProposalValidationCode.SAFETY_GROUNDING_REQUIRED,
                value.section_key,
                week_id=week_id,
            )
        if (
            value.reference_id is None
            and normalize_visible_text(value.value) in evidence_texts
        ):
            fail(
                ProposalValidationCode.SOURCE_TEXT_COPY,
                value.section_key,
                week_id=week_id,
            )
    return MonthlyProposalValidationResult(tuple(issues))


def validate_monthly_proposal(
    proposal: MonthlyPlanProposal,
    packet: MonthlyContextPacket,
    request: MonthlyPlanningRequest,
) -> MonthlyProposalValidationResult:
    schema = validate_monthly_proposal_schema(proposal, request)
    grounding = validate_monthly_proposal_grounding(proposal, packet, request)
    return MonthlyProposalValidationResult(schema.issues + grounding.issues)
