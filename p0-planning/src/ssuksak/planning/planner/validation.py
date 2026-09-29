"""Deterministic validation for full-month LLM proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from ..context.models import (
    GroundingContextItem,
    MonthlyContextPacket,
    OfficialSafetyContent,
    SafetyReferenceContext,
    SafetySlotContext,
)
from ..evidence.safety_classification import SafetyReferenceKind
from ..context.serialization import packet_fingerprint
from ..domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    SectionRole,
    TemplateSection,
)
from ..domain.monthly_template_profile import INSTITUTION_INPUT_SECTION_KEYS
from ..domain.safety_placement import SafetyKind
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
    # Wrong ref choice inside the Rule-fixed slot: repairable.
    SAFETY_GROUNDING_MISMATCH = "SAFETY_GROUNDING_MISMATCH"
    # Content that would change the slot's kind or legal category: never repaired.
    SAFETY_PLACEMENT_MISMATCH = "SAFETY_PLACEMENT_MISMATCH"
    # A ref other than the slot's fixed focus / primary: repairable re-selection.
    SAFETY_FOCUS_MISMATCH = "SAFETY_FOCUS_MISMATCH"
    # An active supplemental week left empty although its primary was assigned.
    SAFETY_CELL_UNRESOLVED = "SAFETY_CELL_UNRESOLVED"
    # Cell quality, repairable by rewriting inside the same grounding.
    SAFETY_MULTIPLE_SENTENCES = "SAFETY_MULTIPLE_SENTENCES"
    SAFETY_DUPLICATE_CONTENT = "SAFETY_DUPLICATE_CONTENT"
    SAFETY_DUPLICATE_REFERENCE = "SAFETY_DUPLICATE_REFERENCE"


class SafetySlotReason(str, Enum):
    """Stable cause of a SAFETY_* slot finding (one per validator branch)."""

    STATUTORY_SLOT_EMPTY = "STATUTORY_SLOT_EMPTY"
    WRONG_LEGAL_CATEGORY_OFFICIAL_REF = "WRONG_LEGAL_CATEGORY_OFFICIAL_REF"
    OFFICIAL_REF_MISSING = "OFFICIAL_REF_MISSING"
    WRONG_SAMPLE_REFERENCE = "WRONG_SAMPLE_REFERENCE"
    OFFICIAL_REF_IN_SUPPLEMENTAL_SLOT = "OFFICIAL_REF_IN_SUPPLEMENTAL_SLOT"
    STATUTORY_REF_IN_SUPPLEMENTAL_SLOT = "STATUTORY_REF_IN_SUPPLEMENTAL_SLOT"
    NON_FOCUS_OFFICIAL_REF = "NON_FOCUS_OFFICIAL_REF"
    TOO_MANY_SAMPLE_REFS = "TOO_MANY_SAMPLE_REFS"
    SUPPLEMENTAL_SLOT_EMPTY = "SUPPLEMENTAL_SLOT_EMPTY"
    PRIMARY_REF_MISSING = "PRIMARY_REF_MISSING"
    NON_PRIMARY_REF = "NON_PRIMARY_REF"
    MULTIPLE_SENTENCES = "MULTIPLE_SENTENCES"
    SAME_TEXT_AS_OTHER_WEEK = "SAME_TEXT_AS_OTHER_WEEK"
    SAME_REFERENCE_AS_OTHER_WEEK = "SAME_REFERENCE_AS_OTHER_WEEK"
    SAME_TOPIC_AS_OTHER_WEEK = "SAME_TOPIC_AS_OTHER_WEEK"
    SAFETY_REFERENCE_ID_FORBIDDEN = "SAFETY_REFERENCE_ID_FORBIDDEN"


MAX_STATUTORY_SAMPLE_REFS = 2
_SENTENCE_END = re.compile(r"[.!?。]+")


def sentence_count(text: str) -> int:
    """Sentences split at terminal punctuation or line breaks."""
    return sum(bool(piece.strip()) for line in text.splitlines() for piece in _SENTENCE_END.split(line))


@dataclass(frozen=True, slots=True)
class ProposalValidationIssue:
    code: ProposalValidationCode
    field: str
    detail: str = ""
    week_id: str | None = None
    # Stable, content-free locators for logs: never generated text or evidence text.
    reason: str | None = None
    expected: str | None = None
    actual: str | None = None


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


@dataclass(frozen=True, slots=True)
class SafetySlotProblem:
    code: ProposalValidationCode
    reason: SafetySlotReason
    expected: str
    actual: str | None = None

    @property
    def detail(self) -> str:
        return f"{self.reason.value}: expected={self.expected} actual={self.actual}"


def _reference_label(reference: SafetyReferenceContext) -> str:
    return f"{reference.kind.value}:{reference.legal_category_id or reference.supplemental_label}"


def safety_slot_problem(
    slot: SafetySlotContext | None,
    value: ProposedSectionValue,
    official: dict[str, OfficialSafetyContent],
    references: dict[str, SafetyReferenceContext] | None = None,
) -> SafetySlotProblem | None:
    """How a safety value breaks its Rule-fixed slot, or None when it does not."""
    if slot is None:
        return None
    categories = {official[ref].category_id for ref in value.grounding_refs if ref in official}
    samples = [references[ref] for ref in value.grounding_refs if references and ref in references]
    placement = ProposalValidationCode.SAFETY_PLACEMENT_MISMATCH
    grounding = ProposalValidationCode.SAFETY_GROUNDING_MISMATCH
    if slot.kind is SafetyKind.STATUTORY:
        expected = f"STATUTORY:{slot.category_id}"
        if value.unresolved:
            return SafetySlotProblem(placement, SafetySlotReason.STATUTORY_SLOT_EMPTY, expected, "UNRESOLVED")
        if categories - {slot.category_id}:
            return SafetySlotProblem(
                placement, SafetySlotReason.WRONG_LEGAL_CATEGORY_OFFICIAL_REF, expected,
                "official:" + ",".join(sorted(categories)),
            )
        if not categories:
            return SafetySlotProblem(grounding, SafetySlotReason.OFFICIAL_REF_MISSING, expected, "official:none")
        cited_official = sorted(ref for ref in value.grounding_refs if ref in official)
        if slot.focus_ref is not None and cited_official != [slot.focus_ref]:
            return SafetySlotProblem(
                ProposalValidationCode.SAFETY_FOCUS_MISMATCH, SafetySlotReason.NON_FOCUS_OFFICIAL_REF,
                slot.focus_ref, ",".join(cited_official),
            )
        wrong = sorted({_reference_label(s) for s in samples if s.legal_category_id != slot.category_id})
        if wrong:
            return SafetySlotProblem(grounding, SafetySlotReason.WRONG_SAMPLE_REFERENCE, expected, ",".join(wrong))
        if slot.focus_ref is not None and len(samples) > MAX_STATUTORY_SAMPLE_REFS:
            return SafetySlotProblem(
                grounding, SafetySlotReason.TOO_MANY_SAMPLE_REFS, f"<={MAX_STATUTORY_SAMPLE_REFS}", str(len(samples))
            )
        return None
    if categories:
        return SafetySlotProblem(
            placement, SafetySlotReason.OFFICIAL_REF_IN_SUPPLEMENTAL_SLOT, "SUPPLEMENTAL",
            "official:" + ",".join(sorted(categories)),
        )
    statutory = sorted({_reference_label(s) for s in samples if s.kind is SafetyReferenceKind.STATUTORY_REFERENCE})
    if statutory:
        return SafetySlotProblem(
            placement, SafetySlotReason.STATUTORY_REF_IN_SUPPLEMENTAL_SLOT, "SUPPLEMENTAL", ",".join(statutory)
        )
    if slot.primary_ref is not None:
        if value.unresolved:
            return SafetySlotProblem(
                ProposalValidationCode.SAFETY_CELL_UNRESOLVED, SafetySlotReason.SUPPLEMENTAL_SLOT_EMPTY,
                slot.primary_ref, "UNRESOLVED",
            )
        refs = set(value.grounding_refs)
        focus = ProposalValidationCode.SAFETY_FOCUS_MISMATCH
        if slot.primary_ref not in refs:
            return SafetySlotProblem(focus, SafetySlotReason.PRIMARY_REF_MISSING, slot.primary_ref, ",".join(sorted(refs)))
        extra = sorted(refs - {slot.primary_ref, *slot.support_refs})
        if extra:
            return SafetySlotProblem(focus, SafetySlotReason.NON_PRIMARY_REF, slot.primary_ref, ",".join(extra))
    return None


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
        **located: str | None,
    ) -> None:
        issues.append(ProposalValidationIssue(code, field, detail, week_id, **located))

    if request.packet_fingerprint != packet_fingerprint(packet):
        fail(
            ProposalValidationCode.PACKET_FINGERPRINT_MISMATCH,
            "packet_fingerprint",
        )
        return MonthlyProposalValidationResult(tuple(issues))

    evidence_items = packet.grounding_items
    evidence_by_ref = {item.evidence_ref: item for item in evidence_items}
    official = packet.safety.official_by_ref if packet.safety is not None else {}
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
        if value.section_key == "safety_education" and packet.safety is not None and week_id:
            problem = safety_slot_problem(
                packet.safety.slot(week_id), value, official, packet.safety.reference_by_ref
            )
            if problem:
                fail(
                    problem.code, value.section_key, problem.detail, week_id,
                    reason=problem.reason.value, expected=problem.expected, actual=problem.actual,
                )
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
            ref in official
            or (evidence_by_ref.get(ref) is not None and is_safety_grounding(evidence_by_ref[ref]))
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
                reason=code,
            )
        unknown = tuple(
            ref
            for ref in value.grounding_refs
            if ref not in evidence_by_ref and ref not in official
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
            if value.section_key == "safety_education":
                # Safety never uses the Activity catalog field, whatever id it holds.
                fail(
                    ProposalValidationCode.UNKNOWN_REFERENCE_ID,
                    value.section_key,
                    week_id=week_id,
                    reason=SafetySlotReason.SAFETY_REFERENCE_ID_FORBIDDEN.value,
                    expected="null",
                    actual="annex6" if value.reference_id.startswith("annex6:") else "non_null",
                )
            elif expected is None:
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
    if packet.safety is not None:
        seen_text: dict[str, str] = {}
        seen_ref: dict[str, str] = {}
        seen_topic: dict[str, str] = {}
        samples = packet.safety.reference_by_ref
        for value, week_id in _canonical_values(proposal):
            if value.section_key != "safety_education" or week_id is None or value.unresolved:
                continue
            if sentence_count(value.value) > 1:
                fail(ProposalValidationCode.SAFETY_MULTIPLE_SENTENCES, value.section_key, "", week_id,
                     reason=SafetySlotReason.MULTIPLE_SENTENCES.value, expected="1",
                     actual=str(sentence_count(value.value)))
            key = normalize_visible_text(value.value)
            if key in seen_text:
                fail(ProposalValidationCode.SAFETY_DUPLICATE_CONTENT, value.section_key, "", week_id,
                     reason=SafetySlotReason.SAME_TEXT_AS_OTHER_WEEK.value, expected="unique", actual=seen_text[key])
            seen_text.setdefault(key, week_id)
            for ref in value.grounding_refs:
                if ref in samples and ref in seen_ref:
                    fail(ProposalValidationCode.SAFETY_DUPLICATE_REFERENCE, value.section_key, "", week_id,
                         reason=SafetySlotReason.SAME_REFERENCE_AS_OTHER_WEEK.value, expected="unique",
                         actual=seen_ref[ref])
                seen_ref.setdefault(ref, week_id)
            # Two refs of one topic count as one topic, whatever their label.
            topics = {samples[r].topic_group for r in value.grounding_refs if r in samples and samples[r].topic_group}
            for topic in sorted(topics):
                if topic in seen_topic:
                    fail(ProposalValidationCode.SAFETY_DUPLICATE_REFERENCE, value.section_key, "", week_id,
                         reason=SafetySlotReason.SAME_TOPIC_AS_OTHER_WEEK.value, expected="unique topic",
                         actual=seen_topic[topic])
                seen_topic.setdefault(topic, week_id)
    return MonthlyProposalValidationResult(tuple(issues))


def validate_monthly_proposal(
    proposal: MonthlyPlanProposal,
    packet: MonthlyContextPacket,
    request: MonthlyPlanningRequest,
) -> MonthlyProposalValidationResult:
    schema = validate_monthly_proposal_schema(proposal, request)
    grounding = validate_monthly_proposal_grounding(proposal, packet, request)
    return MonthlyProposalValidationResult(schema.issues + grounding.issues)
