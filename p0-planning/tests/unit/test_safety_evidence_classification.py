from __future__ import annotations

from collections import Counter
from dataclasses import replace
import copy
import json

import pytest

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.monthly_reference_repositories import JsonSafetyLegalRuleRepository
from ssuksak.adapters.safety_evidence_classification_repository import (
    DEFAULT_SAFETY_CLASSIFICATION_PATH,
    SAFETY_CLASSIFICATION_V0_1_0_PATH,
    SafetyEvidenceClassificationError,
    load_safety_classification_from_dict,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.safety_placement import SafetyKind, SafetyPlacement
from ssuksak.planning.evidence.models import SourceSection
from ssuksak.planning.evidence.safety_classification import (
    SafetyClassificationEntry,
    SafetyReferenceKind,
    item_tag_of,
    reference_supports,
)

LEGAL = "child-welfare-act-decree-annex6-2022-06-21"
KINDS = SafetyReferenceKind
STORE = JsonInstitutionEvidenceRepository().get_store()
SAFETY = tuple(r for r in STORE.records if r.source_section is SourceSection.SAFETY_EDUCATION)


def _payload():
    """The approved v0.1.0 artifact (kept unchanged)."""
    return json.loads(SAFETY_CLASSIFICATION_V0_1_0_PATH.read_text(encoding="utf-8"))


def _payload_v2():
    return json.loads(DEFAULT_SAFETY_CLASSIFICATION_PATH.read_text(encoding="utf-8"))


def _approve(payload):
    payload["review"] = {
        **payload["review"],
        "domain_owner_approval": "HUMAN_APPROVED",
        "approved_by": "reviewer_test_001",
        "approved_at": "2026-09-26T00:00:00+09:00",
        "runtime_active": True,
    }
    return load_safety_classification_from_dict(payload)


def _approved():
    payload = _payload()
    payload["review"] = {
        **payload["review"],
        "domain_owner_approval": "HUMAN_APPROVED",
        "approved_by": "reviewer_test_001",
        "approved_at": "2026-09-26T00:00:00+09:00",
        "runtime_active": True,
    }
    return load_safety_classification_from_dict(payload)


def _record(text):
    return replace(SAFETY[0], activity_text=text, experience_text=None)


def _placement(kind, category=None):
    return SafetyPlacement(kind, category, "ssuksak-safety-placement-v1", LEGAL)


def _pending():
    payload = _payload()
    payload["review"] = {
        **payload["review"],
        "domain_owner_approval": "PENDING_HUMAN_REVIEW",
        "approved_by": None,
        "approved_at": None,
        "runtime_active": False,
    }
    return payload


def test_approved_artifact_activates_only_statutory_and_supplemental_references():
    classification = load_safety_classification_from_dict(_payload())
    references = [classification.runtime_reference(record) for record in SAFETY]
    usable = [ref for ref in references if ref is not None]

    assert classification.runtime_active
    assert len(usable) == 440
    assert {ref.kind for ref in usable} == {KINDS.STATUTORY_REFERENCE, KINDS.SUPPLEMENTAL_REFERENCE}
    assert Counter(ref.supplemental_label for ref in usable if ref.supplemental_label) == {
        "life_safety": 68, "fire_safety": 8, "digital_safety": 4
    }
    assert classification.supplemental_labels == {"life_safety", "fire_safety", "digital_safety"}


def test_pending_artifact_loads_for_review_but_is_never_used_at_runtime():
    classification = load_safety_classification_from_dict(_pending())

    assert not classification.runtime_active
    assert all(classification.runtime_reference(record) is None for record in SAFETY)
    classification.require_bound_to(STORE.content_sha256)
    classification.require_legal_rule(JsonSafetyLegalRuleRepository().get_legal_rule(LEGAL))


def test_every_observed_item_tag_is_classified_exactly_once_and_counts_are_stable():
    classification = load_safety_classification_from_dict(_payload())
    observed = {item_tag_of(record.text) for record in SAFETY} - {None}
    kinds = Counter(classification.classify(record).kind for record in SAFETY)
    categories = Counter(classification.classify(record).legal_category_id for record in SAFETY)

    assert {entry.item_tag for entry in classification.entries} == observed
    assert len(SAFETY) == 1845
    assert kinds == {KINDS.STATUTORY_REFERENCE: 360, KINDS.SUPPLEMENTAL_REFERENCE: 80, KINDS.NEEDS_REVIEW: 1405}
    assert {key: value for key, value in categories.items() if key} == {
        "traffic_safety": 106,
        "missing_and_abduction_prevention": 60,
        "infectious_disease_and_drug_misuse_prevention": 52,
        "sexual_violence_prevention": 45,
        "child_abuse_prevention": 27,
        "disaster_preparedness_safety": 70,
    }


@pytest.mark.parametrize(
    ("text", "kind", "category", "label"),
    [
        ("[교통안전] 자전거를 탈 때 안전모를 써요", KINDS.STATUTORY_REFERENCE, "traffic_safety", None),
        ("  [ 교통안전 ] 신호등을 봐요", KINDS.STATUTORY_REFERENCE, "traffic_safety", None),
        ("[소방안전] 불이 나면 코와 입을 막아요", KINDS.SUPPLEMENTAL_REFERENCE, None, "fire_safety"),
        ("[생활안전] 계단에서 뛰지 않아요", KINDS.SUPPLEMENTAL_REFERENCE, None, "life_safety"),
        ("[성폭력 및 아동학대] 내 몸은 소중해요", KINDS.NEEDS_REVIEW, None, None),
        ("[비상대응훈련] 지진이 나면 몸을 낮춰요", KINDS.NEEDS_REVIEW, None, None),
        ("[교통안전교육 활동] 길 건너기", KINDS.NEEDS_REVIEW, None, None),  # no substring match
        ("(교통안전) 길 건너기", KINDS.NEEDS_REVIEW, None, None),  # round tags are not item tags
        ("교통안전교육 - 신호등아 고마워", KINDS.NEEDS_REVIEW, None, None),  # untagged
    ],
    ids=["exact", "exact-spaced-variant", "fire-is-not-disaster", "life", "composite", "emergency-key",
         "no-substring", "round-tag", "untagged"],
)
def test_classification_is_exact_on_the_leading_item_tag(text, kind, category, label):
    entry = load_safety_classification_from_dict(_payload()).classify(_record(text))

    assert (entry.kind, entry.legal_category_id, entry.supplemental_label) == (kind, category, label)


def test_classification_ignores_entry_order():
    payload = _payload()
    reversed_payload = copy.deepcopy(payload)
    reversed_payload["entries"].reverse()
    forward = load_safety_classification_from_dict(payload)
    backward = load_safety_classification_from_dict(reversed_payload)

    assert [forward.classify(r) for r in SAFETY] == [backward.classify(r) for r in SAFETY]


def test_artifact_entries_are_in_deterministic_order():
    order = {"STATUTORY_REFERENCE": 0, "SUPPLEMENTAL_REFERENCE": 1, "NEEDS_REVIEW": 2}
    entries = _payload()["entries"]

    assert entries == sorted(
        entries,
        key=lambda e: (order[e["kind"]], e["legal_category_id"] or e["supplemental_label"] or "", e["item_tag"]),
    )


def _mutated(mutate):
    payload = _payload()
    mutate(payload)
    return payload


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(extra=True),
        lambda p: p.update(key=["source_section", "source_label"]),
        lambda p: p.update(default_kind="SUPPLEMENTAL_REFERENCE"),
        lambda p: p["review"].update(domain_owner_approval="PENDING_HUMAN_REVIEW"),
        lambda p: p["entries"].append(dict(p["entries"][0])),
        lambda p: p["entries"][0].update(kind="STATUTORY"),
        lambda p: p["entries"][0].update(legal_category_id=None),
        lambda p: p["entries"][0].update(supplemental_label="life_safety"),
        lambda p: p["entries"][-1].update(legal_category_id="traffic_safety"),
        lambda p: p["entries"][0].update(note="x"),
        lambda p: next(e for e in p["entries"] if e["kind"] == "SUPPLEMENTAL_REFERENCE").update(supplemental_label="unknown"),
    ],
    ids=["root-field", "label-key", "default-kind", "active-without-approval", "duplicate-tag", "bad-kind",
         "statutory-without-category", "statutory-with-supplemental", "review-with-category", "entry-field",
         "unknown-supplemental-label"],
)
def test_malformed_artifacts_are_rejected(mutate):
    with pytest.raises(SafetyEvidenceClassificationError):
        load_safety_classification_from_dict(_mutated(mutate))


