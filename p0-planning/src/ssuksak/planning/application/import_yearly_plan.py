"""Save a teacher-supplied Yearly table as a DRAFT Yearly Plan (2026-11-01 I-A).

No Rule picks the themes, so no Theme Reference is cited. MANUAL = typed into the
table, IMPORTED = read from a file and checked by the teacher.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.identifiers import ActorId
from ..domain.plan import PlanItem, PlanStatus
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    GenerationMethod,
    GenerationMethodDetail,
)
from ..domain.yearly_plan import YearlyPeriod, YearlyPlan
from ..rules.academic_periods import ACADEMIC_MONTH_ORDER, academic_year_periods
from ..rules.yearly_reference_rules import validate_age_set
from .ports import Clock, IdGenerator, PlanRepository
from .yearly_errors import YearlyApplicationError
from .yearly_support import require_actor


@dataclass(frozen=True, slots=True)
class ImportYearlyPlanCommand:
    school_year: int
    classroom_ref: str
    target_ages: frozenset[int]
    method: GenerationMethod  # MANUAL | IMPORTED
    themes: tuple[tuple[int, str], ...]  # (calendar month, theme), March → February
    actor_id: ActorId


class ImportYearlyPlan:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[YearlyPlan],
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._plans = plan_repository
        self._clock = clock
        self._ids = id_generator

    def execute(self, command: ImportYearlyPlanCommand) -> YearlyPlan:
        if command.method not in (GenerationMethod.MANUAL, GenerationMethod.IMPORTED):
            raise YearlyApplicationError(
                "invalid_import_method", "Yearly import is MANUAL or IMPORTED"
            )
        actor_id = require_actor(command.actor_id)
        themes = tuple(command.themes)
        # Order check covers count, duplicates and gaps at once (OD-Y01).
        if tuple(month for month, _ in themes) != ACADEMIC_MONTH_ORDER:
            raise YearlyApplicationError(
                "invalid_import_months",
                "Yearly import needs 12 months from March through February",
            )
        if any(not isinstance(theme, str) or not theme.strip() for _, theme in themes):
            raise YearlyApplicationError(
                "invalid_import_months", "Every imported month needs a non-blank theme"
            )
        periods = academic_year_periods(command.school_year)
        ages = validate_age_set(command.target_ages)

        plan_id = self._ids.new_plan_id()
        now = self._clock.now()
        generation = GenerationMethodDetail(method=command.method)
        yearly_periods = []
        for period, (_, theme) in zip(periods, themes, strict=True):
            item_id = self._ids.new_item_id()
            created = AuditEvent(
                event_type=AuditEventType.CREATED,
                occurred_at=now,
                plan_id=plan_id,
                item_id=item_id,
                actor_id=actor_id,
            )
            item = PlanItem(
                item_id=item_id,
                value=theme.strip(),
                evidence=(),
                generation=generation,
                audit=AuditHistory((created,)),
            )
            yearly_periods.append(YearlyPeriod(period=period, theme=item))

        plan = YearlyPlan(
            plan_id=plan_id,
            school_year=command.school_year,
            classroom_ref=command.classroom_ref,
            target_ages=ages,
            status=PlanStatus.DRAFT,
            periods=tuple(yearly_periods),
            audit=AuditHistory(
                (
                    AuditEvent(
                        event_type=AuditEventType.CREATED,
                        occurred_at=now,
                        plan_id=plan_id,
                        actor_id=actor_id,
                    ),
                )
            ),
        )
        self._plans.save(plan.plan_id, plan)
        return plan
