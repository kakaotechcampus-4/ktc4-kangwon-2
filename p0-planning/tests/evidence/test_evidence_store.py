from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ssuksak.adapters.institution_evidence_repository import (
    DEFAULT_EVIDENCE_STORE_PATH,
    EvidenceStoreError,
    JsonInstitutionEvidenceRepository,
    load_evidence_store_from_dict,
)
from ssuksak.planning.evidence.artifact import evidence_content_sha256
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.evidence.models import ExtractionQuality, ReusePolicy
from ssuksak.planning.evidence.ports import InstitutionEvidenceRepository

EXPECTED_FILE_SHA = "5bf84e5a59fd74880b040ea1e545b00f4ddbe8cd1cc07da11a416161dedc8bb4"
EXPECTED_CONTENT_SHA = "7d6d9bdb29dc5e84c024acc418a092c6e01d72134cf51043ab5dfd38a1332463"


@pytest.fixture(scope="module")
def payload():
    return json.loads(DEFAULT_EVIDENCE_STORE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def store():
    return JsonInstitutionEvidenceRepository().get_store()


def test_approved_artifact_bytes_and_lf_are_frozen():
    raw = DEFAULT_EVIDENCE_STORE_PATH.read_bytes()
    assert len(raw) == 14_007_752
    assert b"\r" not in raw
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_FILE_SHA


def test_real_store_contract_and_counts(store, payload):
    assert isinstance(JsonInstitutionEvidenceRepository(), InstitutionEvidenceRepository)
    assert len(store) == payload["record_count"] == 12_325
    assert payload["source_count"] == len(payload["source_hash_manifest"]) == 349
    assert payload["source_text_layer_count"] == 326
    assert payload["source_image_only_count"] == 23
    assert store.content_sha256 == EXPECTED_CONTENT_SHA


def test_privacy_derivative_removes_whole_records_and_preserves_every_retained_field(payload):
    original = json.loads(DEFAULT_EVIDENCE_STORE_PATH.with_name("institution_evidence_v0_1_0.json").read_text(encoding="utf-8"))
    removed = set(payload["build"]["removed_record_ids"])
    assert len(removed) == 42
    assert {r["record_id"] for r in original["records"]} - {r["record_id"] for r in payload["records"]} == removed
    retained = [r for r in original["records"] if r["record_id"] not in removed]
    # Digest comparisons keep excluded personal text out of assertion output.
    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    retained_sha, actual_sha = digest(retained), digest(payload["records"])
    original_manifest_sha = digest(original["source_hash_manifest"])
    actual_manifest_sha = digest(payload["source_hash_manifest"])
    assert retained_sha == actual_sha
    assert original_manifest_sha == actual_manifest_sha


def test_record_uses_pr0_evidence_source_and_preserves_reuse_policy(store):
    record = store.records[0]
    assert record.source_type is EvidenceSourceType.INSTITUTION_SAMPLE
    assert record.reuse_policy is ReusePolicy.CONTEXT_ONLY
    assert record.extraction_quality in ExtractionQuality
    assert record.general_grounding_eligible


def test_store_is_immutable_and_indexed(store):
    assert len(store.by_month(9)) == 2019
    with pytest.raises(AttributeError):
        store.records = ()
    with pytest.raises(FrozenInstanceError):
        store.records[0].page = 2


def test_content_pin_is_enforced(payload):
    with pytest.raises(EvidenceStoreError, match="requested pin"):
        load_evidence_store_from_dict(payload, expected_content_sha256="0" * 64)


@pytest.mark.parametrize(
    ("version", "supported"),
    [
        ("institution-evidence-ingestion-v0.1.0", True),
        ("institution-evidence-ingestion-v0.2.0", True),
        ("institution-evidence-ingestion-v9.9.9", False),
        ([], False),
        ({}, False),
    ],
)
def test_loader_accepts_supported_store_versions_and_keeps_the_one_read(payload, version, supported):
    altered = dict(payload)
    altered["ingestion_version"] = version
    altered["build"] = {"content_sha256": evidence_content_sha256(altered)}
    if not supported:
        with pytest.raises(EvidenceStoreError, match="ingestion version is invalid"):
            load_evidence_store_from_dict(altered)
        return
    # The version read is what every INSTITUTION_SAMPLE Evidence cites as source_version.
    assert load_evidence_store_from_dict(altered).ingestion_version == version


def test_normative_status_cannot_be_confused_with_approved_reference(payload):
    altered = dict(payload)
    altered["normative_status"] = "HUMAN_APPROVED"
    with pytest.raises(EvidenceStoreError, match="corpus observation"):
        load_evidence_store_from_dict(altered)


def test_record_unknown_field_is_rejected(payload):
    altered = dict(payload)
    first = dict(payload["records"][0])
    first["future_field"] = "not silently accepted"
    altered["records"] = [first]
    altered["record_count"] = 1
    altered["source_hash_manifest"] = payload["source_hash_manifest"]
    altered["build"] = {"content_sha256": evidence_content_sha256(altered)}
    with pytest.raises(EvidenceStoreError, match="unknown fields"):
        load_evidence_store_from_dict(altered)
