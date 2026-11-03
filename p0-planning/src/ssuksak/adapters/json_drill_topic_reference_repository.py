"""Exact-version JSON adapter for the 소방대피 · 재난대비 drill topic Reference."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ..planning.domain.drill_topic_reference import DrillKind, DrillOrigin, DrillTopic, DrillTopicCatalog
from ..planning.domain.theme_reference import ActivationStatus

DRAFT_DRILL_TOPIC_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "drills" / "emergency_drill_topics_v0_1_0_draft.json"
)


class DrillTopicReferenceError(ValueError):
    pass


def parse_drill_topic_payload(payload: Mapping) -> DrillTopicCatalog:
    review = payload["review"]
    try:
        status = ActivationStatus(review["domain_owner_approval"])
    except ValueError:
        raise DrillTopicReferenceError("domain_owner_approval is not a known status") from None
    # runtime_active is derived, not a separate switch: it must equal the approval.
    if review["runtime_active"] is not (status is ActivationStatus.HUMAN_APPROVED):
        raise DrillTopicReferenceError("runtime_active must be derived from domain_owner_approval")
    curriculum = payload["curriculum"]
    return DrillTopicCatalog(
        catalog_id=payload["catalog_id"],
        catalog_version=payload["catalog_version"],
        activation_status=status,
        curriculum_catalog_id=curriculum["catalog_id"],
        curriculum_catalog_version=curriculum["catalog_version"],
        origins=tuple(DrillOrigin(o["origin_id"], o["title"], o["sha256"], o["pages"]) for o in payload["origins"]),
        topics=tuple(
            DrillTopic(
                topic_id=t["topic_id"],
                kind=DrillKind(t["kind"]),
                label=t["label"],
                situation=t["situation"],
                content_id=t["content_id"],
                applicable_months=tuple(t["applicable_months"]),
                origin_id=t["origin_id"],
            )
            for t in payload["topics"]
        ),
    )


class JsonDrillTopicReferenceRepository:
    def __init__(self, paths: tuple[Path, ...] = (DRAFT_DRILL_TOPIC_PATH,)) -> None:
        # 훈련 칸이 없는 생성은 파일을 읽지 않는다 — 첫 get_catalog 때 읽는다.
        self._paths = paths
        self._cached: tuple[DrillTopicCatalog, ...] | None = None

    def get_catalog(self, catalog_id: str, catalog_version: str) -> DrillTopicCatalog | None:
        if self._cached is None:
            self._cached = tuple(
                parse_drill_topic_payload(json.loads(Path(path).read_text(encoding="utf-8")))
                for path in self._paths
            )
        return next(
            (c for c in self._cached if (c.catalog_id, c.catalog_version) == (catalog_id, catalog_version)),
            None,
        )
