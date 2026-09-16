"""In-memory test adapter for the logical PlanRepository port.

This is not a persistence design and must not be treated as a production DB.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import PlanId

TPlan = TypeVar("TPlan")


class InMemoryPlanRepository(Generic[TPlan]):
    def __init__(self) -> None:
        self._plans: dict[PlanId, TPlan] = {}
        self.save_count = 0

    def save(self, plan_id: PlanId, plan: TPlan) -> None:
        if not isinstance(plan_id, PlanId):
            raise InvalidDomainValueError("InMemoryPlanRepository requires PlanId keys")
        self._plans[plan_id] = plan
        self.save_count += 1

    def get(self, plan_id: PlanId) -> TPlan | None:
        if not isinstance(plan_id, PlanId):
            raise InvalidDomainValueError("InMemoryPlanRepository requires PlanId keys")
        return self._plans.get(plan_id)

    def __len__(self) -> int:
        return len(self._plans)
