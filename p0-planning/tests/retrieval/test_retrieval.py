from __future__ import annotations

from dataclasses import replace

import pytest

from ssuksak.adapters.evidence_classification_repository import (
    JsonEvidenceClassificationRepository,
)
from ssuksak.adapters.institution_evidence_repository import (
    InMemoryInstitutionEvidenceRepository,
    JsonInstitutionEvidenceRepository,
)
from ssuksak.adapters.json_activity_reference_repository import JsonActivityReferenceRepository
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.classification import (
    EvidenceSemanticClassification,
    SemanticClass,
)
from ssuksak.planning.evidence.models import (
    AgeEvidenceType,
    EvidenceRecord,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from ssuksak.planning.evidence.safety_classification import (
    SafetyClassificationEntry,
    SafetyEvidenceClassification,
    SafetyReferenceKind,
)
from ssuksak.planning.evidence.safety_quality import (
    MonthScope,
    ReferenceQuality,
    ReferenceQualityEntry,
    SafetyReferenceQuality,
)
from ssuksak.planning.retrieval.models import AgeMatchKind, BlockName, RetrievalRequest
from ssuksak.planning.retrieval.ranking import (
    age_match_kind,
    apply_source_diversity,
    ngrams,
    rank_records,
)
from ssuksak.planning.retrieval.retriever import CLASS_BLOCKS, MonthlyEvidenceRetriever


def _record(
    record_id: str,
    *,
    age_scope=(3,),
    age_kind=AgeEvidenceType.SINGLE_AGE_PAGE,
    text="가을 나들이",
    theme="가을과 자연",
    section=SourceSection.OUTDOOR_PLAY,
    setting=Setting.OUTDOOR,
    institution="A",
    source_sha=None,
):
    return EvidenceRecord(
        record_id=record_id,
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path=f"{record_id}.pdf",
        source_sha256=source_sha or (record_id[-1] * 64),
        page=1,
        institution_id=institution,
        institution_type="국공립",
        year=2026,
        month=9,
        age_scope=age_scope,
        age_evidence_type=age_kind,
        monthly_theme=theme,
        source_section=section,
        source_label="바깥놀이",
        activity_text=text,
        setting=setting,
        template_family=False,
        machine_readability=MachineReadability.TEXT_LAYER,
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        extraction_quality=ExtractionQuality.VALID,
        extraction_method="test",
    )


def _request(ages=frozenset({3}), **overrides):
    values = dict(
        target_month=YearMonth(2026, 9),
        ages=ages,
        confirmed_theme_id="yr_theme_autumn_and_nature",
        confirmed_theme_value="가을과 자연",
        week_count=5,
        keywords=("나들이",),
    )
    values.update(overrides)
    return RetrievalRequest(**values)


def test_korean_ngrams_ignore_spaces_and_punctuation():
    assert ngrams("우리 동네!") == ngrams("우리동네")


def test_age_match_tiers_are_structural_not_keyword_guesses():
    assert age_match_kind(_record("ev_a"), frozenset({3})) is AgeMatchKind.SINGLE_AGE_EXACT
    mixed = _record("ev_b", age_scope=(3, 4), age_kind=AgeEvidenceType.MIXED_AGE_PAGE)
    assert age_match_kind(mixed, frozenset({4})) is AgeMatchKind.MIXED_AGE_COVERING
    assert age_match_kind(_record("ev_c"), frozenset({5})) is None


def test_ranking_combines_age_structure_theme_and_keyword_score():
    weak = _record("ev_b", text="공놀이", theme="다른 주제")
    strong = _record("ev_a", text="가을 자연 나들이", theme="가을과 자연")
    ranked = rank_records(
        (weak, strong),
        requested_ages=frozenset({3}),
        query_grams=ngrams("가을과 자연 나들이"),
    )
    assert [item.record_id for item in ranked] == ["ev_a", "ev_b"]
    assert ranked[0].trace.total_score > ranked[1].trace.total_score


def test_source_diversity_cap_is_applied_before_top_k():
    records = (
        _record("ev_a", institution="A"),
        _record("ev_b", institution="A"),
        _record("ev_c", institution="B"),
    )
    ranked = rank_records(records, requested_ages=frozenset({3}), query_grams=ngrams("가을"))
    selected = apply_source_diversity(ranked, top_k=3, institution_cap=1)
    assert len(selected) == 2
    assert {item.record.institution_id for item in selected} == {"A", "B"}


def test_retriever_returns_typed_blocks_and_does_not_invent_week_positions():
    shared = "d" * 64
    records = (
        _record("ev_a", age_scope=(3,), source_sha=shared),
        _record("ev_b", age_scope=(4,), source_sha=shared),
        _record("ev_c", section=SourceSection.WEEK_EXPERIENCE, setting=Setting.UNKNOWN),
    )
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    classification = EvidenceSemanticClassification(
        "classification-test",
        store.content_sha256,
        ((SourceSection.WEEK_EXPERIENCE, "바깥놀이", SemanticClass.SUBTHEME),),
    )
    request = replace(
        _request(frozenset({3, 4})), grounding_classes=frozenset({SemanticClass.SUBTHEME})
    )
    result = MonthlyEvidenceRetriever(store, classification=classification).retrieve(request)

    # The safety block is opt-in (safety_keywords); every other block is always present.
    assert tuple(block.name for block in result.blocks) == tuple(
        name
        for name in BlockName
        if name not in {
            BlockName.SAFETY_EDUCATION_EVIDENCE,
            BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE,
            BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE,
        }
    )
    assert result.block(BlockName.AGE_CONTRAST_EVIDENCE).size == 2
    assert result.block(BlockName.SUBTHEME_EVIDENCE).items[0].record.week_position is None


def test_real_artifact_retrieval_is_deterministic_and_uses_approved_reference():
    store = JsonInstitutionEvidenceRepository().get_store()
    catalog = JsonActivityReferenceRepository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
    )
    retriever = MonthlyEvidenceRetriever(store, activity_catalog=catalog)
    first = retriever.retrieve(_request(frozenset({3, 4})))
    second = retriever.retrieve(_request(frozenset({3, 4})))

    assert first == second
    assert first.block(BlockName.INSTITUTION_MONTHLY_EVIDENCE).size == 12
    assert first.block(BlockName.REFERENCE_ACTIVITIES).size == 12
    assert all(
        item.record.reuse_policy is ReusePolicy.CONTEXT_ONLY
        for block in first.blocks
        for item in block.items
    )


