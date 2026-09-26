"""Build the full-month prompt from a PR4 Context Packet."""

from __future__ import annotations

from dataclasses import replace
import json

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from ..domain.monthly_template import DisplayMode, TemplateSection
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..domain.week_period import WeekId
from ..evidence.classification import grounding_class_for
from .contracts import (
    MONTHLY_PROMPT_VERSION,
    MONTHLY_REPAIR_PROMPT_VERSION,
    MONTHLY_SAFETY_PROMPT_VERSION,
    MONTHLY_SAFETY_REPAIR_PROMPT_VERSION,
    MonthlyPlanningRequest,
    generation_target_sections,
)
from .text_policy import MAX_VISIBLE_TEXT_CHARS
from .validation import ProposalValidationIssue, is_safety_grounding, wrong_source_refs

MONTHLY_TASK = "monthly_plan_proposal"

SYSTEM_PROMPT = """You propose values for one monthly plan Template snapshot.
Use only the supplied Context Packet and generation_schema.
Do not add, remove, relabel, reorder, or reinterpret Template sections.
Return content only for canonical section_key addresses in response_contract.
Do not return display_label, order, semantic_variant, category, display_mode,
required_for_generation, or visible.
The locked theme must be returned exactly with its supplied reference_id.
Do not make legal decisions or claim statutory compliance.
For safety_education, use approved safety grounding from the supplied Context;
when that grounding is unavailable, return value="", unresolved=true, no refs.
Every other resolved generated value needs supplied grounding_refs or, where
allowed below, a supplied reference_id. Do not invent facts or citations and do
not copy evidence verbatim.
Use reference_id only in a section whose reference catalog is supplied: theme
(parent_theme.theme_id) and outdoor_play (reference_activities activity_id).
In every other section reference_id is null; never put a grounding_ref, theme_id
or activity_id there. When reference_id is not null, value must exactly equal the
canonical label of that referenced item; do not paraphrase, expand, summarize or
rewrite it. To write your own sentence instead, set reference_id to null and cite
grounding_refs.
A section with a grounding_class may cite only evidence with that grounding_class;
a section without one must not cite evidence that has a grounding_class.
Within each grounding_refs array, include each reference id at most once;
never repeat the same reference id in a cell.
Omit an optional section when no evidence with its grounding_class is supplied.
Write user-facing plan text in value fields in natural Korean.
Keep JSON keys, section_key, week ids, enum values, IDs, reference_id and
grounding_refs exactly as supplied or specified; never translate them.
Include every key required by response_contract in every object and cell;
for a nullable field with no value, include the key with null, never omit it.
Return only one JSON object matching response_contract; add no fields.
"""

# Appended to SYSTEM_PROMPT only when the Context Packet carries safety placement.
SAFETY_SYSTEM_PROMPT = SYSTEM_PROMPT + """safety_plan fixes every week's safety_education slot: its week, kind, legal
category, official content focus or primary reference. Never change any of them.
Write every safety_education value as exactly one Korean sentence about one
safety concept or action; never list several actions or topics.
For a STATUTORY week, express its one official_content focus for young children.
Cite that focus grounding_ref, optionally with at most two of that week's
sample_refs that illustrate the same focus, and cite no other official_content.
For a SUPPLEMENTAL week, express the one key action of its primary_ref. Cite
primary_ref, optionally with its support_refs, and nothing else.
Record the official_content focus ref, primary_ref and support_refs only in
grounding_refs. For safety_education, reference_id is always null: reference_id
is the activity reference catalog field, never safety grounding.
Never write the same safety sentence in two weeks.
State only safety practice found in the cited official_content or evidence; add
no new safety rules, numbers, legal duties, education hours, or schedules.
"""

REPAIR_HEADER = f"""You repair one monthly plan proposal.
rejected_proposal matches response_contract but failed semantic validation.
Each validation_findings entry names a failed code with its section_key and
week_id; a null week_id is the month-level cell. For TEXT_POLICY, detail names
the violated text rule.
Return the complete corrected proposal as one JSON object matching
original_request.response_contract. Change only the cells named in
validation_findings and keep cells without a finding unchanged: copy their
value, reference_id and grounding_refs exactly as in rejected_proposal.
Fix each named cell only as its finding requires:
- SOURCE_TEXT_COPY: keep the meaning of its cited grounding_refs but rewrite
  the value in your own words; never copy evidence text verbatim.
- TEXT_POLICY with detail TEXT_TOO_LONG: keep the same meaning and cited refs;
  shorten the value to at most {MAX_VISIBLE_TEXT_CHARS} characters by removing
  unnecessary modifiers and repetition.
- Other TEXT_POLICY: remove only the violation that detail names.
- WRONG_SOURCE_GROUNDING: cite only refs with that section's grounding_class.
- SAFETY_*: fix the cell inside its safety_plan slot, citing only that week's
  focus or primary_ref and its allowed refs.
In every value you rewrite, never copy evidence text verbatim.
Cite only grounding_refs supplied in original_request.evidence, following the
grounding_class rules below.
Value text must not claim legal or official status, must not mention safety
education outside safety_education, and must not contain source markers,
institution aliases, source ids or grounding_refs.
The repaired proposal is validated again in full. The original planning rules
follow and still apply.

"""
REPAIR_SYSTEM_PROMPT = REPAIR_HEADER + SYSTEM_PROMPT


