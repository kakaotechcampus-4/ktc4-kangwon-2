from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.safety_reference_quality_repository import (
    DEFAULT_SAFETY_QUALITY_PATH,
    SafetyReferenceQualityError,
    load_safety_quality_from_dict,
)
from ssuksak.planning.evidence.models import SourceSection

RECORD = next(
    r for r in JsonInstitutionEvidenceRepository().get_store().records if r.source_section is SourceSection.SAFETY_EDUCATION
)


def _payload():
    return json.loads(DEFAULT_SAFETY_QUALITY_PATH.read_text(encoding="utf-8"))


def _record(text):
    return replace(RECORD, activity_text=text, experience_text=None)


def test_every_usable_candidate_has_a_month_scope_and_excluded_ones_none():
    payload = _payload()
    usable = [e for e in payload["entries"] if e["quality"] == "USABLE"]

    assert payload["review"]["domain_owner_approval"] == "HUMAN_APPROVED"
    assert payload["review"]["approved_by"] == "reviewer_ai_lead_001"
    assert all(e["month_scope"] in {"TARGET_MONTH_ONLY", "MONTH_INDEPENDENT"} and e["month_scope_reason"] for e in usable)
    assert all(e["month_scope"] is None for e in payload["entries"] if e["quality"] == "EXCLUDED")
    # Human review: content itself has no season/month/event dependency.
    assert {e["month_scope"] for e in usable} == {"MONTH_INDEPENDENT"}
    assert {e["topic_group"] for e in usable if e["topic_group"] in {"crowd", "eating_safely"}} == {"crowd", "eating_safely"}


def test_month_independence_comes_only_from_the_approved_review():
    payload = _payload()
    payload["review"] = {**payload["review"], "domain_owner_approval": "PENDING_HUMAN_REVIEW", "runtime_active": False}
    stairs = _record("[생활안전교육] 계단에서는 조심조심")
    crowd = _record("[생활안전] 사람이 많이 모이는 곳을 조심해요")

    assert load_safety_quality_from_dict(payload).month_independent_topic_group(stairs) is None  # PENDING
    payload["review"] = {**payload["review"], "domain_owner_approval": "HUMAN_APPROVED",
                         "approved_by": "reviewer_test_001", "approved_at": "2026-09-26T00:00:00+09:00",
                         "runtime_active": True}
    approved = load_safety_quality_from_dict(payload)
    assert approved.month_independent_topic_group(stairs) == "stairs"
    assert approved.month_independent_topic_group(crowd) == "crowd"  # re-reviewed: MONTH_INDEPENDENT
    target_only = load_safety_quality_from_dict({**payload, "entries": [
        {**e, "month_scope": "TARGET_MONTH_ONLY"} if e["topic_group"] == "crowd" else e for e in payload["entries"]]})
    assert target_only.month_independent_topic_group(crowd) is None
    assert target_only.usable_topic_group(crowd) == "crowd"
    assert approved.month_independent_topic_group(_record("[생활안전] 승강기")) is None  # EXCLUDED


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: next(e for e in p["entries"] if e["quality"] == "USABLE").update(month_scope=None),
        lambda p: next(e for e in p["entries"] if e["quality"] == "EXCLUDED").update(month_scope="MONTH_INDEPENDENT"),
        lambda p: next(e for e in p["entries"] if e["quality"] == "USABLE").update(month_scope="ANY_MONTH"),
        lambda p: p.update(month_scopes=["ANY_MONTH"]),
    ],
    ids=["usable-without-scope", "excluded-with-scope", "unknown-scope", "undeclared-scopes"],
)
def test_malformed_month_scopes_are_rejected(mutate):
    payload = _payload()
    mutate(payload)

    with pytest.raises(SafetyReferenceQualityError):
        load_safety_quality_from_dict(payload)
