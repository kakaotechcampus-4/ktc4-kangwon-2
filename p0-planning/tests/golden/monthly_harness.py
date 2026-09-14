"""Monthly Golden harness.

Yearly `harness.py`와 같은 역할이되 Monthly 전용이다. Yearly harness를
수정하지 않는다.

승인된 실제 데이터 파일(`monthly_template_a.json` / `safety_education_legal_v1.json`)을
로드해서 쓴다. 미승인 차단 case는 `approval_override`로 상태를 주입하며
파일을 수정하지 않는다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.monthly_repositories import (
    InMemoryMonthlyPlanRepository,
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.planning.application.dto import (
    CatalogSelector,
    ClassroomContext,
    DaycareContext,
    PlanningSetup,
)
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.application.monthly_dto import (
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
    SafetyRuleSelector,
)
from ssuksak.planning.domain.identifiers import (
    ActorId,
    ItemId,
    PlanId,
    SemanticKey,
)
from ssuksak.planning.domain.monthly_template import TemplateRef
from ssuksak.planning.domain.plan import MonthPeriod, PlanItem, PlanStatus, YearlyPlan
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditTrail,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
    SYSTEM_ACTOR_MARKER,
)
from ssuksak.planning.rules.periods import academic_period_keys

SUITE_PATH = Path(__file__).resolve().parent / "monthly_cases.json"
NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)


def load_suite() -> dict[str, Any]:
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))


SUITE = load_suite()
TEMPLATE_ID = SUITE["reference_fixtures"]["template"]["template_id"]
TEMPLATE_VERSION = SUITE["reference_fixtures"]["template"]["template_version"]
SAFETY_VERSION = SUITE["reference_fixtures"]["safety_legal_rule"]["legal_rule_version"]
CATALOG_ID = SUITE["reference_fixtures"]["parent_catalog"]["catalog_id"]
CATALOG_VERSION = SUITE["reference_fixtures"]["parent_catalog"]["catalog_version"]

PARENT = SUITE["fixtures"]["parent_confirmed"]
DAYCARE_REF = SUITE["fixtures"]["daycare"]["daycare_ref"]
CLASSROOM_REF = SUITE["fixtures"]["classroom_age4"]["classroom_ref"]


def case(case_id: str) -> dict[str, Any]:
    for c in SUITE["cases"]:
        if c["case_id"] == case_id:
            return c
    raise KeyError(case_id)


def build_parent_yearly(
    *,
    status: str = "CONFIRMED",
    classroom_ref: str | None = None,
    drop_month: str | None = None,
) -> YearlyPlan:
    """Golden fixture 상위 Yearly Plan."""
    classroom_ref = classroom_ref or PARENT["classroom_ref"]
    school_year = PARENT["school_year"]
    plan_id = PARENT["plan_id"]

    periods = []
    for index, pk in enumerate(academic_period_keys(school_year), start=1):
        if drop_month and pk.value == drop_month:
            continue
        periods.append(
            MonthPeriod(
                period_key=pk,
                theme=PlanItem(
                    item_id=ItemId(f"y_item_{index:02d}"),
                    semantic_key=SemanticKey.yearly_month_theme(pk.calendar_month),
                    value=f"{pk.calendar_month}월 주제",
                    generation=GenerationMethodDetail(
                        method=GenerationMethod.RULE_ONLY,
                        rule_id="yearly.theme.sample_derived_candidate_selection",
                        rule_version="v2",
                    ),
                    evidence=[
                        EvidenceSource(
                            source_type=EvidenceSourceType.THEME_REFERENCE,
                            source_id=f"yr_theme_{pk.calendar_month:02d}",
                            source_version=CATALOG_VERSION,
                            display_name=f"{pk.calendar_month}월 주제",
                        )
                    ],
                    audit=AuditTrail(
                        [
                            AuditEvent(
                                event_type=AuditEventType.CREATED,
                                occurred_at=NOW,
                                plan_id=plan_id,
                                system_actor=SYSTEM_ACTOR_MARKER,
                            )
                        ]
                    ),
                ),
            )
        )

    events = [
        AuditEvent(
            event_type=AuditEventType.CREATED,
            occurred_at=NOW,
            plan_id=plan_id,
            system_actor=SYSTEM_ACTOR_MARKER,
        )
    ]
    if status == "CONFIRMED":
        events.append(
            AuditEvent(
                event_type=AuditEventType.CONFIRMED,
                occurred_at=NOW,
                plan_id=plan_id,
                actor_id=ActorId(PARENT["confirmed_by"]),
            )
        )

    return YearlyPlan(
        plan_id=PlanId(plan_id),
        school_year=school_year,
        classroom_ref=classroom_ref,
        status=PlanStatus[status],
        month_periods=periods,
        classroom_ages=frozenset({4}),
        audit=AuditTrail(events),
    )


class RaisingOptionalContextProvider:
    """Optional Provider 규약 위반(예외)까지 견디는지 확인용."""

    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, requested):
        self.calls += 1
        raise RuntimeError("optional provider down")


class MonthlyHarness:
    def __init__(
        self,
        *,
        parent: YearlyPlan | None,
        template_approval: str | None = None,
        safety_approval: str | None = None,
        optional_context=None,
    ) -> None:
        self.yearly = InMemoryPlanRepository()
        if parent is not None:
            self.yearly.save(parent)
        self.monthly = InMemoryMonthlyPlanRepository()
        self.optional_provider = optional_context
        templates = JsonMonthlyTemplateRepository(
            approval_override=template_approval
        )
        clock = FixedClock(NOW, advance_seconds=1)
        self.edit = EditMonthlyPlanItem(
            monthly_plan_repository=self.monthly,
            template_repository=templates,
            clock=clock,
        )
        self.regenerate_item = RegenerateMonthlyPlanItem(
            monthly_plan_repository=self.monthly,
            template_repository=templates,
            clock=clock,
        )
        self.generate = GenerateMonthlyPlan(
            yearly_plan_repository=self.yearly,
            monthly_plan_repository=self.monthly,
            template_repository=JsonMonthlyTemplateRepository(
                approval_override=template_approval
            ),
            safety_rule_repository=JsonSafetyLegalRuleRepository(
                approval_override=safety_approval
            ),
            clock=FixedClock(NOW),
            id_generator=DeterministicIdGenerator(prefix="golden_m"),
            optional_context=optional_context,
        )

    @property
    def monthly_plan_persisted(self) -> bool:
        return self.monthly.save_count > 0


def make_harness(arrange: dict[str, Any]) -> MonthlyHarness:
    """case의 arrange 블록에서 harness를 조립한다."""
    parent_present = arrange.get("parent", "PRESENT") is not None
    parent = (
        build_parent_yearly(
            status=arrange.get("parent_status", "CONFIRMED"),
            classroom_ref=arrange.get("parent_classroom_ref"),
            drop_month=arrange.get("drop_parent_month"),
        )
        if parent_present
        else None
    )
    optional = (
        RaisingOptionalContextProvider()
        if arrange.get("optional_context") == "RAISES"
        else None
    )
    return MonthlyHarness(
        parent=parent,
        template_approval=arrange.get("template_approval"),
        safety_approval=arrange.get("safety_approval"),
        optional_context=optional,
    )


def build_command(arrange: dict[str, Any]) -> GenerateMonthlyPlanCommand:
    ages = frozenset(arrange.get("ages", SUITE["fixtures"]["classroom_age4"]["ages"]))
    return GenerateMonthlyPlanCommand(
        parent_yearly_plan_id=PARENT["plan_id"],
        school_year=PARENT["school_year"],
        target_month=arrange.get("target_month", "2026-09"),
        daycare=DaycareContext(daycare_ref=DAYCARE_REF),
        classroom=ClassroomContext(classroom_ref=CLASSROOM_REF, ages=ages),
        planning_setup=PlanningSetup(
            completed=arrange.get("planning_setup_completed", True),
            start_mode="CREATE_NEW",
        ),
        template_ref=TemplateRef(
            TEMPLATE_ID, arrange.get("template_version", TEMPLATE_VERSION)
        ),
        safety_rule=SafetyRuleSelector(
            arrange.get("safety_rule_version", SAFETY_VERSION)
        ),
        catalog=CatalogSelector(
            CATALOG_ID, arrange.get("catalog_version", CATALOG_VERSION)
        ),
        optional_context_requested=(
            {"trend": {}} if arrange.get("optional_context") == "RAISES" else {}
        ),
    )


TEACHER_ACTOR = ActorId("teacher_golden_edit_001")
"""Plan actor. reviewer identifier(OD-N10)와 다른 개념이므로 섞지 않는다."""


def build_address(arrange: dict[str, Any], target_month: str = "2026-09"):
    return MonthlyCellAddress(
        target_month=arrange.get("address_target_month", target_month),
        section_key=arrange["section_key"],
        week_id=arrange.get("week_id"),
        item_id=arrange.get("item_id"),
    )


def build_edit_command(plan_id: str, arrange: dict[str, Any], new_value: str | None = None):
    return EditMonthlyPlanItemCommand(
        plan_id=plan_id,
        address=build_address(arrange),
        new_value=arrange["new_value"] if new_value is None else new_value,
        actor_id=TEACHER_ACTOR,
    )


def build_regenerate_command(plan_id: str, arrange: dict[str, Any]):
    return RegenerateMonthlyPlanItemCommand(
        plan_id=plan_id,
        address=build_address(arrange),
        actor_id=TEACHER_ACTOR,
    )


def make_draft_plan(harness: "MonthlyHarness"):
    """Golden 기본 조건으로 DRAFT Monthly Plan을 하나 만든다."""
    return harness.generate.execute(build_command({})).plan


def cell_snapshot(plan) -> dict:
    """Cell 단위 불변성 비교용 스냅샷."""
    return {
        item.item_id.value: (
            item.value,
            item.cell_state,
            item.week_id.value if item.week_id else None,
            item.semantic_key.value,
            len(item.audit.events),
            item.generation.method,
            item.generation.rule_id,
            tuple((e.source_type, e.source_id, e.source_version) for e in item.evidence),
        )
        for item in plan.items
    }


def plan_level_snapshot(plan) -> tuple:
    return (
        plan.status,
        plan.parent_lineage,
        plan.template_ref,
        tuple(w.week_id.value for w in plan.week_periods),
        plan.constraint_assessments,
    )
