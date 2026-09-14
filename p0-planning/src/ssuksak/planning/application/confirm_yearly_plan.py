"""ConfirmYearlyPlan Use Case와 하위 단계 Gate 조회.

CLAUDE.md §19 / docs/screen-spec.md §8:
- Confirm은 opaque ActorId를 요구한다. 담임 표시 이름이 이를 대체하지 못한다.
- Confirm은 제출/발송을 수행하지 않는다.
- 확정 후 Plan은 read-only가 된다.

**Reference Validation은 절대 생략하지 않는다.**
`ThemeReferenceRepository`는 Confirm의 필수 Dependency이고
`ConfirmYearlyPlanCommand.catalog`도 필수다. catalog를 생략해
Reference Validation을 우회하는 경로가 존재하지 않는다.
"""

from __future__ import annotations

from ..domain.errors import FailureCategory, validation_failed
from ..domain.identifiers import ActorId
from ..domain.plan import PlanStatus, YearlyPlan
from ..domain.provenance import AuditEvent, AuditEventType
from ..rules import gates
from .dto import ConfirmYearlyPlanCommand, YearlyPlanResult
from .ports import Clock, PlanRepository, ThemeReferenceRepository
from .validate_yearly_plan import validate_yearly_plan


class ConfirmYearlyPlan:
    def __init__(
        self,
        *,
        plan_repository: PlanRepository,
        clock: Clock,
        theme_repository: ThemeReferenceRepository,
    ) -> None:
        if theme_repository is None:
            raise ValueError(
                "ConfirmYearlyPlan은 ThemeReferenceRepository를 필수로 요구한다. "
                "Reference Validation을 생략할 수 없다."
            )
        self._plans = plan_repository
        self._clock = clock
        self._themes = theme_repository

    def execute(self, command: ConfirmYearlyPlanCommand) -> YearlyPlanResult:
        plan = self._plans.get(command.plan_id)
        if plan is None:
            raise validation_failed(
                "target_plan_must_exist",
                FailureCategory.INPUT_VALIDATION,
                f"Plan을 찾을 수 없다: {command.plan_id}",
            )

        # ------------------------------------------- 1. Actor Validation
        require_opaque_actor(command.actor_id, rule="confirm_requires_opaque_actor_id")

        # ------------------------------------------------ 2. 상태 확인
        if plan.status is PlanStatus.CONFIRMED:
            raise validation_failed(
                "confirmed_yearly_plan_is_read_only",
                FailureCategory.PLAN_STATE_GATE,
                "이미 확정된 Plan이다",
            )

        # --------------------------- 3. Catalog 정확 resolve + 승인 Gate
        if command.catalog is None:
            raise validation_failed(
                "confirm_requires_resolved_theme_reference_catalog",
                FailureCategory.REFERENCE_VALIDATION,
                "Confirm은 Reference Validation을 위해 Catalog를 요구한다",
            )

        catalog = gates.require_resolved_catalog(
            self._themes.get_catalog(
                command.catalog.catalog_id, command.catalog.catalog_version
            ),
            command.catalog.catalog_id,
            command.catalog.catalog_version,
        )
        gates.require_human_approved_catalog(catalog)

        # ------------------------- 4. 전체 Validation (Reference 포함)
        validate_yearly_plan(
            plan,
            catalog=catalog,
            expected_school_year=plan.school_year,
            expected_classroom_ref=plan.classroom_ref,
        )

        # ------------------ 5. 성공한 경우에만 CONFIRMED로 전이
        event = AuditEvent(
            event_type=AuditEventType.CONFIRMED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id.value,
            actor_id=command.actor_id,
        )
        plan.confirm(event)
        self._plans.save(plan)
        return YearlyPlanResult(plan=plan)


def require_opaque_actor(actor_id: object, *, rule: str) -> ActorId:
    """Actor가 opaque ActorId인지 확인한다.

    **모든 Mutation보다 먼저** 호출되어야 한다. 타입 힌트만으로는 원시 문자열
    (예: 담임 표시 이름)이 들어오는 것을 막을 수 없으므로 런타임에서 확인한다(OD-Y03).
    """
    if actor_id is None:
        raise validation_failed(
            rule,
            FailureCategory.ACTOR_VALIDATION,
            "opaque actor_id가 필요하다. 담임 표시 이름은 이를 대체하지 못한다.",
        )
    if not isinstance(actor_id, ActorId):
        raise validation_failed(
            rule,
            FailureCategory.ACTOR_VALIDATION,
            f"actor_id는 opaque ActorId여야 한다: {type(actor_id).__name__}",
        )
    return actor_id


class MonthlyGenerationGate:
    """하위 단계 Gate 조회.

    tests/golden/yearly_cases.json case 15는 Yearly Slice가 다음 단계 Gate를
    올바르게 제공하는지만 검증하며 Monthly 구현을 요구하지 않는다(scope_note).
    """

    def __init__(self, *, plan_repository: PlanRepository) -> None:
        self._plans = plan_repository

    def ensure_can_generate_monthly(self, classroom_ref: str, school_year: int) -> YearlyPlan:
        parent = self._plans.find_yearly(classroom_ref, school_year)
        gates.require_confirmed_parent_yearly(parent)
        assert parent is not None
        return parent
