"""Regenerate one DRAFT Yearly item without changing unrelated periods."""

from __future__ import annotations

from dataclasses import replace

from ..domain.provenance import (
    AuditEvent,
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodChange,
    GenerationMethodDetail,
    ValueChange,
)
from ..domain.yearly_plan import YearlyPlan
from ..rules.yearly_reference_rules import (
    require_human_approved_catalog,
    require_resolved_catalog,
)
from ..rules.yearly_theme_selection import (
    RULE_ID,
    RULE_VERSION,
    select_theme_for_period,
)
from .ports import Clock, PlanRepository, ThemeReferenceRepository
from .yearly_dto import (
    RegenerateYearlyPlanItemCommand,
    RegenerateYearlyPlanItemResult,
)
from .yearly_errors import YearlyApplicationError
from .yearly_ports import ThemeTextGenerator, ThemeTextRequest
from .yearly_support import (
    generate_theme_text,
    require_actor,
    require_item_id,
    require_plan,
)


class RegenerateYearlyPlanItem:
    def __init__(
        self,
        *,
        theme_repository: ThemeReferenceRepository,
        plan_repository: PlanRepository[YearlyPlan],
        text_generator: ThemeTextGenerator,
        clock: Clock,
    ) -> None:
        self._themes = theme_repository
        self._plans = plan_repository
        self._text = text_generator
        self._clock = clock

    def execute(
        self, command: RegenerateYearlyPlanItemCommand
    ) -> RegenerateYearlyPlanItemResult:
        plan = require_plan(self._plans, command.plan_id)
        plan.ensure_mutable("regenerate")
        item_id = require_item_id(command.item_id)
        actor_id = require_actor(command.actor_id)
        found = plan.find_item(item_id)
        if found is None:
            raise YearlyApplicationError(
                "yearly_item_not_found", f"Yearly item not found: {item_id}"
            )
        index, target = found

        catalog = require_resolved_catalog(
            self._themes.get_catalog(
                command.catalog.catalog_id,
                command.catalog.catalog_version,
            ),
            command.catalog.catalog_id,
            command.catalog.catalog_version,
        )
        require_human_approved_catalog(catalog)

        adjacent_theme_ids = frozenset(
            plan.periods[position].theme_id
            for position in (index - 1, index + 1)
            if 0 <= position < len(plan.periods)
        )
        selection = select_theme_for_period(
            catalog=catalog,
            period=target.period,
            ages=plan.target_ages,
            adjacent_theme_ids=adjacent_theme_ids,
            exclude_theme_id=target.theme_id,
        )
        request = ThemeTextRequest(
            period=target.period,
            theme_id=selection.candidate.theme_id,
            reference_label=selection.candidate.label,
            target_ages=tuple(sorted(plan.target_ages)),
        )
        text = generate_theme_text(self._text, (request,))[0]

        previous = target.theme
        generation = GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
        )
        evidence = (
            EvidenceSource(
                source_type=EvidenceSourceType.THEME_REFERENCE,
                source_id=selection.candidate.theme_id,
                source_version=catalog.catalog_version,
                display_name=selection.candidate.label,
            ),
            *(
                source
                for source in previous.evidence
                if source.source_type is not EvidenceSourceType.THEME_REFERENCE
            ),
        )
        event = AuditEvent(
            event_type=AuditEventType.REGENERATED,
            occurred_at=self._clock.now(),
            plan_id=plan.plan_id,
            item_id=previous.item_id,
            actor_id=actor_id,
            value_change=ValueChange(before=previous.value, after=text.value),
            generation_change=GenerationMethodChange(
                before=previous.generation,
                after=generation,
            ),
        )
        regenerated = replace(
            previous,
            value=text.value,
            evidence=evidence,
            generation=generation,
            audit=previous.audit.append(event),
        )
        updated = plan.replace_item(item_id, regenerated)
        self._plans.save(updated.plan_id, updated)
        return RegenerateYearlyPlanItemResult(
            plan=updated,
            selection_trace=selection.trace,
        )
