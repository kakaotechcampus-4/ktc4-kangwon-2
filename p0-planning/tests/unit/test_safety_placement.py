from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json

import pytest

from ssuksak.adapters.monthly_reference_repositories import (
    DEFAULT_SAFETY_PLACEMENT_PATH,
    JsonSafetyLegalRuleRepository,
    JsonSafetyPlacementPolicyRepository,
)
from ssuksak.adapters.safety_placement_schema import (
    SafetyPlacementPolicySchemaError,
    parse_safety_placement_payload,
)
from ssuksak.planning.application.monthly_dto import SafetyPlacementSelector
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.application.monthly_support import load_safety_placement_policy
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.safety_placement import (
    SafetyKind,
    SafetyPlacement,
    SafetyPlacementEntry,
)
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods
from ssuksak.planning.rules.safety_placement import month_safety_slots, policy_violations

LEGAL = "child-welfare-act-decree-annex6-2022-06-21"
POLICY = "ssuksak-safety-placement-v1"
SCHOOL_YEAR = tuple(YearMonth(2026, month) for month in range(3, 13)) + (YearMonth(2027, 1), YearMonth(2027, 2))
EXPECTED_MONTHS = {
    "traffic_safety": {3, 5, 7, 9, 11, 1},
    "missing_and_abduction_prevention": {4, 7, 10, 1},
    "infectious_disease_and_drug_misuse_prevention": {5, 8, 11, 2},
    "sexual_violence_prevention": {3, 9},
    "child_abuse_prevention": {6, 12},
    "disaster_preparedness_safety": {8, 2},
}


def _payload():
    return json.loads(DEFAULT_SAFETY_PLACEMENT_PATH.read_text(encoding="utf-8"))


def _rule():
    return JsonSafetyLegalRuleRepository().get_legal_rule(LEGAL)


def _policy():
    return JsonSafetyPlacementPolicyRepository().get_policy(POLICY)


class _Repository:
    def __init__(self, policy):
        self.policy = policy

    def get_policy(self, policy_version):
        return self.policy if self.policy.policy_version == policy_version else None


def _active(weeks):
    return tuple(period for period in weeks if period.active)


def test_policy_is_an_approved_product_policy_bound_to_the_legal_rule():
    policy = _policy()

    assert policy.runtime_active and policy.legal_rule_version == LEGAL
    assert {entry.category_id: set() for entry in policy.entries}.keys() == EXPECTED_MONTHS.keys()
    for category, months in EXPECTED_MONTHS.items():
        assert {entry.month for entry in policy.entries if entry.category_id == category} == months
    assert Counter(entry.category_id for entry in policy.entries) == {
        category: len(months) for category, months in EXPECTED_MONTHS.items()
    }
    assert len(policy.entries) == 20
    assert all(policy.for_month(month) for month in range(1, 13))
    assert policy_violations(policy, _rule()) == ()


def test_legal_rule_keeps_every_official_traffic_content_item():
    traffic = _rule().category("traffic_safety")

    assert len(traffic.content_items) == 6
    assert "바퀴 달린 탈것의 안전한 이용법" in traffic.content_items


def test_unapproved_policy_fails_closed_at_the_boundary_and_at_runtime():
    payload = _payload()
    payload["review"] = {**payload["review"], "domain_owner_approval": "PENDING_HUMAN_REVIEW", "runtime_active": False}
    pending = parse_safety_placement_payload(payload)

    assert not pending.runtime_active
    with pytest.raises(MonthlyApplicationError) as exc:
        load_safety_placement_policy(_Repository(pending), SafetyPlacementSelector(POLICY), _rule())
    assert exc.value.code == "safety_placement_policy_not_approved"

    payload["review"]["runtime_active"] = True  # active without approval
    with pytest.raises(SafetyPlacementPolicySchemaError, match="derived from approval"):
        parse_safety_placement_payload(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(normative_status="STATUTORY"),
        lambda payload: payload["placements"][0].update(hours=2),
        lambda payload: payload["placements"].append({"month": 3, "category_id": "traffic_safety", "week_ordinal": 3}),
    ],
    ids=["statutory-status", "extra-field", "duplicate-category-in-month"],
)
def test_schema_rejects_contract_violations(mutate):
    payload = _payload()
    mutate(payload)

    with pytest.raises(SafetyPlacementPolicySchemaError):
        parse_safety_placement_payload(payload)


