"""Build the full-month prompt from a PR4 Context Packet."""

from __future__ import annotations

from dataclasses import replace
import json

from ..context.models import MonthlyContextPacket
from ..context.serialization import packet_fingerprint
from ..domain.monthly_template import RepeatBy, TemplateSection
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..domain.week_period import WeekId
from ..evidence.classification import grounding_class_for
from .contracts import (
    MONTHLY_CONTEXT_PROMPT_VERSION,
    MONTHLY_CONTEXT_REPAIR_PROMPT_VERSION,
    MONTHLY_CONTEXT_SAFETY_PROMPT_VERSION,
    MONTHLY_DRILL_CANDIDATES_PROMPT_TAG,
    MONTHLY_CONTEXT_SAFETY_REPAIR_PROMPT_VERSION,
    MONTHLY_INDOOR_PROMPT_TAG,
    MONTHLY_PROMPT_VERSION,
    MONTHLY_REPAIR_PROMPT_VERSION,
    MONTHLY_SAFETY_CANDIDATES_PROMPT_TAG,
    MONTHLY_SAFETY_PROMPT_VERSION,
    MONTHLY_SAFETY_REPAIR_PROMPT_VERSION,
    DRILL_CANDIDATE_PREFIX,
    SAFETY_CANDIDATE_PREFIX,
    MonthlyPlanningRequest,
    generation_target_sections,
)
from .text_policy import MAX_VISIBLE_TEXT_CHARS
from .v1_guidance import V1_GUIDANCE, curriculum_context
from ..retrieval.models import AGE_VERIFIABLE_TIERS
from .validation import ProposalValidationIssue, is_safety_grounding, repair_targets, wrong_source_refs

MONTHLY_TASK = "monthly_plan_proposal"

SYSTEM_PROMPT = """You propose values for one monthly plan Template snapshot.
Use only the supplied Context Packet and generation_schema.
Do not add, remove, relabel, reorder, or reinterpret Template sections.
Return content only for canonical section_key addresses in response_contract.
Do not return display_label, order, semantic_variant, category, repeat_by,
required_for_generation, or visible.
Return the locked theme exactly with its supplied reference_id and text, and
grounding_refs as []; its parent plan already grounds it.
Do not make legal decisions or claim statutory compliance.
For safety_education, use approved safety grounding from the supplied Context;
when that grounding is unavailable, return value="", unresolved=true, no refs.
Every other resolved generated value needs supplied grounding_refs or, where
allowed below, a supplied reference_id. Do not invent facts or citations and do
not copy evidence verbatim.
Use reference_id only in a section whose reference catalog is supplied: theme
(parent_theme.theme_id) and outdoor_play (reference_activities activity_id).
In every other section reference_id is null; never put a grounding_ref, theme_id
or activity_id there. A reference cell returns one reference_id and value pair
allowed by the response schema; that value is the canonical label of the
referenced item, and its grounding_refs is [] because the reference grounds it.
To write your own sentence instead, set reference_id to null and cite
grounding_refs.
A section with a grounding_class may cite only evidence with that grounding_class;
a section without one must not cite evidence that has a grounding_class.
Within each grounding_refs array, include each reference id at most once;
never repeat the same reference id in a cell.
Omit an optional section when no evidence with its grounding_class is supplied.
For goals, write one concise Korean summary of the month's key goals, usually
about 120 to 160 characters, and stay concise even in a complex month.
Synthesize the core meaning of the cited goals evidence; do not list each
institution's goals or try to include every evidence phrase.
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
A week missing from safety_plan has no safety education: return its
safety_education with unresolved true, an empty value and no grounding_refs.
Write every safety_education value about one safety concept or action; never
list several actions or topics. Never write a category name, brackets or a
leading dash: the application adds the category label to STATUTORY weeks.
For a STATUTORY week, write one short Korean sentence expressing its one
official_content focus for young children. Cite that focus grounding_ref,
optionally with at most two of that week's sample_refs that illustrate the same
focus, and cite no other official_content.
For a SUPPLEMENTAL week, write only a short Korean topic phrase, not a sentence
and with no final period, naming the one key action of its primary_ref (for
example a phrase ending in 하기). Cite primary_ref, optionally with its
support_refs, and nothing else.
Record the official_content focus ref, primary_ref and support_refs only in
grounding_refs. For safety_education, reference_id is always null: reference_id
is the activity reference catalog field, never safety grounding.
Never write the same safety sentence in two weeks.
State only safety practice found in the cited official_content or evidence; add
no new safety rules, numbers, legal duties, education hours, or schedules.
"""

