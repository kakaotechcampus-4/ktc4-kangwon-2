"""Official assembly point for Weekly use cases (the monthly_composition counterpart).

The backend supplies only what it owns: the parent / plan repositories, the LLM
provider, the clock and the id generator. The approved weekly Template, the
Activity Catalog, the Safety Rule and the context / planner pipeline are wired
here. Weekly has no TemplateProfile, so the exact weekly Template version is a
server constant (docs/weekly-plan-contract.md §13).

The weekly evidence classification (W3c) is always passed: the shipped file is
HUMAN_APPROVED and SHA-frozen (test_freeze). If it were broken or unapproved, loading
it fails generation instead of silently leaving indoor_play · group_activity ·
indoor_alternative empty.
"""

from __future__ import annotations

from pathlib import Path

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.json_activity_reference_repository import (
    JsonActivityReferenceRepository,
)
from ssuksak.adapters.monthly_composition import monthly_context_pipeline
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.adapters.weekly_evidence_classification_repository import (
    JsonWeeklyEvidenceClassificationRepository,
)
from ssuksak.planning.application.generate_weekly_plan import GenerateWeeklyPlan
from ssuksak.planning.application.weekly_lifecycle import (
    ConfirmWeeklyPlan,
    EditWeeklyPlanCell,
    RegenerateWeeklyPlanCell,
)
from ssuksak.planning.application.ports import MonthlyTemplateRepository
from ssuksak.planning.domain.monthly_template import TemplateRef
from ssuksak.planning.domain.weekly_plan import WEEKDAYS, WEEKDAYS_WITH_SATURDAY, OperatingDay
from ssuksak.planning.planner.weekly import WeeklyPlanner, WeeklyPlanningProvider

WEEKLY_TEMPLATE_REF = TemplateRef("ssuksak.weekly-template-a", "weekly-template-a-v0.1.0")
WEEKLY_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "templates" / "weekly_template_a_v0_1_0.json"
)


def weekly_operating_days(saturday_enabled: bool) -> tuple[OperatingDay, ...]:
    """The center setting snapshot copied into the plan (§3-5): MON-FRI, or MON-SAT."""
    return WEEKDAYS_WITH_SATURDAY if saturday_enabled else WEEKDAYS


def weekly_generation(
    *,
    parent_plan_repository,
    plan_repository,
    provider: WeeklyPlanningProvider,
    clock,
    id_generator,
    template_repository: MonthlyTemplateRepository | None = None,
) -> GenerateWeeklyPlan:
    """GenerateWeeklyPlan on the LLM planner path with the approved References.

    ``template_repository`` defaults to the approved weekly Template file; Core still
    refuses it unless it is human-approved and runtime-active (ADR-027).
    """
    return GenerateWeeklyPlan(
        parent_plan_repository=parent_plan_repository,
        plan_repository=plan_repository,
        # A missing file is the same reference-data problem as an unapproved Template:
        # Core finds no Template (503), instead of FileNotFoundError leaking as a 500.
        template_repository=template_repository
        or JsonMonthlyTemplateRepository(
            paths=(WEEKLY_TEMPLATE_PATH,) if WEEKLY_TEMPLATE_PATH.is_file() else ()
        ),
        safety_repository=JsonSafetyLegalRuleRepository(),
        clock=clock,
        id_generator=id_generator,
        activity_repository=JsonActivityReferenceRepository(),
        context_pipeline=monthly_context_pipeline(),
        planner=WeeklyPlanner(provider),
        evidence_repository=JsonInstitutionEvidenceRepository(),
        weekly_classification_repository=JsonWeeklyEvidenceClassificationRepository(),
    )


def weekly_edit(*, plan_repository, parent_plan_repository, clock) -> EditWeeklyPlanCell:
    """EditWeeklyPlanCell with the approved Activity Catalog for re-verification."""
    return EditWeeklyPlanCell(
        plan_repository=plan_repository,
        parent_plan_repository=parent_plan_repository,
        clock=clock,
        activity_repository=JsonActivityReferenceRepository(),
    )


def weekly_regeneration(
    *, plan_repository, parent_plan_repository, provider: WeeklyPlanningProvider, clock
) -> RegenerateWeeklyPlanCell:
    """RegenerateWeeklyPlanCell on the same References and range as weekly_generation."""
    return RegenerateWeeklyPlanCell(
        plan_repository=plan_repository,
        parent_plan_repository=parent_plan_repository,
        clock=clock,
        activity_repository=JsonActivityReferenceRepository(),
        context_pipeline=monthly_context_pipeline(),
        planner=WeeklyPlanner(provider),
        evidence_repository=JsonInstitutionEvidenceRepository(),
        weekly_classification_repository=JsonWeeklyEvidenceClassificationRepository(),
    )


def weekly_confirmation(*, plan_repository, parent_plan_repository, clock) -> ConfirmWeeklyPlan:
    """ConfirmWeeklyPlan with the approved Activity Catalog for re-verification."""
    return ConfirmWeeklyPlan(
        plan_repository=plan_repository,
        parent_plan_repository=parent_plan_repository,
        clock=clock,
        activity_repository=JsonActivityReferenceRepository(),
    )
