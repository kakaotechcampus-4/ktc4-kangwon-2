"""Plan primitives shared by Yearly, Monthly, and Weekly aggregates."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum

from .errors import InvalidDomainValueError
from .identifiers import ActorId, ItemId, PlanId
from .provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    GenerationMethodDetail,
    ValueChange,
)


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"

    @property
    def is_mutable(self) -> bool:
        return self is PlanStatus.DRAFT


@dataclass(frozen=True, slots=True)
class PlanItem:
    """A provider-neutral editable value with independent provenance axes."""

    item_id: ItemId
    value: str
    evidence: tuple[EvidenceSource, ...]
    generation: GenerationMethodDetail
    audit: AuditHistory = field(default_factory=AuditHistory)

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, ItemId):
            raise InvalidDomainValueError("PlanItem.item_id must be ItemId")
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidDomainValueError("PlanItem.value must be a non-blank string")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(source, EvidenceSource) for source in self.evidence
        ):
            raise InvalidDomainValueError(
                "PlanItem.evidence must be a tuple of EvidenceSource"
            )
        if not isinstance(self.generation, GenerationMethodDetail):
            raise InvalidDomainValueError(
                "PlanItem.generation must be GenerationMethodDetail"
            )
        if not isinstance(self.audit, AuditHistory):
            raise InvalidDomainValueError("PlanItem.audit must be AuditHistory")

    def edit_by_teacher(
        self,
        *,
        plan_id: PlanId,
        new_value: str,
        actor_id: ActorId,
        occurred_at: datetime,
    ) -> PlanItem:
        """Return an edited item; evidence and Generation Method stay, the Audit records the edit."""

        if not isinstance(new_value, str) or not new_value.strip():
            raise InvalidDomainValueError("Teacher-edited value must be non-blank")
        event = AuditEvent(
            event_type=AuditEventType.TEACHER_EDITED,
            occurred_at=occurred_at,
            plan_id=plan_id,
            item_id=self.item_id,
            actor_id=actor_id,
            value_change=ValueChange(before=self.value, after=new_value),
        )
        return replace(self, value=new_value, audit=self.audit.append(event))