# Appended only when indoor_alternative is an LLM target (MONTHLY_INDOOR_PROMPT_TAG).
INDOOR_ALTERNATIVE_PROMPT = """For indoor_alternative, write each week's indoor activity that replaces that
same week's outdoor_play experience on a day the class stays inside; write the
two cells of a week together as a pair. Do not write general indoor free play.
Do not state that particular materials or spaces are available, and do not
invent weather or claim that the activity was carried out.
When no supplied grounding continues that week's outdoor_play, return that week's
indoor_alternative with value "", unresolved true and no grounding_refs; do not
borrow an unrelated activity or add a subject the cited text does not have.
"""

# Appended only when the Context Packet carries safety_candidates (MONTHLY_SAFETY_CANDIDATES_PROMPT_TAG).
SAFETY_CANDIDATES_PROMPT = """safety_candidates lists this month's safety education candidates; a teacher
later places them into weeks. Return one month_sections entry per candidate,
keyed by its section_key, with unresolved false and reference_id null.
Write one short Korean sentence for young children that makes clear what the
candidate teaches; when its cited text states an action, show that action.
Never write a category name, brackets or a leading dash: the application adds
the label.
A STATUTORY candidate cites exactly one of its allowed grounding_refs; a
SUPPLEMENTAL candidate cites one or more of its allowed grounding_refs. Cite no
other ref. Never write the same sentence for two candidates and never copy an
allowed text verbatim. Add no safety rules, actions, materials, detailed
procedures, times, numbers, legal duties or results not found in the cited text.
"""

# v1 monthly expression criteria (2026-10-31). Only requests carrying curriculum or
# annual subthemes get these; other requests keep their prompt bytes.
_GOALS_LENGTH = """usually
about 120 to 160 characters, and stay concise even in a complex month."""
_V1_GOALS_LENGTH = """in one or two
short sentences about the month's central experience."""
_REPAIR_GOALS_LENGTH = "and aim for about 120 to 160 characters"
_V1_REPAIR_GOALS_LENGTH = "in one or two short sentences"
MONTHLY_V1_STYLE = """
월간은 한 달과 각 주에 예상하는 경험을 짧게 보여 준다. 준비물 목록·진행 순서·교사 발문·요일별 절차는 쓰지 않는다.
- goals: 한 달의 중심 경험을 1~2문장으로 묶는다. 인용한 목표 근거가 다루는 범위 안에서 월 주제의 주요 축을 고르게 담고,
  근거에 없는 목표나 축을 더하지 않는다. 관심·친숙함·소중함 같은 말을 나열하지 않는다.
- focus: parent_subthemes의 주요 대상·경험을 바탕으로 정하고 그 주의 예상 경험을 짧게 쓴다. 월간 전체가 그 범위를 유지하도록 하고,
  하나의 소주제를 여러 주로 세분화하느라 다른 주요 내용을 빠뜨리지 않는다. 주차 순서나 1:1 배치는 강제하지 않는다.
  다른 놀이를 넣으려고 소주제 범위를 넓히지 않고, 고르기 쉬운 놀이에 맞추려고 focus를 다른 대상으로 바꾸지 않는다.
- 작성 순서: parent_subthemes → focus → 같은 주 outdoor_play → indoor_alternative. 각 칸은 허용된 근거 범위를 지킨다.
- outdoor_play · indoor_alternative: 대상과 경험이 드러나는 짧은 활동명으로 쓴다. reference_id로 고른 활동은 그 이름 그대로 둔다.
- outdoor_play: 같은 주에 focus가 있으면 그 핵심 대상·경험과 이어지는 놀이를 쓴다. 허용 근거나 reference_activities에
  그런 놀이가 있으면 그것을 고르고, 관련 없는 활동을 편하다는 이유로 고르지 않는다.
- indoor_alternative: 같은 주 바깥놀이의 대상·경험을 실내에서 이어 가되 '바깥 … 대신 실내에서'처럼 설명하지 않는다.
  이어 갈 근거가 없으면 근거 밖 재료·경험을 보태지 않는다.
- 다른 주에 같은 놀이를 이름만 바꿔 다시 쓰지 않는다. 같은 주의 바깥놀이와 실내대체가 같은 놀이·경험을 나누는 것은 괜찮다.
- basic_habit: 유아가 하는 행동이 보이는 짧은 문장으로 쓴다.
"""


