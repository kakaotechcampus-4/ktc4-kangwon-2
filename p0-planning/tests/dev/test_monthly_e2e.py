"""Monthly End-to-End 검증 (M2-E).

실제 Composition(`build_monthly_wiring`)으로 한 흐름을 끝까지 돌린다.

    Confirmed Yearly → Generate → Edit → Outdoor Regenerate → Confirm
    → CONFIRMED read-only → Weekly Gate

여기서 쓰는 Reference는 전부 실제 승인 artifact다.

    Theme Reference       data/themes/theme_reference_v0.json
    Monthly Template A    data/templates/monthly_template_a.json
    Safety Legal Rule     data/rules/safety_education_legal_v1.json
    Activity Reference    data/activities/activity_reference_v0_2_1.json (v0.2.1)

Network 0회 / LLM 0회다. 상위 Yearly fixture도 `use_llm=False` 경로로 만든다.
"""

from __future__ import annotations

import json
import socket

import pytest

from ssuksak.adapters.json_activity_reference_repository import (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    InMemoryActivityReferenceRepository,
    JsonActivityReferenceRepository,
)
from ssuksak.dev import monthly_formatting as fmt
from ssuksak.dev.monthly_wiring import (
    DEV_ACTOR,
    DEV_CLASSROOM_REF,
    MonthlyHarnessSession,
    build_monthly_wiring,
)
from ssuksak.planning.application.dto import CatalogSelector, ClassroomContext
from ssuksak.planning.application.monthly_dto import (
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.domain.activity_reference import (
    ActivationStatus,
    ActivityCandidate,
    ActivityCatalog,
    ActivityEvidence,
    ActivitySetting,
)
from ssuksak.planning.domain.constraint import (
    CellState,
    ConstraintKind,
    ConstraintVerification,
)
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.rules import gates
from ssuksak.planning.rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
)

OUTDOOR = "outdoor_play"
SAFETY = "safety_education"
THEME = "theme"
APPROVED_CATALOG_ID = "ssuksak.outdoor-activity-reference"
APPROVED_CATALOG_VERSION = "activity-reference-v0.2.1"


# ------------------------------------------------------------------ 공통 도우미


def generate(wiring, **over):
    base = dict(
        parent_yearly_plan_id=wiring.parent_yearly.plan_id.value,
        school_year=wiring.school_year,
        target_month=wiring.target_month,
        daycare=wiring.daycare,
        classroom=wiring.classroom,
        planning_setup=wiring.planning_setup,
        template_ref=wiring.template_ref,
        safety_rule=wiring.safety_rule,
        catalog=wiring.catalog,
        activity_catalog=wiring.activity_catalog,
    )
    base.update(over)
    return wiring.generate.execute(GenerateMonthlyPlanCommand(**base))


def address(section_key: str, week_id: str | None, target_month: str = "2026-09"):
    return MonthlyCellAddress(
        target_month=target_month, section_key=section_key, week_id=week_id
    )


def cells(plan, section_key: str):
    section = plan.section(section_key)
    return section.items if section else []


def activity_id_of(item) -> str | None:
    for source in item.evidence:
        if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE:
            return source.source_id
    return None


def cell_snapshot(plan) -> dict:
    out = {}
    for section in plan.sections:
        for item in section.items:
            out[(section.section_key, item.week_id.value if item.week_id else None)] = (
                item.value,
                item.cell_state,
                tuple(
                    (e.source_type, e.source_id, e.source_version) for e in item.evidence
                ),
                item.generation.method,
                item.generation.rule_id,
                item.generation.rule_version,
                len(item.audit.events),
            )
    return out


def plan_level_snapshot(plan) -> tuple:
    return (
        plan.status,
        plan.template_ref,
        plan.parent_lineage,
        plan.week_periods,
        plan.constraint_assessments,
        plan.activity_catalog,
        plan.school_year,
        plan.classroom_ref,
        plan.classroom_ages,
    )


@pytest.fixture()
def wiring():
    return build_monthly_wiring()


# ================================================== Scenario A — 2026-09 / 만4세


