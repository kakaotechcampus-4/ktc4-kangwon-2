"""Theme 선택 Rule 단위 테스트.

CLAUDE.md §20: Theme Candidate Filtering / Age Fit / 결정론적 Rule.
2026-09-10 승인된 선택 우선순위와 중복 정책을 검증한다.
"""

from __future__ import annotations

import pytest

from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.theme_reference import (
    ActivationStatus,
    ThemeCandidate,
    ThemeCatalog,
    ThemeEvidence,
)
from ssuksak.planning.rules.yearly_theme_selection import (
    REASON_AVOIDED_ADJACENT_REPEAT,
    REASON_EXCLUDED_CURRENT,
    REASON_KEPT_CURRENT_TO_AVOID_ADJACENT,
    REASON_ONLY_CANDIDATE,
    REASON_STRONGER_EVIDENCE,
    REASON_TIE_BREAK_THEME_ID,
    select_theme_for_period,
)

from tests.golden import harness as H

ALL_AGES = frozenset({3, 4, 5})


def _candidate(
    theme_id: str,
    *,
    months=(9,),
    ages=(3, 4, 5),
    evidence_months=(),
    allow_mixed=True,
) -> ThemeCandidate:
    return ThemeCandidate(
        theme_id=theme_id,
        label=theme_id,
        applicable_months=tuple(months),
        supported_ages=tuple(ages),
        allow_mixed_age=allow_mixed,
        mixed_age_requires_all_supported=True,
        source_version="v-test",
        evidence=tuple(
            ThemeEvidence(
                origin_id="o", page=1, age_scope=(3,), observed_month=m, observed_label=""
            )
            for m in evidence_months
        ),
    )


def _catalog(*candidates: ThemeCandidate) -> ThemeCatalog:
    return ThemeCatalog(
        catalog_id="test",
        catalog_version="v-test",
        activation_status=ActivationStatus.HUMAN_APPROVED,
        themes=tuple(candidates),
    )


# ------------------------------------------------------------- Filtering


def test_month_filter_excludes_non_applicable_candidates():
    cat = _catalog(
        _candidate("a", months=(9,)),
        _candidate("b", months=(10,)),
    )
    assert {c.theme_id for c in cat.eligible_candidates(9, ALL_AGES)} == {"a"}
    assert {c.theme_id for c in cat.eligible_candidates(10, ALL_AGES)} == {"b"}


def test_age_filter_requires_every_selected_age():
    """혼합연령 후보는 선택된 모든 연령을 지원해야 한다."""
    only_3 = _candidate("only3", ages=(3,))
    assert only_3.supports_age_set(frozenset({3}))
    assert not only_3.supports_age_set(frozenset({3, 4}))

    three_four = _candidate("t34", ages=(3, 4))
    assert three_four.supports_age_set(frozenset({3, 4}))
    assert not three_four.supports_age_set(frozenset({3, 4, 5}))


def test_mixed_age_requires_allow_mixed_flag():
    no_mixed = _candidate("nm", ages=(3, 4), allow_mixed=False)
    assert no_mixed.supports_age_set(frozenset({3}))
    assert not no_mixed.supports_age_set(frozenset({3, 4}))


def test_empty_age_set_is_never_eligible():
    assert not _candidate("x").supports_age_set(frozenset())


# --------------------------------------------------------- 후보 공백 처리


def test_no_eligible_candidate_raises_and_does_not_invent():
    cat = _catalog(_candidate("a", months=(9,)))
    with pytest.raises(PlanningError) as exc:
        select_theme_for_period(
            catalog=cat,
            period_key="2026-06",
            calendar_month=6,
            ages=ALL_AGES,
        )
    assert exc.value.failure_category is FailureCategory.REFERENCE_CANDIDATE_EMPTY
    assert exc.value.violated_rule == "rule_must_select_from_eligible_reference_candidates"


# ------------------------------------------------------------ 우선순위


def test_stronger_month_evidence_wins():
    cat = _catalog(
        _candidate("weak", months=(9,), evidence_months=(9,)),
        _candidate("strong", months=(9,), evidence_months=(9, 9, 9)),
    )
    sel = select_theme_for_period(
        catalog=cat, period_key="2026-09", calendar_month=9, ages=ALL_AGES
    )
    assert sel.candidate.theme_id == "strong"
    assert sel.trace.reason == REASON_STRONGER_EVIDENCE
    assert sel.trace.evidence_strength == 3


def test_evidence_strength_is_month_specific():
    """다른 월의 evidence는 현재 월 강도에 기여하지 않는다."""
    c = _candidate("x", months=(9, 10), evidence_months=(9, 9, 10))
    assert c.evidence_strength_for_month(9) == 2
    assert c.evidence_strength_for_month(10) == 1