def _classified_store():
    records = (
        replace(_record("ev_g", section=SourceSection.WEEK_EXPERIENCE, setting=Setting.UNKNOWN, source_sha="e" * 64), source_label="교사의 기대"),
        replace(_record("ev_s", section=SourceSection.WEEK_EXPERIENCE, setting=Setting.UNKNOWN, source_sha="e" * 64), source_label="소주제"),
        replace(_record("ev_p", section=SourceSection.WEEK_EXPERIENCE, setting=Setting.UNKNOWN, source_sha="e" * 64), source_label="예상놀이"),
        replace(
            _record("ev_x", section=SourceSection.WEEK_EXPERIENCE, setting=Setting.UNKNOWN, source_sha="e" * 64),
            source_label="환경구성 및 예상놀이계획",
        ),
        replace(_record("ev_h", section=SourceSection.DAILY_ROUTINE, setting=Setting.UNKNOWN, source_sha="e" * 64), source_label="기본생활습관"),
        replace(_record("ev_r", section=SourceSection.DAILY_ROUTINE, setting=Setting.UNKNOWN, source_sha="e" * 64), source_label="등원"),
    )
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    classification = EvidenceSemanticClassification(
        "classification-test",
        store.content_sha256,
        (
            (SourceSection.WEEK_EXPERIENCE, "교사의 기대", SemanticClass.GOALS),
            (SourceSection.WEEK_EXPERIENCE, "소주제", SemanticClass.SUBTHEME),
            (SourceSection.WEEK_EXPERIENCE, "예상놀이", SemanticClass.EXPECTED_PLAY),
            (SourceSection.DAILY_ROUTINE, "기본생활습관", SemanticClass.BASIC_HABIT),
        ),
    )
    return store, classification


