"""Monthly Dev 전용 Composition Root.

Yearly `wiring.py`를 수정하지 않는다. Yearly Harness는 frozen baseline이다.

기존 Adapter만 재사용해 Use Case를 조립한다. Harness를 위한 새 Persistence나
HTTP Adapter를 만들지 않는다.

    InMemoryPlanRepository         Parent Yearly
    InMemoryMonthlyPlanRepository  Monthly
    JsonMonthlyTemplateRepository  실제 승인 상태 그대로 (override 없음)
    JsonSafetyLegalRuleRepository  실제 승인 상태 그대로 (override 없음)
    JsonThemeReferenceRepository   실제 승인 상태 그대로 (override 없음)
    JsonActivityReferenceRepository 실제 승인 상태 그대로 (override 없음)
    FixedClock                     현재 시각 시드 + 1초 증가
    DeterministicIdGenerator       prefix="devm"
    OptionalContextProvider        None (P0 입력 없음)

**Monthly는 LLMPort를 연결하지 않는다.** M1 Monthly Use Case 4개 모두 LLM
dependency 자체가 없다.

version 값을 코드에 하드코딩하지 않고 승인된 데이터 파일에서 읽는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..adapters.deterministic import DeterministicIdGenerator, FixedClock
from ..adapters.in_memory_plan_repository import InMemoryPlanRepository
from ..adapters.json_activity_reference_repository import (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    JsonActivityReferenceRepository,
    production_activity_reference_repository,
)
from ..adapters.json_theme_reference_repository import (
    DEFAULT_CATALOG_PATH,
    JsonThemeReferenceRepository,
)
from ..adapters.monthly_repositories import (
    DEFAULT_SAFETY_RULE_PATH,
    DEFAULT_TEMPLATE_PATH,
    InMemoryMonthlyPlanRepository,
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ..planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ..planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ..planning.application.dto import (
    CatalogSelector,
    ClassroomContext,
    ConfirmYearlyPlanCommand,
    DaycareContext,
    GenerateYearlyPlanCommand,
    PlanningSetup,
)
from ..planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ..planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ..planning.application.generate_yearly_plan import GenerateYearlyPlan
from ..planning.application.monthly_dto import (
    MonthlyGenerationRun,
    SafetyRuleSelector,
)
from ..planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ..planning.domain.identifiers import ActorId
from ..planning.domain.monthly_plan import MonthlyPlan
from ..planning.domain.monthly_template import TemplateRef
from ..planning.domain.plan import YearlyPlan
from ..shared.llm.fake import FakeLLM

__all__ = [
    "DEV_ACTOR",
    "DEV_CLASSROOM_REF",
    "DEV_DAYCARE_REF",
    "DEFAULT_AGES",
    "DEFAULT_SCHOOL_YEAR",
    "DEFAULT_TARGET_MONTH",
    "MonthlyHarnessSession",
    "MonthlyWiring",
    "build_monthly_wiring",
    "prepare_confirmed_parent_yearly",
    "read_activity_catalog_selector",
    "read_safety_selector",
    "read_template_ref",
]

DEV_DAYCARE_REF = "dev_daycare_001"
DEV_CLASSROOM_REF = "dev_classroom_001"
DEFAULT_AGES: frozenset[int] = frozenset({4})
DEFAULT_SCHOOL_YEAR = 2026
DEFAULT_TARGET_MONTH = "2026-09"
"""canonical WeekPeriod가 5개이고 월 경계가 양쪽으로 넘어가 구조 검증에 가장 유용하다."""

DEV_ACTOR = ActorId("teacher_dev_001")
"""Plan actor. OD-N10의 reviewer identifier와는 다른 개념이다."""

_KST = timezone(timedelta(hours=9))


def read_template_ref(path: Path = DEFAULT_TEMPLATE_PATH) -> TemplateRef:
    """승인된 Template 파일에서 id/version을 읽는다. 코드에 하드코딩하지 않는다."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return TemplateRef(payload["template_id"], payload["template_version"])


def read_safety_selector(path: Path = DEFAULT_SAFETY_RULE_PATH) -> SafetyRuleSelector:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SafetyRuleSelector(payload["legal_rule_version"])


def read_catalog_selector(path: Path = DEFAULT_CATALOG_PATH) -> CatalogSelector:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CatalogSelector(payload["catalog_id"], payload["catalog_version"])


