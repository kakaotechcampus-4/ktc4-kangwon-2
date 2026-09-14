"""GenerateYearlyPlan Use Case.

실행 순서가 계약이다. tests/golden/yearly_cases.json case 5·6·9·13·14는 모두
`plan_persisted: false`와 `llm_called: false`를 요구하므로
**Gate → Reference → Rule → LLM → Validation → 저장** 순서를 지켜야 한다.
"""

from __future__ import annotations

from ...shared.llm.batch import (
    BatchReconcileError,
    BatchViolation,
    ThemeBatchPolishItem,
    ThemeBatchPolishRequest,
    reconcile_batch,
)
from ...shared.llm.port import (
    LLMConfigurationError,
    LLMPort,
    LLMUnavailableError,
    ThemePolishConstraints,
)
from ..domain.errors import FailureCategory, validation_failed
from ..domain.identifiers import ItemId, PeriodKey, PlanId, SemanticKey
from ..domain.plan import MonthPeriod, PlanItem, PlanStatus, YearlyPlan
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditTrail,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
    SYSTEM_ACTOR_MARKER,
)
from ..domain.theme_reference import ThemeCandidate, ThemeCatalog
from ..rules import gates
from ..rules.periods import academic_period_keys
from ..rules.yearly_theme_selection import (
    RULE_ID,
    RULE_VERSION,
    select_theme_for_period,
)
from .dto import (
    EventInput,
    GenerateYearlyPlanCommand,
    GenerationRun,
    ThemeSelectionTrace,
    YearlyPlanResult,
)
from .ports import (
    Clock,
    IdGenerator,
    OptionalContextBundle,
    OptionalContextProvider,
    PlanRepository,
    ThemeReferenceRepository,
)
from .validate_yearly_plan import validate_yearly_plan


