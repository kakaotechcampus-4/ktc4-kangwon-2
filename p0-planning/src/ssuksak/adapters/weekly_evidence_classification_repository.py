"""Strict JSON and in-memory adapters for the Weekly Evidence classification port.

Same checks as the Monthly loader, against the Weekly schema, id and grounding scope.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.evidence.artifact import EXPECTED_NORMATIVE_STATUS, EXPECTED_STORE_ID
from ..planning.evidence.models import SourceSection
from ..planning.evidence.weekly_classification import (
    WEEKLY_CLASSIFICATION_ID,
    WEEKLY_CLASSIFICATION_SCHEMA_VERSION,
    WEEKLY_GROUNDING_SCOPE,
    WeeklyEvidenceClassification,
    WeeklySemanticClass,
)

DEFAULT_WEEKLY_CLASSIFICATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evidence"
    / "weekly_evidence_semantic_classification_v0_1_0.json"
)

_ROOT_FIELDS = {
    "$schema_note", "schema_version", "classification_id", "classification_version",
    "supersedes", "evidence_store", "review", "matching", "key", "default_class",
    "grounding_scope", "entries",
}
_STORE_FIELDS = {"store_id", "schema_version", "ingestion_version", "content_sha256", "normative_status"}
_REVIEW_REQUIRED = {"domain_owner_approval", "approved_by", "approved_at"}
_ENTRY_FIELDS = {"source_section", "source_label", "semantic_class"}
_EXPECTED_SCOPE = {cls.value: {"section_key": key} for cls, key in WEEKLY_GROUNDING_SCOPE.items()}


class WeeklyEvidenceClassificationError(ValueError):
    pass


def load_weekly_evidence_classification_from_dict(payload: object) -> WeeklyEvidenceClassification:
    error = WeeklyEvidenceClassificationError
    if not isinstance(payload, dict) or set(payload) != _ROOT_FIELDS:
        raise error("Weekly Evidence classification root fields are invalid")
    if payload["schema_version"] != WEEKLY_CLASSIFICATION_SCHEMA_VERSION:
        raise error("Weekly Evidence classification schema version is invalid")
    if payload["classification_id"] != WEEKLY_CLASSIFICATION_ID:
        raise error("Weekly Evidence classification id is invalid")
    review = payload["review"]
    if not isinstance(review, dict) or not _REVIEW_REQUIRED <= set(review):
        raise error("Weekly Evidence classification review is incomplete")
    if review["domain_owner_approval"] != "HUMAN_APPROVED":
        raise error("Weekly Evidence classification is not HUMAN_APPROVED")
    if "runtime_active" in review:
        raise error("Weekly Evidence classification must not own runtime activation")
    if not isinstance(review["approved_by"], str) or not review["approved_by"].startswith("reviewer_"):
        raise error("Weekly Evidence classification approved_by is invalid")
    try:
        approved_at = datetime.fromisoformat(review["approved_at"])
    except (TypeError, ValueError) as exc:
        raise error("Weekly Evidence classification approved_at is invalid") from exc
    if approved_at.tzinfo is None:
        raise error("Weekly Evidence classification approved_at must be timezone-aware")
    if payload["matching"] != "EXACT" or payload["key"] != ["source_section", "source_label"]:
        raise error("Weekly Evidence classification must use exact (source_section, source_label) keys")
    if payload["default_class"] != WeeklySemanticClass.EXCLUDED.value:
        raise error("Weekly Evidence classification default_class must be EXCLUDED")
    if payload["grounding_scope"] != _EXPECTED_SCOPE:
        raise error("Weekly Evidence classification grounding_scope differs from the approved policy")
    store = payload["evidence_store"]
    if not isinstance(store, dict) or set(store) != _STORE_FIELDS:
        raise error("Weekly Evidence classification evidence_store is invalid")
    if store["store_id"] != EXPECTED_STORE_ID or store["normative_status"] != EXPECTED_NORMATIVE_STATUS:
        raise error("Weekly Evidence classification targets an unexpected Evidence Store")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list):
        raise error("Weekly Evidence classification entries must be an array")
    entries = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
            raise error(f"entries[{index}] fields are invalid")
        try:
            entries.append(
                (
                    SourceSection(raw["source_section"]),
                    raw["source_label"],
                    WeeklySemanticClass(raw["semantic_class"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise error(f"entries[{index}] is invalid") from exc
    try:
        return WeeklyEvidenceClassification(
            classification_version=payload["classification_version"],
            evidence_content_sha256=store["content_sha256"],
            entries=tuple(entries),
        )
    except InvalidDomainValueError as exc:
        raise error(str(exc)) from exc


class JsonWeeklyEvidenceClassificationRepository:
    def __init__(self, path: Path | str = DEFAULT_WEEKLY_CLASSIFICATION_PATH) -> None:
        self._path = Path(path)
        self._cached: WeeklyEvidenceClassification | None = None

    def get_classification(self) -> WeeklyEvidenceClassification:
        if self._cached is None:
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                raise WeeklyEvidenceClassificationError(
                    f"Cannot read Weekly Evidence classification: {self._path}"
                ) from exc
            self._cached = load_weekly_evidence_classification_from_dict(payload)
        return self._cached


class InMemoryWeeklyEvidenceClassificationRepository:
    def __init__(self, classification: WeeklyEvidenceClassification) -> None:
        if not isinstance(classification, WeeklyEvidenceClassification):
            raise WeeklyEvidenceClassificationError(
                "InMemory repository requires a WeeklyEvidenceClassification"
            )
        self._classification = classification

    def get_classification(self) -> WeeklyEvidenceClassification:
        return self._classification