def _v1_goals(prompt: str) -> str:
    return prompt.replace(_GOALS_LENGTH, _V1_GOALS_LENGTH).replace(_REPAIR_GOALS_LENGTH, _V1_REPAIR_GOALS_LENGTH)

# Appended only when the Context Packet carries drill_topics (MONTHLY_DRILL_CANDIDATES_PROMPT_TAG).
DRILL_CANDIDATES_PROMPT = """drill_topics lists this month's fire evacuation and disaster drill topics; a
teacher later copies one into the plan. Return one month_sections entry per
topic, keyed by its section_key, with unresolved false, reference_id null and
no grounding_refs. Write one short Korean sentence, in words young children
understand, about a drill that assumes the topic's situation. Never write the
same sentence for two topics. Do not invent dates, times, people in charge,
evacuation routes, assembly points, procedures or results.
"""

REPAIR_HEADER = f"""You repair one monthly plan proposal.
rejected_proposal failed semantic validation. Each validation_findings entry
names a failed code with its section_key and week_id; a null week_id is the
month-level cell. For TEXT_POLICY, detail names the violated text rule.
Return only one JSON object matching response_contract: a patches array with one
patch per repair_targets entry, carrying that entry's week_id (null for the
month-level cell) and section_key and exactly the fields it lists. Return no
other cell and no other field; every cell you do not patch keeps its value.
Fix each patched cell only as its finding requires:
- SOURCE_TEXT_COPY: keep the meaning of its cited grounding_refs but rewrite
  the value in your own words; never copy evidence text verbatim.
- TEXT_POLICY with detail TEXT_TOO_LONG: keep the same meaning and cited refs;
  remove repetition and unnecessary modifiers. For goals, keep only the month's
  key goals and aim for about 120 to 160 characters. The validator rejects a
  value over {MAX_VISIBLE_TEXT_CHARS} characters; that is a hard ceiling, not a target length.
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
The patched proposal is validated again in full. The original planning rules
follow and still apply.

"""
REPAIR_SYSTEM_PROMPT = REPAIR_HEADER + SYSTEM_PROMPT


def official_safety_refs(packet: MonthlyContextPacket) -> tuple[str, ...]:
    return () if packet.safety is None else tuple(packet.safety.official_by_ref)


def valid_grounding_refs(packet: MonthlyContextPacket) -> frozenset[str]:
    return (
        frozenset(item.evidence_ref for item in packet.grounding_items)
        | frozenset(official_safety_refs(packet))
        | frozenset(ref for slot in packet.safety_candidates for ref, _ in slot.allowed)
    )


def safety_candidate_targets(packet: MonthlyContextPacket) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each candidate's month_sections key with the refs its Rule-fixed slot allows.

    A drill candidate cites nothing: its curriculum evidence comes from the Rule's topic."""
    return tuple(
        (SAFETY_CANDIDATE_PREFIX + slot.slot, tuple(ref for ref, _ in slot.allowed))
        for slot in packet.safety_candidates
    ) + tuple((DRILL_CANDIDATE_PREFIX + topic.topic_id, ()) for topic in packet.drill_topics)


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
        if section.section_key == "safety_education" and packet.safety_candidates:
            continue  # S-1: weekly cells stay blank; the candidates are the targets
        wrong = set(wrong_source_refs(section, refs, evidence))
        allowed = tuple(ref for ref in refs if ref not in wrong)
        if section.section_key in {"outdoor_play", "indoor_alternative"}:
            # Only age-verifiable evidence; the schema enum enforces it.
            allowed = tuple(ref for ref in allowed if evidence[ref].age_match in AGE_VERIFIABLE_TIERS)
        if section.section_key == "indoor_alternative" and not allowed:
            continue  # D-5: no evidence leaves its cells empty for the teacher
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
    ) + safety_candidate_targets(packet)


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
    if packet.safety_candidates:
        payload["safety_candidates"] = [
            {
                "section_key": SAFETY_CANDIDATE_PREFIX + slot.slot,
                "kind": slot.kind.value,
                "allowed": [{"grounding_ref": ref, "text": text} for ref, text in slot.allowed],
            }
            for slot in packet.safety_candidates
        ]
    if packet.drill_topics:
        payload["drill_topics"] = [
            {"section_key": DRILL_CANDIDATE_PREFIX + t.topic_id, "label": t.label, "situation": t.situation}
            for t in packet.drill_topics
        ]
    return payload