@pytest.fixture()
def scenario_a(wiring):
    result = generate(wiring)
    return wiring, result


def test_a_parent_yearly_is_confirmed_through_use_cases(scenario_a):
    wiring, _ = scenario_a
    assert wiring.parent_yearly.status is PlanStatus.CONFIRMED
    assert wiring.parent_yearly.audit.contains(AuditEventType.CONFIRMED)


def test_a_structure_is_five_weeks(scenario_a):
    _, result = scenario_a
    assert len(result.plan.week_periods) == 5
    assert result.run.week_period_count == 5


def test_a_theme_is_filled_from_parent_anchor(scenario_a):
    _, result = scenario_a
    theme = cells(result.plan, THEME)
    assert len(theme) == 1
    assert theme[0].cell_state is CellState.FILLED
    assert theme[0].value == result.plan.parent_lineage.parent_yearly_value
    kinds = {e.source_type for e in theme[0].evidence}
    assert EvidenceSourceType.PARENT_PLAN in kinds
    assert EvidenceSourceType.ACTIVITY_REFERENCE not in kinds


def test_a_outdoor_is_five_filled_activities(scenario_a):
    _, result = scenario_a
    items = cells(result.plan, OUTDOOR)
    assert len(items) == 5
    assert all(i.cell_state is CellState.FILLED for i in items)
    assert len({activity_id_of(i) for i in items}) == 5
    assert all(i.generation.rule_id == ACTIVITY_RULE_ID for i in items)
    assert all(i.generation.rule_version == ACTIVITY_RULE_VERSION for i in items)
    assert all(i.generation.method is GenerationMethod.RULE_ONLY for i in items)


def test_a_safety_is_five_empty_unresolved(scenario_a):
    _, result = scenario_a
    items = cells(result.plan, SAFETY)
    assert len(items) == 5
    assert all(i.cell_state is CellState.EMPTY_UNRESOLVED for i in items)
    assert all(i.evidence == [] for i in items)
    assert all(i.generation.rule_id != ACTIVITY_RULE_ID for i in items)


def test_a_uses_the_approved_activity_catalog(scenario_a):
    _, result = scenario_a
    assert result.run.activity_catalog_id == APPROVED_CATALOG_ID
    assert result.run.activity_catalog_version == APPROVED_CATALOG_VERSION
    assert result.plan.activity_catalog.catalog_version == APPROVED_CATALOG_VERSION
    assert all(
        i.evidence[0].source_version == APPROVED_CATALOG_VERSION
        for i in cells(result.plan, OUTDOOR)
    )


def test_a_constraint_assessment_is_unresolved_safety(scenario_a):
    _, result = scenario_a
    assessment = result.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert assessment is not None
    assert assessment.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    assert result.run.unresolved_requirements == (assessment,)


def test_a_no_llm_and_no_fallback(scenario_a):
    _, result = scenario_a
    assert result.run.llm_invoked is False
    assert result.run.llm_call_count == 0
    assert result.run.llm_item_count == 0
    assert result.run.fallbacks_used == ()


def test_a_counts_are_consistent(scenario_a):
    _, result = scenario_a
    run = result.plan, result.run
    assert result.run.generated_cell_count == 11
    assert result.run.filled_cell_count == 6  # theme 1 + outdoor 5
    assert result.run.empty_valid_cell_count == 0
    assert result.run.empty_unresolved_cell_count == 5
    assert result.run.activity_filled_cell_count == 5
    assert result.run.activity_unfilled_cell_count == 0
    assert len(result.run.activity_selection_traces) == 5
    assert run is not None


def test_a_no_network_socket_is_opened(monkeypatch):
    """생성 경로 전체에서 소켓을 열지 않는다."""

    def forbidden(*args, **kwargs):  # pragma: no cover - 열리면 실패한다
        raise AssertionError("Monthly 경로는 네트워크를 사용하지 않는다")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    w = build_monthly_wiring()
    result = generate(w)
    assert len(cells(result.plan, OUTDOOR)) == 5


# ================================================== Scenario B — 4주 달


