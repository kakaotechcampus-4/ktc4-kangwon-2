"""Monthly Harness 출력 포맷.

Yearly `formatting.py`를 수정하지 않는다. Monthly 전용 helper만 둔다.

**개발 검증 목적의 표시다.** 최종 FE 문구나 디자인이 아니다.

원칙:
- Domain model serialization을 위해 Production Contract를 바꾸지 않는다.
  필요한 파생값은 여기서 계산한다.
- `EMPTY_VALID`와 `EMPTY_UNRESOLVED`를 시각적으로 **구분**한다.
  둘 다 "(빈 값)"으로 뭉뚱그리지 않는다.
- 빈 Cell에 Template/Safety Rule을 content Evidence처럼 보여주지 않는다.
"""

from __future__ import annotations

import json

from ..planning.application.monthly_dto import (
    ActivityRegenerationOutcome,
    MonthlyGenerationRun,
)
from ..planning.domain.constraint import CellState, ConstraintAssessment
from ..planning.domain.errors import PlanningError
from ..planning.domain.monthly_plan import MonthlyPlan, MonthlyPlanItem
from ..planning.domain.monthly_template import SectionRole
from ..planning.domain.provenance import EvidenceSourceType
from ..planning.rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_SELECTION_RULE_ID,
)
from ..planning.domain.plan import PlanStatus, YearlyPlan

LINE = "=" * 68
THIN = "-" * 68

CELL_STATE_MARK: dict[CellState, str] = {
    CellState.FILLED: "[FILLED]          ",
    CellState.EMPTY_VALID: "[EMPTY_VALID]     ",
    CellState.EMPTY_UNRESOLVED: "[EMPTY_UNRESOLVED]",
}
"""세 상태를 폭을 맞춰 구분한다. 빈 두 상태를 같은 문자열로 표시하지 않는다."""

CELL_STATE_NOTE: dict[CellState, str] = {
    CellState.FILLED: "값 있음",
    CellState.EMPTY_VALID: "채울 근거가 없는 것이 정상",
    CellState.EMPTY_UNRESOLVED: "채워야 하는데 source가 없음",
}

RULE_ONLY_EXPLANATION = "Rule이 상위 anchor에서 파생했고 LLM은 사용하지 않았습니다."
ACTIVITY_RULE_EXPLANATION = (
    "Rule이 승인된 Activity Catalog 후보 중에서 골랐고 LLM은 사용하지 않았습니다. "
    "값은 Catalog의 canonical label 그대로입니다."
)


def _rule_explanation(item: "MonthlyPlanItem") -> str:
    """어느 Rule이 값을 만들었는지에 따라 설명을 고른다.

    theme와 outdoor는 서로 다른 Rule을 쓰므로 같은 문장으로 설명하면 틀린다.
    """
    if item.generation.rule_id == ACTIVITY_SELECTION_RULE_ID:
        return ACTIVITY_RULE_EXPLANATION
    return RULE_ONLY_EXPLANATION
CONFIRM_SEMANTICS = (
    "CONFIRMED는 교사가 작성 결과를 확정했다는 뜻이며 "
    "법정 안전교육 충족을 뜻하지 않습니다."
)


def _week_label(item: MonthlyPlanItem) -> str:
    """`W1` / `W12` / `병합`. 자리수가 늘어나도 열이 밀리지 않게 왼쪽 정렬로 채운다."""
    if item.week_id is None:
        return "병합"
    return f"W{item.week_id.value.split('-W')[-1]}".ljust(3)


# ------------------------------------------------------------------ 배너


