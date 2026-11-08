"""Validate Evidence Store bytes, content hash, records, and optional source manifest.

Manifest paths are pseudonymized (`references/samples/<kind>/<sha12>.pdf`, ADR-074), so local
sources are matched by SHA-256, not by file name."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..adapters.institution_evidence_repository import (
    DEFAULT_EVIDENCE_STORE_PATH,
    evidence_content_sha256,
    load_evidence_store_from_dict,
)


@dataclass(frozen=True, slots=True)
class EvidenceStoreVerification:
    path: str
    file_sha256: str
    content_sha256: str
    records: int
    sources: int
    sources_checked: bool
    missing_sources: int

    @property
    def valid(self) -> bool:
        return self.missing_sources == 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_evidence_store(
    path: Path = DEFAULT_EVIDENCE_STORE_PATH,
    *,
    source_root: Path | None = None,
) -> EvidenceStoreVerification:
    payload = json.loads(path.read_text(encoding="utf-8"))
    store = load_evidence_store_from_dict(payload)
    missing = 0
    if source_root is not None:
        local = {_sha256(source) for source in source_root.rglob("*") if source.is_file()}
        missing = sum(item["sha256"] not in local for item in payload["source_hash_manifest"])
    return EvidenceStoreVerification(
        path=str(path),
        file_sha256=_sha256(path),
        content_sha256=evidence_content_sha256(payload),
        records=len(store),
        sources=payload["source_count"],
        sources_checked=source_root is not None,
        missing_sources=missing,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_EVIDENCE_STORE_PATH)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    report = verify_evidence_store(args.path, source_root=args.source_root)
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
