"""Activity Reference v0.2.1 Draft 검증 (Monthly Quality Patch 1).

검증 축:
- v0.2.0 승인본이 **바이트 단위로 불변**이다
- v0.2.1이 strict schema를 통과한다
- Source 확정 correction의 Evidence lineage가 손실 없이 이동했다
- Fragment Activity가 제거되고 원문 Activity가 생겼다
- Production default는 여전히 v0.2.0이다
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib

import pytest

from ssuksak.adapters.activity_reference_projection import (
    REVIEW_ONLY_ACTIVITY_FIELDS,
    project_runtime_payload,
)
from ssuksak.adapters.json_activity_reference_repository import (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    JsonActivityReferenceRepository,
    load_activity_catalog_from_dict,
)
from ssuksak.planning.domain.activity_reference import (
    ActivationStatus,
    ActivityDisplayQuality,
    DisplayQualityReviewStatus,
)

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "activities"
V0_2_0 = DATA / "activity_reference_v0_2.json"
V0_2_1 = DATA / "activity_reference_v0_2_1_draft.json"

CATALOG_ID = "ssuksak.outdoor-activity-reference"
V0_VERSION = "activity-reference-v0.2.0"
V1_VERSION = "activity-reference-v0.2.1"

APPROVED_SHA = "e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6"

REMOVED_FRAGMENTS = ["건너기", "장화 신고 물웅덩이", "놀이를 해요.", "우리집에 왜 왔니?"]
RESTORED = ["장화 신고 물웅덩이 건너기", "우리집에 왜 왔니? 놀이를 해요."]


@pytest.fixture(scope="module")
def raw_v1() -> dict:
    return json.loads(V0_2_1.read_text(encoding="utf-8"))


@pytest.fixture()
def payload(raw_v1) -> dict:
    return copy.deepcopy(raw_v1)


def approved(payload: dict):
    """PENDING인 Draft를 승인 상태로 바꾼 **사본**으로 로드한다.

    실제 파일은 건드리지 않는다. 승인 우회 입력이 Production에 없으므로 승인
    동작을 보려면 payload 자체를 바꿔야 한다.
    """
    p = copy.deepcopy(payload)
    p["review"]["domain_owner_approval"] = "HUMAN_APPROVED"
    p["review"]["approved_by"] = "reviewer_test_fixture_001"
    p["review"]["approved_at"] = "2026-09-13T00:00:00+09:00"
    return load_activity_catalog_from_dict(p)


# ============================================== v0.2.0 불변


def test_approved_v0_2_0_is_byte_for_byte_unchanged():
    assert hashlib.sha256(V0_2_0.read_bytes()).hexdigest() == APPROVED_SHA


def test_v0_2_0_still_loads_and_is_pending_free_of_quality_metadata():
    cat = JsonActivityReferenceRepository(V0_2_0).get_catalog(CATALOG_ID, V0_VERSION)
    assert cat is not None
    assert len(cat.activities) == 198
    assert cat.is_active
    assert all(a.display_quality is None for a in cat.activities)
    assert all(a.display_quality_review_status is None for a in cat.activities)
    assert not any(a.has_confirmed_display_issue for a in cat.activities)


def test_the_pending_draft_file_is_never_the_production_default():
    """이 Draft 파일은 승인 경로가 아니다.

    2026-09-13 승인으로 default는 `activity_reference_v0_2_1.json`(승인본)이 됐다.
    **PENDING인 이 Draft 파일**은 그때도 지금도 production 경로가 아니다.
    """
    assert DEFAULT_ACTIVITY_CATALOG_PATH.name != V0_2_1.name
    assert DEFAULT_ACTIVITY_CATALOG_PATH.name == "activity_reference_v0_2_1.json"


# ============================================== v0.2.1 기본 성질


def test_draft_is_pending_human_review(raw_v1):
    assert raw_v1["catalog_version"] == V1_VERSION
    assert raw_v1["review"]["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"
    assert raw_v1["review"]["approved_by"] is None
    assert raw_v1["review"]["approved_at"] is None


def test_draft_is_inactive_in_runtime():
    cat = JsonActivityReferenceRepository(V0_2_1).get_catalog(CATALOG_ID, V1_VERSION)
    assert cat is not None
    assert cat.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert not cat.is_active
    assert cat.eligible_candidates(
        section_key="outdoor_play", calendar_month=9, ages=frozenset({4})
    ) == ()


def test_draft_passes_strict_schema(raw_v1):
    cat = JsonActivityReferenceRepository(V0_2_1).get_catalog(CATALOG_ID, V1_VERSION)
    assert len(cat.activities) == len(raw_v1["activities"]) == 196


def test_draft_records_its_base_and_patch_identity(raw_v1):
    patch = raw_v1["review"]["patch"]
    assert patch["base_version"] == V0_VERSION
    assert patch["base_sha256"] == APPROVED_SHA
    assert raw_v1["review"]["supersedes"] == V0_VERSION


def test_unknown_field_still_fails_strict_schema(payload):
    """Projection allowlist는 고정이다. 새 미지 필드는 여전히 거부된다."""
    from ssuksak.adapters.json_activity_reference_repository import (
        ActivityReferenceSchemaError,
    )

    payload["activities"][0]["totally_unknown_field_v9"] = 1
    with pytest.raises(ActivityReferenceSchemaError):
        load_activity_catalog_from_dict(payload)


def test_correction_metadata_is_stripped_by_projection(payload):
    """correction 기록은 review-only다. runtime schema에 넘기지 않는다."""
    for f in ("correction_type", "correction_note", "supersedes_activity_ids",
              "source_reference"):
        assert f in REVIEW_ONLY_ACTIVITY_FIELDS
    projected = project_runtime_payload(payload)
    for a in projected["activities"]:
        assert "correction_type" not in a
        assert "supersedes_activity_ids" not in a
        # 반면 display_quality는 runtime 값이므로 남아야 한다
        assert "display_quality" in a


# ============================================== Source 확정 correction


@pytest.mark.parametrize("label", REMOVED_FRAGMENTS)
def test_fragment_activities_are_gone(raw_v1, label):
    assert label in {a["label"] for a in json.loads(V0_2_0.read_text("utf-8"))["activities"]}
    assert label not in {a["label"] for a in raw_v1["activities"]}


@pytest.mark.parametrize("label", RESTORED)
def test_restored_activities_exist(raw_v1, label):
    assert label in {a["label"] for a in raw_v1["activities"]}


@pytest.mark.parametrize("label", RESTORED)
def test_restored_activity_keeps_correction_provenance(raw_v1, label):
    a = next(x for x in raw_v1["activities"] if x["label"] == label)
    assert a["correction_type"] == "SOURCE_CONFIRMED_EXTRACTION_DEFECT"
    assert len(a["supersedes_activity_ids"]) == 2
    assert a["source_reference"]
    assert a["label_derivation_type"] == "DIRECT_TRANSCRIPTION"


def test_evidence_lineage_moved_without_loss(raw_v1):
    """제거된 두 조각의 evidence가 복원 Activity로 그대로 옮겨졌다."""
    old = {a["label"]: a for a in json.loads(V0_2_0.read_text("utf-8"))["activities"]}
    new = {a["label"]: a for a in raw_v1["activities"]}
    for restored, parts in (
        ("장화 신고 물웅덩이 건너기", ("장화 신고 물웅덩이", "건너기")),
        ("우리집에 왜 왔니? 놀이를 해요.", ("우리집에 왜 왔니?", "놀이를 해요.")),
    ):
        before = {
            (e["origin_id"], e["page"], e["observed_label"])
            for p in parts
            for e in old[p]["evidence"]
        }
        after = {
            (e["origin_id"], e["page"], e["observed_label"])
            for e in new[restored]["evidence"]
        }
        assert before == after, restored


def test_restored_activity_keeps_fragment_labels_as_aliases(raw_v1):
    a = next(x for x in raw_v1["activities"] if x["label"] == "장화 신고 물웅덩이 건너기")
    assert "장화 신고 물웅덩이" in a["aliases"]
    assert "건너기" in a["aliases"]


def test_item_count_matches_the_two_merges(raw_v1):
    assert len(raw_v1["activities"]) == 198 - 4 + 2


def test_false_positive_case_b_was_not_touched(raw_v1):
    """'자연물로 여름 디저트 만들기'는 v0.2.0에서 이미 정상이었다.

    설계 분석의 Case B 추정은 실제 Catalog와 대조한 결과 **결함이 아니었다.**
    """
    labels = {a["label"] for a in raw_v1["activities"]}
    assert "자연물로 여름 디저트 만들기" in labels
    assert "자연물로 여름 디저트" not in labels
    assert "만들기" not in labels


# ============================================== Display Quality metadata


def test_every_activity_has_display_quality_fields(raw_v1):
    for a in raw_v1["activities"]:
        assert a["display_quality"] in {q.value for q in ActivityDisplayQuality}
        assert a["display_quality_review_status"] in {
            s.value for s in DisplayQualityReviewStatus
        }


def test_human_confirmed_set_is_small_and_source_verified(raw_v1):
    """자동 탐지 결과를 그대로 확정으로 올리지 않았다."""
    confirmed = [
        a for a in raw_v1["activities"]
        if a["display_quality_review_status"] == "HUMAN_CONFIRMED"
    ]
    assert len(confirmed) <= 12
    issues = [a for a in confirmed if a["display_quality"] != "GOOD_STANDALONE"]
    assert [a["label"] for a in issues] == ["전통놀이"]


def test_traditional_play_is_flagged_too_generic(raw_v1):
    a = next(x for x in raw_v1["activities"] if x["label"] == "전통놀이")
    assert a["display_quality"] == "TOO_GENERIC"
    assert a["display_quality_review_status"] == "HUMAN_CONFIRMED"


def test_auto_candidates_do_not_affect_selection(payload):
    """AUTO_CANDIDATE는 runtime에서 중립이다."""
    cat = approved(payload)
    auto = [
        a for a in cat.activities
        if a.display_quality_review_status is DisplayQualityReviewStatus.AUTO_CANDIDATE
    ]
    assert auto, "AUTO_CANDIDATE 표본이 있어야 이 테스트가 의미 있다"
    assert not any(a.has_confirmed_display_issue for a in auto)


def test_only_confirmed_issue_is_penalizable(payload):
    cat = approved(payload)
    flagged = [a for a in cat.activities if a.has_confirmed_display_issue]
    assert [a.label for a in flagged] == ["전통놀이"]


# ============================================== Coverage regression


@pytest.mark.parametrize("month", list(range(1, 13)))
@pytest.mark.parametrize(
    "ages", [frozenset({3}), frozenset({4}), frozenset({5}),
             frozenset({3, 4}), frozenset({3, 5}), frozenset({4, 5})]
)
def test_no_month_age_combination_lost_all_candidates(payload, month, ages):
    """Correction 때문에 후보가 0으로 떨어진 조합이 없어야 한다."""
    before = JsonActivityReferenceRepository(V0_2_0).get_catalog(CATALOG_ID, V0_VERSION)
    after = approved(payload)
    nb = len(before.eligible_candidates(
        section_key="outdoor_play", calendar_month=month, ages=ages))
    na = len(after.eligible_candidates(
        section_key="outdoor_play", calendar_month=month, ages=ages))
    if nb > 0:
        assert na > 0, f"{month}월 만{sorted(ages)}세 후보가 0이 되었다"
    assert nb - na <= 1, f"{month}월 만{sorted(ages)}세 후보가 {nb}→{na}로 과도하게 줄었다"
