"""Monthly Golden Set 실행.

`monthly_cases.json`의 case를 그대로 실행하고 기대값과 대조한다.
문장 exact match는 검증하지 않는다(assertion_policy).

Monthly M1 Core 전 범위(Gate / Generate / Edit / Regenerate / Confirm)를 담는다.
"""

from __future__ import annotations

from typing import Any

import pytest

from ssuksak.planning.domain.constraint import CellState, ConstraintKind
from ssuksak.planning.domain.errors import FailureCategory, Outcome, PlanningError
from ssuksak.planning.domain.monthly_template import SectionRole
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods
from ssuksak.planning.domain.identifiers import PeriodKey

from . import monthly_harness as H

SUITE = H.SUITE
CASES = {c["case_id"]: c for c in SUITE["cases"]}
# Duplicate Gate는 기존 Plan을 미리 만들어야 하므로 전용 테스트가 담당한다.
GATE_CASES = [
    c["case_id"]
    for c in SUITE["cases"]
    if c["classification"] == "GATE_FAILURE"
    and "existing_monthly" not in c["arrange"]
]
SUCCESS_CASES = [
    c["case_id"]
    for c in SUITE["cases"]
    if c["classification"] == "SUCCESS"
    and c["operation"] == "GenerateMonthlyPlan"
]


# ------------------------------------------------------------- meta


def test_suite_metadata_is_consistent():
    assert SUITE["suite_id"] == "ssuksak.monthly-golden"
    assert SUITE["contract_stage"] == "M1-D"
    assert SUITE["assertion_policy"]["exact_sentence_match"] is False
    ids = [c["case_id"] for c in SUITE["cases"]]
    assert len(ids) == len(set(ids)), "case_id가 중복된다"


