"""Yearly Dev Harness CLI.

실행:

    python -m pip install -e .
    python -m ssuksak.dev.yearly_harness

옵션:

    --no-llm    GenerateYearlyPlan(use_llm=False) 경로. 실제 MLAPI 비용 없음.
    --debug     traceback 표시. 기본 모드에서는 숨긴다.

**상태 변경은 전부 Application Use Case를 통해서만 한다.** 이 모듈은 Domain
Aggregate나 PlanItem을 직접 수정하지 않고, 읽어서 표시만 한다.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import replace

from ..planning.application.dto import (
    ClassroomContext,
    ConfirmYearlyPlanCommand,
    DaycareContext,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
    ItemAddress,
    PlanningSetup,
    RegenerateYearlyPlanItemCommand,
)
from ..planning.domain.errors import PlanningError
from ..planning.domain.identifiers import ActorId, InvalidIdentifierError
from ..planning.domain.provenance import EvidenceSourceType
from ..shared.llm.config import LLMConfigError
from . import formatting as fmt
from .parsing import (
    HarnessInputError,
    parse_age_mode,
    parse_ages,
    parse_menu_choice,
    parse_period_key,
    parse_school_year,
    semantic_key_for_period,
)
from .wiring import (
    DEV_CLASSROOM_REF,
    DEV_DAYCARE_REF,
    HarnessSession,
    HarnessWiring,
    build_wiring,
)

MENU = """
[1] 현재 연간계획 보기
[2] MonthPeriod 수정            (DRAFT만)
[3] MonthPeriod 재생성          (DRAFT만 · LLM 호출 · 비용 발생)
[4] MonthPeriod 상세 근거 보기
[5] 전체 Selection Trace 보기
[6] Yearly Confirm
[7] Audit History 보기
[8] JSON 덤프 (디버그)
[0] 종료
"""
CHOICES = ("0", "1", "2", "3", "4", "5", "6", "7", "8")

DEFAULT_SCHOOL_YEAR = 2026


# ------------------------------------------------------------------ 입력


def _ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return "0"


def _ask_until_valid(prompt: str, parser):
    """파싱이 성공할 때까지 다시 묻는다. EOF면 None을 돌려 종료를 유도한다."""
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return None
        try:
            return parser(raw)
        except HarnessInputError as exc:
            print(f"  ! {exc}")


def _ask_actor(prompt: str = "  actor_id (예: teacher_dev_001): ") -> ActorId | None:
    """opaque ActorId를 직접 입력받는다.

    OD-Y03: 담임 표시 이름은 Actor 식별자를 대체하지 못한다.
    OD-N10의 Theme Reference reviewer 식별자와는 다른 개념이다.
    """
    while True:
        try:
            raw = input(prompt)
        except EOFError:
            return None
        try:
            return ActorId(raw.strip())
        except InvalidIdentifierError as exc:
            print(f"  ! {exc}")


# --------------------------------------------------------------- Generate


def _initial_generate(wiring: HarnessWiring, session: HarnessSession) -> bool:
    print("\n최초 설정을 입력하세요.\n")

    school_year = _ask_until_valid(
        f"  학년도 [{DEFAULT_SCHOOL_YEAR}]: ",
        lambda raw: parse_school_year(raw, default=DEFAULT_SCHOOL_YEAR),
    )
    if school_year is None:
        return False

    ages = _ask_until_valid("  연령 (3 / 4 / 5 / 3,4 / 3,4,5): ", parse_ages)
    if ages is None:
        return False

    age_mode = _ask_until_valid(
        "  classroom mode (SINGLE / MIXED, 빈 값이면 자동): ",
        lambda raw: parse_age_mode(raw, ages),
    )

    command = GenerateYearlyPlanCommand(
        school_year=school_year,
        daycare=DaycareContext(daycare_ref=DEV_DAYCARE_REF),
        classroom=ClassroomContext(
            classroom_ref=DEV_CLASSROOM_REF,
            ages=ages,
            age_mode=age_mode,
        ),
        planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
        catalog=wiring.selector,
    )

    if wiring.live_api:
        print("\n  → 실제 Elice MLAPI를 호출합니다. 잠시 기다려 주세요.")

    result = wiring.generate.execute(command)
    session.adopt(result.plan)
    session.absorb_run(result.run)
    session.llm_records = list(wiring.llm_records)

    print()
    print(fmt.format_yearly_plan(result.plan, catalog=wiring.catalog, run=result.run))
    if session.llm_records:
        print(" LLM telemetry")
        print(fmt.format_llm_records(session.llm_records))
    return True


# ------------------------------------------------------------------ 메뉴


def _show_plan(wiring: HarnessWiring, session: HarnessSession) -> None:
    print(fmt.format_yearly_plan(session.plan, catalog=wiring.catalog))


def _find_item(session: HarnessSession, period_key: str):
    """표시용 조회. Domain을 변경하지 않는다."""
    return session.plan.find_item(
        period_key=period_key, semantic_key=semantic_key_for_period(period_key)
    )


def _theme_id_of(item) -> str | None:
    refs = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    return refs[0].source_id if refs else None


def _edit(wiring: HarnessWiring, session: HarnessSession) -> None:
    period_key = _ask_until_valid(
        "  수정할 월 (예: 5 또는 2026-05): ",
        lambda raw: parse_period_key(raw, session.plan.school_year),
    )
    if period_key is None:
        return

    found = _find_item(session, period_key)
    if found is None:
        print(f"  ! {period_key}를 찾을 수 없습니다.")
        return
    _, item = found

    print(f"  현재 값: {item.value}")
    new_value = _ask("  새 값: ").strip()
    if not new_value:
        print("  ! 빈 값은 사용할 수 없습니다.")
        return

    actor = _ask_actor()
    if actor is None:
        return

    previous_value = item.value
    previous_method = item.generation.method

    result = wiring.edit.execute(
        EditYearlyPlanItemCommand(
            plan_id=session.plan_id,
            address=ItemAddress(
                period_key=period_key,
                semantic_key=semantic_key_for_period(period_key),
            ),
            new_value=new_value,
            actor_id=actor,
        )
    )
    session.adopt(result.plan)

    _, updated = _find_item(session, period_key)
    print()
    print(
        fmt.format_edit_result(
            period_key,
            updated,
            previous_value=previous_value,
            previous_method=previous_method,
        )
    )


def _regenerate(wiring: HarnessWiring, session: HarnessSession) -> None:
    period_key = _ask_until_valid(
        "  재생성할 월 (예: 10 또는 2026-10): ",
        lambda raw: parse_period_key(raw, session.plan.school_year),
    )
    if period_key is None:
        return

    found = _find_item(session, period_key)
    if found is None:
        print(f"  ! {period_key}를 찾을 수 없습니다.")
        return
    _, item = found

    previous_value = item.value
    previous_theme_id = _theme_id_of(item)
    print(f"  현재 theme_id: {previous_theme_id}")
    print(f"  현재 값      : {previous_value}")

    actor = _ask_actor()
    if actor is None:
        return

    if wiring.live_api:
        print("  → 실제 Elice MLAPI 호출을 시도합니다. (Gate에서 차단될 수 있음)")

    before = len(wiring.llm_records)
    result = wiring.regenerate.execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=session.plan_id,
            address=ItemAddress(
                period_key=period_key,
                semantic_key=semantic_key_for_period(period_key),
            ),
            actor_id=actor,
            catalog=wiring.selector,
        )
    )
    session.adopt(result.plan)
    session.absorb_run(result.run)
    session.llm_records = list(wiring.llm_records)

    _, updated = _find_item(session, period_key)
    print()
    print(
        fmt.format_regenerate_result(
            period_key,
            updated,
            previous_value=previous_value,
            previous_theme_id=previous_theme_id,
            new_theme_id=_theme_id_of(updated),
            trace=session.traces.get(period_key),
            run=result.run,
        )
    )
    new_records = wiring.llm_records[before:]
    if new_records:
        print(" LLM telemetry")
        print(fmt.format_llm_records(new_records))


def _evidence(wiring: HarnessWiring, session: HarnessSession) -> None:
    period_key = _ask_until_valid(
        "  볼 월 (예: 4 또는 2026-04): ",
        lambda raw: parse_period_key(raw, session.plan.school_year),
    )
    if period_key is None:
        return
    found = _find_item(session, period_key)
    if found is None:
        print(f"  ! {period_key}를 찾을 수 없습니다.")
        return
    _, item = found
    print()
    print(
        fmt.format_evidence_detail(
            period_key,
            item,
            catalog=wiring.catalog,
            trace=session.traces.get(period_key),
        )
    )


def _confirm(wiring: HarnessWiring, session: HarnessSession) -> None:
    print(f"  현재 상태: {session.plan.status.value}")
    print("  확정해도 외부 기관으로 자동 제출되지 않습니다.")

    answer = _ask("  확정하시겠습니까? (y/N): ").strip().lower()
    if answer not in ("y", "yes"):
        print("  취소했습니다.")
        return

    actor = _ask_actor()
    if actor is None:
        return

    result = wiring.confirm.execute(
        ConfirmYearlyPlanCommand(
            plan_id=session.plan_id, actor_id=actor, catalog=wiring.selector
        )
    )
    session.adopt(result.plan)

    print()
    print(f"[성공] Yearly Confirm   DRAFT → {result.plan.status.value}")
    print(f"  확정자   : {actor}")
    confirmed = [
        e for e in result.plan.audit if e.event_type.value == "CONFIRMED"
    ]
    if confirmed:
        print(f"  확정 시각 : {confirmed[-1].occurred_at.isoformat()}")
    print("  ℹ 이제 수정·재생성이 Application Gate에서 차단됩니다. [2]/[3]으로 확인하세요.")


def _json_dump(session: HarnessSession) -> None:
    import json

    from ..planning.application.dto import yearly_plan_to_contract_dict

    print(
        json.dumps(
            yearly_plan_to_contract_dict(session.plan), ensure_ascii=False, indent=2
        )
    )


# ------------------------------------------------------------------ 루프


_OPERATION_NAMES = {
    "2": "MonthPeriod 수정",
    "3": "MonthPeriod 재생성",
    "6": "Yearly Confirm",
}


def _run_loop(wiring: HarnessWiring, session: HarnessSession, *, debug: bool) -> None:
    while True:
        print(MENU)
        choice = _ask_until_valid("선택> ", lambda raw: parse_menu_choice(raw, CHOICES))
        if choice is None or choice == "0":
            print("\n종료합니다. InMemory Plan은 소멸합니다.")
            return

        print()
        try:
            if choice == "1":
                _show_plan(wiring, session)
            elif choice == "2":
                _edit(wiring, session)
            elif choice == "3":
                _regenerate(wiring, session)
            elif choice == "4":
                _evidence(wiring, session)
            elif choice == "5":
                print(fmt.format_selection_traces(session.plan, session.traces))
            elif choice == "6":
                _confirm(wiring, session)
            elif choice == "7":
                print(fmt.format_audit_history(session.plan))
            elif choice == "8":
                _json_dump(session)
        except PlanningError as exc:
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
        prog="python -m ssuksak.dev.yearly_harness",
        description="쓱싹요정 Yearly Dev Harness (제품 FE가 아님)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="GenerateYearlyPlan(use_llm=False) 경로. 실제 MLAPI 비용 없음.",
    )
    parser.add_argument(
        "--debug", action="store_true", help="traceback 표시"
    )
    args = parser.parse_args(argv)

    try:
        wiring = build_wiring(use_llm=not args.no_llm)
    except LLMConfigError as exc:
        print(fmt.format_config_error(str(exc)))
        return 2

    print(
        fmt.format_banner(
            provider=wiring.provider,
            model=wiring.model,
            live_api=wiring.live_api,
            catalog=wiring.catalog,
            api_style=wiring.api_style,
        )
    )

    if not wiring.catalog.is_active:
        print()
        print(" [경고] Reference Catalog가 활성 상태가 아닙니다.")
        print(f"        activation_status = {wiring.catalog.activation_status.value}")
        print("        생성은 Application Gate에서 차단됩니다.")

    session = HarnessSession(selector=wiring.selector)

    try:
        if not _initial_generate(wiring, session):
            print("\n입력이 중단되어 종료합니다.")
            return 1
    except PlanningError as exc:
        print()
        print(fmt.format_planning_error("Yearly 생성", exc))
        if args.debug:
            traceback.print_exc()
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"\n[오류] Yearly 생성 실패: {type(exc).__name__}: {exc}")
        if args.debug:
            traceback.print_exc()
        return 1

    _run_loop(wiring, session, debug=args.debug)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
