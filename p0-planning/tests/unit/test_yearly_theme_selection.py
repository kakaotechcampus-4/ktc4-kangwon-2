from __future__ import annotations

import pytest

from ssuksak.adapters.json_theme_reference_repository import (
    JsonThemeReferenceRepository,
)
from ssuksak.planning.domain.theme_reference import (
    ActivationStatus,
    ThemeCandidate,
    ThemeCatalog,
    ThemeEvidence,
)
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.errors import YearlyRuleError
from ssuksak.planning.rules.yearly_theme_selection import (
    REASON_AVOIDED_ADJACENT_REPEAT,
    REASON_EXCLUDED_CURRENT,
    REASON_KEPT_CURRENT_TO_AVOID_ADJACENT,
    REASON_ONLY_CANDIDATE,
    REASON_STRONGER_EVIDENCE,
    REASON_TIE_BREAK_THEME_ID,
    RULE_ID,
    RULE_VERSION,
    ThemeSelectionTrace,
    select_theme_for_period,
)

ALL_AGES = frozenset({3, 4, 5})


def _candidate(
    theme_id: str,
    *,
    months: tuple[int, ...] = (9,),
    ages: tuple[int, ...] = (3, 4, 5),
    evidence_months: tuple[int, ...] = (),
    allow_mixed: bool = True,
) -> ThemeCandidate:
    return ThemeCandidate(
        theme_id=theme_id,
        label=theme_id,
        applicable_months=months,
        supported_ages=ages,
        allow_mixed_age=allow_mixed,
        mixed_age_requires_all_supported=True,
        source_version="v-test",
        evidence=tuple(
            ThemeEvidence(
                origin_id="sample",
                page=1,
                age_scope=(3,),
                observed_month=month,
                observed_label=theme_id,
            )
            for month in evidence_months
        ),
    )


def _catalog(*candidates: ThemeCandidate) -> ThemeCatalog:
    return ThemeCatalog(
        catalog_id="catalog.test",
        catalog_version="v-test",
        activation_status=ActivationStatus.HUMAN_APPROVED,
        themes=candidates,
    )


def _select(
    catalog: ThemeCatalog,
    *,
    month: int = 9,
    adjacent: frozenset[str] = frozenset(),
    exclude: str | None = None,
):
    return select_theme_for_period(
        catalog=catalog,
        period=YearMonth(2026, month),
        ages=ALL_AGES,
        adjacent_theme_ids=adjacent,
        exclude_theme_id=exclude,
    )


def test_no_eligible_candidate_raises_a_domain_rule_error():
    catalog = _catalog(_candidate("nine", months=(9,)))

    with pytest.raises(YearlyRuleError) as exc:
        _select(catalog, month=6)

    assert exc.value.rule_id == RULE_ID
    assert exc.value.period == YearMonth(2026, 6)


def test_stronger_current_month_evidence_wins():
    selection = _select(
        _catalog(
            _candidate("weak", evidence_months=(9,)),
            _candidate("strong", evidence_months=(9, 9, 9)),
        )
    )

    assert selection.candidate.theme_id == "strong"
    assert selection.trace.reason == REASON_STRONGER_EVIDENCE
    assert selection.trace.evidence_strength == 3


def test_adjacent_repeat_is_a_higher_penalty_than_evidence_strength():
    selection = _select(
        _catalog(
            _candidate("previous", evidence_months=(9, 9, 9)),
            _candidate("other", evidence_months=(9,)),
        ),
        adjacent=frozenset({"previous"}),
    )

    assert selection.candidate.theme_id == "other"
    assert selection.trace.reason == REASON_AVOIDED_ADJACENT_REPEAT
    assert selection.trace.avoided_adjacent_repeat is True


def test_a_single_candidate_remains_selectable_despite_soft_penalties():
    selection = _select(
        _catalog(_candidate("sole", evidence_months=(9,))),
        adjacent=frozenset({"sole"}),
        exclude="sole",
    )

    assert selection.candidate.theme_id == "sole"
    assert selection.trace.reason == REASON_ONLY_CANDIDATE


def test_explicit_exclusion_prefers_an_alternative():
    selection = _select(
        _catalog(
            _candidate("current", evidence_months=(9, 9)),
            _candidate("alternative", evidence_months=(9,)),
        ),
        exclude="current",
    )

    assert selection.candidate.theme_id == "alternative"
    assert selection.trace.reason == REASON_EXCLUDED_CURRENT


