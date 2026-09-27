from __future__ import annotations

from datetime import UTC, datetime
import json

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.deterministic_theme_text_generator import (
    DeterministicThemeTextGenerator,
)
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.institution_evidence_repository import (
    JsonInstitutionEvidenceRepository,
)
from ssuksak.adapters.json_activity_reference_repository import (
    JsonActivityReferenceRepository,
)
from ssuksak.adapters.json_theme_reference_repository import (
    JsonThemeReferenceRepository,
)
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.edit_yearly_plan_item import EditYearlyPlanItem
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.generate_yearly_plan import GenerateYearlyPlan
from ssuksak.planning.application.monthly_dto import (
    ActivityCatalogSelector,
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    RegenerateMonthlyPlanItemCommand,
    SafetyRuleSelector,
)
from ssuksak.planning.application.monthly_support import MonthlyContextPipeline
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.application.regenerate_yearly_plan_item import (
    RegenerateYearlyPlanItem,
)
from ssuksak.planning.application.yearly_dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
    RegenerateYearlyPlanItemCommand,
)
from ssuksak.planning.context.builder import ContextPacketBuilder
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from ssuksak.planning.domain.monthly_template import TemplateRef
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.domain.yearly_plan import YearlyPlan
from ssuksak.planning.planner.cell_service import MonthlyCellPlanner
from ssuksak.planning.planner.contracts import (
    MONTHLY_MODEL,
    MonthlyCellPlanningRequest,
    MonthlyPlanningRequest,
    RawLlmResponse,
)
from ssuksak.planning.planner.service import MonthlyPlanner

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
TEACHER = ActorId("teacher_001")
TARGET_MONTH = YearMonth(2026, 9)
THEME_CATALOG = CatalogSelector(
    "ssuksak.yearly-theme-reference", "theme-reference-v0.1.2"
)
ACTIVITY_CATALOG = ActivityCatalogSelector(
    "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
)
RULE_TEMPLATE = TemplateRef(
    "ssuksak.monthly-template-a", "monthly-template-a-v0.1.0"
)
LLM_TEMPLATE = TemplateRef(
    "ssuksak.monthly-template-a", "monthly-template-a-v0.2.0"
)
SAFETY_RULE = SafetyRuleSelector(
    "child-welfare-act-decree-annex6-2022-06-21"
)

_EVIDENCE_REPOSITORY = JsonInstitutionEvidenceRepository()


class RequestAwareMonthlyLlm:
    """Network-free provider whose output is derived only from each request."""

    def __init__(self) -> None:
        self.monthly_requests: list[MonthlyPlanningRequest] = []
        self.cell_requests: list[MonthlyCellPlanningRequest] = []

    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        self.monthly_requests.append(request)
        grounding_ref = sorted(request.valid_grounding_refs)[0]
        first_reference = request.reference_labels[0]
        weeks = []
        for index, week_id in enumerate(request.expected_week_ids, start=1):
            if index == 1:
                activity = {
                    "value": first_reference[1],
                    "origin": "REFERENCE",
                    "reference_activity_id": first_reference[0],
                    "grounding_refs": [],
                }
            else:
                activity = {
                    "value": f"Context-based outdoor activity {index}",
                    "origin": "LLM_SYNTHESIZED",
                    "reference_activity_id": None,
                    "grounding_refs": [grounding_ref],
                }
            weeks.append(
                {
                    "week_id": week_id,
                    "experience": f"Context-based weekly focus {index}",
                    "activity": activity,
                }
            )
        payload = {
            "target_month": request.target_month,
            "theme_id": request.expected_theme_id,
            "month_flow_rationale": "The monthly flow follows the supplied context.",
            "weeks": weeks,
        }
        return RawLlmResponse(
            json.dumps(payload, ensure_ascii=False),
            MONTHLY_MODEL,
            "deterministic-monthly",
        )

    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse:
        self.cell_requests.append(request)
        grounding_ref = sorted(request.valid_grounding_refs)[0]
        is_focus = request.target_section_key == "focus"
        payload = {
            "target_month": request.target_month,
            "target_week_id": request.target_week_id,
            "target_section_key": request.target_section_key,
            "value": f"Regenerated {request.target_section_key} value",
            "activity_origin": None if is_focus else "LLM_SYNTHESIZED",
            "reference_activity_id": None,
            "grounding_refs": [grounding_ref],
        }
        return RawLlmResponse(
            json.dumps(payload, ensure_ascii=False),
            MONTHLY_MODEL,
            "deterministic-cell",
        )


