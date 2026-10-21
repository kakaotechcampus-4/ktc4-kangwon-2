"""주간계획안 Luna-6 실측 (W7b — docs: 하민 개인 계획 「실측 절차」).

실제 주간 스키마로 엘리스를 불러 400 여부 · 호출별 시간 · 수리 · 저장 성공 / 실패 코드 · 토큰 ·
비용을 잰다. **돈이 드는 호출이라 `--live` 없이는 부르지 않는다.**

**주간 호출만 돈이 든다.** 부모 연간 · 월간은 mock(결정적 provider)으로 메모리에 만든다 — DB 도
쓰지 않는다. 그래서 잰 토큰 · 비용은 주간 몫뿐이다. 요청 9개(생성 5 · 한 칸 재생성 4), 수리까지
최대 18 호출이다.

    docker compose exec backend python scripts/bench_weekly_luna.py --live [--show-values]

**서버에서만 부른다**(월간 bench 와 같은 `TimedTransport` 가드 — `IS_SERVER` 가 `1` · `true`
가 아니면 실제 전송을 만들지 않는다). 필요한 env 는 `IS_SERVER` · `ELICE_MLAPI_BASE_URL` ·
`ELICE_MLAPI_API_KEY` 뿐이다 — `WEEKLY_LLM_ENABLED` 는 API 경로의 스위치라 여기선 안 쓴다.

**예산을 넘기 전에 멈춘다.** 호출마다 토큰으로 비용을 계산하고(단가 ₩141 입력 · ₩14 캐시 입력 ·
₩708 출력 / 100만 토큰), 다음 요청이 수리까지 해도 `--budget-won`(기본 1,000원)을 넘을 것 같으면
남은 요청을 하지 않고 결과를 낸다. 호출 수도 `--max-calls`(기본 24)를 넘지 않는다.

키는 출력하지 않는다. 생성 문장은 `--show-values` 일 때만 낸다 — 사람이 품질을 보는 용도이고,
팀 문서 · 로그로 옮기지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from functools import partial

from bench_monthly_luna import (
    NOW,
    PROFILE,
    TimedTransport,
    _ApprovedTemplates,
    _count,
    _profile,
)
from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.deterministic_theme_text_generator import DeterministicThemeTextGenerator
from ssuksak.adapters.elice_openai_monthly import EliceOpenAiMonthlyAdapter, MonthlyLlmConfig
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.in_memory_template_profile_repository import (
    InMemoryTemplateProfileRepository,
)
from ssuksak.adapters.json_activity_reference_repository import JsonActivityReferenceRepository
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository
from ssuksak.adapters.monthly_composition import monthly_context_pipeline
from ssuksak.adapters.monthly_reference_repositories import JsonSafetyLegalRuleRepository
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.adapters.weekly_composition import (
    WEEKLY_TEMPLATE_REF,
    weekly_edit,
    weekly_generation,
    weekly_operating_days,
    weekly_regeneration,
)
from ssuksak.planning import (
    ActivityCatalogSelector,
    CatalogSelector,
    ConfirmMonthlyPlan,
    ConfirmMonthlyPlanCommand,
    ConfirmYearlyPlan,
    ConfirmYearlyPlanCommand,
    EditWeeklyPlanCellCommand,
    GenerateMonthlyPlan,
    GenerateMonthlyPlanCommand,
    GenerateWeeklyPlanCommand,
    GenerateYearlyPlan,
    GenerateYearlyPlanCommand,
    MonthlyApplicationError,
    MonthlyGenerationMode,
    RegenerateWeeklyPlanCellCommand,
    SafetyRuleSelector,
)
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.planner.service import MonthlyPlanner

LLM = MonthlyGenerationMode.LLM_PLANNER
SAFETY_RULE = SafetyRuleSelector("child-welfare-act-decree-annex6-2022-06-21")
CATALOG = ActivityCatalogSelector("ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1")
TEACHER = ActorId("bench_teacher")

# 원 / 100만 토큰 (하민 제공 2026-10-21).
PRICE_INPUT, PRICE_CACHED, PRICE_OUTPUT = 141, 14, 708

# (이름, 연령, 달, 주 순번, 토요일, 다시 만들 칸).
# 주 순번은 그 달 활성 주 목록의 index 다(-1 = 마지막).
CASES = [
    ("만3 · 3월 1주", {3}, YearMonth(2026, 3), 0, False, ()),
    ("만4 · 9월 2주", {4}, YearMonth(2026, 9), 1, False, ("goals", "indoor_play")),
    ("만5 · 12월 3주 · 토", {5}, YearMonth(2026, 12), 2, True, ()),
    ("혼합3+4 · 10월 2주", {3, 4}, YearMonth(2026, 10), 1, False, ("outdoor_play",)),
    ("혼합4+5 · 2월 마지막 · 토", {4, 5}, YearMonth(2027, 2), -1, True, ()),
]
# 결정 B 확인: 교사가 goals 에 날짜를 쓴 뒤 focus 를 다시 만든다 — 막히면 안 된다.
DECISION_B_CASE = "만4 · 9월 2주"
DECISION_B_GOALS = "10월 9일 한글날을 알아본다."


def call_cost(call: dict) -> float:
    usage = call.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return (
        (prompt - cached) * PRICE_INPUT + cached * PRICE_CACHED + completion * PRICE_OUTPUT
    ) / 1e6


class Budget:
    """다음 요청이 수리까지 해도(호출 2회) 예산 · 호출 수 안인지 본다. 처음엔 1회분을 모른다."""

    def __init__(self, transport, *, won: float, max_calls: int):
        self.transport, self.won, self.max_calls = transport, won, max_calls

    @property
    def spent(self) -> float:
        return sum(call_cost(call) for call in self.transport.calls)

    def allows_next(self) -> bool:
        calls = self.transport.calls
        if len(calls) + 2 > self.max_calls:
            return False
        worst = max((call_cost(call) for call in calls), default=0.0)
        return self.spent + 2 * worst <= self.won


def _parents(ages: frozenset[int], month: YearMonth):
    """mock 으로 확정 연간 → 확정 월간. 돈이 들지 않는다."""
    clock = FixedClock(NOW)
    yearly, monthly = InMemoryPlanRepository(), InMemoryPlanRepository()
    year = (
        GenerateYearlyPlan(
            theme_repository=JsonThemeReferenceRepository(),
            plan_repository=yearly,
            text_generator=DeterministicThemeTextGenerator(),
            clock=clock,
            id_generator=DeterministicIdGenerator("bench-yearly"),
        )
        .execute(
            GenerateYearlyPlanCommand(
                school_year=2026,
                classroom_ref="bench-classroom",
                target_ages=ages,
                catalog=CatalogSelector("ssuksak.yearly-theme-reference", "theme-reference-v0.1.2"),
            )
        )
        .plan
    )
    ConfirmYearlyPlan(plan_repository=yearly, clock=clock).execute(
        ConfirmYearlyPlanCommand(year.plan_id, TEACHER)
    )
    draft = (
        GenerateMonthlyPlan(
            parent_plan_repository=yearly,
            plan_repository=monthly,
            profile_repository=InMemoryTemplateProfileRepository((_profile(),)),
            template_repository=_ApprovedTemplates(),
            safety_repository=JsonSafetyLegalRuleRepository(),
            activity_repository=JsonActivityReferenceRepository(),
            clock=clock,
            id_generator=DeterministicIdGenerator("bench-monthly"),
            context_pipeline=monthly_context_pipeline(),
            planner=MonthlyPlanner(RequestAwareMonthlyLlm()),
        )
        .execute(
            GenerateMonthlyPlanCommand(
                parent_yearly_plan_id=year.plan_id,
                target_month=month,
                daycare_ref="bench-daycare",
                profile_ref=PROFILE,
                safety_rule=SAFETY_RULE,
                generation_mode=LLM,
                activity_catalog=CATALOG,
            )
        )
        .plan
    )
    parent = ConfirmMonthlyPlan(
        plan_repository=monthly, clock=clock, activity_repository=JsonActivityReferenceRepository()
    ).execute(ConfirmMonthlyPlanCommand(draft.plan_id, TEACHER))
    return monthly, parent


def _summary(plan, show_values: bool) -> dict:
    cells = {}
    for cell in plan.cells:
        entry = {
            "method": cell.generation.method.value if cell.generation else None,
            "state": cell.cell_state.value,
            "evidence": sorted({e.source_type.value for e in cell.evidence}),
            "chars": len(cell.value),
        }
        if show_values:
            entry["value"] = cell.value
        cells[cell.section_key] = entry
    return {
        "operating_days": [d.value for d in plan.operating_days],
        "cells": cells,
        "findings": _count(f.code for f in plan.verification_report.findings),
    }


def _attempt(transport, kind: str, call) -> tuple[dict, object]:
    first = len(transport.calls)
    started = time.perf_counter()
    outcome: dict = {"kind": kind}
    result = None
    try:
        result = call()
        outcome["result"] = "SAVED"
    except MonthlyApplicationError as error:
        cause = error.__cause__
        outcome.update(
            result="FAILED",
            code=error.code,
            validation_codes=list(getattr(cause, "validation_codes", ()) or ()),
            cause=None if cause is None else type(cause).__name__,
        )
    outcome["seconds"] = round(time.perf_counter() - started, 2)
    outcome["calls"] = transport.calls[first:]
    outcome["repaired"] = len(outcome["calls"]) > 1
    outcome["won"] = round(sum(call_cost(c) for c in outcome["calls"]), 2)
    return outcome, result


def run(transport, budget: Budget, *, show_values: bool = False) -> list[dict]:
    adapter = EliceOpenAiMonthlyAdapter(MonthlyLlmConfig.from_env(), transport=transport)
    clock = FixedClock(NOW)
    results: list[dict] = []
    for name, ages, month, week_index, saturday, regenerate in CASES:
        if not budget.allows_next():
            results.append({"case": name, "result": "SKIPPED_BUDGET"})
            continue
        monthly, parent = _parents(frozenset(ages), month)
        week = [p for p in parent.week_periods if p.active][week_index]
        weekly = InMemoryPlanRepository()
        generate = weekly_generation(
            parent_plan_repository=monthly,
            plan_repository=weekly,
            provider=adapter,
            clock=clock,
            id_generator=DeterministicIdGenerator("bench-weekly"),
        )
        command = GenerateWeeklyPlanCommand(
            parent_monthly_plan_id=parent.plan_id,
            week_id=week.week_id,
            operating_days=weekly_operating_days(saturday),
            template_ref=WEEKLY_TEMPLATE_REF,
            safety_rule=SAFETY_RULE,
            generation_mode=LLM,
            activity_catalog=CATALOG,
        )
        outcome, generated = _attempt(transport, "generate", partial(generate.execute, command))
        plan = None if generated is None else generated.plan
        case = {"case": name, "week_id": week.week_id.value, **outcome}
        if plan is not None:
            case["plan"] = _summary(plan, show_values)
        results.append(case)
        if plan is None:
            continue

        steps = [(key, None) for key in regenerate]
        if name == DECISION_B_CASE:
            steps.append(("focus", DECISION_B_GOALS))
        regenerate_cell = weekly_regeneration(
            plan_repository=weekly, parent_plan_repository=monthly, provider=adapter, clock=clock
        )
        for key, teacher_goals in steps:
            label = f"{name} · {key} 다시" + (
                " (교사 goals 날짜 뒤 — 결정 B)" if teacher_goals else ""
            )
            if not budget.allows_next():
                results.append({"case": label, "result": "SKIPPED_BUDGET"})
                continue
            if teacher_goals is not None:
                plan = weekly_edit(
                    plan_repository=weekly, parent_plan_repository=monthly, clock=clock
                ).execute(
                    EditWeeklyPlanCellCommand(
                        plan.plan_id, plan.cell("goals").item_id, teacher_goals, TEACHER
                    )
                )
            command = RegenerateWeeklyPlanCellCommand(plan.plan_id, plan.cell(key).item_id, TEACHER)
            outcome, changed = _attempt(
                transport, "regenerate", partial(regenerate_cell.execute, command)
            )
            step = {"case": label, **outcome}
            if changed is not None:
                plan = changed
                step["cell"] = _summary(changed, show_values)["cells"][key]
            results.append(step)
    return results


def report(transport, results: list[dict]) -> dict:
    requests = [r for r in results if "calls" in r]
    calls = transport.calls
    tokens = {
        k: sum(int((c.get("usage") or {}).get(k) or 0) for c in calls)
        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    return {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_expected": MonthlyLlmConfig.from_env().model,
        "requests": len(requests),
        "saved": sum(r["result"] == "SAVED" for r in requests),
        "failed_codes": _count(r.get("code") for r in requests if r["result"] == "FAILED"),
        "repaired": sum(r["repaired"] for r in requests),
        "skipped_budget": sum(r.get("result") == "SKIPPED_BUDGET" for r in results),
        "calls": len(calls),
        "http_status": _count(c.get("status") for c in calls),
        "seconds_max": max((c.get("seconds", 0) for c in calls), default=0),
        "tokens": tokens,
        "won": round(sum(call_cost(c) for c in calls), 2),
        "results": results,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="실제 엘리스 호출에 동의한다")
    parser.add_argument("--budget-won", type=float, default=1000.0)
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--show-values", action="store_true", help="생성 문장을 낸다(사람 확인용)")
    args = parser.parse_args(argv)
    if not args.live:
        print("--live 없이는 부르지 않는다 (호출마다 비용이 든다).", file=sys.stderr)
        return 2
    if not (0 < args.budget_won <= 1000 and 1 <= args.max_calls <= 24):
        print("--budget-won 은 0 초과 1,000 이하, --max-calls 는 1~24 다.", file=sys.stderr)
        return 2
    try:
        transport = TimedTransport()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    budget = Budget(transport, won=args.budget_won, max_calls=args.max_calls)
    results = run(transport, budget, show_values=args.show_values)
    print(json.dumps(report(transport, results), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
