"""RegenerateYearlyPlanItem Use Case.

승인된 결정 4 + 인접 중복 보강:
- 인접 MonthPeriod Theme과 중복되지 않는 후보를 우선한다.
- 그 안에서 현재 Theme과 다른 후보를 우선한다.
- 현재 Theme과 다른 후보가 있어도 그것이 인접 월 Theme과 충돌하고 다른 안전한
  후보가 없다면, 기존 theme_id를 유지하고 표현만 재생성한다.
- Reference 밖의 새 Theme을 LLM이 생성하는 것은 계속 금지한다.
- **Regenerate가 반드시 값이나 theme_id를 바꿔야 한다는 Contract가 아니다.**

CLAUDE.md §19: 선택하지 않은 Item의 item_id·값·Evidence를 보존하고,
대상 Item의 item_id와 semantic_key도 안정적으로 유지한다.

**Mutation Atomicity**
Actor Validation과 LLM 호출, AuditEvent 생성을 모두 Mutation보다 먼저 수행한다.
"""

from __future__ import annotations

from ...shared.llm.port import (
    LLMPort,
    LLMUnavailableError,
    ThemePolishConstraints,
    ThemePolishRequest,
)
from ..domain.errors import FailureCategory, validation_failed
from ..domain.plan import YearlyPlan
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ..rules import gates
from ..rules.yearly_theme_selection import (
    RULE_ID,
    RULE_VERSION,
    adjacent_theme_ids_for,
    select_theme_for_period,
)
from .confirm_yearly_plan import require_opaque_actor
from .dto import GenerationRun, RegenerateYearlyPlanItemCommand, YearlyPlanResult
from .ports import Clock, IdGenerator, PlanRepository, ThemeReferenceRepository