def test_b_march_2026_has_four_weeks_all_filled():
    w = build_monthly_wiring(target_month="2026-03")
    result = generate(w)
    assert len(result.plan.week_periods) == 4
    items = cells(result.plan, OUTDOOR)
    assert len(items) == 4
    assert all(i.cell_state is CellState.FILLED for i in items)
    assert len({activity_id_of(i) for i in items}) == 4
    assert len(cells(result.plan, SAFETY)) == 4
    assert all(
        i.cell_state is CellState.EMPTY_UNRESOLVED for i in cells(result.plan, SAFETY)
    )
    assert result.run.activity_filled_cell_count == 4
    assert result.run.llm_call_count == 0


def test_b_week_count_is_not_hardcoded():
    five = build_monthly_wiring(target_month="2026-09")
    four = build_monthly_wiring(target_month="2026-03")
    assert len(generate(five).plan.week_periods) == 5
    assert len(generate(four).plan.week_periods) == 4


# ================================================== Scenario C — 혼합연령


@pytest.fixture()
def scenario_c():
    w = build_monthly_wiring(ages=frozenset({4, 5}))
    return w, generate(w)


def test_c_mixed_age_plan_keeps_one_plan_per_classroom(scenario_c):
    _, result = scenario_c
    assert result.plan.classroom_ages == frozenset({4, 5})
    assert result.plan.classroom_ref == DEV_CLASSROOM_REF
    assert result.plan.age_mode != "SINGLE"


def test_c_mixed_age_outdoor_is_filled(scenario_c):
    _, result = scenario_c
    items = cells(result.plan, OUTDOOR)
    assert len(items) == 5
    assert all(i.cell_state is CellState.FILLED for i in items)


def test_c_every_selected_activity_supports_all_classroom_ages(scenario_c):
    """혼합연령에서 일부 연령만 지원하는 활동을 강제로 넣지 않는다."""
    _, result = scenario_c
    catalog = JsonActivityReferenceRepository(
        DEFAULT_ACTIVITY_CATALOG_PATH
    ).get_catalog(APPROVED_CATALOG_ID, APPROVED_CATALOG_VERSION)
    for item in cells(result.plan, OUTDOOR):
        candidate = catalog.get(activity_id_of(item))
        assert candidate is not None
        assert candidate.supports_age_set(frozenset({4, 5})), candidate.activity_id


def test_c_single_age_and_mixed_age_candidate_pools_differ():
    catalog = JsonActivityReferenceRepository(
        DEFAULT_ACTIVITY_CATALOG_PATH
    ).get_catalog(APPROVED_CATALOG_ID, APPROVED_CATALOG_VERSION)
    single = catalog.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({4})
    )
    mixed = catalog.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({4, 5})
    )
    assert len(mixed) <= len(single)
    assert {c.activity_id for c in mixed} <= {c.activity_id for c in single}


# ================================================== Edit (§5)


def test_edit_changes_only_the_target_cell(scenario_a):
    wiring, result = scenario_a
    plan = result.plan
    before_cells = cell_snapshot(plan)
    before_plan = plan_level_snapshot(plan)
    target = cells(plan, OUTDOOR)[1]
    original_activity = activity_id_of(target)

    wiring.edit.execute(
        EditMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=address(OUTDOOR, "2026-09-W2"),
            new_value="교사가 정한 바깥놀이",
            actor_id=DEV_ACTOR,
        )
    )

    after = cell_snapshot(plan)
    assert [k for k in before_cells if before_cells[k] != after[k]] == [
        (OUTDOOR, "2026-09-W2")
    ]
    assert plan_level_snapshot(plan)[1:] == before_plan[1:]
    assert target.value == "교사가 정한 바깥놀이"
    assert target.cell_state is CellState.FILLED
    assert target.audit.events[-1].event_type is AuditEventType.TEACHER_EDITED
    # Provenance는 보존된다. 교사 수정이 근거를 지우지 않는다.
    assert activity_id_of(target) == original_activity
    assert target.generation.rule_id == ACTIVITY_RULE_ID
    assert plan.activity_catalog.catalog_version == APPROVED_CATALOG_VERSION


# ================================================== Outdoor Regenerate (§6)


