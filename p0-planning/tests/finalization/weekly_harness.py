"""Weekly test harness: the monthly PlanningHarness plus a confirmed parent and weekly generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ssuksak.adapters.deterministic import DeterministicIdGenerator
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.adapters.weekly_evidence_classification_repository import (
    JsonWeeklyEvidenceClassificationRepository,
)
from ssuksak.planning.application.generate_weekly_plan import (
    GenerateWeeklyPlan,
    GenerateWeeklyPlanCommand,
    GenerateWeeklyPlanResult,
)
from ssuksak.planning.application.weekly_lifecycle import (
    RegenerateWeeklyPlanCell,
    RegenerateWeeklyPlanCellCommand,
)
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from ssuksak.planning.domain.monthly_template import TemplateRef
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.weekly_plan import WEEKDAYS, OperatingDay, WeeklyPlan
from ssuksak.planning.planner.weekly import WeeklyPlanner

from .harness import _EVIDENCE_REPOSITORY, ACTIVITY_CATALOG, SAFETY_RULE, TEACHER, ApprovedTemplates, PlanningHarness
from .snapshots import _audit, _evidence, _generation

WEEKLY_TEMPLATE = TemplateRef("ssuksak.weekly-template-a", "weekly-template-a-v0.1.0")
WEEKLY_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "data" / "templates" / "weekly_template_a_v0_1_0.json"
WEEKLY_DAY_TEMPLATE = TemplateRef("ssuksak.weekly-template-a", "weekly-template-a-v0.2.0")  # ADR-051
WEEK = WeekId("2026-09-W2")


class WeeklyHarness(PlanningHarness):
    def __init__(self) -> None:
        super().__init__()
        self.weekly_plans: InMemoryPlanRepository[WeeklyPlan] = InMemoryPlanRepository()
        self.weekly_ids = DeterministicIdGenerator("weekly-final")
        self.weekly_templates = JsonMonthlyTemplateRepository(
            paths=(WEEKLY_TEMPLATE_PATH, WEEKLY_TEMPLATE_PATH.with_name("weekly_template_a_v0_2_0.json"))
        )
        # Generation sees the approved fixture; the real file stays PENDING (ADR-027).
        self.weekly_generation_templates = ApprovedTemplates(self.weekly_templates)
        self.weekly_provider = RequestAwareWeeklyLlm()
        self.weekly_classification = JsonWeeklyEvidenceClassificationRepository()

    def monthly_parent(
        self, *, confirm: bool = True, mode: MonthlyGenerationMode = MonthlyGenerationMode.RULE_ONLY
    ) -> MonthlyPlan:
        yearly = self.confirm_yearly(self.generate_yearly().plan)
        monthly = self.generate_monthly(yearly, mode).plan
        return self.confirm_monthly(monthly) if confirm else monthly

    def generate_weekly(
        self,
        parent: MonthlyPlan,
        *,
        week_id: WeekId = WEEK,
        operating_days: tuple[OperatingDay, ...] = WEEKDAYS,
        mode: MonthlyGenerationMode = MonthlyGenerationMode.RULE_ONLY,
        templates=None,
        optional_context=None,
        optional_context_names: tuple[str, ...] = (),
        provider=None,
        weekly_classification: bool = True,
        template_ref: TemplateRef = WEEKLY_TEMPLATE,
    ) -> GenerateWeeklyPlanResult:
        return GenerateWeeklyPlan(
            parent_plan_repository=self.monthly_plans,
            plan_repository=self.weekly_plans,
            template_repository=templates or self.weekly_generation_templates,
            safety_repository=self.safety,
            clock=self.clock,
            id_generator=self.weekly_ids,
            activity_repository=self.activities,
            optional_context=optional_context,
            context_pipeline=self.context,
            planner=WeeklyPlanner(provider or self.weekly_provider),
            evidence_repository=_EVIDENCE_REPOSITORY,
            weekly_classification_repository=self.weekly_classification if weekly_classification else None,
        ).execute(
            GenerateWeeklyPlanCommand(
                parent_monthly_plan_id=parent.plan_id,
                week_id=week_id,
                operating_days=operating_days,
                template_ref=template_ref,
                safety_rule=SAFETY_RULE,
                generation_mode=mode,
                activity_catalog=ACTIVITY_CATALOG,
                optional_context_names=optional_context_names,
            )
        )


    def regenerate_weekly(
        self,
        plan: WeeklyPlan,
        *,
        section_key: str,
        provider=None,
        actor=TEACHER,
        weekly_classification: bool = True,
        day: OperatingDay | None = None,
    ) -> WeeklyPlan:
        return RegenerateWeeklyPlanCell(
            plan_repository=self.weekly_plans,
            parent_plan_repository=self.monthly_plans,
            clock=self.clock,
            activity_repository=self.activities,
            context_pipeline=self.context,
            planner=WeeklyPlanner(provider or self.weekly_provider),
            evidence_repository=_EVIDENCE_REPOSITORY,
            weekly_classification_repository=self.weekly_classification if weekly_classification else None,
        ).execute(RegenerateWeeklyPlanCellCommand(plan.plan_id, plan.cell(section_key, day).item_id, actor))


def _cell(cell) -> dict[str, Any]:
    return {
        "section_key": cell.section_key,
        "value": cell.value,
        "state": cell.cell_state.value,
        "generation": _generation(cell.generation),
        "evidence": [_evidence(source) for source in cell.evidence],
        "parent_snapshots": [
            [item.parent_item_id.value, item.snapshot_value] for item in cell.parent_snapshots
        ],
        "audit": _audit(cell.audit),
    }


def weekly_cell_regeneration_snapshot(before: WeeklyPlan, after: WeeklyPlan, section_key: str, request) -> dict[str, Any]:
    """W4b Application contract for one regenerated Cell (not the model's wording)."""
    target = before.cell(section_key).item_id
    siblings = [(b, a) for b, a in zip(before.cells, after.cells) if b.item_id != target]
    return {
        "schema": "weekly-cell-regeneration-golden-v1",
        "generation_mode": after.generation_mode.value,
        "section": section_key,
        "item_id_preserved": after.cell(section_key).item_id == target,
        "request": {
            "prompt_version": request.prompt_version,
            "targets": [t.section_key for t in request.targets],
            "allowed_grounding_refs": len(request.targets[0].allowed_grounding_refs),
        },
        "before": _cell(before.cell(section_key)),
        "after": _cell(after.cell(section_key)),
        "siblings": {"count": len(siblings), "unchanged": all(b == a for b, a in siblings)},
        "findings": [
            [f.code, f.finding_kind.value]
            for f in after.verification_report.findings
            if f.location.section_key == section_key
        ],
    }


def weekly_snapshot(result: GenerateWeeklyPlanResult) -> dict[str, Any]:
    plan = result.plan
    report = plan.verification_report
    return {
        "status": plan.status.value,
        "school_year": plan.school_year,
        "week_id": plan.week_id.value,
        "week_period": [plan.week_period.start_date.isoformat(), plan.week_period.end_date.isoformat()],
        "operating_days": [day.value for day in plan.operating_days],
        "classroom_ref": plan.classroom_ref,
        "target_ages": sorted(plan.target_ages),
        "generation_mode": plan.generation_mode.value,
        "template": str(plan.template_snapshot.base_template_ref),
        "parent_lineage": {
            "parent_plan_id": plan.parent_lineage.parent_plan_id.value,
            "confirmed_by": plan.parent_lineage.confirmed_by.value,
        },
        "constraints": [
            [item.constraint.code, item.verification.value] for item in plan.constraint_assessments
        ],
        "activity_catalog": (
            None if plan.activity_catalog_ref is None
            else f"{plan.activity_catalog_ref.catalog_id}/{plan.activity_catalog_ref.catalog_version}"
        ),
        "plan_audit": _audit(plan.audit),
        "cells": [_cell(cell) for cell in plan.cells],
        "verification": {
            "executed_rules": [f"{rule.rule_id}/{rule.rule_version}" for rule in report.executed_rules],
            "findings": [[f.location.section_key, f.code, f.finding_kind.value] for f in report.findings],
        },
        "activity_selection": (
            None if result.activity_selection is None
            else {
                "selected": result.activity_selection.selected_activity_id,
                "reasons": list(result.activity_selection.reason_codes),
            }
        ),
        "optional_context": [[item.name, item.status.value] for item in result.optional_context],
    }
