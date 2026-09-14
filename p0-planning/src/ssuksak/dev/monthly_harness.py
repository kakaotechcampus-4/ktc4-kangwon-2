"""Monthly Dev Harness CLI.

실행:

    python -m pip install -e .
    python -m ssuksak.dev.monthly_harness
    python -m ssuksak.dev.monthly_harness --month 2026-03
    python -m ssuksak.dev.monthly_harness --debug

Yearly Harness(`yearly_harness.py`)는 frozen baseline이므로 건드리지 않는다.
Monthly는 별도 CLI다.

**상태 변경은 전부 Application Use Case를 통해서만 한다.** 이 모듈은 Domain
Aggregate나 MonthlyPlanItem을 직접 수정하지 않고 읽어서 표시만 한다.

**Monthly M1은 LLM dependency가 없다.** 네트워크도 필요하지 않다.
"""

from __future__ import annotations

import argparse
import sys
import traceback

from ..planning.application.monthly_dto import (
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ..planning.domain.errors import PlanningError
from ..planning.domain.identifiers import ActorId, InvalidIdentifierError
from ..planning.domain.monthly_template import SectionRole
from ..planning.rules import gates
from . import monthly_formatting as fmt
from .monthly_wiring import (
    DEFAULT_TARGET_MONTH,
    DEV_ACTOR,
    MonthlyHarnessSession,
    MonthlyWiring,
    build_monthly_wiring,
)
from .parsing import HarnessInputError, parse_menu_choice

MENU = """
[1] 현재 Monthly Plan 보기
[2] Cell 수정            (DRAFT만)
[3] Cell 재생성          (DRAFT만 · theme / outdoor_play)
[4] Cell 상세 근거 (Provenance 3축)
[5] Constraint Status
[6] Generation Run
[7] Audit History
[8] Monthly Confirm
[9] Duplicate Generate 확인   (개발 Contract 확인용)
[10] Weekly Gate 확인         (진단 전용 · Weekly 생성 아님)
[11] Raw JSON 덤프 (디버그)
[12] Activity Selection Trace  (왜 그 활동을 골랐는가)
[0] 종료
"""
CHOICES = tuple(str(i) for i in range(13))

_OPERATION_NAMES = {
    "2": "Cell 수정",
    "3": "Cell 재생성",
    "8": "Monthly Confirm",
    "9": "Duplicate Generate",
}


# ------------------------------------------------------------------ 입력


def _ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _ask_until_valid(prompt: str, parser):
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return None
        try:
            return parser(raw)
        except HarnessInputError as exc:
            print(f"  ! {exc}")


def _ask_actor(prompt: str = "  actor_id (빈 값이면 teacher_dev_001): ") -> ActorId | None:
    """opaque ActorId를 입력받는다.

    OD-Y03: 담임 표시 이름은 Actor 식별자를 대체하지 못한다.
    OD-N10의 reviewer 식별자와도 다른 개념이다.
    """
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return None
        raw = raw.strip()
        if not raw:
            return DEV_ACTOR
        try:
            return ActorId(raw)
        except InvalidIdentifierError as exc:
            print(f"  ! {exc}")


def _content_sections(session: MonthlyHarnessSession) -> list[str]:
    """차단 Cell도 숨기지 않는다. 왜 차단되는지 확인하는 것도 Harness 목적이다."""
    return [
        s.section_key
        for s in session.plan.sections
        if s.role is not SectionRole.AXIS
    ]


def _ask_address(session: MonthlyHarnessSession) -> MonthlyCellAddress | None:
    keys = _content_sections(session)
    print(f"  Section 후보: {', '.join(keys)}")
    section_key = _ask("  section_key: ").strip()
    if not section_key:
        return None

    section = session.plan.section(section_key)
    week_id: str | None = None
    if section is not None and section.display_mode is not None:
        if section.display_mode.value == "WEEKLY_CELLS":
            weeks = [w.week_id.value for w in session.plan.active_week_periods]
            print(f"  week 후보: {', '.join(weeks)}")
            raw = _ask("  week_id (또는 순번 1~N): ").strip()
            if not raw:
                return None
            week_id = (
                weeks[int(raw) - 1]
                if raw.isdigit() and 1 <= int(raw) <= len(weeks)
                else raw
            )
    return MonthlyCellAddress(
        target_month=session.plan.target_month.value,
        section_key=section_key,
        week_id=week_id,
    )


# --------------------------------------------------------------- Generate


def _initial_generate(wiring: MonthlyWiring, session: MonthlyHarnessSession) -> None:
    """startup 자동 실행.

    Yearly Harness가 Generate를 startup에서 자동 실행하고 메뉴는 생성 이후
    동작만 두는 패턴을 따른다. Monthly도 Plan 없이는 대부분의 메뉴가 의미가
    없으므로 같은 구조가 일관적이다.
    """
    result = wiring.generate.execute(
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
            activity_catalog=wiring.activity_catalog,
        )
    )
    session.adopt(result.plan)
    session.absorb_run(result.run)
    print()
    print(fmt.format_generate_result(result.plan, result.run))