def test_regenerate_after_edit_uses_pinned_catalog_and_preserves_contract(scenario_a):
    wiring, result = scenario_a
    plan = result.plan
    target = cells(plan, OUTDOOR)[1]
    original_activity = activity_id_of(target)

    wiring.edit.execute(
        EditMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=address(OUTDOOR, "2026-09-W2"),
            new_value="교사가 정한 바깥놀이",
            actor_id=DEV_ACTOR,
        )
    )
    before_cells = cell_snapshot(plan)
    before_plan = plan_level_snapshot(plan)

    outcome = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=address(OUTDOOR, "2026-09-W2"),
            actor_id=DEV_ACTOR,
        )
    ).activity_regeneration

    after = cell_snapshot(plan)
    assert [k for k in before_cells if before_cells[k] != after[k]] == [
        (OUTDOOR, "2026-09-W2")
    ]
    assert plan_level_snapshot(plan) == before_plan
    # M2-D 계약: previous는 보존된 Evidence, previous_value는 teacher edit 값
    assert outcome.previous_activity_id == original_activity
    assert outcome.previous_value == "교사가 정한 바깥놀이"
    assert outcome.catalog_id == APPROVED_CATALOG_ID
    assert outcome.catalog_version == APPROVED_CATALOG_VERSION
    assert outcome.rule_id == ACTIVITY_RULE_ID
    assert outcome.rule_version == ACTIVITY_RULE_VERSION
    assert outcome.trace.candidate_count > 0
    assert target.value == outcome.selected_value
    assert target.cell_state is CellState.FILLED
    assert target.generation.method is GenerationMethod.RULE_ONLY
    assert target.audit.events[-1].event_type is AuditEventType.REGENERATED
    assert target.audit.contains(AuditEventType.TEACHER_EDITED)


def test_regenerated_label_is_the_catalog_canonical_label(scenario_a):
    wiring, result = scenario_a
    outcome = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=result.plan.plan_id.value,
            address=address(OUTDOOR, "2026-09-W3"),
            actor_id=DEV_ACTOR,
        )
    ).activity_regeneration
    catalog = JsonActivityReferenceRepository(
        DEFAULT_ACTIVITY_CATALOG_PATH
    ).get_catalog(APPROVED_CATALOG_ID, APPROVED_CATALOG_VERSION)
    assert catalog.get(outcome.selected_activity_id).label == outcome.selected_value


def test_theme_regenerate_still_works_alongside_outdoor(scenario_a):
    wiring, result = scenario_a
    plan = result.plan
    theme = cells(plan, THEME)[0]

    regen = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=address(THEME, None),
            actor_id=DEV_ACTOR,
        )
    )

    assert regen.activity_regeneration is None
    assert theme.value == plan.parent_lineage.parent_yearly_value
    assert theme.generation.rule_id != ACTIVITY_RULE_ID
    assert theme.audit.events[-1].event_type is AuditEventType.REGENERATED


def test_safety_regenerate_stays_blocked(scenario_a):
    wiring, result = scenario_a
    before = cell_snapshot(result.plan)
    saves = wiring.monthly_plans.save_count
    with pytest.raises(PlanningError) as exc:
        wiring.regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=result.plan.plan_id.value,
                address=address(SAFETY, "2026-09-W1"),
                actor_id=DEV_ACTOR,
            )
        )
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert cell_snapshot(result.plan) == before
    assert wiring.monthly_plans.save_count == saves


# ================================================== Confirm (§7)


def test_confirm_transitions_and_preserves_everything(scenario_a):
    wiring, result = scenario_a
    plan = result.plan
    before_cells = cell_snapshot(plan)
    assessments = plan.constraint_assessments
    lineage = plan.activity_catalog

    confirmed = wiring.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=DEV_ACTOR)
    ).plan

    assert confirmed.status is PlanStatus.CONFIRMED
    assert cell_snapshot(confirmed) == before_cells
    assert confirmed.constraint_assessments == assessments
    assert confirmed.activity_catalog == lineage
    assert all(i.cell_state is CellState.FILLED for i in cells(confirmed, OUTDOOR))
    assert all(
        i.cell_state is CellState.EMPTY_UNRESOLVED for i in cells(confirmed, SAFETY)
    )
    assert confirmed.audit.contains(AuditEventType.CONFIRMED)


