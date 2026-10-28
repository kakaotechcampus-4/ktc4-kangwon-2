"""Versioned 소방대피 · 재난대비 drill topic Reference for the play monthly plan.

Each topic is a drill situation taken from an official guide (lineage in ``origins``) and
linked to one 누리과정 content id. ``applicable_months`` is a product candidate condition, not
an official monthly schedule; the catalog says nothing about how often a drill must run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError
from .theme_reference import ActivationStatus


class DrillKind(str, Enum):
    FIRE = "FIRE"
    DISASTER = "DISASTER"


def _non_blank(owner: object, *names: str) -> None:
    for name in names:
        value = getattr(owner, name)
        if not isinstance(value, str) or not value.strip():
            raise InvalidDomainValueError(f"{type(owner).__name__}.{name} must be non-blank")


@dataclass(frozen=True, slots=True)
class DrillOrigin:
    origin_id: str
    title: str
    sha256: str  # upstream file version
    pages: str

    def __post_init__(self) -> None:
        _non_blank(self, "origin_id", "title", "sha256", "pages")
        if re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise InvalidDomainValueError("DrillOrigin.sha256 must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class DrillTopic:
    topic_id: str
    kind: DrillKind
    label: str  # short product name of the situation, e.g. 조리실 화재
    situation: str
    content_id: str
    applicable_months: tuple[int, ...]
    origin_id: str

    def __post_init__(self) -> None:
        _non_blank(self, "topic_id", "label", "situation", "content_id", "origin_id")
        if not isinstance(self.kind, DrillKind):
            raise InvalidDomainValueError("DrillTopic.kind is invalid")
        months = self.applicable_months
        if not months or len(set(months)) != len(months) or any(
            type(m) is not int or not 1 <= m <= 12 for m in months
        ):
            raise InvalidDomainValueError("DrillTopic.applicable_months must be unique calendar months")


@dataclass(frozen=True, slots=True)
class DrillTopicCatalog:
    catalog_id: str
    catalog_version: str
    activation_status: ActivationStatus
    curriculum_catalog_id: str
    curriculum_catalog_version: str
    origins: tuple[DrillOrigin, ...]
    topics: tuple[DrillTopic, ...]

    def __post_init__(self) -> None:
        _non_blank(self, "catalog_id", "catalog_version", "curriculum_catalog_id", "curriculum_catalog_version")
        if not isinstance(self.activation_status, ActivationStatus):
            raise InvalidDomainValueError("DrillTopicCatalog.activation_status is invalid")
        ids = [topic.topic_id for topic in self.topics]
        if not ids or len(ids) != len(set(ids)):
            raise InvalidDomainValueError("DrillTopicCatalog needs unique topic ids")
        origin_ids = [origin.origin_id for origin in self.origins]
        if len(origin_ids) != len(set(origin_ids)):
            raise InvalidDomainValueError("DrillTopicCatalog needs unique origin ids")
        if not {t.origin_id for t in self.topics} <= set(origin_ids):
            raise InvalidDomainValueError("DrillTopic.origin_id must name a catalog origin")

    @property
    def is_active(self) -> bool:
        return self.activation_status is ActivationStatus.HUMAN_APPROVED

    def for_month(self, month: int) -> tuple[DrillTopic, ...]:
        return tuple(topic for topic in self.topics if month in topic.applicable_months)