# ------------------------------------------------------------------ 메뉴


def _edit(wiring: MonthlyWiring, session: MonthlyHarnessSession) -> None:
    address = _ask_address(session)
    if address is None:
        return
    found = session.plan.find_cell(
        section_key=address.section_key, week_id=address.week_id
    )
    if found is not None:
        _, current = found
        print(f"  현재 value     : {current.value or '(빈 값)'}")
        print(f"  현재 CellState : {current.cell_state.value}")
        previous_value, previous_state = current.value, current.cell_state
    else:
        previous_value, previous_state = "", None

    new_value = _ask("  새 value (빈 값 허용 여부는 Section 정책이 결정): ")
    actor = _ask_actor()
    if actor is None:
        return

    result = wiring.edit.execute(
        EditMonthlyPlanItemCommand(
            plan_id=session.plan_id,
            address=address,
            new_value=new_value,
            actor_id=actor,
        )
    )
    session.adopt(result.plan)
    _, updated = session.plan.find_cell(
        section_key=address.section_key, week_id=address.week_id
    )
    print()
    print(
        fmt.format_edit_result(
            address.section_key,
            address.week_id,
            updated,
            previous_value=previous_value,
            previous_state=previous_state or updated.cell_state,
        )
    )


def _regenerate(wiring: MonthlyWiring, session: MonthlyHarnessSession) -> None:
    print("  재생성 가능한 Cell은 theme와 outdoor_play입니다.")
    print("  두 Section은 서로 다른 Rule을 씁니다.")
    print("    theme        : 상위 Yearly anchor에서 재파생")
    print("    outdoor_play : Plan에 고정된 Activity Catalog + Selection Rule")
    print("  safety_education을 선택하면 실제 Use Case가 차단합니다.")
    address = _ask_address(session)
    if address is None:
        return
    found = session.plan.find_cell(
        section_key=address.section_key, week_id=address.week_id
    )
    previous_value = found[1].value if found else ""

    actor = _ask_actor()
    if actor is None:
        return

    result = wiring.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=session.plan_id, address=address, actor_id=actor
        )
    )
    session.adopt(result.plan)
    _, updated = session.plan.find_cell(
        section_key=address.section_key, week_id=address.week_id
    )
    print()
    if result.activity_regeneration is not None:
        # outdoor는 theme와 다른 Rule을 쓰므로 표시도 분리한다.
        print(
            fmt.format_activity_regenerate_result(
                result.activity_regeneration, updated
            )
        )
        return
    print(
        fmt.format_regenerate_result(
            address.section_key,
            updated,
            previous_value=previous_value,
            anchor_theme_id=session.plan.parent_lineage.parent_yearly_theme_id,
        )
    )


def _provenance(session: MonthlyHarnessSession) -> None:
    address = _ask_address(session)
    if address is None:
        return
    found = session.plan.find_cell(
        section_key=address.section_key, week_id=address.week_id
    )
    if found is None:
        print(f"  ! Cell을 찾을 수 없습니다: {address}")
        return
    print()
    print(fmt.format_cell_provenance(address.section_key, address.week_id, found[1]))


def _confirm(wiring: MonthlyWiring, session: MonthlyHarnessSession) -> None:
    print(f"  현재 상태: {session.plan.status.value}")
    print("  확정해도 외부 기관으로 자동 제출되지 않습니다.")
    print(f"  {fmt.CONFIRM_SEMANTICS}")
    if _ask("  확정하시겠습니까? (y/N): ").strip().lower() != "y":
        print("  취소했습니다.")
        return
    actor = _ask_actor()
    if actor is None:
        return

    previous_status = session.plan.status
    result = wiring.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=session.plan_id, actor_id=actor)
    )
    session.adopt(result.plan)
    print()
    print(fmt.format_confirm_result(result.plan, previous_status=previous_status))


