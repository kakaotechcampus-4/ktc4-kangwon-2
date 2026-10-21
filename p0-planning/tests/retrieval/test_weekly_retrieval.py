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
from ssuksak.planning.retrieval.weekly import weekly_section_evidence

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


def test_at_most_two_per_institution_and_top_k():
    records = tuple(_record(f"ev_{i}", institution="A" if i < 4 else f"I{i}") for i in range(1, 10))
    found = _search(records, top_k=5)
    assert len(found) == 5
    assert sum(record_id in {"ev_1", "ev_2", "ev_3"} for record_id in found) == 2


def test_mixed_age_requests_are_balanced_by_age():
    records = tuple(_record(f"ev_3{i}", age_scope=(3,), institution=f"T{i}") for i in range(3)) + tuple(
        _record(f"ev_4{i}", age_scope=(4,), institution=f"F{i}") for i in range(3)
    )
    found = _search(records, ages=frozenset({3, 4}), top_k=4)
    assert sorted(record_id[3] for record_id in found) == ["3", "3", "4", "4"]


def test_a_classification_for_another_store_is_refused():
    store = InMemoryInstitutionEvidenceRepository((_record("ev_1"),)).get_store()
    other = WeeklyEvidenceClassification(
        "weekly-classification-test", "f" * 64, ((SourceSection.INDOOR_PLAY, "쌓기", INDOOR),)
    )
    with pytest.raises(InvalidDomainValueError):
        weekly_section_evidence(
            store, other, weekly_class=INDOOR, calendar_month=9, ages=frozenset({3}), query_text=""
        )


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
