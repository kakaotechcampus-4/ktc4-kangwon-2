"""Activity Reference v0.2.0 승인 Catalog 검증.

이 테스트는 **승인 artifact의 상태만** 검증한다. runtime에 연결하지 않으며
Production Repository path / Composition Root / M2-C dependency를 건드리지 않는다.

검증 축:
- HUMAN_APPROVED이고 is_active가 **파생**으로 True다
- Draft와 Activity 내용이 동일하다 (승인 metadata와 source_version 제외)
- v0.1.0과 Draft 파일이 모두 보존돼 있다
- Production runtime은 여전히 v0.1.0을 바라본다
- Human Review warning이 삭제되지 않았다
- 승인본이 품질 metadata를 달고 있어 **현재 strict schema로는 그대로 로드되지
  않는다**는 사실을 명시적으로 고정한다 (M2-C 선행 과제)
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re

import pytest

from ssuksak.adapters.activity_reference_schema import (
    ActivityReferenceSchemaError,
    parse_activity_reference_payload,
)
from ssuksak.planning.domain.activity_reference import ActivationStatus

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "activities"
V1_PATH = DATA / "activity_reference_v0.json"
DRAFT_PATH = DATA / "activity_reference_v0_2_draft.json"
APPROVED_PATH = DATA / "activity_reference_v0_2.json"

V1_SHA = "b565254f6668aeea04ef4ddce235ef51fd7af80d258d568e2f4d31fae6648b0d"

ACTIVITY_META = {
    "draft_status", "draft_delta", "alias_candidates_pending_review",
    "observed_institution_count", "observed_institutions",
    "age_support_basis", "age_support_review_required", "draft_review_flags",
    "evidence_count", "origins_used", "draft_exclusion",
    "hd_g_verdict", "hd_g_reason",
}
TOP_META = {"draft", "draft_note", "pending_human_review", "approved_from_draft"}


@pytest.fixture(scope="module")
def approved() -> dict:
    return json.loads(APPROVED_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def draft() -> dict:
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def v1() -> dict:
    return json.loads(V1_PATH.read_text(encoding="utf-8"))


def core(payload: dict) -> dict:
    """품질 metadata를 제거한 runtime-equivalent 투영."""
    c = copy.deepcopy(payload)
    for k in TOP_META:
        c.pop(k, None)
    for a in c["activities"]:
        for k in ACTIVITY_META:
            a.pop(k, None)
        for e in a["evidence"]:
            e.pop("age_evidence_basis", None)
    return c


# ----------------------------------------------------- 파일 보존


def test_all_three_catalog_files_exist():
    assert V1_PATH.exists() and DRAFT_PATH.exists() and APPROVED_PATH.exists()


def test_v0_1_0_is_unchanged():
    assert hashlib.sha256(V1_PATH.read_bytes()).hexdigest() == V1_SHA


def test_v0_1_0_is_still_pending(v1):
    assert v1["review"]["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"
    assert v1["review"]["approved_by"] is None
    assert len(v1["activities"]) == 49


def test_draft_is_preserved_and_still_marked_draft(draft):
    assert draft["draft"] is True
    assert draft["catalog_version"] == "activity-reference-v0.2.0-draft"
    assert draft["review"]["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"


# ------------------------------------------------- 승인 metadata


def test_approved_catalog_metadata(approved):
    assert approved["catalog_version"] == "activity-reference-v0.2.0"
    assert approved["draft"] is False
    assert approved["supersedes"] == "activity-reference-v0.1.0"
    assert approved["approved_from_draft"] == "activity-reference-v0.2.0-draft"
    r = approved["review"]
    assert r["domain_owner_approval"] == "HUMAN_APPROVED"
    assert r["pending_reason"] is None
    assert r["approval_note"]


def test_approver_follows_od_n10_format(approved):
    by = approved["review"]["approved_by"]
    assert re.fullmatch(r"reviewer_[a-z_]+_\d{3}", by), by
    assert by == "reviewer_ai_lead_001"


def test_approved_at_is_iso8601_with_kst_offset(approved):
    at = approved["review"]["approved_at"]
    assert re.fullmatch(r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00", at), at
    # 기존 artifact의 승인 시각을 복사하지 않았다
    assert at not in ("2026-09-11T01:11:07+09:00", "2026-09-11T10:25:01+09:00")


def test_approver_matches_existing_repository_convention(approved):
    """기존 HUMAN_APPROVED artifact 3건과 같은 reviewer identifier를 쓴다."""
    others = [
        DATA.parent / "themes" / "theme_reference_v0.json",
        DATA.parent / "templates" / "monthly_template_a.json",
        DATA.parent / "rules" / "safety_education_legal_v1.json",
    ]
    for p in others:
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["review"]["approved_by"] == approved["review"]["approved_by"]


# ------------------------------------------------ activation 파생


def test_approved_catalog_is_active_by_derivation(approved):
    cat = parse_activity_reference_payload(core(approved))
    assert cat.activation_status is ActivationStatus.HUMAN_APPROVED
    assert cat.is_active is True


def test_activation_is_not_a_writable_file_field(approved):
    """is_active / runtime_active를 파일 필드로 두지 않았다."""
    assert "runtime_active" not in approved
    assert "activation_status" not in approved
    assert "is_active" not in approved
    for a in approved["activities"]:
        assert "runtime_active" not in a
        assert "is_active" not in a


def test_approved_catalog_yields_candidates_every_month(approved):
    cat = parse_activity_reference_payload(core(approved))
    for month in range(1, 13):
        got = cat.eligible_candidates(
            section_key="outdoor_play", calendar_month=month,
            ages=frozenset({3, 4, 5}),
        )
        assert len(got) > 0, month


def test_approved_catalog_still_rejects_safety_slot(approved):
    cat = parse_activity_reference_payload(core(approved))
    assert cat.eligible_candidates(
        section_key="safety_education", calendar_month=9, ages=frozenset({4})
    ) == ()


# ------------------------------------------------ 내용 불변 (§3)


def test_activities_are_content_equivalent_to_draft(approved, draft):
    a, d = copy.deepcopy(approved), copy.deepcopy(draft)
    for x in (a, d):
        for it in x["activities"]:
            it["source_version"] = "__NORM__"
    assert a["activities"] == d["activities"]


def test_supporting_sections_are_identical_to_draft(approved, draft):
    for key in ("origins", "pending_human_review", "exclusion_policy",
                "coverage", "age_semantics", "theme_link_semantics",
                "curriculum_link_semantics", "setting_semantics"):
        assert approved[key] == draft[key], key


def test_source_version_matches_catalog_version(approved):
    for a in approved["activities"]:
        assert a["source_version"] == approved["catalog_version"]


@pytest.mark.parametrize(
    "key,expected",
    [
        ("item_count", 198),
        ("carried_over_item_count", 49),
        ("carried_over_existing_items", 49),
        ("new_item_count", 149),
        ("total_evidence_count", 288),
        ("ambiguous_pending_count", 8),
        ("safety_adjacent_included_count", 3),
        ("safety_adjacent_excluded_count", 2),
        ("section_label_excluded_count", 1),
    ],
)
def test_frozen_counts(approved, key, expected):
    assert approved["coverage"][key] == expected


def test_month_and_age_coverage(approved):
    assert set(approved["coverage"]["month_coverage"]) == set(range(1, 13))
    assert approved["coverage"]["age_coverage"] == [3, 4, 5]
    assert len(approved["activities"]) == 198
    assert sum(len(a["evidence"]) for a in approved["activities"]) == 288


def test_existing_49_are_preserved_verbatim(approved, v1):
    d = {a["activity_id"]: a for a in approved["activities"]}
    for a in v1["activities"]:
        got = d[a["activity_id"]]
        assert got["label"] == a["label"]
        assert got["aliases"] == a["aliases"]
        assert len(got["evidence"]) >= len(a["evidence"])


def test_no_merge_of_any_kind(approved, v1):
    d = {a["activity_id"]: a for a in approved["activities"]}
    for a in v1["activities"]:
        assert d[a["activity_id"]]["aliases"] == a["aliases"]
    for a in approved["activities"]:
        if a["draft_status"] == "NEW_CANDIDATE":
            assert a["aliases"] == []


def test_no_curriculum_links_invented(approved):
    assert sum(len(a["curriculum_links"]) for a in approved["activities"]) == 0


def test_hd1_evidence_never_widened_supported_ages(approved):
    for a in approved["activities"]:
        for e in a["evidence"]:
            if e.get("age_evidence_basis") == "HD1_UNRESOLVED_MIXED_LIKELY_UNMARKED":
                assert e["age_scope"] == []


def test_hd_g_and_hd_h_verdicts_are_carried_into_approved(approved):
    ph = approved["pending_human_review"]
    labels = {a["label"] for a in approved["activities"]}
    assert len(ph["safety_adjacent_included_hd_g"]) == 3
    assert len(ph["safety_adjacent_excluded_hd_g"]) == 2
    assert {i["label"] for i in ph["safety_adjacent_included_hd_g"]} <= labels
    assert not {e["label"] for e in ph["safety_adjacent_excluded_hd_g"]} & labels
    assert "실외놀이" not in labels
    assert len(ph["ambiguous_items"]) == 8
    assert not {i["observed_label"] for i in ph["ambiguous_items"]} & labels


# --------------------------- Human Review warning 보존 (§4)


def test_age_evidence_warning_is_preserved(approved):
    c = approved["coverage"]
    assert c["items_supporting_age4"] == 100
    assert c["items_with_single_age4_evidence"] == 4
    assert c["items_age4_from_mixed_evidence_only"] == 96
    assert approved["age_semantics"]["age4_warning"]
    assert approved["age_semantics"]["hd_a_rule"]


def test_age_support_basis_survives_approval(approved):
    flagged = [a for a in approved["activities"] if a.get("age_support_review_required")]
    assert len(flagged) > 0
    for a in approved["activities"]:
        for age in a["supported_ages"]:
            assert str(age) in a["age_support_basis"]


def test_institution_diversity_warning_is_preserved(approved):
    c = approved["coverage"]
    assert c["single_institution_only_items"] == 178
    assert c["multi_institution_items"] == 20
    for a in approved["activities"]:
        assert a["observed_institution_count"] >= 1
        assert a["origins_used"]


def test_reproducibility_warning_data_is_preserved(approved):
    multi = [a for a in approved["activities"] if a["observed_institution_count"] >= 2]
    assert len(multi) == 20


def test_warnings_are_not_runtime_hard_gates(approved):
    """품질 metadata가 eligibility를 막지 않는다."""
    cat = parse_activity_reference_payload(core(approved))
    weak = [a for a in approved["activities"]
            if a.get("age_support_review_required") or a["observed_institution_count"] == 1]
    assert weak
    got = cat.eligible_candidates(
        section_key="outdoor_play", calendar_month=9, ages=frozenset({3})
    )
    assert got, "품질 경고가 붙은 item도 후보에 나올 수 있어야 한다"


# ------------------------- Production runtime 연결 (M2-C에서 전환)


def test_v0_2_0_is_no_longer_the_default_but_stays_resolvable():
    """2026-09-13에 default가 v0.2.1로 바뀌었다.

    v0.2.0은 default가 아니지만 **기존 Plan이 pin한 version**이므로 production
    Repository가 여전히 정확히 해소해야 한다.
    """
    from ssuksak.adapters.json_activity_reference_repository import (
        DEFAULT_ACTIVITY_CATALOG_PATH,
        SUPERSEDED_ACTIVITY_CATALOG_PATHS,
    )

    assert DEFAULT_ACTIVITY_CATALOG_PATH.name == "activity_reference_v0_2_1.json"
    assert APPROVED_PATH in SUPERSEDED_ACTIVITY_CATALOG_PATHS


def test_legacy_repository_still_returns_pending_v0_1_0():
    """v0.1.0은 보존되며 명시 경로로 여전히 PENDING·inactive로 로드된다."""
    from ssuksak.adapters.json_activity_reference_repository import (
        LEGACY_ACTIVITY_CATALOG_PATH,
        JsonActivityReferenceRepository,
    )

    repo = JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH)
    cat = repo.get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.1.0"
    )
    assert cat is not None
    assert len(cat.activities) == 49
    assert not cat.is_active


def test_v0_2_0_is_active_from_the_production_repository():
    """승인본 v0.2.0이 production Repository에서 여전히 활성으로 해소된다."""
    from ssuksak.adapters.json_activity_reference_repository import (
        production_activity_reference_repository,
    )

    cat = production_activity_reference_repository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.0"
    )
    assert cat is not None
    assert cat.is_active
    assert len(cat.activities) == 198


# ------------------- M2-C 선행 과제: 품질 metadata와 strict schema


def test_approved_file_is_not_directly_loadable_by_strict_schema(approved):
    """승인본은 per-activity 품질 metadata를 달고 있어 현재 schema가 거부한다.

    §4가 warning 보존을 요구하고 schema가 `extra="forbid"`이므로 둘이 충돌한다.
    이 사실을 숨기지 않고 고정한다. **runtime 연결(M2-C) 전에** schema 확장 또는
    runtime projection 중 하나를 사람이 결정해야 한다.
    """
    with pytest.raises(ActivityReferenceSchemaError):
        parse_activity_reference_payload(approved)


def test_runtime_projection_of_approved_file_parses_and_is_active(approved):
    """품질 metadata를 제거한 투영은 정상 로드되고 활성이다."""
    cat = parse_activity_reference_payload(core(approved))
    assert cat.is_active
    assert len(cat.activities) == 198
    assert cat.catalog_version == "activity-reference-v0.2.0"
