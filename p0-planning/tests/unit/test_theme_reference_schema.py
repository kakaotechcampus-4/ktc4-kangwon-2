"""Theme Reference Loader fail-fast 테스트.

CLAUDE.md §7·§8: 필수 필드 누락을 기본값으로 조용히 보정하지 않는다.
특히 `themes[].source_version`이 없을 때 `catalog_version`을 자동 대입하지 않는다.

Input Schema(Pydantic)와 Domain Model은 분리되어 있다. 이 테스트는 외부 JSON
경계만 다룬다.
"""

from __future__ import annotations

import copy
import json

import pytest

from ssuksak.adapters.json_theme_reference_repository import DEFAULT_CATALOG_PATH
from ssuksak.adapters.theme_reference_schema import (
    ThemeReferenceSchemaError,
    parse_theme_reference_payload,
)
from ssuksak.planning.domain.theme_reference import ActivationStatus

REQUIRED_THEME_FIELDS = [
    "theme_id",
    "label",
    "applicable_months",
    "age_conditions",
    "curriculum_links",
    "origin_id",
    "source_version",
    "evidence",
]


def _payload() -> dict:
    return json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------ 정상 경로


def test_real_payload_parses_as_human_approved():
    catalog = parse_theme_reference_payload(_payload())

    assert catalog.catalog_version == "theme-reference-v0.1.2"
    assert catalog.activation_status is ActivationStatus.HUMAN_APPROVED
    assert len(catalog.themes) == 12


def test_pending_payload_still_parses_as_pending():
    """PENDING 해석 Contract는 실제 파일 승인과 무관하게 유지된다."""
    payload = _payload()
    payload["review"]["domain_owner_approval"] = "PENDING_HUMAN_REVIEW"
    catalog = parse_theme_reference_payload(payload)

    assert catalog.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert catalog.is_active is False


def test_domain_model_has_no_pydantic_dependency():
    """Domain Model은 외부 Schema를 알지 못한다."""
    import ssuksak.planning.domain.theme_reference as domain_module

    source = (
        __import__("pathlib").Path(domain_module.__file__).read_text(encoding="utf-8")
    )
    assert "pydantic" not in source.lower()


# ------------------------------------------- themes[] 필수 필드 fail-fast


@pytest.mark.parametrize("field", REQUIRED_THEME_FIELDS)
def test_missing_required_theme_field_fails_fast(field: str):
    payload = _payload()
    del payload["themes"][0][field]

    with pytest.raises(ThemeReferenceSchemaError) as exc:
        parse_theme_reference_payload(payload)
    assert field in str(exc.value)


def test_missing_source_version_is_not_defaulted_to_catalog_version():
    """가장 중요한 회귀: source_version을 catalog_version으로 자동 대입하지 않는다."""
    payload = _payload()
    del payload["themes"][0]["source_version"]

    with pytest.raises(ThemeReferenceSchemaError) as exc:
        parse_theme_reference_payload(payload)

    message = str(exc.value)
    assert "source_version" in message


def test_blank_source_version_is_rejected():
    payload = _payload()
    payload["themes"][0]["source_version"] = "   "
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_source_version_is_preserved_exactly_not_overwritten():
    """다른 값이 들어 있으면 그 값이 그대로 보존된다(조용한 보정 금지)."""
    payload = _payload()
    payload["themes"][0]["source_version"] = "theme-reference-v0.0.9"

    catalog = parse_theme_reference_payload(payload)
    target = catalog.get(payload["themes"][0]["theme_id"])

    assert target.source_version == "theme-reference-v0.0.9"
    assert catalog.catalog_version == "theme-reference-v0.1.2"


# --------------------------------------------------------- 타입 Validation


@pytest.mark.parametrize("bad", ["", "   "])
def test_blank_theme_id_and_label_are_rejected(bad: str):
    for field in ("theme_id", "label"):
        payload = _payload()
        payload["themes"][0][field] = bad
        with pytest.raises(ThemeReferenceSchemaError):
            parse_theme_reference_payload(payload)


@pytest.mark.parametrize("months", [[], [0], [13], [3, 99], "3", 3])
def test_invalid_applicable_months_are_rejected(months):
    payload = _payload()
    payload["themes"][0]["applicable_months"] = months
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_empty_supported_ages_is_rejected():
    payload = _payload()
    payload["themes"][0]["age_conditions"]["supported_ages"] = []
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("field", [
    "supported_ages",
    "allow_mixed_age",
    "mixed_age_requires_all_supported",
])
def test_missing_age_condition_field_is_rejected(field: str):
    payload = _payload()
    del payload["themes"][0]["age_conditions"][field]
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_age_conditions_must_be_an_object():
    payload = _payload()
    payload["themes"][0]["age_conditions"] = [3, 4, 5]
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("field", ["source_id", "domain", "source_page", "relation"])
def test_missing_curriculum_link_field_is_rejected(field: str):
    payload = _payload()
    del payload["themes"][0]["curriculum_links"][0][field]
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("field", [
    "origin_id",
    "page",
    "age_scope",
    "observed_month",
    "observed_label",
])
def test_missing_evidence_field_is_rejected(field: str):
    payload = _payload()
    del payload["themes"][0]["evidence"][0][field]
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_empty_evidence_list_is_rejected():
    """evidence가 없으면 선택 Rule의 강도가 조용히 0이 되므로 거부한다."""
    payload = _payload()
    payload["themes"][0]["evidence"] = []
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("month", [0, 13, -1, "9"])
def test_invalid_observed_month_is_rejected(month):
    payload = _payload()
    payload["themes"][0]["evidence"][0]["observed_month"] = month
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


# --------------------------------------------------- catalog 수준 Validation


@pytest.mark.parametrize("field", ["catalog_id", "catalog_version", "review", "themes"])
def test_missing_catalog_level_field_is_rejected(field: str):
    payload = _payload()
    del payload[field]
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_missing_review_approval_is_rejected():
    payload = _payload()
    del payload["review"]["domain_owner_approval"]
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_empty_themes_list_is_rejected():
    payload = _payload()
    payload["themes"] = []
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_duplicate_theme_ids_are_rejected():
    payload = _payload()
    payload["themes"] = [
        payload["themes"][0],
        copy.deepcopy(payload["themes"][0]),
    ]
    with pytest.raises(ThemeReferenceSchemaError, match="중복된 theme_id"):
        parse_theme_reference_payload(payload)


def test_non_object_payload_is_rejected():
    for bad in (None, [], "not json", 42):
        with pytest.raises(ThemeReferenceSchemaError):
            parse_theme_reference_payload(bad)


def test_unknown_approval_value_is_not_treated_as_active():
    payload = _payload()
    payload["review"]["domain_owner_approval"] = "APPROVED_MAYBE"
    catalog = parse_theme_reference_payload(payload)
    assert catalog.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert catalog.is_active is False


def test_activation_override_does_not_bypass_schema_validation():
    """override는 승인 상태만 바꾼다. Schema 위반은 그대로 실패한다."""
    payload = _payload()
    del payload["themes"][0]["source_version"]

    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(
            payload, activation_override=ActivationStatus.HUMAN_APPROVED
        )
