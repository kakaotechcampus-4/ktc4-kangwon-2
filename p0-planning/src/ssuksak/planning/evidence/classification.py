"""Human-approved exact-label semantic classification of Institution Evidence.

The classification decides which Evidence records may ground which Monthly
Section. It keys on the exact ``(source_section, source_label)`` pair: no
substring, fuzzy or institution-specific matching. Unlisted labels are
EXCLUDED. It never changes the Evidence corpus itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ..domain.errors import InvalidDomainValueError
from ..domain.monthly_template import SemanticVariant, TemplateSection
from .models import EvidenceRecord, SourceSection

CLASSIFICATION_SCHEMA_VERSION = "monthly-evidence-semantic-classification.schema.v0"
CLASSIFICATION_ID = "ssuksak.monthly-evidence-semantic-classification"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SemanticClass(str, Enum):
    GOALS = "GOALS"
    BASIC_HABIT = "BASIC_HABIT"
    SUBTHEME = "SUBTHEME"
    EXPECTED_PLAY = "EXPECTED_PLAY"
    EXCLUDED = "EXCLUDED"


# Approved D2 grounding policy: each class grounds exactly one Section/variant.
GROUNDING_SCOPE: dict[SemanticClass, tuple[str, SemanticVariant | None]] = {
    SemanticClass.GOALS: ("goals", None),
    SemanticClass.BASIC_HABIT: ("basic_habit", None),
    SemanticClass.SUBTHEME: ("focus", SemanticVariant.SUBTHEME),
    SemanticClass.EXPECTED_PLAY: ("focus", SemanticVariant.EXPECTED_PLAY),
}
CLASS_SCOPED_SECTION_KEYS = frozenset(key for key, _ in GROUNDING_SCOPE.values())


def grounding_class_for(section: TemplateSection) -> SemanticClass | None:
    """Return the only Evidence class this Section may cite, if any.

    A class-scoped Section (goals, basic_habit, focus) whose semantic variant
    has no approved class, such as focus WEEKLY_THEME, returns None.
    """
    for semantic_class, (section_key, variant) in GROUNDING_SCOPE.items():
        if section.section_key == section_key and (
            variant is None or section.semantic_variant is variant
        ):
            return semantic_class
    return None


@dataclass(frozen=True, slots=True)
class EvidenceSemanticClassification:
    classification_version: str
    evidence_content_sha256: str
    entries: tuple[tuple[SourceSection, str, SemanticClass], ...]
    _index: dict[tuple[SourceSection, str], SemanticClass] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.classification_version, str) or not self.classification_version.strip():
            raise InvalidDomainValueError("Evidence classification version must be non-blank")
        if not isinstance(self.evidence_content_sha256, str) or _SHA256.fullmatch(
            self.evidence_content_sha256
        ) is None:
            raise InvalidDomainValueError("Evidence classification content_sha256 is invalid")
        if not isinstance(self.entries, tuple) or not self.entries:
            raise InvalidDomainValueError("Evidence classification entries must be a non-empty tuple")
        index: dict[tuple[SourceSection, str], SemanticClass] = {}
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 3:
                raise InvalidDomainValueError("Evidence classification entry is invalid")
            section, label, semantic_class = entry
            if not isinstance(section, SourceSection):
                raise InvalidDomainValueError("Evidence classification source_section is invalid")
            if not isinstance(label, str) or not label.strip():
                raise InvalidDomainValueError("Evidence classification source_label must be non-blank")
            if not isinstance(semantic_class, SemanticClass) or semantic_class is SemanticClass.EXCLUDED:
                raise InvalidDomainValueError(
                    "Evidence classification entries list allowed classes only; EXCLUDED is the default"
                )
            if (section, label) in index:
                raise InvalidDomainValueError(
                    f"Evidence classification key is duplicated: {section.value}/{label}"
                )
            index[(section, label)] = semantic_class
        object.__setattr__(self, "_index", index)

    def class_of(self, record: EvidenceRecord) -> SemanticClass:
        return self._index.get((record.source_section, record.source_label), SemanticClass.EXCLUDED)

    def require_bound_to(self, content_sha256: str) -> None:
        if content_sha256 != self.evidence_content_sha256:
            raise InvalidDomainValueError(
                "Evidence classification is bound to different Evidence Store content"
            )