def test_confirm_does_not_mean_safety_legal_verification(scenario_a):
    wiring, result = scenario_a
    confirmed = wiring.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=result.plan.plan_id.value, actor_id=DEV_ACTOR)
    ).plan
    assessment = confirmed.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert assessment.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    assert "법정" in fmt.CONFIRM_SEMANTICS and "뜻하지 않습니다" in fmt.CONFIRM_SEMANTICS


# ================================================== CONFIRMED read-only (§8)


@pytest.mark.parametrize(
    "operation,section_key,week_id",
    [
        ("edit", THEME, None),
        ("edit", OUTDOOR, "2026-09-W2"),
        ("regenerate", THEME, None),
        ("regenerate", OUTDOOR, "2026-09-W2"),
    ],
)
def test_confirmed_plan_blocks_every_mutation(scenario_a, operation, section_key, week_id):
    wiring, result = scenario_a
    plan = result.plan
    wiring.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=DEV_ACTOR)
    )
    before_cells = cell_snapshot(plan)
    before_plan = plan_level_snapshot(plan)
    saves = wiring.monthly_plans.save_count

    with pytest.raises(PlanningError):
        if operation == "edit":
            wiring.edit.execute(
                EditMonthlyPlanItemCommand(
                    plan_id=plan.plan_id.value,
                    address=address(section_key, week_id),
                    new_value="확정 후 수정 시도",
                    actor_id=DEV_ACTOR,
                )
            )
        else:
            wiring.regenerate.execute(
                RegenerateMonthlyPlanItemCommand(
                    plan_id=plan.plan_id.value,
                    address=address(section_key, week_id),
                    actor_id=DEV_ACTOR,
                )
            )

    assert cell_snapshot(plan) == before_cells
    assert plan_level_snapshot(plan) == before_plan
    assert wiring.monthly_plans.save_count == saves


# ================================================== Weekly Gate (§9)


def test_weekly_gate_blocks_before_confirm_and_passes_after(scenario_a):
    wiring, result = scenario_a
    plan = result.plan

    with pytest.raises(PlanningError) as exc:
        gates.require_confirmed_parent_monthly(plan)
    assert exc.value.failure_category is FailureCategory.CONFIRMATION_GATE

    wiring.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=DEV_ACTOR)
    )
    gates.require_confirmed_parent_monthly(plan)


def test_weekly_gate_passes_even_with_unresolved_safety(scenario_a):
    wiring, result = scenario_a
    plan = result.plan
    wiring.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=DEV_ACTOR)
    )
    assert plan.unresolved_constraints  # 여전히 미해소다
    gates.require_confirmed_parent_monthly(plan)  # 그래도 Gate는 통과한다


# ================================================== Duplicate Generate (§10)


def test_duplicate_generate_is_still_blocked(scenario_a):
    wiring, _ = scenario_a
    stored = wiring.monthly_plans.stored_count
    saves = wiring.monthly_plans.save_count

    with pytest.raises(PlanningError) as exc:
        generate(wiring)

    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert (
        exc.value.violated_rule
        == "monthly_plan_is_unique_per_classroom_and_target_month"
    )
    assert wiring.monthly_plans.stored_count == stored
    assert wiring.monthly_plans.save_count == saves


def test_duplicate_gate_is_unchanged_without_activity_catalog(wiring):
    generate(wiring, activity_catalog=None)
    stored = wiring.monthly_plans.stored_count
    with pytest.raises(PlanningError) as exc:
        generate(wiring, activity_catalog=None)
    assert (
        exc.value.violated_rule
        == "monthly_plan_is_unique_per_classroom_and_target_month"
    )
    assert wiring.monthly_plans.stored_count == stored


# ================================================== Candidate 0 regression (§11)


