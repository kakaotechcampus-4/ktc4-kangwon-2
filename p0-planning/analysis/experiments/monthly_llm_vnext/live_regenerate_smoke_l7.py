"""L7 Live Regenerate Smoke — 실제 GPT-4.1 mini로 Cell 하나 재생성 (§34).

    Generate(LLM_PLANNER) → DRAFT
      → Regenerate outdoor_play 1건
      → Regenerate focus 1건

    PYTHONPATH=src python -m analysis.experiments.monthly_llm_vnext.live_regenerate_smoke_l7

**저장 격리**: InMemory Repository만 쓴다. 실제 사용자 데이터를 건드리지 않는다.
**비밀정보**: API Key · Base URL · Prompt 전문을 출력하거나 저장하지 않는다.
"""

from __future__ import annotations

import pathlib
import time

from ssuksak.adapters.elice_mlapi_adapter import EliceMLAPIAdapter
from ssuksak.adapters.json_activity_reference_repository import (
    production_activity_reference_repository,
)
from ssuksak.adapters.monthly_repositories import (
    production_monthly_template_repository,
)
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_dto import (
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    MonthlyGenerationMode,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.monthly_llm_cell_regeneration import (
    MonthlyLlmCellRegenerator,
)
from ssuksak.planning.application.monthly_llm_planning import MonthlyLlmPlanner
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.context import MonthlyContextPacketBuilder
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_template import TemplateRef
from ssuksak.planning.retrieval import (
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.shared.llm.config import LLMConfig, LLMConfigError
from ssuksak.shared.llm.telemetry import LLMCallRecord

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "analysis" / "tmp" / "l7_live_regenerate_smoke.txt"

TARGET_MONTH = "2026-06"
AGES = (4,)
CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"
TEMPLATE_ID = "ssuksak.monthly-template-a"
TEMPLATE_VERSION = "monthly-template-a-v0.2.0"
ACTOR = ActorId("smoke_actor_001")


def cells(plan, section_key):
    section = next(s for s in plan.sections if s.section_key == section_key)
    return {i.week_id.value: i for i in section.items}


def main() -> int:
    lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        lines.append(text)

    try:
        config = LLMConfig.from_env()
    except LLMConfigError as exc:
        emit("LIVE_REGENERATE_SMOKE_BLOCKED_BY_CREDENTIAL")
        emit(f"  {exc}")
        return 2

    from ssuksak.dev import monthly_wiring

    wiring = monthly_wiring.build_monthly_wiring(
        target_month=TARGET_MONTH, ages=frozenset(AGES)
    )
    base = wiring.generate

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
    templates = production_monthly_template_repository()

    generate = GenerateMonthlyPlan(
        yearly_plan_repository=base._yearly,
        monthly_plan_repository=base._monthly,
        template_repository=templates,
        safety_rule_repository=base._safety_rules,
        clock=base._clock,
        id_generator=base._ids,
        activity_reference_repository=base._activities,
        llm_planner=MonthlyLlmPlanner(
            context_builder=builder,
            llm=adapter,
            planner_model=config.model,
            activity_catalog=catalog,
        ),
    )
    regenerate = RegenerateMonthlyPlanItem(
        monthly_plan_repository=base._monthly,
        template_repository=templates,
        clock=base._clock,
        activity_reference_repository=base._activities,
        llm_cell_regenerator=MonthlyLlmCellRegenerator(
            context_builder=builder, llm=adapter, planner_model=config.model
        ),
    )

    emit("LIVE_GPT_4_1_MINI  (Cell Regenerate)")
    emit(f"  model            {config.safe_summary['model']}")
    emit(f"  target           {TARGET_MONTH} 만{'/'.join(map(str, AGES))}세")
    emit(f"  repository       InMemory (격리)")
    emit("")

    command = GenerateMonthlyPlanCommand(
        parent_yearly_plan_id=wiring.parent_yearly.plan_id.value,
        school_year=wiring.school_year,
        target_month=wiring.target_month,
        daycare=wiring.daycare,
        classroom=wiring.classroom,
        planning_setup=wiring.planning_setup,
        template_ref=TemplateRef(TEMPLATE_ID, TEMPLATE_VERSION),
        safety_rule=wiring.safety_rule,
        catalog=wiring.catalog,
        activity_catalog=wiring.activity_catalog,
        generation_mode=MonthlyGenerationMode.LLM_PLANNER,
    )

    started = time.perf_counter()
    try:
        plan = generate.execute(command).plan
    except Exception as exc:  # noqa: BLE001
        emit(f"  GENERATE         FAILED ({type(exc).__name__}) {exc}")
        _write(lines)
        return 1
    emit(f"  GENERATE         OK  ({(time.perf_counter() - started) * 1000:.0f}ms)")

    before_focus = {k: v.value for k, v in cells(plan, "focus").items()}
    before_outdoor = {k: v.value for k, v in cells(plan, "outdoor_play").items()}
    emit("")
    emit("  생성된 계획")
    for week_id in before_focus:
        emit(f"    {week_id}")
        emit(f"      focus    {before_focus[week_id]}")
        emit(f"      outdoor  {before_outdoor[week_id]}")

    weeks = [w.week_id.value for w in plan.week_periods if w.active]
    target_week = weeks[min(2, len(weeks) - 1)]

    failures = 0
    for section_key in ("outdoor_play", "focus"):
        emit("")
        emit("=" * 70)
        emit(f"REGENERATE  {target_week} / {section_key}")
        emit("=" * 70)
        before_calls = len(records)
        started = time.perf_counter()
        try:
            result = regenerate.execute(
                RegenerateMonthlyPlanItemCommand(
                    plan_id=plan.plan_id.value,
                    address=MonthlyCellAddress(
                        target_month=plan.target_month.value,
                        section_key=section_key,
                        week_id=target_week,
                    ),
                    actor_id=ACTOR,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            emit(f"  RESULT           FAILED ({type(exc).__name__})")
            emit(f"  detail           {exc}")
            emit(f"  provider calls   {len(records) - before_calls}")
            continue

        elapsed = time.perf_counter() - started
        outcome = result.cell_regeneration
        after_focus = {k: v.value for k, v in cells(result.plan, "focus").items()}
        after_outdoor = {
            k: v.value for k, v in cells(result.plan, "outdoor_play").items()
        }

        emit(f"  RESULT           OK   ({elapsed * 1000:.0f}ms)")
        emit(f"  provider calls   {outcome.provider_call_count}")
        emit(f"  l5 repairs       {outcome.validation_repair_count}")
        emit(f"  repaired codes   {list(outcome.rejected_violation_codes)}")
        emit(f"  prompt_version   {outcome.prompt_version}")
        emit("")
        if section_key == "outdoor_play":
            emit(f"  이전             {before_outdoor[target_week]}")
            emit(f"  새 값            {after_outdoor[target_week]}")
            emit(f"  origin           {outcome.proposal.activity_origin.value}")
            emit(f"  reference        {outcome.proposal.reference_activity_id}")
            emit(f"  grounding        {list(outcome.proposal.grounding_refs)}")
            emit(f"  paired focus     {after_focus[target_week]}  (고정)")
        else:
            emit(f"  이전             {before_focus[target_week]}")
            emit(f"  새 값            {after_focus[target_week]}")
            emit(f"  paired outdoor   {after_outdoor[target_week]}  (고정)")

        changed = [
            f"{key}/{week}"
            for key, before, after in (
                ("focus", before_focus, after_focus),
                ("outdoor_play", before_outdoor, after_outdoor),
            )
            for week in before
            if before[week] != after[week]
        ]
        emit("")
        emit(f"  바뀐 Cell        {changed}")
        emit(f"  기대             ['{section_key}/{target_week}']")

        before_focus, before_outdoor = after_focus, after_outdoor
        plan = result.plan

    emit("")
    emit(f"  총 provider call {len(records)}")
    emit(f"  저장 횟수        {base._monthly.save_count}")

    # L4 contract repair는 Adapter 안에서 일어나므로 Application의
    # `validation_repair_count`에 잡히지 않는다. telemetry record 수와
    # 논리 호출 수의 차이로만 보이던 것을 직접 보이게 한다.
    emit("")
    emit("  telemetry (L4 contract repair 축)")
    for index, record in enumerate(records, start=1):
        emit(
            f"    {index:>2}. {record.operation:<24}"
            f" repair={record.extra.get('repair_count')}"
            f" retry={record.retry_count}"
            f" ok={record.success}"
            f" validation={record.validation_result}"
        )
    _write(lines)
    return 1 if failures else 0


def _write(lines: list[str]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    raise SystemExit(main())
