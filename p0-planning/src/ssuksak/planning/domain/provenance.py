"""The three independent axes of Planning Core provenance.

Evidence answers where a value came from. Generation describes how the current
value was produced. Audit history records later actions. AI and teacher edits
are deliberately not evidence source types.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from .errors import InvalidDomainValueError
from .identifiers import ActorId, ItemId, PlanId


class EvidenceSourceType(str, Enum):
    CURRICULUM = "CURRICULUM"
    THEME_REFERENCE = "THEME_REFERENCE"
    PARENT_PLAN = "PARENT_PLAN"
    DAYCARE_PROFILE = "DAYCARE_PROFILE"
    CLASSROOM_PROFILE = "CLASSROOM_PROFILE"
    EVENT = "EVENT"
    SAFETY_RULE = "SAFETY_RULE"
    ACTIVITY_REFERENCE = "ACTIVITY_REFERENCE"
    INSTITUTION_SAMPLE = "INSTITUTION_SAMPLE"
    CALENDAR = "CALENDAR"
    TREND = "TREND"
    EXTERNAL_CONTEXT = "EXTERNAL_CONTEXT"


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    source_type: EvidenceSourceType
    source_id: str
    source_version: str | None = None
    effective_date: date | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, EvidenceSourceType):
            raise InvalidDomainValueError("EvidenceSource.source_type is invalid")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise InvalidDomainValueError("EvidenceSource.source_id must be non-blank")
        for name in ("source_version", "display_name"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise InvalidDomainValueError(
                    f"EvidenceSource.{name} must be non-blank when set"
                )
        if self.effective_date is not None and not isinstance(
            self.effective_date, date
        ):
            raise InvalidDomainValueError(
                "EvidenceSource.effective_date must be a date"
            )


class GenerationMethod(str, Enum):
    RULE_ONLY = "RULE_ONLY"
    RULE_LLM = "RULE_LLM"
    IMPORTED = "IMPORTED"
    MANUAL = "MANUAL"
    TEACHER_EDIT = "TEACHER_EDIT"


@dataclass(frozen=True, slots=True)
class GenerationMethodDetail:
    method: GenerationMethod
    rule_id: str | None = None
    rule_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.method, GenerationMethod):
            raise InvalidDomainValueError("GenerationMethodDetail.method is invalid")
        if self.method in (
            GenerationMethod.RULE_ONLY,
            GenerationMethod.RULE_LLM,
        ) and (not _is_non_blank(self.rule_id) or not _is_non_blank(self.rule_version)):
            raise InvalidDomainValueError(
                "Rule-based generation requires rule_id and rule_version"
            )
        for name in ("rule_id", "rule_version"):
            value = getattr(self, name)
            if value is not None and not _is_non_blank(value):
                raise InvalidDomainValueError(
                    f"GenerationMethodDetail.{name} cannot be blank"
                )


class AuditEventType(str, Enum):
    CREATED = "CREATED"
    REGENERATED = "REGENERATED"
    TEACHER_EDITED = "TEACHER_EDITED"
    CONFIRMED = "CONFIRMED"
    # Plan-level: a teacher saved which candidates a play-project period keeps (2026-10-26).
    CANDIDATES_SELECTED = "CANDIDATES_SELECTED"
    # Plan-level: a teacher added or removed a play row, or placed a safety week (2026-10-27).
    ARRANGEMENT_CHANGED = "ARRANGEMENT_CHANGED"
    # Cell-level: a teacher copied a same-plan candidate into a cell (2026-10-27, M2-D17).
    CANDIDATE_COPIED = "CANDIDATE_COPIED"


@dataclass(frozen=True, slots=True)
class ValueChange:
    before: str
    after: str

    def __post_init__(self) -> None:
        if not isinstance(self.before, str) or not isinstance(self.after, str):
            raise InvalidDomainValueError(
                "ValueChange values must be strings"
            )
        if not self.before.strip() and not self.after.strip():
            raise InvalidDomainValueError(
                "ValueChange must contain at least one non-blank value"
            )


@dataclass(frozen=True, slots=True)
class GenerationMethodChange:
    before: GenerationMethodDetail
    after: GenerationMethodDetail

    def __post_init__(self) -> None:
        if not isinstance(self.before, GenerationMethodDetail) or not isinstance(
            self.after, GenerationMethodDetail
        ):
            raise InvalidDomainValueError(
                "GenerationMethodChange values must be GenerationMethodDetail"
            )


@dataclass(frozen=True, slots=True)
class SelectionChange:
    """The kept candidates of one period before and after a save, in document order."""

    period_key: str
    before: tuple[str, ...]
    after: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _is_non_blank(self.period_key):
            raise InvalidDomainValueError("SelectionChange.period_key must be non-blank")
        for keys in (self.before, self.after):
            if not isinstance(keys, tuple) or not all(_is_non_blank(key) for key in keys):
                raise InvalidDomainValueError("SelectionChange keys must be non-blank strings")
            if len(keys) != len(set(keys)):
                raise InvalidDomainValueError("SelectionChange keys must be unique")
        if self.before == self.after:
            raise InvalidDomainValueError("SelectionChange must change the selection")


@dataclass(frozen=True, slots=True)
class ArrangementChange:
    """The active item ids of one scope (a play section or a week) before and after a change."""

    scope: str
    before: tuple[str, ...]
    after: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _is_non_blank(self.scope):
            raise InvalidDomainValueError("ArrangementChange.scope must be non-blank")
        for ids in (self.before, self.after):
            if not isinstance(ids, tuple) or not all(_is_non_blank(i) for i in ids):
                raise InvalidDomainValueError("ArrangementChange ids must be non-blank strings")
            if len(ids) != len(set(ids)):
                raise InvalidDomainValueError("ArrangementChange ids must be unique")
        if self.before == self.after:
            raise InvalidDomainValueError("ArrangementChange must change the arrangement")


@dataclass(frozen=True, slots=True)
class LinkChange:
    """A teacher's change to a play's curriculum content ids, within one catalog version."""

    before: tuple[str, ...]
    after: tuple[str, ...]
    catalog_version: str

    def __post_init__(self) -> None:
        for ids in (self.before, self.after):
            if not isinstance(ids, tuple) or not all(_is_non_blank(i) for i in ids):
                raise InvalidDomainValueError("LinkChange ids must be non-blank strings")
            if len(ids) != len(set(ids)):
                raise InvalidDomainValueError("LinkChange ids must be unique")
        if self.before == self.after:
            raise InvalidDomainValueError("LinkChange must change the links")
        if not _is_non_blank(self.catalog_version):
            raise InvalidDomainValueError("LinkChange.catalog_version must be non-blank")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: AuditEventType
    occurred_at: datetime
    plan_id: PlanId
    item_id: ItemId | None = None
    actor_id: ActorId | None = None
    system_actor: str | None = None
    value_change: ValueChange | None = None
    generation_change: GenerationMethodChange | None = None
    selection_change: SelectionChange | None = None
    link_change: LinkChange | None = None
    arrangement_change: ArrangementChange | None = None
    copied_from: ItemId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, AuditEventType):
            raise InvalidDomainValueError("AuditEvent.event_type is invalid")
        if not _is_aware(self.occurred_at):
            raise InvalidDomainValueError(
                "AuditEvent.occurred_at must be timezone-aware"
            )
        if not isinstance(self.plan_id, PlanId):
            raise InvalidDomainValueError("AuditEvent.plan_id must be PlanId")
        if self.item_id is not None and not isinstance(self.item_id, ItemId):
            raise InvalidDomainValueError("AuditEvent.item_id must be ItemId when set")
        if (self.actor_id is None) == (self.system_actor is None):
            raise InvalidDomainValueError(
                "AuditEvent requires exactly one of actor_id or system_actor"
            )
        if self.actor_id is not None and not isinstance(self.actor_id, ActorId):
            raise InvalidDomainValueError("AuditEvent.actor_id must be ActorId")
        if self.system_actor is not None and not _is_non_blank(self.system_actor):
            raise InvalidDomainValueError("AuditEvent.system_actor must be non-blank")
        if self.value_change is not None and not isinstance(
            self.value_change, ValueChange
        ):
            raise InvalidDomainValueError(
                "AuditEvent.value_change must be ValueChange when set"
            )
        if self.generation_change is not None and not isinstance(
            self.generation_change, GenerationMethodChange
        ):
            raise InvalidDomainValueError(
                "AuditEvent.generation_change must be GenerationMethodChange when set"
            )
        if self.link_change is not None and (
            self.event_type is not AuditEventType.TEACHER_EDITED
            or not isinstance(self.link_change, LinkChange)
        ):
            raise InvalidDomainValueError("Only TEACHER_EDITED carries a LinkChange")
        # A teacher edit changes the value or the curriculum links, never the Generation
        # Method, so it needs no generation_change (REGENERATED is where the method changes).
        if self.event_type is AuditEventType.TEACHER_EDITED and (
            self.actor_id is None
            or self.item_id is None
            or (self.value_change is None and self.link_change is None)
        ):
            raise InvalidDomainValueError(
                "TEACHER_EDITED requires actor_id, item_id and value_change or link_change"
            )
        if self.event_type is AuditEventType.CANDIDATES_SELECTED:
            if (
                self.actor_id is None
                or not isinstance(self.selection_change, SelectionChange)
                or self.item_id is not None
                or self.value_change is not None
                or self.generation_change is not None
            ):
                raise InvalidDomainValueError(
                    "CANDIDATES_SELECTED is a plan-level teacher event with selection_change only"
                )
        elif self.selection_change is not None:
            raise InvalidDomainValueError(
                "Only CANDIDATES_SELECTED carries selection_change"
            )
        if self.event_type is AuditEventType.ARRANGEMENT_CHANGED:
            if (
                self.actor_id is None
                or not isinstance(self.arrangement_change, ArrangementChange)
                or self.item_id is not None
                or self.value_change is not None
                or self.generation_change is not None
            ):
                raise InvalidDomainValueError(
                    "ARRANGEMENT_CHANGED is a plan-level teacher event with arrangement_change only"
                )
        elif self.arrangement_change is not None:
            raise InvalidDomainValueError("Only ARRANGEMENT_CHANGED carries arrangement_change")
        # generation_change is absent only when the cell was never written before the copy.
        if self.event_type is AuditEventType.CANDIDATE_COPIED:
            if (
                self.actor_id is None
                or self.item_id is None
                or not isinstance(self.copied_from, ItemId)
                or self.value_change is None
            ):
                raise InvalidDomainValueError(
                    "CANDIDATE_COPIED requires actor_id, item_id, copied_from and value_change"
                )
        elif self.copied_from is not None:
            raise InvalidDomainValueError("Only CANDIDATE_COPIED carries copied_from")


@dataclass(frozen=True, slots=True)
class AuditHistory:
    """An immutable, chronological sequence of audit events."""

    events: tuple[AuditEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple):
            raise InvalidDomainValueError("AuditHistory.events must be a tuple")
        previous: datetime | None = None
        for event in self.events:
            if not isinstance(event, AuditEvent):
                raise InvalidDomainValueError(
                    "AuditHistory accepts AuditEvent values only"
                )
            if previous is not None and event.occurred_at < previous:
                raise InvalidDomainValueError(
                    "AuditHistory events must be chronological"
                )
            previous = event.occurred_at

    def append(self, event: AuditEvent) -> AuditHistory:
        return AuditHistory(self.events + (event,))

    def current_value_teacher_edited(self) -> bool:
        """True when a teacher edit set the current value: no later regeneration.

        A links-only edit (no value_change) leaves the value as it was, so it is skipped.
        """
        for event in reversed(self.events):
            if event.event_type is AuditEventType.CONFIRMED or (
                event.event_type is AuditEventType.TEACHER_EDITED and event.value_change is None
            ):
                continue
            return event.event_type is AuditEventType.TEACHER_EDITED
        return False

    def __iter__(self) -> Iterator[AuditEvent]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)


def _is_non_blank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )
