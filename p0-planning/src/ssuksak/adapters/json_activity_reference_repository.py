"""Exact-version JSON adapter for Activity Reference catalogs."""

from __future__ import annotations

import json
from pathlib import Path

from ..planning.domain.activity_reference import ActivityCatalog
from .activity_reference_schema import parse_activity_reference_payload

_DATA = Path(__file__).resolve().parents[3] / "data" / "activities"
DEFAULT_ACTIVITY_CATALOG_PATH = _DATA / "activity_reference_v0_2_1.json"
APPROVED_ACTIVITY_CATALOG_PATHS = (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    _DATA / "activity_reference_v0_2.json",
)
LEGACY_ACTIVITY_CATALOG_PATH = _DATA / "activity_reference_v0.json"


class JsonActivityReferenceRepository:
    def __init__(self, paths: tuple[Path, ...] = APPROVED_ACTIVITY_CATALOG_PATHS + (LEGACY_ACTIVITY_CATALOG_PATH,)) -> None:
        self._paths = tuple(Path(path) for path in paths)
        self._cache: dict[Path, ActivityCatalog] = {}

    def _load(self, path: Path) -> ActivityCatalog:
        if path not in self._cache:
            self._cache[path] = parse_activity_reference_payload(
                json.loads(path.read_text(encoding="utf-8"))
            )
        return self._cache[path]

    def get_catalog(self, catalog_id: str, catalog_version: str) -> ActivityCatalog | None:
        for path in self._paths:
            catalog = self._load(path)
            if (catalog.catalog_id, catalog.catalog_version) == (catalog_id, catalog_version):
                return catalog
        return None
