"""Retriever — Eligibility · Age · Ranking · Diversity · Block · 결정론 (L2).

In-Memory Record로 규칙을 고정한다. 실제 Artifact에 의존하는 검증은
`test_retrieval_quality.py`에 따로 둔다.
"""

from __future__ import annotations

import pytest

from ssuksak.ingestion.models import (
    AgeEvidenceType,
    EvidenceRecord,
    EvidenceSourceType,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from ssuksak.planning.retrieval import (
    AgeMatchKind,
    BlockName,
    InMemoryInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
    RetrievalRequest,
    age_match_kind,
    apply_source_diversity,
    diversity_group,
    ngrams,
    rank_records,
)

SUMMER = "여름"


def rec(
    rid: str,
    *,
    month: int = 7,
    ages: tuple[int, ...] = (4,),
    age_kind: AgeEvidenceType = AgeEvidenceType.SINGLE_AGE_PAGE,
    section: SourceSection = SourceSection.OUTDOOR_PLAY,
    setting: Setting = Setting.OUTDOOR,
    quality: ExtractionQuality = ExtractionQuality.VALID,
    readability: MachineReadability = MachineReadability.TEXT_LAYER,
    institution: str | None = "가어린이집",
    text: str = "모래놀이",
    theme: str | None = None,
    sha: str | None = None,
) -> EvidenceRecord:
    is_exp = section is SourceSection.WEEK_EXPERIENCE
    return EvidenceRecord(
        record_id=rid,
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path=f"references/samples/monthly/{institution or 'unknown'}.pdf",
        source_sha256=(sha or (institution or "?").encode().hex().ljust(64, "0"))[:64],
        page=1,
        institution_id=institution,
        month=month,
        age_scope=ages,
        age_evidence_type=age_kind,
        monthly_theme=theme,
        source_section=section,
        source_label="바깥놀이",
        experience_text=text if is_exp else None,
        activity_text=None if is_exp else text,
        setting=setting,
        machine_readability=readability,
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        extraction_quality=quality,
        extraction_method="table_line_geometry_v1",
    )


def request(ages: tuple[int, ...] = (4,), *, month: int = 7, theme: str = SUMMER):
    return RetrievalRequest(
        target_month=f"2026-{month:02d}", calendar_month=month, ages=ages,
        age_mode="SINGLE" if len(ages) == 1 else "MIXED",
        confirmed_theme_id="yr_theme_summer", confirmed_theme_value=theme,
        week_count=5,
    )


def retriever(records, **kw) -> MonthlyEvidenceRetriever:
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    return MonthlyEvidenceRetriever(store, **kw)


def inst_ids(result) -> list[str]:
    return [i.record_id
            for i in result.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items]


# ============================================== Request 검증


def test_request_rejects_out_of_target_age():
    with pytest.raises(ValueError, match="만3~5세"):
        RetrievalRequest(target_month="2026-07", calendar_month=7, ages=(2,),
                         age_mode="SINGLE", confirmed_theme_id="t",
                         confirmed_theme_value="여름", week_count=5)


def test_request_rejects_empty_ages_and_bad_month():
    with pytest.raises(ValueError, match="ages"):
        RetrievalRequest(target_month="2026-07", calendar_month=7, ages=(),
                         age_mode="SINGLE", confirmed_theme_id="t",
                         confirmed_theme_value="여름", week_count=5)
    with pytest.raises(ValueError, match="calendar_month"):
        RetrievalRequest(target_month="2026-13", calendar_month=13, ages=(4,),
                         age_mode="SINGLE", confirmed_theme_id="t",
                         confirmed_theme_value="여름", week_count=5)


# ============================================== Eligibility


def test_needs_review_is_excluded():
    r = retriever([rec("ev_ok"), rec("ev_nr", quality=ExtractionQuality.NEEDS_REVIEW)])
    assert inst_ids(r.retrieve(request())) == ["ev_ok"]


def test_invalid_is_excluded():
    r = retriever([rec("ev_ok"), rec("ev_bad", quality=ExtractionQuality.INVALID)])
    assert inst_ids(r.retrieve(request())) == ["ev_ok"]


def test_image_only_is_excluded():
    r = retriever([rec("ev_ok"),
                   rec("ev_img", readability=MachineReadability.IMAGE_ONLY)])
    assert inst_ids(r.retrieve(request())) == ["ev_ok"]


def test_indoor_alternative_is_excluded_from_outdoor_blocks():
    r = retriever([
        rec("ev_ok"),
        rec("ev_alt", setting=Setting.INDOOR_ALTERNATIVE,
            section=SourceSection.INDOOR_ALTERNATIVE),
    ])
    res = r.retrieve(request())
    assert inst_ids(res) == ["ev_ok"]
    assert not res.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE].items


