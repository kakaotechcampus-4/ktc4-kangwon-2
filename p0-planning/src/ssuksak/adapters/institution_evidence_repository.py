"""Strict JSON and in-memory adapters for the Institution Evidence Store port."""

from __future__ import annotations

import json
from pathlib import Path

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.domain.provenance import EvidenceSourceType
from ..planning.evidence.artifact import (
    EVIDENCE_STORE_SCHEMA_VERSION,
    EXPECTED_NORMATIVE_STATUS,
    EXPECTED_STORE_ID,
    INGESTION_VERSION,
    evidence_content_sha256,
)
from ..planning.evidence.models import (
    AgeEvidenceType,
    CellCoordinates,
    EvidenceRecord,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from ..planning.evidence.store import InstitutionEvidenceStore

DEFAULT_EVIDENCE_STORE_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evidence"
    / "institution_evidence_v0_1_0.json"
)

_RECORD_FIELDS = {
    "record_id", "source_type", "source_path", "source_sha256", "page",
    "institution_id", "institution_type", "year", "month", "age_scope",
    "age_evidence_type", "monthly_theme", "source_section", "source_label",
    "week_position", "week_label", "experience_text", "activity_text",
    "setting", "template_family", "machine_readability", "reuse_policy",
    "extraction_quality", "extraction_method", "source_cell",
}
_ROOT_FIELDS = {
    "build", "disclaimer", "ingestion_version", "normative_status",
    "record_count", "records", "schema_version", "source_count",
    "source_hash_manifest", "source_image_only_count", "source_text_layer_count",
    "store_id",
}


class EvidenceStoreError(ValueError):
    pass


def _record(raw: object, index: int) -> EvidenceRecord:
    if not isinstance(raw, dict):
        raise EvidenceStoreError(f"record[{index}] must be an object")
    unknown = set(raw) - _RECORD_FIELDS
    if unknown:
        raise EvidenceStoreError(f"record[{index}] contains unknown fields: {sorted(unknown)}")
    required = {
        "record_id", "source_type", "source_path", "source_sha256", "page",
        "age_scope", "age_evidence_type", "source_section", "source_label",
        "setting", "template_family", "machine_readability", "reuse_policy",
        "extraction_quality", "extraction_method",
    }
    missing = required - set(raw)
    if missing:
        raise EvidenceStoreError(f"record[{index}] lacks fields: {sorted(missing)}")
    cell = raw.get("source_cell")
    try:
        coordinates = None
        if cell is not None:
            if not isinstance(cell, dict) or set(cell) != {"row_top", "row_bottom", "column", "item_index"}:
                raise EvidenceStoreError(f"record[{index}].source_cell is invalid")
            coordinates = CellCoordinates(**cell)
        ages = raw["age_scope"]
        if not isinstance(ages, list):
            raise EvidenceStoreError(f"record[{index}].age_scope must be an array")
        return EvidenceRecord(
            record_id=raw["record_id"],
            source_type=EvidenceSourceType(raw["source_type"]),
            source_path=raw["source_path"],
            source_sha256=raw["source_sha256"],
            page=raw["page"],
            institution_id=raw.get("institution_id"),
            institution_type=raw.get("institution_type"),
            year=raw.get("year"),
            month=raw.get("month"),
            age_scope=tuple(ages),
            age_evidence_type=AgeEvidenceType(raw["age_evidence_type"]),
            monthly_theme=raw.get("monthly_theme"),
            source_section=SourceSection(raw["source_section"]),
            source_label=raw["source_label"],
            week_position=raw.get("week_position"),
            week_label=raw.get("week_label"),
            experience_text=raw.get("experience_text"),
            activity_text=raw.get("activity_text"),
            setting=Setting(raw["setting"]),
            template_family=raw["template_family"],
            machine_readability=MachineReadability(raw["machine_readability"]),
            reuse_policy=ReusePolicy(raw["reuse_policy"]),
            extraction_quality=ExtractionQuality(raw["extraction_quality"]),
            extraction_method=raw["extraction_method"],
            source_cell=coordinates,
        )
    except (InvalidDomainValueError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, EvidenceStoreError):
            raise
        raise EvidenceStoreError(f"record[{index}] violates EvidenceRecord: {exc}") from exc


