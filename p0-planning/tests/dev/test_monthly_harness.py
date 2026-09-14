"""Monthly Dev Harness 테스트.

검증 축:
- startup wiring과 CONFIRMED Parent Yearly가 실제 Use Case 경로로 준비된다
- 모든 상태 변경이 Application Use Case를 통한다 (Domain 직접 mutation 없음)
- EMPTY_VALID와 EMPTY_UNRESOLVED가 시각적으로 구분된다
- Monthly는 LLM dependency가 없다
- Yearly Harness를 건드리지 않는다
"""

from __future__ import annotations

import pathlib
import re

import pytest

from ssuksak.dev import monthly_formatting as fmt
from ssuksak.dev import monthly_harness as cli
from ssuksak.dev.monthly_wiring import (
    DEFAULT_TARGET_MONTH,
    DEV_ACTOR,
    MonthlyHarnessSession,
    build_monthly_wiring,
    read_safety_selector,
    read_template_ref,
)
from ssuksak.planning.application.monthly_dto import (
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.domain.constraint import CellState, ConstraintKind
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType, EvidenceSourceType
from ssuksak.planning.rules import gates

DEV_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "ssuksak" / "dev"


# ------------------------------------------------------- startup wiring


@pytest.fixture()
def wiring():
    return build_monthly_wiring()


def generated(w):
    session = MonthlyHarnessSession()
    result = w.generate.execute(
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
    session.adopt(result.plan)
    session.absorb_run(result.run)
    return session


def generated_without_activities(w):
    """Activity Reference를 쓰지 않는 M1 경로. 빈 Cell 표시를 확인할 때 쓴다."""
    session = MonthlyHarnessSession()
    result = w.generate.execute(
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
        )
    )
    session.adopt(result.plan)
    session.absorb_run(result.run)
    return session


def test_wiring_builds_without_network_or_llm(wiring):
    assert wiring.parent_yearly is not None
    assert wiring.target_month == DEFAULT_TARGET_MONTH
    assert wiring.school_year == 2026


def test_parent_yearly_is_confirmed_via_use_cases(wiring):
    """status를 직접 바꾸지 않고 Generate → Confirm 경로로 만든다."""
    parent = wiring.parent_yearly
    assert parent.status is PlanStatus.CONFIRMED
    assert parent.audit.contains(AuditEventType.CREATED)
    assert parent.audit.contains(AuditEventType.CONFIRMED)
    confirmed = [
        e for e in parent.audit.events if e.event_type is AuditEventType.CONFIRMED
    ]
    assert confirmed[-1].actor_id == DEV_ACTOR


def test_parent_yearly_has_twelve_periods_and_target_theme(wiring):
    assert len(wiring.parent_yearly.month_periods) == 12
    period = wiring.parent_yearly.period(wiring.target_month)
    assert period is not None and period.theme.value


def test_versions_are_read_from_approved_files_not_hardcoded():
    assert read_template_ref().template_version == "monthly-template-a-v0.1.0"
    assert (
        read_safety_selector().legal_rule_version
        == "child-welfare-act-decree-annex6-2022-06-21"
    )


def test_wiring_creates_no_new_persistence_adapter():
    """기존 Adapter만 재사용한다. 새 Persistence/HTTP Adapter를 만들지 않는다."""
    import ast

    src = (DEV_DIR / "monthly_wiring.py").read_text(encoding="utf-8")
    assert "InMemoryMonthlyPlanRepository" in src

    modules: list[str] = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            modules += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    banned = ("psycopg", "sqlite", "sqlalchemy", "httpx", "requests", "fastapi")
    assert not [m for m in modules if any(b in m for b in banned)], modules
    # class 정의가 없다 = 새 Adapter를 만들지 않았다 (dataclass 2개는 값 객체)
    defined = [
        n.name
        for n in ast.parse(src).body
        if isinstance(n, ast.ClassDef)
    ]
    assert defined == ["MonthlyHarnessSession", "MonthlyWiring"]


def test_monthly_harness_has_no_llm_dependency():
    for name in ("monthly_wiring.py", "monthly_harness.py", "monthly_formatting.py"):
        src = (DEV_DIR / name).read_text(encoding="utf-8")
        assert "EliceMLAPIAdapter" not in src, name
        assert "polish" not in src, name
        assert "LLMConfig" not in src, name


def test_monthly_uses_fake_llm_only_for_yearly_no_llm_path():
    """Yearly Generate는 Port가 필요하지만 use_llm=False라 호출되지 않는다."""
    src = (DEV_DIR / "monthly_wiring.py").read_text(encoding="utf-8")
    assert "use_llm=False" in src
    assert "FakeLLM()" in src


# --------------------------------------------------------- Generate


def test_generate_produces_expected_structure(wiring):
    session = generated(wiring)
    plan = session.plan
    assert plan.status is PlanStatus.DRAFT
    assert len(plan.week_periods) == 5
    assert {s.section_key: len(s.items) for s in plan.sections} == {
        "theme": 1,
        "week_axis": 0,
        "outdoor_play": 5,
        "safety_education": 5,
    }
    assert len(plan.items) == 11


def test_generate_result_formatting(wiring):
    session = generated(wiring)
    text = fmt.format_generate_result(session.plan, session.run)
    assert "[성공] GenerateMonthlyPlan" in text
    assert "DRAFT" in text
    assert "WeekPeriod     : 5개" in text
    assert "content Cell   : 11개" in text
    assert "Parent anchor" in text


def test_march_has_four_weeks_and_nine_cells():
    w = build_monthly_wiring(target_month="2026-03")
    session = generated(w)
    assert len(session.plan.week_periods) == 4
    assert len(session.plan.items) == 9


# --------------------------------------------------------- 배너·Plan


def test_banner_shows_required_fields(wiring):
    text = fmt.format_banner(
        school_year=wiring.school_year,
        target_month=wiring.target_month,
        classroom_ref=wiring.classroom.classroom_ref,
        ages=wiring.classroom.ages,
        age_mode=wiring.classroom.effective_age_mode.value,
        parent=wiring.parent_yearly,
        template_ref=wiring.template_ref,
        safety_rule_version=wiring.safety_rule.legal_rule_version,
        has_monthly_plan=False,
    )
    assert "2026" in text and "2026-09" in text
    assert wiring.classroom.classroom_ref in text
    assert "만 4세" in text and "SINGLE" in text
    assert wiring.parent_yearly.plan_id.value in text
    assert "CONFIRMED" in text
    assert "monthly-template-a-v0.1.0" in text
    assert "child-welfare-act-decree-annex6-2022-06-21" in text
    assert "아직 없음" in text
    assert "제품 FE가 아님" in text


def test_plan_view_separates_theme_weeks_outdoor_safety(wiring):
    text = fmt.format_monthly_plan(generated(wiring).plan)
    for header in (" Theme", " Weeks", " outdoor_play", " safety_education"):
        assert header in text
    assert "2026-09-W1  08/31~09/04" in text
    assert "2026-09-W5  09/28~10/02" in text
    assert "structural axis" in text


def test_empty_valid_and_empty_unresolved_are_visually_distinct(wiring):
    session = generated(wiring)
    text = fmt.format_monthly_plan(session.plan)
    assert "[EMPTY_UNRESOLVED]" in text
    # M2-C 이후 outdoor 5개는 FILLED다. safety 5개만 EMPTY_UNRESOLVED로 남는다.
    assert text.count("[EMPTY_UNRESOLVED]") == 5
    assert text.count("[FILLED]") == 6  # theme 1 + outdoor 5
    # 빈 Cell이 남는 Plan에서도 두 빈 상태는 구분되어야 한다.
    # duplicate gate 때문에 같은 wiring으로 두 번 생성할 수 없다. 새로 조립한다.
    empty_text = fmt.format_monthly_plan(
        generated_without_activities(build_monthly_wiring()).plan
    )
    assert empty_text.count("[EMPTY_VALID]") == 5
    assert empty_text.count("[EMPTY_UNRESOLVED]") == 5
    # 둘 다 "(빈 값)"으로 뭉뚱그리지 않는다.
    assert fmt.CELL_STATE_MARK[CellState.EMPTY_VALID] != (
        fmt.CELL_STATE_MARK[CellState.EMPTY_UNRESOLVED]
    )


def test_cell_state_marks_cover_all_states():
    assert set(fmt.CELL_STATE_MARK) == set(CellState)
    assert len({v.strip() for v in fmt.CELL_STATE_MARK.values()}) == 3


# ------------------------------------------------------------- Edit


def address(section_key, week_id=None, month=DEFAULT_TARGET_MONTH):
    return MonthlyCellAddress(
        target_month=month, section_key=section_key, week_id=week_id
    )


def do_edit(w, session, section_key, value, week_id=None):
    result = w.edit.execute(
        EditMonthlyPlanItemCommand(
            plan_id=session.plan_id,
            address=address(section_key, week_id),
            new_value=value,
            actor_id=DEV_ACTOR,
        )
    )
    session.adopt(result.plan)
    return session.plan.find_cell(section_key=section_key, week_id=week_id)[1]


def test_edit_outdoor_to_filled(wiring):
    session = generated(wiring)
    cell = do_edit(wiring, session, "outdoor_play", "가을 숲 산책", "2026-09-W2")
    assert cell.value == "가을 숲 산책"
    assert cell.cell_state is CellState.FILLED


def test_edit_result_formatting_shows_state_change(wiring):
    session = generated(wiring)
    before = session.plan.find_cell(
        section_key="outdoor_play", week_id="2026-09-W2"
    )[1]
    prev_value, prev_state = before.value, before.cell_state
    cell = do_edit(wiring, session, "outdoor_play", "산책", "2026-09-W2")
    text = fmt.format_edit_result(
        "outdoor_play", "2026-09-W2", cell,
        previous_value=prev_value, previous_state=prev_state,
    )
    assert "[성공] Cell 수정" in text
    assert "FILLED" in text
    assert "RULE_ONLY (변경 없음)" in text
    assert "TEACHER_EDITED" in text
    assert prev_state is CellState.FILLED  # M2-C 이후 outdoor는 채워져 있다


@pytest.mark.parametrize(
    "section_key,week_id,value,expected",
    [
        ("theme", None, "새 주제", CellState.FILLED),
        ("outdoor_play", "2026-09-W1", "", CellState.EMPTY_VALID),
        ("safety_education", "2026-09-W1", "", CellState.EMPTY_UNRESOLVED),
        ("safety_education", "2026-09-W1", "교통안전", CellState.FILLED),
    ],
)
def test_blank_policy_transitions_are_observable(
    wiring, section_key, week_id, value, expected
):
    session = generated(wiring)
    cell = do_edit(wiring, session, section_key, value, week_id)
    assert cell.cell_state is expected


def test_blank_theme_edit_is_blocked_by_use_case(wiring):
    session = generated(wiring)
    with pytest.raises(PlanningError) as exc:
        do_edit(wiring, session, "theme", "   ")
    text = fmt.format_planning_error("Cell 수정", exc.value)
    assert "REQUIRED_VALUE_VALIDATION" in text
    assert "theme_cell_is_required_and_non_blank" in text
    assert "Traceback" not in text


def test_error_formatting_has_category_and_rule(wiring):
    session = generated(wiring)
    with pytest.raises(PlanningError) as exc:
        wiring.edit.execute(
            EditMonthlyPlanItemCommand(
                plan_id=session.plan_id,
                address=address("theme", "2026-09-W1"),
                new_value="x",
                actor_id=DEV_ACTOR,
            )
        )
    text = fmt.format_planning_error("Cell 수정", exc.value)
    assert "[실패]" in text
    assert "category :" in text and "rule     :" in text
    assert 'File "' not in text


# ------------------------------------------------------- Regenerate


def test_theme_regenerate_success_and_same_value(wiring):
    session = generated(wiring)
    cell_before = session.plan.section("theme").items[0]
    previous = cell_before.value

    result = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=session.plan_id, address=address("theme"), actor_id=DEV_ACTOR
        )
    )
    session.adopt(result.plan)
    cell = session.plan.section("theme").items[0]

    text = fmt.format_regenerate_result(
        "theme", cell,
        previous_value=previous,
        anchor_theme_id=session.plan.parent_lineage.parent_yearly_theme_id,
    )
    assert "[성공] Cell 재생성" in text
    assert "same_value     : true" in text
    assert "monthly.theme.parent_anchor_derivation" in text
    assert "오류가 아닙니다" in text
    assert "REGENERATED" in text


