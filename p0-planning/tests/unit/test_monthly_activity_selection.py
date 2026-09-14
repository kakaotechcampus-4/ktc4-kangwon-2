"""Monthly Activity Selection Rule 테스트 (M2-B).

검증 축:
- 후보 0 → 예외 없이 NO_ELIGIBLE_CANDIDATE
- 후보 1 → penalty가 있어도 항상 선택
- 5단계 ranking 우선순위가 정확히 그 순서로 지배
- 모든 축이 penalty이며 hard exclusion이 아님
- 결정론 (같은 입력 → 같은 결과)
- curriculum_links 빈 배열이 중립
- Regenerate용 current_activity_id 처리
- Rule이 Repository / JSON / MonthlyPlan / LLM에 접근하지 않음

synthetic fixture 중심이다. 실제 v0 catalog 결과를 정답으로 고정하지 않는다.
"""

from __future__ import annotations

import pytest

from ssuksak.planning.application.monthly_dto import ActivitySelectionTrace
from ssuksak.planning.domain.activity_reference import (
    ActivityCandidate,
    ActivityEvidence,
    ActivitySetting,
    ActivityThemeLink,
    CurriculumLink,
)
from ssuksak.planning.rules.monthly_activity_selection import (
    REASON_AVOIDED_CURRICULUM_REPEAT,
    REASON_AVOIDED_REPEAT_IN_MONTH,
    REASON_KEPT_PENALIZED_CANDIDATE,
    REASON_MATCHED_PARENT_THEME,
    REASON_NO_ELIGIBLE_CANDIDATE,
    REASON_ONLY_CANDIDATE,
    REASON_STRONGER_MONTH_EVIDENCE,
    REASON_TIE_BREAK_ACTIVITY_ID,
    RULE_ID,
    RULE_VERSION,
    ActivitySelection,
    select_activity_for_cell,
)

VERSION = "activity-reference-v0.1.0"
THEME_VERSION = "theme-reference-v0.1.2"
KOREA = "yr_theme_korea_and_world_cultures"
AUTUMN = "yr_theme_autumn_and_nature"
OUTDOOR = "outdoor_play"
MONTH = "2026-09"


def make(
    activity_id: str,
    *,
    themes: tuple[str, ...] = (),
    domains: tuple[str, ...] = (),
    evidence_count: int = 1,
    month: int = 9,
) -> ActivityCandidate:
    return ActivityCandidate(
        activity_id=activity_id,
        label=f"활동 {activity_id}",
        supported_ages=(3, 4, 5),
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=(month,),
        placement_slots=(OUTDOOR,),
        setting=ActivitySetting.OUTDOOR,
        source_version=VERSION,
        theme_links=tuple(
            ActivityThemeLink(t, "OBSERVED_TOGETHER", THEME_VERSION) for t in themes
        ),
        curriculum_links=tuple(
            CurriculumLink("curriculum.mohw.notice-2019-152", d, 10) for d in domains
        ),
        evidence=tuple(
            ActivityEvidence(
                origin_id=f"sample.monthly.test{i}",
                page=1,
                age_scope=(3, 4, 5),
                observed_month=month,
                observed_label=f"원문 {activity_id} {i}",
                observed_section=OUTDOOR,
                observed_source_label="바깥놀이",
            )
            for i in range(evidence_count)
        ),
    )


def pick(candidates, **kw) -> ActivitySelection:
    kw.setdefault("target_month", MONTH)
    kw.setdefault("section_key", OUTDOOR)
    return select_activity_for_cell(candidates=candidates, **kw)


def chosen_id(candidates, **kw) -> str | None:
    return pick(candidates, **kw).trace.selected_activity_id


# --------------------------------------------------------- Rule identity


def test_rule_identity_follows_existing_convention():
    """Rule Version은 Ranking tuple이 바뀔 때만 올린다.

    v1 → v2: Quality Patch 1에서 display quality 축이 추가되었다. yearly_theme_selection이
    쓰는 정수 증분(`v1` → `v2`) 관례를 따른다.
    """
    assert RULE_ID == "monthly.activity.reference_candidate_selection"
    assert RULE_VERSION == "v2"
    # 기존 dotted convention: <scope>.<subject>.<descriptor>
    assert len(RULE_ID.split(".")) == 3
    assert RULE_ID.startswith("monthly.")
    assert RULE_VERSION.startswith("v")


