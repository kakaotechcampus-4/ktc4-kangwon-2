"""Display Quality Soft Penalty 검증 (Monthly Quality Patch 1).

핵심 안전장치: **`HUMAN_CONFIRMED`인 품질 문제만 Selection에 영향을 준다.**
자동 탐지 결과(`AUTO_CANDIDATE`), 미검토, 필드 부재(legacy v0.2.0)는 전부 중립이다.
"""

from __future__ import annotations

import pytest

from ssuksak.planning.domain.activity_reference import (
    ActivityCandidate,
    ActivityDisplayQuality,
    ActivityEvidence,
    ActivitySetting,
    ActivityThemeLink,
    DisplayQualityReviewStatus,
    THEME_RELATION_OBSERVED_TOGETHER,
)
from ssuksak.planning.rules.monthly_activity_selection import (
    REASON_AVOIDED_DISPLAY_QUALITY_ISSUE,
    RULE_ID,
    RULE_VERSION,
    select_activity_for_cell,
)

OUTDOOR = "outdoor_play"
VERSION = "test-quality-v1"


def candidate(
    activity_id: str,
    label: str,
    *,
    quality=None,
    status=None,
    evidence_count: int = 1,
    months: tuple[int, ...] = (9,),
    theme_ids: tuple[str, ...] = (),
) -> ActivityCandidate:
    return ActivityCandidate(
        activity_id=activity_id,
        label=label,
        supported_ages=(4,),
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=months,
        placement_slots=(OUTDOOR,),
        setting=ActivitySetting.OUTDOOR,
        source_version=VERSION,
        display_quality=quality,
        display_quality_review_status=status,
        theme_links=tuple(
            ActivityThemeLink(
                theme_id=t,
                relation=THEME_RELATION_OBSERVED_TOGETHER,
                theme_catalog_version="theme-reference-v0.1.2",
            )
            for t in theme_ids
        ),
        evidence=tuple(
            ActivityEvidence(
                origin_id=f"{activity_id}.origin.{n}",
                page=n + 1,
                age_scope=(4,),
                observed_month=months[0],
                observed_label=f"{months[0]}월 관찰",
                observed_section=OUTDOOR,
                observed_source_label="바깥놀이",
            )
            for n in range(evidence_count)
        ),
    )


def pick(*cands):
    return select_activity_for_cell(
        candidates=list(cands), target_month="2026-09", section_key=OUTDOOR
    )


# ============================================================ Rule 신원


def test_rule_version_was_bumped_for_the_new_axis():
    """Ranking tuple이 바뀌었으므로 version을 올렸다. rule_id는 유지한다."""
    assert RULE_ID == "monthly.activity.reference_candidate_selection"
    assert RULE_VERSION == "v2"


# ==================================================== HUMAN_CONFIRMED만 penalty


def test_human_confirmed_issue_is_penalized():
    """품질 문제가 확정된 후보는 evidence가 더 많아도 밀린다."""
    bad = candidate(
        "act_bad",
        "전통놀이",
        quality=ActivityDisplayQuality.TOO_GENERIC,
        status=DisplayQualityReviewStatus.HUMAN_CONFIRMED,
        evidence_count=11,
    )
    good = candidate("act_good", "강강술래", evidence_count=1)

    sel = pick(bad, good)

    assert sel.candidate.activity_id == "act_good"
    assert sel.trace.display_quality_penalty == 0
    assert sel.trace.reason == REASON_AVOIDED_DISPLAY_QUALITY_ISSUE


def test_good_standalone_receives_no_penalty():
    strong = candidate(
        "act_strong",
        "무궁화 꽃이 피었습니다",
        quality=ActivityDisplayQuality.GOOD_STANDALONE,
        status=DisplayQualityReviewStatus.HUMAN_CONFIRMED,
        evidence_count=5,
    )
    weak = candidate("act_weak", "사방치기", evidence_count=1)

    sel = pick(strong, weak)

    assert sel.candidate.activity_id == "act_strong"
    assert sel.trace.display_quality_penalty == 0