def test_indoor_play_is_excluded_from_outdoor_blocks():
    r = retriever([rec("ev_in", section=SourceSection.INDOOR_PLAY,
                       setting=Setting.INDOOR)])
    assert inst_ids(r.retrieve(request())) == []


def test_other_month_is_excluded():
    r = retriever([rec("ev_ok"), rec("ev_other", month=8)])
    assert inst_ids(r.retrieve(request())) == ["ev_ok"]


# ============================================== Age


@pytest.mark.parametrize("age", [3, 4, 5])
def test_single_age_request_prefers_exact_evidence(age):
    others = [a for a in (3, 4, 5) if a != age]
    records = [rec(f"ev_{a}", ages=(a,), institution=f"기관{a}") for a in (3, 4, 5)]
    res = retriever(records).retrieve(request(ages=(age,)))
    got = res.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items
    assert [i.record_id for i in got] == [f"ev_{age}"]
    assert got[0].trace.retrieval_tier is AgeMatchKind.SINGLE_AGE_EXACT
    assert all(f"ev_{o}" not in inst_ids(res) for o in others)


def test_mixed_age_record_covers_a_single_age_request():
    res = retriever([rec("ev_mix", ages=(3, 4, 5),
                         age_kind=AgeEvidenceType.MIXED_AGE_PAGE)]
                    ).retrieve(request(ages=(4,)))
    got = res.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items
    assert got[0].trace.retrieval_tier is AgeMatchKind.MIXED_AGE_COVERING


def test_mixed_request_uses_in_request_tier_and_keeps_both_ages():
    records = [
        rec("ev_a4", ages=(4,), institution="가어린이집"),
        rec("ev_b5", ages=(5,), institution="나어린이집"),
        rec("ev_c45", ages=(4, 5), age_kind=AgeEvidenceType.MIXED_AGE_PAGE,
            institution="다어린이집"),
    ]
    res = retriever(records).retrieve(request(ages=(4, 5)))
    items = res.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items
    assert {i.record_id for i in items} == {"ev_a4", "ev_b5", "ev_c45"}
    tiers = {i.record_id: i.trace.retrieval_tier for i in items}
    assert tiers["ev_a4"] is AgeMatchKind.SINGLE_AGE_IN_REQUEST
    assert tiers["ev_b5"] is AgeMatchKind.SINGLE_AGE_IN_REQUEST
    assert tiers["ev_c45"] is AgeMatchKind.MIXED_AGE_COVERING


def test_one_age_does_not_monopolise_a_mixed_request():
    """혼합 요청에서 한 연령이 Block을 독점하지 않는다."""
    records = [rec(f"ev_4_{i}", ages=(4,), institution=f"기관4{i}") for i in range(6)]
    records += [rec(f"ev_5_{i}", ages=(5,), institution=f"기관5{i}") for i in range(6)]
    res = retriever(records, top_k={BlockName.INSTITUTION_MONTHLY_EVIDENCE: 6}
                    ).retrieve(request(ages=(4, 5)))
    ages = [i.record.age_scope[0]
            for i in res.blocks[BlockName.INSTITUTION_MONTHLY_EVIDENCE].items]
    assert 4 in ages and 5 in ages


