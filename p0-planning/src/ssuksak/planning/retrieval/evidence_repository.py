"""Evidence Store Loader (L2).

**Runtime은 PDF를 읽지 않는다.** L1이 만든 Artifact 하나만 읽는다. 따라서
`pymupdf` · `SourceDocumentReader` · 셀 추출은 L2 Runtime dependency가 아니다.

Artifact가 깨졌거나 Contract와 다르면 **조용히 넘어가지 않고 실패한다**
(CLAUDE.md §14: Validation 실패를 성공으로 저장하거나 조용히 통과시키지 않는다).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from ...ingestion.models import EvidenceRecord
from ...ingestion.pipeline import (
    EVIDENCE_STORE_SCHEMA_VERSION,
    INGESTION_VERSION,
)

__all__ = [
    "DEFAULT_EVIDENCE_STORE_PATH",
    "EXPECTED_NORMATIVE_STATUS",
    "EXPECTED_STORE_ID",
    "EvidenceStoreError",
    "InMemoryInstitutionEvidenceRepository",
    "InstitutionEvidenceStore",
    "JsonInstitutionEvidenceRepository",
    "load_evidence_store_from_dict",
]

DEFAULT_EVIDENCE_STORE_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "evidence"
    / "institution_evidence_v0_1_0.json"
)

EXPECTED_STORE_ID = "ssuksak.institution-evidence"
EXPECTED_NORMATIVE_STATUS = "CORPUS_OBSERVATION_NON_NORMATIVE"
"""Evidence Store는 Corpus 관찰값이다. 승인 Reference가 아니다.

