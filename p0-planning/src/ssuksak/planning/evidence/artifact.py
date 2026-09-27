"""Provider-neutral Evidence Store artifact identity and canonical content hash."""

from __future__ import annotations

import hashlib
import json

EVIDENCE_STORE_SCHEMA_VERSION = "institution-evidence.schema.v0"
INGESTION_VERSION = "institution-evidence-ingestion-v0.1.0"
EXPECTED_STORE_ID = "ssuksak.institution-evidence"
EXPECTED_NORMATIVE_STATUS = "CORPUS_OBSERVATION_NON_NORMATIVE"


def evidence_content_sha256(payload: dict[str, object]) -> str:
    content = {key: value for key, value in payload.items() if key != "build"}
    blob = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
