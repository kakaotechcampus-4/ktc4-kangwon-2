"""Strict boundary validation for an external Theme Reference JSON payload."""

from __future__ import annotations

from collections.abc import Mapping

from ..planning.domain.errors import InvalidDomainValueError
from ..planning.domain.theme_reference import (
    ActivationStatus,
    CurriculumLink,
    ThemeCandidate,
    ThemeCatalog,
    ThemeEvidence,
)

__all__ = ["ThemeReferenceSchemaError", "parse_theme_reference_payload"]


class ThemeReferenceSchemaError(ValueError):
    """The external JSON shape cannot be converted into a Theme Catalog."""


def _object(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ThemeReferenceSchemaError(f"{path} must be an object")
    return value


def _field(data: Mapping[str, object], name: str, path: str) -> object:
    if name not in data:
        raise ThemeReferenceSchemaError(f"{path}.{name} is required")
    return data[name]


def _list(
    value: object, path: str, *, non_empty: bool = False
) -> list[object]:
    if not isinstance(value, list):
        raise ThemeReferenceSchemaError(f"{path} must be an array")
    if non_empty and not value:
        raise ThemeReferenceSchemaError(f"{path} must not be empty")
    return value


def _string(value: object, path: str, *, non_blank: bool = True) -> str:
    if not isinstance(value, str):
        raise ThemeReferenceSchemaError(f"{path} must be a string")
    if non_blank and not value.strip():
        raise ThemeReferenceSchemaError(f"{path} must not be blank")
    return value


def _integer(
    value: object, path: str, *, minimum: int, maximum: int | None = None
) -> int:
    if type(value) is not int:
        raise ThemeReferenceSchemaError(f"{path} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f" through {maximum}" if maximum is not None else " or greater"
        raise ThemeReferenceSchemaError(f"{path} must be {minimum}{suffix}")
    return value


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise ThemeReferenceSchemaError(f"{path} must be a boolean")
    return value


def _string_or_none(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path, non_blank=False)


def _months(value: object, path: str) -> tuple[int, ...]:
    return tuple(
        _integer(item, f"{path}[{index}]", minimum=1, maximum=12)
        for index, item in enumerate(_list(value, path, non_empty=True))
    )


def _ages(
    value: object, path: str, *, non_empty: bool = False
) -> tuple[int, ...]:
    return tuple(
        _integer(item, f"{path}[{index}]", minimum=0, maximum=7)
        for index, item in enumerate(_list(value, path, non_empty=non_empty))
    )


def _parse_curriculum_link(value: object, path: str) -> CurriculumLink:
    item = _object(value, path)
    return CurriculumLink(
        source_id=_string(_field(item, "source_id", path), f"{path}.source_id"),
        domain=_string(_field(item, "domain", path), f"{path}.domain"),
        source_page=_integer(
            _field(item, "source_page", path),
            f"{path}.source_page",
            minimum=0,
        ),
        relation=_string(_field(item, "relation", path), f"{path}.relation"),
    )


def _parse_evidence(value: object, path: str) -> ThemeEvidence:
    item = _object(value, path)
    return ThemeEvidence(
        origin_id=_string(_field(item, "origin_id", path), f"{path}.origin_id"),
        page=_integer(_field(item, "page", path), f"{path}.page", minimum=0),
        age_scope=_ages(_field(item, "age_scope", path), f"{path}.age_scope"),
        observed_month=_integer(
            _field(item, "observed_month", path),
            f"{path}.observed_month",
            minimum=1,
            maximum=12,
        ),
        observed_label=_string(
            _field(item, "observed_label", path),
            f"{path}.observed_label",
            non_blank=False,
        ),
    )


def _parse_theme(value: object, index: int) -> ThemeCandidate:
    path = f"themes[{index}]"
    item = _object(value, path)
    age_path = f"{path}.age_conditions"
    age_conditions = _object(
        _field(item, "age_conditions", path),
        age_path,
    )
    links_path = f"{path}.curriculum_links"
    evidence_path = f"{path}.evidence"
    links = _list(_field(item, "curriculum_links", path), links_path)
    evidence = _list(
        _field(item, "evidence", path), evidence_path, non_empty=True
    )

    return ThemeCandidate(
        theme_id=_string(_field(item, "theme_id", path), f"{path}.theme_id"),
        label=_string(_field(item, "label", path), f"{path}.label"),
        applicable_months=_months(
            _field(item, "applicable_months", path),
            f"{path}.applicable_months",
        ),
        supported_ages=_ages(
            _field(age_conditions, "supported_ages", age_path),
            f"{age_path}.supported_ages",
            non_empty=True,
        ),
        allow_mixed_age=_boolean(
            _field(age_conditions, "allow_mixed_age", age_path),
            f"{age_path}.allow_mixed_age",
        ),
        mixed_age_requires_all_supported=_boolean(
            _field(age_conditions, "mixed_age_requires_all_supported", age_path),
            f"{age_path}.mixed_age_requires_all_supported",
        ),
        source_version=_string(
            _field(item, "source_version", path), f"{path}.source_version"
        ),
        origin_id=_string(_field(item, "origin_id", path), f"{path}.origin_id"),
        curriculum_links=tuple(
            _parse_curriculum_link(link, f"{links_path}[{link_index}]")
            for link_index, link in enumerate(links)
        ),
        evidence=tuple(
            _parse_evidence(observation, f"{evidence_path}[{evidence_index}]")
            for evidence_index, observation in enumerate(evidence)
        ),
    )


def _activation_status(review: Mapping[str, object]) -> ActivationStatus:
    raw = _string(
        _field(review, "domain_owner_approval", "review"),
        "review.domain_owner_approval",
    )
    if raw.strip().upper() == ActivationStatus.HUMAN_APPROVED.value:
        return ActivationStatus.HUMAN_APPROVED
    return ActivationStatus.PENDING_HUMAN_REVIEW


def parse_theme_reference_payload(payload: object) -> ThemeCatalog:
    """Validate raw JSON and convert it to the dependency-free domain model."""

    data = _object(payload, "catalog")
    review = _object(_field(data, "review", "catalog"), "review")
    themes = _list(_field(data, "themes", "catalog"), "themes", non_empty=True)
    normative = data.get("normative_status")
    if normative is not None:
        normative = _string_or_none(normative, "catalog.normative_status")

    try:
        return ThemeCatalog(
            catalog_id=_string(
                _field(data, "catalog_id", "catalog"), "catalog.catalog_id"
            ),
            catalog_version=_string(
                _field(data, "catalog_version", "catalog"),
                "catalog.catalog_version",
            ),
            activation_status=_activation_status(review),
            themes=tuple(
                _parse_theme(theme, index) for index, theme in enumerate(themes)
            ),
            normative_status=normative,
        )
    except InvalidDomainValueError as exc:
        raise ThemeReferenceSchemaError(str(exc)) from exc
