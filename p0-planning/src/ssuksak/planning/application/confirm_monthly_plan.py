"""Explicit teacher confirmation of a DRAFT Monthly Plan."""

from __future__ import annotations

from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_verification import FindingKind, Severity
from ..rules.monthly_verification import AGE_RULE_ID, AGE_UNSUPPORTED_CODE
from .monthly_dto import ConfirmMonthlyPlanCommand
from .monthly_errors import MonthlyApplicationError
from .monthly_support import (
    load_plan_activity_catalog,
    require_actor,
    require_monthly_plan,
    with_fresh_monthly_verification,
)
from .ports import ActivityReferenceRepository, Clock, PlanRepository


class ConfirmMonthlyPlan:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository[MonthlyPlan],
        clock: Clock,
        activity_repository: ActivityReferenceRepository | None = None,
    ) -> None:
        self._plans = plan_repository
        self._clock = clock
        self._activities = activity_repository

    def execute(self, command: ConfirmMonthlyPlanCommand) -> MonthlyPlan:
        plan = require_monthly_plan(self._plans, command.plan_id)
        actor_id = require_actor(command.actor_id)
        catalog = load_plan_activity_catalog(self._activities, plan)
        verified = with_fresh_monthly_verification(plan, catalog)
        report = verified.verification_report
        if report is not None and any(
            finding.rule_id == AGE_RULE_ID
            and finding.code == AGE_UNSUPPORTED_CODE
            and finding.finding_kind is FindingKind.VIOLATION
            and finding.severity is Severity.ERROR
            for finding in report.findings
        ):
            self._plans.save(verified.plan_id, verified)
            raise MonthlyApplicationError(
                "monthly_confirmation_blocked",
                "Monthly Plan has a blocking supported-age violation",
            )
        confirmed = verified.confirm(
            actor_id=actor_id, occurred_at=self._clock.now()
        )
        self._plans.save(confirmed.plan_id, confirmed)
        return confirmed