_ALL_CLASSES = frozenset(set(SemanticClass) - {SemanticClass.EXCLUDED})


def test_section_blocks_hold_only_their_approved_class_and_drop_excluded():
    store, classification = _classified_store()
    request = replace(_request(frozenset({3, 4})), grounding_classes=_ALL_CLASSES)
    result = MonthlyEvidenceRetriever(store, classification=classification).retrieve(request)

    def ids(name):
        return {item.record_id for item in result.block(name).items}

    assert ids(BlockName.GOALS_EVIDENCE) == {"ev_g"}
    assert ids(BlockName.SUBTHEME_EVIDENCE) == {"ev_s"}
    assert ids(BlockName.EXPECTED_PLAY_EVIDENCE) == {"ev_p"}
    assert ids(BlockName.BASIC_HABIT_EVIDENCE) == {"ev_h"}
    everywhere = {item.record_id for block in result.blocks for item in block.items}
    assert not everywhere & {"ev_x", "ev_r"}
    assert result.evidence_classification_version == "classification-test"


def test_inactive_section_classes_are_not_retrieved():
    store, classification = _classified_store()
    request = replace(
        _request(frozenset({3, 4})), grounding_classes=frozenset({SemanticClass.EXPECTED_PLAY})
    )
    result = MonthlyEvidenceRetriever(store, classification=classification).retrieve(request)

    assert {item.record_id for item in result.block(BlockName.EXPECTED_PLAY_EVIDENCE).items} == {"ev_p"}
    for name in (BlockName.GOALS_EVIDENCE, BlockName.SUBTHEME_EVIDENCE, BlockName.BASIC_HABIT_EVIDENCE):
        assert result.block(name).size == 0


def test_section_scoped_retrieval_fails_closed_without_a_bound_classification():
    store, classification = _classified_store()
    request = replace(_request(frozenset({3, 4})), grounding_classes=_ALL_CLASSES)

    with pytest.raises(ValueError, match="approved Evidence classification"):
        MonthlyEvidenceRetriever(store).retrieve(request)
    with pytest.raises(InvalidDomainValueError, match="different Evidence Store"):
        MonthlyEvidenceRetriever(
            store, classification=replace(classification, evidence_content_sha256="1" * 64)
        )


def test_real_section_scoped_retrieval_is_deterministic_and_class_pure():
    store = JsonInstitutionEvidenceRepository().get_store()
    classification = JsonEvidenceClassificationRepository().get_classification()
    request = replace(_request(frozenset({3, 4})), grounding_classes=_ALL_CLASSES)
    retriever = MonthlyEvidenceRetriever(store, classification=classification)
    first = retriever.retrieve(request)

    assert first == retriever.retrieve(request)
    assert first.retrieval_version == "monthly-evidence-retrieval-v0.2.0"
    for semantic_class, name in CLASS_BLOCKS.items():
        items = first.block(name).items
        assert items
        assert all(classification.class_of(item.record) is semantic_class for item in items)
        assert all(item.record.week_position is None for item in items)


def _quality(store, classification, runtime_active=True):
    return SafetyReferenceQuality(
        "quality-test", classification.classification_version, store.content_sha256,
        (
            ReferenceQualityEntry("계단에서는난간을잡아요", ReferenceQuality.USABLE, "stairs", month_scope=MonthScope.TARGET_MONTH_ONLY),
            ReferenceQualityEntry("물놀이수칙소방대피훈련누전화재", ReferenceQuality.USABLE, "water", month_scope=MonthScope.TARGET_MONTH_ONLY),
        ),
        runtime_active=runtime_active,
    )