class RegenerateYearlyPlanItem:
    def __init__(
        self,
        *,
        theme_repository: ThemeReferenceRepository,
        plan_repository: PlanRepository,
        llm: LLMPort,
        clock: Clock,
        id_generator: IdGenerator,
        polish_constraints: ThemePolishConstraints | None = None,
        use_llm: bool = True,
    ) -> None:
        self._themes = theme_repository
        self._plans = plan_repository
        self._llm = llm
        self._clock = clock
        self._ids = id_generator
        self._constraints = polish_constraints or ThemePolishConstraints()
        self._use_llm = use_llm

    def execute(self, command: RegenerateYearlyPlanItemCommand) -> YearlyPlanResult:
        plan = self._require_plan(command.plan_id)

        # ---- 실패 가능한 검사는 전부 Mutation·LLM 호출 이전에 수행한다 ----

        # CONFIRMED는 read-only.
        plan.ensure_mutable("RegenerateYearlyPlanItem")

        # Actor Validation을 LLM 호출·Mutation 전에.
        actor = require_opaque_actor(
            command.actor_id, rule="regenerate_requires_opaque_actor_id"
        )

        found = plan.find_item(
            item_id=command.address.item_id,
            period_key=command.address.period_key,
            semantic_key=command.address.semantic_key,
        )
        if found is None:
            raise validation_failed(
                "regenerate_target_item_must_exist",
                FailureCategory.INPUT_VALIDATION,
                f"대상 Item을 찾을 수 없다: {command.address}",
            )
        month_period, item = found

        catalog = gates.require_resolved_catalog(
            self._themes.get_catalog(
                command.catalog.catalog_id, command.catalog.catalog_version
            ),
            command.catalog.catalog_id,
            command.catalog.catalog_version,
        )
        gates.require_human_approved_catalog(catalog)

        current_theme_id = _current_theme_id(item)

        run = GenerationRun(
            run_id=self._ids.new_run_id(),
            started_at=self._clock.now(),
            catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
        )

        selection = select_theme_for_period(
            catalog=catalog,
            period_key=month_period.period_key.value,
            calendar_month=month_period.period_key.calendar_month,
            ages=plan.classroom_ages,
            adjacent_theme_ids=adjacent_theme_ids_for(
                plan, month_period.period_key.value
            ),
            exclude_theme_id=current_theme_id,
        )
        run.selection_traces = (selection.trace,)
        candidate = selection.candidate

        # LLM 호출도 Mutation 전에 끝낸다.
        new_value, method = self._resolve_value(
            candidate, month_period.period_key.value, plan, selection.trace.reason, run
        )

        new_evidence = [
            EvidenceSource(
                source_type=EvidenceSourceType.THEME_REFERENCE,
                source_id=candidate.theme_id,
                source_version=catalog.catalog_version,
                display_name=candidate.label,
            ),
            # 이 기간에 원래 붙어 있던 비-Theme Evidence(예: EVENT)는 보존한다.
            *[
                e
                for e in item.evidence
                if e.source_type is not EvidenceSourceType.THEME_REFERENCE
            ],
        ]

        # AuditEvent를 Mutation 전에 만들어 둔다.
        event = AuditEvent(
            event_type=AuditEventType.REGENERATED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id.value,
            item_id=item.item_id.value,
            actor_id=actor,
            previous_value=item.value,
            new_value=new_value,
            previous_method=item.generation.method,
            new_method=method.method,
        )

        # ---------------------- 여기서부터 Mutation ----------------------
        # 대상 Item의 item_id / semantic_key는 그대로 둔다.
        item.value = new_value
        item.generation = method
        item.evidence = new_evidence
        item.audit.append(event)

        self._plans.save(plan)
        return YearlyPlanResult(plan=plan, run=run)

    # ------------------------------------------------------------ 내부

    def _require_plan(self, plan_id: str) -> YearlyPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise validation_failed(
                "target_plan_must_exist",
                FailureCategory.INPUT_VALIDATION,
                f"Plan을 찾을 수 없다: {plan_id}",
            )
        return plan

    def _resolve_value(
        self,
        candidate,
        period_key: str,
        plan: YearlyPlan,
        selection_reason: str,
        run: GenerationRun,
    ) -> tuple[str, GenerationMethodDetail]:
        base = GenerationMethodDetail(
            method=GenerationMethod.RULE_ONLY,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            selection_reason=selection_reason,
        )
        if not self._use_llm:
            return candidate.label, base

        request = ThemePolishRequest(
            task="polish_yearly_theme_label",
            selected_theme_id=candidate.theme_id,
            selected_theme_label=candidate.label,
            period_key=period_key,
            ages=tuple(sorted(plan.classroom_ages)),
            constraints=self._constraints,
        )

        run.llm_invoked = True
        run.llm_call_count += 1

        try:
            response = self._llm.polish_theme(request)
        except LLMUnavailableError as exc:
            raise validation_failed(
                "llm_final_failure_is_not_a_successful_plan",
                FailureCategory.LLM_FAILURE,
                str(exc),
                period_key=period_key,
            ) from exc
        except ValueError as exc:
            raise validation_failed(
                "llm_output_must_satisfy_structured_output_schema",
                FailureCategory.LLM_OUTPUT_VALIDATION,
                str(exc),
                period_key=period_key,
            ) from exc

        if response.theme_id != candidate.theme_id:
            raise validation_failed(
                "llm_must_not_select_or_replace_theme",
                FailureCategory.LLM_OUTPUT_VALIDATION,
                f"Rule 선택 {candidate.theme_id} != LLM 반환 {response.theme_id}",
                period_key=period_key,
            )

        if not response.value.strip():
            raise validation_failed(
                "theme_is_required_and_non_blank_for_every_period",
                FailureCategory.REQUIRED_VALUE_VALIDATION,
                "LLM이 공백 표현을 반환했다",
                period_key=period_key,
            )

        return response.value, GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=base.rule_id,
            rule_version=base.rule_version,
            selection_reason=selection_reason,
        )


def _current_theme_id(item) -> str | None:
    refs = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    return refs[0].source_id if refs else None
