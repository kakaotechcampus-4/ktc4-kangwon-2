"""Exact-version JSON adapter for the 누리과정 content Reference."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ..planning.domain.curriculum_reference import CurriculumCatalog, CurriculumContent
from ..planning.domain.theme_reference import ActivationStatus

_DATA = Path(__file__).resolve().parents[3] / "data" / "curriculum"
DRAFT_CURRICULUM_PATH = _DATA / "nuri_curriculum_content_v0_1_0_draft.json"


class CurriculumReferenceError(ValueError):
    pass


def parse_curriculum_payload(payload: Mapping) -> CurriculumCatalog:
    review = payload["review"]
    approval, runtime_active = review["domain_owner_approval"], review["runtime_active"]
    try:
        status = ActivationStatus(approval)
    except ValueError:
        raise CurriculumReferenceError("domain_owner_approval is not a known status") from None
    # runtime_active is derived, not a separate switch: it must equal the approval.
    if not isinstance(runtime_active, bool) or runtime_active is not (
        status is ActivationStatus.HUMAN_APPROVED
    ):
        raise CurriculumReferenceError("runtime_active must be derived from domain_owner_approval")
    return CurriculumCatalog(
        catalog_id=payload["catalog_id"],
        catalog_version=payload["catalog_version"],
        activation_status=status,
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
