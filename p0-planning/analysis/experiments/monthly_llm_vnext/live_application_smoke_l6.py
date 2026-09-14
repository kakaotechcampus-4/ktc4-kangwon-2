"""L6 Application Live Smoke — 실제 GPT-4.1 mini로 Monthly DRAFT 생성 (§37).

    Confirmed Yearly → GenerateMonthlyPlan(mode=LLM_PLANNER)
      → Retrieval → Packet → live GPT → L5 → DRAFT

    PYTHONPATH=src python -m analysis.experiments.monthly_llm_vnext.live_application_smoke_l6

**저장 격리**: InMemory Repository만 쓴다(§38). 실제 사용자 데이터를 건드리지 않는다.
**비밀정보**: API Key · Base URL · Prompt 전문을 출력하거나 저장하지 않는다.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import time

from ssuksak.adapters.elice_mlapi_adapter import EliceMLAPIAdapter
from ssuksak.adapters.json_activity_reference_repository import (
    production_activity_reference_repository,
)
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_dto import (
    GenerateMonthlyPlanCommand,
    MonthlyGenerationMode,
)
from ssuksak.planning.application.monthly_llm_planning import MonthlyLlmPlanner
from ssuksak.planning.context import MonthlyContextPacketBuilder
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.retrieval import (
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.shared.llm.config import LLMConfig, LLMConfigError
from ssuksak.shared.llm.telemetry import LLMCallRecord

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "analysis" / "tmp" / "l6_live_application_smoke.txt"

TARGET_MONTH = "2026-06"
AGES = (4,)
CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"


def main() -> int:
    lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        lines.append(text)

    try:
        config = LLMConfig.from_env()
    except LLMConfigError as exc:
        emit("LIVE_APPLICATION_SMOKE_BLOCKED_BY_CREDENTIAL")
        emit(f"  {exc}")
        return 2

    # 기존 Monthly E2E harness의 InMemory Wiring을 그대로 쓴다.
    from ssuksak.dev import monthly_wiring

    wiring = monthly_wiring.build_monthly_wiring(
        target_month=TARGET_MONTH, ages=frozenset(AGES)
    )

    records: list[LLMCallRecord] = []
    adapter = EliceMLAPIAdapter(config, telemetry_sink=records.append)

    store = JsonInstitutionEvidenceRepository().get_store()
    catalog = production_activity_reference_repository().get_catalog(
        CATALOG_ID, CATALOG_VERSION
    )
    builder = MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(store, activity_catalog=catalog),
        store,
        activity_catalog=catalog,
    )
    planner = MonthlyLlmPlanner(
        context_builder=builder,
        llm=adapter,
        planner_model=config.model,
        activity_catalog=catalog,
    )

    # 기존 harness가 조립한 Generate와 **같은 협력자**를 쓰고 Planner만 더한다.
    base = wiring.generate
    use_case = GenerateMonthlyPlan(
        yearly_plan_repository=base._yearly,
        monthly_plan_repository=base._monthly,
        template_repository=base._templates,
        safety_rule_repository=base._safety_rules,
        clock=base._clock,
        id_generator=base._ids,
        activity_reference_repository=base._activities,
        llm_planner=planner,
    )

    command = GenerateMonthlyPlanCommand(
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
        generation_mode=MonthlyGenerationMode.LLM_PLANNER,
    )

    emit("LIVE_GPT_4_1_MINI  (Application Use Case)")
    summary = config.safe_summary
    emit(f"  model            {summary['model']}")
    emit(f"  api_style        {summary['api_style']}")
    emit(f"  target           {wiring.target_month} 만{'/'.join(map(str, AGES))}세")
    emit(f"  repository       InMemory (격리)")
    emit("")

    started = time.perf_counter()
    try:
        result = use_case.execute(command)
    except Exception as exc:  # noqa: BLE001 - smoke 보고 목적
        elapsed = time.perf_counter() - started
        emit(f"  RESULT           FAILED ({type(exc).__name__})")
        emit(f"  detail           {exc}")
        emit(f"  latency          {elapsed * 1000:.0f}ms")
        emit(f"  provider calls   {len(records)}")
        emit(f"  saved plans      {wiring.monthly_plans.stored_count}")
        _write(lines)
        return 1

    elapsed = time.perf_counter() - started
    plan, run = result.plan, result.run

    emit(f"  RESULT           OK")
    emit(f"  status           {plan.status.value}")
    emit(f"  saved plans      {wiring.monthly_plans.stored_count}")
    emit(f"  latency          {elapsed * 1000:.0f}ms")
    emit("")
    emit(f"  generation_mode  {run.generation_mode}")
    emit(f"  planner_model    {run.planner_model}")
    emit(f"  prompt_version   {run.prompt_version}")
    emit(f"  packet_finger    {run.packet_fingerprint}")
    emit(f"  evidence_sha     {run.evidence_store_sha256}")
    emit(f"  retrieval_ver    {run.retrieval_version}")
    emit(f"  packet_ver       {run.context_packet_version}")
    emit(f"  provider calls   {run.llm_call_count}")
    emit(f"  l5 repairs       {run.planner_validation_repair_count}")
    emit(f"  repaired codes   {list(run.planner_repaired_violations)}")
    transport = sum(c.retry_count for c in records)
    l4_repairs = max((c.extra.get("repair_count", 0) for c in records), default=0)
    emit(f"  transport retry  {transport}")
    emit(f"  l4 contract rep  {l4_repairs}")

    theme = next(s for s in plan.sections if s.section_key == "theme").items[0]
    emit("")
    emit(f"  theme            {theme.value}   [{theme.generation.method.value}]")

    outdoor = next(s for s in plan.sections if s.section_key == "outdoor_play")
    emit("")
    emit("  outdoor_play")
    for item in outdoor.items:
        kinds = "·".join(sorted({e.source_type.value for e in item.evidence}))
        emit(f"    {item.week_id.value}  {item.value}")
        emit(f"        {item.generation.method.value} / {kinds or '(evidence 없음)'}")
        for evidence in item.evidence:
            emit(f"        - {evidence.source_type.value}: {evidence.source_id}")

    safety = next(s for s in plan.sections if s.section_key == "safety_education")
    emit("")
    emit(f"  safety           {[i.cell_state.value for i in safety.items]}")
    emit(
        f"  constraint       "
        f"{[a.verification.value for a in plan.constraint_assessments]}"
    )

    emit("")
    emit("  week experience (Plan Item이 아니다 — OD-N18)")
    proposal_weeks = run.llm_item_count
    emit(f"    Proposal week 수 {proposal_weeks} / 저장된 experience Item 0")

    _write(lines)
    return 0


def _write(lines: list[str]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    raise SystemExit(main())
