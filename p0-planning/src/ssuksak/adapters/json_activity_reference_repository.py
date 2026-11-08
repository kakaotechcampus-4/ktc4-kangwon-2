"""Exact-version JSON adapter for Activity Reference catalogs."""

from __future__ import annotations

import functools
from pathlib import Path

from .. import timing
from ..planning.domain.activity_reference import ActivityCatalog
from .activity_reference_schema import parse_activity_reference_payload

_DATA = Path(__file__).resolve().parents[3] / "data" / "activities"
DEFAULT_ACTIVITY_CATALOG_PATH = _DATA / "activity_reference_v0_2_1.json"
APPROVED_ACTIVITY_CATALOG_PATHS = (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    _DATA / "activity_reference_v0_2.json",
)
LEGACY_ACTIVITY_CATALOG_PATH = _DATA / "activity_reference_v0.json"


# Cached per process, not per instance: the compositions build a new repository on
# every request, so a per-instance cache never hit and every Monthly / Weekly request
# re-parsed the catalogs. They are read-only versioned artifacts; a failed parse raises
# and is not cached.
@functools.cache
def _load_catalog(path: Path) -> ActivityCatalog:
    return parse_activity_reference_payload(timing.read_json(path))


class JsonActivityReferenceRepository:
    def __init__(self, paths: tuple[Path, ...] = APPROVED_ACTIVITY_CATALOG_PATHS + (LEGACY_ACTIVITY_CATALOG_PATH,)) -> None:
        self._paths = tuple(Path(path) for path in paths)

    def get_catalog(self, catalog_id: str, catalog_version: str) -> ActivityCatalog | None:
        for path in self._paths:
            catalog = _load_catalog(path)
            if (catalog.catalog_id, catalog.catalog_version) == (catalog_id, catalog_version):
                return catalog
        return None
