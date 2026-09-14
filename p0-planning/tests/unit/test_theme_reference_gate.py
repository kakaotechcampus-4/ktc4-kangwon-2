"""Theme Reference 승인 Gate와 Reference version 검증 단위 테스트.

CLAUDE.md §8·§20 / 2026-09-10 결정 1·5.
"""

from __future__ import annotations

import json

import pytest

from ssuksak.adapters.json_theme_reference_repository import (
    DEFAULT_CATALOG_PATH,
    JsonThemeReferenceRepository,
    load_catalog_from_dict,
)
from ssuksak.planning.domain.errors import FailureCategory, Outcome, PlanningError
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.rules import gates

CATALOG_ID = "ssuksak.yearly-theme-reference"
CATALOG_VERSION = "theme-reference-v0.1.2"


def _payload() -> dict:
    return json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))


# --------------------------- 실제 파일은 v0.1.2에서 사람 승인을 받았다


def test_repository_file_is_human_approved():
    """v0.1.2는 2026-09-11 사람 검토를 통과했다(OD-N10)."""
    review = _payload()["review"]
    assert review["domain_owner_approval"] == "HUMAN_APPROVED"
    assert review["approved_by"]
    assert review["approved_at"]


def test_approved_by_is_opaque_reviewer_identifier_not_login_user_id():
    """approved_by는 인증 user_id가 아니라 P0 opaque reviewer identifier다.

    OD-N10: 형식은 reviewer_<role>_<sequence>. Plan Confirm의 담임교사
    actor_id와 다른 개념이므로 섞지 않는다.
    """
    review = _payload()["review"]
    approved_by = review["approved_by"]

    assert approved_by.startswith("reviewer_"), approved_by
    assert len(approved_by.split("_")) >= 3, "reviewer_<role>_<sequence> 형식"
    # 테스트 fixture나 Plan actor 형식을 쓰지 않는다.
    assert not approved_by.startswith("user_")
    assert "fixture" not in approved_by
    assert review["approved_by_semantics"]


def test_approved_at_is_iso8601_with_offset():
    from datetime import datetime

    approved_at = _payload()["review"]["approved_at"]
    parsed = datetime.fromisoformat(approved_at)
    assert parsed.tzinfo is not None, "시간대 오프셋이 있어야 한다"


def test_runtime_repository_reads_real_approved_state_and_is_active():
    """운영 경로는 파일의 실제 승인 상태를 읽는다. override를 쓰지 않는다."""
    repo = JsonThemeReferenceRepository()
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)

    assert catalog is not None
    assert catalog.activation_status is ActivationStatus.HUMAN_APPROVED
    assert catalog.is_active is True


def test_approved_catalog_passes_the_gate():
    repo = JsonThemeReferenceRepository()
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)

    gates.require_human_approved_catalog(catalog)  # 예외 없음


def test_pending_catalog_is_still_blocked_by_gate():
    """실제 catalog가 승인되었어도 PENDING 거부 Contract는 계속 필요하다.

    다른 버전이나 미승인 카탈로그가 들어오면 여전히 차단되어야 한다.
    """
    repo = JsonThemeReferenceRepository(
        activation_override=ActivationStatus.PENDING_HUMAN_REVIEW
    )
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)

    with pytest.raises(PlanningError) as exc:
        gates.require_human_approved_catalog(catalog)

    assert exc.value.outcome is Outcome.BLOCKED
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert (
        exc.value.violated_rule
        == "only_human_approved_versioned_theme_reference_is_eligible"
    )


def test_activation_override_does_not_rewrite_the_file():
    """override는 메모리 상태만 바꾼다. 파일 승인 기록은 그대로다."""
    repo = JsonThemeReferenceRepository(
        activation_override=ActivationStatus.PENDING_HUMAN_REVIEW
    )
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)

    assert catalog.is_active is False
    # 파일은 여전히 승인 상태다.
    assert _payload()["review"]["domain_owner_approval"] == "HUMAN_APPROVED"


