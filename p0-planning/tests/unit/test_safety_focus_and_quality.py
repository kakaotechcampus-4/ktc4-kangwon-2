from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json

import pytest

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.monthly_reference_repositories import (
    JsonSafetyLegalRuleRepository,
    JsonSafetyPlacementPolicyRepository,
)
from ssuksak.adapters.safety_evidence_classification_repository import JsonSafetyEvidenceClassificationRepository
from ssuksak.adapters.safety_reference_quality_repository import (
    DEFAULT_SAFETY_QUALITY_PATH,
    SafetyReferenceQualityError,
    load_safety_quality_from_dict,
)
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.models import SourceSection
from ssuksak.planning.evidence.safety_quality import body_key_of
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods
from ssuksak.planning.rules.safety_placement import (
    month_safety_slots,
    official_content_focus,
    policy_violations,
    select_supplemental_primaries,
)

LEGAL = JsonSafetyLegalRuleRepository().get_legal_rule("child-welfare-act-decree-annex6-2022-06-21")
POLICIES = JsonSafetyPlacementPolicyRepository()
V1 = POLICIES.get_policy("ssuksak-safety-placement-v1")
V2 = POLICIES.get_policy("ssuksak-safety-placement-v2")
SCHOOL_YEAR_2026 = tuple(YearMonth(2026, m) for m in range(3, 13)) + (YearMonth(2027, 1), YearMonth(2027, 2))

# The resolved focus table of focus_rule for school year 2026 (official item numbers).
FOCUS_2026 = {
    "traffic_safety": {3: 1, 5: 2, 7: 3, 9: 4, 11: 5, 1: 6},
    "missing_and_abduction_prevention": {4: 1, 7: 2, 10: 3, 1: 4},
    "infectious_disease_and_drug_misuse_prevention": {5: 1, 8: 2, 11: 3, 2: 4},
    "sexual_violence_prevention": {3: 1, 9: 2},
    "child_abuse_prevention": {6: 1, 12: 2},
    "disaster_preparedness_safety": {8: 1, 2: 2},
}


def _statutory_focus(policy, months):
    return {
        (slot.placement.category_id, month.calendar_month): slot.placement.official_content_focus_ref
        for month in months
        for slot in month_safety_slots(
            replace(policy, runtime_active=True), month,
            tuple(p for p in canonical_week_periods(month) if p.active), LEGAL,
        )
        if slot.placement.category_id
    }


def test_v2_keeps_v1_placements_adds_a_focus_rule_and_is_approved():
    assert V1.runtime_active and V2.runtime_active
    assert V2.entries == V1.entries and V2.focus_rule == "OFFICIAL_ORDER_ROTATING_BY_SCHOOL_YEAR"
    assert V2.base_school_year == 2026 and V1.focus_rule is None
    assert policy_violations(V2, LEGAL) == ()


def test_focus_rule_resolves_to_the_documented_2026_table():
    resolved = _statutory_focus(V2, SCHOOL_YEAR_2026)

    assert resolved == {
        (category, month): f"annex6:{category}:{item}"
        for category, months in FOCUS_2026.items()
        for month, item in months.items()
    }
    assert resolved[("traffic_safety", 9)] == "annex6:traffic_safety:4"  # 바퀴 달린 탈것의 안전한 이용법


