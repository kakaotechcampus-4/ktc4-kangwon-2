"""Human-approved exact-label classification of Institution Evidence for Weekly Sections.

Kept apart from the Monthly classification (ADR-033): the same exact
``(source_section, source_label)`` rule, but Weekly classes that ground the
indoor_play, group_activity and indoor_alternative Sections. Unlisted labels are
EXCLUDED. It never changes the Evidence corpus itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ..domain.errors import InvalidDomainValueError
from .models import EvidenceRecord, SourceSection

WEEKLY_CLASSIFICATION_SCHEMA_VERSION = "weekly-evidence-semantic-classification.schema.v0"
WEEKLY_CLASSIFICATION_ID = "ssuksak.weekly-evidence-semantic-classification"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class WeeklySemanticClass(str, Enum):
    INDOOR_PLAY = "INDOOR_PLAY"
    GROUP_ACTIVITY = "GROUP_ACTIVITY"
    INDOOR_ALTERNATIVE = "INDOOR_ALTERNATIVE"
    EXCLUDED = "EXCLUDED"


# Approved grounding policy: each class grounds exactly one Weekly Section.
WEEKLY_GROUNDING_SCOPE: dict[WeeklySemanticClass, str] = {
    WeeklySemanticClass.INDOOR_PLAY: "indoor_play",
    WeeklySemanticClass.GROUP_ACTIVITY: "group_activity",
    WeeklySemanticClass.INDOOR_ALTERNATIVE: "indoor_alternative",
}


@dataclass(frozen=True, slots=True)
class WeeklyEvidenceClassification:
    classification_version: str
    evidence_content_sha256: str
    entries: tuple[tuple[SourceSection, str, WeeklySemanticClass], ...]
    _index: dict[tuple[SourceSection, str], WeeklySemanticClass] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.classification_version, str) or not self.classification_version.strip():
            raise InvalidDomainValueError("Weekly Evidence classification version must be non-blank")
        if not isinstance(self.evidence_content_sha256, str) or _SHA256.fullmatch(
            self.evidence_content_sha256
        ) is None:
            raise InvalidDomainValueError("Weekly Evidence classification content_sha256 is invalid")
        if not isinstance(self.entries, tuple) or not self.entries:
            raise InvalidDomainValueError("Weekly Evidence classification entries must be a non-empty tuple")
        index: dict[tuple[SourceSection, str], WeeklySemanticClass] = {}
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 3:
                raise InvalidDomainValueError("Weekly Evidence classification entry is invalid")
            section, label, weekly_class = entry
            if not isinstance(section, SourceSection):
                raise InvalidDomainValueError("Weekly Evidence classification source_section is invalid")
            if not isinstance(label, str) or not label.strip():
                raise InvalidDomainValueError("Weekly Evidence classification source_label must be non-blank")
            if not isinstance(weekly_class, WeeklySemanticClass) or weekly_class is WeeklySemanticClass.EXCLUDED:
                raise InvalidDomainValueError(
                    "Weekly Evidence classification entries list allowed classes only; EXCLUDED is the default"
                )
            if (section, label) in index:
                raise InvalidDomainValueError(
                    f"Weekly Evidence classification key is duplicated: {section.value}/{label}"
                )
            index[(section, label)] = weekly_class
        object.__setattr__(self, "_index", index)

    def class_of(self, record: EvidenceRecord) -> WeeklySemanticClass:
        return self._index.get((record.source_section, record.source_label), WeeklySemanticClass.EXCLUDED)

    def require_bound_to(self, content_sha256: str) -> None:
        if content_sha256 != self.evidence_content_sha256:
            raise InvalidDomainValueError(
                "Weekly Evidence classification is bound to different Evidence Store content"
            )