def test_current_candidate_is_kept_when_the_alternative_repeats_adjacent():
    selection = _select(
        _catalog(
            _candidate("adjacent", evidence_months=(9, 9)),
            _candidate("current", evidence_months=(9,)),
        ),
        adjacent=frozenset({"adjacent"}),
        exclude="current",
    )

    assert selection.candidate.theme_id == "current"
    assert selection.trace.reason == REASON_KEPT_CURRENT_TO_AVOID_ADJACENT


def test_theme_id_is_the_stable_last_resort_tie_break():
    selection = _select(
        _catalog(
            _candidate("zzz", evidence_months=(9,)),
            _candidate("aaa", evidence_months=(9,)),
        )
    )

    assert selection.candidate.theme_id == "aaa"
    assert selection.trace.reason == REASON_TIE_BREAK_THEME_ID


def test_selection_is_independent_of_catalog_order():
    first = _candidate("first", evidence_months=(9,))
    second = _candidate("second", evidence_months=(9,))

    assert _select(_catalog(first, second)).candidate.theme_id == _select(
        _catalog(second, first)
    ).candidate.theme_id


def test_non_candidate_adjacent_id_does_not_create_a_false_avoidance_reason():
    selection = _select(
        _catalog(
            _candidate("strong", evidence_months=(9, 9)),
            _candidate("weak", evidence_months=(9,)),
        ),
        adjacent=frozenset({"not-eligible"}),
    )

    assert selection.trace.reason == REASON_STRONGER_EVIDENCE
    assert selection.trace.avoided_adjacent_repeat is False
    assert selection.trace.excluded_theme_ids == ("not-eligible",)


def test_trace_is_a_rule_result_and_records_rule_identity():
    selection = _select(_catalog(_candidate("only", evidence_months=(9,))))

    assert isinstance(selection.trace, ThemeSelectionTrace)
    assert ThemeSelectionTrace.__module__.endswith("rules.yearly_theme_selection")
    assert selection.trace.period == YearMonth(2026, 9)
    assert selection.trace.rule_id == RULE_ID
    assert selection.trace.rule_version == RULE_VERSION


def test_real_catalog_selects_evidence_backed_september_and_october_themes():
    repository = JsonThemeReferenceRepository()
    catalog = repository.get_catalog(
        "ssuksak.yearly-theme-reference", "theme-reference-v0.1.2"
    )
    assert catalog is not None

    september = select_theme_for_period(
        catalog=catalog,
        period=YearMonth(2026, 9),
        ages=frozenset({3}),
    )
    october = select_theme_for_period(
        catalog=catalog,
        period=YearMonth(2026, 10),
        ages=frozenset({3}),
        adjacent_theme_ids=frozenset({september.candidate.theme_id}),
    )

    assert september.candidate.theme_id == "yr_theme_korea_and_world_cultures"
    assert september.trace.evidence_strength == 5
    assert october.candidate.theme_id == "yr_theme_autumn_and_nature"
    assert october.trace.evidence_strength == 5


def test_real_catalog_produces_the_expected_full_academic_year():
    repository = JsonThemeReferenceRepository()
    catalog = repository.get_catalog(
        "ssuksak.yearly-theme-reference", "theme-reference-v0.1.2"
    )
    assert catalog is not None
    expected = [
        (3, "yr_theme_new_environment_friends"),
        (4, "yr_theme_spring"),
        (5, "yr_theme_self_and_family"),
        (6, "yr_theme_our_neighborhood"),
        (7, "yr_theme_summer"),
        (8, "yr_theme_transportation"),
        (9, "yr_theme_korea_and_world_cultures"),
        (10, "yr_theme_autumn_and_nature"),
        (11, "yr_theme_environment_and_life"),
        (12, "yr_theme_winter"),
        (1, "yr_theme_living_tools"),
        (2, "yr_theme_growth_and_transition"),
    ]

    previous: str | None = None
    actual: list[tuple[int, str]] = []
    for month, _ in expected:
        selection = select_theme_for_period(
            catalog=catalog,
            period=YearMonth(2026 if month >= 3 else 2027, month),
            ages=frozenset({3}),
            adjacent_theme_ids=frozenset({previous}) if previous else frozenset(),
        )
        actual.append((month, selection.candidate.theme_id))
        previous = selection.candidate.theme_id

    assert actual == expected