def test_trace_carries_rule_identity():
    t = pick([make("a")]).trace
    assert t.rule_id == RULE_ID
    assert t.rule_version == RULE_VERSION


# -------------------------------------------------------------- 후보 0


def test_no_candidates_returns_no_selection_without_raising():
    result = pick([])
    assert result.candidate is None
    assert not result.has_selection
    assert result.trace.reason == REASON_NO_ELIGIBLE_CANDIDATE
    assert result.trace.candidate_count == 0
    assert result.trace.selected_activity_id is None
    assert result.trace.selected_label is None
    assert not result.trace.has_selection


def test_no_candidates_still_records_cell_identity():
    t = pick([], week_id="2026-09-W3", parent_theme_id=KOREA).trace
    assert t.target_month == MONTH
    assert t.section_key == OUTDOOR
    assert t.week_id == "2026-09-W3"
    assert t.parent_theme_id == KOREA


def test_no_candidates_does_not_invent_an_activity():
    result = pick([])
    assert result.candidate is None
    assert result.trace.selected_label is None


# -------------------------------------------------------------- 후보 1


def test_single_candidate_is_always_selected():
    assert chosen_id([make("only")]) == "only"


@pytest.mark.parametrize(
    "kw",
    [
        {"used_activity_ids": frozenset({"only"})},
        {"current_activity_id": "only"},
        {"parent_theme_id": KOREA},
        {"used_curriculum_domains": {"자연탐구": 3}},
        {
            "used_activity_ids": frozenset({"only"}),
            "current_activity_id": "only",
            "parent_theme_id": KOREA,
            "used_curriculum_domains": {"자연탐구": 3},
        },
    ],
)
def test_single_candidate_survives_every_penalty(kw):
    """penalty 때문에 유일 후보가 제거되면 안 된다."""
    c = make("only", domains=("자연탐구",))
    assert chosen_id([c], **kw) == "only"


def test_single_candidate_reason_is_only_candidate():
    assert pick([make("only")]).trace.reason == REASON_ONLY_CANDIDATE


def test_single_penalized_candidate_records_penalty_in_trace():
    t = pick([make("only")], used_activity_ids=frozenset({"only"})).trace
    assert t.selected_activity_id == "only"
    assert t.repeat_penalty == 1
    assert t.reused_in_month is True
    assert t.all_candidates_penalized is True


# ------------------------------------------------------ 결정론 / tie-break


def test_stable_tie_break_by_activity_id():
    ids = ["act_z", "act_a", "act_m"]
    assert chosen_id([make(i) for i in ids]) == "act_a"


def test_tie_break_is_independent_of_input_order():
    ids = ["act_z", "act_a", "act_m"]
    for order in ([0, 1, 2], [2, 1, 0], [1, 2, 0]):
        assert chosen_id([make(ids[i]) for i in order]) == "act_a"


def test_same_input_gives_same_result_repeatedly():
    cands = [make("act_b", evidence_count=2), make("act_a", evidence_count=2)]
    results = {chosen_id(cands) for _ in range(20)}
    assert results == {"act_a"}


def test_tie_break_reason():
    assert pick([make("act_a"), make("act_b")]).trace.reason == (
        REASON_TIE_BREAK_ACTIVITY_ID
    )


def test_no_randomness_or_time_in_rule_source():
    import ast
    import pathlib

    src = pathlib.Path(
        "src/ssuksak/planning/rules/monthly_activity_selection.py"
    ).read_text(encoding="utf-8")
    mods = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mods.append(n.module or "")
    for banned in ("random", "time", "datetime", "uuid", "secrets"):
        assert not any(banned in m for m in mods), (banned, mods)


# --------------------------------------------- 1. duplicate penalty