def test_missing_selector_or_repository_is_explicit():
    assert load_safety_placement_policy(None, None, _rule()) is None
    with pytest.raises(MonthlyApplicationError) as exc:
        load_safety_placement_policy(None, SafetyPlacementSelector(POLICY), _rule())
    assert exc.value.code == "safety_placement_repository_required"


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda entries: tuple(e for e in entries if not (e.category_id == "traffic_safety" and e.month == 5)),
         "traffic_safety gap 4 months exceeds 2"),
        (lambda entries: tuple(e for e in entries if e.category_id != "child_abuse_prevention"),
         "child_abuse_prevention is never placed"),
        (lambda entries: entries + (SafetyPlacementEntry(4, "fire_drill", 3),), "fire_drill is not a legal category"),
    ],
    ids=["interval", "missing-category", "unknown-category"],
)
def test_policy_violations_check_intervals_and_categories(change, problem):
    policy = replace(_policy(), entries=change(_policy().entries))

    assert problem in "; ".join(policy_violations(policy, _rule()))


def test_policy_for_another_legal_version_is_invalid():
    policy = replace(_policy(), legal_rule_version="child-welfare-act-decree-annex6-2018")

    with pytest.raises(MonthlyApplicationError) as exc:
        load_safety_placement_policy(_Repository(policy), SafetyPlacementSelector(POLICY), _rule())
    assert exc.value.code == "safety_placement_policy_invalid"


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (YearMonth(2026, 9), [None, "traffic_safety", None, "sexual_violence_prevention", None]),
        (YearMonth(2026, 10), [None, "missing_and_abduction_prevention", None, None]),
    ],
    ids=["5-week", "4-week"],
)
def test_month_slots_follow_policy_week_ordinals(month, expected):
    slots = month_safety_slots(_policy(), month, _active(canonical_week_periods(month)))

    assert [slot.placement.category_id for slot in slots] == expected
    assert [slot.placement.kind for slot in slots] == [
        SafetyKind.STATUTORY if category else SafetyKind.SUPPLEMENTAL for category in expected
    ]
    assert {slot.placement.policy_version for slot in slots} == {POLICY}
    assert {slot.placement.legal_rule_version for slot in slots} == {LEGAL}


def test_school_year_statutory_slots_total_twenty_and_supplemental_never_counts():
    slots = [
        slot
        for month in SCHOOL_YEAR
        for slot in month_safety_slots(_policy(), month, _active(canonical_week_periods(month)))
    ]
    statutory = Counter(slot.placement.category_id for slot in slots if slot.placement.kind is SafetyKind.STATUTORY)
    supplemental = [slot for slot in slots if slot.placement.kind is SafetyKind.SUPPLEMENTAL]

    assert sum(statutory.values()) == 20
    assert statutory == {category: len(months) for category, months in EXPECTED_MONTHS.items()}
    assert supplemental and all(slot.placement.category_id is None for slot in supplemental)
    assert len(slots) == sum(len(_active(canonical_week_periods(month))) for month in SCHOOL_YEAR)


def test_policy_puts_one_category_in_week_two_and_two_categories_in_weeks_two_and_four():
    policy = _policy()
    for month in range(1, 13):
        ordinals = [entry.week_ordinal for entry in policy.for_month(month)]
        assert ordinals == ([2] if len(ordinals) == 1 else [2, 4]), month
    for month in SCHOOL_YEAR:  # every real 4- or 5-week month has weeks 2 and 4 active
        assert month_safety_slots(policy, month, _active(canonical_week_periods(month)))


def test_a_missing_week_four_fails_closed():
    active = _active(canonical_week_periods(YearMonth(2026, 9)))[:3]

    with pytest.raises(ValueError, match="3 active weeks; the policy needs 4"):
        month_safety_slots(_policy(), YearMonth(2026, 9), active)


def test_two_statutory_categories_cannot_share_a_week():
    with pytest.raises(InvalidDomainValueError, match="repeats a week_ordinal"):
        replace(_policy(), entries=_policy().entries + (SafetyPlacementEntry(4, "traffic_safety", 2),))


def test_a_policy_needing_more_weeks_than_the_month_has_fails_closed():
    policy = replace(_policy(), entries=_policy().entries + (SafetyPlacementEntry(10, "traffic_safety", 5),))

    with pytest.raises(ValueError, match="4 active weeks"):
        month_safety_slots(policy, YearMonth(2026, 10), _active(canonical_week_periods(YearMonth(2026, 10))))


def test_placement_kind_and_category_are_consistent():
    with pytest.raises(InvalidDomainValueError):
        SafetyPlacement(SafetyKind.STATUTORY, None, POLICY, LEGAL)
    with pytest.raises(InvalidDomainValueError):
        SafetyPlacement(SafetyKind.SUPPLEMENTAL, "traffic_safety", POLICY, LEGAL)