def official_safety_refs(packet: MonthlyContextPacket) -> tuple[str, ...]:
    return () if packet.safety is None else tuple(packet.safety.official_by_ref)


def valid_grounding_refs(packet: MonthlyContextPacket) -> frozenset[str]:
    return frozenset(item.evidence_ref for item in packet.grounding_items) | frozenset(
        official_safety_refs(packet)
    )


def generation_targets(
    packet: MonthlyContextPacket, snapshot: TemplateSnapshot
) -> tuple[tuple[TemplateSection, tuple[str, ...]], ...]:
    """This request's LLM targets with the supplied refs each may cite.

    Refs follow the validators: WRONG_SOURCE_GROUNDING for every Section and
    SAFETY_GROUNDING_REQUIRED for safety_education. Without approved safety
    grounding safety_education is no LLM target; the Core safety assessment
    leaves its cells EMPTY_UNRESOLVED.
    """
    evidence = {item.evidence_ref: item for item in packet.grounding_items}
    refs = tuple(sorted(evidence))
    targets = []
    for section in generation_target_sections(snapshot):
        wrong = set(wrong_source_refs(section, refs, evidence))
        allowed = tuple(ref for ref in refs if ref not in wrong)
        if section.section_key == "safety_education":
            allowed = tuple(ref for ref in allowed if is_safety_grounding(evidence[ref]))
            allowed += tuple(sorted(official_safety_refs(packet)))
            if not allowed:
                continue
        targets.append((section, allowed))
    return tuple(targets)


def allowed_grounding_refs_by_section(
    packet: MonthlyContextPacket, snapshot: TemplateSnapshot
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (section.section_key, refs) for section, refs in generation_targets(packet, snapshot)
    )


def _safety_plan(packet: MonthlyContextPacket) -> dict[str, object]:
    official = packet.safety.official_content
    return {
        "weeks": [
            {
                "week_id": slot.week_id,
                "kind": slot.kind.value,
                "category_id": slot.category_id,
                "official_label": next(
                    (item.official_label for item in official if item.category_id == slot.category_id),
                    None,
                ),
                "official_content": [
                    {"grounding_ref": item.grounding_ref, "text": item.text}
                    for item in official
                    if item.category_id == slot.category_id
                ],
                "sample_refs": list(packet.safety.sample_refs_for(slot)),
                "primary_ref": slot.primary_ref,
                "support_refs": list(slot.support_refs),
                "supplemental_label": (
                    packet.safety.reference_by_ref[slot.primary_ref].supplemental_label if slot.primary_ref else None
                ),
            }
            for slot in packet.safety.slots
        ]
    }


def _prompt_payload(packet: MonthlyContextPacket) -> dict[str, object]:
    payload = _base_payload(packet)
    if packet.safety is not None:
        payload["safety_plan"] = _safety_plan(packet)
    return payload


def _base_payload(packet: MonthlyContextPacket) -> dict[str, object]:
    return {
        "target_month": packet.target_month.value,
        "ages": list(packet.ages),
        "locked_theme": {
            "theme_id": packet.parent_theme_id,
            "value": packet.parent_theme_value,
        },
        "weeks": [
            {
                "week_id": week.week_id,
                "start_date": week.start_date.isoformat(),
                "end_date": week.end_date.isoformat(),
                "display_label": week.display_label,
            }
            for week in packet.weeks
        ],
        "evidence": [
            {
                "grounding_ref": item.evidence_ref,
                "text": item.text,
                "source_section": item.source_section.value,
                "source_label": item.source_label,
                "age_scope": list(item.age_scope),
                "institution_alias": item.institution_alias,
                "reuse_policy": item.reuse_policy.value,
                "grounding_class": (
                    None if item.grounding_class is None else item.grounding_class.value
                ),
            }
            for item in packet.grounding_items
        ],
        "reference_activities": [
            {"activity_id": item.activity_id, "label": item.label, "rank": item.rank}
            for item in packet.reference_activities
        ],
        "deterministic_constraints": list(
            packet.constraints.deterministic_constraint_codes
        ),
        "lineage": {
            "evidence_store_version": packet.lineage.evidence_store_version,
            "evidence_store_sha256": packet.lineage.evidence_store_sha256,
            "retrieval_version": packet.lineage.retrieval_version,
            "activity_catalog_id": packet.lineage.activity_catalog_id,
            "activity_catalog_version": packet.lineage.activity_catalog_version,
        },
    }