def _zero_candidate_repo() -> InMemoryActivityReferenceRepository:
    """승인된 정상 Catalog이지만 9월 후보가 0인 fixture."""
    spring = ActivityCandidate(
        activity_id="act_spring_only",
        label="봄 산책",
        supported_ages=(4,),
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=(4,),
        placement_slots=(OUTDOOR,),
        setting=ActivitySetting.OUTDOOR,
        source_version=APPROVED_CATALOG_VERSION,
        evidence=(
            ActivityEvidence(
                origin_id="e2e.zero.origin",
                page=1,
                age_scope=(4,),
                observed_month=4,
                observed_label="봄 산책",
                observed_section=OUTDOOR,
                observed_source_label="바깥놀이",
            ),
        ),
    )
    return InMemoryActivityReferenceRepository(
        [
            ActivityCatalog(
                catalog_id=APPROVED_CATALOG_ID,
                catalog_version=APPROVED_CATALOG_VERSION,
                activation_status=ActivationStatus.HUMAN_APPROVED,
                activities=(spring,),
            )
        ]
    )


def test_generate_with_zero_candidates_yields_empty_valid():
    from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
    from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan

    w = build_monthly_wiring()
    generator = GenerateMonthlyPlan(
        yearly_plan_repository=w.yearly_plans,
        monthly_plan_repository=w.monthly_plans,
        template_repository=w.generate._templates,
        safety_rule_repository=w.generate._safety_rules,
        clock=FixedClock(w.generate._clock.now()),
        id_generator=DeterministicIdGenerator(prefix="e2ezero"),
        activity_reference_repository=_zero_candidate_repo(),
    )
    result = generator.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=w.parent_yearly.plan_id.value,
            school_year=w.school_year,
            target_month=w.target_month,
            daycare=w.daycare,
            classroom=w.classroom,
            planning_setup=w.planning_setup,
            template_ref=w.template_ref,
            safety_rule=w.safety_rule,
            catalog=w.catalog,
            activity_catalog=w.activity_catalog,
        )
    )
    items = cells(result.plan, OUTDOOR)
    assert all(i.cell_state is CellState.EMPTY_VALID for i in items)
    assert result.run.activity_unfilled_cell_count == 5
    assert result.run.activity_filled_cell_count == 0
    # Catalog lineage는 남는다. 후보 0은 Catalog 부재가 아니다.
    assert result.plan.activity_catalog.catalog_version == APPROVED_CATALOG_VERSION


def test_regenerate_with_zero_candidates_is_blocked_and_preserves_the_cell(scenario_a):
    """같은 후보 0이라도 Regenerate는 EMPTY_VALID로 지우지 않고 차단한다."""
    from ssuksak.adapters.deterministic import FixedClock
    from ssuksak.planning.application.regenerate_monthly_plan_item import (
        RegenerateMonthlyPlanItem,
    )

    wiring, result = scenario_a
    plan = result.plan
    before = cell_snapshot(plan)
    saves = wiring.monthly_plans.save_count

    regenerate = RegenerateMonthlyPlanItem(
        monthly_plan_repository=wiring.monthly_plans,
        template_repository=wiring.regenerate._templates,
        clock=FixedClock(wiring.regenerate._clock.now()),
        activity_reference_repository=_zero_candidate_repo(),
    )
    with pytest.raises(PlanningError) as exc:
        regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=address(OUTDOOR, "2026-09-W2"),
                actor_id=DEV_ACTOR,
            )
        )

    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert (
        exc.value.violated_rule
        == "regenerate_requires_at_least_one_eligible_candidate"
    )
    assert cell_snapshot(plan) == before
    assert all(i.cell_state is CellState.FILLED for i in cells(plan, OUTDOOR))
    assert wiring.monthly_plans.save_count == saves


# ================================================== Reference failure (§12)


@pytest.fixture()
def malformed_catalog_path(tmp_path):
    """승인 artifact를 복사해 알 수 없는 필드를 넣는다. 원본은 건드리지 않는다."""
    payload = json.loads(DEFAULT_ACTIVITY_CATALOG_PATH.read_text(encoding="utf-8"))
    payload["activities"][0]["unknown_future_field"] = "not in schema"
    target = tmp_path / "malformed_activity_reference.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


