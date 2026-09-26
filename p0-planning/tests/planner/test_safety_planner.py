from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ssuksak.planning.context.models import (
    GroundingContextItem,
    OfficialSafetyContent,
    SafetyContext,
    SafetyReferenceContext,
    SafetySlotContext,
)
from ssuksak.planning.evidence.safety_classification import SafetyReferenceKind
from ssuksak.planning.domain.safety_placement import SafetyKind
from ssuksak.planning.evidence.models import ReusePolicy, SourceSection
from ssuksak.planning.planner.contracts import (
    MONTHLY_MODEL,
    ProposalRejectedError,
    MONTHLY_SAFETY_PROMPT_VERSION,
    MONTHLY_SAFETY_REPAIR_PROMPT_VERSION,
    RawLlmResponse,
)
from ssuksak.planning.planner.parser import monthly_response_schema, parse_monthly_proposal
from ssuksak.planning.planner.prompt import (
    REPAIR_HEADER,
    SAFETY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_monthly_planning_request,
)
from ssuksak.planning.planner.service import MonthlyPlanner
from ssuksak.planning.planner.validation import validate_monthly_proposal
from ssuksak.planning.retrieval.models import AgeMatchKind

LEGAL = "child-welfare-act-decree-annex6-2022-06-21"
TRAFFIC = (
    OfficialSafetyContent("annex6:traffic_safety:1", "traffic_safety", "교통안전 교육", "차도, 보도 및 신호등의 의미 알기"),
    OfficialSafetyContent("annex6:traffic_safety:4", "traffic_safety", "교통안전 교육", "바퀴 달린 탈것의 안전한 이용법"),
)
SEXUAL = (OfficialSafetyContent("annex6:sexual_violence_prevention:1", "sexual_violence_prevention", "성폭력 예방 교육", "내 몸의 소중함"),)
def _sample(ref, text):
    return GroundingContextItem(
        evidence_ref=ref,
        text=text,
        source_section=SourceSection.SAFETY_EDUCATION,
        source_label="안전교육",
        age_scope=(3, 4),
        age_match=AgeMatchKind.MIXED_AGE_COVERING,
        institution_alias="S2",
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
    )


TRAFFIC_SAMPLE = _sample("safe-ev-1", "[교통안전] 자전거를 탈 때 안전모를 써요")
LIFE_SAMPLE = _sample("safe-ev-2", "[생활안전] 계단에서는 난간을 잡고 천천히 걸어요")
SEXUAL_SAMPLE = _sample("safe-ev-3", "[성폭력 예방] 싫어요, 안 돼요 말하기")
REFERENCES = {
    "safe-ev-1": SafetyReferenceContext("safe-ev-1", SafetyReferenceKind.STATUTORY_REFERENCE, "traffic_safety"),
    "safe-ev-2": SafetyReferenceContext("safe-ev-2", SafetyReferenceKind.SUPPLEMENTAL_REFERENCE, supplemental_label="life_safety"),
    "safe-ev-3": SafetyReferenceContext("safe-ev-3", SafetyReferenceKind.STATUTORY_REFERENCE, "sexual_violence_prevention"),
}


def _safety_packet(packet, *, second="SUPPLEMENTAL", evidence=None):
    slots = [SafetySlotContext("2026-09-W1", SafetyKind.STATUTORY, "traffic_safety")]
    official = TRAFFIC
    if second == "SUPPLEMENTAL":
        slots.append(SafetySlotContext("2026-09-W2", SafetyKind.SUPPLEMENTAL))
        evidence = (TRAFFIC_SAMPLE, LIFE_SAMPLE) if evidence is None else evidence
    else:
        slots.append(SafetySlotContext("2026-09-W2", SafetyKind.STATUTORY, "sexual_violence_prevention"))
        official = TRAFFIC + SEXUAL
        evidence = (TRAFFIC_SAMPLE, LIFE_SAMPLE, SEXUAL_SAMPLE) if evidence is None else evidence
    return replace(
        packet,
        safety=SafetyContext("ssuksak-safety-placement-v1", LEGAL, "monthly-safety-retrieval-v0.2.0",
                             tuple(slots), official, evidence,
                             tuple(REFERENCES[item.evidence_ref] for item in evidence)),
    )