def _generation_schema(
    packet: MonthlyContextPacket, snapshot: TemplateSnapshot
) -> dict[str, object]:
    sections: list[dict[str, object]] = []
    for section, _ in generation_targets(packet, snapshot):
        placement = (
            "MONTH"
            if section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
            else "WEEK"
        )
        sections.append(
            {
                "section_key": section.section_key,
                "placement": placement,
                "semantic_variant": (
                    None
                    if section.semantic_variant is None
                    else section.semantic_variant.value
                ),
                "empty_value_policy": (
                    None
                    if section.empty_value_policy is None
                    else section.empty_value_policy.value
                ),
                "grounding_class": (
                    None
                    if (grounding_class := grounding_class_for(section)) is None
                    else grounding_class.value
                ),
                "required_for_generation": section.required_for_generation,
            }
        )
    return {
        "profile_id": snapshot.profile_ref.profile_id,
        "profile_version": snapshot.profile_ref.profile_version,
        "sections": sections,
    }


def _response_contract() -> dict[str, object]:
    section = {
        "section_key": "string",
        "value": "string; empty only when unresolved=true",
        "unresolved": "boolean",
        "reference_id": "string | null",
        "grounding_refs": ["string"],
    }
    return {
        "target_month": "YYYY-MM",
        "month_sections": [section],
        "weeks": [{"week_id": "YYYY-MM-Wn", "sections": [section]}],
    }


def build_monthly_planning_request(
    packet: MonthlyContextPacket, snapshot: TemplateSnapshot
) -> MonthlyPlanningRequest:
    if not isinstance(packet, MonthlyContextPacket):
        raise TypeError("packet must be MonthlyContextPacket")
    if not isinstance(snapshot, TemplateSnapshot):
        raise TypeError("snapshot must be TemplateSnapshot")
    body = _prompt_payload(packet)
    body.update(
        {
            "generation_schema": _generation_schema(packet, snapshot),
            "response_contract": _response_contract(),
        }
    )
    safety = packet.safety is not None
    return MonthlyPlanningRequest(
        task=MONTHLY_TASK,
        prompt_version=MONTHLY_SAFETY_PROMPT_VERSION if safety else MONTHLY_PROMPT_VERSION,
        system_prompt=SAFETY_SYSTEM_PROMPT if safety else SYSTEM_PROMPT,
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2),
        target_month=packet.target_month,
        expected_theme_id=packet.parent_theme_id,
        expected_theme_value=packet.parent_theme_value,
        expected_week_ids=tuple(WeekId(week.week_id) for week in packet.weeks),
        template_snapshot=snapshot,
        reference_labels=tuple(
            (item.activity_id, item.label) for item in packet.reference_activities
        ),
        valid_grounding_refs=valid_grounding_refs(packet),
        packet_fingerprint=packet_fingerprint(packet),
        allowed_grounding_refs_by_section=allowed_grounding_refs_by_section(packet, snapshot),
    )


def build_monthly_repair_request(
    request: MonthlyPlanningRequest,
    rejected_content: str,
    issues: tuple[ProposalValidationIssue, ...],
) -> MonthlyPlanningRequest:
    """Same targets, refs and strict schema as `request`; only the prompt contract differs."""
    body = {
        "original_request": json.loads(request.user_content),
        "rejected_proposal": json.loads(rejected_content),
        "validation_findings": [
            {
                "code": issue.code.value,
                "section_key": issue.field,
                "week_id": issue.week_id,
                "detail": issue.detail,
            }
            for issue in issues
        ],
    }
    return replace(
        request,
        prompt_version=(
            MONTHLY_SAFETY_REPAIR_PROMPT_VERSION
            if request.prompt_version == MONTHLY_SAFETY_PROMPT_VERSION
            else MONTHLY_REPAIR_PROMPT_VERSION
        ),
        system_prompt=REPAIR_HEADER + request.system_prompt,
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2),
    )