def test_unused_activity_is_preferred():
    used = frozenset({"act_a"})
    assert chosen_id([make("act_a"), make("act_b")], used_activity_ids=used) == "act_b"


def test_duplicate_is_not_a_hard_exclusion():
    """모든 후보가 이미 사용됐어도 하나를 선택한다."""
    used = frozenset({"act_a", "act_b"})
    result = pick([make("act_a"), make("act_b")], used_activity_ids=used)
    assert result.has_selection
    assert result.trace.selected_activity_id == "act_a"
    assert result.trace.repeat_penalty == 1
    assert result.trace.all_candidates_penalized is True
    assert result.trace.reason == REASON_KEPT_PENALIZED_CANDIDATE


def test_avoided_repeat_reason_and_trace():
    t = pick(
        [make("act_a"), make("act_b")], used_activity_ids=frozenset({"act_a"})
    ).trace
    assert t.selected_activity_id == "act_b"
    assert t.reason == REASON_AVOIDED_REPEAT_IN_MONTH
    assert t.repeat_penalty == 0
    assert t.reused_in_month is False
    assert t.all_candidates_penalized is False


def test_used_ids_not_in_candidate_set_are_harmless():
    t = pick([make("act_a")], used_activity_ids=frozenset({"other"})).trace
    assert t.selected_activity_id == "act_a"
    assert t.repeat_penalty == 0


def test_empty_used_ids_is_neutral():
    assert chosen_id([make("act_a"), make("act_b")], used_activity_ids=frozenset()) == (
        "act_a"
    )


# ------------------------------------------------------ 2. theme match


def test_theme_matching_candidate_is_preferred():
    plain = make("act_a")
    matched = make("act_z", themes=(KOREA,))
    assert chosen_id([plain, matched], parent_theme_id=KOREA) == "act_z"


def test_selection_works_without_any_theme_match():
    result = pick([make("act_a"), make("act_b")], parent_theme_id=KOREA)
    assert result.has_selection
    assert result.trace.theme_matched is False


def test_theme_mismatch_is_not_a_hard_exclusion():
    only_mismatched = [make("act_a", themes=(AUTUMN,))]
    assert chosen_id(only_mismatched, parent_theme_id=KOREA) == "act_a"


def test_no_parent_theme_makes_the_axis_neutral():
    plain = make("act_a")
    matched = make("act_z", themes=(KOREA,))
    assert chosen_id([plain, matched], parent_theme_id=None) == "act_a"


def test_theme_match_uses_theme_id_only_not_labels():
    """label이 주제와 같아도 theme_id link가 없으면 매칭되지 않는다."""
    lookalike = ActivityCandidate(
        activity_id="act_a",
        label="우리나라와 세계 여러 나라",  # theme label과 동일한 문자열
        supported_ages=(3,),
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=(9,),
        placement_slots=(OUTDOOR,),
        setting=ActivitySetting.OUTDOOR,
        source_version=VERSION,
        theme_links=(),
        evidence=(),
    )
    linked = make("act_z", themes=(KOREA,))
    assert chosen_id([lookalike, linked], parent_theme_id=KOREA) == "act_z"


def test_theme_match_reason_and_trace():
    t = pick(
        [make("act_a"), make("act_z", themes=(KOREA,))], parent_theme_id=KOREA
    ).trace
    assert t.reason == REASON_MATCHED_PARENT_THEME
    assert t.theme_matched is True
    assert t.parent_theme_id == KOREA


def test_multiple_theme_links_match_any():
    c = make("act_a", themes=(KOREA, AUTUMN))
    assert chosen_id([c, make("act_b")], parent_theme_id=AUTUMN) == "act_a"


# --------------------------------------------- 3. curriculum diversity


def test_unused_domain_is_preferred():
    used_domain = make("act_a", domains=("자연탐구",))
    fresh = make("act_z", domains=("예술경험",))
    assert chosen_id([used_domain, fresh], used_curriculum_domains={"자연탐구": 2}) == (
        "act_z"
    )