def test_age_unknown_is_not_used_for_institution_block():
    r = retriever([rec("ev_unknown", ages=(),
                       age_kind=AgeEvidenceType.AGE_UNKNOWN)])
    assert inst_ids(r.retrieve(request())) == []


def test_age_unknown_is_allowed_for_other_outdoor_evidence():
    """그 Block의 목적은 연령 구분이 아니라 그 달의 활동 범위다."""
    r = retriever([rec("ev_unknown", ages=(),
                       age_kind=AgeEvidenceType.AGE_UNKNOWN)])
    res = r.retrieve(request())
    assert [i.record_id
            for i in res.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE].items] == [
        "ev_unknown"
    ]


def test_age_match_kind_returns_none_for_unrelated_age():
    assert age_match_kind(rec("x", ages=(3,)), [5]) is None


# ============================================== Ranking


def test_ngrams_absorb_spacing_variants():
    assert ngrams("우리 동네") == ngrams("우리동네")


def test_theme_relevance_orders_results():
    records = [
        rec("ev_far", text="줄넘기", institution="가어린이집"),
        rec("ev_near", text="여름 곤충 찾기", institution="나어린이집"),
    ]
    assert inst_ids(retriever(records).retrieve(request())) == ["ev_near", "ev_far"]


def test_page_theme_match_outranks_text_overlap_only():
    records = [
        rec("ev_page", text="줄넘기", theme="여름", institution="가어린이집"),
        rec("ev_text", text="여름 곤충 찾기", theme="가을", institution="나어린이집"),
    ]
    assert inst_ids(retriever(records).retrieve(request()))[0] == "ev_page"


def test_single_age_tier_beats_theme_relevance():
    """연령 tier가 theme 신호보다 앞선다."""
    records = [
        rec("ev_mixed_relevant", ages=(3, 4, 5),
            age_kind=AgeEvidenceType.MIXED_AGE_PAGE,
            text="여름 곤충 찾기", institution="가어린이집"),
        rec("ev_single_plain", ages=(4,), text="줄넘기", institution="나어린이집"),
    ]
    assert inst_ids(retriever(records).retrieve(request()))[0] == "ev_single_plain"


def test_tie_break_is_stable_record_id():
    records = [rec("ev_b", institution="가어린이집"),
               rec("ev_a", institution="나어린이집")]
    assert inst_ids(retriever(records).retrieve(request())) == ["ev_a", "ev_b"]


def test_rank_records_is_pure_and_repeatable():
    records = [rec("ev_a"), rec("ev_b", institution="나어린이집")]
    grams = ngrams(SUMMER)
    first = rank_records(records, requested_ages=[4], theme_grams=grams)
    second = rank_records(records, requested_ages=[4], theme_grams=grams)
    assert [i.record_id for i in first] == [i.record_id for i in second]


# ============================================== Diversity


def test_institution_cap_limits_one_source():
    records = [rec(f"ev_{i}", institution="같은어린이집") for i in range(5)]
    res = retriever(records).retrieve(request())
    assert len(inst_ids(res)) == 2


def test_cap_off_lets_one_source_dominate():
    records = [rec(f"ev_{i}", institution="같은어린이집") for i in range(5)]
    res = retriever(records, institution_cap=99).retrieve(request())
    assert len(inst_ids(res)) == 5


def test_template_family_counts_as_one_source():
    """마성·우리·키즈로스쿨·혜솔은 본문이 겹치므로 한 Source로 센다."""
    records = [
        rec("ev_a", institution="우리어린이집"),
        rec("ev_b", institution="혜솔어린이집"),
        rec("ev_c", institution="키즈로스쿨어린이집"),
        rec("ev_d", institution="마성어린이집"),
    ]
    assert len(inst_ids(retriever(records).retrieve(request()))) == 2


