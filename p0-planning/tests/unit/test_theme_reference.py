from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.theme_reference import (
    ActivationStatus,
    ThemeCandidate,
    ThemeCatalog,
    ThemeEvidence,
)


def _candidate(
    theme_id: str = "theme-a",
    *,
    months: tuple[int, ...] = (9,),
    ages: tuple[int, ...] = (3, 4, 5),
    allow_mixed: bool = True,
    require_all_supported: bool = True,
    evidence_months: tuple[int, ...] = (9,),
) -> ThemeCandidate:
    return ThemeCandidate(
        theme_id=theme_id,
        label=theme_id,
        applicable_months=months,
        supported_ages=ages,
        allow_mixed_age=allow_mixed,
        mixed_age_requires_all_supported=require_all_supported,
        source_version="v-test",
        origin_id="sample.test",
        evidence=tuple(
            ThemeEvidence(
                origin_id="sample.test",
                page=1,
                age_scope=(3,),
                observed_month=month,
                observed_label=theme_id,
            )
            for month in evidence_months
        ),
    )


def _catalog(*themes: ThemeCandidate) -> ThemeCatalog:
    return ThemeCatalog(
        catalog_id="catalog.test",
        catalog_version="v-test",
        activation_status=ActivationStatus.HUMAN_APPROVED,
        themes=themes or (_candidate(),),
    )


def test_catalog_and_candidate_are_immutable():
    candidate = _candidate()
    catalog = _catalog(candidate)

    with pytest.raises(FrozenInstanceError):
        candidate.label = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        catalog.catalog_version = "changed"  # type: ignore[misc]


def test_catalog_lookup_and_activation_are_explicit():
    candidate = _candidate()
    catalog = _catalog(candidate)

    assert catalog.is_active is True
    assert catalog.get(candidate.theme_id) is candidate
    assert catalog.get("missing") is None


def test_month_and_age_filters_are_independent():
    only_three = _candidate("only-three", ages=(3,), months=(9,))
    mixed = _candidate("mixed", ages=(3, 4), months=(9,))
    october = _candidate("october", ages=(3, 4), months=(10,))
    catalog = _catalog(only_three, mixed, october)

    assert {item.theme_id for item in catalog.eligible_candidates(9, frozenset({3}))} == {
        "only-three",
        "mixed",
    }
    assert {
        item.theme_id
        for item in catalog.eligible_candidates(9, frozenset({3, 4}))
    } == {"mixed"}


def test_mixed_age_flag_must_allow_a_mixed_selection():
    candidate = _candidate(ages=(3, 4), allow_mixed=False)

    assert candidate.supports_age_set(frozenset({3}))
    assert not candidate.supports_age_set(frozenset({3, 4}))


def test_current_p0_policy_requires_all_mixed_ages_to_be_supported():
    candidate = _candidate(ages=(3, 4, 5))

    assert candidate.supports_age_set(frozenset({3}))
    assert candidate.supports_age_set(frozenset({3, 4}))
    assert candidate.supports_age_set(frozenset({3, 4, 5}))
    assert not candidate.supports_age_set(frozenset({2, 3}))
    assert not candidate.supports_age_set(frozenset())


def test_current_p0_policy_rejects_disabling_all_supported_requirement():
    with pytest.raises(
        InvalidDomainValueError,
        match="mixed_age_requires_all_supported must be true",
    ):
        _candidate(require_all_supported=False)


def test_evidence_strength_counts_only_the_requested_month():
    candidate = _candidate(evidence_months=(9, 9, 10))

    assert candidate.evidence_strength_for_month(9) == 2
    assert candidate.evidence_strength_for_month(10) == 1


def test_duplicate_theme_ids_are_a_domain_error():
    candidate = _candidate()

    with pytest.raises(InvalidDomainValueError, match="duplicate theme_id"):
        _catalog(candidate, candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        lambda: _candidate(theme_id=" "),
        lambda: _candidate(months=()),
        lambda: _candidate(months=(0,)),
        lambda: _candidate(months=(9, 9)),
        lambda: _candidate(ages=()),
        lambda: _candidate(ages=(3, 3)),
    ],
)
def test_candidate_rejects_invalid_domain_values(candidate):
    with pytest.raises(InvalidDomainValueError):
        candidate()