def test_statutory_references_cannot_introduce_a_category_the_legal_rule_lacks():
    payload = _mutated(lambda p: p["entries"][0].update(legal_category_id="fire_drill"))

    with pytest.raises(InvalidDomainValueError, match="Not legal categories"):
        load_safety_classification_from_dict(payload).require_legal_rule(
            JsonSafetyLegalRuleRepository().get_legal_rule(LEGAL)
        )


def test_references_support_only_matching_placements_and_never_change_them():
    classification = _approved()
    traffic = classification.runtime_reference(_record("[교통안전] 자전거를 탈 때 안전모를 써요"))
    life = classification.runtime_reference(_record("[생활안전] 계단에서 뛰지 않아요"))
    review = classification.runtime_reference(_record("[비상대응훈련] 몸을 낮춰요"))
    traffic_slot = _placement(SafetyKind.STATUTORY, "traffic_safety")

    assert review is None  # NEEDS_REVIEW is never a runtime Reference
    assert reference_supports(traffic, traffic_slot)
    assert not reference_supports(traffic, _placement(SafetyKind.STATUTORY, "sexual_violence_prevention"))
    assert not reference_supports(traffic, _placement(SafetyKind.SUPPLEMENTAL))
    # A supplemental Reference can never ground (and so never count as) a statutory session.
    assert not reference_supports(life, traffic_slot)
    assert reference_supports(life, _placement(SafetyKind.SUPPLEMENTAL))
    assert traffic_slot == _placement(SafetyKind.STATUTORY, "traffic_safety")