def test_curriculum_repeat_is_not_a_hard_exclusion():
    only_repeated = [make("act_a", domains=("자연탐구",))]
    result = pick(only_repeated, used_curriculum_domains={"자연탐구": 5})
    assert result.trace.selected_activity_id == "act_a"
    assert result.trace.curriculum_repeat_penalty == 5


def test_empty_curriculum_links_are_neutral():
    """현재 v0 seed가 정확히 이 상태다. 차단도 오류도 없어야 한다."""
    cands = [make("act_a"), make("act_b")]
    result = pick(cands, used_curriculum_domains={"자연탐구": 9, "예술경험": 4})
    assert result.trace.selected_activity_id == "act_a"
    assert result.trace.curriculum_repeat_penalty == 0
    assert result.trace.selected_curriculum_domains == ()


def test_empty_curriculum_links_do_not_lose_to_populated_ones_without_repeats():
    empty = make("act_a")
    populated = make("act_b", domains=("예술경험",))
    assert chosen_id([empty, populated], used_curriculum_domains={"자연탐구": 3}) == (
        "act_a"
    )


def test_no_domain_is_invented_for_empty_links():
    t = pick([make("act_a")]).trace
    assert t.selected_curriculum_domains == ()
    assert t.curriculum_repeat_penalty == 0


def test_curriculum_penalty_sums_over_all_links():
    c = make("act_a", domains=("자연탐구", "예술경험"))
    t = pick([c], used_curriculum_domains={"자연탐구": 2, "예술경험": 3}).trace
    assert t.curriculum_repeat_penalty == 5


def test_no_primary_secondary_or_weight_assumption():
    """영역 순서를 바꿔도 결과가 같다. primary 개념이 없다."""
    a = make("act_a", domains=("자연탐구", "예술경험"))
    b = make("act_a", domains=("예술경험", "자연탐구"))
    used = {"자연탐구": 1, "예술경험": 1}
    assert (
        pick([a], used_curriculum_domains=used).trace.curriculum_repeat_penalty
        == pick([b], used_curriculum_domains=used).trace.curriculum_repeat_penalty
    )


def test_avoided_curriculum_repeat_reason():
    t = pick(
        [make("act_a", domains=("자연탐구",)), make("act_z", domains=("예술경험",))],
        used_curriculum_domains={"자연탐구": 2},
    ).trace
    assert t.selected_activity_id == "act_z"
    assert t.reason == REASON_AVOIDED_CURRICULUM_REPEAT


# -------------------------------------------------- 4. evidence strength


def test_stronger_month_evidence_is_preferred():
    weak = make("act_a", evidence_count=1)
    strong = make("act_z", evidence_count=3)
    assert chosen_id([weak, strong]) == "act_z"


def test_evidence_strength_reason_and_trace():
    t = pick([make("act_a", evidence_count=1), make("act_z", evidence_count=3)]).trace
    assert t.selected_activity_id == "act_z"
    assert t.evidence_strength == 3
    assert t.reason == REASON_STRONGER_MONTH_EVIDENCE


def test_other_month_evidence_does_not_boost():
    """3월 evidence가 9월 선택에 영향을 주지 않는다."""
    march_heavy = ActivityCandidate(
        activity_id="act_a",
        label="3월에 근거가 많은 활동",
        supported_ages=(3,),
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=(3, 9),
        placement_slots=(OUTDOOR,),
        setting=ActivitySetting.OUTDOOR,
        source_version=VERSION,
        evidence=tuple(
            ActivityEvidence(
                origin_id=f"sample.monthly.march{i}",
                page=1,
                age_scope=(3,),
                observed_month=3,
                observed_label=f"3월 원문 {i}",
                observed_section=OUTDOOR,
                observed_source_label="바깥놀이",
            )
            for i in range(5)
        )
        + (
            ActivityEvidence(
                origin_id="sample.monthly.sept",
                page=1,
                age_scope=(3,),
                observed_month=9,
                observed_label="9월 원문",
                observed_section=OUTDOOR,
                observed_source_label="바깥놀이",
            ),
        ),
    )
    sept_strong = make("act_z", evidence_count=3)
    result = pick([march_heavy, sept_strong], target_month="2026-09")
    assert result.trace.selected_activity_id == "act_z"
    assert result.trace.evidence_strength == 3


