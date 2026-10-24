from __future__ import annotations

import json
from pathlib import Path

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


def test_draft_is_not_runtime_active_before_human_review():
    review = _load()["review"]

    assert review["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"
    assert review["runtime_active"] is (
        review["domain_owner_approval"] == "HUMAN_APPROVED"
    )