def test_diversity_group_key():
    assert diversity_group(rec("x", institution="우리어린이집")) == "TEMPLATE_FAMILY"
    assert diversity_group(rec("x", institution="가어린이집")) == "가어린이집"
    assert diversity_group(rec("x", institution=None)) == "(기관 미상)"


def test_diversity_runs_after_ranking_not_before():
    """관련도 순서를 유지한 채 상한을 적용한다."""
    records = [
        rec("ev_hi1", text="여름 곤충", institution="가어린이집"),
        rec("ev_hi2", text="여름 하늘", institution="가어린이집"),
        rec("ev_hi3", text="여름 물놀이", institution="가어린이집"),
        rec("ev_lo", text="줄넘기", institution="나어린이집"),
    ]
    got = inst_ids(retriever(records).retrieve(request()))
    assert got[:2] == ["ev_hi1", "ev_hi2"]
    assert "ev_hi3" not in got
    assert "ev_lo" in got


def test_apply_source_diversity_returns_fewer_than_top_k_when_capped():
    """상한 때문에 못 채우면 억지로 채우지 않는다."""
    records = [rec(f"ev_{i}", institution="같은어린이집") for i in range(5)]
    ranked = rank_records(records, requested_ages=[4], theme_grams=ngrams(SUMMER))
    assert len(apply_source_diversity(ranked, top_k=5, institution_cap=2)) == 2


# ============================================== Block


def test_week_experience_is_a_separate_block_and_has_no_week_index():
    records = [
        rec("ev_act", text="모래놀이"),
        rec("ev_exp", section=SourceSection.WEEK_EXPERIENCE,
            setting=Setting.UNKNOWN, text="여름 날씨에 관심 갖기"),
    ]
    res = retriever(records).retrieve(request())
    assert inst_ids(res) == ["ev_act"]
    week = res.blocks[BlockName.WEEK_EXPERIENCE_CANDIDATES]
    assert [i.record_id for i in week.items] == ["ev_exp"]
    assert all(i.record.week_position is None for i in week.items)


def test_other_outdoor_excludes_records_already_in_institution_block():
    records = [rec(f"ev_{i}", institution=f"기관{i}") for i in range(4)]
    res = retriever(records, top_k={BlockName.INSTITUTION_MONTHLY_EVIDENCE: 2}
                    ).retrieve(request())
    used = set(inst_ids(res))
    other = {i.record_id for i in res.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE].items}
    assert used and other and not (used & other)


def test_other_outdoor_keeps_reuse_policy_metadata():
    res = retriever([rec("ev_a"), rec("ev_b", institution="나어린이집")],
                    top_k={BlockName.INSTITUTION_MONTHLY_EVIDENCE: 1}
                    ).retrieve(request())
    items = res.blocks[BlockName.OTHER_OUTDOOR_EVIDENCE].items
    assert items
    assert all(i.record.reuse_policy is ReusePolicy.CONTEXT_ONLY for i in items)


def test_age_contrast_requires_two_single_ages_in_one_document():
    same = "ab" * 32
    records = [
        rec("ev_3", ages=(3,), sha=same, institution="가어린이집", text="대청소"),
        rec("ev_4", ages=(4,), sha=same, institution="가어린이집", text="과일 놀이"),
    ]
    res = retriever(records).retrieve(request(ages=(4,)))
    got = res.blocks[BlockName.AGE_CONTRAST_EVIDENCE].items
    assert {i.record_id for i in got} == {"ev_3", "ev_4"}


def test_age_contrast_is_empty_when_no_contrast_exists():
    """없는 대조쌍을 추론해서 만들지 않는다."""
    res = retriever([rec("ev_4", ages=(4,))]).retrieve(request(ages=(4,)))
    block = res.blocks[BlockName.AGE_CONTRAST_EVIDENCE]
    assert block.items == ()
    assert block.is_empty