def _safety_store_and_classification(runtime_active=True, multi_tag_needs_review=False):
    safety = dict(section=SourceSection.SAFETY_EDUCATION, setting=Setting.UNKNOWN)
    records = (
        _record("ev_outdoor_f"),
        _record("ev_safe_a", text="[교통안전] 자전거를 탈 때 안전모를 써요", **safety),
        _record("ev_safe_b", text="[생활안전] 계단에서는 난간을 잡아요", institution="B", **safety),
        _record("ev_safe_c", text="[비상대응훈련] 지진이 나면 몸을 낮춰요", **safety),
        replace(_record("ev_safe_d", text="[교통안전] 길을 건널 때 손을 들어요", **safety),
                extraction_quality=ExtractionQuality.INVALID),
        _record("ev_safe_e", text="[성폭력 예방] 싫어요 말하기", **safety),
        _record("ev_safe_1", text="교통안전 신호등 놀이", **safety),
        _record("ev_safe_2", text="[생활안전] 물놀이 수칙 [소방대피훈련] 누전 화재", institution="C", **safety),
        _record("ev_safe_3", text="[교통안전] 차에서 내리기 [생활안전] 승강기", institution="D", **safety),
    )
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    classification = SafetyEvidenceClassification(
        "safety-classification-test",
        store.content_sha256,
        "child-welfare-act-decree-annex6-2022-06-21",
        (
            SafetyClassificationEntry("교통안전", SafetyReferenceKind.STATUTORY_REFERENCE, "traffic_safety"),
            SafetyClassificationEntry("성폭력 예방", SafetyReferenceKind.STATUTORY_REFERENCE, "sexual_violence_prevention"),
            SafetyClassificationEntry("생활안전", SafetyReferenceKind.SUPPLEMENTAL_REFERENCE, supplemental_label="life_safety"),
            SafetyClassificationEntry("비상대응훈련", SafetyReferenceKind.NEEDS_REVIEW, review_reason="separate key"),
        ),
        frozenset({"life_safety"}),
        runtime_active=runtime_active,
        multi_tag_needs_review=multi_tag_needs_review,
    )
    return store, classification


def _safety_request():
    return _request(safety_keywords=("바퀴 달린 탈것의 안전한 이용법",), safety_categories=("traffic_safety",))


def test_safety_blocks_hold_only_approved_references_for_their_slot_kind():
    store, classification = _safety_store_and_classification()
    result = MonthlyEvidenceRetriever(
        store, safety_classification=classification, safety_quality=_quality(store, classification)
    ).retrieve(_safety_request())
    statutory = {item.record_id for item in result.block(BlockName.SAFETY_EDUCATION_EVIDENCE).items}
    supplemental = {item.record_id for item in result.block(BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE).items}

    # Placed-category statutory References / supplemental References only; NEEDS_REVIEW,
    # INVALID, unplaced categories and untagged records never enter. Without the
    # multi-tag rule (v0.1.0) the leading tag alone decides multi-tag records.
    assert statutory == {"ev_safe_a", "ev_safe_3"}
    assert supplemental == {"ev_safe_b", "ev_safe_2"}
    without = MonthlyEvidenceRetriever(
        store, safety_classification=classification, safety_quality=_quality(store, classification)
    ).retrieve(_request())
    assert BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE not in {block.name for block in without.blocks}


@pytest.mark.parametrize("approved", [False, None], ids=["pending", "no-classification"])
def test_safety_blocks_fail_closed_without_an_approved_classification(approved):
    store, classification = _safety_store_and_classification(runtime_active=False)
    retriever = MonthlyEvidenceRetriever(store, safety_classification=classification if approved is False else None)
    result = retriever.retrieve(_safety_request())

    assert result.block(BlockName.SAFETY_EDUCATION_EVIDENCE).items == ()
    assert result.block(BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE).items == ()