def test_focus_rotates_into_the_next_school_year_without_dropping_items():
    for category, months in FOCUS_2026.items():
        items = len(LEGAL.category(category).content_items)
        years = -(-items // len(months))  # enough school years to reach every item
        covered = {
            official_content_focus(V2, LEGAL, category, YearMonth(2026 + y + (1 if m < 3 else 0), m))
            for y in range(years)
            for m in months
        }
        assert covered == {f"annex6:{category}:{i}" for i in range(1, items + 1)}, category
    # traffic (6 placements, 6 items) and missing (4, 4) cover every item each year.
    assert Counter(ref for (cat, _), ref in _statutory_focus(V2, SCHOOL_YEAR_2026).items() if cat == "traffic_safety")
    assert len({ref for (cat, _), ref in _statutory_focus(V2, SCHOOL_YEAR_2026).items() if cat == "traffic_safety"}) == 6


def test_v1_slots_have_no_focus():
    assert set(_statutory_focus(V1, SCHOOL_YEAR_2026).values()) == {None}


def test_focus_policy_needs_the_legal_rule():
    month = YearMonth(2026, 9)
    with pytest.raises(ValueError, match="legal Rule"):
        month_safety_slots(V2, month, tuple(p for p in canonical_week_periods(month) if p.active))


# ---------------------------------------------------------------- supplemental primary selection


def test_primaries_are_distinct_topics_and_prefer_unused_labels():
    candidates = (
        ("a", "life_safety", "crowd"), ("b", "life_safety", "crowd"), ("c", "life_safety", "stairs"),
        ("d", "digital_safety", "smartphone"), ("e", "fire_safety", "electricity"),
    )

    assert select_supplemental_primaries(3, candidates) == (("a", ("b",)), ("d", ()), ("e", ()))
    assert select_supplemental_primaries(3, candidates) == select_supplemental_primaries(3, candidates)


def test_same_label_different_topics_is_allowed_and_too_few_topics_fails():
    candidates = (("a", "life_safety", "crowd"), ("b", "life_safety", "stairs"))

    assert select_supplemental_primaries(2, candidates) == (("a", ()), ("b", ()))
    with pytest.raises(ValueError, match="only 2 available"):
        select_supplemental_primaries(3, candidates)


# ---------------------------------------------------------------- quality review artifact


def _quality_payload():
    return json.loads(DEFAULT_SAFETY_QUALITY_PATH.read_text(encoding="utf-8"))


def test_quality_review_is_approved_and_covers_every_single_tag_supplemental_content():
    quality = load_safety_quality_from_dict(_quality_payload())
    store = JsonInstitutionEvidenceRepository().get_store()
    classification = JsonSafetyEvidenceClassificationRepository().get_classification()
    contents = {
        body_key_of(r.text)
        for r in store.records
        if r.source_section is SourceSection.SAFETY_EDUCATION and r.general_grounding_eligible and r.text
        and (ref := classification.runtime_reference(r)) is not None and ref.supplemental_label
    }

    assert quality.runtime_active
    assert {entry.body_key for entry in quality.entries} == contents
    assert Counter(entry.quality.value for entry in quality.entries) == {"USABLE": 19, "EXCLUDED": 13}
    quality.require_bound_to(store.content_sha256, classification.classification_version)
    pending = load_safety_quality_from_dict({**_quality_payload(), "review": {**_quality_payload()["review"],
        "domain_owner_approval": "PENDING_HUMAN_REVIEW", "runtime_active": False}})
    assert all(pending.usable_topic_group(r) is None for r in store.records)  # PENDING fails closed


@pytest.mark.parametrize(
    ("text", "group"),
    [
        ("[생활안전] 사람이 많이 모이는 곳을 조심해요", "crowd"),
        ("[생활안전] 승강기", None),  # TITLE_ONLY
        ("[생활안전교육] 엄마, 아빠 조심해요", None),  # MEANING_UNCLEAR
        ("[생활안전] 새로 나온 내용", None),  # unlisted → EXCLUDED default
        ("[생활안전]", None),  # EMPTY_BODY
    ],
    ids=["usable", "title-only", "unclear", "unlisted", "empty-body"],
)
def test_approved_quality_gates_supplemental_contents(text, group):
    payload = _quality_payload()
    payload["review"] = {**payload["review"], "domain_owner_approval": "HUMAN_APPROVED",
                         "approved_by": "reviewer_test_001", "approved_at": "2026-09-26T00:00:00+09:00",
                         "runtime_active": True}
    quality = load_safety_quality_from_dict(payload)
    record = next(r for r in JsonInstitutionEvidenceRepository().get_store().records
                  if r.source_section is SourceSection.SAFETY_EDUCATION)

    assert quality.usable_topic_group(replace(record, activity_text=text or None, experience_text=None)) == group


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["entries"][0].update(reason="BAD_REASON", quality="EXCLUDED", topic_group=None),
        lambda p: next(e for e in p["entries"] if e["quality"] == "USABLE").update(topic_group=None),
        lambda p: p["entries"].append(dict(p["entries"][0])),
        lambda p: p.update(default_quality="USABLE"),
        lambda p: p["review"].update(domain_owner_approval="PENDING_HUMAN_REVIEW"),
    ],
    ids=["undeclared-reason", "usable-without-topic", "duplicate", "usable-default", "active-without-approval"],
)
def test_malformed_quality_reviews_are_rejected(mutate):
    payload = _quality_payload()
    mutate(payload)

    with pytest.raises(SafetyReferenceQualityError):
        load_safety_quality_from_dict(payload)


def test_cross_month_candidates_come_after_every_target_month_topic():
    candidates = (
        ("x1", "digital_safety", "smartphone", 1),
        ("t1", "life_safety", "crowd", 0),
        ("t2", "life_safety", "stairs", 0),
        ("x2", "fire_safety", "electricity", 1),
    )

    # Target-month topics win even though a cross-month topic would add a new label.
    assert select_supplemental_primaries(3, candidates) == (("t1", ()), ("t2", ()), ("x1", ()))


def test_two_refs_of_one_topic_count_as_one_topic():
    candidates = (
        ("a", "life_safety", "internet_media_use", 0),
        ("b", "life_safety", "internet_media_use", 1),
        ("c", "digital_safety", "smartphone_use", 1),
    )

    assert select_supplemental_primaries(2, candidates) == (("a", ("b",)), ("c", ()))
    with pytest.raises(ValueError, match="only 2 available"):
        select_supplemental_primaries(3, candidates)
