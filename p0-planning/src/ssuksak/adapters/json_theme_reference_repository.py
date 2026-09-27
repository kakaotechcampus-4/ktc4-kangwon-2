"""Replaceable JSON adapter for the exact-version Theme Reference port."""

from __future__ import annotations

import json
from pathlib import Path

from ..planning.domain.theme_reference import ThemeCatalog
from .theme_reference_schema import (
    ThemeReferenceSchemaError,
    parse_theme_reference_payload,
)

__all__ = [
    "DEFAULT_CATALOG_PATH",
    "JsonThemeReferenceRepository",
    "ThemeReferenceSchemaError",
    "load_catalog_from_dict",
]

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "themes"
    / "theme_reference_v0.json"
)


def load_catalog_from_dict(payload: object) -> ThemeCatalog:
    return parse_theme_reference_payload(payload)


class JsonThemeReferenceRepository:
    """Read one committed catalog; unknown id/version pairs never fall back."""

    def __init__(self, path: Path | str = DEFAULT_CATALOG_PATH) -> None:
        self._path = Path(path)
        self._catalog: ThemeCatalog | None = None

    def _load(self) -> ThemeCatalog:
        if self._catalog is None:
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ThemeReferenceSchemaError(
                    f"Theme Reference is not valid JSON: {exc}"
                ) from exc
            self._catalog = parse_theme_reference_payload(payload)
        return self._catalog

    def get_catalog(
        self, catalog_id: str, catalog_version: str
    ) -> ThemeCatalog | None:
        catalog = self._load()
        if (
            catalog.catalog_id != catalog_id
            or catalog.catalog_version != catalog_version
        ):
            return None
        return catalog