class BrokenRepository:
    def __init__(self):
        self.calls = 0

    def get_catalog(self, catalog_id, catalog_version):
        self.calls += 1
        raise RuntimeError("catalog storage is unavailable")


def _generate_with(wiring, repository, selector=None):
    from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
    from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan

    generator = GenerateMonthlyPlan(
        yearly_plan_repository=wiring.yearly_plans,
        monthly_plan_repository=wiring.monthly_plans,
        template_repository=wiring.generate._templates,
        safety_rule_repository=wiring.generate._safety_rules,
        clock=FixedClock(wiring.generate._clock.now()),
        id_generator=DeterministicIdGenerator(prefix="e2efail"),
        activity_reference_repository=repository,
    )
    return generator.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=wiring.parent_yearly.plan_id.value,
            school_year=wiring.school_year,
            target_month=wiring.target_month,
            daycare=wiring.daycare,
            classroom=wiring.classroom,
            planning_setup=wiring.planning_setup,
            template_ref=wiring.template_ref,
            safety_rule=wiring.safety_rule,
            catalog=wiring.catalog,
            activity_catalog=selector or wiring.activity_catalog,
        )
    )


def test_generate_fails_on_malformed_catalog_without_saving(
    wiring, malformed_catalog_path
):
    from ssuksak.adapters.json_activity_reference_repository import (
        ActivityReferenceSchemaError,
    )

    stored = wiring.monthly_plans.stored_count
    with pytest.raises(ActivityReferenceSchemaError):
        _generate_with(wiring, JsonActivityReferenceRepository(malformed_catalog_path))
    assert wiring.monthly_plans.stored_count == stored


def test_generate_fails_on_repository_error_without_saving(wiring):
    broken = BrokenRepository()
    stored = wiring.monthly_plans.stored_count
    with pytest.raises(RuntimeError):
        _generate_with(wiring, broken)
    assert broken.calls == 1
    assert wiring.monthly_plans.stored_count == stored


def test_generate_fails_on_missing_exact_catalog_without_saving(wiring):
    stored = wiring.monthly_plans.stored_count
    with pytest.raises(PlanningError) as exc:
        _generate_with(
            wiring,
            JsonActivityReferenceRepository(DEFAULT_ACTIVITY_CATALOG_PATH),
            selector=CatalogSelector(APPROVED_CATALOG_ID, "activity-reference-v9.9.9"),
        )
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert wiring.monthly_plans.stored_count == stored


def test_generate_fails_on_unapproved_catalog_without_saving(wiring):
    """v0.1.0은 PENDING_HUMAN_REVIEW다. 승인 Gate를 우회할 수 없다."""
    from ssuksak.adapters.json_activity_reference_repository import (
        LEGACY_ACTIVITY_CATALOG_PATH,
    )

    stored = wiring.monthly_plans.stored_count
    with pytest.raises(PlanningError) as exc:
        _generate_with(
            wiring,
            JsonActivityReferenceRepository(LEGACY_ACTIVITY_CATALOG_PATH),
            selector=CatalogSelector(APPROVED_CATALOG_ID, "activity-reference-v0.1.0"),
        )
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert wiring.monthly_plans.stored_count == stored


@pytest.mark.parametrize("kind", ["malformed", "broken", "missing_version"])
def test_regenerate_reference_failures_never_mutate(
    scenario_a, malformed_catalog_path, kind
):
    from ssuksak.adapters.deterministic import FixedClock
    from ssuksak.planning.application.regenerate_monthly_plan_item import (
        RegenerateMonthlyPlanItem,
    )

    wiring, result = scenario_a
    plan = result.plan
    before = cell_snapshot(plan)
    saves = wiring.monthly_plans.save_count

    repository = {
        "malformed": lambda: JsonActivityReferenceRepository(malformed_catalog_path),
        "broken": BrokenRepository,
        "missing_version": lambda: InMemoryActivityReferenceRepository([]),
    }[kind]()

    regenerate = RegenerateMonthlyPlanItem(
        monthly_plan_repository=wiring.monthly_plans,
        template_repository=wiring.regenerate._templates,
        clock=FixedClock(wiring.regenerate._clock.now()),
        activity_reference_repository=repository,
    )
    with pytest.raises(Exception):
        regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=address(OUTDOOR, "2026-09-W2"),
                actor_id=DEV_ACTOR,
            )
        )

    assert cell_snapshot(plan) == before
    assert wiring.monthly_plans.save_count == saves