def _base_payload(packet: MonthlyContextPacket) -> dict[str, object]:
    payload = {
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
    if packet.curriculum is not None:
        payload["curriculum_context"] = curriculum_context(packet.curriculum)
    if packet.parent_subthemes:
        payload["parent_subthemes"] = list(packet.parent_subthemes)
    return payload


def _generation_schema(
    packet: MonthlyContextPacket, snapshot: TemplateSnapshot
) -> dict[str, object]:
    sections: list[dict[str, object]] = []
    for section, _ in generation_targets(packet, snapshot):
        placement = (
            "MONTH"
            if section.repeat_by is RepeatBy.NONE
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
    contextual = packet.curriculum is not None or bool(packet.parent_subthemes)
    indoor = any(section.section_key == "indoor_alternative" for section, _ in generation_targets(packet, snapshot))
    version = MONTHLY_SAFETY_PROMPT_VERSION if safety else MONTHLY_PROMPT_VERSION
    if contextual:
        version = MONTHLY_CONTEXT_SAFETY_PROMPT_VERSION if safety else MONTHLY_CONTEXT_PROMPT_VERSION
    if indoor:
        version += MONTHLY_INDOOR_PROMPT_TAG
    if packet.safety_candidates:
        version += MONTHLY_SAFETY_CANDIDATES_PROMPT_TAG
    if packet.drill_topics:
        version += MONTHLY_DRILL_CANDIDATES_PROMPT_TAG
    return MonthlyPlanningRequest(
        task=MONTHLY_TASK,
        prompt_version=version,
        system_prompt=(
            _v1_goals(SAFETY_SYSTEM_PROMPT if safety else SYSTEM_PROMPT) + V1_GUIDANCE
            + "\nparent_subthemes는 확정된 연간의 월별 예상 소주제다. "
            "월간 경험을 구체화하는 맥락으로 쓰며, 각 소주제를 주차에 하나씩 강제로 복사하지 않는다.\n"
            + MONTHLY_V1_STYLE
            if contextual else (SAFETY_SYSTEM_PROMPT if safety else SYSTEM_PROMPT)
        ) + (INDOOR_ALTERNATIVE_PROMPT if indoor else "")
        + (SAFETY_CANDIDATES_PROMPT if packet.safety_candidates else "")
        + (DRILL_CANDIDATES_PROMPT if packet.drill_topics else ""),
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
    """Same refs as `request`, but the provider returns patches for the repair targets only.

    repair_targets selects parser.repair_patch_schema: one branch per finding-named
    cell, with exactly the fields its findings authorize.
    """
    targets = repair_targets(issues)
    original = json.loads(request.user_content)
    original.pop("response_contract", None)  # the full-proposal contract is not this response
    body = {
        "original_request": original,
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
        "repair_targets": [
            {"week_id": week_id, "section_key": section_key, "fields": list(fields)}
            for week_id, section_key, fields in targets
        ],
        "response_contract": {
            "patches": [
                {
                    "week_id": "YYYY-MM-Wn | null",
                    "section_key": "string",
                    "value": "string, when the target lists it",
                    "grounding_refs": ["string, when the target lists it"],
                }
            ]
        },
    }
    base = request.prompt_version.split("+", 1)[0]  # tags keep their order after the repair version
    contextual = base in (MONTHLY_CONTEXT_PROMPT_VERSION, MONTHLY_CONTEXT_SAFETY_PROMPT_VERSION)
    return replace(
        request,
        prompt_version={
            MONTHLY_CONTEXT_SAFETY_PROMPT_VERSION: MONTHLY_CONTEXT_SAFETY_REPAIR_PROMPT_VERSION,
            MONTHLY_CONTEXT_PROMPT_VERSION: MONTHLY_CONTEXT_REPAIR_PROMPT_VERSION,
            MONTHLY_SAFETY_PROMPT_VERSION: MONTHLY_SAFETY_REPAIR_PROMPT_VERSION,
        }.get(base, MONTHLY_REPAIR_PROMPT_VERSION)
        + request.prompt_version[len(base):],
        system_prompt=(_v1_goals(REPAIR_HEADER) if contextual else REPAIR_HEADER) + request.system_prompt,
        user_content=json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2),
        repair_targets=targets,
    )