`HUMAN_APPROVED`로 바뀌어 있으면 누군가 Activity Reference와 혼동한 것이므로
로드를 거부한다.
"""


class EvidenceStoreError(Exception):
    """Evidence Store Artifact가 Contract를 만족하지 않는다."""


class InstitutionEvidenceStore:
    """검증을 마친 Evidence Record 모음. 읽기 전용이다."""

    __slots__ = ("_records", "_sha256", "_version", "_schema_version", "_by_month")

    def __init__(
        self,
        records: list[EvidenceRecord],
        *,
        ingestion_version: str,
        schema_version: str,
        content_sha256: str,
    ) -> None:
        self._records = tuple(records)
        self._version = ingestion_version
        self._schema_version = schema_version
        self._sha256 = content_sha256
        by_month: dict[int | None, list[EvidenceRecord]] = {}
        for r in self._records:
            by_month.setdefault(r.month, []).append(r)
        self._by_month = {k: tuple(v) for k, v in by_month.items()}

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return self._records

    @property
    def ingestion_version(self) -> str:
        return self._version

    @property
    def schema_version(self) -> str:
        return self._schema_version

    @property
    def content_sha256(self) -> str:
        return self._sha256

    def by_month(self, month: int) -> tuple[EvidenceRecord, ...]:
        """월 index. 12,367건 전수 순회를 피하기 위한 것뿐이며 필터는 아니다."""
        return self._by_month.get(month, ())

    def __len__(self) -> int:
        return len(self._records)


def _content_sha256(payload: dict) -> str:
    content = {k: v for k, v in payload.items() if k != "build"}
    blob = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_evidence_store_from_dict(
    payload: object, *, expected_sha256: str | None = None
) -> InstitutionEvidenceStore:
    """Artifact를 strict 검증하고 Store로 만든다.

    Args:
        expected_sha256: 주면 Artifact의 content SHA가 이 값과 같은지 확인한다.
            Pin을 강제할 때 쓴다.

    Raises:
        EvidenceStoreError: 필수 필드 누락 · 식별자 불일치 · SHA 불일치 ·
            record 수 불일치 · record schema 위반.
    """
    if not isinstance(payload, dict):
        raise EvidenceStoreError(f"Evidence Store는 object여야 한다: {type(payload)}")

    for key in ("store_id", "schema_version", "ingestion_version",
                "normative_status", "record_count", "records"):
        if key not in payload:
            raise EvidenceStoreError(f"필수 필드가 없다: {key}")

    if payload["store_id"] != EXPECTED_STORE_ID:
        raise EvidenceStoreError(
            f"store_id가 다르다: {payload['store_id']!r} "
            f"(기대 {EXPECTED_STORE_ID!r})"
        )
    if payload["schema_version"] != EVIDENCE_STORE_SCHEMA_VERSION:
        raise EvidenceStoreError(
            f"schema_version이 다르다: {payload['schema_version']!r} "
            f"(기대 {EVIDENCE_STORE_SCHEMA_VERSION!r})"
        )
    if payload["ingestion_version"] != INGESTION_VERSION:
        raise EvidenceStoreError(
            f"ingestion_version이 다르다: {payload['ingestion_version']!r} "
            f"(기대 {INGESTION_VERSION!r})"
        )
    if payload["normative_status"] != EXPECTED_NORMATIVE_STATUS:
        raise EvidenceStoreError(
            f"normative_status가 다르다: {payload['normative_status']!r}. "
            "Evidence Store는 Corpus 관찰값이며 승인 Reference가 아니다"
        )

    raw_records = payload["records"]
    if not isinstance(raw_records, list):
        raise EvidenceStoreError("records는 list여야 한다")
    if payload["record_count"] != len(raw_records):
        raise EvidenceStoreError(
            f"record_count가 실제 개수와 다르다: "
            f"{payload['record_count']} vs {len(raw_records)}"
        )

    actual_sha = _content_sha256(payload)
    recorded = (payload.get("build") or {}).get("content_sha256")
    if recorded is not None and recorded != actual_sha:
        raise EvidenceStoreError(
            f"content_sha256이 기록값과 다르다. Artifact가 손상됐다: "
            f"{actual_sha} vs {recorded}"
        )
    if expected_sha256 is not None and actual_sha != expected_sha256:
        raise EvidenceStoreError(
            f"content_sha256이 기대 pin과 다르다: {actual_sha} vs {expected_sha256}"
        )

    records: list[EvidenceRecord] = []
    for i, raw in enumerate(raw_records):
        try:
            records.append(EvidenceRecord.model_validate(raw))
        except ValidationError as exc:
            raise EvidenceStoreError(
                f"record[{i}]가 schema를 위반했다: {exc}"
            ) from exc

    seen: set[str] = set()
    for r in records:
        if r.record_id in seen:
            raise EvidenceStoreError(f"record_id가 중복이다: {r.record_id}")
        seen.add(r.record_id)

    return InstitutionEvidenceStore(
        records,
        ingestion_version=payload["ingestion_version"],
        schema_version=payload["schema_version"],
        content_sha256=actual_sha,
    )


class JsonInstitutionEvidenceRepository:
    """JSON Artifact 하나를 읽는 Repository. 로드 결과를 캐시한다."""

    def __init__(
        self,
        path: Path | str = DEFAULT_EVIDENCE_STORE_PATH,
        *,
        expected_sha256: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._expected = expected_sha256
        self._store: InstitutionEvidenceStore | None = None

    def get_store(self) -> InstitutionEvidenceStore:
        if self._store is None:
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise EvidenceStoreError(
                    f"Evidence Store 파일이 없다: {self._path}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise EvidenceStoreError(
                    f"Evidence Store가 올바른 JSON이 아니다: {self._path}"
                ) from exc
            self._store = load_evidence_store_from_dict(
                payload, expected_sha256=self._expected
            )
        return self._store


class InMemoryInstitutionEvidenceRepository:
    """테스트에서 Record를 직접 구성하기 위한 Repository."""

    def __init__(self, records: list[EvidenceRecord] | None = None) -> None:
        self._store = InstitutionEvidenceStore(
            list(records or []),
            ingestion_version=INGESTION_VERSION,
            schema_version=EVIDENCE_STORE_SCHEMA_VERSION,
            content_sha256="0" * 64,
        )

    def get_store(self) -> InstitutionEvidenceStore:
        return self._store