def load_evidence_store_from_dict(
    payload: object, *, expected_content_sha256: str | None = None
) -> InstitutionEvidenceStore:
    if not isinstance(payload, dict):
        raise EvidenceStoreError("Evidence Store must be an object")
    required = {
        "store_id", "schema_version", "ingestion_version", "normative_status",
        "source_count", "source_text_layer_count", "source_image_only_count",
        "source_hash_manifest", "record_count", "records", "build",
    }
    missing = required - set(payload)
    if missing:
        raise EvidenceStoreError(f"Evidence Store lacks fields: {sorted(missing)}")
    unknown = set(payload) - _ROOT_FIELDS
    if unknown:
        raise EvidenceStoreError(f"Evidence Store contains unknown fields: {sorted(unknown)}")
    if payload["store_id"] != EXPECTED_STORE_ID:
        raise EvidenceStoreError("Evidence Store id is invalid")
    if payload["schema_version"] != EVIDENCE_STORE_SCHEMA_VERSION:
        raise EvidenceStoreError("Evidence Store schema version is invalid")
    if payload["ingestion_version"] != INGESTION_VERSION:
        raise EvidenceStoreError("Evidence Store ingestion version is invalid")
    if payload["normative_status"] != EXPECTED_NORMATIVE_STATUS:
        raise EvidenceStoreError("Evidence Store is a corpus observation, not an approved Reference")
    raw_records = payload["records"]
    manifest = payload["source_hash_manifest"]
    if not isinstance(raw_records, list) or payload["record_count"] != len(raw_records):
        raise EvidenceStoreError("Evidence Store record_count does not match records")
    if not isinstance(manifest, list) or payload["source_count"] != len(manifest):
        raise EvidenceStoreError("Evidence Store source_count does not match manifest")
    if payload["source_count"] != (
        payload["source_text_layer_count"] + payload["source_image_only_count"]
    ):
        raise EvidenceStoreError("Evidence Store readability source counts do not add up")
    manifest_by_path: dict[str, tuple[str, MachineReadability]] = {}
    for index, item in enumerate(manifest):
        if not isinstance(item, dict) or set(item) != {
            "path", "sha256", "machine_readability"
        }:
            raise EvidenceStoreError(f"source_hash_manifest[{index}] is invalid")
        try:
            path = item["path"]
            sha = item["sha256"]
            readability = MachineReadability(item["machine_readability"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceStoreError(f"source_hash_manifest[{index}] is invalid") from exc
        if not isinstance(path, str) or not path.strip():
            raise EvidenceStoreError(f"source_hash_manifest[{index}].path is invalid")
        if not isinstance(sha, str) or len(sha) != 64 or any(
            char not in "0123456789abcdef" for char in sha
        ):
            raise EvidenceStoreError(f"source_hash_manifest[{index}].sha256 is invalid")
        if path in manifest_by_path:
            raise EvidenceStoreError(f"source manifest path is duplicated: {path}")
        manifest_by_path[path] = (sha, readability)
    text_count = sum(
        readability is MachineReadability.TEXT_LAYER
        for _, readability in manifest_by_path.values()
    )
    if text_count != payload["source_text_layer_count"]:
        raise EvidenceStoreError("Evidence Store text-layer count does not match manifest")
    actual_content_sha = evidence_content_sha256(payload)
    build = payload["build"]
    if not isinstance(build, dict) or build.get("content_sha256") != actual_content_sha:
        raise EvidenceStoreError("Evidence Store content hash does not match build metadata")
    if expected_content_sha256 is not None and actual_content_sha != expected_content_sha256:
        raise EvidenceStoreError("Evidence Store content hash does not match the requested pin")
    records = tuple(_record(raw, index) for index, raw in enumerate(raw_records))
    for record in records:
        source = manifest_by_path.get(record.source_path)
        if source is None or source != (record.source_sha256, record.machine_readability):
            raise EvidenceStoreError(
                f"record source lineage is absent or mismatched: {record.record_id}"
            )
    try:
        return InstitutionEvidenceStore(
            records,
            ingestion_version=payload["ingestion_version"],
            schema_version=payload["schema_version"],
            content_sha256=actual_content_sha,
        )
    except InvalidDomainValueError as exc:
        raise EvidenceStoreError(str(exc)) from exc


class JsonInstitutionEvidenceRepository:
    def __init__(
        self,
        path: Path | str = DEFAULT_EVIDENCE_STORE_PATH,
        *,
        expected_content_sha256: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._expected = expected_content_sha256
        self._cached: InstitutionEvidenceStore | None = None

    def get_store(self) -> InstitutionEvidenceStore:
        if self._cached is None:
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                raise EvidenceStoreError(f"Cannot read Evidence Store: {self._path}") from exc
            self._cached = load_evidence_store_from_dict(
                payload, expected_content_sha256=self._expected
            )
        return self._cached


class InMemoryInstitutionEvidenceRepository:
    def __init__(self, records: tuple[EvidenceRecord, ...] = ()) -> None:
        ordered = tuple(sorted(records, key=lambda item: item.record_id))
        self._store = InstitutionEvidenceStore(
            ordered,
            ingestion_version=INGESTION_VERSION,
            schema_version=EVIDENCE_STORE_SCHEMA_VERSION,
            content_sha256="0" * 64,
        )

    def get_store(self) -> InstitutionEvidenceStore:
        return self._store
