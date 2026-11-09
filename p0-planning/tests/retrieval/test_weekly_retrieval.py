from __future__ import annotations

import collections

import pytest
from ssuksak.adapters.institution_evidence_repository import (
    InMemoryInstitutionEvidenceRepository,
    JsonInstitutionEvidenceRepository,
)
from ssuksak.adapters.weekly_evidence_classification_repository import (
    JsonWeeklyEvidenceClassificationRepository,
)
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.evidence.models import (
    AgeEvidenceType,
    EvidenceRecord,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from ssuksak.planning.evidence.weekly_classification import (
    WeeklyEvidenceClassification,
    WeeklySemanticClass,
)
from ssuksak.planning.retrieval.models import AGE_VERIFIABLE_TIERS
from ssuksak.planning.retrieval.weekly import activity_type, weekly_section_evidence

INDOOR = WeeklySemanticClass.INDOOR_PLAY


def _record(record_id, *, month=9, label="쌓기", age_scope=(3,), institution="A",
            quality=ExtractionQuality.VALID, text="가을 열매 쌓기"):
    return EvidenceRecord(
        record_id=record_id,
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path=f"{record_id}.pdf",
        source_sha256=record_id[-1] * 64,
        page=1,
        institution_id=institution,
        institution_type="국공립",
        year=2026,
        month=month,
        age_scope=age_scope,
        age_evidence_type=AgeEvidenceType.SINGLE_AGE_PAGE if age_scope else AgeEvidenceType.AGE_UNKNOWN,
        monthly_theme="가을",
        source_section=SourceSection.INDOOR_PLAY,
        source_label=label,
        activity_text=text,
        setting=Setting.INDOOR,
        template_family=False,
        machine_readability=MachineReadability.TEXT_LAYER,
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        extraction_quality=quality,
        extraction_method="test",
    )


def _search(records, **overrides):
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    classification = WeeklyEvidenceClassification(
        "weekly-classification-test",
        store.content_sha256,
        (
            (SourceSection.INDOOR_PLAY, "쌓기", INDOOR),
            (SourceSection.INDOOR_PLAY, "이야기 나누기", WeeklySemanticClass.GROUP_ACTIVITY),
            (SourceSection.INDOOR_PLAY, "실내대체", WeeklySemanticClass.INDOOR_ALTERNATIVE),
        ),
    )
    arguments = dict(weekly_class=INDOOR, calendar_month=9, ages=frozenset({3}), query_text="가을 열매")
    arguments.update(overrides)
    return [item.record_id for item in weekly_section_evidence(store, classification, **arguments)]


def test_only_that_class_that_month_valid_and_age_verified_records_are_used():
    records = (
        _record("ev_1"),
        _record("ev_2", month=10),  # another month
        _record("ev_3", label="이야기 나누기"),  # another class
        _record("ev_4", label="미술"),  # unlisted: EXCLUDED
        _record("ev_5", quality=ExtractionQuality.NEEDS_REVIEW),
        _record("ev_6", age_scope=()),  # age unknown (decision B)
        _record("ev_7", age_scope=(5,)),  # another age
    )
    assert _search(records) == ["ev_1"]
    assert _search(records, weekly_class=WeeklySemanticClass.GROUP_ACTIVITY) == ["ev_3"]


def test_new_generation_excludes_venue_bound_source_without_rewriting_it():
    records = (_record("ev_1", text="<현장학습> 배산유아숲터 숲체험"),
               _record("ev_2", text="부산시민공원 가을소풍"),
               _record("ev_3", text="자연물로 겨울나무 꾸미기"))
    assert _search(records, exclude_venue_bound=True) == ["ev_3"]
    assert records[0].text == "<현장학습> 배산유아숲터 숲체험"


def test_indoor_methods_are_explicit_without_bypassing_month_age_or_class():
    records = (
        _record("ev_1", label="실내대체", text="겨울나무를 표현해요"),
        _record("ev_2", label="실내대체", text="겨울나무를 몸으로 표현해요"),
        _record("ev_3", label="실내대체", text="겨울나무를 몸으로 표현해요", age_scope=()),
        _record("ev_4", label="실내대체", text="겨울나무를 몸으로 표현해요", month=12),
        _record("ev_5", label="쌓기", text="겨울나무를 몸으로 표현해요"),
    )
    assert _search(records, weekly_class=WeeklySemanticClass.INDOOR_ALTERNATIVE,
                   query_text="겨울나무", explicit_indoor_methods=True) == ["ev_2", "ev_1"]
    assert _search(records, weekly_class=WeeklySemanticClass.INDOOR_ALTERNATIVE,
                   query_text="겨울나무") == ["ev_1", "ev_2"]  # legacy requests keep their ranking
    assert _search(records, query_text="겨울나무") == ["ev_5"]


@pytest.mark.parametrize("text,label,expected", [
    ("[이야기 나누기] 가을 이야기", "대소집단", "이야기나누기"),
    ("[이야기나누기] 가을 이야기", "대소집단", "이야기나누기"),
    ("(휴지심,종이컵) 소리 탐색", "대소집단", "기타"),
    ("[모두 함께 체험해요] 놀이", "대소집단", "기타"),
    ("(휴지심,종이컵) 소리 탐색", "음 률", "음률"),
    ("[과학·요리] 음식 만들기", "대소집단", "과학·요리"),
])
def test_activity_types_normalize_spacing_and_do_not_copy_material_notes(text, label, expected):
    assert activity_type(_record("ev_1", text=text, label=label)) == expected


def test_at_most_two_per_institution_and_top_k():
    records = tuple(_record(f"ev_{i}", institution="A" if i < 4 else f"I{i}") for i in range(1, 10))
    found = _search(records, top_k=5)
    assert len(found) == 5
    assert sum(record_id in {"ev_1", "ev_2", "ev_3"} for record_id in found) == 2


def test_candidate_pools_fill_leftover_slots_with_capped_sources_after_distinct_ones():
    # Human Decision 2026-11-05(하민): for candidates the source cap orders, it does not cut.
    records = tuple(_record(f"ev_{i}", text=f"가을 열매 쌓기 {i}") for i in range(1, 7)) + (
        _record("ev_7", text="가을 열매 쌓기 7", institution="B"),
        _record("ev_8", text="가을 열매 쌓기 8", institution="C"),
    )
    assert len(_search(records, top_k=5)) == 4
    found = _search(records, top_k=5, by_activity_type=True)
    assert len(found) == 5
    assert {"ev_7", "ev_8"} <= set(found[:4]) and sum(r not in {"ev_7", "ev_8"} for r in found[:4]) == 2
    assert found[4] not in {"ev_7", "ev_8"}
    assert len(_search(records, top_k=20, by_activity_type=True)) == 8


def test_earlier_weeks_evidence_goes_last_and_fills_a_shortfall_least_used_first():
    # 2026-11-09 하민: skip what earlier weeks of the month used; fill only a shortfall.
    records = tuple(_record(f"ev_{i}", text=f"가을 열매 쌓기 {i}", institution=f"I{i}") for i in range(1, 7))
    today = _search(records, top_k=3, by_activity_type=True)
    assert _search(records, top_k=3, by_activity_type=True, prior_week_refs=()) == today
    assert _search(records, top_k=3, by_activity_type=True, prior_week_refs=tuple(today)) == [
        r for r in _search(records, top_k=6, by_activity_type=True) if r not in today
    ]
    used = ("ev_1", "ev_1", "ev_2", "ev_3", "ev_4", "ev_5")  # ev_6 unused; ev_1 used twice
    found = _search(records, top_k=4, by_activity_type=True, prior_week_refs=used)
    assert found[0] == "ev_6" and "ev_1" not in found and len(found) == 4
    # A tag-only title surfaced in the 11-09 live run once earlier weeks took the top of the pool.
    tagged = records + (_record("ev_7", text="[절기놀이]", institution="I7"),
                        _record("ev_8", text="【동시", institution="I8"))
    assert {"ev_7", "ev_8"}.isdisjoint(_search(tagged, top_k=8, by_activity_type=True, prior_week_refs=used))


def test_a_sample_seed_picks_top_k_from_the_top_pool_in_rank_order():
    # 2026-11-10 하민: sample 10 of the top 20; no seed keeps the fixed cut.
    records = tuple(_record(f"ev_{i:02}", text=f"가을 열매 쌓기 {i}", institution=f"I{i}") for i in range(30))
    ranked = _search(records, top_k=30, by_activity_type=True)
    assert _search(records, top_k=10, by_activity_type=True, sample_seed=None) == ranked[:10]
    picks = {seed: _search(records, top_k=10, by_activity_type=True, sample_seed=seed) for seed in range(5)}
    for found in picks.values():
        assert len(found) == 10 and set(found) <= set(ranked[:20])
        assert found == sorted(found, key=ranked.index)
    assert picks[0] == _search(records, top_k=10, by_activity_type=True, sample_seed=0)
    assert len({tuple(found) for found in picks.values()}) > 1
    used = tuple(ranked[:5])  # earlier weeks still go out first, before sampling
    assert set(used).isdisjoint(_search(records, top_k=10, by_activity_type=True, sample_seed=1, prior_week_refs=used))
    # 2026-11-10 하민 (b): exact-age records fill first; sampling happens only inside the tier that overflows.
    mixed = tuple(_record(f"ev_m{i:02}", text=f"가을 열매 쌓기 m{i}", institution=f"M{i}", age_scope=(3, 4))
                  for i in range(10))
    tiered = mixed + records[:6]
    for seed in range(5):
        found = _search(tiered, top_k=10, by_activity_type=True, sample_seed=seed)
        assert len(found) == 10 and {f"ev_{i:02}" for i in range(6)} <= set(found)
    assert len({tuple(_search(tiered, top_k=10, by_activity_type=True, sample_seed=s)) for s in range(5)}) > 1
    # PR #469 review: a mixed class keeps every requested age the overflowing tier has (balance_by_age).
    by_age = tuple(_record(f"ev_a{age}{i:02}", text=f"가을 열매 쌓기 {age}-{i}", institution=f"A{age}{i}",
                           age_scope=(age,)) for age, n in ((3, 12), (4, 1), (5, 12)) for i in range(n))
    for seed in range(30):
        found = _search(by_age, top_k=10, by_activity_type=True, sample_seed=seed, ages=frozenset({3, 4, 5}))
        assert len(found) == 10 and "ev_a400" in found


def test_parent_citation_survives_top_k_without_bypassing_eligibility_or_source_cap():
    records = tuple(_record(f"ev_{i:02}", institution=f"I{i}") for i in range(12)) + (
        _record("ev_99", text="놀이터 약속", institution="parent"),
        _record("ev_80", month=10),
        _record("ev_81", label="이야기 나누기"),
        _record("ev_82", age_scope=()),
        _record("ev_83", age_scope=(5,)),
        _record("ev_84", quality=ExtractionQuality.NEEDS_REVIEW),
    )
    assert "ev_99" not in _search(records)
    found = _search(records, preferred_refs=("ev_99", "ev_80", "ev_81", "ev_82", "ev_83", "ev_84"))
    assert found[0] == "ev_99"
    assert len(found) == 10
    assert not set(found) & {"ev_80", "ev_81", "ev_82", "ev_83", "ev_84"}
    assert _search(records) == _search(records, preferred_refs=())
    same_source = tuple(_record(f"ev_{i:02}", institution="parent") for i in range(4))
    assert len(_search(same_source, preferred_refs=("ev_00", "ev_01", "ev_02"))) == 2


def test_mixed_age_requests_are_balanced_by_age():
    records = tuple(_record(f"ev_3{i}", age_scope=(3,), institution=f"T{i}") for i in range(3)) + tuple(
        _record(f"ev_4{i}", age_scope=(4,), institution=f"F{i}") for i in range(3)
    )
    found = _search(records, ages=frozenset({3, 4}), top_k=4)
    assert sorted(record_id[3] for record_id in found) == ["3", "3", "4", "4"]


@pytest.mark.parametrize("weekly_class,label,ref,text", [
    (INDOOR, "쌓기", "ev_010245b6472d_p01_r00208_c05_i02", "우리 반에서 지켜야 할 약속"),
    (WeeklySemanticClass.GROUP_ACTIVITY, "이야기 나누기", "ev_e5e84e83db52_p01_r00428_c01_i02", "파랑새반 약속!"),
])
def test_reviewed_unclear_sources_are_removed_before_candidate_ranking_only(weekly_class, label, ref, text):
    reviewed = _record(ref, text=text, label=label, institution="reviewed")
    clear = _record("ev_99", text="우리 반 놀잇감 책 만들기", label=label, institution="clear")
    records = (reviewed, clear)
    normal = _search(records, weekly_class=weekly_class, query_text="", top_k=20)
    assert set(normal) == {r.record_id for r in records}
    assert _search(records, weekly_class=weekly_class, query_text="", by_activity_type=True) == [clear.record_id]


def test_candidate_source_review_is_not_a_word_length_or_genre_filter():
    ref, text = "ev_e5e84e83db52_p01_r00428_c01_i02", "파랑새반 약속!"
    records = (
        _record(ref, text="우리 반 약속 카드 만들기", institution="changed"),
        _record("ev_97", text=text, institution="unreviewed"),
        _record("ev_98", text="책 만들기", institution="short"),
    )
    found = _search(records, by_activity_type=True, query_text="")
    assert set(found) == {r.record_id for r in records}


def test_reviewed_candidate_sources_match_the_unchanged_evidence_artifact():
    from ssuksak.planning.retrieval.weekly import REVIEWED_UNCLEAR_ACTIVITY_SOURCES

    records = {r.record_id: r for r in JsonInstitutionEvidenceRepository().get_store().records}
    assert REVIEWED_UNCLEAR_ACTIVITY_SOURCES
    for ref, text in REVIEWED_UNCLEAR_ACTIVITY_SOURCES:
        assert records[ref].text == text
        assert records[ref].month in {3, 12}  # the months reviewed so far


@pytest.mark.parametrize("text,expected,terms", [
    ("【이야기나누기】 친구와 같은 점과 다른 점 【음악】 사랑의 인사 【미술】 친구 얼굴 꾸미기",
     "【이야기나누기】 친구와 같은 점과 다른 점", ()),
    ("[명화] ‘아이들 놀이’", "[명화] ‘아이들 놀이’", ("감상",)),
    ("동화[바람과 햇님]듣기", "동화[바람과 햇님]듣기", ("듣기",)),
    ("‘ㄱ, ㄴ, ㄷ’ 낱말을 배워요", "‘ㄱ, ㄴ, ㄷ’ 낱말을 배워요", ()),
    ("종이, 빨대로 만들기", "종이, 빨대로 만들기", ()),
])
def test_candidate_activity_basis_uses_only_explicit_tag_boundaries(text, expected, terms):
    from ssuksak.planning.retrieval.weekly import candidate_activity_basis

    basis, required = candidate_activity_basis(_record("ev_1", text=text))
    assert basis == expected and required == terms
    assert basis in text


def test_reviewed_letter_activity_does_not_apply_to_revised_or_unrelated_sources():
    from ssuksak.planning.retrieval.weekly import candidate_activity_basis

    ref = "ev_e5e84e83db52_p01_r00428_c01_i01"
    text = "<이야기 나누기> 편지 발표, 함께 지켜요"
    assert candidate_activity_basis(_record(ref, text=text)) == ("편지 발표", ("편지", "발표"))
    assert candidate_activity_basis(_record("ev_99", text=text)) == (text, ())
    revised = "<이야기 나누기> 편지 읽기, 함께 지켜요"
    assert candidate_activity_basis(_record(ref, text=revised)) == (revised, ())


def test_a_classification_for_another_store_is_refused():
    store = InMemoryInstitutionEvidenceRepository((_record("ev_1"),)).get_store()
    other = WeeklyEvidenceClassification(
        "weekly-classification-test", "f" * 64, ((SourceSection.INDOOR_PLAY, "쌓기", INDOOR),)
    )
    with pytest.raises(InvalidDomainValueError):
        weekly_section_evidence(
            store, other, weekly_class=INDOOR, calendar_month=9, ages=frozenset({3}), query_text=""
        )


def test_focus_search_keeps_hard_filters_and_falls_back_when_all_grams_are_shared():
    records = (
        _record("ev_1", text="가을 나들이", institution="A"),
        _record("ev_2", text="세계 전통 의상을 꾸며요", institution="B"),
        _record("ev_3", text="세계 의상", month=10, institution="C"),
        _record("ev_4", text="세계 의상", age_scope=(), institution="D"),
    )
    assert _search(records, query_text="가을 나들이", top_k=1) == ["ev_1"]
    assert _search(records, query_text="가을 나들이", top_k=1, focus_text="세계 의상",
                   sibling_focuses=("우리나라 음식", "우리나라 놀이", "세계 의상")) == ["ev_2"]
    assert _search(records, query_text="가을 나들이", top_k=1, focus_text="우리나라",
                   sibling_focuses=("우리나라", "우리나라")) == ["ev_1"]


@pytest.mark.parametrize("weekly_class", [c for c in WeeklySemanticClass if c is not WeeklySemanticClass.EXCLUDED])
def test_the_approved_classification_grounds_every_month_and_age(weekly_class):
    store = JsonInstitutionEvidenceRepository().get_store()
    classification = JsonWeeklyEvidenceClassificationRepository().get_classification()
    for month in range(1, 13):
        for ages in (frozenset({3}), frozenset({4}), frozenset({5}), frozenset({3, 4, 5})):
            items = weekly_section_evidence(
                store, classification, weekly_class=weekly_class, calendar_month=month, ages=ages, query_text=""
            )
            assert items, (weekly_class, month, ages)
            assert len(items) <= 10
            assert max(collections.Counter(i.trace.diversity_group for i in items).values()) <= 2
            for item in items:
                assert item.record.month == month
                assert classification.class_of(item.record) is weekly_class
                assert item.trace.age_match in AGE_VERIFIABLE_TIERS
