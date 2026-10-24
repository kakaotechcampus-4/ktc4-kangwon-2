"""Exact-version JSON adapter for the 누리과정 content Reference."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ..planning.domain.curriculum_reference import CurriculumCatalog, CurriculumContent
from ..planning.domain.theme_reference import ActivationStatus

_DATA = Path(__file__).resolve().parents[3] / "data" / "curriculum"
DRAFT_CURRICULUM_PATH = _DATA / "nuri_curriculum_content_v0_1_0_draft.json"


def parse_curriculum_payload(payload: Mapping) -> CurriculumCatalog:
    approval = str(payload["review"]["domain_owner_approval"]).strip().upper()
    return CurriculumCatalog(
        catalog_id=payload["catalog_id"],
        catalog_version=payload["catalog_version"],
        activation_status=(
            ActivationStatus.HUMAN_APPROVED
            if approval == ActivationStatus.HUMAN_APPROVED.value
            else ActivationStatus.PENDING_HUMAN_REVIEW
        ),
        contents=tuple(
            CurriculumContent(content["content_id"], domain["name"], category["name"], content["text"])
            for domain in payload["domains"]
            for category in domain["categories"]
            for content in category["contents"]
        ),
    )


class JsonCurriculumReferenceRepository:
    def __init__(self, paths: tuple[Path, ...] = (DRAFT_CURRICULUM_PATH,)) -> None:
        self._catalogs = tuple(
            parse_curriculum_payload(json.loads(Path(path).read_text(encoding="utf-8")))
            for path in paths
        )

    def get_catalog(self, catalog_id: str, catalog_version: str) -> CurriculumCatalog | None:
        return next(
            (
                c
                for c in self._catalogs
                if (c.catalog_id, c.catalog_version) == (catalog_id, catalog_version)
            ),
            None,
        )
