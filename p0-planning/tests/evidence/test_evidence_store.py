from __future__ import annotations

import hashlib
import json
import re
from dataclasses import FrozenInstanceError

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

EXPECTED_FILE_SHA = "d680b955ce8efb39b0cd42107e2424af32c54dbf807b525ee5a7242657a5e562"
EXPECTED_CONTENT_SHA = "4e01195eea06f28c71548b7c091ad8223b322b155e54f2bcbab957132f9cd7cd"


@pytest.fixture(scope="module")
def payload():
    return json.loads(DEFAULT_EVIDENCE_STORE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def store():
    return JsonInstitutionEvidenceRepository().get_store()


def test_approved_artifact_bytes_and_lf_are_frozen():
    raw = DEFAULT_EVIDENCE_STORE_PATH.read_bytes()
    assert len(raw) == 12_506_806
    assert b"\r" not in raw
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_FILE_SHA


def test_real_store_contract_and_counts(store, payload):
    assert isinstance(JsonInstitutionEvidenceRepository(), InstitutionEvidenceRepository)
    assert len(store) == payload["record_count"] == 12_324
    assert payload["source_count"] == len(payload["source_hash_manifest"]) == 349
    assert payload["source_text_layer_count"] == 326
    assert payload["source_image_only_count"] == 23
    assert store.content_sha256 == EXPECTED_CONTENT_SHA


def test_removal_reasons_cover_ids_and_followup_review_preserves_original_audit(payload):
    build = payload["build"]
    removed = set(build["removed_record_ids"])
    assert len(removed) == len(build["removed_record_ids"]) == 43
    assert set(build["removal_reasons"]) == removed
    original = build["privacy_review"]
    assert (
        original["reviewed_records"],
        original["removed_records"],
        original["kept_records"],
    ) == (74, 42, 32)
    assert (
        original["decisions_sha256"]
        == "ab6810e6173d276fdde506b31e64fdd4ab3226e43a701a15c673e424335c64e9"
    )
    ids = [
        record_id
        for review in build["privacy_review_addenda"]
        for record_id in review["removed_record_ids"]
    ]
    assert len(ids) == len(set(ids)) == 1
    assert set(ids) <= removed
    assert original["removed_records"] + len(ids) == len(removed)
    for review in build["privacy_review_addenda"]:
        assert review["removed_records"] == len(review["removed_record_ids"])
        assert review["decision_ref"] and review["source_commit"] and review["reviewer_id"]
        assert all(
            build["removal_reasons"][record_id] == review["reason_code"]
            for record_id in review["removed_record_ids"]
        )


def test_new_repositories_share_one_loaded_store(store):
    # Each request builds a new repository; reloading the 14 MB store per request
    # doubled the test suite's time. A second load must be the same object.
    assert JsonInstitutionEvidenceRepository().get_store() is store


def test_privacy_derivative_keeps_none_of_the_removed_records(payload):
    # The v0.1.0 original was deleted; the derivation was checked against it when v0.2.0 was approved.
    removed = set(payload["build"]["removed_record_ids"])
    assert len(removed) == 43
    assert not removed & {r["record_id"] for r in payload["records"]}


def test_shipped_data_carries_only_pseudonymous_institution_fields(payload):
    """ADR-079: 다시 빌드해도 실명 · 유형 · 실명 경로가 data 에 돌아오지 않는다."""
    path = re.compile(r"references/samples/[^/]+/([0-9a-f]{12})\.pdf")
    for record in payload["records"]:
        assert re.fullmatch(r"inst_\d{3}", record.get("institution_id", "inst_000")), record[
            "record_id"
        ]
        assert path.fullmatch(record["source_path"])[1] == record["source_sha256"][:12], record[
            "record_id"
        ]
    for source in payload["source_hash_manifest"]:
        assert path.fullmatch(source["path"])[1] == source["sha256"][:12], source["path"]
    for data_file in DEFAULT_EVIDENCE_STORE_PATH.parents[1].rglob("*.json"):
        if data_file.parent.name == "rules":
            continue  # 법정 Rule 의 institution_types 는 법 적용 시설 종류(어린이집 · 유치원 …)다
        text = data_file.read_text(encoding="utf-8")
        assert '"institution_type' not in text, data_file.name


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
def test_loader_accepts_supported_store_versions_and_keeps_the_one_read(
    payload, version, supported
):
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