def _section(key, value, refs, *, reference_id=None, unresolved=False):
    return {"section_key": key, "value": value, "unresolved": unresolved, "reference_id": reference_id, "grounding_refs": refs}


def _payload(w1_safety=None, w2_safety=None):
    w1_safety = w1_safety or _section(
        "safety_education", "바퀴 달린 탈것을 탈 때는 안전모와 보호장비를 착용해요.", ["annex6:traffic_safety:4", "safe-ev-1"]
    )
    w2_safety = w2_safety or _section("safety_education", "계단을 오르내릴 때는 난간을 꼭 잡아요.", ["safe-ev-2"])
    return {
        "target_month": "2026-09",
        "month_sections": [_section("theme", "가을과 자연", [], reference_id="theme-autumn")],
        "weeks": [
            {"week_id": "2026-09-W1", "sections": [
                _section("focus", "바람과 빛의 변화를 몸으로 살펴본다.", ["ev-3"]),
                _section("outdoor_play", "바람개비 놀이", [], reference_id="act-1"),
                w1_safety,
            ]},
            {"week_id": "2026-09-W2", "sections": [
                _section("focus", "주변의 색과 모양을 새롭게 발견한다.", ["ev-3"]),
                _section("outdoor_play", "색 그림자 찾기", ["ev-1"]),
                w2_safety,
            ]},
        ],
    }


def _validate(packet, snapshot, body):
    request = build_monthly_planning_request(packet, snapshot)
    return validate_monthly_proposal(parse_monthly_proposal(json.dumps(body, ensure_ascii=False)), packet, request)


def test_safety_packet_uses_the_safety_prompt_contract(packet, snapshot):
    request = build_monthly_planning_request(_safety_packet(packet), snapshot)
    body = json.loads(request.user_content)
    weeks = body["safety_plan"]["weeks"]

    assert request.prompt_version == MONTHLY_SAFETY_PROMPT_VERSION
    assert request.system_prompt == SAFETY_SYSTEM_PROMPT and SAFETY_SYSTEM_PROMPT.startswith(SYSTEM_PROMPT)
    assert [(week["kind"], week["category_id"]) for week in weeks] == [("STATUTORY", "traffic_safety"), ("SUPPLEMENTAL", None)]
    assert [item["text"] for item in weeks[0]["official_content"]] == [item.text for item in TRAFFIC]
    assert weeks[1]["official_content"] == []
    assert (weeks[0]["sample_refs"], weeks[1]["sample_refs"]) == (["safe-ev-1"], ["safe-ev-2"])
    for excluded in ("interval", "annual_hours", "derived_totals"):
        assert excluded not in request.user_content  # legal Rule exclusions stay out of the prompt


def test_packets_without_safety_keep_the_planner_contract(packet, snapshot):
    request = build_monthly_planning_request(packet, snapshot)

    assert request.prompt_version != MONTHLY_SAFETY_PROMPT_VERSION
    assert "safety_plan" not in json.loads(request.user_content)


def test_safety_branch_lists_only_official_and_safety_sample_refs(packet, snapshot):
    request = build_monthly_planning_request(_safety_packet(packet), snapshot)
    week_items = monthly_response_schema(request)["properties"]["weeks"]["items"]["properties"]["sections"]["items"]
    safety = next(b for b in week_items["anyOf"] if b["properties"]["section_key"]["enum"] == ["safety_education"])

    assert set(safety["properties"]["grounding_refs"]["items"]["enum"]) == {
        "safe-ev-1", "safe-ev-2", "annex6:traffic_safety:1", "annex6:traffic_safety:4"
    }


def test_a_grounded_safety_proposal_is_valid(packet, snapshot):
    assert _validate(_safety_packet(packet), snapshot, _payload()).is_valid


SEXUAL_W2 = _section("safety_education", "싫은 느낌이 들면 싫어요라고 말해요.", ["annex6:sexual_violence_prevention:1", "safe-ev-3"])