def test_regenerate_shows_changed_value_when_edited_first(wiring):
    session = generated(wiring)
    do_edit(wiring, session, "theme", "교사가 바꾼 값")
    previous = session.plan.section("theme").items[0].value

    result = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=session.plan_id, address=address("theme"), actor_id=DEV_ACTOR
        )
    )
    session.adopt(result.plan)
    cell = session.plan.section("theme").items[0]
    text = fmt.format_regenerate_result(
        "theme", cell, previous_value=previous,
        anchor_theme_id=session.plan.parent_lineage.parent_yearly_theme_id,
    )
    assert "same_value     : false" in text
    assert cell.value == session.plan.parent_lineage.parent_yearly_value


@pytest.mark.parametrize(
    "section_key,week_id,keyword",
    [("safety_education", "2026-09-W1", "배치 source")],
)
def test_blocked_regenerate_is_shown_not_hidden(wiring, section_key, week_id, keyword):
    """메뉴에서 차단 Cell을 숨기지 않고 실제 Use Case가 차단한다."""
    session = generated(wiring)
    with pytest.raises(PlanningError) as exc:
        wiring.regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=session.plan_id,
                address=address(section_key, week_id),
                actor_id=DEV_ACTOR,
            )
        )
    text = fmt.format_planning_error("Cell 재생성", exc.value)
    assert "PREREQUISITE_GATE" in text
    assert "regenerate_requires_resolved_candidate_source" in text
    assert keyword in text


