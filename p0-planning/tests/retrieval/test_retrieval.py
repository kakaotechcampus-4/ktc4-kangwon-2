from __future__ import annotations

from ssuksak.adapters.institution_evidence_repository import (
    InMemoryInstitutionEvidenceRepository,
    JsonInstitutionEvidenceRepository,
)
from ssuksak.adapters.json_activity_reference_repository import JsonActivityReferenceRepository
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.models import (
    AgeEvidenceType,
    EvidenceRecord,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from ssuksak.planning.retrieval.models import AgeMatchKind, BlockName, RetrievalRequest
from ssuksak.planning.retrieval.ranking import (
    age_match_kind,
    apply_source_diversity,
    ngrams,
    rank_records,
)
from ssuksak.planning.retrieval.retriever import MonthlyEvidenceRetriever


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
    result = MonthlyEvidenceRetriever(store).retrieve(_request(frozenset({3, 4})))

    assert tuple(block.name for block in result.blocks) == tuple(BlockName)
    assert result.block(BlockName.AGE_CONTRAST_EVIDENCE).size == 2
    assert result.block(BlockName.WEEK_EXPERIENCE_CANDIDATES).items[0].record.week_position is None


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