@pytest.mark.parametrize(
    ("second", "w1", "w2", "code"),
    [
        ("STATUTORY", _section("safety_education", "내 몸은 소중해요.", ["annex6:sexual_violence_prevention:1"]),
         SEXUAL_W2, "SAFETY_PLACEMENT_MISMATCH"),
        ("SUPPLEMENTAL", _section("safety_education", "자전거를 탈 때 안전모를 써요.", ["safe-ev-1"]), None, "SAFETY_GROUNDING_MISMATCH"),
        ("SUPPLEMENTAL", _section("safety_education", "바퀴 달린 탈것은 조심히 타요.", ["annex6:traffic_safety:4", "safe-ev-2"]),
         None, "SAFETY_GROUNDING_MISMATCH"),
        ("STATUTORY", _section("safety_education", "바퀴 달린 탈것은 조심히 타요.", ["annex6:traffic_safety:4", "safe-ev-3"]),
         SEXUAL_W2, "SAFETY_GROUNDING_MISMATCH"),
        ("SUPPLEMENTAL", _section("safety_education", "", [], unresolved=True), None, "SAFETY_PLACEMENT_MISMATCH"),
        ("SUPPLEMENTAL", None, _section("safety_education", "신호등을 보고 건너요.", ["annex6:traffic_safety:1"]), "SAFETY_PLACEMENT_MISMATCH"),
        ("SUPPLEMENTAL", None, _section("safety_education", "자전거를 탈 때는 안전모를 써요.", ["safe-ev-1"]), "SAFETY_PLACEMENT_MISMATCH"),
        ("SUPPLEMENTAL", None, _section("safety_education", "안전하게 놀아요.", []), "SAFETY_GROUNDING_REQUIRED"),
        ("SUPPLEMENTAL", None, _section("safety_education", "안전하게 놀아요.", ["ev-1"]), "SAFETY_GROUNDING_REQUIRED"),
        ("SUPPLEMENTAL", _section("safety_education", "신호등을 봐요.", ["annex6:traffic_safety:99"]), None, "UNKNOWN_GROUNDING_REF"),
        ("SUPPLEMENTAL", None, _section("safety_education", "안전하게 놀아요.", ["ev-3"]), "WRONG_SOURCE_GROUNDING"),
    ],
    ids=["other-category", "statutory-without-official", "statutory-cites-supplemental-sample",
         "statutory-cites-other-category-sample", "statutory-unresolved", "supplemental-cites-official",
         "supplemental-cites-statutory-sample", "supplemental-ungrounded", "supplemental-non-safety-ref",
         "unknown-ref", "wrong-source"],
)
def test_invalid_safety_grounding_is_rejected(packet, snapshot, second, w1, w2, code):
    assert code in _validate(_safety_packet(packet, second=second), snapshot, _payload(w1, w2)).codes


def test_supplemental_without_safety_evidence_stays_empty(packet, snapshot):
    empty = _safety_packet(packet, evidence=())
    w1 = _section("safety_education", "바퀴 달린 탈것을 탈 때는 안전모를 써요.", ["annex6:traffic_safety:4"])
    unresolved = _section("safety_education", "", [], unresolved=True)

    assert _validate(empty, snapshot, _payload(w1, unresolved)).is_valid
    assert "SAFETY_GROUNDING_REQUIRED" in _validate(
        empty, snapshot, _payload(w1, _section("safety_education", "안전하게 놀아요.", []))
    ).codes


class _Scripted:
    def __init__(self, *bodies):
        self._bodies = [json.dumps(body, ensure_ascii=False) for body in bodies]
        self.monthly_requests = []

    def generate_monthly(self, request):
        self.monthly_requests.append(request)
        return RawLlmResponse(self._bodies[len(self.monthly_requests) - 1], MONTHLY_MODEL)


def test_safety_grounding_mismatch_is_repaired_once_under_the_safety_repair_contract(packet, snapshot):
    rejected = _payload(_section("safety_education", "자전거를 탈 때 안전모를 써요.", ["safe-ev-1"]))
    fake = _Scripted(rejected, _payload(), _payload())

    outcome = MonthlyPlanner(fake).plan(_safety_packet(packet), snapshot)
    initial, repair = fake.monthly_requests

    assert outcome.prompt_version == repair.prompt_version == MONTHLY_SAFETY_REPAIR_PROMPT_VERSION
    assert repair.system_prompt == REPAIR_HEADER + SAFETY_SYSTEM_PROMPT
    assert json.loads(repair.user_content)["validation_findings"][0]["code"] == "SAFETY_GROUNDING_MISMATCH"
    assert initial.prompt_version == MONTHLY_SAFETY_PROMPT_VERSION


