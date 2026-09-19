from __future__ import annotations

import copy
import inspect
import json

import pytest

from ssuksak.adapters.json_theme_reference_repository import (
    DEFAULT_CATALOG_PATH,
    JsonThemeReferenceRepository,
)
from ssuksak.adapters.theme_reference_schema import (
    ThemeReferenceSchemaError,
    parse_theme_reference_payload,
)
from ssuksak.planning.application.ports import ThemeReferenceRepository
from ssuksak.planning.domain.theme_reference import ActivationStatus

CATALOG_ID = "ssuksak.yearly-theme-reference"
CATALOG_VERSION = "theme-reference-v0.1.2"


def _payload() -> dict:
    return json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))


def test_approved_repository_artifact_loads_through_the_port():
    repository = JsonThemeReferenceRepository()
    catalog = repository.get_catalog(CATALOG_ID, CATALOG_VERSION)

    assert isinstance(repository, ThemeReferenceRepository)
    assert catalog is not None
    assert catalog.activation_status is ActivationStatus.HUMAN_APPROVED
    assert catalog.is_active is True
    assert catalog.normative_status == "SAMPLE_DERIVED_NON_NORMATIVE"
    assert len(catalog.themes) == 12


def test_repository_requires_an_exact_id_and_version():
    repository = JsonThemeReferenceRepository()

    assert repository.get_catalog("other", CATALOG_VERSION) is None
    assert repository.get_catalog(CATALOG_ID, "latest") is None


def test_approval_state_cannot_be_overridden_by_repository_callers():
    assert "activation_override" not in inspect.signature(
        JsonThemeReferenceRepository
    ).parameters
    assert "activation_override" not in inspect.signature(
        parse_theme_reference_payload
    ).parameters


def test_unknown_review_value_is_never_treated_as_approved():
    payload = _payload()
    payload["review"]["domain_owner_approval"] = "APPROVED_MAYBE"

    catalog = parse_theme_reference_payload(payload)

    assert catalog.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert catalog.is_active is False


@pytest.mark.parametrize(
    "field",
    [
        "theme_id",
        "label",
        "applicable_months",
        "age_conditions",
        "curriculum_links",
        "origin_id",
        "source_version",
        "evidence",
    ],
)
def test_missing_required_theme_fields_fail_fast(field: str):
    payload = _payload()
    del payload["themes"][0][field]

    with pytest.raises(ThemeReferenceSchemaError, match=field):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("field", ["catalog_id", "catalog_version", "review", "themes"])
def test_missing_required_catalog_fields_fail_fast(field: str):
    payload = _payload()
    del payload[field]

    with pytest.raises(ThemeReferenceSchemaError, match=field):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("months", [[], [0], [13], [3, "4"], "3", 3])
def test_months_are_a_non_empty_strict_integer_array(months):
    payload = _payload()
    payload["themes"][0]["applicable_months"] = months

    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("bad", [True, "9", 0, 13])
def test_observed_month_is_a_strict_calendar_month(bad):
    payload = _payload()
    payload["themes"][0]["evidence"][0]["observed_month"] = bad

    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_missing_source_version_is_not_defaulted_from_catalog_version():
    payload = _payload()
    del payload["themes"][0]["source_version"]

    with pytest.raises(ThemeReferenceSchemaError, match="source_version"):
        parse_theme_reference_payload(payload)


def test_source_version_is_preserved_instead_of_rewritten():
    payload = _payload()
    payload["themes"][0]["source_version"] = "different-version"

    catalog = parse_theme_reference_payload(payload)

    assert catalog.themes[0].source_version == "different-version"
    assert catalog.catalog_version == CATALOG_VERSION


def test_duplicate_theme_ids_are_reported_as_schema_failure():
    payload = _payload()
    payload["themes"] = [
        payload["themes"][0],
        copy.deepcopy(payload["themes"][0]),
    ]

    with pytest.raises(ThemeReferenceSchemaError, match="duplicate theme_id"):
        parse_theme_reference_payload(payload)


@pytest.mark.parametrize("payload", [None, [], "not an object", 42])
def test_non_object_payload_is_rejected(payload):
    with pytest.raises(ThemeReferenceSchemaError):
        parse_theme_reference_payload(payload)


def test_domain_model_does_not_import_schema_or_json_modules():
    import ssuksak.planning.domain.theme_reference as domain_module

    source = inspect.getsource(domain_module)
    assert "pydantic" not in source.lower()
    assert "json" not in source.lower()