def test_multi_tag_records_never_enter_safety_retrieval_under_the_multi_tag_rule():
    store, classification = _safety_store_and_classification(multi_tag_needs_review=True)
    result = MonthlyEvidenceRetriever(
        store, safety_classification=classification, safety_quality=_quality(store, classification)
    ).retrieve(_safety_request())
    ids = {
        item.record_id
        for name in (BlockName.SAFETY_EDUCATION_EVIDENCE, BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE)
        for item in result.block(name).items
    }

    assert ids == {"ev_safe_a", "ev_safe_b"}


@pytest.mark.parametrize("quality", ["pending", "missing", "unlisted"])
def test_supplemental_retrieval_needs_an_approved_usable_quality_entry(quality):
    store, classification = _safety_store_and_classification()
    review = {
        "pending": _quality(store, classification, runtime_active=False),
        "missing": None,
        "unlisted": replace(_quality(store, classification), entries=()),
    }[quality]
    result = MonthlyEvidenceRetriever(store, safety_classification=classification, safety_quality=review).retrieve(
        _safety_request()
    )

    assert result.block(BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE).items == ()
    assert {item.record_id for item in result.block(BlockName.SAFETY_EDUCATION_EVIDENCE).items} == {"ev_safe_a", "ev_safe_3"}


def test_cross_month_fallback_takes_only_month_independent_contents_with_age_fit():
    safety = dict(section=SourceSection.SAFETY_EDUCATION, setting=Setting.UNKNOWN)
    records = (
        _record("ev_safe_a", text="[생활안전] 계단에서는 난간을 잡아요", **safety),  # target month (9)
        replace(_record("ev_safe_b", text="[생활안전] 놀이터에서 안전하게 놀아요", institution="B", **safety), month=5),
        replace(_record("ev_safe_c", text="[생활안전] 사람이 많이 모이는 곳을 조심해요", institution="C", **safety), month=5),
        replace(_record("ev_safe_d", text="[생활안전] 손이 끼었어요", age_scope=(5,), institution="D", **safety), month=6),
    )
    store = InMemoryInstitutionEvidenceRepository(records).get_store()
    classification = SafetyEvidenceClassification(
        "safety-classification-test", store.content_sha256, "child-welfare-act-decree-annex6-2022-06-21",
        (SafetyClassificationEntry("생활안전", SafetyReferenceKind.SUPPLEMENTAL_REFERENCE, supplemental_label="life_safety"),),
        frozenset({"life_safety"}), runtime_active=True,
    )
    independent, target_only = MonthScope.MONTH_INDEPENDENT, MonthScope.TARGET_MONTH_ONLY
    quality = SafetyReferenceQuality(
        "quality-test", classification.classification_version, store.content_sha256,
        (
            ReferenceQualityEntry("계단에서는난간을잡아요", ReferenceQuality.USABLE, "stairs", month_scope=independent),
            ReferenceQualityEntry("놀이터에서안전하게놀아요", ReferenceQuality.USABLE, "playground", month_scope=independent),
            ReferenceQualityEntry("사람이많이모이는곳을조심해요", ReferenceQuality.USABLE, "crowd", month_scope=target_only),
            ReferenceQualityEntry("손이끼었어요", ReferenceQuality.USABLE, "finger_pinch", month_scope=independent),
        ),
        runtime_active=True,
    )
    result = MonthlyEvidenceRetriever(store, safety_classification=classification, safety_quality=quality).retrieve(
        _safety_request()
    )

    assert {i.record_id for i in result.block(BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE).items} == {"ev_safe_a"}
    # crowd is TARGET_MONTH_ONLY; the finger-pinch record is age 5 only (request is age 3).
    assert {i.record_id for i in result.block(BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE).items} == {"ev_safe_b"}
