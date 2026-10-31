from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ssuksak.adapters.json_drill_topic_reference_repository import JsonDrillTopicReferenceRepository
from ssuksak.adapters.monthly_composition import (
    monthly_confirmation,
    monthly_edit,
    monthly_generation,
    monthly_regeneration,
)
from ssuksak.adapters.in_memory_template_profile_repository import (
    InMemoryTemplateProfileRepository,
)
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning.application.monthly_dto import (
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_constraint import CellState
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType
from ssuksak.planning.domain.monthly_template_profile import TemplateProfileRef
from ssuksak.planning.domain.year_month import YearMonth
from tests.application.test_monthly_application import (
    DRILL_TEMPLATE,
    DRILL_TOPICS,
    _profile,
)
from tests.finalization.harness import (
    ACTIVITY_CATALOG,
    EXTENDED_PROFILE,
    LLM_PROFILE,
    RULE_PROFILE,
    SAFETY_RULE,
    PlanningHarness,
)


def _generate(harness, parent, provider, *, month, profile):
    use_case = monthly_generation(
        parent_plan_repository=harness.yearly_plans,
        plan_repository=harness.monthly_plans,
        profile_repository=harness.profiles,
        template_repository=harness.generation_templates,
        provider=provider,
        clock=harness.clock,
        id_generator=harness.monthly_ids,
    )
    return use_case.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=parent.plan_id,
            target_month=month,
            daycare_ref="daycare_001",
            profile_ref=profile,
            safety_rule=SAFETY_RULE,
            generation_mode=MonthlyGenerationMode.LLM_PLANNER,
            activity_catalog=ACTIVITY_CATALOG,
        )
    ).plan


def test_request_aware_provider_follows_month_weeks_and_sections():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    provider = RequestAwareMonthlyLlm()

    plans = (
        _generate(harness, parent, provider, month=YearMonth(2026, 9), profile=LLM_PROFILE),
        _generate(harness, parent, provider, month=YearMonth(2027, 2), profile=LLM_PROFILE),
        _generate(harness, parent, provider, month=YearMonth(2026, 10), profile=EXTENDED_PROFILE),
    )

    assert len({len(plan.active_week_periods) for plan in plans}) > 1
    assert len({tuple(s.section_key for s in plan.sections) for plan in plans}) > 1
    for plan in plans:
        assert plan.status is PlanStatus.DRAFT
        assert plan.generation_mode is MonthlyGenerationMode.LLM_PLANNER
        # No placement selector: safety stays unresolved instead of invented content.
        safety = plan.section("safety_education").cells
        assert safety and all(c.cell_state is CellState.EMPTY_UNRESOLVED for c in safety)
        assert all(c.value == "" for c in safety)
    assert plans[2].section("goals").cells[0].cell_state is CellState.FILLED


def test_lifecycle_builders_edit_regenerate_and_confirm():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    plan = _generate(
        harness, parent, RequestAwareMonthlyLlm(), month=YearMonth(2026, 9), profile=LLM_PROFILE
    )
    focus = plan.section("focus").cells[0]
    outdoor = plan.section("outdoor_play").cells[1]
    actor = ActorId("teacher_001")

    edited = monthly_edit(plan_repository=harness.monthly_plans, clock=harness.clock).execute(
        EditMonthlyPlanItemCommand(plan.plan_id, outdoor.item_id, "Teacher value", actor)
    )
    assert edited.find_cell(outdoor.item_id)[3].value == "Teacher value"

    regenerated = monthly_regeneration(
        plan_repository=harness.monthly_plans,
        provider=RequestAwareMonthlyLlm(),
        clock=harness.clock,
    ).execute(RegenerateMonthlyPlanItemCommand(plan.plan_id, focus.item_id, actor)).plan
    cell = regenerated.find_cell(focus.item_id)[3]
    assert (cell.item_id, cell.week_id) == (focus.item_id, focus.week_id)
    assert cell.audit.events[-1].event_type is AuditEventType.REGENERATED

    confirmed = monthly_confirmation(
        plan_repository=harness.monthly_plans, clock=harness.clock
    ).execute(ConfirmMonthlyPlanCommand(plan.plan_id, actor))
    assert confirmed.status is PlanStatus.CONFIRMED
    # Re-confirming is idempotent: same plan, nothing new recorded.
    again = monthly_confirmation(
        plan_repository=harness.monthly_plans, clock=harness.clock
    ).execute(ConfirmMonthlyPlanCommand(plan.plan_id, actor))
    assert again == confirmed


def test_composed_generation_rejects_the_real_pending_template():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    requests = []

    class CountingLlm(RequestAwareMonthlyLlm):
        def generate_monthly(self, request):
            requests.append(request)
            return super().generate_monthly(request)

    provider = CountingLlm()
    # The real files. RULE_PROFILE sits on v0.1.1, still PENDING_HUMAN_REVIEW; LLM_PROFILE
    # sits on v0.2.1, approved 2026-10-20 (reviewer_pm_001, ADR-027 §5).
    harness.generation_templates = harness.templates

    with pytest.raises(MonthlyApplicationError) as exc:
        _generate(harness, parent, provider, month=YearMonth(2026, 9), profile=RULE_PROFILE)

    assert exc.value.code == "monthly_template_not_approved"
    assert harness.monthly_plans.save_count == 0
    assert requests == []


def test_composed_generation_wires_the_drill_reference():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    base = _profile(harness.templates, DRILL_TEMPLATE, TemplateProfileRef("monthly-profile-drill", "v1"))
    template = harness.templates.get_template(DRILL_TEMPLATE.template_id, DRILL_TEMPLATE.template_version)
    drill = replace(template.section("drill"), activated=True, display_label="Drill")
    harness.profiles = InMemoryTemplateProfileRepository(
        (replace(base, selected_optional_keys=(*base.selected_optional_keys, "drill"), sections=(*base.sections, drill)),)
    )
    use_case = monthly_generation(
        parent_plan_repository=harness.yearly_plans,
        plan_repository=harness.monthly_plans,
        profile_repository=harness.profiles,
        template_repository=harness.generation_templates,
        provider=RequestAwareMonthlyLlm(),
        clock=harness.clock,
        id_generator=harness.monthly_ids,
    )

    plan = use_case.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=parent.plan_id,
            target_month=YearMonth(2026, 9),
            daycare_ref="daycare_001",
            profile_ref=base.profile_ref,
            safety_rule=SAFETY_RULE,
            generation_mode=MonthlyGenerationMode.LLM_PLANNER,
            activity_catalog=ACTIVITY_CATALOG,
            drill_topics=DRILL_TOPICS,
        )
    ).plan

    assert plan.drill_candidates


def test_generation_without_drill_section_does_not_read_the_drill_file(monkeypatch):
    monkeypatch.setattr(
        "ssuksak.adapters.monthly_composition.JsonDrillTopicReferenceRepository",
        lambda: JsonDrillTopicReferenceRepository((Path("/nonexistent/drill.json"),)),
    )
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)

    plan = _generate(harness, parent, RequestAwareMonthlyLlm(), month=YearMonth(2026, 9), profile=LLM_PROFILE)

    assert plan.status is PlanStatus.DRAFT