def test_harness_does_not_hide_blocked_sections():
    src = (DEV_DIR / "monthly_harness.py").read_text(encoding="utf-8")
    # 차단 Section을 후보 목록에서 제외하는 필터가 없어야 한다.
    assert "REGENERATABLE" not in src
    assert "차단 Cell을 숨기지 않는다" in src or "숨기지 않는다" in src


# -------------------------------------------------------- Constraint


def test_constraint_formatting(wiring):
    session = generated(wiring)
    text = fmt.format_constraints(session.plan.constraint_assessments)
    assert "STATUTORY_SAFETY_EDUCATION" in text
    assert "NOT_VERIFIED_SOURCE_REQUIRED" in text
    assert "child-welfare-act-decree-annex6-2022-06-21" in text
    assert "INSTITUTION_ANNUAL_SAFETY_PLAN" in text
    assert "safety_education" in text
    assert "fallback" in text


def test_constraint_formatting_handles_empty():
    assert "없음" in fmt.format_constraints(())


# ----------------------------------------------------- GenerationRun


def test_generation_run_formatting(wiring):
    session = generated(wiring)
    text = fmt.format_generation_run(session.run)
    assert "monthly-template-a-v0.1.0" in text
    assert "child-welfare-act-decree-annex6-2022-06-21" in text
    assert "week_period_count           : 5" in text
    assert "generated_cell_count        : 11" in text
    assert "filled_cell_count           : 6" in text  # theme 1 + outdoor 5
    assert "empty_valid_cell_count      : 0" in text
    assert "empty_unresolved_cell_count : 5" in text
    assert "activity_catalog_version    : activity-reference-v0.2.1" in text
    assert "activity_filled_cell_count  : 5" in text
    assert "activity_unfilled_cell_count: 0" in text
    assert "llm_invoked                 : false" in text
    assert "fallbacks_used              : 없음" in text
    assert "unresolved_requirements     : 1건" in text