@pytest.mark.parametrize(
    "w1",
    [
        _section("safety_education", "", [], unresolved=True),
        _section("safety_education", "신호등을 보고 건너요.", ["annex6:traffic_safety:1", "annex6:sexual_violence_prevention:1"]),
    ],
    ids=["statutory-dropped", "category-mixed"],
)
def test_safety_placement_mismatch_is_never_repaired(packet, snapshot, w1):
    fake = _Scripted(_payload(w1, SEXUAL_W2), _payload(), _payload())

    with pytest.raises(ProposalRejectedError) as exc:
        MonthlyPlanner(fake).plan(_safety_packet(packet, second="STATUTORY"), snapshot)
    assert "SAFETY_PLACEMENT_MISMATCH" in exc.value.validation_codes
    assert len(fake.monthly_requests) == 1


def test_a_supplemental_sentence_grounded_on_a_supplemental_reference_is_valid(packet, snapshot):
    result = _validate(_safety_packet(packet), snapshot, _payload())

    assert result.is_valid


# ---------------------------------------------------------------- finding observability


@pytest.mark.parametrize(
    ("second", "w1", "w2", "expected"),
    [
        ("SUPPLEMENTAL", _section("safety_education", "", [], unresolved=True), None,
         ("2026-09-W1", "SAFETY_PLACEMENT_MISMATCH", "STATUTORY_SLOT_EMPTY", "STATUTORY:traffic_safety", "UNRESOLVED")),
        ("STATUTORY", _section("safety_education", "내 몸은 소중해요.", ["annex6:sexual_violence_prevention:1"]), SEXUAL_W2,
         ("2026-09-W1", "SAFETY_PLACEMENT_MISMATCH", "WRONG_LEGAL_CATEGORY_OFFICIAL_REF", "STATUTORY:traffic_safety",
          "official:sexual_violence_prevention")),
        ("SUPPLEMENTAL", _section("safety_education", "자전거를 탈 때 안전모를 써요.", ["safe-ev-1"]), None,
         ("2026-09-W1", "SAFETY_GROUNDING_MISMATCH", "OFFICIAL_REF_MISSING", "STATUTORY:traffic_safety", "official:none")),
        ("SUPPLEMENTAL", _section("safety_education", "바퀴 달린 탈것은 조심히 타요.", ["annex6:traffic_safety:4", "safe-ev-2"]), None,
         ("2026-09-W1", "SAFETY_GROUNDING_MISMATCH", "WRONG_SAMPLE_REFERENCE", "STATUTORY:traffic_safety",
          "SUPPLEMENTAL_REFERENCE:life_safety")),
        ("SUPPLEMENTAL", None, _section("safety_education", "신호등을 보고 건너요.", ["annex6:traffic_safety:1"]),
         ("2026-09-W2", "SAFETY_PLACEMENT_MISMATCH", "OFFICIAL_REF_IN_SUPPLEMENTAL_SLOT", "SUPPLEMENTAL", "official:traffic_safety")),
        ("SUPPLEMENTAL", None, _section("safety_education", "자전거를 탈 때는 안전모를 써요.", ["safe-ev-1"]),
         ("2026-09-W2", "SAFETY_PLACEMENT_MISMATCH", "STATUTORY_REF_IN_SUPPLEMENTAL_SLOT", "SUPPLEMENTAL",
          "STATUTORY_REFERENCE:traffic_safety")),
    ],
    ids=["statutory-empty", "wrong-category-official", "official-missing", "wrong-sample",
         "official-in-supplemental", "statutory-ref-in-supplemental"],
)
def test_safety_findings_carry_week_and_a_stable_reason(packet, snapshot, second, w1, w2, expected):
    first = _validate(_safety_packet(packet, second=second), snapshot, _payload(w1, w2))
    again = _validate(_safety_packet(packet, second=second), snapshot, _payload(w1, w2))
    cross_week = {"SAFETY_DUPLICATE_REFERENCE", "SAFETY_DUPLICATE_CONTENT"}
    safety = [i for i in first.issues if i.code.value.startswith("SAFETY_") and i.reason and i.code.value not in cross_week]

    assert [(i.week_id, i.code.value, i.reason, i.expected, i.actual) for i in safety] == [expected]
    assert first.issues == again.issues  # deterministic


