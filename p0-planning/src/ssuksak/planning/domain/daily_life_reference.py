"""Versioned daily-life Reference: approved 기본생활습관 · 건강 · 영양 entries for the play monthly plan.

Each entry is a product sentence linked to one official 누리과정 content id. The label is the
product's display word (e.g. 청결), not an official domain or content category.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError
from .theme_reference import ActivationStatus


class DailyLifeKind(str, Enum):
    HABIT = "HABIT"
    HEALTH = "HEALTH"
    NUTRITION = "NUTRITION"


@dataclass(frozen=True, slots=True)
class DailyLifeEntry:
    entry_id: str
    kind: DailyLifeKind
    label: str
    text: str
    content_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DailyLifeKind):
            raise InvalidDomainValueError("DailyLifeEntry.kind is invalid")
        for name in ("entry_id", "label", "text", "content_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(f"DailyLifeEntry.{name} must be non-blank")


@dataclass(frozen=True, slots=True)
class DailyLifeCatalog:
    catalog_id: str
    catalog_version: str
    activation_status: ActivationStatus
    # The exact 누리과정 Reference version its content ids belong to.
    curriculum_catalog_id: str
    curriculum_catalog_version: str
    entries: tuple[DailyLifeEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.activation_status, ActivationStatus):
            raise InvalidDomainValueError("DailyLifeCatalog.activation_status is invalid")
        ids = [entry.entry_id for entry in self.entries]
        if not ids or len(ids) != len(set(ids)):
            raise InvalidDomainValueError("DailyLifeCatalog needs unique entry ids")

    @property
    def is_active(self) -> bool:
        return self.activation_status is ActivationStatus.HUMAN_APPROVED

    def of_kind(self, kind: DailyLifeKind) -> tuple[DailyLifeEntry, ...]:
        return tuple(entry for entry in self.entries if entry.kind is kind)

    def get(self, entry_id: str) -> DailyLifeEntry | None:
        return next((e for e in self.entries if e.entry_id == entry_id), None)
