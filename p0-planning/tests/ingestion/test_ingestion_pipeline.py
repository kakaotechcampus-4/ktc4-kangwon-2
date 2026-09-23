from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ssuksak.adapters.institution_evidence_repository import load_evidence_store_from_dict
from ssuksak.ingestion.pipeline import finalized_store_payload, ingest_sources
from ssuksak.ingestion.ports import (
    EvidenceObservation,
    IngestionSource,
    SourceReadError,
)
from ssuksak.planning.evidence.models import (
    AgeEvidenceType,
    CellCoordinates,
    ExtractionQuality,
    MachineReadability,
    Setting,
    SourceSection,
)


def _source(name: str, *, readable=True):
    return IngestionSource(
        f"references/samples/monthly/{name}.pdf",
        ("a" if name == "a" else "b") * 64,
        MachineReadability.TEXT_LAYER if readable else MachineReadability.IMAGE_ONLY,
    )


def _observation(text="가을 나들이", *, row=10.2):
    return EvidenceObservation(
        page=1,
        institution_id="기관",
        institution_type="국공립",
        year=2026,
        month=9,
        age_scope=(3,),
        age_evidence_type=AgeEvidenceType.SINGLE_AGE_PAGE,
        monthly_theme="가을",
        source_section=SourceSection.OUTDOOR_PLAY,
        source_label="바깥놀이",
        activity_text=text,
        setting=Setting.OUTDOOR,
        extraction_quality=ExtractionQuality.VALID,
        extraction_method="fake_geometry_v1",
        source_cell=CellCoordinates(row, row + 10, 2, 1),
    )


class Reader:
    def read(self, source):
        if source.path.endswith("broken.pdf"):
            raise SourceReadError("cannot read")
        return (_observation(source.path),)


def test_ingestion_is_sorted_and_skips_image_only_without_guessing():
    result = ingest_sources((_source("b"), _source("a"), _source("image", readable=False)), Reader())

    assert tuple(source.path for source in result.sources) == tuple(sorted(source.path for source in result.sources))
    assert len(result.records) == 2
    assert all(record.machine_readability is MachineReadability.TEXT_LAYER for record in result.records)
    assert tuple(record.record_id for record in result.records) == tuple(sorted(record.record_id for record in result.records))


def test_ingestion_records_reader_failure_without_fabricating_records():
    broken = IngestionSource("broken.pdf", "c" * 64, MachineReadability.TEXT_LAYER)
    result = ingest_sources((broken,), Reader())
    assert result.records == ()
    assert result.failures == (("broken.pdf", "cannot read"),)


def test_same_input_produces_same_record_id():
    source = _source("a")
    first = ingest_sources((source,), Reader())
    second = ingest_sources((source,), Reader())
    assert first.records[0].record_id == second.records[0].record_id


def test_duplicate_source_coordinate_is_rejected():
    class DuplicateReader:
        def read(self, source):
            return (_observation("one"), _observation("two"))

    with pytest.raises(ValueError, match="duplicate record ids"):
        ingest_sources((_source("a"),), DuplicateReader())


def test_finalized_payload_round_trips_through_store_contract():
    result = ingest_sources((_source("a"), _source("image", readable=False)), Reader())
    payload = finalized_store_payload(result, generated_at="2026-09-20T00:00:00+09:00")
    store = load_evidence_store_from_dict(payload)

    assert len(store) == 1
    assert payload["source_count"] == 2
    assert payload["source_image_only_count"] == 1


def test_ingestion_observation_is_immutable():
    observation = _observation()
    with pytest.raises(FrozenInstanceError):
        observation.month = 10
