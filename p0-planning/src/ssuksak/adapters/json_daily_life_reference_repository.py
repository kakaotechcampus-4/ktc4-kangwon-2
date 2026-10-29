"""Exact-version JSON adapter for the 기본생활습관 · 건강 · 영양 daily-life Reference.

``origins`` and each entry's ``origin_refs`` are review lineage: checked here, not carried by
the domain catalog. Reading an unapproved file is allowed; the generation Gate refuses it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from ..planning.domain.daily_life_reference import DailyLifeCatalog, DailyLifeEntry, DailyLifeKind
from ..planning.domain.theme_reference import ActivationStatus

DAILY_LIFE_PATH = Path(__file__).resolve().parents[3] / "data" / "daily-life" / "daily_life_reference_v0_1_0_draft.json"

_SHA256 = re.compile(r"[0-9a-f]{64}")


class DailyLifeReferenceError(ValueError):
    pass


def _origin_ids(origins: list) -> set[str]:
    ids = [o["origin_id"] for o in origins]
    if not ids or len(ids) != len(set(ids)):
        raise DailyLifeReferenceError("origins need unique origin ids")
    if any(not isinstance(o["sha256"], str) or not _SHA256.fullmatch(o["sha256"]) for o in origins):
        raise DailyLifeReferenceError("each origin needs a sha256 digest")
    return set(ids)


def parse_daily_life_payload(payload: Mapping) -> DailyLifeCatalog:
    try:
        review = payload["review"]
        try:
            status = ActivationStatus(review["domain_owner_approval"])
        except ValueError:
            raise DailyLifeReferenceError("domain_owner_approval is not a known status") from None
        # runtime_active is derived, not a separate switch: it must be the bool the approval gives.
        if review["runtime_active"] is not (status is ActivationStatus.HUMAN_APPROVED):
            raise DailyLifeReferenceError("runtime_active must be derived from domain_owner_approval")
        origin_ids = _origin_ids(payload["origins"])
        entries = []
        for e in payload["entries"]:
            refs = e["origin_refs"]
            if not refs or any(r["origin_id"] not in origin_ids or not r["pages"] for r in refs):
                raise DailyLifeReferenceError(f"{e['entry_id']} needs origin_refs naming catalog origins")
            try:
                kind = DailyLifeKind(e["kind"])
            except ValueError:
                raise DailyLifeReferenceError(f"{e['entry_id']} has an unknown kind") from None
            entries.append(DailyLifeEntry(e["entry_id"], kind, e["label"], e["text"], e["content_id"]))
        curriculum = payload["curriculum"]
        return DailyLifeCatalog(
            catalog_id=payload["catalog_id"],
            catalog_version=payload["catalog_version"],
            activation_status=status,
            curriculum_catalog_id=curriculum["catalog_id"],
            curriculum_catalog_version=curriculum["catalog_version"],
            entries=tuple(entries),
        )
    except (KeyError, TypeError) as error:
        raise DailyLifeReferenceError(f"malformed daily-life payload: {error!r}") from None


class JsonDailyLifeReferenceRepository:
    def __init__(self, paths: tuple[Path, ...] = (DAILY_LIFE_PATH,)) -> None:
        catalogs = tuple(parse_daily_life_payload(json.loads(Path(path).read_text(encoding="utf-8"))) for path in paths)
        keys = [(c.catalog_id, c.catalog_version) for c in catalogs]
        if len(keys) != len(set(keys)):  # never let file order pick the winner
            raise DailyLifeReferenceError("two files carry the same catalog id and version")
        self._catalogs = catalogs

    def get_catalog(self, catalog_id: str, catalog_version: str) -> DailyLifeCatalog | None:
        return next(
            (c for c in self._catalogs if (c.catalog_id, c.catalog_version) == (catalog_id, catalog_version)),
            None,
        )
