"""Official assembly point for Monthly use cases.

Callers outside Planning Core (the backend) supply only what they own: the
plan / profile repositories, the LLM provider, the clock and the id generator.
Generation, cell edit, cell regeneration and confirmation are all wired here.
The approved Reference repositories and the context / planner pipeline are
wired here, so callers never import Core internals one by one.

This module lives in ``adapters`` because it wires concrete JSON Reference
adapters; ``planning`` must not import ``adapters``.
"""

from __future__ import annotations

from ssuksak.adapters.evidence_classification_repository import (
    JsonEvidenceClassificationRepository,
)
from ssuksak.adapters.institution_evidence_repository import (
    JsonInstitutionEvidenceRepository,
)
from ssuksak.adapters.json_activity_reference_repository import (
    JsonActivityReferenceRepository,
)
from ssuksak.adapters.monthly_reference_repositories import (
    JsonSafetyLegalRuleRepository,
    JsonSafetyPlacementPolicyRepository,
)
from ssuksak.adapters.safety_evidence_classification_repository import (
    JsonSafetyEvidenceClassificationRepository,
)
from ssuksak.adapters.safety_reference_quality_repository import (
    JsonSafetyReferenceQualityRepository,
)
from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_support import MonthlyContextPipeline
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.context.builder import ContextPacketBuilder
from ssuksak.planning.planner.cell_service import MonthlyCellPlanner
from ssuksak.planning.planner.ports import (
    MonthlyCellPlanningProvider,
    MonthlyPlanningProvider,
)
from ssuksak.planning.planner.service import MonthlyPlanner


def monthly_context_pipeline() -> MonthlyContextPipeline:
    """Context pipeline over the approved Evidence / classification / quality data."""
    return MonthlyContextPipeline(
        evidence_repository=JsonInstitutionEvidenceRepository(),
        classification_repository=JsonEvidenceClassificationRepository(),
        context_builder=ContextPacketBuilder(),
        safety_classification_repository=JsonSafetyEvidenceClassificationRepository(),
        safety_quality_repository=JsonSafetyReferenceQualityRepository(),
    )


def monthly_generation(
    *,
    parent_plan_repository,
    plan_repository,
    profile_repository,
    provider: MonthlyPlanningProvider,
    clock,
    id_generator,
) -> GenerateMonthlyPlan:
    """GenerateMonthlyPlan on the LLM planner path with the approved References.

    Generation rules are unchanged: this only wires the existing use case.
    """
    return GenerateMonthlyPlan(
        parent_plan_repository=parent_plan_repository,
        plan_repository=plan_repository,
        profile_repository=profile_repository,
        safety_repository=JsonSafetyLegalRuleRepository(),
        activity_repository=JsonActivityReferenceRepository(),
        clock=clock,
        id_generator=id_generator,
        context_pipeline=monthly_context_pipeline(),
        planner=MonthlyPlanner(provider),
        safety_placement_repository=JsonSafetyPlacementPolicyRepository(),
    )


def monthly_edit(*, plan_repository, clock) -> EditMonthlyPlanItem:
    """EditMonthlyPlanItem with the approved Activity Catalog for re-verification."""
    return EditMonthlyPlanItem(
        plan_repository=plan_repository,
        clock=clock,
        activity_repository=JsonActivityReferenceRepository(),
    )


def monthly_regeneration(
    *, plan_repository, provider: MonthlyCellPlanningProvider, clock
) -> RegenerateMonthlyPlanItem:
    """RegenerateMonthlyPlanItem on the approved References and the cell planner."""
    return RegenerateMonthlyPlanItem(
        plan_repository=plan_repository,
        clock=clock,
        activity_repository=JsonActivityReferenceRepository(),
        context_pipeline=monthly_context_pipeline(),
        cell_planner=MonthlyCellPlanner(provider),
    )


def monthly_confirmation(*, plan_repository, clock) -> ConfirmMonthlyPlan:
    """ConfirmMonthlyPlan with the approved Activity Catalog for re-verification."""
    return ConfirmMonthlyPlan(
        plan_repository=plan_repository,
        clock=clock,
        activity_repository=JsonActivityReferenceRepository(),
    )