# -------------------------------------------------------- Provenance


def test_provenance_three_axes_for_theme(wiring):
    session = generated(wiring)
    cell = session.plan.section("theme").items[0]
    text = fmt.format_cell_provenance("theme", None, cell)
    assert "[1축] Evidence Source" in text
    assert "[2축] Generation Method" in text
    assert "[3축] Audit History" in text
    assert "PARENT_PLAN" in text
    assert "THEME_REFERENCE" in text
    assert "RULE_ONLY" in text
    assert "monthly.theme.parent_anchor_derivation" in text
    assert "CREATED" in text
    assert "None (월간 병합 Cell)" in text


def test_provenance_for_empty_cell_shows_no_content_evidence(wiring):
    session = generated(wiring)
    cell = session.plan.section("safety_education").items[0]
    text = fmt.format_cell_provenance("safety_education", "2026-09-W1", cell)
    assert "content Evidence 없음" in text
    assert "EMPTY_UNRESOLVED" in text
    # Template / Safety Rule을 content Evidence처럼 보여주지 않는다.
    assert "SAFETY_RULE" not in text
    assert "source_type" not in text


def test_provenance_shows_teacher_edit_and_regenerate(wiring):
    session = generated(wiring)
    do_edit(wiring, session, "theme", "교사 수정본")
    result = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=session.plan_id, address=address("theme"), actor_id=DEV_ACTOR
        )
    )
    session.adopt(result.plan)
    cell = session.plan.section("theme").items[0]
    text = fmt.format_cell_provenance("theme", None, cell)
    assert "TEACHER_EDITED" in text
    assert "REGENERATED" in text