def test_rejection_log_names_week_and_reason_without_text_prompt_or_secret(packet, snapshot, caplog):
    secret_text = "비밀생성문장-이문장은로그에나오면안돼요"
    body = _payload(_section("safety_education", "", [], unresolved=True),
                    _section("safety_education", secret_text, ["safe-ev-1"]))
    fake = _Scripted(body, body)

    with caplog.at_level("INFO", logger="ssuksak.planning.planner"):
        with pytest.raises(ProposalRejectedError) as exc:
            MonthlyPlanner(fake).plan(_safety_packet(packet), snapshot)
    log = caplog.text

    assert "SAFETY_PLACEMENT_MISMATCH@2026-09-W1/safety_education reason=STATUTORY_SLOT_EMPTY" in log
    assert "reason=STATUTORY_REF_IN_SUPPLEMENTAL_SLOT expected=SUPPLEMENTAL actual=STATUTORY_REFERENCE:traffic_safety" in log
    assert {i.reason for i in exc.value.issues} >= {"STATUTORY_SLOT_EMPTY", "STATUTORY_REF_IN_SUPPLEMENTAL_SLOT"}
    for forbidden in (secret_text, "safety_plan fixes every week", "자전거를 탈 때 안전모를 써요", "Authorization", "api_key"):
        assert forbidden not in log


# ---------------------------------------------------------------- one core topic per cell (focus / primary / quality)

from ssuksak.planning.planner.service import REPAIRABLE_CODES  # noqa: E402

OTHER_LIFE = _sample("safe-ev-4", "[생활안전] 계단에서는 조심조심 걸어요")
FOCUS_REFERENCES = {
    **REFERENCES,
    "safe-ev-2": SafetyReferenceContext("safe-ev-2", SafetyReferenceKind.SUPPLEMENTAL_REFERENCE,
                                        supplemental_label="life_safety", topic_group="stairs_railing"),
    "safe-ev-4": SafetyReferenceContext("safe-ev-4", SafetyReferenceKind.SUPPLEMENTAL_REFERENCE,
                                        supplemental_label="life_safety", topic_group="stairs"),
}


def _focused_packet(packet):
    evidence = (TRAFFIC_SAMPLE, LIFE_SAMPLE, OTHER_LIFE)
    slots = (
        SafetySlotContext("2026-09-W1", SafetyKind.STATUTORY, "traffic_safety", focus_ref="annex6:traffic_safety:4"),
        SafetySlotContext("2026-09-W2", SafetyKind.SUPPLEMENTAL, primary_ref="safe-ev-2"),
    )
    return replace(
        packet,
        safety=SafetyContext("ssuksak-safety-placement-v2", LEGAL, "monthly-safety-retrieval-v0.3.0", slots, TRAFFIC,
                             evidence, tuple(FOCUS_REFERENCES[item.evidence_ref] for item in evidence)),
    )


def _focus_codes(packet, snapshot, w1=None, w2=None):
    result = _validate(_focused_packet(packet), snapshot, _payload(w1, w2))
    return [(i.week_id, i.code.value, i.reason) for i in result.issues if i.code.value.startswith("SAFETY_")]


def test_one_focus_and_one_primary_are_valid(packet, snapshot):
    w1 = _section("safety_education", "바퀴 달린 탈것을 탈 때는 안전모를 써요.", ["annex6:traffic_safety:4", "safe-ev-1"])

    assert _focus_codes(packet, snapshot, w1) == []