def test_reference_fixture_states_match_repository():
    """Golden이 참조하는 데이터의 승인 상태가 실제와 일치해야 한다."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    tpl = json.loads(
        (root / "data" / "templates" / "monthly_template_a.json").read_text(
            encoding="utf-8"
        )
    )
    saf = json.loads(
        (root / "data" / "rules" / "safety_education_legal_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert tpl["review"]["domain_owner_approval"] == (
        SUITE["reference_fixtures"]["template"]["current_review_state"]
    )
    assert saf["review"]["domain_owner_approval"] == (
        SUITE["reference_fixtures"]["safety_legal_rule"]["current_review_state"]
    )
    assert tpl["template_version"] == (
        SUITE["reference_fixtures"]["template"]["template_version"]
    )
    assert saf["legal_rule_version"] == (
        SUITE["reference_fixtures"]["safety_legal_rule"]["legal_rule_version"]
    )


def test_week_policy_expectations_match_rule():
    expected = SUITE["week_policy"]["expected_week_counts"]
    for month, count in expected.items():
        assert len(canonical_week_periods(PeriodKey(month))) == count


# ------------------------------------------------------- Gate cases


@pytest.mark.parametrize("case_id", GATE_CASES)
def test_gate_case(case_id: str):
    case = CASES[case_id]
    harness = H.make_harness(case["arrange"])
    command = H.build_command(case["arrange"])
    expected = case["expected"]

    with pytest.raises(PlanningError) as exc:
        harness.generate.execute(command)

    error = exc.value
    assert error.outcome is Outcome[expected["outcome"]], case_id
    assert error.failure_category is FailureCategory[expected["failure_category"]], case_id
    assert error.violated_rule == expected["violated_rule"], case_id

    # 실패 시 저장 0회 / LLM 호출 0회
    assert harness.monthly_plan_persisted is expected["monthly_plan_persisted"]
    assert harness.monthly.save_count == 0
    assert harness.monthly.stored_count == 0
    if harness.optional_provider is not None:
        assert harness.optional_provider.calls == 0, "Gate 실패인데 Optional을 호출했다"


# ---------------------------------------------------- Success cases


def run_success(case_id: str):
    case = CASES[case_id]
    harness = H.make_harness(case["arrange"])
    result = harness.generate.execute(H.build_command(case["arrange"]))
    return case, harness, result


def check_common_invariants(plan, run, harness) -> None:
    """common_success_invariants를 실제로 검증한다."""
    rules = {i["rule_id"]: i for i in SUITE["common_success_invariants"]}

    assert plan.status is PlanStatus.DRAFT
    assert rules["monthly_status_is_draft"]["expected"] == plan.status.value

    assert plan.school_year == H.PARENT["school_year"]
    assert plan.classroom_ref == H.PARENT["classroom_ref"]

    # WeekPeriod
    expected_weeks = canonical_week_periods(PeriodKey(plan.target_month.value))
    assert [w.week_id.value for w in plan.week_periods] == [
        w.week_id.value for w in expected_weeks
    ]
    ids = [w.week_id.value for w in plan.week_periods]
    assert len(ids) == len(set(ids))
    assert [w.week_id.ordinal for w in plan.week_periods] == list(
        range(1, len(ids) + 1)
    )
    for got, want in zip(plan.week_periods, expected_weeks):
        assert got.start_date == want.start_date
        assert got.end_date == want.end_date

    # Section
    assert [s.section_key for s in plan.sections] == rules[
        "active_sections_match_template_exactly"
    ]["expected"]
    for inactive in rules["inactive_sections_are_not_generated"]["expected"]:
        assert plan.section(inactive) is None
    for section in plan.sections:
        if section.role is SectionRole.CONTENT:
            assert section.display_mode is not None
        else:
            assert section.display_mode is None

    # Cell 주소
    item_ids = [i.item_id.value for i in plan.items]
    assert len(item_ids) == len(set(item_ids))
    for section in plan.sections:
        for item in section.items:
            assert item.item_id.value.strip()
            wid = item.week_id.value if item.week_id else None
            assert plan.find_cell(section_key=section.section_key, week_id=wid)
            if section.display_mode is not None and section.display_mode.value == (
                "MONTHLY_MERGED_SUMMARY"
            ):
                assert item.week_id is None
            elif item.week_id is not None:
                assert item.week_id.value in ids

    # lineage / anchor
    lineage = plan.parent_lineage
    assert lineage.parent_yearly_plan_id == H.PARENT["plan_id"]
    assert lineage.parent_yearly_period_key == plan.target_month.value
    assert lineage.reference_version == H.CATALOG_VERSION
    assert lineage.confirmed_by == H.PARENT["confirmed_by"]

    theme_cell = plan.section("theme").items[0]
    anchor = theme_cell.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0]
    assert anchor.source_id == lineage.parent_yearly_theme_id

    # Provenance 3축
    for item in plan.items:
        assert item.generation.method in (
            GenerationMethod.RULE_ONLY,
            GenerationMethod.RULE_LLM,
        )
        assert item.audit.contains(AuditEventType.CREATED)
        for evidence in item.evidence:
            assert evidence.source_type is not None
            assert evidence.source_type.value not in ("AI", "TEACHER_EDIT")

    # LLM 미호출
    assert run.llm_invoked is False
    assert run.llm_call_count == 0
    assert run.llm_item_count == 0

    # Safety unresolved는 fallback이 아니다
    assessment = plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert assessment is not None
    assert assessment.is_unresolved
    assert all("safety" not in f.lower() for f in run.fallbacks_used)
    assert len(run.unresolved_requirements) == 1


@pytest.mark.parametrize("case_id", SUCCESS_CASES)
def test_success_case_common_invariants(case_id: str):
    _, harness, result = run_success(case_id)
    check_common_invariants(result.plan, result.run, harness)
    assert harness.monthly.save_count == 1


def test_generate_september_2026_structure():
    case, harness, result = run_success("generate_september_2026_age4")
    plan, expected = result.plan, case["expected"]

    assert len(plan.week_periods) == expected["week_period_count"]
    assert len(plan.items) == expected["content_cell_count"]
    counts = {s.section_key: len(s.items) for s in plan.sections}
    assert counts == expected["cells_by_section"]

    states = expected["cell_states"]
    assert plan.section("theme").items[0].cell_state.value == states["theme"]
    for item in plan.section("outdoor_play").items:
        assert item.cell_state.value == states["outdoor_play"]
    for item in plan.section("safety_education").items:
        assert item.cell_state.value == states["safety_education"]

    assessment = plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert assessment.kind.value == expected["constraint"]["kind"]
    assert assessment.verification.value == expected["constraint"]["verification"]
    assert harness.monthly_plan_persisted is expected["monthly_plan_persisted"]


def test_generate_march_2026_structure():
    case, _, result = run_success("generate_march_2026_age4")
    plan, expected = result.plan, case["expected"]
    assert len(plan.week_periods) == expected["week_period_count"]
    assert len(plan.items) == expected["content_cell_count"]
    counts = {s.section_key: len(s.items) for s in plan.sections}
    assert counts == expected["cells_by_section"]


def test_generate_mixed_age():
    case, _, result = run_success("generate_mixed_age_3_4")
    assert result.plan.age_mode == case["expected"]["age_mode"]
    assert result.plan.classroom_ages == frozenset({3, 4})


def test_optional_context_failure_is_harmless():
    case, harness, result = run_success("generate_with_optional_context_failure")
    assert result.run.used_fallback is case["expected"]["used_fallback"]
    assert harness.optional_provider.calls == 1
    assert harness.monthly.save_count == 1
    # Safety unresolved가 fallback으로 새어 들어가지 않는다
    assert len(result.run.fallbacks_used) == 1
    assert result.run.fallbacks_used[0].startswith("trend:")
    assert len(result.run.unresolved_requirements) == 1


def test_no_empty_cell_blocks_generation():
    """빈 Cell이 10개여도 생성은 성공한다(RENDER_EMPTY_CELL)."""
    _, _, result = run_success("generate_september_2026_age4")
    empty = [i for i in result.plan.items if i.cell_state is not CellState.FILLED]
    assert len(empty) == 10
    assert result.plan.status is PlanStatus.DRAFT


# ==================================================== M1-C 확장

DUP_CASES = [
    c["case_id"] for c in SUITE["cases"] if "existing_monthly" in c["arrange"]
]
# pre_confirm case는 test_post_confirm_mutation_is_blocked가 담당한다.
EDIT_CASES = [
    c["case_id"]
    for c in SUITE["cases"]
    if c["operation"] == "EditMonthlyPlanItem"
    and not c["arrange"].get("pre_confirm")
]
REGEN_CASES = [
    c["case_id"]
    for c in SUITE["cases"]
    if c["operation"] == "RegenerateMonthlyPlanItem"
    and not c["arrange"].get("pre_confirm")
]

M1B_CASE_IDS = [
    "gate_monthly_requires_parent_yearly",
    "gate_monthly_requires_confirmed_parent",
    "gate_monthly_requires_matching_classroom",
    "gate_target_month_outside_academic_year",
    "gate_parent_month_period_missing",
    "gate_unapproved_monthly_template",
    "gate_unapproved_safety_legal_rule",
    "gate_unknown_template_version",
    "gate_unknown_safety_rule_version",
    "gate_catalog_version_mismatch_with_parent",
    "gate_planning_setup_incomplete",
    "generate_september_2026_age4",
    "generate_march_2026_age4",
    "generate_mixed_age_3_4",
    "generate_with_optional_context_failure",
]


def test_m1c_suite_metadata():
    """M1-C가 도입한 Contract가 유지되는지. stage 단언은 M1-D 테스트가 담당한다."""
    assert SUITE["product_contracts"]["duplicate_monthly"]["violated_rule"] == (
        "monthly_plan_is_unique_per_classroom_and_target_month"
    )
    assert SUITE["product_contracts"]["regeneratable_cells_m1"]["allowed"] == ["theme"]
    assert len(SUITE["common_edit_invariants"]) == 9


def test_m1b_case_ids_are_preserved():
    """M1-C 확장이 M1-B case를 바꾸지 않았다."""
    actual = [c["case_id"] for c in SUITE["cases"]]
    assert actual[: len(M1B_CASE_IDS)] == M1B_CASE_IDS


# ----------------------------------------------- Duplicate Gate


@pytest.mark.parametrize("case_id", DUP_CASES)
def test_duplicate_monthly_is_blocked(case_id: str):
    case = CASES[case_id]
    harness = H.make_harness({})
    existing = H.make_draft_plan(harness)
    if case["arrange"]["existing_monthly"] == "CONFIRMED":
        existing.status = PlanStatus.CONFIRMED

    before_cells = H.cell_snapshot(existing)
    before_plan = H.plan_level_snapshot(existing)
    saves_before = harness.monthly.save_count

    with pytest.raises(PlanningError) as exc:
        harness.generate.execute(H.build_command({}))

    expected = case["expected"]
    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert exc.value.failure_category is FailureCategory[expected["failure_category"]]
    assert exc.value.violated_rule == expected["violated_rule"]

    # 새 Plan 저장 0건, 기존 Plan 보존·불변
    assert harness.monthly.save_count == saves_before
    assert harness.monthly.stored_count == 1
    assert harness.monthly.get(existing.plan_id.value) is existing
    assert H.cell_snapshot(existing) == before_cells
    assert H.plan_level_snapshot(existing) == before_plan


def test_duplicate_gate_runs_before_optional_context():
    import dataclasses

    provider = H.RaisingOptionalContextProvider()
    harness = H.MonthlyHarness(
        parent=H.build_parent_yearly(), optional_context=provider
    )
    H.make_draft_plan(harness)
    assert provider.calls == 0

    command = dataclasses.replace(
        H.build_command({}), optional_context_requested={"trend": {}}
    )
    with pytest.raises(PlanningError):
        harness.generate.execute(command)
    assert provider.calls == 0


def test_different_month_is_not_a_duplicate():
    harness = H.make_harness({})
    H.make_draft_plan(harness)
    result = harness.generate.execute(H.build_command({"target_month": "2026-10"}))
    assert result.plan.target_month.value == "2026-10"
    assert harness.monthly.stored_count == 2


# ------------------------------------------------------- Edit


def prepare(case: dict):
    """DRAFT Plan을 만들고 seed 값을 적용한 뒤 harness를 돌려준다."""
    arrange = case["arrange"]
    harness = H.make_harness({})
    plan = H.make_draft_plan(harness)
    if arrange.get("seed_value") is not None:
        harness.edit.execute(
            H.build_edit_command(plan.plan_id.value, arrange, arrange["seed_value"])
        )
    if arrange.get("plan_status") == "CONFIRMED":
        plan.status = PlanStatus.CONFIRMED
    return harness, plan


@pytest.mark.parametrize(
    "case_id", [c for c in EDIT_CASES if CASES[c]["classification"] == "SUCCESS"]
)
def test_edit_success_case(case_id: str):
    case = CASES[case_id]
    arrange, expected = case["arrange"], case["expected"]
    harness, plan = prepare(case)

    before_cells = H.cell_snapshot(plan)
    before_plan = H.plan_level_snapshot(plan)
    saves = harness.monthly.save_count

    harness.edit.execute(H.build_edit_command(plan.plan_id.value, arrange))

    _section, cell = plan.find_cell(
        section_key=arrange["section_key"], week_id=arrange.get("week_id")
    )
    assert cell.value == arrange["new_value"]
    assert cell.cell_state.value == expected["cell_state"]
    assert cell.audit.events[-1].event_type.value == expected["audit_event"]
    assert cell.audit.events[-1].actor_id == H.TEACHER_ACTOR

    after_cells = H.cell_snapshot(plan)
    for item_id, snap in before_cells.items():
        if item_id == cell.item_id.value:
            continue
        assert after_cells[item_id] == snap, "sibling " + item_id + " 변경됨"
    assert H.plan_level_snapshot(plan) == before_plan
    assert plan.status is PlanStatus.DRAFT
    assert harness.monthly.save_count == saves + 1

    if expected.get("generation_method"):
        assert cell.generation.method.value == expected["generation_method"]
    if expected.get("evidence_preserved"):
        assert cell.evidence_of_type(EvidenceSourceType.PARENT_PLAN)
        assert cell.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)


@pytest.mark.parametrize(
    "case_id", [c for c in EDIT_CASES if CASES[c]["classification"] == "FAILURE"]
)
def test_edit_failure_case(case_id: str):
    case = CASES[case_id]
    arrange, expected = case["arrange"], case["expected"]
    harness, plan = prepare(case)

    before_cells = H.cell_snapshot(plan)
    before_plan = H.plan_level_snapshot(plan)
    saves = harness.monthly.save_count

    with pytest.raises(PlanningError) as exc:
        harness.edit.execute(H.build_edit_command(plan.plan_id.value, arrange))

    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert exc.value.failure_category is FailureCategory[expected["failure_category"]]
    assert exc.value.violated_rule == expected["violated_rule"]
    assert H.cell_snapshot(plan) == before_cells
    assert H.plan_level_snapshot(plan) == before_plan
    assert harness.monthly.save_count == saves


# ------------------------------------------------- Regenerate


@pytest.mark.parametrize(
    "case_id", [c for c in REGEN_CASES if CASES[c]["classification"] == "SUCCESS"]
)
def test_regenerate_success_case(case_id: str):
    case = CASES[case_id]
    arrange, expected = case["arrange"], case["expected"]
    harness, plan = prepare(case)

    before_cells = H.cell_snapshot(plan)
    before_plan = H.plan_level_snapshot(plan)
    saves = harness.monthly.save_count
    _section, cell = plan.find_cell(
        section_key=arrange["section_key"], week_id=arrange.get("week_id")
    )
    value_before = cell.value

    harness.regenerate_item.execute(
        H.build_regenerate_command(plan.plan_id.value, arrange)
    )

    assert cell.audit.events[-1].event_type.value == expected["audit_event"]
    assert cell.audit.events[-1].actor_id == H.TEACHER_ACTOR
    if expected.get("value_equals_parent_anchor_value"):
        assert cell.value == plan.parent_lineage.parent_yearly_value
    if expected.get("value_changed") is False:
        assert cell.value == value_before
    if expected.get("cell_state"):
        assert cell.cell_state.value == expected["cell_state"]
    if expected.get("generation_method"):
        assert cell.generation.method.value == expected["generation_method"]

    after_cells = H.cell_snapshot(plan)
    for item_id, snap in before_cells.items():
        if item_id == cell.item_id.value:
            continue
        assert after_cells[item_id] == snap, "sibling " + item_id + " 변경됨"
    assert H.plan_level_snapshot(plan) == before_plan
    assert harness.monthly.save_count == saves + 1


@pytest.mark.parametrize(
    "case_id", [c for c in REGEN_CASES if CASES[c]["classification"] == "FAILURE"]
)
def test_regenerate_failure_case(case_id: str):
    case = CASES[case_id]
    arrange, expected = case["arrange"], case["expected"]
    harness, plan = prepare(case)

    before_cells = H.cell_snapshot(plan)
    before_plan = H.plan_level_snapshot(plan)
    saves = harness.monthly.save_count

    with pytest.raises(PlanningError) as exc:
        harness.regenerate_item.execute(
            H.build_regenerate_command(plan.plan_id.value, arrange)
        )

    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert exc.value.failure_category is FailureCategory[expected["failure_category"]]
    assert exc.value.violated_rule == expected["violated_rule"]
    assert H.cell_snapshot(plan) == before_cells
    assert H.plan_level_snapshot(plan) == before_plan
    assert harness.monthly.save_count == saves


# ==================================================== M1-D 확장

from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.monthly_dto import ConfirmMonthlyPlanCommand
from ssuksak.planning.domain.constraint import ConstraintVerification
from ssuksak.planning.rules import gates as shared_gates

CONFIRM_CASES = [
    c["case_id"] for c in SUITE["cases"] if c["operation"] == "ConfirmMonthlyPlan"
]
WEEKLY_GATE_CASES = [
    c["case_id"]
    for c in SUITE["cases"]
    if c["operation"] == "RequireConfirmedParentMonthly"
]
POST_CONFIRM_CASES = [
    c["case_id"]
    for c in SUITE["cases"]
    if c["arrange"].get("pre_confirm")
    and c["operation"] in ("EditMonthlyPlanItem", "RegenerateMonthlyPlanItem")
]


def test_m1d_suite_metadata():
    assert SUITE["contract_stage"] == "M1-D"
    confirm = SUITE["product_contracts"]["confirm_semantics"]
    assert "법정 안전교육 충족" in confirm["does_not_mean"]
    assert SUITE["product_contracts"]["weekly_gate"]["rule_id"] == (
        "weekly_generation_requires_confirmed_monthly_plan"
    )
    assert len(SUITE["common_confirm_invariants"]) == 17


def test_m1c_case_ids_are_preserved():
    """M1-D 확장이 M1-B/M1-C case를 바꾸지 않았다."""
    actual = [c["case_id"] for c in SUITE["cases"]]
    assert actual[: len(M1B_CASE_IDS)] == M1B_CASE_IDS
    m1c_tail = [
        "generate_blocked_by_existing_draft_monthly",
        "generate_blocked_by_existing_confirmed_monthly",
        "edit_theme_success",
        "regenerate_theme_success",
    ]
    for cid in m1c_tail:
        assert cid in actual


def build_confirm(harness, *, template_approval=None, safety_approval=None):
    from ssuksak.adapters.monthly_repositories import (
        JsonMonthlyTemplateRepository,
        JsonSafetyLegalRuleRepository,
    )
    from ssuksak.adapters.deterministic import FixedClock

    return ConfirmMonthlyPlan(
        monthly_plan_repository=harness.monthly,
        template_repository=JsonMonthlyTemplateRepository(
            approval_override=template_approval
        ),
        safety_rule_repository=JsonSafetyLegalRuleRepository(
            approval_override=safety_approval
        ),
        clock=FixedClock(H.NOW, advance_seconds=1),
    )


def prepare_confirm(case: dict):
    """DRAFT Plan을 만들고 arrange를 적용한다."""
    arrange = case["arrange"]
    harness = H.make_harness({})
    plan = H.make_draft_plan(harness)

    if arrange.get("fill_all_safety"):
        for week in plan.week_periods:
            harness.edit.execute(
                H.build_edit_command(
                    plan.plan_id.value,
                    {"section_key": "safety_education", "week_id": week.week_id.value},
                    week.display_label + " 안전교육",
                )
            )
    if arrange.get("pre_confirm"):
        build_confirm(harness).execute(
            ConfirmMonthlyPlanCommand(
                plan_id=plan.plan_id.value, actor_id=H.TEACHER_ACTOR
            )
        )
    if arrange.get("corrupt") == "blank_theme":
        theme = plan.section("theme").items[0]
        theme.value = ""
        theme.cell_state = CellState.EMPTY_VALID

    confirm = build_confirm(
        harness,
        template_approval=arrange.get("template_approval"),
        safety_approval=arrange.get("safety_approval"),
    )
    return harness, plan, confirm


def confirm_command(plan, case: dict):
    arrange = case["arrange"]
    actor = H.TEACHER_ACTOR if "actor" not in arrange else arrange["actor"]
    return ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=actor)


@pytest.mark.parametrize(
    "case_id", [c for c in CONFIRM_CASES if CASES[c]["classification"] == "SUCCESS"]
)
def test_confirm_success_case(case_id: str):
    case = CASES[case_id]
    expected = case["expected"]
    harness, plan, confirm = prepare_confirm(case)

    cells_before = H.cell_snapshot(plan)
    lineage = plan.parent_lineage
    template_ref = plan.template_ref
    weeks = plan.week_periods
    constraints = plan.constraint_assessments
    sections = [s.section_key for s in plan.sections]
    audit_before = len(plan.audit.events)
    cell_audit_before = {i.item_id.value: len(i.audit.events) for i in plan.items}
    saves = harness.monthly.save_count

    confirm.execute(confirm_command(plan, case))

    # common_confirm_invariants
    assert plan.status is PlanStatus.CONFIRMED
    assert plan.status.value == expected["status"]
    assert len(plan.audit.events) == audit_before + 1
    event = plan.audit.events[-1]
    assert event.event_type.value == expected["audit_event"]
    assert event.actor_id == H.TEACHER_ACTOR
    assert event.occurred_at is not None

    assert H.cell_snapshot(plan) == cells_before
    assert plan.parent_lineage == lineage
    assert plan.parent_lineage.parent_yearly_theme_id == lineage.parent_yearly_theme_id
    assert plan.template_ref == template_ref
    assert plan.week_periods == weeks
    assert plan.constraint_assessments == constraints
    assert [s.section_key for s in plan.sections] == sections
    assert {
        i.item_id.value: len(i.audit.events) for i in plan.items
    } == cell_audit_before
    assert harness.monthly.save_count == saves + 1

    if expected.get("constraint_verification_after"):
        after = plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
        assert after.verification.value == expected["constraint_verification_after"]
        assert after.verification is not ConstraintVerification.VERIFIED
    if expected.get("safety_cell_state"):
        for item in plan.section("safety_education").items:
            assert item.cell_state.value == expected["safety_cell_state"]


@pytest.mark.parametrize(
    "case_id", [c for c in CONFIRM_CASES if CASES[c]["classification"] == "FAILURE"]
)
def test_confirm_failure_case(case_id: str):
    case = CASES[case_id]
    expected = case["expected"]
    harness, plan, confirm = prepare_confirm(case)

    cells_before = H.cell_snapshot(plan)
    plan_before = H.plan_level_snapshot(plan)
    audit_before = len(plan.audit.events)
    saves = harness.monthly.save_count

    with pytest.raises(PlanningError) as exc:
        confirm.execute(confirm_command(plan, case))

    assert exc.value.outcome is Outcome[expected["outcome"]]
    assert exc.value.failure_category is FailureCategory[expected["failure_category"]]
    assert exc.value.violated_rule == expected["violated_rule"]

    assert plan.status.value == expected["status_after"]
    assert len(plan.audit.events) == audit_before
    assert H.cell_snapshot(plan) == cells_before
    assert H.plan_level_snapshot(plan) == plan_before
    assert harness.monthly.save_count == saves


@pytest.mark.parametrize("case_id", POST_CONFIRM_CASES)
def test_post_confirm_mutation_is_blocked(case_id: str):
    case = CASES[case_id]
    arrange, expected = case["arrange"], case["expected"]
    harness, plan, _ = prepare_confirm(case)

    cells_before = H.cell_snapshot(plan)
    plan_before = H.plan_level_snapshot(plan)
    saves = harness.monthly.save_count

    with pytest.raises(PlanningError) as exc:
        if case["operation"] == "EditMonthlyPlanItem":
            harness.edit.execute(H.build_edit_command(plan.plan_id.value, arrange))
        else:
            harness.regenerate_item.execute(
                H.build_regenerate_command(plan.plan_id.value, arrange)
            )

    assert exc.value.violated_rule == expected["violated_rule"]
    assert plan.status is PlanStatus.CONFIRMED
    assert H.cell_snapshot(plan) == cells_before
    assert H.plan_level_snapshot(plan) == plan_before
    assert harness.monthly.save_count == saves


@pytest.mark.parametrize("case_id", WEEKLY_GATE_CASES)
def test_weekly_gate_case(case_id: str):
    case = CASES[case_id]
    expected = case["expected"]
    _harness, plan, _ = prepare_confirm(case)

    if expected["outcome"] == "SUCCESS":
        shared_gates.require_confirmed_parent_monthly(plan)
        # Safety 미해결이어도 통과한다.
        assert len(plan.unresolved_constraints) == 1
    else:
        with pytest.raises(PlanningError) as exc:
            shared_gates.require_confirmed_parent_monthly(plan)
        assert exc.value.failure_category is FailureCategory[
            expected["failure_category"]
        ]
        assert exc.value.violated_rule == expected["violated_rule"]
