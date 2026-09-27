"""Deterministic structured observations to Institution Evidence Store payload."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..planning.evidence.artifact import (
    EVIDENCE_STORE_SCHEMA_VERSION,
    EXPECTED_NORMATIVE_STATUS,
    EXPECTED_STORE_ID,
    INGESTION_VERSION,
    evidence_content_sha256,
)
from ..planning.domain.provenance import EvidenceSourceType
from ..planning.evidence.models import EvidenceRecord, MachineReadability
from .ports import EvidenceObservation, IngestionSource, InstitutionEvidenceReader, SourceReadError


@dataclass(frozen=True, slots=True)
class IngestionResult:
    sources: tuple[IngestionSource, ...]
    records: tuple[EvidenceRecord, ...]
    failures: tuple[tuple[str, str], ...] = ()


def _record_id(source: IngestionSource, observation: EvidenceObservation) -> str:
    cell = observation.source_cell
    return (
        f"ev_{source.sha256[:12]}_p{observation.page:02d}"
        f"_r{round(cell.row_top):05d}_c{cell.column:02d}_i{cell.item_index:02d}"
    )


def _to_record(source: IngestionSource, observation: EvidenceObservation) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=_record_id(source, observation),
        source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
        source_path=source.path,
        source_sha256=source.sha256,
        page=observation.page,
        institution_id=observation.institution_id,
        institution_type=observation.institution_type,
        year=observation.year,
        month=observation.month,
        age_scope=observation.age_scope,
        age_evidence_type=observation.age_evidence_type,
        monthly_theme=observation.monthly_theme,
        source_section=observation.source_section,
        source_label=observation.source_label,
        week_position=observation.week_position,
        week_label=observation.week_label,
        experience_text=observation.experience_text,
        activity_text=observation.activity_text,
        setting=observation.setting,
        template_family=observation.template_family,
        machine_readability=source.machine_readability,
        reuse_policy=observation.reuse_policy,
        extraction_quality=observation.extraction_quality,
        extraction_method=observation.extraction_method,
        source_cell=observation.source_cell,
    )


def ingest_sources(
    sources: tuple[IngestionSource, ...], reader: InstitutionEvidenceReader
) -> IngestionResult:
    records: list[EvidenceRecord] = []
    failures: list[tuple[str, str]] = []
    ordered_sources = tuple(sorted(sources, key=lambda source: source.path))
    for source in ordered_sources:
        if source.machine_readability is MachineReadability.IMAGE_ONLY:
            continue
        try:
            observations = reader.read(source)
        except SourceReadError as exc:
            failures.append((source.path, str(exc)))
            continue
        records.extend(_to_record(source, observation) for observation in observations)
    ordered_records = tuple(sorted(records, key=lambda record: record.record_id))
    if len({record.record_id for record in ordered_records}) != len(ordered_records):
        raise ValueError("Ingestion generated duplicate record ids")
    return IngestionResult(ordered_sources, ordered_records, tuple(failures))


def _record_payload(record: EvidenceRecord) -> dict[str, object]:
    payload = asdict(record)
    payload["age_scope"] = list(record.age_scope)
    for name in (
        "source_type", "age_evidence_type", "source_section", "setting",
        "machine_readability", "reuse_policy", "extraction_quality",
    ):
        payload[name] = getattr(record, name).value
    return {key: value for key, value in payload.items() if value is not None}


def store_content_payload(result: IngestionResult) -> dict[str, object]:
    return {
        "schema_version": EVIDENCE_STORE_SCHEMA_VERSION,
        "ingestion_version": INGESTION_VERSION,
        "store_id": EXPECTED_STORE_ID,
        "normative_status": EXPECTED_NORMATIVE_STATUS,
        "disclaimer": (
            "Corpus observations are grounding context only; they do not replace "
            "approved canonical References or become Plan values."
        ),
        "source_count": len(result.sources),
        "source_text_layer_count": sum(
            source.machine_readability is MachineReadability.TEXT_LAYER
            for source in result.sources
        ),
        "source_image_only_count": sum(
            source.machine_readability is MachineReadability.IMAGE_ONLY
            for source in result.sources
        ),
        "source_hash_manifest": [
            {
                "path": source.path,
                "sha256": source.sha256,
                "machine_readability": source.machine_readability.value,
            }
            for source in result.sources
        ],
        "record_count": len(result.records),
        "records": [_record_payload(record) for record in result.records],
    }


def finalized_store_payload(result: IngestionResult, *, generated_at: str) -> dict[str, object]:
    content = store_content_payload(result)
    return {
        **content,
        "build": {
            "content_sha256": evidence_content_sha256(content),
            "generated_at": generated_at,
        },
    }
