"""Evidence Store Loader 검증 (L2).

Artifact corruption / schema mismatch를 **조용히 무시하지 않는다**
(CLAUDE.md §14).
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib

import pytest

from ssuksak.ingestion.pipeline import (
    EVIDENCE_STORE_SCHEMA_VERSION,
    INGESTION_VERSION,
)
from ssuksak.planning.retrieval import (
    DEFAULT_EVIDENCE_STORE_PATH,
    EvidenceStoreError,
    JsonInstitutionEvidenceRepository,
    load_evidence_store_from_dict,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
L1_CONTENT_SHA = (
    "52b409557d3503422aa0109664298976bd7f831ed18304b818aaad936916e5ea"
)


def _record(record_id: str = "ev_abc_p01_r00100_c01_i01", **over) -> dict:
    base = {
        "record_id": record_id,
        "source_type": "INSTITUTION_SAMPLE",
        "source_path": "references/samples/monthly/x.pdf",
        "source_sha256": "a" * 64,
        "page": 1,
        "age_scope": [4],
        "age_evidence_type": "SINGLE_AGE_PAGE",
        "source_section": "outdoor_play",
        "source_label": "바깥놀이",
        "activity_text": "모래놀이",
        "setting": "OUTDOOR",
        "machine_readability": "TEXT_LAYER",
        "extraction_quality": "VALID",
        "extraction_method": "table_line_geometry_v1",
        "month": 7,
        "institution_id": "테스트어린이집",
    }
    base.update(over)
    return base


def _payload(records: list[dict] | None = None, **over) -> dict:
    recs = records if records is not None else [_record()]
    p = {
        "schema_version": EVIDENCE_STORE_SCHEMA_VERSION,
        "ingestion_version": INGESTION_VERSION,
        "store_id": "ssuksak.institution-evidence",
        "normative_status": "CORPUS_OBSERVATION_NON_NORMATIVE",
        "source_count": 1,
        "record_count": len(recs),
        "records": recs,
    }
    p.update(over)
    return p


def _with_build(payload: dict) -> dict:
    content = {k: v for k, v in payload.items() if k != "build"}
    blob = json.dumps(content, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    out = dict(payload)
    out["build"] = {"generated_at": "2026-09-13T00:00:00+09:00",
                    "content_sha256": sha}
    return out


# ============================================== valid


def test_valid_artifact_loads():
    store = load_evidence_store_from_dict(_payload())
    assert len(store) == 1
    assert store.ingestion_version == INGESTION_VERSION
    assert store.schema_version == EVIDENCE_STORE_SCHEMA_VERSION


def test_content_sha_is_computed_and_matches_recorded_build_value():
    payload = _with_build(_payload())
    store = load_evidence_store_from_dict(payload)
    assert store.content_sha256 == payload["build"]["content_sha256"]


def test_month_index_returns_only_that_month():
    store = load_evidence_store_from_dict(
        _payload([_record("ev_a_p01_r00100_c01_i01", month=7),
                  _record("ev_b_p01_r00200_c01_i01", month=8)])
    )
    assert [r.record_id for r in store.by_month(7)] == ["ev_a_p01_r00100_c01_i01"]
    assert store.by_month(12) == ()


# ============================================== 실패


def test_sha_mismatch_is_rejected():
    payload = _with_build(_payload())
    payload["build"]["content_sha256"] = "f" * 64
    with pytest.raises(EvidenceStoreError, match="content_sha256"):
        load_evidence_store_from_dict(payload)


def test_expected_sha_pin_mismatch_is_rejected():
    with pytest.raises(EvidenceStoreError, match="기대 pin"):
        load_evidence_store_from_dict(_payload(), expected_sha256="0" * 64)


def test_schema_version_mismatch_is_rejected():
    with pytest.raises(EvidenceStoreError, match="schema_version"):
        load_evidence_store_from_dict(_payload(schema_version="something-else"))


def test_ingestion_version_mismatch_is_rejected():
    with pytest.raises(EvidenceStoreError, match="ingestion_version"):
        load_evidence_store_from_dict(_payload(ingestion_version="v9.9.9"))


def test_store_id_mismatch_is_rejected():
    with pytest.raises(EvidenceStoreError, match="store_id"):
        load_evidence_store_from_dict(_payload(store_id="other.store"))


def test_normative_status_must_stay_a_corpus_observation():
    """승인 Reference로 둔갑한 Artifact를 로드하지 않는다."""
    with pytest.raises(EvidenceStoreError, match="normative_status"):
        load_evidence_store_from_dict(_payload(normative_status="HUMAN_APPROVED"))


def test_record_count_mismatch_is_rejected():
    with pytest.raises(EvidenceStoreError, match="record_count"):
        load_evidence_store_from_dict(_payload(record_count=99))


def test_missing_required_field_is_rejected():
    payload = _payload()
    del payload["records"]
    with pytest.raises(EvidenceStoreError, match="필수 필드"):
        load_evidence_store_from_dict(payload)


def test_record_schema_violation_is_rejected():
    bad = _record(setting="MAYBE_OUTDOOR")
    with pytest.raises(EvidenceStoreError, match="schema"):
        load_evidence_store_from_dict(_payload([bad]))


def test_duplicate_record_id_is_rejected():
    with pytest.raises(EvidenceStoreError, match="중복"):
        load_evidence_store_from_dict(_payload([_record(), copy.deepcopy(_record())]))


def test_non_object_payload_is_rejected():
    with pytest.raises(EvidenceStoreError):
        load_evidence_store_from_dict(["not", "an", "object"])


def test_missing_file_is_reported_clearly(tmp_path):
    repo = JsonInstitutionEvidenceRepository(tmp_path / "nope.json")
    with pytest.raises(EvidenceStoreError, match="파일이 없다"):
        repo.get_store()


def test_invalid_json_is_reported_clearly(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(EvidenceStoreError, match="JSON"):
        JsonInstitutionEvidenceRepository(p).get_store()


# ============================================== 실제 Artifact


@pytest.mark.skipif(
    not DEFAULT_EVIDENCE_STORE_PATH.exists(), reason="Evidence Store 미빌드"
)
def test_production_artifact_loads_and_is_pinned_to_l1_output():
    store = JsonInstitutionEvidenceRepository().get_store()
    assert store.content_sha256 == L1_CONTENT_SHA
    assert store.ingestion_version == INGESTION_VERSION
    assert len(store) == 12_367


@pytest.mark.skipif(
    not DEFAULT_EVIDENCE_STORE_PATH.exists(), reason="Evidence Store 미빌드"
)
def test_repository_can_pin_the_expected_sha():
    repo = JsonInstitutionEvidenceRepository(expected_sha256=L1_CONTENT_SHA)
    assert repo.get_store().content_sha256 == L1_CONTENT_SHA