def test_adjacent_repeat_is_avoided_when_alternative_exists():
    cat = _catalog(
        _candidate("prev", months=(9, 10), evidence_months=(9, 10, 10, 10)),
        _candidate("other", months=(9, 10), evidence_months=(10,)),
    )
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-10",
        calendar_month=10,
        ages=ALL_AGES,
        adjacent_theme_ids=frozenset({"prev"}),
    )
    # 'prev'가 10월 evidence 강도는 더 높지만 인접 반복 회피가 앞선다.
    assert sel.candidate.theme_id == "other"
    assert sel.trace.reason == REASON_AVOIDED_ADJACENT_REPEAT
    assert sel.trace.avoided_adjacent_repeat is True


def test_same_theme_allowed_when_no_alternative_exists():
    """대체 가능한 후보가 없으면 동일 Theme 사용을 허용한다(결정 3)."""
    cat = _catalog(_candidate("sole", months=(10,), evidence_months=(10,)))
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-10",
        calendar_month=10,
        ages=ALL_AGES,
        adjacent_theme_ids=frozenset({"sole"}),
    )
    assert sel.candidate.theme_id == "sole"
    assert sel.trace.reason == REASON_ONLY_CANDIDATE


def test_theme_id_stable_sort_is_last_resort_tie_break():
    """모든 조건이 동률일 때만 theme_id 사전순을 쓴다."""
    cat = _catalog(
        _candidate("zzz", months=(9,), evidence_months=(9,)),
        _candidate("aaa", months=(9,), evidence_months=(9,)),
    )
    sel = select_theme_for_period(
        catalog=cat, period_key="2026-09", calendar_month=9, ages=ALL_AGES
    )
    assert sel.candidate.theme_id == "aaa"
    assert sel.trace.reason == REASON_TIE_BREAK_THEME_ID


def test_selection_is_deterministic_across_repeated_calls():
    cat = _catalog(
        _candidate("b", months=(9,), evidence_months=(9,)),
        _candidate("a", months=(9,), evidence_months=(9,)),
    )
    picks = {
        select_theme_for_period(
            catalog=cat, period_key="2026-09", calendar_month=9, ages=ALL_AGES
        ).candidate.theme_id
        for _ in range(20)
    }
    assert picks == {"a"}


def test_selection_is_independent_of_catalog_ordering():
    a = _candidate("a", months=(9,), evidence_months=(9,))
    b = _candidate("b", months=(9,), evidence_months=(9,))
    first = select_theme_for_period(
        catalog=_catalog(a, b), period_key="2026-09", calendar_month=9, ages=ALL_AGES
    )
    second = select_theme_for_period(
        catalog=_catalog(b, a), period_key="2026-09", calendar_month=9, ages=ALL_AGES
    )
    assert first.candidate.theme_id == second.candidate.theme_id


# ----------------------------------------------------- Regenerate 후보 제외


def test_regenerate_prefers_candidate_other_than_current():
    cat = _catalog(
        _candidate("current", months=(10,), evidence_months=(10, 10, 10)),
        _candidate("alt", months=(10,), evidence_months=(10,)),
    )
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-10",
        calendar_month=10,
        ages=ALL_AGES,
        exclude_theme_id="current",
    )
    assert sel.candidate.theme_id == "alt"
    assert sel.trace.reason == REASON_EXCLUDED_CURRENT


def test_regenerate_keeps_current_when_no_other_candidate():
    """결정 4: 다른 후보가 없으면 기존 theme_id를 유지한다."""
    cat = _catalog(_candidate("only", months=(10,), evidence_months=(10,)))
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-10",
        calendar_month=10,
        ages=ALL_AGES,
        exclude_theme_id="only",
    )
    assert sel.candidate.theme_id == "only"
    assert sel.trace.reason == REASON_ONLY_CANDIDATE


def test_regenerate_keeps_current_theme_when_alternative_collides_with_adjacent():
    """다른 후보가 있어도 그것이 인접 월과 충돌하면 현재 Theme을 유지한다."""
    cat = _catalog(
        _candidate("a", months=(10,), evidence_months=(10, 10, 10)),
        _candidate("b", months=(10,), evidence_months=(10,)),
    )
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-10",
        calendar_month=10,
        ages=ALL_AGES,
        adjacent_theme_ids=frozenset({"a"}),
        exclude_theme_id="b",
    )
    # 'a'는 강도가 높지만 인접 충돌. 'b'는 현재 Theme이지만 인접 안전 → 'b' 유지.
    assert sel.candidate.theme_id == "b"
    assert sel.trace.reason == REASON_KEPT_CURRENT_TO_AVOID_ADJACENT