class GenerateYearlyPlan:
    def __init__(
        self,
        *,
        theme_repository: ThemeReferenceRepository,
        plan_repository: PlanRepository,
        llm: LLMPort,
        clock: Clock,
        id_generator: IdGenerator,
        optional_context: OptionalContextProvider | None = None,
        polish_constraints: ThemePolishConstraints | None = None,
        use_llm: bool = True,
    ) -> None:
        self._themes = theme_repository
        self._plans = plan_repository
        self._llm = llm
        self._clock = clock
        self._ids = id_generator
        self._optional_context = optional_context
        # max_chars 등 수치는 Source of Truth 미확정이므로 여기서 주입만 받는다.
        self._constraints = polish_constraints or ThemePolishConstraints()
        self._use_llm = use_llm

    def execute(self, command: GenerateYearlyPlanCommand) -> YearlyPlanResult:
        run = GenerationRun(
            run_id=self._ids.new_run_id(),
            started_at=self._clock.now(),
            catalog_id=command.catalog.catalog_id,
            catalog_version=command.catalog.catalog_version,
        )

        # ---------------------------------------------- 1. 선행조건 Gate
        gates.require_planning_setup_complete(command.planning_setup)
        gates.require_valid_age_configuration(command.classroom)

        # ------------------------------------------- 2. Catalog 해석·승인
        catalog = gates.require_resolved_catalog(
            self._themes.get_catalog(
                command.catalog.catalog_id, command.catalog.catalog_version
            ),
            command.catalog.catalog_id,
            command.catalog.catalog_version,
        )
        gates.require_human_approved_catalog(catalog)

        # -------------------------------------- 3. Optional Context (실패 무해)
        bundle = self._fetch_optional_context(command)
        fallbacks = tuple(
            f"{r.name}:{r.status.value}" for r in bundle.failures
        )
        run.optional_context = bundle.results
        run.fallbacks_used = fallbacks

        # ------------------------------------------------- 4. Rule 선택
        ages = command.classroom.ages
        selections: list[tuple[PeriodKey, ThemeCandidate, ThemeSelectionTrace]] = []
        previous_theme_id: str | None = None

        for period_key in academic_period_keys(command.school_year):
            selection = select_theme_for_period(
                catalog=catalog,
                period_key=period_key.value,
                calendar_month=period_key.calendar_month,
                ages=ages,
                # 순차 생성이므로 직후 월은 아직 확정되지 않았다. 직전 월만 인접으로 본다.
                adjacent_theme_ids=(
                    frozenset({previous_theme_id}) if previous_theme_id else frozenset()
                ),
            )
            selections.append((period_key, selection.candidate, selection.trace))
            previous_theme_id = selection.candidate.theme_id

        run.selection_traces = tuple(t for _, _, t in selections)

        # ------------------------------- 5. LLM 표현 다듬기 (요청 1회)
        events_by_period = _events_by_period(command.events)
        values = self._polish_all(selections, events_by_period, ages, command, run)

        month_periods: list[MonthPeriod] = []
        plan_id = PlanId(self._ids.new_plan_id())
        now = self._clock.now()

        for period_key, candidate, trace in selections:
            events = events_by_period.get(period_key.value, ())
            value = values[period_key.value]
            method = GenerationMethodDetail(
                method=(
                    GenerationMethod.RULE_LLM if self._use_llm
                    else GenerationMethod.RULE_ONLY
                ),
                rule_id=RULE_ID,
                rule_version=RULE_VERSION,
                selection_reason=trace.reason,
            )

            item = PlanItem(
                item_id=ItemId(self._ids.new_item_id()),
                semantic_key=SemanticKey.yearly_month_theme(period_key.calendar_month),
                value=value,
                generation=method,
                evidence=self._build_evidence(candidate, catalog, events),
                audit=AuditTrail(
                    [
                        AuditEvent(
                            event_type=AuditEventType.CREATED,
                            occurred_at=now,
                            plan_id=plan_id.value,
                            system_actor=SYSTEM_ACTOR_MARKER,
                            new_value=value,
                            new_method=method.method,
                        )
                    ]
                ),
            )
            month_periods.append(MonthPeriod(period_key=period_key, theme=item))

        plan = YearlyPlan(
            plan_id=plan_id,
            school_year=command.school_year,
            classroom_ref=command.classroom.classroom_ref,
            status=PlanStatus.DRAFT,
            month_periods=month_periods,
            classroom_ages=ages,
            audit=AuditTrail(
                [
                    AuditEvent(
                        event_type=AuditEventType.CREATED,
                        occurred_at=now,
                        plan_id=plan_id.value,
                        system_actor=SYSTEM_ACTOR_MARKER,
                    )
                ]
            ),
        )

        # ------------------------------------------------ 6. Validation
        validate_yearly_plan(
            plan,
            catalog=catalog,
            expected_school_year=command.school_year,
            expected_classroom_ref=command.classroom.classroom_ref,
        )

        # -------------------------------------------- 7. 저장 (마지막에만)
        self._plans.save(plan)
        return YearlyPlanResult(plan=plan, run=run)

    # ------------------------------------------------------------ 내부

    def _fetch_optional_context(
        self, command: GenerateYearlyPlanCommand
    ) -> OptionalContextBundle:
        """Optional Context 조회.

        CLAUDE.md §7: 외부 API 실패·timeout이 Core 생성을 실패시키지 않는다.
        Provider가 규약을 어기고 예외를 던져도 여기서 막는다.
        """
        if self._optional_context is None or not command.optional_context_requested:
            return OptionalContextBundle(results=())
        try:
            return self._optional_context.fetch(command.optional_context_requested)
        except Exception:  # noqa: BLE001 - Optional 의존성은 Core를 깨뜨릴 수 없다
            from .ports import OptionalContextResult, OptionalContextStatus

            return OptionalContextBundle(
                results=tuple(
                    OptionalContextResult(
                        name=name,
                        status=OptionalContextStatus.ERROR,
                        detail="provider raised",
                    )
                    for name in command.optional_context_requested
                )
            )

    def _polish_all(
        self,
        selections,
        events_by_period,
        ages: frozenset[int],
        command: GenerateYearlyPlanCommand,
        run: GenerationRun,
    ) -> dict[str, str]:
        """12개월 표현을 **요청 1회**로 받아 period_key → value map을 만든다.

        LLM을 쓰지 않는 모드면 Reference label을 그대로 사용한다.
        LLM 최종 실패·스키마 위반·reconcile 실패는 조용히 degrade하지 않고
        오류로 전파한다. 부분 성공을 저장하지 않는다(GENERATION_PARTIAL 미구현).
        """
        if not self._use_llm:
            return {pk.value: candidate.label for pk, candidate, _ in selections}

        items = tuple(
            ThemeBatchPolishItem(
                period_key=period_key.value,
                theme_id=candidate.theme_id,
                label=candidate.label,
                event_labels=tuple(
                    e.label for e in events_by_period.get(period_key.value, ())
                ),
            )
            for period_key, candidate, _trace in selections
        )

        request = ThemeBatchPolishRequest(
            task="polish_yearly_theme_labels",
            school_year=command.school_year,
            ages=tuple(sorted(ages)),
            items=items,
            constraints=self._constraints,
        )

        run.llm_invoked = True
        run.llm_call_count += 1
        run.llm_item_count += len(items)

        try:
            response = self._llm.polish_themes(request)
        except LLMConfigurationError as exc:
            # 인증·권한·요청 형식 오류. 재시도가 무의미한 설정 문제다.
            raise validation_failed(
                "llm_provider_configuration_is_invalid",
                FailureCategory.LLM_CONFIG_ERROR,
                str(exc),
            ) from exc
        except LLMUnavailableError as exc:
            # OD-N04: 재시도 후 실패를 잘못된 Plan 성공으로 처리하지 않는다.
            # Optional Context 실패와 달리 fallbacks_used에 기록하지 않는다.
            raise validation_failed(
                "llm_final_failure_is_not_a_successful_plan",
                FailureCategory.LLM_FAILURE,
                str(exc),
            ) from exc
        except ValueError as exc:
            raise validation_failed(
                "llm_output_must_satisfy_structured_output_schema",
                FailureCategory.LLM_OUTPUT_VALIDATION,
                str(exc),
            ) from exc

        try:
            return reconcile_batch(response, request.expected)
        except BatchReconcileError as exc:
            category = (
                FailureCategory.REQUIRED_VALUE_VALIDATION
                if exc.violation is BatchViolation.BLANK_VALUE
                else FailureCategory.LLM_OUTPUT_VALIDATION
            )
            raise validation_failed(
                exc.violation.value,
                category,
                exc.detail,
                period_key=exc.period_key,
            ) from exc

    def _build_evidence(
        self,
        candidate: ThemeCandidate,
        catalog: ThemeCatalog,
        events: tuple[EventInput, ...],
    ) -> list[EvidenceSource]:
        """방어 3: Evidence는 Rule 결과에서만 세팅하고 LLM 응답에서 읽지 않는다."""
        evidence = [
            EvidenceSource(
                source_type=EvidenceSourceType.THEME_REFERENCE,
                source_id=candidate.theme_id,
                source_version=catalog.catalog_version,
                display_name=candidate.label,
            )
        ]
        # 입력으로 명시된 행사만 Evidence로 붙인다. 없는 행사를 만들지 않는다.
        for event in events:
            evidence.append(
                EvidenceSource(
                    source_type=EvidenceSourceType.EVENT,
                    source_id=event.event_id,
                    display_name=event.label,
                    effective_date=event.starts_on,
                )
            )
        return evidence


def _events_by_period(events: tuple[EventInput, ...]) -> dict[str, tuple[EventInput, ...]]:
    grouped: dict[str, list[EventInput]] = {}
    for event in events:
        grouped.setdefault(event.period_key, []).append(event)
    return {k: tuple(v) for k, v in grouped.items()}
