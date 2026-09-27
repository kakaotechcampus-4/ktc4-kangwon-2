"""Reference and input gates needed before Yearly Theme selection."""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.theme_reference import ThemeCatalog
from .errors import YearlyRuleError

SUPPORTED_AGES = frozenset({3, 4, 5})

AGE_RULE_ID = "yearly.input.supported_ages"
CATALOG_RESOLUTION_RULE_ID = "catalog_id_and_version_must_resolve_exactly"
CATALOG_APPROVAL_RULE_ID = (
    "only_human_approved_versioned_theme_reference_is_eligible"
)


def validate_age_set(ages: Iterable[int]) -> frozenset[int]:
    """Validate P0 ages without depending on an Application DTO."""

    if isinstance(ages, (str, bytes)):
        raise YearlyRuleError(AGE_RULE_ID, "ages must be an iterable of integers")
    try:
        values = tuple(ages)
    except TypeError as exc:
        raise YearlyRuleError(
            AGE_RULE_ID, "ages must be an iterable of integers"
        ) from exc

    if not values:
        raise YearlyRuleError(AGE_RULE_ID, "at least one age is required")
    if any(type(age) is not int for age in values):
        raise YearlyRuleError(AGE_RULE_ID, "every age must be an integer")
    if len(set(values)) != len(values):
        raise YearlyRuleError(AGE_RULE_ID, "ages must not contain duplicates")

    unsupported = sorted(set(values) - SUPPORTED_AGES)
    if unsupported:
        raise YearlyRuleError(
            AGE_RULE_ID,
            f"unsupported P0 ages: {unsupported}; supported ages are {sorted(SUPPORTED_AGES)}",
        )
    return frozenset(values)


def require_resolved_catalog(
    catalog: ThemeCatalog | None,
    catalog_id: str,
    catalog_version: str,
) -> ThemeCatalog:
    """Require an exact catalog id/version match; never fall back to latest."""

    if catalog is None:
        raise YearlyRuleError(
            CATALOG_RESOLUTION_RULE_ID,
            f"Theme Catalog not found: {catalog_id}/{catalog_version}",
        )
    if catalog.catalog_id != catalog_id or catalog.catalog_version != catalog_version:
        raise YearlyRuleError(
            CATALOG_RESOLUTION_RULE_ID,
            "resolved Theme Catalog does not match the requested id/version",
        )
    return catalog


def require_human_approved_catalog(catalog: ThemeCatalog) -> None:
    """Allow deterministic selection only from human-approved catalog metadata."""

    if not catalog.is_active:
        raise YearlyRuleError(
            CATALOG_APPROVAL_RULE_ID,
            f"Theme Catalog {catalog.catalog_version} is {catalog.activation_status.value}",
        )
