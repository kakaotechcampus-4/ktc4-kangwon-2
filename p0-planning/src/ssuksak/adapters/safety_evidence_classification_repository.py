"""Strict JSON adapter for the safety evidence classification (review stage)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.evidence.artifact import EXPECTED_NORMATIVE_STATUS, EXPECTED_STORE_ID
from ..planning.evidence.safety_classification import (
    MULTI_TAG_RULE,
    SAFETY_CLASSIFICATION_ID,
    SAFETY_CLASSIFICATION_SCHEMA_V1,
    SAFETY_CLASSIFICATION_SCHEMA_VERSION,
    SafetyClassificationEntry,
    SafetyEvidenceClassification,
    SafetyReferenceKind,
)

_EVIDENCE = Path(__file__).resolve().parents[3] / "data" / "evidence"
SAFETY_CLASSIFICATION_V0_1_0_PATH = _EVIDENCE / "safety_evidence_classification_v0_1_0.json"
# Runtime default: the latest version. It is used only once HUMAN_APPROVED.
DEFAULT_SAFETY_CLASSIFICATION_PATH = _EVIDENCE / "safety_evidence_classification_v0_2_0.json"
_ROOT_FIELDS = {
    "$schema_note", "schema_version", "classification_id", "classification_version", "supersedes",
    "evidence_store", "legal_rule_version", "review", "matching", "key", "item_tag_rule",
    "item_tag_rule_note", "default_kind", "supplemental_labels", "entries",
}
_STORE_FIELDS = {"store_id", "schema_version", "ingestion_version", "content_sha256", "normative_status"}
_ENTRY_FIELDS = {"source_section", "item_tag", "kind", "legal_category_id", "supplemental_label", "review_reason"}


class SafetyEvidenceClassificationError(ValueError):
    pass


def _review_active(review: object) -> bool:
    if not isinstance(review, dict) or not {"domain_owner_approval", "approved_by", "approved_at", "runtime_active"} <= set(review):
        raise SafetyEvidenceClassificationError("safety classification review is incomplete")
    approved = review["domain_owner_approval"] == "HUMAN_APPROVED"
    if review["runtime_active"] is not approved:
        raise SafetyEvidenceClassificationError("runtime_active must be derived from approval")
    if approved:
        if not isinstance(review["approved_by"], str) or not review["approved_by"].startswith("reviewer_"):
            raise SafetyEvidenceClassificationError("approved_by is invalid")
        try:
            if datetime.fromisoformat(review["approved_at"]).tzinfo is None:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise SafetyEvidenceClassificationError("approved_at must be a timezone-aware time") from exc
    return approved


def load_safety_classification_from_dict(payload: object) -> SafetyEvidenceClassification:
    v1 = isinstance(payload, dict) and payload.get("schema_version") == SAFETY_CLASSIFICATION_SCHEMA_V1
    expected_fields = _ROOT_FIELDS | ({"multi_tag_rule", "multi_tag_rule_note"} if v1 else set())
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise SafetyEvidenceClassificationError("safety classification root fields are invalid")
    if payload["schema_version"] not in (SAFETY_CLASSIFICATION_SCHEMA_VERSION, SAFETY_CLASSIFICATION_SCHEMA_V1) or (
        payload["classification_id"] != SAFETY_CLASSIFICATION_ID
    ):
        raise SafetyEvidenceClassificationError("safety classification identity is invalid")
    if v1 and payload["multi_tag_rule"] != MULTI_TAG_RULE:
        raise SafetyEvidenceClassificationError(f"schema v1 requires multi_tag_rule {MULTI_TAG_RULE}")
    if (
        payload["matching"] != "EXACT"
        or payload["key"] != ["source_section", "item_tag"]
        or payload["item_tag_rule"] != "LEADING_SQUARE_BRACKET"
        or payload["default_kind"] != SafetyReferenceKind.NEEDS_REVIEW.value
    ):
        raise SafetyEvidenceClassificationError("safety classification must use exact item tags with a NEEDS_REVIEW default")
    store = payload["evidence_store"]
    if not isinstance(store, dict) or set(store) != _STORE_FIELDS or store["store_id"] != EXPECTED_STORE_ID or (
        store["normative_status"] != EXPECTED_NORMATIVE_STATUS
    ):
        raise SafetyEvidenceClassificationError("safety classification targets an unexpected Evidence Store")
    active = _review_active(payload["review"])
    labels = payload["supplemental_labels"]
    raw_entries = payload["entries"]
    if not isinstance(labels, list) or not isinstance(raw_entries, list):
        raise SafetyEvidenceClassificationError("supplemental_labels and entries must be arrays")
    entries = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS or raw["source_section"] != "safety_education":
            raise SafetyEvidenceClassificationError(f"entries[{index}] fields are invalid")
        try:
            entries.append(
                SafetyClassificationEntry(
                    raw["item_tag"], SafetyReferenceKind(raw["kind"]), raw["legal_category_id"],
                    raw["supplemental_label"], raw["review_reason"],
                )
            )
        except (TypeError, ValueError) as exc:  # InvalidDomainValueError is a ValueError
            raise SafetyEvidenceClassificationError(f"entries[{index}] is invalid: {exc}") from exc
    try:
        return SafetyEvidenceClassification(
            classification_version=payload["classification_version"],
            evidence_content_sha256=store["content_sha256"],
            legal_rule_version=payload["legal_rule_version"],
            entries=tuple(entries),
            supplemental_labels=frozenset(labels),
            runtime_active=active,
            multi_tag_needs_review=v1,
        )
    except InvalidDomainValueError as exc:
        raise SafetyEvidenceClassificationError(str(exc)) from exc


class JsonSafetyEvidenceClassificationRepository:
    def __init__(self, path: Path | str = DEFAULT_SAFETY_CLASSIFICATION_PATH) -> None:
        self._path = Path(path)
        self._cached: SafetyEvidenceClassification | None = None

    def get_classification(self) -> SafetyEvidenceClassification:
        if self._cached is None:
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                raise SafetyEvidenceClassificationError(f"Cannot read safety classification: {self._path}") from exc
            self._cached = load_safety_classification_from_dict(payload)
        return self._cached