# -------------------------------------------- 실제 Catalog 기반 회귀 테스트


def test_real_catalog_september_and_october_resolve_by_evidence():
    """실제 Catalog에서 9·10월이 후보 2개를 공유하는 상황의 회귀 테스트.

    theme_id 사전순만으로 고르면 9월이 `autumn`이 되지만, evidence 강도가
    9월은 korea(5) vs autumn(1), 10월은 autumn(5) vs korea(1)이다.
    """
    catalog = H.build_catalog()

    sept = select_theme_for_period(
        catalog=catalog, period_key="2026-09", calendar_month=9, ages=frozenset({3})
    )
    assert sept.candidate.theme_id == "yr_theme_korea_and_world_cultures"
    assert sept.trace.evidence_strength == 5

    octo = select_theme_for_period(
        catalog=catalog,
        period_key="2026-10",
        calendar_month=10,
        ages=frozenset({3}),
        adjacent_theme_ids=frozenset({sept.candidate.theme_id}),
    )
    assert octo.candidate.theme_id == "yr_theme_autumn_and_nature"
    assert octo.trace.evidence_strength == 5

    # 두 후보 집합이 실제로 같다는 전제 확인
    assert set(sept.trace.eligible_theme_ids) == set(octo.trace.eligible_theme_ids)
    assert len(sept.trace.eligible_theme_ids) == 2


def test_real_catalog_has_no_adjacent_duplicate_for_every_age():
    """실제 Catalog로 12개월을 뽑을 때 인접 중복이 없어야 한다."""
    catalog = H.build_catalog()
    for ages in (frozenset({3}), frozenset({4}), frozenset({5}), frozenset({3, 4})):
        picked: list[str] = []
        previous = None
        for month in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2):
            sel = select_theme_for_period(
                catalog=catalog,
                period_key=f"2026-{month:02d}",
                calendar_month=month,
                ages=ages,
                adjacent_theme_ids=(
                    frozenset({previous}) if previous else frozenset()
                ),
            )
            picked.append(sel.candidate.theme_id)
            previous = sel.candidate.theme_id

        adjacent = [(a, b) for a, b in zip(picked, picked[1:]) if a == b]
        assert not adjacent, f"ages={sorted(ages)} 인접 중복: {adjacent}"


def test_real_catalog_selection_traces_record_rule_and_reason():
    """선택 이유와 적용 Rule이 추적 가능해야 한다(결정 2 마지막 문단)."""
    catalog = H.build_catalog()
    sel = select_theme_for_period(
        catalog=catalog, period_key="2026-09", calendar_month=9, ages=frozenset({3})
    )
    assert sel.trace.rule_id == "yearly.theme.sample_derived_candidate_selection"
    assert sel.trace.rule_version == "v2"
    assert sel.trace.reason
    assert sel.trace.eligible_theme_ids


# ============================================================================
# reason 분류 정확성 — adjacent ∩ eligible 기준
# ============================================================================


def test_adjacent_not_in_eligible_is_not_recorded_as_avoided():
    """인접 Theme이 해당 월 후보에 없으면 회피가 일어난 것이 아니다.

    회귀 대상: 이전에는 adjacent set이 비어 있지 않기만 하면
    AVOIDED_ADJACENT_REPEAT로 기록했다.
    """
    cat = _catalog(
        _candidate("strong", months=(9,), evidence_months=(9, 9, 9)),
        _candidate("weak", months=(9,), evidence_months=(9,)),
        # 8월 전용 후보. 9월 eligible 집합에 포함되지 않는다.
        _candidate("prev_month_only", months=(8,), evidence_months=(8,)),
    )
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-09",
        calendar_month=9,
        ages=ALL_AGES,
        adjacent_theme_ids=frozenset({"prev_month_only"}),
    )

    assert sel.candidate.theme_id == "strong"
    assert sel.trace.reason == REASON_STRONGER_EVIDENCE
    assert sel.trace.avoided_adjacent_repeat is False
    # 후보 집합에 인접 Theme이 없음을 확인
    assert "prev_month_only" not in sel.trace.eligible_theme_ids


def test_adjacent_in_eligible_and_avoided_is_recorded():
    """인접 Theme이 실제 후보이고 penalty로 회피되면 기록한다."""
    cat = _catalog(
        _candidate("prev", months=(9, 10), evidence_months=(10, 10, 10)),
        _candidate("other", months=(9, 10), evidence_months=(10,)),
    )
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-10",
        calendar_month=10,
        ages=ALL_AGES,
        adjacent_theme_ids=frozenset({"prev"}),
    )

    assert sel.candidate.theme_id == "other"
    assert sel.trace.reason == REASON_AVOIDED_ADJACENT_REPEAT
    assert sel.trace.avoided_adjacent_repeat is True
    assert "prev" in sel.trace.eligible_theme_ids