def test_age_contrast_skips_documents_that_do_not_include_requested_age():
    same = "cd" * 32
    records = [
        rec("ev_3", ages=(3,), sha=same, institution="가어린이집"),
        rec("ev_5", ages=(5,), sha=same, institution="가어린이집"),
    ]
    res = retriever(records).retrieve(request(ages=(4,)))
    assert res.blocks[BlockName.AGE_CONTRAST_EVIDENCE].is_empty


def test_reference_block_is_empty_without_a_catalog():
    res = retriever([rec("ev_a")]).retrieve(request())
    block = res.blocks[BlockName.REFERENCE_ACTIVITIES]
    assert block.reference_items == ()
    assert "주입되지 않" in block.retrieval_reason


def test_all_blocks_exist_even_when_store_is_empty():
    res = retriever([]).retrieve(request())
    assert set(res.blocks) == set(BlockName)
    assert all(res.blocks[n].is_empty for n in BlockName)
    assert res.total_evidence_records == 0


def test_result_carries_store_and_catalog_identity():
    res = retriever([rec("ev_a")]).retrieve(request())
    assert res.evidence_store_version
    assert len(res.evidence_store_sha256) == 64


# ============================================== 결정론


def test_same_input_returns_identical_result():
    records = [rec(f"ev_{i}", institution=f"기관{i % 3}") for i in range(9)]
    a = retriever(records).retrieve(request())
    b = retriever(records).retrieve(request())
    for name in BlockName:
        assert [i.record_id for i in a.blocks[name].items] == [
            i.record_id for i in b.blocks[name].items
        ]


def test_record_input_order_does_not_change_output():
    records = [rec(f"ev_{i}", institution=f"기관{i % 3}") for i in range(9)]
    a = retriever(records).retrieve(request())
    b = retriever(list(reversed(records))).retrieve(request())
    assert inst_ids(a) == inst_ids(b)


# ============================================== Rule v2 의미 불변


def test_context_ranking_reuses_rule_v2_axes_without_changing_them():
    """L2가 추가한 `context_ranking_sort_key`는 Rule v2의 축을 그대로 쓴다.

    Cell 단위 상태(같은 달 사용분·현재 activity·누리과정 사용량)를 중립으로 둔
    `_sort_key`와 **완전히 같은 값**이어야 한다. Rule의 의미를 바꾸지 않았다는 뜻이다.
    """
    from ssuksak.adapters.json_activity_reference_repository import (
        production_activity_reference_repository,
    )
    from ssuksak.planning.rules import monthly_activity_selection as rule_v2

    catalog = production_activity_reference_repository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
    )
    candidates = catalog.eligible_candidates(
        section_key="outdoor_play", calendar_month=7, ages=frozenset({4})
    )
    assert candidates
    for c in candidates:
        assert rule_v2.context_ranking_sort_key(
            c, calendar_month=7, parent_theme_id="yr_theme_summer"
        ) == rule_v2._sort_key(
            c,
            calendar_month=7,
            used_activity_ids=frozenset(),
            current_activity_id=None,
            parent_theme_id="yr_theme_summer",
            used_curriculum_domains={},
        )


def test_context_ranking_key_has_the_six_rule_v2_axes():
    from ssuksak.adapters.json_activity_reference_repository import (
        production_activity_reference_repository,
    )
    from ssuksak.planning.rules import monthly_activity_selection as rule_v2

    catalog = production_activity_reference_repository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
    )
    one = catalog.eligible_candidates(
        section_key="outdoor_play", calendar_month=7, ages=frozenset({4})
    )[0]
    key = rule_v2.context_ranking_sort_key(one, calendar_month=7)
    assert len(key) == 6
    assert key[0] == 0, "Retrieval 시점에는 같은 달 재사용 penalty가 없다"
