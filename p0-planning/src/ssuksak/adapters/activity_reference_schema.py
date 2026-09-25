"""Boundary validation for Activity Reference JSON payloads."""

from __future__ import annotations

from ..planning.domain.activity_reference import (
    ActivityCandidate,
    ActivityCatalog,
    ActivityCurriculumLink,
    ActivityDisplayQuality,
    ActivityEvidence,
    ActivitySetting,
    ActivityThemeLink,
    DisplayQualityReviewStatus,
)
from ..planning.domain.errors import InvalidDomainValueError
from ..planning.domain.theme_reference import ActivationStatus


class ActivityReferenceSchemaError(ValueError):
    pass


def _mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ActivityReferenceSchemaError(f"{path} must be an object")
    return value


def _list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ActivityReferenceSchemaError(f"{path} must be an array")
    return value


def _required(data: dict[str, object], name: str, path: str) -> object:
    if name not in data:
        raise ActivityReferenceSchemaError(f"{path}.{name} is required")
    return data[name]


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActivityReferenceSchemaError(f"{path} must be non-blank")
    return value


def _texts(value: object, path: str) -> tuple[str, ...]:
    return tuple(_text(item, f"{path}[]") for item in _list(value, path))


def _ints(value: object, path: str) -> tuple[int, ...]:
    result = tuple(_list(value, path))
    if any(type(item) is not int for item in result):
        raise ActivityReferenceSchemaError(f"{path} must contain integers")
    return result


def _optional_text(data: dict[str, object], name: str, path: str) -> str | None:
    value = data.get(name)
    return None if value is None else _text(value, f"{path}.{name}")


def _parse_evidence(raw: object, path: str) -> ActivityEvidence:
    item = _mapping(raw, path)
    return ActivityEvidence(
        origin_id=_text(_required(item, "origin_id", path), f"{path}.origin_id"),
        page=_required(item, "page", path),
        age_scope=_ints(_required(item, "age_scope", path), f"{path}.age_scope"),
        observed_month=_required(item, "observed_month", path),
        observed_label=_text(_required(item, "observed_label", path), f"{path}.observed_label"),
        observed_section=_text(_required(item, "observed_section", path), f"{path}.observed_section"),
        observed_source_label=_text(_required(item, "observed_source_label", path), f"{path}.observed_source_label"),
        matched_via=_optional_text(item, "matched_via", path),
        match_note=_optional_text(item, "match_note", path),
    )


def _parse_activity(raw: object, path: str) -> ActivityCandidate:
    item = _mapping(raw, path)
    try:
        theme_links = tuple(
            ActivityThemeLink(
                theme_id=_text(_required(link, "theme_id", lp), f"{lp}.theme_id"),
                relation=_text(_required(link, "relation", lp), f"{lp}.relation"),
                theme_catalog_version=_text(_required(link, "theme_catalog_version", lp), f"{lp}.theme_catalog_version"),
            )
            for index, value in enumerate(_list(_required(item, "theme_links", path), f"{path}.theme_links"))
            for lp, link in [(f"{path}.theme_links[{index}]", _mapping(value, f"{path}.theme_links[{index}]"))]
        )
        curriculum_links = tuple(
            ActivityCurriculumLink(
                source_id=_text(_required(link, "source_id", lp), f"{lp}.source_id"),
                domain=_text(_required(link, "domain", lp), f"{lp}.domain"),
                source_page=_required(link, "source_page", lp),
                relation=_text(_required(link, "relation", lp), f"{lp}.relation"),
            )
            for index, value in enumerate(_list(_required(item, "curriculum_links", path), f"{path}.curriculum_links"))
            for lp, link in [(f"{path}.curriculum_links[{index}]", _mapping(value, f"{path}.curriculum_links[{index}]"))]
        )
        evidence = tuple(
            _parse_evidence(value, f"{path}.evidence[{index}]")
            for index, value in enumerate(_list(_required(item, "evidence", path), f"{path}.evidence"))
        )
        quality = item.get("display_quality")
        quality_status = item.get("display_quality_review_status")
        return ActivityCandidate(
            activity_id=_text(_required(item, "activity_id", path), f"{path}.activity_id"),
            label=_text(_required(item, "label", path), f"{path}.label"),
            supported_ages=_ints(_required(item, "supported_ages", path), f"{path}.supported_ages"),
            allow_mixed_age=_required(item, "allow_mixed_age", path),
            mixed_age_requires_all_supported=_required(item, "mixed_age_requires_all_supported", path),
            applicable_months=_ints(_required(item, "applicable_months", path), f"{path}.applicable_months"),
            placement_slots=_texts(_required(item, "placement_slots", path), f"{path}.placement_slots"),
            setting=ActivitySetting(_text(_required(item, "setting", path), f"{path}.setting")),
            source_version=_text(_required(item, "source_version", path), f"{path}.source_version"),
            origin_id=_optional_text(item, "origin_id", path),
            label_derivation_type=_optional_text(item, "label_derivation_type", path),
            label_derivation=_optional_text(item, "label_derivation", path),
            aliases=_texts(item.get("aliases", []), f"{path}.aliases"),
            theme_links=theme_links,
            curriculum_links=curriculum_links,
            evidence=evidence,
            display_quality=None if quality is None else ActivityDisplayQuality(quality),
            display_quality_review_status=(None if quality_status is None else DisplayQualityReviewStatus(quality_status)),
        )
    except (InvalidDomainValueError, ValueError, TypeError) as exc:
        raise ActivityReferenceSchemaError(f"{path} violates the Activity contract: {exc}") from exc


def parse_activity_reference_payload(payload: object) -> ActivityCatalog:
    root = _mapping(payload, "activity_reference")
    if root.get("schema_version") != "activity-reference.schema.v0":
        raise ActivityReferenceSchemaError("unsupported activity schema_version")
    review = _mapping(_required(root, "review", "activity_reference"), "activity_reference.review")
    approval = _text(_required(review, "domain_owner_approval", "activity_reference.review"), "activity_reference.review.domain_owner_approval")
    try:
        status = ActivationStatus(approval)
        activities = tuple(
            _parse_activity(value, f"activity_reference.activities[{index}]")
            for index, value in enumerate(_list(_required(root, "activities", "activity_reference"), "activity_reference.activities"))
        )
        coverage = _mapping(_required(root, "coverage", "activity_reference"), "activity_reference.coverage")
        return ActivityCatalog(
            catalog_id=_text(_required(root, "catalog_id", "activity_reference"), "activity_reference.catalog_id"),
            catalog_version=_text(_required(root, "catalog_version", "activity_reference"), "activity_reference.catalog_version"),
            activation_status=status,
            activities=activities,
            normative_status=_optional_text(root, "normative_status", "activity_reference"),
            month_coverage=_ints(_required(coverage, "month_coverage", "activity_reference.coverage"), "activity_reference.coverage.month_coverage"),
        )
    except (InvalidDomainValueError, ValueError, TypeError) as exc:
        raise ActivityReferenceSchemaError(f"Activity Reference violates the domain contract: {exc}") from exc