def test_unrelated_adjacent_does_not_mask_tie_break_reason():
    """후보 밖 인접 Theme이 tie-break 이유를 가리지 않는다."""
    cat = _catalog(
        _candidate("bbb", months=(9,), evidence_months=(9,)),
        _candidate("aaa", months=(9,), evidence_months=(9,)),
        _candidate("elsewhere", months=(3,), evidence_months=(3,)),
    )
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-09",
        calendar_month=9,
        ages=ALL_AGES,
        adjacent_theme_ids=frozenset({"elsewhere"}),
    )

    assert sel.candidate.theme_id == "aaa"
    assert sel.trace.reason == REASON_TIE_BREAK_THEME_ID
    assert sel.trace.avoided_adjacent_repeat is False


def test_excluded_theme_outside_eligible_is_not_recorded_as_excluded():
    """Regenerate 제외 대상이 후보 밖이면 EXCLUDED_CURRENT로 기록하지 않는다."""
    cat = _catalog(
        _candidate("strong", months=(9,), evidence_months=(9, 9)),
        _candidate("weak", months=(9,), evidence_months=(9,)),
        _candidate("gone", months=(4,), evidence_months=(4,)),
    )
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-09",
        calendar_month=9,
        ages=ALL_AGES,
        exclude_theme_id="gone",
    )

    assert sel.candidate.theme_id == "strong"
    assert sel.trace.reason == REASON_STRONGER_EVIDENCE


def test_requested_avoid_set_is_still_recorded_in_trace():
    """실효 판정과 별개로 '요청된' 회피 대상은 추적에 남는다."""
    cat = _catalog(_candidate("a", months=(9,), evidence_months=(9, 9)),
                   _candidate("b", months=(9,), evidence_months=(9,)))
    sel = select_theme_for_period(
        catalog=cat,
        period_key="2026-09",
        calendar_month=9,
        ages=ALL_AGES,
        adjacent_theme_ids=frozenset({"not_a_candidate"}),
    )
    assert "not_a_candidate" in sel.trace.excluded_theme_ids
    assert sel.trace.avoided_adjacent_repeat is False


def test_real_catalog_september_reason_is_evidence_strength_not_avoidance():
    """실제 Catalog 회귀: 9월의 8월 Theme(교통기관)은 9월 후보가 아니다."""
    catalog = H.build_catalog()

    aug = select_theme_for_period(
        catalog=catalog, period_key="2026-08", calendar_month=8, ages=frozenset({3})
    )
    sept = select_theme_for_period(
        catalog=catalog,
        period_key="2026-09",
        calendar_month=9,
        ages=frozenset({3}),
        adjacent_theme_ids=frozenset({aug.candidate.theme_id}),
    )

    assert aug.candidate.theme_id == "yr_theme_transportation"
    assert aug.candidate.theme_id not in sept.trace.eligible_theme_ids
    assert sept.candidate.theme_id == "yr_theme_korea_and_world_cultures"
    assert sept.trace.reason == REASON_STRONGER_EVIDENCE
    assert sept.trace.avoided_adjacent_repeat is False


def test_real_catalog_october_reason_stays_avoidance():
    """10월은 9월 Theme이 실제 후보이므로 회피 기록이 유지된다."""
    catalog = H.build_catalog()

    octo = select_theme_for_period(
        catalog=catalog,
        period_key="2026-10",
        calendar_month=10,
        ages=frozenset({3}),
        adjacent_theme_ids=frozenset({"yr_theme_korea_and_world_cultures"}),
    )

    assert "yr_theme_korea_and_world_cultures" in octo.trace.eligible_theme_ids
    assert octo.candidate.theme_id == "yr_theme_autumn_and_nature"
    assert octo.trace.reason == REASON_AVOIDED_ADJACENT_REPEAT
    assert octo.trace.avoided_adjacent_repeat is True


def test_real_catalog_full_year_selection_is_unchanged():
    """선택 결과 자체는 바뀌지 않는다. reason만 정확해진다."""
    catalog = H.build_catalog()
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

    previous = None
    for month, expected_id in expected:
        sel = select_theme_for_period(
            catalog=catalog,
            period_key=f"2026-{month:02d}",
            calendar_month=month,
            ages=frozenset({3}),
            adjacent_theme_ids=(
                frozenset({previous}) if previous else frozenset()
            ),
        )
        assert sel.candidate.theme_id == expected_id, f"{month}월"
        previous = sel.candidate.theme_id