@pytest.mark.parametrize(
    ("w1", "w2", "expected"),
    [
        (_section("safety_education", "신호등을 보고 건너요.", ["annex6:traffic_safety:1"]), None,
         ("2026-09-W1", "SAFETY_FOCUS_MISMATCH", "NON_FOCUS_OFFICIAL_REF")),
        (_section("safety_education", "바퀴 달린 탈것과 신호등을 알아요.", ["annex6:traffic_safety:4", "annex6:traffic_safety:1"]),
         None, ("2026-09-W1", "SAFETY_FOCUS_MISMATCH", "NON_FOCUS_OFFICIAL_REF")),
        (None, _section("safety_education", "계단에서는 조심조심 걸어요.", ["safe-ev-4"]),
         ("2026-09-W2", "SAFETY_FOCUS_MISMATCH", "PRIMARY_REF_MISSING")),
        (None, _section("safety_education", "계단에서는 난간을 잡아요.", ["safe-ev-2", "safe-ev-4"]),
         ("2026-09-W2", "SAFETY_FOCUS_MISMATCH", "NON_PRIMARY_REF")),
        (None, _section("safety_education", "", [], unresolved=True),
         ("2026-09-W2", "SAFETY_CELL_UNRESOLVED", "SUPPLEMENTAL_SLOT_EMPTY")),
        (None, _section("safety_education", "계단에서는 난간을 잡아요. 천천히 걸어요.", ["safe-ev-2"]),
         ("2026-09-W2", "SAFETY_MULTIPLE_SENTENCES", "MULTIPLE_SENTENCES")),
        (_section("safety_education", "계단에서는 난간을 잡아요.", ["annex6:traffic_safety:4"]),
         _section("safety_education", "계단에서는 난간을 잡아요.", ["safe-ev-2"]),
         ("2026-09-W2", "SAFETY_DUPLICATE_CONTENT", "SAME_TEXT_AS_OTHER_WEEK")),
    ],
    ids=["other-official-item", "two-official-items", "primary-missing", "non-primary-ref", "supplemental-empty",
         "two-sentences", "duplicate-text"],
)
def test_cells_must_express_exactly_their_slot_focus(packet, snapshot, w1, w2, expected):
    assert expected in _focus_codes(packet, snapshot, w1, w2)


def test_too_many_statutory_samples_are_a_grounding_mismatch(packet, snapshot):
    samples = tuple(_sample(f"safe-ev-t{i}", f"[교통안전] 교통 예시 {i}") for i in range(3))
    focused = _focused_packet(packet)
    references = focused.safety.references + tuple(
        SafetyReferenceContext(s.evidence_ref, SafetyReferenceKind.STATUTORY_REFERENCE, "traffic_safety") for s in samples
    )
    focused = replace(focused, safety=replace(focused.safety, evidence=focused.safety.evidence + samples, references=references))
    w1 = _section("safety_education", "바퀴 달린 탈것은 조심해요.", ["annex6:traffic_safety:4", *(s.evidence_ref for s in samples)])
    result = _validate(focused, snapshot, _payload(w1))

    assert ("SAFETY_GROUNDING_MISMATCH", "TOO_MANY_SAMPLE_REFS") in [(i.code.value, i.reason) for i in result.issues]


def test_quality_and_focus_findings_are_repairable_but_an_empty_cell_is_not():
    assert {"SAFETY_FOCUS_MISMATCH", "SAFETY_MULTIPLE_SENTENCES", "SAFETY_DUPLICATE_CONTENT",
            "SAFETY_DUPLICATE_REFERENCE"} <= REPAIRABLE_CODES
    assert not {"SAFETY_CELL_UNRESOLVED", "SAFETY_PLACEMENT_MISMATCH"} & REPAIRABLE_CODES


def test_the_prompt_names_one_focus_and_one_primary_per_week(packet, snapshot):
    weeks = json.loads(build_monthly_planning_request(_focused_packet(packet), snapshot).user_content)["safety_plan"]["weeks"]

    assert weeks[1]["primary_ref"] == "safe-ev-2" and weeks[1]["supplemental_label"] == "life_safety"
    assert weeks[1]["sample_refs"] == ["safe-ev-2"]
    assert "exactly one Korean sentence about one" in SAFETY_SYSTEM_PROMPT


# ---------------------------------------------------------------- safety reference_id is always null (prompt v4)