# ------------------------------------------------------------- Audit


def test_audit_separates_plan_and_cell_levels(wiring):
    session = generated(wiring)
    do_edit(wiring, session, "outdoor_play", "산책", "2026-09-W1")
    text = fmt.format_audit(session.plan)
    assert "[Plan level]" in text
    assert "[Cell level]" in text
    assert "CREATED" in text
    assert "TEACHER_EDITED" in text
    assert "outdoor_play / 2026-09-W1" in text


def test_audit_uses_only_existing_event_types(wiring):
    session = generated(wiring)
    text = fmt.format_audit(session.plan)
    for token in re.findall(r"- ([A-Z_]+)\s", text):
        assert token in {e.value for e in AuditEventType}


# ----------------------------------------------------------- Confirm


def do_confirm(w, session):
    result = w.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=session.plan_id, actor_id=DEV_ACTOR)
    )
    session.adopt(result.plan)
    return result.plan


def test_confirm_transitions_and_keeps_constraint(wiring):
    session = generated(wiring)
    before = session.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    plan = do_confirm(wiring, session)
    assert plan.status is PlanStatus.CONFIRMED
    assert plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION) is before


def test_confirm_formatting_states_semantics(wiring):
    session = generated(wiring)
    previous = session.plan.status
    plan = do_confirm(wiring, session)
    text = fmt.format_confirm_result(plan, previous_status=previous)
    assert "DRAFT → CONFIRMED" in text
    assert "teacher_dev_001" in text
    assert "NOT_VERIFIED_SOURCE_REQUIRED (변경 없음)" in text
    assert "CONFIRMED ≠ Safety VERIFIED" in text


def test_edit_after_confirm_is_blocked_by_application_gate(wiring):
    session = generated(wiring)
    do_confirm(wiring, session)
    saves = wiring.monthly_plans.save_count
    with pytest.raises(PlanningError) as exc:
        do_edit(wiring, session, "theme", "확정 후 수정")
    assert exc.value.failure_category is FailureCategory.PLAN_STATE_GATE
    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"
    assert wiring.monthly_plans.save_count == saves


def test_regenerate_after_confirm_is_blocked_by_application_gate(wiring):
    session = generated(wiring)
    do_confirm(wiring, session)
    with pytest.raises(PlanningError) as exc:
        wiring.regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=session.plan_id, address=address("theme"), actor_id=DEV_ACTOR
            )
        )
    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"


def test_harness_does_not_disable_menu_after_confirm():
    """메뉴를 숨기지 않고 실제 Gate가 차단해야 한다."""
    src = (DEV_DIR / "monthly_harness.py").read_text(encoding="utf-8")
    assert "is_confirmed" not in src
    assert "CONFIRMED" not in src.split("MENU = ")[1].split('"""')[1]


# ------------------------------------------------- Duplicate / Weekly


def test_duplicate_generate_is_blocked(wiring):
    session = generated(wiring)
    stored = wiring.monthly_plans.stored_count
    with pytest.raises(PlanningError) as exc:
        generated(wiring)
    assert exc.value.violated_rule == (
        "monthly_plan_is_unique_per_classroom_and_target_month"
    )
    assert wiring.monthly_plans.stored_count == stored


def test_weekly_gate_blocked_for_draft(wiring):
    session = generated(wiring)
    with pytest.raises(PlanningError) as exc:
        gates.require_confirmed_parent_monthly(session.plan)
    text = fmt.format_weekly_gate_result(session.plan, exc.value)
    assert "BLOCKED" in text
    assert "weekly_generation_requires_confirmed_monthly_plan" in text
    assert "DRAFT" in text


def test_weekly_gate_passes_for_confirmed_with_unresolved_safety(wiring):
    session = generated(wiring)
    do_confirm(wiring, session)
    gates.require_confirmed_parent_monthly(session.plan)
    text = fmt.format_weekly_gate_result(session.plan, None)
    assert "PASS" in text
    assert "CONFIRMED ≠ Safety verified" in text
    assert "unresolved     : 1건" in text


def test_harness_has_no_weekly_generation_menu():
    """Weekly Gate 확인 메뉴는 있어도 Weekly 생성은 없다 (M2 범위)."""
    src = (DEV_DIR / "monthly_harness.py").read_text(encoding="utf-8")
    menu = src.split("MENU = ")[1].split('"""')[1]
    assert "Weekly 생성 아님" in menu
    assert "GenerateWeekly" not in src
    assert "WeeklyPlan" not in src