@pytest.mark.parametrize(
    "status",
    [
        DisplayQualityReviewStatus.AUTO_CANDIDATE,
        DisplayQualityReviewStatus.UNREVIEWED,
        None,
    ],
)
def test_unconfirmed_quality_flags_are_neutral(status):
    """자동 탐지기에 False Positive가 남아 있으므로 확정 전에는 중립이다."""
    flagged = candidate(
        "act_flagged",
        "사방치기",
        quality=ActivityDisplayQuality.CONTEXT_DEPENDENT,
        status=status,
        evidence_count=5,
    )
    plain = candidate("act_plain", "강강술래", evidence_count=1)

    sel = pick(flagged, plain)

    assert sel.candidate.activity_id == "act_flagged"  # evidence가 더 강하다
    assert sel.trace.display_quality_penalty == 0


def test_missing_metadata_is_neutral_legacy_v0_2_0():
    """v0.2.0처럼 필드가 아예 없는 Catalog에서 기존과 동일하게 동작한다."""
    a = candidate("act_a", "가을 나들이", evidence_count=3)
    b = candidate("act_b", "모래놀이", evidence_count=1)

    sel = pick(a, b)

    assert sel.candidate.activity_id == "act_a"
    assert sel.trace.display_quality_penalty == 0
    assert a.display_quality is None
    assert a.has_confirmed_display_issue is False


# ============================================================ Hard Filter 아님


def test_quality_issue_is_never_a_hard_exclusion():
    """모든 후보가 품질 문제여도 후보 집합은 줄지 않는다."""
    bad1 = candidate(
        "act_b1", "전통놀이",
        quality=ActivityDisplayQuality.TOO_GENERIC,
        status=DisplayQualityReviewStatus.HUMAN_CONFIRMED,
    )
    bad2 = candidate(
        "act_b2", "놀이", evidence_count=2,
        quality=ActivityDisplayQuality.SECTION_LABEL_LIKE,
        status=DisplayQualityReviewStatus.HUMAN_CONFIRMED,
    )

    sel = pick(bad1, bad2)

    assert sel.candidate is not None
    assert sel.trace.candidate_count == 2
    assert sel.trace.display_quality_penalty == 1  # 고른 것도 penalty를 받았다


def test_single_bad_candidate_is_still_selected():
    only = candidate(
        "act_only", "전통놀이",
        quality=ActivityDisplayQuality.TOO_GENERIC,
        status=DisplayQualityReviewStatus.HUMAN_CONFIRMED,
    )
    sel = pick(only)
    assert sel.candidate.activity_id == "act_only"


# ==================================================== 기존 축 의미 보존


def test_repeat_penalty_still_dominates_quality():
    """반복 회피가 품질보다 앞선다. 기존 축 순서를 바꾸지 않았다."""
    clean_but_used = candidate("act_used", "강강술래")
    dirty_but_new = candidate(
        "act_new", "전통놀이",
        quality=ActivityDisplayQuality.TOO_GENERIC,
        status=DisplayQualityReviewStatus.HUMAN_CONFIRMED,
    )
    sel = select_activity_for_cell(
        candidates=[clean_but_used, dirty_but_new],
        target_month="2026-09",
        section_key=OUTDOOR,
        used_activity_ids=frozenset({"act_used"}),
    )
    assert sel.candidate.activity_id == "act_new"


def test_theme_penalty_still_dominates_quality():
    """parent theme은 상위 Plan이 내려준 의미 제약이라 품질보다 앞선다."""
    theme_id = "yr_theme_korea_and_world_cultures"
    linked_but_generic = candidate(
        "act_linked", "전통놀이",
        theme_ids=(theme_id,),
        quality=ActivityDisplayQuality.TOO_GENERIC,
        status=DisplayQualityReviewStatus.HUMAN_CONFIRMED,
    )
    unlinked_but_clean = candidate("act_unlinked", "모래놀이", evidence_count=9)

    sel = select_activity_for_cell(
        candidates=[linked_but_generic, unlinked_but_clean],
        target_month="2026-09",
        section_key=OUTDOOR,
        parent_theme_id=theme_id,
    )
    assert sel.candidate.activity_id == "act_linked"
    assert sel.trace.display_quality_penalty == 1


def test_tie_break_is_still_stable_activity_id():
    a = candidate("act_bbb", "놀이 A")
    b = candidate("act_aaa", "놀이 B")
    assert pick(a, b).candidate.activity_id == "act_aaa"
    assert pick(b, a).candidate.activity_id == "act_aaa"


def test_evidence_strength_still_orders_within_same_quality():
    strong = candidate("act_s", "강강술래", evidence_count=7)
    weak = candidate("act_w", "가을 나들이", evidence_count=2)
    assert pick(weak, strong).candidate.activity_id == "act_s"
