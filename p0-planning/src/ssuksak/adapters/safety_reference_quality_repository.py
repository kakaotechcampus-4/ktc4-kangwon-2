"""Strict JSON adapter for the supplemental safety Reference quality review."""

from __future__ import annotations

import json
from pathlib import Path

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.evidence.safety_quality import (
    SAFETY_QUALITY_ID,
    SAFETY_QUALITY_SCHEMA_VERSION,
    MonthScope,
    ReferenceQuality,
    ReferenceQualityEntry,
    SafetyReferenceQuality,
)

DEFAULT_SAFETY_QUALITY_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "evidence" / "safety_reference_quality_v0_1_0.json"
)
_ROOT_FIELDS = {
    "$schema_note", "schema_version", "quality_id", "quality_version", "classification_version",
    "evidence_store", "review", "body_key_rule", "body_key_rule_note", "default_quality", "reason_codes",
    "month_scopes", "month_scope_note", "entries",
}
_ENTRY_FIELDS = {
    "body_key", "example_text", "supplemental_label", "quality", "topic_group", "reason", "note",
    "month_scope", "month_scope_reason",
}


class SafetyReferenceQualityError(ValueError):
    pass


def load_safety_quality_from_dict(payload: object) -> SafetyReferenceQuality:
    if not isinstance(payload, dict) or set(payload) != _ROOT_FIELDS:
        raise SafetyReferenceQualityError("safety reference quality root fields are invalid")
    if payload["schema_version"] != SAFETY_QUALITY_SCHEMA_VERSION or payload["quality_id"] != SAFETY_QUALITY_ID:
        raise SafetyReferenceQualityError("safety reference quality identity is invalid")
    if set(payload["month_scopes"]) != {scope.value for scope in MonthScope}:
        raise SafetyReferenceQualityError("month_scopes must list TARGET_MONTH_ONLY and MONTH_INDEPENDENT")
    if payload["body_key_rule"] != "LEADING_TAG_STRIPPED_ALNUM" or payload["default_quality"] != "EXCLUDED":
        raise SafetyReferenceQualityError("safety reference quality must use exact body keys with an EXCLUDED default")
    review = payload["review"]
    if not isinstance(review, dict) or type(review.get("runtime_active")) is not bool or review["runtime_active"] != (
        review.get("domain_owner_approval") == "HUMAN_APPROVED"
    ):
        raise SafetyReferenceQualityError("runtime_active must be derived from approval")
    if review["runtime_active"] and not str(review.get("approved_by", "")).startswith("reviewer_"):
        raise SafetyReferenceQualityError("approved_by is invalid")
    reasons = set(payload["reason_codes"])
    entries = []
    for index, raw in enumerate(payload["entries"]):
        if not isinstance(raw, dict) or set(raw) != _ENTRY_FIELDS:
            raise SafetyReferenceQualityError(f"entries[{index}] fields are invalid")
        if raw["reason"] is not None and raw["reason"] not in reasons:
            raise SafetyReferenceQualityError(f"entries[{index}] uses an undeclared reason")
        try:
            entries.append(
                ReferenceQualityEntry(
                    raw["body_key"], ReferenceQuality(raw["quality"]), raw["topic_group"], raw["reason"],
                    None if raw["month_scope"] is None else MonthScope(raw["month_scope"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise SafetyReferenceQualityError(f"entries[{index}] is invalid: {exc}") from exc
    try:
        return SafetyReferenceQuality(
            quality_version=payload["quality_version"],
            classification_version=payload["classification_version"],
            evidence_content_sha256=payload["evidence_store"]["content_sha256"],
            entries=tuple(entries),
            runtime_active=review["runtime_active"],
        )
    except (InvalidDomainValueError, KeyError, TypeError) as exc:
        raise SafetyReferenceQualityError(str(exc)) from exc


class JsonSafetyReferenceQualityRepository:
    def __init__(self, path: Path | str = DEFAULT_SAFETY_QUALITY_PATH) -> None:
        self._path = Path(path)
        self._cached: SafetyReferenceQuality | None = None

    def get_quality(self) -> SafetyReferenceQuality:
        if self._cached is None:
            self._cached = load_safety_quality_from_dict(json.loads(self._path.read_text(encoding="utf-8")))
        return self._cached