def test_entry_kinds_enforce_their_fields():
    with pytest.raises(InvalidDomainValueError):
        SafetyClassificationEntry("교통안전", KINDS.SUPPLEMENTAL_REFERENCE, legal_category_id="traffic_safety")
    with pytest.raises(InvalidDomainValueError):
        SafetyClassificationEntry("비상대응", KINDS.NEEDS_REVIEW, supplemental_label="life_safety")


# ---------------------------------------------------------------- v0.2.0 multi-tag fail-closed


def test_v0_2_0_supersedes_v0_1_0_with_the_same_entries_and_is_approved():
    v1, v2 = _payload(), _payload_v2()
    approved = load_safety_classification_from_dict(v2)
    v2["review"] = {**v2["review"], "domain_owner_approval": "PENDING_HUMAN_REVIEW", "runtime_active": False}
    pending = load_safety_classification_from_dict(v2)

    assert v2["supersedes"] == v1["classification_version"] == "safety-evidence-classification-v0.1.0"
    assert v2["classification_version"] == "safety-evidence-classification-v0.2.0"
    assert v2["entries"] == v1["entries"] and v1["review"]["domain_owner_approval"] == "HUMAN_APPROVED"
    assert approved.runtime_active and approved.multi_tag_needs_review
    assert _payload_v2()["review"]["approved_by"] == "reviewer_ai_lead_001"
    assert all(pending.runtime_reference(record) is None for record in SAFETY)


@pytest.mark.parametrize(
    ("text", "was"),
    [
        ("[생활안전] 물놀이 안전 수칙 [소방대피훈련] 장마철 누전으로 인한 화재", KINDS.SUPPLEMENTAL_REFERENCE),
        ("[교통안전] 길 건너기 [생활안전] 승강기", KINDS.STATUTORY_REFERENCE),
    ],
    ids=["supplemental", "statutory"],
)
def test_multi_tag_records_become_needs_review(text, was):
    v1 = load_safety_classification_from_dict(_payload())
    v2 = _approve(_payload_v2())

    assert v1.classify(_record(text)).kind is was
    assert v2.classify(_record(text)).kind is KINDS.NEEDS_REVIEW
    assert v2.runtime_reference(_record(text)) is None


def test_single_tag_records_keep_their_v0_1_0_classification():
    v1 = load_safety_classification_from_dict(_payload())
    v2 = _approve(_payload_v2())
    single = [r for r in SAFETY if len(__import__("re").findall(r"\[[^\[\]]+\]", r.text or "")) <= 1]
    usable = [v2.runtime_reference(r) for r in SAFETY]

    assert all(v1.classify(r) == v2.classify(r) for r in single)
    assert Counter(v2.classify(r).kind for r in SAFETY) == {
        KINDS.STATUTORY_REFERENCE: 331, KINDS.SUPPLEMENTAL_REFERENCE: 62, KINDS.NEEDS_REVIEW: 1452
    }
    assert sum(ref is not None for ref in usable) == 393


def test_schema_v1_requires_the_multi_tag_rule():
    payload = _payload_v2()
    payload["multi_tag_rule"] = "SPLIT_TAGS"

    with pytest.raises(SafetyEvidenceClassificationError, match="multi_tag_rule"):
        load_safety_classification_from_dict(payload)
