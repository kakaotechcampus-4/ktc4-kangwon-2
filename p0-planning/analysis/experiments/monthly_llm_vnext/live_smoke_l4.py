"""L4 Live Smoke — 실제 GPT-4.1 mini Monthly Planner 호출 (§29~§32).

Production 경로를 그대로 쓴다. Fake도 canned response도 쓰지 않는다.

    PYTHONPATH=src python -m analysis.experiments.monthly_llm_vnext.live_smoke_l4 [case ...]

**API Key / Base URL / 전체 Prompt를 출력하지 않는다.** 환경변수는
`LLMConfig.from_env()`가 읽고, 이 스크립트는 `safe_summary`만 본다.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time

from ssuksak.adapters.elice_mlapi_adapter import EliceMLAPIAdapter
from ssuksak.adapters.json_activity_reference_repository import (
    production_activity_reference_repository,
)
from ssuksak.planning.context import (
    MonthlyContextPacketBuilder,
    MonthlyContextRequest,
    packet_fingerprint,
)
from ssuksak.planning.domain.identifiers import PeriodKey
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.planner import build_monthly_planner_request
from ssuksak.planning.retrieval import (
    JsonInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.shared.llm.config import LLMConfig, LLMConfigError
from ssuksak.shared.llm.telemetry import LLMCallRecord

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "analysis" / "tmp" / "l4_live_smoke.txt"

CATALOG_ID = "ssuksak.outdoor-activity-reference"
CATALOG_VERSION = "activity-reference-v0.2.1"

CASES = {
    "2026-07": (4,),
    "2026-06": (4,),
    "2027-02": (5,),
}

_THEMES = json.loads(
    (ROOT / "data" / "themes" / "theme_reference_v0.json").read_text("utf-8")
)
THEME_BY_MONTH: dict[int, tuple[str, str]] = {}
for _t in _THEMES["themes"]:
    for _m in _t.get("applicable_months", []):
        THEME_BY_MONTH.setdefault(_m, (_t["theme_id"], _t["label"]))


def context_request(target_month: str, ages: tuple[int, ...]):
    key = PeriodKey(target_month)
    theme_id, label = THEME_BY_MONTH[key.calendar_month]
    return MonthlyContextRequest(
        school_year="2026",
        target_month=key,
        classroom_ages=ages,
        age_mode="SINGLE" if len(ages) == 1 else "MIXED",
        parent_lineage=ParentYearlyLineage(
            parent_yearly_plan_id="yp_smoke_001",
            parent_yearly_period_key=target_month,
            parent_yearly_theme_id=theme_id,
            parent_yearly_value=label,
            reference_catalog_id=_THEMES["catalog_id"],
            reference_version=_THEMES["catalog_version"],
            confirmed_at=datetime.datetime(2026, 2, 20, 9, 0, tzinfo=datetime.UTC),
            confirmed_by="actor_smoke_001",
        ),
    )


def main(argv: list[str]) -> int:
    wanted = argv or ["2026-07"]
    lines: list[str] = []

    def emit(text: str = "") -> None:
        print(text)
        lines.append(text)

    try:
        config = LLMConfig.from_env()
    except LLMConfigError as exc:
        emit("LIVE_SMOKE_BLOCKED_BY_CREDENTIAL")
        emit(f"  {exc}")
        return 2

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

    summary = config.safe_summary
    emit("LIVE_GPT_4_1_MINI")
    emit(f"  model            {summary['model']}")
    emit(f"  api_style        {summary['api_style']}")
    emit(f"  timeout / retry  {summary['timeout_seconds']}s / {summary['max_retries']}")
    emit(f"  reasoning_effort {summary['reasoning_effort']}")

    failures = 0
    for target_month in wanted:
        ages = CASES[target_month]
        packet = builder.build(context_request(target_month, ages))
        request = build_monthly_planner_request(packet)

        emit("")
        emit("=" * 74)
        emit(f"CASE  {target_month}  만{'/'.join(map(str, ages))}세  "
             f"주제={packet.parent_theme.theme_value}")
        emit("=" * 74)
        emit(f"  prompt_version      {request.prompt_version}")
        emit(f"  packet_fingerprint  {packet_fingerprint(packet)}")
        emit(f"  prompt 문자 수       system {len(request.system_prompt)} + "
             f"context {len(request.user_content)} = "
             f"{len(request.system_prompt) + len(request.user_content)}")
        emit(f"  expected weeks      {len(request.expected_week_ids)}")
        emit(f"  reference 후보       {len(request.reference_labels)}")
        emit(f"  grounding refs      {len(request.valid_grounding_refs)}")

        before = len(records)
        started = time.perf_counter()
        try:
            proposal = adapter.plan_monthly(request)
        except Exception as exc:  # noqa: BLE001 - smoke 보고 목적
            failures += 1
            elapsed = time.perf_counter() - started
            emit(f"  RESULT              FAILED  ({type(exc).__name__})")
            emit(f"  detail              {exc}")
            emit(f"  latency             {elapsed * 1000:.0f}ms")
            emit(f"  call count          {len(records) - before}")
            continue

        elapsed = time.perf_counter() - started
        calls = records[before:]
        emit(f"  RESULT              OK")
        emit(f"  parse + reconcile   PASSED")
        emit(f"  latency             {elapsed * 1000:.0f}ms")
        emit(f"  call count          {len(calls)}")
        emit(f"  retry count         {sum(c.retry_count for c in calls)}")
        emit(f"  repair count        "
             f"{max((c.extra.get('repair_count', 0) for c in calls), default=0)}")
        tokens_in = [c.input_tokens for c in calls if c.input_tokens is not None]
        tokens_out = [c.output_tokens for c in calls if c.output_tokens is not None]
        emit(f"  tokens              in {sum(tokens_in) or '?'} / "
             f"out {sum(tokens_out) or '?'}")

        emit("")
        emit(f"  theme_id            {proposal.theme_id}")
        emit(f"  theme lock          "
             f"{proposal.theme_id == request.expected_theme_id}")
        emit(f"  week lock           "
             f"{[w.week_id for w in proposal.weeks] == list(request.expected_week_ids)}")
        emit("")
        emit(f"  month_flow_rationale")
        for line in proposal.month_flow_rationale.splitlines() or [""]:
            emit(f"    {line}")

        emit("")
        for week in proposal.weeks:
            act = week.activity
            emit(f"  {week.week_id}")
            emit(f"    experience  {week.experience}")
            emit(f"    activity    {act.value}")
            emit(f"    origin      {act.origin.value}")
            emit(f"    reference   {act.reference_activity_id}")
            emit(f"    grounding   {act.grounding_refs}")

        ref_used = [w for w in proposal.weeks if w.activity.origin.value == "REFERENCE"]
        syn_used = [w for w in proposal.weeks if w.activity.origin.value != "REFERENCE"]
        emit("")
        emit(f"  REFERENCE 사용       {len(ref_used)}")
        emit(f"  LLM_SYNTHESIZED 사용 {len(syn_used)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n-> {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
