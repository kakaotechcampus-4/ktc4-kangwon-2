from __future__ import annotations

import json
from pathlib import Path

import pytest

from ssuksak.adapters.json_curriculum_reference_repository import (
    CurriculumReferenceError,
    parse_curriculum_payload,
)

PROJECT_ROOT = Path(__file__).parents[2]
DRAFT = PROJECT_ROOT / "data" / "curriculum" / "nuri_curriculum_content_v0_1_0_draft.json"


def _load() -> dict:
    return json.loads(DRAFT.read_text(encoding="utf-8"))


def test_draft_matches_official_counts():
    doc = _load()
    domains = doc["domains"]

    assert [d["name"] for d in domains] == [
        "신체운동·건강",
        "의사소통",
        "사회관계",
        "예술경험",
        "자연탐구",
    ]
    assert all(len(d["categories"]) == 3 for d in domains)
    assert [sum(len(c["contents"]) for c in d["categories"]) for d in domains] == [
        12,
        12,
        12,
        10,
        13,
    ]
    assert doc["derived_totals"]["contents"] == 59


def test_ids_follow_the_order_rule_and_are_unique():
    ids = []
    for d, domain in enumerate(_load()["domains"], 1):
        assert domain["domain_id"] == f"nuri2019.{d}"
        for c, category in enumerate(domain["categories"], 1):
            assert category["category_id"] == f"nuri2019.{d}.{c}"
            for k, content in enumerate(category["contents"], 1):
                assert content["content_id"] == f"nuri2019.{d}.{c}.{k}"
                assert content["text"].strip() == content["text"]
                assert content["text"].endswith("다.")
                ids.append(content["content_id"])

    assert len(ids) == len(set(ids)) == 59


def test_reference_is_runtime_active_after_human_review():
    # 하민(reviewer_ai_lead_01) approved v0.1.0 on 2026-10-29; only the review fields changed.
    review = _load()["review"]

    assert review["domain_owner_approval"] == "HUMAN_APPROVED"
    assert review["runtime_active"] is (
        review["domain_owner_approval"] == "HUMAN_APPROVED"
    )


def _with_review(approval, runtime_active) -> dict:
    doc = _load()  # in memory only; the file itself is not changed
    doc["review"].update(domain_owner_approval=approval, runtime_active=runtime_active)
    return doc


@pytest.mark.parametrize(
    ("approval", "runtime_active"),
    [
        ("HUMAN_APPROVED", False),
        ("PENDING_HUMAN_REVIEW", True),
        ("HUMAN_APPROVED", "true"),
        ("human_approved", True),
        (None, False),
    ],
)
def test_runtime_active_must_be_derived_from_the_approval(approval, runtime_active):
    with pytest.raises(CurriculumReferenceError):
        parse_curriculum_payload(_with_review(approval, runtime_active))


def test_consistent_review_metadata_parses():
    assert parse_curriculum_payload(_with_review("HUMAN_APPROVED", True)).is_active
    assert not parse_curriculum_payload(_with_review("PENDING_HUMAN_REVIEW", False)).is_active
    assert parse_curriculum_payload(_load()).is_active