def test_runtime_projection_still_rejects_unknown_fields(malformed_catalog_path):
    """Projection은 allowlist만 제거한다. 미지 필드는 여전히 실패해야 한다."""
    from ssuksak.adapters.json_activity_reference_repository import (
        ActivityReferenceSchemaError,
    )

    repo = JsonActivityReferenceRepository(malformed_catalog_path)
    with pytest.raises(ActivityReferenceSchemaError):
        repo.get_catalog(APPROVED_CATALOG_ID, APPROVED_CATALOG_VERSION)


# ================================================== Harness 출력 (§4, §14)


def test_plan_view_shows_activity_catalog_and_activity_ids(scenario_a):
    _, result = scenario_a
    text = fmt.format_monthly_plan(result.plan)
    assert APPROVED_CATALOG_VERSION in text
    assert "Activity Catalog" in text
    for item in cells(result.plan, OUTDOOR):
        assert activity_id_of(item) in text
        assert item.value in text
    assert "[EMPTY_UNRESOLVED]" in text


def test_generate_result_view_reports_activity_counts(scenario_a):
    _, result = scenario_a
    text = fmt.format_generate_result(result.plan, result.run)
    assert APPROVED_CATALOG_VERSION in text
    assert "FILLED 5개" in text


def test_selection_trace_view_explains_every_week(scenario_a):
    _, result = scenario_a
    text = fmt.format_activity_selection_traces(result.run)
    for trace in result.run.activity_selection_traces:
        assert trace.week_id in text
        assert trace.reason in text
        assert trace.selected_activity_id in text
    assert ACTIVITY_RULE_ID in text
    assert "hard filter가 아닙니다" in text


def test_selection_trace_view_handles_plans_without_activities(wiring):
    result = generate(wiring, activity_catalog=None)
    text = fmt.format_activity_selection_traces(result.run)
    assert "Activity Reference를 쓰지 않고" in text


def test_outdoor_regenerate_view_is_distinct_from_theme(scenario_a):
    wiring, result = scenario_a
    regen = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=result.plan.plan_id.value,
            address=address(OUTDOOR, "2026-09-W2"),
            actor_id=DEV_ACTOR,
        )
    )
    item = cells(result.plan, OUTDOOR)[1]
    text = fmt.format_activity_regenerate_result(regen.activity_regeneration, item)
    assert regen.activity_regeneration.selected_activity_id in text
    assert APPROVED_CATALOG_VERSION in text
    assert "자동 승격하지 않습니다" in text


def test_raw_json_dump_is_still_available(scenario_a):
    _, result = scenario_a
    payload = json.loads(fmt.format_raw_dump(result.plan, result.run))
    assert payload["plan"]["plan_id"] == result.plan.plan_id.value


def test_harness_menu_covers_the_final_monthly_contract():
    from ssuksak.dev import monthly_harness as cli

    menu = cli.MENU
    for keyword in (
        "Monthly Plan 보기",
        "Cell 수정",
        "Cell 재생성",
        "Provenance",
        "Constraint",
        "Generation Run",
        "Audit",
        "Confirm",
        "Duplicate",
        "Weekly Gate",
        "Raw JSON",
        "Activity Selection Trace",
    ):
        assert keyword in menu, keyword
    assert "outdoor_play" in menu  # 재생성 대상이 무엇인지 숨기지 않는다


def test_harness_session_round_trip(scenario_a):
    wiring, result = scenario_a
    session = MonthlyHarnessSession()
    session.adopt(result.plan)
    session.absorb_run(result.run)
    assert session.has_plan
    assert session.plan_id == result.plan.plan_id.value
    assert session.run.activity_catalog_version == APPROVED_CATALOG_VERSION
    assert wiring is not None
