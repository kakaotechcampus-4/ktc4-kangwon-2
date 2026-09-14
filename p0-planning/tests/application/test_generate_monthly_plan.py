"""GenerateMonthlyPlan Use Case 검증.

M1-B 범위: Gate → Reference → Optional → WeekPeriod → Template → Cell →
Constraint → Validation → 저장.

LLM은 호출하지 않는다. 빈 Cell을 GPT로 채우지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_dto import (
    GenerateMonthlyPlanCommand,
    SafetyRuleSelector,
)
from ssuksak.planning.domain.constraint import (
    CellState,
    ConstraintKind,
    ConstraintVerification,
)
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PeriodKey, PlanId, SemanticKey
from ssuksak.planning.domain.monthly_template import DisplayMode, TemplateRef
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

TEMPLATE_REF = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.1.0")
SAFETY_VERSION = "child-welfare-act-decree-annex6-2022-06-21"
CATALOG_ID = "ssuksak.yearly-theme-reference"
CATALOG_VERSION = "theme-reference-v0.1.2"
NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
CLASSROOM = "classroom_m1b"


def build_parent(
    *,
    school_year: int = 2026,
    classroom_ref: str = CLASSROOM,
    status: PlanStatus = PlanStatus.CONFIRMED,
    drop_month: str | None = None,
    theme_version: str = CATALOG_VERSION,
) -> YearlyPlan:
    periods = []
    for i, pk in enumerate(academic_period_keys(school_year), start=1):
        if drop_month and pk.value == drop_month:
            continue
        theme = PlanItem(
            item_id=ItemId(f"y_item_{i:02d}"),
            semantic_key=SemanticKey.yearly_month_theme(pk.calendar_month),
            value=f"{pk.calendar_month}월 주제",
            generation=GenerationMethodDetail(
                method=GenerationMethod.RULE_ONLY, rule_id="r", rule_version="v1"
            ),
            evidence=[
                EvidenceSource(
                    source_type=EvidenceSourceType.THEME_REFERENCE,
                    source_id=f"yr_theme_{pk.calendar_month:02d}",
                    source_version=theme_version,
                    display_name=f"{pk.calendar_month}월 주제",
                )
            ],
            audit=AuditTrail(
                [
                    AuditEvent(
                        event_type=AuditEventType.CREATED,
                        occurred_at=NOW,
                        plan_id="y_plan_001",
                        system_actor=SYSTEM_ACTOR_MARKER,
                    )
                ]
            ),
        )
        periods.append(MonthPeriod(period_key=pk, theme=theme))

    events = [
        AuditEvent(
            event_type=AuditEventType.CREATED,
            occurred_at=NOW,
            plan_id="y_plan_001",
            system_actor=SYSTEM_ACTOR_MARKER,
        )
    ]
    if status is PlanStatus.CONFIRMED:
        events.append(
            AuditEvent(
                event_type=AuditEventType.CONFIRMED,
                occurred_at=NOW,
                plan_id="y_plan_001",
                actor_id=ActorId("teacher_m1b_001"),
            )
        )
    return YearlyPlan(
        plan_id=PlanId("y_plan_001"),
        school_year=school_year,
        classroom_ref=classroom_ref,
        status=status,
        month_periods=periods,
        classroom_ages=frozenset({4}),
        audit=AuditTrail(events),
    )


class Wiring:
    def __init__(
        self,
        *,
        parent: YearlyPlan | None = None,
        template_approval: str | None = None,
        safety_approval: str | None = None,
        optional_context=None,
    ) -> None:
        self.yearly = InMemoryPlanRepository()
        if parent is not None:
            self.yearly.save(parent)
        self.monthly = InMemoryMonthlyPlanRepository()
        self.use_case = GenerateMonthlyPlan(
            yearly_plan_repository=self.yearly,
            monthly_plan_repository=self.monthly,
            template_repository=JsonMonthlyTemplateRepository(
                approval_override=template_approval
            ),
            safety_rule_repository=JsonSafetyLegalRuleRepository(
                approval_override=safety_approval
            ),
            clock=FixedClock(NOW),
            id_generator=DeterministicIdGenerator(prefix="m1b"),
            optional_context=optional_context,
        )


def command(**over) -> GenerateMonthlyPlanCommand:
    base = dict(
        parent_yearly_plan_id="y_plan_001",
        school_year=2026,
        target_month="2026-09",
        daycare=DaycareContext(daycare_ref="daycare_m1b"),
        classroom=ClassroomContext(classroom_ref=CLASSROOM, ages=frozenset({4})),
        planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
        template_ref=TEMPLATE_REF,
        safety_rule=SafetyRuleSelector(SAFETY_VERSION),
        catalog=CatalogSelector(CATALOG_ID, CATALOG_VERSION),
    )
    base.update(over)
    return GenerateMonthlyPlanCommand(**base)


def generate(**over):
    w = Wiring(parent=build_parent())
    return w, w.use_case.execute(command(**over))


# ------------------------------------------------------------ 성공 경로


def test_generates_draft_monthly_plan():
    w, result = generate()
    plan = result.plan
    assert plan.status is PlanStatus.DRAFT
    assert plan.target_month == PeriodKey("2026-09")
    assert plan.school_year == 2026
    assert plan.classroom_ref == CLASSROOM
    assert plan.daycare_ref == "daycare_m1b"
    assert plan.template_ref == TEMPLATE_REF
    assert w.monthly.save_count == 1


def test_september_2026_structure_is_eleven_content_cells():
    _, result = generate()
    plan = result.plan
    assert len(plan.week_periods) == 5
    counts = {s.section_key: len(s.items) for s in plan.sections}
    assert counts == {
        "theme": 1,
        "week_axis": 0,
        "outdoor_play": 5,
        "safety_education": 5,
    }
    assert len(plan.items) == 11


def test_march_2026_structure_is_nine_content_cells():
    _, result = generate(target_month="2026-03")
    plan = result.plan
    assert len(plan.week_periods) == 4
    counts = {s.section_key: len(s.items) for s in plan.sections}
    assert counts == {
        "theme": 1,
        "week_axis": 0,
        "outdoor_play": 4,
        "safety_education": 4,
    }
    assert len(plan.items) == 9


def test_active_sections_match_template_and_inactive_are_absent():
    _, result = generate()
    keys = [s.section_key for s in result.plan.sections]
    assert keys == ["theme", "week_axis", "outdoor_play", "safety_education"]
    for inactive in (
        "focus", "goals", "habits", "emergency_response",
        "drill", "indoor_alternative", "special_program", "event_schedule",
    ):
        assert result.plan.section(inactive) is None


def test_display_modes_come_from_template():
    _, result = generate()
    by_key = {s.section_key: s for s in result.plan.sections}
    assert by_key["theme"].display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
    assert by_key["outdoor_play"].display_mode is DisplayMode.WEEKLY_CELLS
    assert by_key["safety_education"].display_mode is DisplayMode.WEEKLY_CELLS
    assert by_key["week_axis"].display_mode is None


def test_week_periods_are_canonical_and_not_clipped():
    _, result = generate()
    weeks = result.plan.week_periods
    assert [w.week_id.value for w in weeks] == [
        f"2026-09-W{i}" for i in range(1, 6)
    ]
    assert weeks[0].start_date.month == 8
    assert weeks[-1].end_date.month == 10


# ---------------------------------------------------------- Cell 상태


def test_theme_cell_is_filled_from_parent_anchor():
    _, result = generate()
    section = result.plan.section("theme")
    cell = section.items[0]
    assert cell.cell_state is CellState.FILLED
    assert cell.value == "9월 주제"
    assert cell.is_merged_cell
    assert cell.generation.method is GenerationMethod.RULE_ONLY


def test_theme_cell_has_parent_and_theme_reference_evidence():
    _, result = generate()
    cell = result.plan.section("theme").items[0]
    parent_ev = cell.evidence_of_type(EvidenceSourceType.PARENT_PLAN)
    theme_ev = cell.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    assert parent_ev and parent_ev[0].source_id == "y_plan_001"
    assert theme_ev and theme_ev[0].source_id == "yr_theme_09"
    assert theme_ev[0].source_version == CATALOG_VERSION


def test_outdoor_cells_are_empty_valid_without_content_evidence():
    _, result = generate()
    for cell in result.plan.section("outdoor_play").items:
        assert cell.value == ""
        assert cell.cell_state is CellState.EMPTY_VALID
        assert cell.evidence == []
        assert cell.week_id is not None


def test_safety_cells_are_empty_unresolved_without_content_evidence():
    _, result = generate()
    for cell in result.plan.section("safety_education").items:
        assert cell.value == ""
        assert cell.cell_state is CellState.EMPTY_UNRESOLVED
        assert cell.evidence == []


def test_week_axis_has_no_items():
    _, result = generate()
    assert result.plan.section("week_axis").items == []


def test_every_cell_address_resolves_and_item_ids_are_unique():
    _, result = generate()
    plan = result.plan
    ids = [i.item_id.value for i in plan.items]
    assert len(ids) == len(set(ids))
    for section in plan.sections:
        for item in section.items:
            wid = item.week_id.value if item.week_id else None
            assert plan.find_cell(section_key=section.section_key, week_id=wid)


# -------------------------------------------------------- lineage


def test_parent_lineage_is_snapshotted():
    _, result = generate()
    lin = result.plan.parent_lineage
    assert lin.parent_yearly_plan_id == "y_plan_001"
    assert lin.parent_yearly_period_key == "2026-09"
    assert lin.parent_yearly_theme_id == "yr_theme_09"
    assert lin.parent_yearly_value == "9월 주제"
    assert lin.reference_catalog_id == CATALOG_ID
    assert lin.reference_version == CATALOG_VERSION
    assert lin.confirmed_by == "teacher_m1b_001"
    assert lin.confirmed_at == NOW


def test_catalog_version_must_match_parent_evidence():
    w = Wiring(parent=build_parent())
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(
            command(catalog=CatalogSelector(CATALOG_ID, "theme-reference-v9.9.9"))
        )
    assert exc.value.violated_rule == (
        "requested_catalog_version_must_match_parent_theme_evidence"
    )
    assert w.monthly.save_count == 0


# ------------------------------------------------------ Constraint


def test_safety_constraint_is_recorded_as_unresolved():
    _, result = generate()
    assessment = result.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert assessment is not None
    assert (
        assessment.verification
        is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    )
    assert assessment.rule_version == SAFETY_VERSION
    assert assessment.required_source_kinds == (
        "INSTITUTION_ANNUAL_SAFETY_PLAN",
        "TEACHER_INPUT",
    )
    assert assessment.affected_section_keys == ("safety_education",)
    assert assessment.detail


def test_unresolved_constraint_does_not_claim_legal_compliance():
    _, result = generate()
    detail = result.plan.constraint(
        ConstraintKind.STATUTORY_SAFETY_EDUCATION
    ).detail
    assert "충족" not in detail or "판정이 아니라" in detail
    assert "미검증" in detail


def test_generation_succeeds_despite_unresolved_constraint():
    w, result = generate()
    assert result.plan.status is PlanStatus.DRAFT
    assert w.monthly.save_count == 1
    assert len(result.plan.unresolved_constraints) == 1


# --------------------------------------------------- GenerationRun


def test_generation_run_counts():
    _, result = generate()
    run = result.run
    assert run.template_id == TEMPLATE_REF.template_id
    assert run.template_version == TEMPLATE_REF.template_version
    assert run.safety_legal_rule_version == SAFETY_VERSION
    assert run.week_period_count == 5
    assert run.generated_cell_count == 11
    assert run.filled_cell_count == 1
    assert run.empty_valid_cell_count == 5
    assert run.empty_unresolved_cell_count == 5


def test_generation_run_reports_no_llm_call():
    _, result = generate()
    assert result.run.llm_invoked is False
    assert result.run.llm_call_count == 0
    assert result.run.llm_item_count == 0


def test_unresolved_requirement_is_not_a_fallback():
    _, result = generate()
    run = result.run
    assert run.fallbacks_used == ()
    assert run.used_fallback is False
    assert run.has_unresolved_requirement is True
    assert len(run.unresolved_requirements) == 1


def test_use_case_has_no_llm_dependency():
    """M1-B는 LLMPort를 주입받지 않는다."""
    import inspect

    params = inspect.signature(GenerateMonthlyPlan.__init__).parameters
    assert "llm" not in params
    src = inspect.getsource(GenerateMonthlyPlan)
    assert "polish" not in src


# ------------------------------------------------------------- Gate


def test_parent_missing_is_blocked():
    w = Wiring(parent=None)
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command())
    assert exc.value.failure_category is FailureCategory.CONFIRMATION_GATE
    assert exc.value.violated_rule == (
        "monthly_generation_requires_confirmed_yearly_plan"
    )
    assert w.monthly.save_count == 0


def test_parent_draft_is_blocked():
    w = Wiring(parent=build_parent(status=PlanStatus.DRAFT))
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command())
    assert exc.value.violated_rule == (
        "monthly_generation_requires_confirmed_yearly_plan"
    )
    assert w.monthly.save_count == 0


def test_wrong_classroom_is_blocked():
    w = Wiring(parent=build_parent(classroom_ref="other_classroom"))
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command())
    assert exc.value.violated_rule == (
        "monthly_plan_owner_must_match_parent_yearly_classroom"
    )
    assert w.monthly.save_count == 0


@pytest.mark.parametrize("bad_month", ["2026-02", "2027-03", "2025-09"])
def test_target_month_outside_academic_year_is_blocked(bad_month: str):
    w = Wiring(parent=build_parent())
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command(target_month=bad_month))
    assert exc.value.violated_rule == (
        "target_month_must_belong_to_parent_academic_year"
    )
    assert w.monthly.save_count == 0


def test_missing_parent_month_period_is_blocked():
    w = Wiring(parent=build_parent(drop_month="2026-09"))
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command())
    assert exc.value.violated_rule == "parent_yearly_month_period_must_exist"
    assert w.monthly.save_count == 0


def test_unapproved_template_is_blocked():
    w = Wiring(parent=build_parent(), template_approval="PENDING_HUMAN_REVIEW")
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command())
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert exc.value.violated_rule == (
        "only_human_approved_template_instance_is_eligible"
    )
    assert w.monthly.save_count == 0


def test_unapproved_safety_rule_is_blocked():
    w = Wiring(parent=build_parent(), safety_approval="PENDING_HUMAN_REVIEW")
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command())
    assert exc.value.violated_rule == (
        "only_human_approved_safety_legal_rule_is_eligible"
    )
    assert w.monthly.save_count == 0


def test_unknown_template_version_is_blocked():
    w = Wiring(parent=build_parent())
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(
            command(template_ref=TemplateRef("ssuksak.monthly-template-a", "v9.9.9"))
        )
    assert exc.value.violated_rule == "template_id_and_version_must_resolve_exactly"
    assert w.monthly.save_count == 0


def test_unknown_safety_rule_version_is_blocked():
    w = Wiring(parent=build_parent())
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command(safety_rule=SafetyRuleSelector("nope-v0")))
    assert exc.value.violated_rule == (
        "safety_legal_rule_version_must_resolve_exactly"
    )
    assert w.monthly.save_count == 0


def test_incomplete_planning_setup_is_blocked():
    w = Wiring(parent=build_parent())
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command(planning_setup=PlanningSetup(completed=False)))
    assert exc.value.violated_rule == "planning_initial_setup_must_be_complete"
    assert w.monthly.save_count == 0


def test_invalid_age_configuration_is_blocked():
    w = Wiring(parent=build_parent())
    with pytest.raises(PlanningError):
        w.use_case.execute(
            command(
                classroom=ClassroomContext(
                    classroom_ref=CLASSROOM, ages=frozenset({2})
                )
            )
        )
    assert w.monthly.save_count == 0


# ------------------------------------------------- Optional Context


class _RaisingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, requested):
        self.calls += 1
        raise RuntimeError("provider down")


def test_optional_context_failure_does_not_block_generation():
    provider = _RaisingProvider()
    w = Wiring(parent=build_parent(), optional_context=provider)
    result = w.use_case.execute(command(optional_context_requested={"trend": {}}))
    assert result.plan.status is PlanStatus.DRAFT
    assert w.monthly.save_count == 1
    assert result.run.used_fallback is True
    assert result.run.fallbacks_used[0].startswith("trend:")


def test_optional_provider_is_not_called_when_gate_fails():
    """필수 Gate 실패인데 외부 Provider부터 호출하지 않는다."""
    provider = _RaisingProvider()
    w = Wiring(parent=build_parent(status=PlanStatus.DRAFT), optional_context=provider)
    with pytest.raises(PlanningError):
        w.use_case.execute(command(optional_context_requested={"trend": {}}))
    assert provider.calls == 0
    assert w.monthly.save_count == 0


def test_no_optional_context_requested_means_no_call():
    provider = _RaisingProvider()
    w = Wiring(parent=build_parent(), optional_context=provider)
    result = w.use_case.execute(command())
    assert provider.calls == 0
    assert result.run.fallbacks_used == ()


# --------------------------------------------------------- Repository


def test_find_monthly_locates_saved_plan():
    w, result = generate()
    found = w.monthly.find_monthly(CLASSROOM, "2026-09")
    assert found is not None and found.plan_id == result.plan.plan_id
    assert w.monthly.find_monthly(CLASSROOM, "2026-10") is None


def test_monthly_repository_does_not_share_yearly_storage():
    w, result = generate()
    assert w.yearly.get(result.plan.plan_id.value) is None
    assert w.monthly.get("y_plan_001") is None
