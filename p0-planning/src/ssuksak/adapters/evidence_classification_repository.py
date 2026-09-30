"""Strict JSON and in-memory adapters for the Evidence classification port."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.evidence.artifact import EXPECTED_NORMATIVE_STATUS, EXPECTED_STORE_ID
from ..planning.evidence.classification import (
    CLASSIFICATION_ID,
    CLASSIFICATION_SCHEMA_VERSION,
    GROUNDING_SCOPE,
    EvidenceSemanticClassification,
    SemanticClass,
)
from ..planning.evidence.models import SourceSection

DEFAULT_CLASSIFICATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evidence"
    / "monthly_evidence_semantic_classification_v0_1_0.json"
)

_ROOT_FIELDS = {
    "$schema_note", "schema_version", "classification_id", "classification_version",
    "supersedes", "evidence_store", "review", "matching", "key", "default_class",
    "grounding_scope", "entries",
}
_STORE_FIELDS = {"store_id", "schema_version", "ingestion_version", "content_sha256", "normative_status"}
_REVIEW_REQUIRED = {"domain_owner_approval", "approved_by", "approved_at"}
_ENTRY_FIELDS = {"source_section", "source_label", "semantic_class"}


class EvidenceClassificationError(ValueError):
    pass


def _expected_scope() -> dict[str, dict[str, str]]:
    scope = {}
    for semantic_class, (section_key, variant) in GROUNDING_SCOPE.items():
        value = {"section_key": section_key}
        if variant is not None:
            value["semantic_variant"] = variant.value
        scope[semantic_class.value] = value
    return scope


def load_evidence_classification_from_dict(payload: object) -> EvidenceSemanticClassification:
    if not isinstance(payload, dict) or set(payload) != _ROOT_FIELDS:
        raise EvidenceClassificationError("Evidence classification root fields are invalid")
    if payload["schema_version"] != CLASSIFICATION_SCHEMA_VERSION:
        raise EvidenceClassificationError("Evidence classification schema version is invalid")
    if payload["classification_id"] != CLASSIFICATION_ID:
        raise EvidenceClassificationError("Evidence classification id is invalid")
    review = payload["review"]
    if not isinstance(review, dict) or not _REVIEW_REQUIRED <= set(review):
        raise EvidenceClassificationError("Evidence classification review is incomplete")
    if review["domain_owner_approval"] != "HUMAN_APPROVED":
        raise EvidenceClassificationError("Evidence classification is not HUMAN_APPROVED")
    if "runtime_active" in review:
        raise EvidenceClassificationError("Evidence classification must not own runtime activation")
    if not isinstance(review["approved_by"], str) or not review["approved_by"].startswith("reviewer_"):
        raise EvidenceClassificationError("Evidence classification approved_by is invalid")
    try:
        approved_at = datetime.fromisoformat(review["approved_at"])
    except (TypeError, ValueError) as exc:
        raise EvidenceClassificationError("Evidence classification approved_at is invalid") from exc
    if approved_at.tzinfo is None:
        raise EvidenceClassificationError("Evidence classification approved_at must be timezone-aware")
    if payload["matching"] != "EXACT" or payload["key"] != ["source_section", "source_label"]:
        raise EvidenceClassificationError("Evidence classification must use exact (source_section, source_label) keys")
    if payload["default_class"] != SemanticClass.EXCLUDED.value:
        raise EvidenceClassificationError("Evidence classification default_class must be EXCLUDED")
    if payload["grounding_scope"] != _expected_scope():
        raise EvidenceClassificationError("Evidence classification grounding_scope differs from the approved policy")
    store = payload["evidence_store"]
    if not isinstance(store, dict) or set(store) != _STORE_FIELDS:
        raise EvidenceClassificationError("Evidence classification evidence_store is invalid")
    if store["store_id"] != EXPECTED_STORE_ID or store["normative_status"] != EXPECTED_NORMATIVE_STATUS:
        raise EvidenceClassificationError("Evidence classification targets an unexpected Evidence Store")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list):
        raise EvidenceClassificationError("Evidence classification entries must be an array")
    entries = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
            raise EvidenceClassificationError(f"entries[{index}] fields are invalid")
        try:
            entries.append(
                (
                    SourceSection(raw["source_section"]),
                    raw["source_label"],
                    SemanticClass(raw["semantic_class"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise EvidenceClassificationError(f"entries[{index}] is invalid") from exc
    try:
        return EvidenceSemanticClassification(
            classification_version=payload["classification_version"],
            evidence_content_sha256=store["content_sha256"],
            entries=tuple(entries),
        )
    except InvalidDomainValueError as exc:
        raise EvidenceClassificationError(str(exc)) from exc


class JsonEvidenceClassificationRepository:
    def __init__(self, path: Path | str = DEFAULT_CLASSIFICATION_PATH) -> None:
        self._path = Path(path)
        self._cached: EvidenceSemanticClassification | None = None

    def get_classification(self) -> EvidenceSemanticClassification:
        if self._cached is None:
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                raise EvidenceClassificationError(
                    f"Cannot read Evidence classification: {self._path}"
                ) from exc
            self._cached = load_evidence_classification_from_dict(payload)
        return self._cached


class InMemoryEvidenceClassificationRepository:
    def __init__(self, classification: EvidenceSemanticClassification) -> None:
        if not isinstance(classification, EvidenceSemanticClassification):
            raise EvidenceClassificationError("InMemory repository requires an EvidenceSemanticClassification")
        self._classification = classification

    def get_classification(self) -> EvidenceSemanticClassification:
        return self._classification