def test_approved_review_state_in_payload_activates_without_override():
    payload = _payload()
    payload["review"]["domain_owner_approval"] = "HUMAN_APPROVED"
    catalog = load_catalog_from_dict(payload)

    assert catalog.activation_status is ActivationStatus.HUMAN_APPROVED
    assert catalog.is_active is True


def test_unknown_review_value_is_treated_as_pending():
    """알 수 없는 승인 문자열을 활성으로 해석하지 않는다."""
    payload = _payload()
    payload["review"]["domain_owner_approval"] = "SOMETHING_ELSE"
    catalog = load_catalog_from_dict(payload)

    assert catalog.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert catalog.is_active is False


# ------------------------------------------------- version 정확 일치 검증


def test_repository_returns_none_for_unknown_version():
    repo = JsonThemeReferenceRepository(
        activation_override=ActivationStatus.HUMAN_APPROVED
    )
    assert repo.get_catalog(CATALOG_ID, "theme-reference-v9.9.9") is None


def test_repository_returns_none_for_unknown_catalog_id():
    repo = JsonThemeReferenceRepository(
        activation_override=ActivationStatus.HUMAN_APPROVED
    )
    assert repo.get_catalog("some.other.catalog", CATALOG_VERSION) is None


def test_unresolved_catalog_raises_reference_validation():
    with pytest.raises(PlanningError) as exc:
        gates.require_resolved_catalog(None, CATALOG_ID, "nope")

    assert exc.value.outcome is Outcome.VALIDATION_FAILED
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert exc.value.violated_rule == "catalog_id_and_version_must_resolve_exactly"


# ----------------------------------------------------- Reference 의미 규정


def test_catalog_normative_status_is_non_normative():
    """Theme은 국가가 정한 월별 주제가 아니다."""
    repo = JsonThemeReferenceRepository()
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)
    assert catalog.normative_status == "SAMPLE_DERIVED_NON_NORMATIVE"


def test_theme_source_version_matches_catalog_version():
    repo = JsonThemeReferenceRepository()
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)
    for theme in catalog.themes:
        assert theme.source_version == CATALOG_VERSION


def test_origin_id_is_lineage_not_evidence_source_id():
    """origin_id는 upstream lineage이며 Evidence의 canonical source_id가 아니다."""
    repo = JsonThemeReferenceRepository()
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)

    for theme in catalog.themes:
        assert theme.origin_id is not None
        # lineage 식별자는 theme_id와 다른 값이다.
        assert theme.origin_id != theme.theme_id


def test_curriculum_links_are_domain_level_alignment_only():
    repo = JsonThemeReferenceRepository()
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)

    nuri_domains = {
        "신체운동·건강",
        "의사소통",
        "사회관계",
        "예술경험",
        "자연탐구",
    }
    for theme in catalog.themes:
        for link in theme.curriculum_links:
            assert link.relation == "EDUCATIONAL_ALIGNMENT"
            assert link.domain in nuri_domains


def test_catalog_rejects_duplicate_theme_ids():
    payload = _payload()
    payload["themes"] = [payload["themes"][0], payload["themes"][0]]
    with pytest.raises(ValueError, match="중복된 theme_id"):
        load_catalog_from_dict(payload)


def test_every_academic_month_has_at_least_one_candidate_for_each_age():
    """Golden 성공 경로의 전제 확인."""
    repo = JsonThemeReferenceRepository(
        activation_override=ActivationStatus.HUMAN_APPROVED
    )
    catalog = repo.get_catalog(CATALOG_ID, CATALOG_VERSION)

    for ages in (frozenset({3}), frozenset({4}), frozenset({5}), frozenset({3, 4})):
        for month in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2):
            eligible = catalog.eligible_candidates(month, ages)
            assert eligible, f"ages={sorted(ages)} month={month} 후보 없음"