def test_evidence_strength_is_month_scoped_in_trace():
    c = make("act_a", evidence_count=4, month=9)
    assert pick([c], target_month="2026-09").trace.evidence_strength == 4


# ------------------------------------------- priority interaction 테스트


def test_duplicate_avoidance_outranks_theme_match():
    """반복 회피(1)가 theme 매칭(2)보다 우선한다."""
    used_but_matched = make("act_a", themes=(KOREA,))
    fresh_mismatched = make("act_z")
    got = chosen_id(
        [used_but_matched, fresh_mismatched],
        used_activity_ids=frozenset({"act_a"}),
        parent_theme_id=KOREA,
    )
    assert got == "act_z"


def test_theme_match_outranks_curriculum_diversity():
    """theme 매칭(2)이 curriculum 다양성(3)보다 우선한다."""
    matched_repeated_domain = make("act_a", themes=(KOREA,), domains=("자연탐구",))
    mismatched_fresh_domain = make("act_z", domains=("예술경험",))
    got = chosen_id(
        [matched_repeated_domain, mismatched_fresh_domain],
        parent_theme_id=KOREA,
        used_curriculum_domains={"자연탐구": 3},
    )
    assert got == "act_a"


def test_curriculum_diversity_outranks_evidence_strength():
    """curriculum 다양성(3)이 evidence 강도(4)보다 우선한다."""
    repeated_domain_strong = make("act_a", domains=("자연탐구",), evidence_count=9)
    fresh_domain_weak = make("act_z", domains=("예술경험",), evidence_count=1)
    got = chosen_id(
        [repeated_domain_strong, fresh_domain_weak],
        used_curriculum_domains={"자연탐구": 4},
    )
    assert got == "act_z"


def test_evidence_strength_outranks_activity_id_tie_break():
    """evidence 강도(4)가 activity_id tie-break(5)보다 우선한다."""
    early_id_weak = make("act_a", evidence_count=1)
    late_id_strong = make("act_z", evidence_count=5)
    assert chosen_id([early_id_weak, late_id_strong]) == "act_z"


def test_full_priority_chain_is_respected():
    """1 > 2 > 3 > 4 > 5를 한 번에 확인한다."""
    # act_a: 반복 penalty를 받지만 나머지 축 전부 최상
    worst_on_axis1 = make("act_a", themes=(KOREA,), domains=("예술경험",), evidence_count=9)
    # act_z: 반복 penalty 없음, 나머지 축 전부 최악
    best_on_axis1 = make("act_z", domains=("자연탐구",), evidence_count=1)
    got = chosen_id(
        [worst_on_axis1, best_on_axis1],
        used_activity_ids=frozenset({"act_a"}),
        parent_theme_id=KOREA,
        used_curriculum_domains={"자연탐구": 5},
    )
    assert got == "act_z"


# ------------------------------------------------- Regenerate 대비


def test_current_activity_is_penalized_not_excluded():
    result = pick([make("act_a")], current_activity_id="act_a")
    assert result.trace.selected_activity_id == "act_a"
    assert result.trace.is_current_activity is True
    assert result.trace.repeat_penalty == 1


def test_alternative_is_preferred_over_current_activity():
    got = chosen_id([make("act_a"), make("act_b")], current_activity_id="act_a")
    assert got == "act_b"


def test_sole_candidate_allows_same_value_regeneration():
    """대체 후보가 없으면 현재 Activity를 다시 선택할 수 있다."""
    result = pick([make("act_a")], current_activity_id="act_a")
    assert result.has_selection
    assert result.candidate.activity_id == "act_a"
    assert result.trace.reason == REASON_ONLY_CANDIDATE


def test_current_and_used_penalties_accumulate():
    t = pick(
        [make("act_a"), make("act_b")],
        used_activity_ids=frozenset({"act_a", "act_b"}),
        current_activity_id="act_a",
    ).trace
    # act_a는 used+current=2, act_b는 used=1 → act_b 선택
    assert t.selected_activity_id == "act_b"
    assert t.repeat_penalty == 1
    assert t.is_current_activity is False
    assert t.reused_in_month is True