class PlanningHarness:
    def __init__(self) -> None:
        self.themes = JsonThemeReferenceRepository()
        self.yearly_plans: InMemoryPlanRepository[YearlyPlan] = (
            InMemoryPlanRepository()
        )
        self.monthly_plans: InMemoryPlanRepository[MonthlyPlan] = (
            InMemoryPlanRepository()
        )
        self.text = DeterministicThemeTextGenerator()
        self.clock = FixedClock(NOW)
        self.yearly_ids = DeterministicIdGenerator("yearly-final")
        self.monthly_ids = DeterministicIdGenerator("monthly-final")
        self.templates = JsonMonthlyTemplateRepository()
        self.safety = JsonSafetyLegalRuleRepository()
        self.activities = JsonActivityReferenceRepository()
        self.context = MonthlyContextPipeline(
            evidence_repository=_EVIDENCE_REPOSITORY,
            context_builder=ContextPacketBuilder(),
        )
        self.provider = RequestAwareMonthlyLlm()

    def generate_yearly(self):
        return GenerateYearlyPlan(
            theme_repository=self.themes,
            plan_repository=self.yearly_plans,
            text_generator=self.text,
            clock=self.clock,
            id_generator=self.yearly_ids,
        ).execute(
            GenerateYearlyPlanCommand(
                school_year=2026,
                classroom_ref="classroom_001",
                target_ages=frozenset({3, 4}),
                catalog=THEME_CATALOG,
            )
        )

    def edit_yearly(self, plan: YearlyPlan, *, index: int, value: str) -> YearlyPlan:
        return EditYearlyPlanItem(
            plan_repository=self.yearly_plans, clock=self.clock
        ).execute(
            EditYearlyPlanItemCommand(
                plan.plan_id,
                plan.periods[index].theme.item_id,
                value,
                TEACHER,
            )
        )

    def regenerate_yearly(self, plan: YearlyPlan, *, index: int):
        return RegenerateYearlyPlanItem(
            theme_repository=self.themes,
            plan_repository=self.yearly_plans,
            text_generator=self.text,
            clock=self.clock,
        ).execute(
            RegenerateYearlyPlanItemCommand(
                plan.plan_id,
                plan.periods[index].theme.item_id,
                TEACHER,
                THEME_CATALOG,
            )
        )

    def confirm_yearly(self, plan: YearlyPlan) -> YearlyPlan:
        return ConfirmYearlyPlan(
            plan_repository=self.yearly_plans, clock=self.clock
        ).execute(ConfirmYearlyPlanCommand(plan.plan_id, TEACHER))

    def generate_monthly(
        self,
        parent: YearlyPlan,
        mode: MonthlyGenerationMode,
    ):
        template = (
            RULE_TEMPLATE
            if mode is MonthlyGenerationMode.RULE_ONLY
            else LLM_TEMPLATE
        )
        planner = (
            None
            if mode is MonthlyGenerationMode.RULE_ONLY
            else MonthlyPlanner(self.provider)
        )
        return GenerateMonthlyPlan(
            parent_plan_repository=self.yearly_plans,
            plan_repository=self.monthly_plans,
            template_repository=self.templates,
            safety_repository=self.safety,
            activity_repository=self.activities,
            clock=self.clock,
            id_generator=self.monthly_ids,
            context_pipeline=self.context,
            planner=planner,
        ).execute(
            GenerateMonthlyPlanCommand(
                parent_yearly_plan_id=parent.plan_id,
                target_month=TARGET_MONTH,
                daycare_ref="daycare_001",
                template_ref=template,
                safety_rule=SAFETY_RULE,
                generation_mode=mode,
                activity_catalog=ACTIVITY_CATALOG,
            )
        )

    def edit_monthly(self, plan: MonthlyPlan, *, item_id, value: str) -> MonthlyPlan:
        return EditMonthlyPlanItem(
            plan_repository=self.monthly_plans, clock=self.clock
        ).execute(EditMonthlyPlanItemCommand(plan.plan_id, item_id, value, TEACHER))

    def regenerate_monthly(self, plan: MonthlyPlan, *, item_id):
        return RegenerateMonthlyPlanItem(
            plan_repository=self.monthly_plans,
            clock=self.clock,
            activity_repository=self.activities,
            context_pipeline=self.context,
            cell_planner=MonthlyCellPlanner(self.provider),
        ).execute(
            RegenerateMonthlyPlanItemCommand(plan.plan_id, item_id, TEACHER)
        )

    def confirm_monthly(self, plan: MonthlyPlan) -> MonthlyPlan:
        return ConfirmMonthlyPlan(
            plan_repository=self.monthly_plans, clock=self.clock
        ).execute(ConfirmMonthlyPlanCommand(plan.plan_id, TEACHER))
