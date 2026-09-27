from dataclasses import replace

import pytest

from ssuksak.planning.domain.activity_reference import (
    ActivityCandidate,
    ActivityCatalog,
    ActivityDisplayQuality,
    ActivityEvidence,
    ActivitySetting,
    ActivityThemeLink,
    DisplayQualityReviewStatus,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.rules.monthly_activity_selection import (
    ActivitySelectionTrace,
    select_activity_for_cell,
)


def _candidate(activity_id: str, *, theme: str | None = None, months=(9,), issue=False):
    return ActivityCandidate(
        activity_id=activity_id,
        label=activity_id,
        supported_ages=(3, 4, 5),
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=months,
        placement_slots=("outdoor_play",),
        setting=ActivitySetting.OUTDOOR,
        source_version="v-test",
        theme_links=(() if theme is None else (ActivityThemeLink(theme, "OBSERVED_TOGETHER", "theme-v1"),)),
        evidence=(
            ActivityEvidence("sample", 1, (3, 4, 5), months[0], activity_id, "outdoor_play", "바깥놀이"),
        ),
        display_quality=(ActivityDisplayQuality.TOO_SHORT if issue else None),
        display_quality_review_status=(DisplayQualityReviewStatus.HUMAN_CONFIRMED if issue else None),
    )


def _catalog(*items):
    coverage = tuple(sorted({month for item in items for month in item.applicable_months}))
    return ActivityCatalog(
        "catalog",
        "v-test",
        ActivationStatus.HUMAN_APPROVED,
        tuple(items),
        month_coverage=coverage,
    )


def test_activity_mixed_age_policy_is_an_invariant():
    with pytest.raises(InvalidDomainValueError, match="must be true"):
        replace(_candidate("one"), mixed_age_requires_all_supported=False)


@pytest.mark.parametrize(
    ("ages", "expected"),
    [
        (frozenset(), False),
        (frozenset({3}), True),
        (frozenset({3, 4}), True),
        (frozenset({3, 4, 5}), True),
        (frozenset({2, 3}), False),
    ],
)
def test_activity_age_support(ages, expected):
    assert _candidate("one").supports_age_set(ages) is expected


def test_activity_catalog_hard_filters_month_age_slot_and_setting():
    catalog = _catalog(_candidate("september"), _candidate("october", months=(10,)))

    assert [item.activity_id for item in catalog.eligible_candidates(
        section_key="outdoor_play", calendar_month=9, ages=frozenset({3, 4})
    )] == ["september"]
    assert catalog.eligible_candidates(
        section_key="safety_education", calendar_month=9, ages=frozenset({3})
    ) == ()


def test_pending_activity_catalog_cannot_supply_runtime_candidates():
    catalog = replace(_catalog(_candidate("one")), activation_status=ActivationStatus.PENDING_HUMAN_REVIEW)

    assert catalog.eligible_candidates(
        section_key="outdoor_play", calendar_month=9, ages=frozenset({3})
    ) == ()


def test_activity_selection_trace_is_rule_local_and_deterministic():
    candidates = (_candidate("b"), _candidate("a", theme="theme-a"))
    first = select_activity_for_cell(candidates, calendar_month=9, parent_theme_id="theme-a")
    second = select_activity_for_cell(tuple(reversed(candidates)), calendar_month=9, parent_theme_id="theme-a")

    assert first.candidate.activity_id == second.candidate.activity_id == "a"
    assert isinstance(first.trace, ActivitySelectionTrace)
    assert first.trace.selected_activity_id == "a"


def test_activity_selection_avoids_repeat_before_theme_preference():
    repeated_match = _candidate("a", theme="theme-a")
    new_nonmatch = _candidate("b")

    result = select_activity_for_cell(
        (repeated_match, new_nonmatch),
        calendar_month=9,
        used_activity_ids=frozenset({"a"}),
        parent_theme_id="theme-a",
    )
    assert result.candidate.activity_id == "b"


def test_confirmed_display_issue_is_a_soft_penalty():
    result = select_activity_for_cell(
        (_candidate("a", issue=True), _candidate("b")), calendar_month=9
    )
    assert result.candidate.activity_id == "b"


def test_no_activity_candidate_is_an_explicit_non_exception_result():
    result = select_activity_for_cell((), calendar_month=9)

    assert not result.has_selection
    assert result.trace.reason_codes == ("NO_ELIGIBLE_CANDIDATE",)
