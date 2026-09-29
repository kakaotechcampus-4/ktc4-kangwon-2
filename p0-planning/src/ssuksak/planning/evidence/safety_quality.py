"""Human-reviewed quality of approved SUPPLEMENTAL safety Reference contents.

Contents are keyed by an exact body key: the item text without its leading
[tag], keeping only Hangul, Latin letters and digits. Only USABLE contents may
ground a supplemental Cell; unlisted contents are EXCLUDED. A topic_group
names one core safety topic and is used once per month as a primary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ..domain.errors import InvalidDomainValueError
from .models import EvidenceRecord

SAFETY_QUALITY_SCHEMA_VERSION = "safety-reference-quality.schema.v0"
SAFETY_QUALITY_ID = "ssuksak.safety-reference-quality"
_LEADING_TAG = re.compile(r"^\s*\[[^\[\]]+\]")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z가-힣]")


class ReferenceQuality(str, Enum):
    USABLE = "USABLE"
    EXCLUDED = "EXCLUDED"


class MonthScope(str, Enum):
    """Where a USABLE content may ground a week; human-reviewed, never inferred."""

    TARGET_MONTH_ONLY = "TARGET_MONTH_ONLY"
    MONTH_INDEPENDENT = "MONTH_INDEPENDENT"


def body_key_of(text: str | None) -> str:
    """LEADING_TAG_STRIPPED_ALNUM body key; empty means no body (EMPTY_BODY)."""
    return _NON_ALNUM.sub("", _LEADING_TAG.sub("", text or "", count=1))


@dataclass(frozen=True, slots=True)
class ReferenceQualityEntry:
    body_key: str
    quality: ReferenceQuality
    topic_group: str | None = None
    reason: str | None = None
    month_scope: MonthScope | None = None

    def __post_init__(self) -> None:
        if (self.quality is ReferenceQuality.USABLE) != isinstance(self.month_scope, MonthScope):
            raise InvalidDomainValueError("Exactly the USABLE entries carry a month_scope")
        if not isinstance(self.body_key, str) or not self.body_key:
            raise InvalidDomainValueError("ReferenceQualityEntry.body_key must be non-blank")
        if not isinstance(self.quality, ReferenceQuality):
            raise InvalidDomainValueError("ReferenceQualityEntry.quality is invalid")
        usable = self.quality is ReferenceQuality.USABLE
        if usable != bool(self.topic_group) or usable == bool(self.reason):
            raise InvalidDomainValueError(
                "USABLE needs a topic_group and no reason; EXCLUDED needs a reason and no topic_group"
            )


@dataclass(frozen=True, slots=True)
class SafetyReferenceQuality:
    quality_version: str
    classification_version: str
    evidence_content_sha256: str
    entries: tuple[ReferenceQualityEntry, ...]
    runtime_active: bool = False
    _index: dict[str, ReferenceQualityEntry] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("quality_version", "classification_version", "evidence_content_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"SafetyReferenceQuality.{name} must be non-blank")
        keys = [entry.body_key for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise InvalidDomainValueError("SafetyReferenceQuality repeats a body_key")
        if type(self.runtime_active) is not bool:
            raise InvalidDomainValueError("SafetyReferenceQuality.runtime_active must be a boolean")
        object.__setattr__(self, "_index", {entry.body_key: entry for entry in self.entries})

    def require_bound_to(self, content_sha256: str, classification_version: str) -> None:
        if content_sha256 != self.evidence_content_sha256 or classification_version != self.classification_version:
            raise InvalidDomainValueError("Safety reference quality targets different evidence or classification")

    def entry_for(self, record: EvidenceRecord) -> ReferenceQualityEntry | None:
        return self._index.get(body_key_of(record.text))

    def usable_topic_group(self, record: EvidenceRecord) -> str | None:
        """topic_group of a USABLE content when approved; None fails closed."""
        if not self.runtime_active:
            return None
        entry = self.entry_for(record)
        return entry.topic_group if entry is not None and entry.quality is ReferenceQuality.USABLE else None

    def month_independent_topic_group(self, record: EvidenceRecord) -> str | None:
        """topic_group usable in other months too; not yet wired into retrieval."""
        if self.usable_topic_group(record) is None:
            return None
        entry = self.entry_for(record)
        return entry.topic_group if entry.month_scope is MonthScope.MONTH_INDEPENDENT else None