def format_banner(
    *,
    school_year: int,
    target_month: str,
    classroom_ref: str,
    ages: frozenset[int],
    age_mode: str,
    parent: YearlyPlan,
    template_ref,
    safety_rule_version: str,
    has_monthly_plan: bool,
) -> str:
    parent_period = parent.period(target_month)
    parent_theme = parent_period.theme.value if parent_period else "(없음)"
    age_text = "·".join(str(a) for a in sorted(ages))
    lines = [
        LINE,
        " 쓱싹요정 Monthly Dev Harness   (제품 FE가 아님)",
        LINE,
        f" School Year   : {school_year}",
        f" Target Month  : {target_month}",
        f" Classroom     : {classroom_ref}",
        f" Ages          : 만 {age_text}세 ({age_mode})",
        THIN,
        f" Parent Yearly : {parent.plan_id.value}",
        f" Parent Status : {parent.status.value}",
        f" Parent Theme  : {parent_theme}",
        THIN,
        f" Template      : {template_ref.template_id}",
        f"                 {template_ref.template_version}",
        f" Safety Rule   : {safety_rule_version}",
        THIN,
        f" Monthly Plan  : {'생성됨' if has_monthly_plan else '아직 없음'}",
        f" LLM           : 사용 안 함 (M1 Monthly는 LLM dependency 없음)",
        " 저장          : InMemory (종료 시 소멸)",
        LINE,
    ]
    return "\n".join(lines)


# ------------------------------------------------------------ Plan 보기


def format_monthly_plan(plan: MonthlyPlan) -> str:
    lines = [
        LINE,
        f" Monthly Plan {plan.target_month.value} | {plan.classroom_ref} | "
        f"{plan.status.value}",
        LINE,
        f" Plan ID       : {plan.plan_id.value}",
        f" School Year   : {plan.school_year}",
        f" Template      : {plan.template_ref.template_version}",
        "",
        " Theme",
    ]
    theme = plan.section("theme")
    if theme is None or not theme.items:
        lines.append("   (Section 없음)")
    else:
        for item in theme.items:
            lines.append(f"   {CELL_STATE_MARK[item.cell_state]} {item.value or ''}")

    lines += ["", " Weeks"]
    for week in plan.week_periods:
        active = "" if week.active else "   (비활성)"
        lines.append(
            f"   {week.week_id.value}  "
            f"{week.start_date.strftime('%m/%d')}~{week.end_date.strftime('%m/%d')}  "
            f"{week.display_label}{active}"
        )

    for section in plan.sections:
        if section.section_key == "theme":
            continue
        lines += ["", f" {section.section_key}"]
        if section.role is SectionRole.AXIS:
            lines.append("   (structural axis — Item 없음)")
            continue
        if not section.items:
            lines.append("   (Cell 없음)")
            continue
        for item in section.items:
            value = item.value or ""
            lines.append(
                f"   {_week_label(item)}  {CELL_STATE_MARK[item.cell_state]} {value}"
            )
            activity_id = _activity_source_id(item)
            if activity_id is not None:
                lines.append(f"              ↳ activity_id {activity_id}")

    lines += [
        THIN,
        f" WeekPeriod {len(plan.week_periods)}개 · Section {len(plan.sections)}개 · "
        f"content Cell {len(plan.items)}개",
        f" Parent lineage : {plan.parent_lineage.parent_yearly_plan_id} / "
        f"{plan.parent_lineage.parent_yearly_period_key} / "
        f"anchor={plan.parent_lineage.parent_yearly_theme_id}",
        f" Activity Catalog: {_activity_catalog_label(plan)}",
        LINE,
    ]
    return "\n".join(lines)


def _activity_source_id(item: MonthlyPlanItem) -> str | None:
    """Cell이 어떤 Activity를 담고 있는지. 없으면 None이다."""
    for source in item.evidence:
        if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE:
            return source.source_id
    return None


def _activity_catalog_label(plan: MonthlyPlan) -> str:
    """Plan에 고정된 Activity Catalog. Regenerate가 이 version을 다시 쓴다."""
    lineage = plan.activity_catalog
    if lineage is None:
        return "(없음 — Activity Reference 없이 생성된 Plan)"
    return f"{lineage.catalog_id} @ {lineage.catalog_version}"