def test_current_activity_id_none_is_neutral():
    assert chosen_id([make("act_a"), make("act_b")], current_activity_id=None) == "act_a"


def test_current_activity_not_in_candidates_is_harmless():
    t = pick([make("act_a")], current_activity_id="gone").trace
    assert t.selected_activity_id == "act_a"
    assert t.repeat_penalty == 0
    assert t.is_current_activity is False


# --------------------------------------------------------------- Trace


def test_trace_records_cell_identity():
    t = pick([make("act_a")], week_id="2026-09-W2").trace
    assert t.target_month == "2026-09"
    assert t.section_key == OUTDOOR
    assert t.week_id == "2026-09-W2"


def test_trace_week_id_is_none_for_merged_cells():
    assert pick([make("act_a")]).trace.week_id is None


def test_trace_records_candidate_count_and_label():
    t = pick([make("act_a"), make("act_b"), make("act_c")]).trace
    assert t.candidate_count == 3
    assert t.selected_label == "활동 act_a"


def test_trace_is_frozen_and_compact():
    t = pick([make("act_a")]).trace
    with pytest.raises(Exception):
        t.reason = "x"  # type: ignore[misc]
    # Domain truth를 복제하지 않는다.
    fields = set(ActivitySelectionTrace.__dataclass_fields__)
    for forbidden in ("candidates", "catalog", "activities", "evidence", "plan"):
        assert forbidden not in fields


def test_trace_field_count_stays_small():
    assert len(ActivitySelectionTrace.__dataclass_fields__) <= 19


# --------------------------------------------------- 순수 Rule 경계


def test_rule_does_not_import_repository_json_plan_or_llm():
    import ast
    import pathlib

    src = pathlib.Path(
        "src/ssuksak/planning/rules/monthly_activity_selection.py"
    ).read_text(encoding="utf-8")
    mods = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mods.append(n.module or "")
    banned = (
        "json",
        "pathlib",
        "repositor",
        "adapters",
        "llm",
        "openai",
        "monthly_plan",
        "ports",
        "requests",
        "httpx",
    )
    for b in banned:
        assert not any(b in m.lower() for m in mods), (b, mods)


def test_rule_signature_takes_no_catalog_or_selector():
    import inspect

    params = set(inspect.signature(select_activity_for_cell).parameters)
    for banned in ("catalog", "selector", "repository", "repo", "plan", "llm"):
        assert not any(banned in p for p in params), (banned, params)


def test_rule_does_not_mutate_candidates():
    cands = [make("act_b"), make("act_a")]
    before = [c.activity_id for c in cands]
    pick(cands)
    assert [c.activity_id for c in cands] == before


def test_rule_does_not_reapply_hard_filters():
    """승인·연령·월·slot·setting을 Rule이 다시 판정하지 않는다.

    hard filter를 통과했다고 전제하므로, month가 맞지 않는 후보를 넣어도 Rule은
    거부하지 않고 evidence 강도 0으로 ranking할 뿐이다.
    """
    march_only = make("act_a", month=3)
    result = pick([march_only], target_month="2026-09")
    assert result.has_selection
    assert result.trace.evidence_strength == 0


# ------------------------------------------------------- 입력 방어


@pytest.mark.parametrize("bad", ["2026", "2026-13", "2026-00", "202609", "9월", ""])
def test_invalid_target_month_is_rejected(bad):
    with pytest.raises(ValueError, match="target_month"):
        pick([make("act_a")], target_month=bad)


def test_invalid_target_month_is_rejected_even_with_no_candidates():
    with pytest.raises(ValueError, match="target_month"):
        pick([], target_month="2026-13")


def test_selection_result_exposes_has_selection():
    assert pick([make("act_a")]).has_selection
    assert not pick([]).has_selection


def test_selection_result_is_frozen():
    result = pick([make("act_a")])
    with pytest.raises(Exception):
        result.candidate = None  # type: ignore[misc]
