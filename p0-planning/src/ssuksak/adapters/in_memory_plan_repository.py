"""InMemory PlanRepository.

CLAUDE.md §17의 가역 Adapter. 최종 PostgreSQL 구현과 동일시하지 않는다.
`save_count`를 노출하는 이유는 Golden Set의 `plan_persisted: false`를
검증하려면 저장 호출 여부를 관찰해야 하기 때문이다.
"""

from __future__ import annotations

from ..planning.domain.plan import YearlyPlan


class InMemoryPlanRepository:
    def __init__(self) -> None:
        self._plans: dict[str, YearlyPlan] = {}
        self.save_count = 0

    def save(self, plan: YearlyPlan) -> None:
        self._plans[plan.plan_id.value] = plan
        self.save_count += 1

    def get(self, plan_id: str) -> YearlyPlan | None:
        return self._plans.get(plan_id)

    def find_yearly(self, classroom_ref: str, school_year: int) -> YearlyPlan | None:
        for plan in self._plans.values():
            if plan.classroom_ref == classroom_ref and plan.school_year == school_year:
                return plan
        return None

    @property
    def stored_count(self) -> int:
        return len(self._plans)
