from __future__ import annotations

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

EXPECTED_FILE_SHA = "8479c0490a002d9336688c1b6cacf47f2d2c083201b15df01258336c07e0ba1a"
EXPECTED_CONTENT_SHA = "52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea"


@pytest.fixture(scope="module")
def payload():
    return json.loads(DEFAULT_EVIDENCE_STORE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def store():
    return JsonInstitutionEvidenceRepository().get_store()


def test_approved_artifact_bytes_and_lf_are_frozen():
    import hashlib

    raw = DEFAULT_EVIDENCE_STORE_PATH.read_bytes()
    assert len(raw) == 10_947_167
    assert b"\r" not in raw
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_FILE_SHA


def test_real_store_contract_and_counts(store, payload):
    assert isinstance(JsonInstitutionEvidenceRepository(), InstitutionEvidenceRepository)
    assert len(store) == payload["record_count"] == 12_367
    assert payload["source_count"] == len(payload["source_hash_manifest"]) == 349
    assert payload["source_text_layer_count"] == 326
    assert payload["source_image_only_count"] == 23
    assert store.content_sha256 == EXPECTED_CONTENT_SHA


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