def read_activity_catalog_selector(
    path: Path = DEFAULT_ACTIVITY_CATALOG_PATH,
) -> CatalogSelector:
    """승인된 Activity Catalog 파일에서 id/version을 읽는다.

    Theme Catalog와 같은 방식이다. 승인 상태는 읽지 않는다. 활성 여부는
    Repository가 파일의 `review.domain_owner_approval`에서 파생한다.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CatalogSelector(payload["catalog_id"], payload["catalog_version"])


@dataclass(slots=True)
class MonthlyHarnessSession:
    """세션 상태 보관만 한다. 판단·검증·값 대입은 Use Case가 한다."""

    plan: MonthlyPlan | None = None
    run: MonthlyGenerationRun | None = None

    @property
    def plan_id(self) -> str | None:
        return self.plan.plan_id.value if self.plan is not None else None

    @property
    def has_plan(self) -> bool:
        return self.plan is not None

    def adopt(self, plan: MonthlyPlan) -> None:
        """Use Case가 반환한 Plan을 현재 Plan으로 채택한다."""
        self.plan = plan

    def absorb_run(self, run: MonthlyGenerationRun | None) -> None:
        if run is not None:
            self.run = run


@dataclass(slots=True)
class MonthlyWiring:
    """조립된 Monthly Use Case 묶음."""

    school_year: int
    target_month: str
    classroom: ClassroomContext
    daycare: DaycareContext
    planning_setup: PlanningSetup
    template_ref: TemplateRef
    safety_rule: SafetyRuleSelector
    catalog: CatalogSelector
    activity_catalog: CatalogSelector
    parent_yearly: YearlyPlan
    generate: GenerateMonthlyPlan
    edit: EditMonthlyPlanItem
    regenerate: RegenerateMonthlyPlanItem
    confirm: ConfirmMonthlyPlan
    yearly_plans: InMemoryPlanRepository
    monthly_plans: InMemoryMonthlyPlanRepository


def prepare_confirmed_parent_yearly(
    *,
    yearly_plans: InMemoryPlanRepository,
    themes: JsonThemeReferenceRepository,
    catalog: CatalogSelector,
    classroom: ClassroomContext,
    daycare: DaycareContext,
    planning_setup: PlanningSetup,
    school_year: int,
    clock,
    ids,
) -> YearlyPlan:
    """실제 Yearly Use Case 경로로 CONFIRMED Parent를 만든다.

    `plan.status`를 직접 CONFIRMED로 바꾸지 않는다.
    `GenerateYearlyPlan(use_llm=False)` → `ConfirmYearlyPlan` 경로를 그대로 쓰므로
    LLM도 네트워크도 필요하지 않다.
    """
    generate = GenerateYearlyPlan(
        theme_repository=themes,
        plan_repository=yearly_plans,
        llm=FakeLLM(),  # use_llm=False 경로라 호출되지 않는다
        clock=clock,
        id_generator=ids,
        optional_context=None,
        use_llm=False,
    )
    result = generate.execute(
        GenerateYearlyPlanCommand(
            school_year=school_year,
            daycare=daycare,
            classroom=classroom,
            planning_setup=planning_setup,
            catalog=catalog,
        )
    )
    confirm = ConfirmYearlyPlan(
        plan_repository=yearly_plans, clock=clock, theme_repository=themes
    )
    confirmed = confirm.execute(
        ConfirmYearlyPlanCommand(
            plan_id=result.plan.plan_id.value,
            actor_id=DEV_ACTOR,
            catalog=catalog,
        )
    )
    return confirmed.plan


def build_monthly_wiring(
    *,
    target_month: str = DEFAULT_TARGET_MONTH,
    school_year: int = DEFAULT_SCHOOL_YEAR,
    ages: frozenset[int] = DEFAULT_AGES,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    safety_path: Path = DEFAULT_SAFETY_RULE_PATH,
    activity_catalog_path: Path = DEFAULT_ACTIVITY_CATALOG_PATH,
) -> MonthlyWiring:
    """Monthly Use Case를 조립하고 CONFIRMED Parent Yearly를 준비한다."""
    themes = JsonThemeReferenceRepository(catalog_path)  # override 없음
    templates = JsonMonthlyTemplateRepository(template_path)  # override 없음
    safety_rules = JsonSafetyLegalRuleRepository(safety_path)  # override 없음
    # 승인 상태 override 없음. default 경로일 때만 과거 승인 Catalog(v0.2.0) 해소를
    # 함께 붙인다 — 기존 Plan이 pin한 version을 그대로 찾기 위해서다.
    activities = (
        production_activity_reference_repository()
        if activity_catalog_path == DEFAULT_ACTIVITY_CATALOG_PATH
        else JsonActivityReferenceRepository(activity_catalog_path)
    )

    catalog = read_catalog_selector(catalog_path)
    template_ref = read_template_ref(template_path)
    safety_rule = read_safety_selector(safety_path)
    activity_catalog = read_activity_catalog_selector(activity_catalog_path)

    classroom = ClassroomContext(classroom_ref=DEV_CLASSROOM_REF, ages=ages)
    daycare = DaycareContext(daycare_ref=DEV_DAYCARE_REF)
    planning_setup = PlanningSetup(completed=True, start_mode="CREATE_NEW")

    yearly_plans = InMemoryPlanRepository()
    monthly_plans = InMemoryMonthlyPlanRepository()
    clock = FixedClock(datetime.now(_KST).replace(microsecond=0), advance_seconds=1)
    ids = DeterministicIdGenerator(prefix="devm")

    parent = prepare_confirmed_parent_yearly(
        yearly_plans=yearly_plans,
        themes=themes,
        catalog=catalog,
        classroom=classroom,
        daycare=daycare,
        planning_setup=planning_setup,
        school_year=school_year,
        clock=clock,
        ids=ids,
    )

    return MonthlyWiring(
        school_year=school_year,
        target_month=target_month,
        classroom=classroom,
        daycare=daycare,
        planning_setup=planning_setup,
        template_ref=template_ref,
        safety_rule=safety_rule,
        catalog=catalog,
        activity_catalog=activity_catalog,
        parent_yearly=parent,
        generate=GenerateMonthlyPlan(
            yearly_plan_repository=yearly_plans,
            monthly_plan_repository=monthly_plans,
            template_repository=templates,
            safety_rule_repository=safety_rules,
            clock=clock,
            id_generator=ids,
            optional_context=None,  # P0 입력 없음
            activity_reference_repository=activities,
        ),
        edit=EditMonthlyPlanItem(
            monthly_plan_repository=monthly_plans,
            template_repository=templates,
            clock=clock,
        ),
        regenerate=RegenerateMonthlyPlanItem(
            monthly_plan_repository=monthly_plans,
            template_repository=templates,
            clock=clock,
            activity_reference_repository=activities,
        ),
        confirm=ConfirmMonthlyPlan(
            monthly_plan_repository=monthly_plans,
            template_repository=templates,
            safety_rule_repository=safety_rules,
            clock=clock,
        ),
        yearly_plans=yearly_plans,
        monthly_plans=monthly_plans,
    )