def format_generate_result(plan: MonthlyPlan, run: MonthlyGenerationRun) -> str:
    counts = {s.section_key: len(s.items) for s in plan.sections}
    return "\n".join(
        [
            "[성공] GenerateMonthlyPlan",
            f"  Plan ID        : {plan.plan_id.value}",
            f"  Status         : {plan.status.value}",
            f"  Target Month   : {plan.target_month.value}",
            f"  Parent lineage : {plan.parent_lineage.parent_yearly_plan_id} "
            f"({plan.parent_lineage.parent_yearly_period_key})",
            f"  Parent anchor  : {plan.parent_lineage.parent_yearly_theme_id}",
            f"  WeekPeriod     : {len(plan.week_periods)}개",
            f"  Section        : {len(plan.sections)}개  {counts}",
            f"  content Cell   : {len(plan.items)}개",
            f"  Activity Catalog: {_activity_catalog_label(plan)}",
            f"  Activity Cell  : FILLED {run.activity_filled_cell_count}개 / "
            f"후보 없어 비움 {run.activity_unfilled_cell_count}개",
        ]
    )


# ------------------------------------------------- Edit / Regenerate


def format_edit_result(
    section_key: str,
    week_id: str | None,
    item: MonthlyPlanItem,
    *,
    previous_value: str,
    previous_state: CellState,
) -> str:
    where = week_id or "merged"
    return "\n".join(
        [
            f"[성공] Cell 수정  {section_key} / {where}",
            f"  이전 value     : {previous_value or '(빈 값)'}",
            f"  새 value       : {item.value or '(빈 값)'}",
            f"  이전 CellState : {previous_state.value}",
            f"  새 CellState   : {item.cell_state.value}  "
            f"({CELL_STATE_NOTE[item.cell_state]})",
            f"  generation     : {item.generation.method.value} (변경 없음)",
            f"  Evidence       : {len(item.evidence)}건 보존",
            f"  audit          : {' → '.join(e.event_type.value for e in item.audit.events)}",
            "",
            "  ℹ 교사 수정은 Evidence Source를 만들지 않고 Generation Method도",
            "    덮어쓰지 않습니다. TEACHER_EDITED Audit Event로만 남습니다.",
        ]
    )


def format_regenerate_result(
    section_key: str,
    item: MonthlyPlanItem,
    *,
    previous_value: str,
    anchor_theme_id: str,
) -> str:
    same = item.value == previous_value
    lines = [
        f"[성공] Cell 재생성  {section_key}",
        f"  이전 value     : {previous_value or '(빈 값)'}",
        f"  새 value       : {item.value or '(빈 값)'}",
        f"  same_value     : {str(same).lower()}",
        f"  CellState      : {item.cell_state.value}",
        f"  generation     : {item.generation.method.value} "
        f"/ {item.generation.rule_id} {item.generation.rule_version}",
        f"  parent anchor  : {anchor_theme_id} (변경 없음)",
        f"  audit          : {' → '.join(e.event_type.value for e in item.audit.events)}",
        "",
        f"  → {RULE_ONLY_EXPLANATION}",
    ]
    if same:
        lines += [
            "",
            "  ℹ 재생성은 성공했지만 생성된 값이 기존 값과 동일합니다.",
            "    Contract상 Regenerate가 값을 반드시 바꿔야 하는 것은 아니므로",
            "    이것은 오류가 아닙니다.",
        ]
    return "\n".join(lines)


# -------------------------------------------------------- Provenance


def format_cell_provenance(
    section_key: str, week_id: str | None, item: MonthlyPlanItem
) -> str:
    where = week_id or "merged"
    lines = [
        LINE,
        f" [{section_key} / {where}] Cell 상세 근거",
        LINE,
        f" item_id      : {item.item_id.value}",
        f" semantic_key : {item.semantic_key.value}",
        f" week_id      : {item.week_id.value if item.week_id else 'None (월간 병합 Cell)'}",
        f" value        : {item.value or '(빈 값)'}",
        f" cell_state   : {item.cell_state.value}  ({CELL_STATE_NOTE[item.cell_state]})",
        THIN,
        " [1축] Evidence Source — 내용의 근거",
    ]
    if item.evidence:
        for e in item.evidence:
            lines.append(f"   - source_type    : {e.source_type.value}")
            lines.append(f"     source_id      : {e.source_id}")
            lines.append(f"     source_version : {e.source_version or '-'}")
            if e.display_name:
                lines.append(f"     display_name   : {e.display_name}")
    else:
        lines += [
            "   (content Evidence 없음)",
            "   값이 없으므로 근거도 없습니다. 왜 비어 있는지는 cell_state와",
            "   Constraint Status 메뉴가 설명합니다.",
            "   Template과 Safety Rule은 구조·법정 근거이지 이 Cell의 content",
            "   Evidence가 아니므로 여기 표시하지 않습니다.",
        ]

    lines += [
        THIN,
        " [2축] Generation Method — 생성 방식",
        f"   method       : {item.generation.method.value}",
        f"   applied rule : {item.generation.rule_id} {item.generation.rule_version}",
        f"   → {_rule_explanation(item)}",
        THIN,
        " [3축] Audit History — 생성 이후의 변경",
    ]
    for e in item.audit.events:
        who = e.actor_id.value if e.actor_id else (e.system_actor or "-")
        line = f"   - {e.event_type.value:<16} {e.occurred_at.isoformat()}  by {who}"
        lines.append(line)
        if e.previous_value is not None and e.previous_value != e.new_value:
            lines.append(
                f"       '{e.previous_value}' → '{e.new_value}'"
            )
    lines.append(LINE)
    return "\n".join(lines)


# --------------------------------------------------------- Constraint


def format_constraints(assessments: tuple[ConstraintAssessment, ...]) -> str:
    if not assessments:
        return " ConstraintAssessment 없음"
    lines = [LINE, " Constraint Status", LINE]
    for a in assessments:
        lines += [
            f" kind                  : {a.kind.value}",
            f" verification          : {a.verification.value}",
            f" rule_version          : {a.rule_version}",
            f" required_source_kinds : {list(a.required_source_kinds)}",
            f" affected_section_keys : {list(a.affected_section_keys)}",
            f" detail                : {a.detail}",
            THIN,
        ]
    lines.append(
        " ℹ 이 상태는 fallback도 Optional Context 실패도 generation failure도"
    )
    lines.append("   아닙니다. 별도의 unresolved requirement입니다.")
    lines.append(LINE)
    return "\n".join(lines)


# ------------------------------------------------------ GenerationRun


def format_generation_run(run: MonthlyGenerationRun) -> str:
    return "\n".join(
        [
            LINE,
            " MonthlyGenerationRun",
            LINE,
            f" run_id                      : {run.run_id}",
            f" template                    : {run.template_id}",
            f"                               {run.template_version}",
            f" safety_legal_rule_version   : {run.safety_legal_rule_version}",
            THIN,
            f" week_period_count           : {run.week_period_count}",
            f" generated_cell_count        : {run.generated_cell_count}",
            f" filled_cell_count           : {run.filled_cell_count}",
            f" empty_valid_cell_count      : {run.empty_valid_cell_count}",
            f" empty_unresolved_cell_count : {run.empty_unresolved_cell_count}",
            THIN,
            f" activity_catalog_id         : {run.activity_catalog_id or '-'}",
            f" activity_catalog_version    : {run.activity_catalog_version or '-'}",
            f" activity_filled_cell_count  : {run.activity_filled_cell_count}",
            f" activity_unfilled_cell_count: {run.activity_unfilled_cell_count}",
            f" activity_selection_traces   : {len(run.activity_selection_traces)}건",
            THIN,
            f" llm_invoked                 : {str(run.llm_invoked).lower()}",
            f" llm_call_count              : {run.llm_call_count}",
            f" llm_item_count              : {run.llm_item_count}",
            THIN,
            f" fallbacks_used              : {list(run.fallbacks_used) or '없음'}",
            f" unresolved_requirements     : {len(run.unresolved_requirements)}건",
            *[
                f"   - {a.kind.value} / {a.verification.value}"
                for a in run.unresolved_requirements
            ],
            "",
            " ℹ unresolved_requirements는 fallbacks_used와 다른 개념입니다.",
            LINE,
        ]
    )


# ------------------------------------------- Activity Selection (M2-C / M2-D)


def format_activity_selection_traces(run: MonthlyGenerationRun) -> str:
    """Generate가 outdoor Cell마다 왜 그 Activity를 골랐는지.

    Domain truth의 사본이 아니라 **선택 이유**만 보여 준다. Catalog 내용이나
    후보 목록 전체를 여기에 펼치지 않는다.
    """
    lines = [
        LINE,
        " Activity Selection Trace",
        LINE,
        f" catalog : {run.activity_catalog_id or '-'} @ "
        f"{run.activity_catalog_version or '-'}",
        f" 결과    : FILLED {run.activity_filled_cell_count}개 · "
        f"후보 없어 비움 {run.activity_unfilled_cell_count}개",
    ]
    if not run.activity_selection_traces:
        lines += [
            THIN,
            " (Activity Reference를 쓰지 않고 생성된 Plan입니다)",
            LINE,
        ]
        return "\n".join(lines)

    for trace in run.activity_selection_traces:
        lines += [
            THIN,
            f" {trace.week_id or 'merged'}  [{trace.reason}]",
            f"   selected      : {trace.selected_activity_id or '(없음)'}",
            f"   label         : {trace.selected_label or '(없음)'}",
            f"   candidates    : {trace.candidate_count}개",
            f"   evidence 강도 : {trace.evidence_strength}",
            f"   repeat penalty: {trace.repeat_penalty} "
            f"(같은 달 재사용={str(trace.reused_in_month).lower()}, "
            f"현재 Activity={str(trace.is_current_activity).lower()})",
            f"   theme 일치    : {str(trace.theme_matched).lower()} "
            f"(anchor={trace.parent_theme_id or '-'})",
            f"   누리과정 영역 : {list(trace.selected_curriculum_domains) or '없음'} "
            f"(중복 penalty={trace.curriculum_repeat_penalty})",
            f"   rule          : {trace.rule_id} {trace.rule_version}",
        ]
        if trace.all_candidates_penalized:
            lines.append("   ⚠ 모든 후보가 penalty를 받아 반복을 피할 수 없었습니다.")
    lines += [
        "",
        " ℹ 반복·theme·누리과정은 순위 가점 요소이며 hard filter가 아닙니다.",
        LINE,
    ]
    return "\n".join(lines)


def format_activity_regenerate_result(
    outcome: ActivityRegenerationOutcome, item: MonthlyPlanItem
) -> str:
    """outdoor Cell 재생성 결과. theme 재생성과 다른 Rule을 쓰므로 표시도 분리한다."""
    trace = outcome.trace
    lines = [
        f"[성공] Cell 재생성  {outcome.address.section_key} "
        f"/ {outcome.address.week_id or 'merged'}",
        f"  이전 activity  : {outcome.previous_activity_id or '(Activity 근거 없음)'}",
        f"  이전 value     : {outcome.previous_value or '(빈 값)'}",
        f"  새 activity    : {outcome.selected_activity_id}",
        f"  새 value       : {outcome.selected_value}",
        f"  activity 변경  : {str(outcome.activity_changed).lower()}",
        f"  value 변경     : {str(outcome.value_changed).lower()}",
        f"  CellState      : {item.cell_state.value}",
        f"  generation     : {item.generation.method.value} "
        f"/ {item.generation.rule_id} {item.generation.rule_version}",
        f"  catalog        : {outcome.catalog_id} @ {outcome.catalog_version}",
        f"  선택 이유      : {outcome.reason}  (후보 {trace.candidate_count}개)",
        f"  audit          : {' → '.join(e.event_type.value for e in item.audit.events)}",
        "",
        f"  → {ACTIVITY_RULE_EXPLANATION}",
        "  → Catalog version은 Plan 생성 시점에 고정된 값입니다. 최신 Catalog로",
        "    자동 승격하지 않습니다.",
    ]
    if not outcome.value_changed:
        lines += [
            "",
            "  ℹ 재생성은 성공했지만 값이 기존과 동일합니다. 현재 Activity는 배제가",
            "    아니라 penalty이므로 대안이 없으면 같은 값이 유지됩니다.",
        ]
    return "\n".join(lines)


# ------------------------------------------------------------- Audit


def format_audit(plan: MonthlyPlan) -> str:
    lines = [LINE, " Audit History", LINE, " [Plan level]"]
    for e in plan.audit.events:
        who = e.actor_id.value if e.actor_id else (e.system_actor or "-")
        lines.append(
            f"   - {e.event_type.value:<16} {e.occurred_at.isoformat()}  by {who}"
        )

    lines += ["", " [Cell level]"]
    any_cell = False
    for section in plan.sections:
        for item in section.items:
            beyond = [e for e in item.audit.events if e.event_type.value != "CREATED"]
            if not beyond:
                continue
            any_cell = True
            where = item.week_id.value if item.week_id else "merged"
            lines.append(f"   {section.section_key} / {where}  ({item.item_id.value})")
            for e in item.audit.events:
                who = e.actor_id.value if e.actor_id else (e.system_actor or "-")
                lines.append(
                    f"     - {e.event_type.value:<16} "
                    f"{e.occurred_at.isoformat()}  by {who}"
                )
                if e.previous_value is not None and e.previous_value != e.new_value:
                    lines.append(f"         '{e.previous_value}' → '{e.new_value}'")
    if not any_cell:
        lines.append("   (CREATED 이후 변경 없음)")
    lines.append(LINE)
    return "\n".join(lines)


# ----------------------------------------------------------- Confirm


def format_confirm_result(plan: MonthlyPlan, *, previous_status: PlanStatus) -> str:
    unresolved = plan.unresolved_constraints
    lines = [
        f"[성공] Monthly Confirm   {previous_status.value} → {plan.status.value}",
    ]
    event = plan.audit.events[-1]
    who = event.actor_id.value if event.actor_id else "-"
    lines += [
        f"  확정자    : {who}",
        f"  확정 시각 : {event.occurred_at.isoformat()}",
    ]
    for a in unresolved:
        lines.append(
            f"  Constraint: {a.kind.value} = {a.verification.value} (변경 없음)"
        )
    lines += [
        "",
        f"  ℹ {CONFIRM_SEMANTICS}",
        "    CONFIRMED ≠ Safety VERIFIED",
        "    이제 수정·재생성이 Application Gate에서 차단됩니다.",
    ]
    return "\n".join(lines)


# --------------------------------------------------- 진단 / 오류


def format_weekly_gate_result(plan: MonthlyPlan, error: PlanningError | None) -> str:
    lines = [
        " Weekly Gate 진단 — require_confirmed_parent_monthly",
        f"   Monthly status : {plan.status.value}",
        f"   unresolved     : {len(plan.unresolved_constraints)}건",
    ]
    if error is None:
        lines += [
            "   결과           : PASS",
            "",
            "   ℹ Safety가 NOT_VERIFIED_SOURCE_REQUIRED여도 CONFIRMED면 통과합니다.",
            "     CONFIRMED ≠ Safety verified 이기 때문입니다.",
        ]
    else:
        lines += [
            "   결과           : BLOCKED",
            f"   category       : {error.failure_category.value}",
            f"   rule           : {error.violated_rule}",
        ]
    lines.append("\n   (Weekly 생성 기능은 구현하지 않았습니다. Gate 진단 전용입니다.)")
    return "\n".join(lines)


def format_planning_error(operation: str, error: PlanningError) -> str:
    lines = [f"[실패] {operation}", f"  outcome  : {error.outcome.value}"]
    for v in error.violations:
        lines += [
            f"  category : {v.category.value}",
            f"  rule     : {v.violated_rule}",
            f"  message  : {v.detail}",
        ]
        if v.period_key:
            lines.append(f"  period   : {v.period_key}")
    return "\n".join(lines)


# --------------------------------------------------------- Raw dump


def format_raw_dump(plan: MonthlyPlan, run: MonthlyGenerationRun | None) -> str:
    """Harness-side formatter. Production Contract를 바꾸지 않는다."""
    payload = {
        "plan": {
            "plan_id": plan.plan_id.value,
            "school_year": plan.school_year,
            "target_month": plan.target_month.value,
            "daycare_ref": plan.daycare_ref,
            "classroom_ref": plan.classroom_ref,
            "classroom_ages": sorted(plan.classroom_ages),
            "age_mode": plan.age_mode,
            "status": plan.status.value,
            "template_ref": {
                "template_id": plan.template_ref.template_id,
                "template_version": plan.template_ref.template_version,
            },
            "parent_lineage": {
                "parent_yearly_plan_id": plan.parent_lineage.parent_yearly_plan_id,
                "parent_yearly_period_key": plan.parent_lineage.parent_yearly_period_key,
                "parent_yearly_theme_id": plan.parent_lineage.parent_yearly_theme_id,
                "parent_yearly_value": plan.parent_lineage.parent_yearly_value,
                "reference_catalog_id": plan.parent_lineage.reference_catalog_id,
                "reference_version": plan.parent_lineage.reference_version,
                "confirmed_by": plan.parent_lineage.confirmed_by,
            },
            "week_periods": [
                {
                    "week_id": w.week_id.value,
                    "start_date": w.start_date.isoformat(),
                    "end_date": w.end_date.isoformat(),
                    "display_label": w.display_label,
                    "active": w.active,
                }
                for w in plan.week_periods
            ],
            "sections": [
                {
                    "section_key": s.section_key,
                    "role": s.role.value,
                    "display_mode": s.display_mode.value if s.display_mode else None,
                    "items": [
                        {
                            "item_id": i.item_id.value,
                            "semantic_key": i.semantic_key.value,
                            "week_id": i.week_id.value if i.week_id else None,
                            "value": i.value,
                            "cell_state": i.cell_state.value,
                            "generation": {
                                "method": i.generation.method.value,
                                "rule_id": i.generation.rule_id,
                                "rule_version": i.generation.rule_version,
                            },
                            "evidence": [
                                {
                                    "source_type": e.source_type.value,
                                    "source_id": e.source_id,
                                    "source_version": e.source_version,
                                }
                                for e in i.evidence
                            ],
                            "audit": [e.event_type.value for e in i.audit.events],
                        }
                        for i in s.items
                    ],
                }
                for s in plan.sections
            ],
            "constraint_assessments": [
                {
                    "kind": a.kind.value,
                    "verification": a.verification.value,
                    "rule_version": a.rule_version,
                    "required_source_kinds": list(a.required_source_kinds),
                    "affected_section_keys": list(a.affected_section_keys),
                }
                for a in plan.constraint_assessments
            ],
            "audit": [e.event_type.value for e in plan.audit.events],
        },
        "run": None
        if run is None
        else {
            "run_id": run.run_id,
            "template_id": run.template_id,
            "template_version": run.template_version,
            "safety_legal_rule_version": run.safety_legal_rule_version,
            "week_period_count": run.week_period_count,
            "generated_cell_count": run.generated_cell_count,
            "filled_cell_count": run.filled_cell_count,
            "empty_valid_cell_count": run.empty_valid_cell_count,
            "empty_unresolved_cell_count": run.empty_unresolved_cell_count,
            "llm_invoked": run.llm_invoked,
            "llm_call_count": run.llm_call_count,
            "fallbacks_used": list(run.fallbacks_used),
            "unresolved_requirements": len(run.unresolved_requirements),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
