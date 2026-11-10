"""The month's 소방대피 · 재난대비 drill topics, shared by v1 and v2.

The Rule fixes the topics before any LLM call; the LLM only words one sentence per topic.
A failure carries an internal ``code`` the caller maps to its own error.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.drill_topic_reference import DrillTopic, DrillTopicCatalog
from ..domain.errors import DomainError

DRILL_CANDIDATE_COUNT = 5  # M2-D15: candidates, not a drill frequency


class DrillTopicReferenceRepository(Protocol):
    def get_catalog(self, catalog_id: str, catalog_version: str) -> DrillTopicCatalog | None: ...


class DrillTopicError(DomainError):
    """Internal gate failure; ``code`` is not a public API error code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def select_drill_topics(
    drills: DrillTopicCatalog | None, catalog: CurriculumCatalog, month: int, count: int = DRILL_CANDIDATE_COUNT
) -> tuple[DrillTopic, ...]:
    if drills is None:
        raise DrillTopicError("DRILL_REFERENCE_NOT_FOUND")
    if not drills.is_active:
        raise DrillTopicError("DRILL_REFERENCE_NOT_ACTIVE")
    if (drills.curriculum_catalog_id, drills.curriculum_catalog_version) != (
        catalog.catalog_id,
        catalog.catalog_version,
    ):
        raise DrillTopicError("DRILL_CURRICULUM_MISMATCH")
    if any(catalog.get(topic.content_id) is None for topic in drills.topics):
        raise DrillTopicError("DRILL_UNKNOWN_CONTENT_ID")
    # Month-limited topics (e.g. 폭설 in winter) first, then the year-round topics in catalog order
    # starting one step further each school month (March = 0), so neighbouring months differ
    # (Human Decision 2026-11-11 하민, 「대피 후보 달마다 돌리기」).
    available = drills.for_month(month)
    if len(available) < count:
        raise DrillTopicError("DRILL_TOPICS_INSUFFICIENT")
    seasonal = [t for t in available if len(t.applicable_months) < 12]
    year_round = [t for t in available if len(t.applicable_months) == 12]
    start = (month - 3) % 12 % len(year_round) if year_round else 0
    return tuple((seasonal + year_round[start:] + year_round[:start])[:count])