def _duplicate_check(wiring: MonthlyWiring, session: MonthlyHarnessSession) -> None:
    """개발 Contract 확인용. Product 기능이 아니다."""
    before = wiring.monthly_plans.stored_count
    print(f"  같은 (classroom, target_month)로 Generate를 다시 시도합니다.")
    print(f"  기존 Plan {before}건 · status={session.plan.status.value}")
    wiring.generate.execute(
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
            activity_catalog=wiring.activity_catalog,
        )
    )
    print("  ! 차단되지 않았습니다. Duplicate Contract를 확인하세요.")


def _weekly_gate_check(session: MonthlyHarnessSession) -> None:
    """진단 전용. Weekly 생성 기능이 아니다."""
    error: PlanningError | None = None
    try:
        gates.require_confirmed_parent_monthly(session.plan)
    except PlanningError as exc:
        error = exc
    print()
    print(fmt.format_weekly_gate_result(session.plan, error))


# ------------------------------------------------------------------ 루프


def _run_loop(
    wiring: MonthlyWiring, session: MonthlyHarnessSession, *, debug: bool
) -> None:
    while True:
        print(MENU)
        try:
            raw = input("선택> ")
        except EOFError:
            print("\n종료합니다. InMemory Plan은 소멸합니다.")
            return
        try:
            choice = parse_menu_choice(raw, CHOICES)
        except HarnessInputError as exc:
            print(f"  ! {exc}")
            continue

        if choice == "0":
            print("종료합니다. InMemory Plan은 소멸합니다.")
            return

        try:
            if choice == "1":
                print(fmt.format_monthly_plan(session.plan))
            elif choice == "2":
                _edit(wiring, session)
            elif choice == "3":
                _regenerate(wiring, session)
            elif choice == "4":
                _provenance(session)
            elif choice == "5":
                print(fmt.format_constraints(session.plan.constraint_assessments))
            elif choice == "6":
                if session.run is None:
                    print("  GenerationRun이 없습니다.")
                else:
                    print(fmt.format_generation_run(session.run))
            elif choice == "7":
                print(fmt.format_audit(session.plan))
            elif choice == "8":
                _confirm(wiring, session)
            elif choice == "9":
                _duplicate_check(wiring, session)
            elif choice == "10":
                _weekly_gate_check(session)
            elif choice == "11":
                print(fmt.format_raw_dump(session.plan, session.run))
            elif choice == "12":
                if session.run is None:
                    print("  GenerationRun이 없습니다.")
                else:
                    print(fmt.format_activity_selection_traces(session.run))
        except PlanningError as exc:
            print()
            print(
                fmt.format_planning_error(
                    _OPERATION_NAMES.get(choice, f"메뉴 {choice}"), exc
                )
            )
            if debug:
                traceback.print_exc()
        except Exception as exc:  # noqa: BLE001 - Harness가 죽지 않게 한다
            print(f"[오류] 예상하지 못한 문제: {type(exc).__name__}: {exc}")
            if debug:
                traceback.print_exc()


# ------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ssuksak.dev.monthly_harness",
        description="쓱싹요정 Monthly Dev Harness (제품 FE가 아님)",
    )
    parser.add_argument(
        "--month",
        default=DEFAULT_TARGET_MONTH,
        help=f"대상 월 YYYY-MM (기본 {DEFAULT_TARGET_MONTH})",
    )
    parser.add_argument("--debug", action="store_true", help="traceback 표시")
    args = parser.parse_args(argv)

    try:
        wiring = build_monthly_wiring(target_month=args.month)
    except PlanningError as exc:
        print(fmt.format_planning_error("Parent Yearly 준비", exc))
        if args.debug:
            traceback.print_exc()
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[오류] wiring 실패: {type(exc).__name__}: {exc}")
        if args.debug:
            traceback.print_exc()
        return 2

    session = MonthlyHarnessSession()
    print(
        fmt.format_banner(
            school_year=wiring.school_year,
            target_month=wiring.target_month,
            classroom_ref=wiring.classroom.classroom_ref,
            ages=wiring.classroom.ages,
            age_mode=wiring.classroom.effective_age_mode.value,
            parent=wiring.parent_yearly,
            template_ref=wiring.template_ref,
            safety_rule_version=wiring.safety_rule.legal_rule_version,
            has_monthly_plan=session.has_plan,
        )
    )

    try:
        _initial_generate(wiring, session)
    except PlanningError as exc:
        print()
        print(fmt.format_planning_error("Monthly 생성", exc))
        if args.debug:
            traceback.print_exc()
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"\n[오류] Monthly 생성 실패: {type(exc).__name__}: {exc}")
        if args.debug:
            traceback.print_exc()
        return 1

    _run_loop(wiring, session, debug=args.debug)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
