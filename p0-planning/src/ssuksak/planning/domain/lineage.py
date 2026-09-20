"""Immutable parent-plan lineage kept separate from provenance axes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import InvalidDomainValueError
from .identifiers import ActorId, ItemId, PlanId


@dataclass(frozen=True, slots=True)
class ParentLineage:
    """Snapshot of the confirmed parent used to create a child plan.

    Plan-level lineage leaves ``parent_item_id`` and ``snapshot_value`` empty.
    Item-level lineage supplies both. Evidence that cites this parent remains a
    separate ``EvidenceSource(PARENT_PLAN, ...)`` on the child item.
    """

    parent_plan_id: PlanId
    confirmed_at: datetime
    confirmed_by: ActorId
    parent_item_id: ItemId | None = None
    snapshot_value: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.parent_plan_id, PlanId):
            raise InvalidDomainValueError("ParentLineage.parent_plan_id must be PlanId")
        if not _is_aware(self.confirmed_at):
            raise InvalidDomainValueError(
                "ParentLineage.confirmed_at must be timezone-aware"
            )
        if not isinstance(self.confirmed_by, ActorId):
            raise InvalidDomainValueError("ParentLineage.confirmed_by must be ActorId")
        if (self.parent_item_id is None) != (self.snapshot_value is None):
            raise InvalidDomainValueError(
                "ParentLineage item snapshot requires both parent_item_id and snapshot_value"
            )
        if self.parent_item_id is not None and not isinstance(
            self.parent_item_id, ItemId
        ):
            raise InvalidDomainValueError("ParentLineage.parent_item_id must be ItemId")
        if self.snapshot_value is not None and (
            not isinstance(self.snapshot_value, str) or not self.snapshot_value.strip()
        ):
            raise InvalidDomainValueError(
                "ParentLineage.snapshot_value must be non-blank"
            )


def _is_aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )
