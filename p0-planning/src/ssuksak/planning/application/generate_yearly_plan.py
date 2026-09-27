"""Generate a complete DRAFT Yearly Plan from PR1 Rules and Reference."""

from __future__ import annotations

from ..domain.plan import PlanItem, PlanStatus
from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ..domain.yearly_plan import YearlyPeriod, YearlyPlan
from ..rules.academic_periods import academic_year_periods
from ..rules.yearly_reference_rules import (
    require_human_approved_catalog,
    require_resolved_catalog,
    validate_age_set,
)
from ..rules.yearly_theme_selection import (
    RULE_ID,
    RULE_VERSION,
    ThemeSelection,
    select_theme_for_period,
)
from .ports import (
    Clock,
    IdGenerator,
    OptionalContextProvider,
    PlanRepository,
    ThemeReferenceRepository,
)
from .yearly_dto import GenerateYearlyPlanCommand, GenerateYearlyPlanResult
from .yearly_ports import ThemeTextGenerator, ThemeTextRequest
from .yearly_support import fetch_optional_context, generate_theme_text

SYSTEM_ACTOR = "yearly_application"


class GenerateYearlyPlan:
    def __init__(
        self,
        *,
        theme_repository: ThemeReferenceRepository,
        plan_repository: PlanRepository[YearlyPlan],
        text_generator: ThemeTextGenerator,
        clock: Clock,
        id_generator: IdGenerator,
        optional_context: OptionalContextProvider | None = None,
    ) -> None:
        self._themes = theme_repository
        self._plans = plan_repository
        self._text = text_generator
        self._clock = clock
        self._ids = id_generator
        self._optional_context = optional_context

    def execute(
        self, command: GenerateYearlyPlanCommand
    ) -> GenerateYearlyPlanResult:
        periods = academic_year_periods(command.school_year)
        ages = validate_age_set(command.target_ages)
        catalog = require_resolved_catalog(
            self._themes.get_catalog(
                command.catalog.catalog_id,
                command.catalog.catalog_version,
            ),
            command.catalog.catalog_id,
            command.catalog.catalog_version,
        )
        require_human_approved_catalog(catalog)
        optional_context = fetch_optional_context(
            command.optional_context_names,
            self._optional_context,
        )

        selections: list[ThemeSelection] = []
        previous_theme_id: str | None = None
        for period in periods:
            selection = select_theme_for_period(
                catalog=catalog,
                period=period,
                ages=ages,
                adjacent_theme_ids=(
                    frozenset({previous_theme_id})
                    if previous_theme_id is not None
                    else frozenset()
                ),
            )
            selections.append(selection)
            previous_theme_id = selection.candidate.theme_id

        requests = tuple(
            ThemeTextRequest(
                period=period,
                theme_id=selection.candidate.theme_id,
                reference_label=selection.candidate.label,
                target_ages=tuple(sorted(ages)),
                optional_context=optional_context,
            )
            for period, selection in zip(periods, selections, strict=True)
        )
        text_results = generate_theme_text(self._text, requests)

        plan_id = self._ids.new_plan_id()
        now = self._clock.now()
        yearly_periods: list[YearlyPeriod] = []
        generation = GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
        )
        for period, selection, text in zip(
            periods, selections, text_results, strict=True
        ):
            item_id = self._ids.new_item_id()
            item = PlanItem(
                item_id=item_id,
                value=text.value,
                evidence=(
                    EvidenceSource(
                        source_type=EvidenceSourceType.THEME_REFERENCE,
                        source_id=selection.candidate.theme_id,
                        source_version=catalog.catalog_version,
                        display_name=selection.candidate.label,
                    ),
                ),
                generation=generation,
                audit=AuditHistory(
                    (
                        AuditEvent(
                            event_type=AuditEventType.CREATED,
                            occurred_at=now,
                            plan_id=plan_id,
                            item_id=item_id,
                            system_actor=SYSTEM_ACTOR,
                        ),
                    )
                ),
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
                        system_actor=SYSTEM_ACTOR,
                    ),
                )
            ),
        )
        self._plans.save(plan.plan_id, plan)
        return GenerateYearlyPlanResult(
            plan=plan,
            selection_traces=tuple(
                selection.trace for selection in selections
            ),
            optional_context=optional_context,
        )