from ssuksak.planning.planner.contracts import MONTHLY_SAFETY_PROMPT_VERSION as SAFETY_V4  # noqa: E402


def _safety_branch(schema, section_key="safety_education"):
    items = schema["properties"]["weeks"]["items"]["properties"]["sections"]["items"]
    return next(b for b in items["anyOf"] if b["properties"]["section_key"]["enum"] == [section_key])


def test_safety_schema_branch_allows_only_a_null_reference_id(packet, snapshot):
    schema = monthly_response_schema(build_monthly_planning_request(_focused_packet(packet), snapshot))

    assert _safety_branch(schema)["properties"]["reference_id"] == {"type": "null"}
    assert _safety_branch(schema, "outdoor_play")["properties"]["reference_id"] == {"type": ["string", "null"]}
    assert schema["properties"]["month_sections"]["items"]["properties"]["reference_id"] == {"type": ["string", "null"]}


@pytest.mark.parametrize(
    ("week", "reference_id", "actual"),
    [("2026-09-W2", "safe-ev-2", "non_null"), ("2026-09-W1", "annex6:traffic_safety:4", "annex6"), ("2026-09-W1", "act-1", "non_null")],
    ids=["sample-id", "official-annex-ref", "activity-id"],
)
def test_a_safety_reference_id_is_rejected_whatever_it_holds(packet, snapshot, week, reference_id, actual):
    w1 = _section("safety_education", "바퀴 달린 탈것을 탈 때는 안전모를 써요.", ["annex6:traffic_safety:4"])
    w2 = _section("safety_education", "계단을 오르내릴 때는 난간을 꼭 잡아요.", ["safe-ev-2"])
    target = w1 if week.endswith("W1") else w2
    target["reference_id"] = reference_id
    result = _validate(_focused_packet(packet), snapshot, _payload(w1, w2))
    found = [(i.week_id, i.code.value, i.reason, i.expected, i.actual) for i in result.issues if i.field == "safety_education"]

    assert (week, "UNKNOWN_REFERENCE_ID", "SAFETY_REFERENCE_ID_FORBIDDEN", "null", actual) in found
    assert "UNKNOWN_REFERENCE_ID" not in REPAIRABLE_CODES


def test_null_safety_reference_ids_with_grounding_refs_are_valid(packet, snapshot):
    w1 = _section("safety_education", "바퀴 달린 탈것을 탈 때는 안전모를 써요.", ["annex6:traffic_safety:4"])
    w2 = _section("safety_education", "계단을 오르내릴 때는 난간을 꼭 잡아요.", ["safe-ev-2"])

    assert [i for i in _validate(_focused_packet(packet), snapshot, _payload(w1, w2)).issues if i.field == "safety_education"] == []


def test_non_safety_reference_ids_keep_their_contract(packet, snapshot):
    outdoor = _payload()
    week = outdoor["weeks"][0]["sections"][1]
    assert week["reference_id"] == "act-1"  # activity reference stays valid
    assert not [i for i in _validate(_focused_packet(packet), snapshot, outdoor).issues if i.field == "outdoor_play"]
    week["reference_id"] = "invented"
    codes = [(i.code.value, i.reason) for i in _validate(_focused_packet(packet), snapshot, outdoor).issues if i.field == "outdoor_play"]
    assert ("UNKNOWN_REFERENCE_ID", None) in codes


def test_initial_and_repair_prompts_carry_the_same_reference_id_contract(packet, snapshot):
    rejected = _payload(_section("safety_education", "자전거를 탈 때 안전모를 써요.", ["safe-ev-1"]))
    fake = _Scripted(rejected, _payload(), _payload())
    MonthlyPlanner(fake).plan(_safety_packet(packet), snapshot)
    initial, repair = fake.monthly_requests
    contract = "For safety_education, reference_id is always null"

    assert initial.prompt_version == SAFETY_V4 == "monthly-planner-safety-v4"
    assert repair.prompt_version == "monthly-planner-safety-repair-v4"
    assert contract in initial.system_prompt and contract in repair.system_prompt
    assert "only in\ngrounding_refs" in SAFETY_SYSTEM_PROMPT
