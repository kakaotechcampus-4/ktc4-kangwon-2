"""Activity Reference v0.2.1 승인본 / Activation 검증.

검증 축:
- 승인 Artifact가 존재하고 `HUMAN_APPROVED`다
- Draft → Approved 사이에 **승인 metadata 외 의미 변경이 없다**
- Production default가 v0.2.1로 전환됐다
- 과거 승인본 v0.2.0이 **정확히 그 version을 요청받았을 때만** 여전히 해소된다
- v0.2.0 파일은 바이트 단위로 불변이다
- Demo가 Production과 같은 승인 Artifact를 쓴다
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from ssuksak.adapters.json_activity_reference_repository import (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    LEGACY_ACTIVITY_CATALOG_PATH,
    SUPERSEDED_ACTIVITY_CATALOG_PATHS,
    JsonActivityReferenceRepository,
    production_activity_reference_repository,
)
from ssuksak.planning.domain.activity_reference import ActivationStatus

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "activities"
V0_2_0 = DATA / "activity_reference_v0_2.json"
V0_2_1_DRAFT = DATA / "activity_reference_v0_2_1_draft.json"
V0_2_1 = DATA / "activity_reference_v0_2_1.json"

CATALOG_ID = "ssuksak.outdoor-activity-reference"
VER_0 = "activity-reference-v0.2.0"
VER_1 = "activity-reference-v0.2.1"
OUTDOOR = "outdoor_play"

V0_2_0_SHA = "e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6"
DRAFT_SHA = "a3ec9f7956bf84fb6a510605dfff6064627de5482b1e56dc584e2ceb734f608a"

REVIEWER = "reviewer_ai_lead_001"


@pytest.fixture(scope="module")
def approved() -> dict:
    return json.loads(V0_2_1.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def draft() -> dict:
    return json.loads(V0_2_1_DRAFT.read_text(encoding="utf-8"))


# ============================================== 1. Human Approval


def test_approved_artifact_exists_and_is_human_approved(approved):
    assert approved["catalog_version"] == VER_1
    assert approved["review"]["domain_owner_approval"] == "HUMAN_APPROVED"
    assert approved["review"]["approved_by"] == REVIEWER
    assert approved["review"]["approved_at"]
    assert approved["review"]["pending_reason"] is None
    assert len(approved["activities"]) == 196


def test_reviewer_id_follows_the_opaque_convention(approved):
    """`reviewer_<role>_<sequence>` (OD-N10). 로그인 user_id도 fixture도 아니다."""
    parts = approved["review"]["approved_by"].split("_")
    assert parts[0] == "reviewer" and parts[-1].isdigit()
    assert approved["review"]["approved_by"] == json.loads(
        V0_2_0.read_text(encoding="utf-8")
    )["review"]["approved_by"], "기존 승인 Convention과 같은 Reviewer다"


def test_approved_at_is_kst_iso8601(approved):
    from datetime import datetime

    at = datetime.fromisoformat(approved["review"]["approved_at"])
    assert at.utcoffset() is not None
    assert at.utcoffset().total_seconds() == 9 * 3600


def test_approval_records_the_exact_draft_it_came_from(approved):
    got = approved["review"]["approved_from"]
    assert got["draft_path"] == "data/activities/activity_reference_v0_2_1_draft.json"
    assert got["draft_sha256"] == DRAFT_SHA
    assert hashlib.sha256(V0_2_1_DRAFT.read_bytes()).hexdigest() == DRAFT_SHA


def test_approval_note_cites_both_review_documents(approved):
    docs = approved["review"]["review_document"]
    assert "docs/analysis/monthly-quality-patch-1-review.md" in docs
    assert "docs/analysis/activity-v0-2-1-setting-audit.md" in docs


# ============================================== 2. Draft → Approved Semantic Diff


def test_activities_block_is_byte_for_byte_identical(draft, approved):
    assert json.dumps(draft["activities"], ensure_ascii=False, sort_keys=True) == (
        json.dumps(approved["activities"], ensure_ascii=False, sort_keys=True)
    )


@pytest.mark.parametrize(
    "field",
    ["activity_id", "label", "supported_ages", "applicable_months", "setting",
     "evidence", "display_quality", "display_quality_review_status",
     "origin_id", "source_version", "label_derivation_type"],
)
def test_per_activity_axis_is_unchanged(draft, approved, field):
    a = {x["activity_id"]: x.get(field) for x in draft["activities"]}
    b = {x["activity_id"]: x.get(field) for x in approved["activities"]}
    assert a == b


def test_correction_metadata_is_unchanged(draft, approved):
    def corr(cat):
        return {
            x["activity_id"]: (
                x.get("correction_type"),
                x.get("supersedes_activity_ids"),
                x.get("source_reference"),
            )
            for x in cat["activities"]
        }

    assert corr(draft) == corr(approved)


def test_only_approval_metadata_differs_at_top_level(draft, approved):
    allowed = {"$schema_note", "draft", "draft_note", "approved_from_draft", "review"}
    changed = {
        k for k in set(draft) | set(approved)
        if json.dumps(draft.get(k), ensure_ascii=False, sort_keys=True)
        != json.dumps(approved.get(k), ensure_ascii=False, sort_keys=True)
    }
    assert changed <= allowed, f"승인 metadata 밖의 변경: {sorted(changed - allowed)}"


def test_lineage_blocks_are_unchanged(draft, approved):
    for key in ("origins", "coverage", "exclusion_policy", "setting_semantics",
                "evidence_semantics", "age_semantics", "taxonomy_scope",
                "source_of_truth_refs", "safety_exclusion_statement"):
        assert draft[key] == approved[key], key


# ============================================== 3. v0.2.0 Freeze


def test_v0_2_0_is_byte_for_byte_unchanged():
    assert hashlib.sha256(V0_2_0.read_bytes()).hexdigest() == V0_2_0_SHA


def test_draft_file_is_byte_for_byte_unchanged():
    assert hashlib.sha256(V0_2_1_DRAFT.read_bytes()).hexdigest() == DRAFT_SHA


# ============================================== 4. Production Default


def test_production_default_is_v0_2_1():
    assert DEFAULT_ACTIVITY_CATALOG_PATH == V0_2_1


def test_default_repository_resolves_v0_2_1_as_active():
    cat = JsonActivityReferenceRepository().get_catalog(CATALOG_ID, VER_1)
    assert cat is not None
    assert cat.activation_status is ActivationStatus.HUMAN_APPROVED
    assert cat.is_active
    assert len(cat.activities) == 196


def test_default_repository_still_serves_september_candidates():
    cat = JsonActivityReferenceRepository().get_catalog(CATALOG_ID, VER_1)
    for ages in (frozenset({3}), frozenset({4}), frozenset({5})):
        assert cat.eligible_candidates(
            section_key=OUTDOOR, calendar_month=9, ages=ages
        )


# ============================================== 5. Superseded pin 해소


def test_v0_2_0_stays_resolvable_from_the_production_repository():
    """Default가 바뀌어도 기존 Plan이 pin한 version은 그대로 찾아야 한다."""
    repo = production_activity_reference_repository()
    old = repo.get_catalog(CATALOG_ID, VER_0)
    assert old is not None
    assert old.catalog_version == VER_0
    assert old.is_active
    assert len(old.activities) == 198


def test_production_repository_serves_both_versions_distinctly():
    repo = production_activity_reference_repository()
    assert repo.get_catalog(CATALOG_ID, VER_1).catalog_version == VER_1
    assert repo.get_catalog(CATALOG_ID, VER_0).catalog_version == VER_0


def test_superseded_list_is_exactly_the_previous_approved_file():
    assert SUPERSEDED_ACTIVITY_CATALOG_PATHS == (V0_2_0,)


def test_unknown_version_is_not_silently_upgraded_to_the_default():
    """해소 실패는 실패다. default로 대체하지 않는다."""
    repo = production_activity_reference_repository()
    assert repo.get_catalog(CATALOG_ID, "activity-reference-v0.9.9") is None
    assert repo.get_catalog(CATALOG_ID, "activity-reference-v0.2.0-draft") is None
    assert repo.get_catalog("other.catalog", VER_1) is None


def test_v0_1_0_is_not_reachable_from_the_production_repository():
    repo = production_activity_reference_repository()
    assert repo.get_catalog(CATALOG_ID, "activity-reference-v0.1.0") is None
    explicit = JsonActivityReferenceRepository(
        LEGACY_ACTIVITY_CATALOG_PATH
    ).get_catalog(CATALOG_ID, "activity-reference-v0.1.0")
    assert explicit is not None and not explicit.is_active


def test_bare_repository_does_not_gain_superseded_resolution():
    """`superseded_paths`를 주지 않으면 기존 단일 파일 동작 그대로다."""
    assert JsonActivityReferenceRepository().get_catalog(CATALOG_ID, VER_0) is None


# ============================================== 6. Demo default


def test_demo_uses_the_same_approved_artifact_as_production():
    """Demo 전용 Fake Catalog를 만들지 않는다."""
    composition = (
        pathlib.Path(__file__).resolve().parents[2]
        / "demo-planning" / "backend" / "composition.py"
    ).read_text(encoding="utf-8")
    assert "production_activity_reference_repository()" in composition
    assert "DEFAULT_ACTIVITY_CATALOG_PATH" in composition
    assert "InMemoryActivityReferenceRepository" not in composition


# ============================================== 7. Quality metadata 유지


def test_traditional_play_survives_activation_with_soft_penalty_only():
    cat = JsonActivityReferenceRepository().get_catalog(CATALOG_ID, VER_1)
    trad = next(a for a in cat.activities if a.label == "전통놀이")
    assert trad.display_quality.value == "TOO_GENERIC"
    assert trad.display_quality_review_status.value == "HUMAN_CONFIRMED"
    assert trad.has_confirmed_display_issue
    pool = cat.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({5})
    )
    assert any(c.activity_id == trad.activity_id for c in pool), (
        "Hard Exclusion이 아니다. 후보에는 남고 순위에서만 밀린다"
    )


def test_only_traditional_play_carries_a_confirmed_display_issue():
    cat = JsonActivityReferenceRepository().get_catalog(CATALOG_ID, VER_1)
    flagged = [a.label for a in cat.activities if a.has_confirmed_display_issue]
    assert flagged == ["전통놀이"]


@pytest.mark.parametrize(
    "label", ["건너기", "장화 신고 물웅덩이", "우리집에 왜 왔니?", "놀이를 해요."]
)
def test_fragment_activities_are_absent_from_the_production_default(label):
    cat = JsonActivityReferenceRepository().get_catalog(CATALOG_ID, VER_1)
    assert label not in {a.label for a in cat.activities}


@pytest.mark.parametrize(
    "label", ["장화 신고 물웅덩이 건너기", "우리집에 왜 왔니? 놀이를 해요."]
)
def test_restored_activities_are_present_in_the_production_default(label):
    cat = JsonActivityReferenceRepository().get_catalog(CATALOG_ID, VER_1)
    assert label in {a.label for a in cat.activities}


# ============================================== 8. Coverage regression


@pytest.mark.parametrize("month", list(range(1, 13)))
@pytest.mark.parametrize(
    "ages", [frozenset({3}), frozenset({4}), frozenset({5}),
             frozenset({3, 4}), frozenset({3, 5}), frozenset({4, 5})]
)
def test_no_month_age_combination_lost_all_candidates_after_activation(month, ages):
    repo = production_activity_reference_repository()
    before = repo.get_catalog(CATALOG_ID, VER_0)
    after = repo.get_catalog(CATALOG_ID, VER_1)
    nb = len(before.eligible_candidates(
        section_key=OUTDOOR, calendar_month=month, ages=ages))
    na = len(after.eligible_candidates(
        section_key=OUTDOOR, calendar_month=month, ages=ages))
    if nb > 0:
        assert na > 0, f"{month}월 만{sorted(ages)}세 후보가 0이 되었다"
    assert nb - na <= 1, f"{month}월 만{sorted(ages)}세 후보가 {nb}→{na}로 과도하게 줄었다"
