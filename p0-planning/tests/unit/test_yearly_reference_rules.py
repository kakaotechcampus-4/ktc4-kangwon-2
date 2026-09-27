from __future__ import annotations

import pytest

from ssuksak.planning.domain.errors import DomainError
from ssuksak.planning.domain.theme_reference import (
    ActivationStatus,
    ThemeCandidate,
    ThemeCatalog,
)
from ssuksak.planning.rules.errors import YearlyRuleError
from ssuksak.planning.rules.yearly_reference_rules import (
    AGE_RULE_ID,
    CATALOG_APPROVAL_RULE_ID,
    CATALOG_RESOLUTION_RULE_ID,
    require_human_approved_catalog,
    require_resolved_catalog,
    validate_age_set,
)


def _catalog(status: ActivationStatus) -> ThemeCatalog:
    return ThemeCatalog(
        catalog_id="catalog.test",
        catalog_version="v1",
        activation_status=status,
        themes=(
            ThemeCandidate(
                theme_id="theme",
                label="Theme",
                applicable_months=(3,),
                supported_ages=(3, 4, 5),
                allow_mixed_age=True,
                mixed_age_requires_all_supported=True,
                source_version="v1",
            ),
        ),
    )


@pytest.mark.parametrize("ages", [{3}, {4}, {5}, {3, 4}, {3, 4, 5}])
def test_supported_age_sets_are_normalized(ages):
    assert validate_age_set(ages) == frozenset(ages)


@pytest.mark.parametrize("ages", [set(), {2}, {6}, {3, True}, [3, 3], "3", None])
def test_invalid_age_sets_use_current_domain_error_contract(ages):
    with pytest.raises(DomainError) as exc:
        validate_age_set(ages)

    assert isinstance(exc.value, YearlyRuleError)
    assert exc.value.rule_id == AGE_RULE_ID


def test_exact_catalog_resolution_returns_the_same_catalog():
    catalog = _catalog(ActivationStatus.HUMAN_APPROVED)

    assert require_resolved_catalog(catalog, "catalog.test", "v1") is catalog


@pytest.mark.parametrize(
    ("catalog", "catalog_id", "version"),
    [
        (None, "catalog.test", "v1"),
        (_catalog(ActivationStatus.HUMAN_APPROVED), "other", "v1"),
        (_catalog(ActivationStatus.HUMAN_APPROVED), "catalog.test", "v2"),
    ],
)
def test_catalog_resolution_never_falls_back(catalog, catalog_id, version):
    with pytest.raises(YearlyRuleError) as exc:
        require_resolved_catalog(catalog, catalog_id, version)

    assert exc.value.rule_id == CATALOG_RESOLUTION_RULE_ID


def test_only_human_approved_catalog_passes_activation_gate():
    require_human_approved_catalog(_catalog(ActivationStatus.HUMAN_APPROVED))

    with pytest.raises(YearlyRuleError) as exc:
        require_human_approved_catalog(
            _catalog(ActivationStatus.PENDING_HUMAN_REVIEW)
        )
    assert exc.value.rule_id == CATALOG_APPROVAL_RULE_ID
