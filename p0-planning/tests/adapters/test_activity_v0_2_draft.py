"""Activity Reference v0.2.0-draft 구조 검증 (Draft 전용).

이 테스트는 **Draft 파일의 구조만** 검증한다. runtime에 연결하지 않으며
Production selector / Composition Root / M2-C dependency를 건드리지 않는다.

검증 축:
- v0.1.0 기준 파일이 변경되지 않았다
- Draft가 현재 ActivityCatalog Contract를 만족한다 (draft 전용 필드 제외 후)
- Draft는 PENDING_HUMAN_REVIEW이며 runtime 후보를 내지 않는다
- 기존 49개가 삭제·재작성되지 않았다
- 월·연령을 근거보다 넓게 주장하지 않는다
- HD-1 보류 근거로 supported_ages를 넓히지 않았다
- 자동 merge / LLM tagging의 흔적이 없다
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib

import pytest

from ssuksak.adapters.activity_reference_schema import (
    ActivityReferenceSchemaError,
    parse_activity_reference_payload,
)
from ssuksak.planning.domain.activity_reference import ActivationStatus

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "activities"
BASE_PATH = DATA / "activity_reference_v0.json"
DRAFT_PATH = DATA / "activity_reference_v0_2_draft.json"

BASE_SHA = "b565254f6668aeea04ef4ddce235ef51fd7af80d258d568e2f4d31fae6648b0d"

# Draft 전용(검토용) 필드. Contract 검증 시 제거한다.
ACTIVITY_DRAFT_FIELDS = {
    "draft_status", "draft_delta", "alias_candidates_pending_review",
    "observed_institution_count", "observed_institutions",
    "age_support_basis", "age_support_review_required", "draft_review_flags",
    "evidence_count", "origins_used", "draft_exclusion",
    "hd_g_verdict", "hd_g_reason",
}
EVIDENCE_DRAFT_FIELDS = {"age_evidence_basis"}
TOP_DRAFT_FIELDS = {"draft", "draft_note", "pending_human_review"}


@pytest.fixture(scope="module")
def draft() -> dict:
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def base() -> dict:
    return json.loads(BASE_PATH.read_text(encoding="utf-8"))


def core_projection(payload: dict) -> dict:
    """draft 전용 필드를 제거한 Contract 검증용 사본."""
    core = copy.deepcopy(payload)
    for k in TOP_DRAFT_FIELDS:
        core.pop(k, None)
    for a in core["activities"]:
        for k in ACTIVITY_DRAFT_FIELDS:
            a.pop(k, None)
        for e in a["evidence"]:
            for k in EVIDENCE_DRAFT_FIELDS:
                e.pop(k, None)
    return core


# --------------------------------------------------- v0.1.0 불변


def test_base_catalog_file_is_unchanged():
    actual = hashlib.sha256(BASE_PATH.read_bytes()).hexdigest()
    assert actual == BASE_SHA


def test_base_catalog_is_still_pending(base):
    assert base["review"]["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"
    assert base["review"]["approved_by"] is None
    assert len(base["activities"]) == 49


def test_draft_is_a_separate_file():
    assert DRAFT_PATH.exists()
    assert DRAFT_PATH != BASE_PATH


# ------------------------------------------------- Draft 메타


def test_draft_declares_itself_as_draft(draft):
    assert draft["draft"] is True
    assert draft["catalog_version"] == "activity-reference-v0.2.0-draft"
    assert draft["supersedes"] == "activity-reference-v0.1.0"
    assert draft["review"]["base_catalog"]["unchanged"] is True


def test_draft_is_pending_with_no_approver(draft):
    assert draft["review"]["domain_owner_approval"] == "PENDING_HUMAN_REVIEW"
    assert draft["review"]["approved_by"] is None
    assert draft["review"]["approved_at"] is None
    assert draft["review"]["pending_reason"]


def test_draft_declares_no_runtime_active_field(draft):
    assert "runtime_active" not in draft
    assert "activation_status" not in draft
    for a in draft["activities"]:
        assert "runtime_active" not in a


# ----------------------------------------- Contract 적합성


def test_draft_core_projection_parses(draft):
    cat = parse_activity_reference_payload(core_projection(draft))
    assert cat.catalog_version == "activity-reference-v0.2.0-draft"
    assert len(cat.activities) == len(draft["activities"])


def test_draft_is_inactive_and_yields_no_candidates(draft):
    cat = parse_activity_reference_payload(core_projection(draft))
    assert cat.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert not cat.is_active
    for month in range(1, 13):
        for ages in (frozenset({3}), frozenset({4}), frozenset({5}), frozenset({3, 4, 5})):
            assert cat.eligible_candidates(
                section_key="outdoor_play", calendar_month=month, ages=ages
            ) == ()


def test_draft_raw_payload_is_rejected_by_strict_schema(draft):
    """draft 전용 필드가 들어간 원본은 현재 strict schema가 거부한다."""
    with pytest.raises(ActivityReferenceSchemaError):
        parse_activity_reference_payload(draft)


def test_draft_month_coverage_is_full_year(draft):
    cat = parse_activity_reference_payload(core_projection(draft))
    assert set(cat.month_coverage) == set(range(1, 13))


def test_draft_is_sample_derived_non_normative(draft):
    assert draft["normative_status"] == "SAMPLE_DERIVED_NON_NORMATIVE"


# -------------------------------------- 기존 49개 보존 (§4)


def test_all_base_activity_ids_are_carried_over(draft, base):
    base_ids = {a["activity_id"] for a in base["activities"]}
    draft_ids = {a["activity_id"] for a in draft["activities"]}
    assert base_ids <= draft_ids
    assert len(base_ids) == 49


def test_carried_over_labels_are_unchanged(draft, base):
    d = {a["activity_id"]: a for a in draft["activities"]}
    for a in base["activities"]:
        assert d[a["activity_id"]]["label"] == a["label"]


def test_carried_over_aliases_are_not_silently_extended(draft, base):
    """aliases는 Human Review 승인 전에는 늘리지 않는다."""
    d = {a["activity_id"]: a for a in draft["activities"]}
    for a in base["activities"]:
        assert d[a["activity_id"]]["aliases"] == a["aliases"]


def test_alias_candidates_are_kept_pending_not_merged(draft):
    pending = [a for a in draft["activities"] if a.get("alias_candidates_pending_review")]
    assert pending, "alias 후보가 있으면 보류 필드로 남아 있어야 한다"
    for a in pending:
        for cand in a["alias_candidates_pending_review"]:
            assert cand not in a["aliases"]


def test_carried_over_evidence_is_never_removed(draft, base):
    d = {a["activity_id"]: a for a in draft["activities"]}
    for a in base["activities"]:
        assert len(d[a["activity_id"]]["evidence"]) >= len(a["evidence"])


def test_every_activity_has_draft_status(draft):
    allowed = {"CARRIED_OVER_UNCHANGED", "CARRIED_OVER_WITH_NEW_EVIDENCE", "NEW_CANDIDATE"}
    for a in draft["activities"]:
        assert a["draft_status"] in allowed


# ----------------------------- 근거보다 넓게 주장하지 않음 (§5 §9)


def test_applicable_months_never_exceed_observed(draft):
    for a in draft["activities"]:
        observed = {e["observed_month"] for e in a["evidence"] if e.get("observed_month")}
        assert set(a["applicable_months"]) <= observed, a["activity_id"]


def test_supported_ages_never_exceed_observed(draft):
    for a in draft["activities"]:
        observed = {x for e in a["evidence"] for x in e["age_scope"]}
        assert set(a["supported_ages"]) <= observed, a["activity_id"]


def test_hd1_unresolved_evidence_carries_empty_age_scope(draft):
    """HD-1 보류 근거는 age applicability를 넓힐 수 없다."""
    seen = 0
    for a in draft["activities"]:
        for e in a["evidence"]:
            if e.get("age_evidence_basis") == "HD1_UNRESOLVED_MIXED_LIKELY_UNMARKED":
                assert e["age_scope"] == []
                seen += 1
    assert seen > 0, "HD-1 보류 evidence가 Draft에 기록돼 있어야 한다"


def test_age_support_basis_is_recorded_for_every_supported_age(draft):
    for a in draft["activities"]:
        basis = a.get("age_support_basis", {})
        for age in a["supported_ages"]:
            assert str(age) in basis, (a["activity_id"], age)


def test_mixed_only_age_support_is_flagged(draft):
    """혼합 근거만으로 지원되는 연령은 반드시 표시된다."""
    for a in draft["activities"]:
        weak = [k for k, v in a.get("age_support_basis", {}).items()
                if v == "MIXED_AGE_EVIDENCE_ONLY"]
        if weak:
            assert a.get("age_support_review_required") == sorted(weak), a["activity_id"]


# ----------------------------------------- 병합·태깅 금지 (§7 §10 §11)


def test_no_curriculum_links_were_invented(draft):
    assert sum(len(a["curriculum_links"]) for a in draft["activities"]) == 0


def test_every_theme_link_uses_observed_together(draft):
    themes = json.loads(
        (DATA.parent / "themes" / "theme_reference_v0.json").read_text(encoding="utf-8")
    )
    known = {t["theme_id"] for t in themes["themes"]}
    version = themes["catalog_version"]
    seen = 0
    for a in draft["activities"]:
        for link in a["theme_links"]:
            assert link["relation"] == "OBSERVED_TOGETHER"
            assert link["theme_catalog_version"] == version
            assert link["theme_id"] in known
            seen += 1
    assert seen > 0


def test_placement_and_setting_stay_outdoor_only(draft):
    for a in draft["activities"]:
        assert a["placement_slots"] == ["outdoor_play"], a["activity_id"]
        assert a["setting"] == "OUTDOOR", a["activity_id"]


def test_no_safety_fields_anywhere(draft):
    for a in draft["activities"]:
        assert "safety_flags" not in a
        assert "activity_area" not in a
        assert "tags" not in a
        assert "safety_education" not in a["placement_slots"]


def test_activity_ids_and_labels_are_unique(draft):
    ids = [a["activity_id"] for a in draft["activities"]]
    labels = [a["label"] for a in draft["activities"]]
    assert len(set(ids)) == len(ids)
    assert len(set(labels)) == len(labels)


# ------------------------------------------ pending list (§6 §12)


def test_ambiguous_items_are_pending_not_canonical(draft):
    amb = draft["pending_human_review"]["ambiguous_items"]
    assert len(amb) == 8
    labels = {a["label"] for a in draft["activities"]}
    for item in amb:
        assert item["observed_label"] not in labels


def test_hd1_items_are_listed_for_review(draft):
    assert draft["pending_human_review"]["hd1_unresolved_age_items"]


def test_skipped_candidates_are_recorded(draft):
    skipped = draft["pending_human_review"]["new_candidates_skipped_no_age_evidence"]
    assert skipped
    for s in skipped:
        assert s["reason"]


def test_exclusion_summary_is_preserved(draft):
    summary = draft["exclusion_policy"]["v0_2_summary"]
    assert summary["SAFETY_BOUNDARY_EXCLUDE"] == 0
    assert summary["INDOOR_ALTERNATIVE_EXCLUDE"] > 0
    assert draft["exclusion_policy"]["excluded_items_v0_1_0"]
    assert draft["exclusion_policy"]["durumi_exclusion"]


# ------------------------------------------------- origins


def test_all_evidence_origins_are_declared(draft):
    declared = {o["origin_id"] for o in draft["origins"]}
    for a in draft["activities"]:
        assert a["origin_id"] in declared, a["activity_id"]
        for e in a["evidence"]:
            assert e["origin_id"] in declared, (a["activity_id"], e["origin_id"])


def test_origin_sha256_matches_repository_files(draft):
    root = DATA.parents[1]
    for o in draft["origins"]:
        p = root / o["path"]
        assert p.exists(), o["path"]
        assert hashlib.sha256(p.read_bytes()).hexdigest().upper() == o["sha256"], o["origin_id"]


def test_origins_are_monthly_samples_only(draft):
    for o in draft["origins"]:
        assert o["kind"] == "MONTHLY_PLAN_SAMPLE"
        assert o["path"].startswith("references/samples/monthly/")
        for token in ("http", "www.", "키드키즈", "꼬망세"):
            assert token not in json.dumps(o, ensure_ascii=False)


# --------------------------------- Production 무연결 (§14)


def test_draft_is_not_wired_into_the_default_repository():
    """Draft는 production 경로가 아니다. 기본 경로는 승인본 v0.2.1이다."""
    from ssuksak.adapters.json_activity_reference_repository import (
        DEFAULT_ACTIVITY_CATALOG_PATH,
    )

    assert (
        DEFAULT_ACTIVITY_CATALOG_PATH.name == "activity_reference_v0_2_1.json"
    )


def test_legacy_repository_still_returns_v0_1_0():
    from ssuksak.adapters.json_activity_reference_repository import (
        LEGACY_ACTIVITY_CATALOG_PATH,
        JsonActivityReferenceRepository,
    )

    cat = JsonActivityReferenceRepository(
        LEGACY_ACTIVITY_CATALOG_PATH
    ).get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.1.0"
    )
    assert cat is not None
    assert len(cat.activities) == 49
    assert not cat.is_active


def test_draft_version_is_not_resolvable_from_default_repository():
    from ssuksak.adapters.json_activity_reference_repository import (
        JsonActivityReferenceRepository,
    )

    assert JsonActivityReferenceRepository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.0-draft"
    ) is None


# ============================================ Human Decision HD-A ~ HD-F


def test_hd_a_mixed_evidence_counts_but_basis_is_distinguished(draft):
    """HD-A: 명시 혼합 근거는 age evidence로 인정하되 강도를 구별한다."""
    allowed = {"SINGLE_AGE_EVIDENCE", "MIXED_AGE_EVIDENCE_ONLY",
               "SINGLE_AND_MIXED", "CARRIED_FROM_V0_1_0"}
    seen_mixed_only = 0
    for a in draft["activities"]:
        for age, basis in a.get("age_support_basis", {}).items():
            assert basis in allowed, (a["activity_id"], age, basis)
            if basis == "MIXED_AGE_EVIDENCE_ONLY":
                seen_mixed_only += 1
    assert seen_mixed_only > 0
    assert draft["age_semantics"]["hd_a_rule"]


def test_hd_b_seojin_evidence_never_widens_supported_ages(draft):
    """HD-B: 서진 만4.5세반은 age applicability 근거가 아니다."""
    for a in draft["activities"]:
        for e in a["evidence"]:
            if e.get("age_evidence_basis") == "HD1_UNRESOLVED_MIXED_LIKELY_UNMARKED":
                assert e["age_scope"] == [], (a["activity_id"], e["origin_id"])


def test_hd_c_ambiguous_items_are_not_approval_candidates(draft):
    amb = draft["pending_human_review"]["ambiguous_items"]
    assert len(amb) == 8
    labels = {a["label"] for a in draft["activities"]}
    for item in amb:
        assert item["observed_label"] not in labels


def test_hd_d_section_label_echo_is_excluded_but_preserved(draft):
    excluded = draft["pending_human_review"]["section_label_echo_excluded"]
    assert len(excluded) == 1
    item = excluded[0]
    assert item["label"] == "실외놀이"
    assert item["exclusion"] == "SECTION_LABEL_ECHO_EXCLUDE"
    assert item["evidence"], "원문 Observation은 보존해야 한다"
    assert item["label"] not in {a["label"] for a in draft["activities"]}


def test_hd_g_safety_adjacent_verdicts_are_applied(draft):
    """HD-G: 구체적 outdoor action/play/object가 있으면 편입, 없으면 제외."""
    ph = draft["pending_human_review"]
    included = ph["safety_adjacent_included_hd_g"]
    excluded = ph["safety_adjacent_excluded_hd_g"]
    assert len(included) == 3
    assert len(excluded) == 2

    labels = {a["label"] for a in draft["activities"]}
    assert {i["label"] for i in included} == {
        "안전 관련 표지판 찾아보며 산책하기",
        "안전 약속 지키며 놀이기구 타기",
        "훌라후프로 안전하게 놀아요",
    }
    assert {e["label"] for e in excluded} == {
        "바깥놀이를 안전하게 해요",
        "안전하게 놀이해요",
    }
    for i in included:
        assert i["hd_g_verdict"] == "INCLUDE_AS_ACTIVITY"
        assert i["label"] in labels, "편입 항목은 canonical에 있어야 한다"
    for e in excluded:
        assert e["hd_g_verdict"] == "EXCLUDE"
        assert e["exclusion"] == "SAFETY_ADJACENT_EXCLUDE_HD_G"
        assert e["label"] not in labels
        assert e["evidence"], "원문 Observation은 보존해야 한다"


def test_hd_g_included_items_keep_verbatim_wording(draft):
    """'안전'을 제거하거나 표현을 일반화하지 않았다."""
    ph = draft["pending_human_review"]
    for i in ph["safety_adjacent_included_hd_g"]:
        assert "안전" in i["label"]
    ids = {i["activity_id"] for i in ph["safety_adjacent_included_hd_g"]}
    by_id = {a["activity_id"]: a for a in draft["activities"]}
    for aid in ids:
        a = by_id[aid]
        assert a["hd_g_verdict"] == "INCLUDE_AS_ACTIVITY"
        assert a["aliases"] == [], "기존 canonical과 merge하지 않았다"
        assert a["label_derivation_type"] == "DIRECT_TRANSCRIPTION"


def test_hd_h_ambiguous_stay_pending_and_are_not_a_blocker(draft):
    """HD-H: AMBIGUOUS 8건은 v0.2 승인 blocker가 아니며 pending에 보존된다."""
    amb = draft["pending_human_review"]["ambiguous_items"]
    assert len(amb) == 8
    labels = {a["label"] for a in draft["activities"]}
    for item in amb:
        assert item["observed_label"] not in labels
    assert draft["coverage"]["ambiguous_pending_count"] == 8


def test_hd_f_single_institution_items_are_kept(draft):
    """HD-F: institution_count == 1 은 제외 조건이 아니다."""
    singles = [a for a in draft["activities"] if a["observed_institution_count"] == 1]
    assert len(singles) > 0
    assert draft["coverage"]["single_institution_only_items"] == len(singles)


def test_every_activity_carries_provenance_counts(draft):
    """HD-F: provenance(기관 수·evidence 수·origins)를 모든 item이 유지한다."""
    for a in draft["activities"]:
        assert a["observed_institution_count"] >= 1
        assert a["evidence_count"] == len(a["evidence"])
        assert a["origins_used"]
        assert set(a["origins_used"]) == {e["origin_id"] for e in a["evidence"]}


# ================================================= 용어 분리 (§2) / 통계 (§3)


def test_carried_over_and_reproduced_are_reported_separately(draft):
    c = draft["coverage"]
    assert c["carried_over_existing_items"] == 49
    assert c["reproduced_with_new_corpus_evidence"] == 36
    assert c["reobserved_but_evidence_already_present"] == 6
    assert c["carried_over_existing_items"] != c["reproduced_with_new_corpus_evidence"]


def test_age_support_strength_is_reported_per_age(draft):
    c = draft["coverage"]
    for age in (3, 4, 5):
        total = c[f"items_supporting_age{age}"]
        single = c[f"items_with_single_age{age}_evidence"]
        mixed = c[f"items_age{age}_from_mixed_evidence_only"]
        assert single + mixed == total, age


def test_item_count_matches_activities(draft):
    c = draft["coverage"]
    assert c["item_count"] == len(draft["activities"])
    assert c["carried_over_item_count"] + c["new_item_count"] == c["item_count"]
    assert c["new_candidates_excluded_by_hd_d_hd_g"] == 3
    assert c["safety_adjacent_included_count"] == 3
    assert c["safety_adjacent_excluded_count"] == 2
    assert c["section_label_excluded_count"] == 1