# --------------------------------------------------------- Raw dump


def test_raw_dump_is_valid_json_and_harness_side(wiring):
    import json

    session = generated(wiring)
    payload = json.loads(fmt.format_raw_dump(session.plan, session.run))
    assert payload["plan"]["status"] == "DRAFT"
    assert len(payload["plan"]["week_periods"]) == 5
    assert len(payload["plan"]["sections"]) == 4
    assert payload["run"]["generated_cell_count"] == 11
    assert payload["run"]["llm_invoked"] is False
    assert payload["plan"]["constraint_assessments"][0]["verification"] == (
        "NOT_VERIFIED_SOURCE_REQUIRED"
    )


def test_raw_dump_handles_missing_run(wiring):
    import json

    session = generated(wiring)
    assert json.loads(fmt.format_raw_dump(session.plan, None))["run"] is None


# ------------------------------------ Domain 직접 Mutation 금지 가드


def test_monthly_dev_sources_do_not_mutate_domain_directly():
    forbidden = [
        re.compile(r"\.value\s*=\s*[^=]"),
        re.compile(r"\.status\s*=\s*[^=]"),
        re.compile(r"\.cell_state\s*=\s*[^=]"),
        re.compile(r"\.evidence\s*=\s*[^=]"),
        re.compile(r"\.generation\s*=\s*[^=]"),
        re.compile(r"\.sections\s*=\s*[^=]"),
        re.compile(r"\.constraint_assessments\s*=\s*[^=]"),
        re.compile(r"\.audit\.append\("),
        re.compile(r"\.confirm\(\s*AuditEvent"),
    ]
    offenders: list[str] = []
    for name in ("monthly_harness.py", "monthly_wiring.py", "monthly_formatting.py"):
        path = DEV_DIR / name
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            for pattern in forbidden:
                if pattern.search(code):
                    offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, "Monthly dev가 Domain을 직접 변경한다:\n" + "\n".join(offenders)


def test_monthly_harness_changes_state_only_through_use_cases():
    src = (DEV_DIR / "monthly_harness.py").read_text(encoding="utf-8")
    for use_case in ("generate", "edit", "regenerate", "confirm"):
        assert f"wiring.{use_case}.execute(" in src, use_case


def test_monthly_dev_does_not_import_domain_mutators():
    joined = "\n".join(
        (DEV_DIR / n).read_text(encoding="utf-8")
        for n in ("monthly_harness.py", "monthly_formatting.py")
    )
    assert "AuditEvent" not in joined
    assert "GenerationMethodDetail" not in joined


# ------------------------------------------ Yearly Harness 무변경


def test_yearly_harness_files_are_untouched_by_monthly():
    for name in ("yearly_harness.py", "wiring.py", "formatting.py"):
        src = (DEV_DIR / name).read_text(encoding="utf-8")
        assert "monthly" not in src.lower(), name


def test_monthly_is_a_separate_cli():
    assert (DEV_DIR / "monthly_harness.py").exists()
    src = (DEV_DIR / "monthly_harness.py").read_text(encoding="utf-8")
    assert "def main(" in src
    assert "--month" in src and "--debug" in src
    assert "--no-llm" not in src  # Monthly에는 LLM이 없다


# ------------------------------------------------------ CLI 파서


def test_cli_menu_choices_cover_all_menu_items():
    items = re.findall(r"\[(\d+)\]", cli.MENU)
    assert set(items) == set(cli.CHOICES)


def test_cli_main_accepts_month_and_debug(monkeypatch):
    calls = {}

    def fake_loop(wiring, session, *, debug):
        calls["debug"] = debug
        calls["month"] = wiring.target_month
        calls["status"] = session.plan.status

    monkeypatch.setattr(cli, "_run_loop", fake_loop)
    assert cli.main(["--month", "2026-03", "--debug"]) == 0
    assert calls["debug"] is True
    assert calls["month"] == "2026-03"
    assert calls["status"] is PlanStatus.DRAFT


def test_cli_main_default_month(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        cli, "_run_loop", lambda w, s, *, debug: seen.update(month=w.target_month)
    )
    assert cli.main([]) == 0
    assert seen["month"] == DEFAULT_TARGET_MONTH
