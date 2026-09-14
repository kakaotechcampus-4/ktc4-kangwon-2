"""Harness 출력 포맷. 모두 순수 함수이며 I/O도 상태 변경도 하지 않는다.

읽기 전용으로 Plan·Evidence·Audit·Trace를 사람이 읽을 수 있게 만든다.
`GenerationMethod`는 실제 Enum 값(`RULE_ONLY`/`RULE_LLM`/`IMPORTED`/`MANUAL`)을
그대로 쓰고, Rule이 theme_id를 선택했고 LLM은 value만 썼다는 점을 문장으로 덧붙인다.
새 Enum을 만들지 않는다.
"""

from __future__ import annotations

from ..planning.application.dto import GenerationRun, ThemeSelectionTrace
from ..planning.domain.errors import PlanningError
from ..planning.domain.plan import PlanItem, YearlyPlan
from ..planning.domain.provenance import EvidenceSourceType, GenerationMethod
from ..planning.domain.theme_reference import ThemeCatalog
from ..shared.llm.telemetry import LLMCallRecord

__all__ = [
    "RULE_LLM_EXPLANATION",
    "RULE_ONLY_EXPLANATION",
    "format_audit_history",
    "format_banner",
    "format_config_error",
    "format_edit_result",
    "format_evidence_detail",
    "format_llm_summary",
    "format_planning_error",
    "format_regenerate_result",
    "format_selection_traces",
    "format_yearly_plan",
]

WIDTH = 64
LINE = "=" * WIDTH
THIN = "-" * WIDTH

RULE_LLM_EXPLANATION = (
    "Rule이 theme_id를 선택했고 LLM은 value 표현만 작성했습니다."
)
RULE_ONLY_EXPLANATION = (
    "Rule이 theme_id를 선택했고 LLM을 호출하지 않았습니다. "
    "value는 Reference label을 그대로 사용했습니다."
)


def _method_explanation(method: GenerationMethod) -> str:
    if method is GenerationMethod.RULE_LLM:
        return RULE_LLM_EXPLANATION
    if method is GenerationMethod.RULE_ONLY:
        return RULE_ONLY_EXPLANATION
    if method is GenerationMethod.IMPORTED:
        return "기존 계획안에서 가져온 값입니다."
    return "사람이 직접 처음부터 작성한 값입니다."


# ------------------------------------------------------------------ 배너


def format_banner(
    *,
    provider: str,
    model: str,
    live_api: bool,
    catalog: ThemeCatalog,
    api_style: str | None = None,
) -> str:
    """시작 배너. **API Key와 base_url을 포함하지 않는다.**"""
    lines = [
        LINE,
        " 쓱싹요정 Yearly Dev Harness   (제품 FE가 아님)",
        LINE,
        f" LLM Provider   : {provider}",
        f" Model          : {model}",
        f" API Style      : {api_style or '-'}",
        f" Live API       : {'ENABLED   ← 실제 비용이 발생합니다' if live_api else 'DISABLED  (--no-llm)'}",
        f" Reference      : {catalog.catalog_version}  ({catalog.activation_status.value})",
        f" Themes         : {len(catalog.themes)}개",
        " Plan 저장       : InMemory (종료 시 소멸)",
        LINE,
    ]
    return "\n".join(lines)


def format_config_error(message: str) -> str:
    """설정 누락 안내. 값이나 Key를 노출하지 않는다."""
    return "\n".join([
        LINE,
        " [설정 오류] Harness를 시작할 수 없습니다.",
        LINE,
        f" {message}",
        "",
        " 프로젝트 루트의 .env에 다음이 필요합니다.",
        "   ELICE_MLAPI_BASE_URL",
        "   ELICE_MLAPI_API_KEY",
        "   LLM_MODEL",
        "   LLM_TIMEOUT_SECONDS",
        "   LLM_MAX_RETRIES",
        "   LLM_REASONING_EFFORT",
        "",
        " .env.example을 복사해 값을 채우세요.",
        " LLM 없이 Rule만 확인하려면 --no-llm 으로 실행하세요.",
        LINE,
    ])


# ------------------------------------------------------------ Plan 전체


def _age_label(plan: YearlyPlan) -> str:
    ages = sorted(plan.classroom_ages)
    if len(ages) == 1:
        return f"만 {ages[0]}세"
    return "만 " + "·".join(str(a) for a in ages) + "세 혼합"


def format_yearly_plan(
    plan: YearlyPlan, *, catalog: ThemeCatalog, run: GenerationRun | None = None
) -> str:
    """12개월 계획을 표로 보여준다. JSON dump가 아니다."""
    lines = [
        LINE,
        f" Yearly Plan {plan.school_year} | {_age_label(plan)} | {plan.status.value}",
        LINE,
    ]
    for mp in plan.month_periods:
        month = mp.period_key.calendar_month
        lines.append(f" {month:02d}월 | {mp.theme.value}")

    lines.append(THIN)
    lines.append(f" Reference : {catalog.catalog_version} ({catalog.activation_status.value})")
    lines.append(f" Classroom : {plan.classroom_ref}")
    lines.append(f" Plan ID   : {plan.plan_id.value}")
    lines.append(f" Status    : {plan.status.value}")
    if run is not None:
        lines.append(f" LLM       : {format_llm_summary(run)}")
    lines.append(LINE)
    return "\n".join(lines)


def format_llm_summary(run: GenerationRun) -> str:
    """LLM 호출 요약.

    `llm_item_count`는 Batch 경로(Generate)에서만 채워진다. 단건 경로
    (Regenerate)는 0이므로 표시하지 않는다. Core를 바꾸지 않고 표시만 맞춘다.
    """
    if not run.llm_invoked:
        return "호출 없음 (RULE_ONLY)"
    parts = [f"요청 {run.llm_call_count}회"]
    if run.llm_item_count:
        parts.append(f"{run.llm_item_count}항목")
    if run.used_fallback:
        parts.append(f"fallback={list(run.fallbacks_used)}")
    return " · ".join(parts)


def format_llm_records(records: list[LLMCallRecord]) -> str:
    """telemetry 요약. Key·프롬프트를 담지 않는다."""
    if not records:
        return " (LLM 호출 기록 없음)"
    lines = []
    for r in records:
        tokens = (
            f"{r.input_tokens}/{r.output_tokens} tokens"
            if r.input_tokens is not None
            else "tokens -"
        )
        lines.append(
            f"  {r.operation:16s} {r.item_count:2d}항목  {tokens:20s}"
            f" {r.latency_ms:6d}ms  retry={r.retry_count}  {r.validation_result}"
        )
    return "\n".join(lines)


# --------------------------------------------------------- Evidence 상세


def format_evidence_detail(
    period_key: str,
    item: PlanItem,
    *,
    catalog: ThemeCatalog,
    trace: ThemeSelectionTrace | None,
) -> str:
    """한 기간의 Provenance 3축을 분리해 보여준다."""
    theme_refs = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    theme_id = theme_refs[0].source_id if theme_refs else "(없음)"
    candidate = catalog.get(theme_id) if theme_refs else None

    lines = [
        LINE,
        f" [{period_key}] MonthPeriod 상세 근거",
        LINE,
        f" theme_id          : {theme_id}",
        f" Reference label   : {candidate.label if candidate else '(resolve 실패)'}",
        f" value (표시 문구)  : {item.value}",
        "",
        f" item_id           : {item.item_id.value}",
        f" semantic_key      : {item.semantic_key.value}",
        THIN,
        " [1축] Evidence Source — 내용의 근거",
    ]

    if not item.evidence:
        lines.append("   등록된 근거 없음")
    for ev in item.evidence:
        lines.append(f"   - source_type    : {ev.source_type.value}")
        lines.append(f"     source_id      : {ev.source_id}")
        if ev.source_version:
            lines.append(f"     source_version : {ev.source_version}")
        if ev.display_name:
            lines.append(f"     display_name   : {ev.display_name}")
        if ev.effective_date:
            lines.append(f"     effective_date : {ev.effective_date}")

    if candidate is not None:
        lines.append("")
        lines.append(f"   Reference 관찰 근거 ({len(candidate.evidence)}건)")
        for obs in candidate.evidence:
            ages = "".join(str(a) for a in obs.age_scope)
            lines.append(
                f"     · {obs.origin_id}  p.{obs.page}  만{ages}세  "
                f"{obs.observed_month:2d}월  {obs.observed_label!r}"
            )
        lines.append(f"   applicable_months : {list(candidate.applicable_months)}")
        lines.append(f"   supported_ages    : {list(candidate.supported_ages)}")
        lines.append(f"   origin_id(lineage): {candidate.origin_id}")
        if candidate.curriculum_links:
            domains = ", ".join(
                f"{l.domain}(p.{l.source_page})" for l in candidate.curriculum_links
            )
            lines.append(f"   curriculum_links  : {domains}")
            lines.append(
                "     ※ 영역 수준 교육적 연계이며 월별 주제의 국가 지정 출처가 아닙니다."
            )

    lines.append(THIN)
    lines.append(" [2축] Generation Method — 생성 방식")
    lines.append(f"   method          : {item.generation.method.value}")
    lines.append(f"   → {_method_explanation(item.generation.method)}")
    if item.generation.rule_id:
        lines.append(
            f"   applied rule    : {item.generation.rule_id} {item.generation.rule_version}"
        )
    if item.generation.selection_reason:
        lines.append(f"   selection reason: {item.generation.selection_reason}")

    lines.append(THIN)
    lines.append(" [3축] Audit History — 생성 이후의 변경")
    if len(item.audit) == 0:
        lines.append("   기록 없음")
    for ev in item.audit:
        who = ev.actor_display
        lines.append(
            f"   - {ev.event_type.value:15s} {ev.occurred_at.isoformat()}  by {who}"
        )
        if ev.previous_value is not None and ev.new_value is not None:
            lines.append(f"       {ev.previous_value!r} → {ev.new_value!r}")

    if trace is not None:
        lines.append(THIN)
        lines.append(" Selection (Rule 결과)")
        lines.append(f"   reason           : {trace.reason}")
        lines.append(f"   evidence_strength: {trace.evidence_strength}")
        lines.append(f"   eligible 후보     : {list(trace.eligible_theme_ids)}")
        lines.append(f"   avoided adjacent : {trace.avoided_adjacent_repeat}")
        lines.append(f"   rule             : {trace.rule_id} {trace.rule_version}")

    lines.append(LINE)
    return "\n".join(lines)


# ------------------------------------------------------- Selection Trace


def format_selection_traces(
    plan: YearlyPlan, traces: dict[str, ThemeSelectionTrace]
) -> str:
    """12개월 selection reason. Harness가 계산하지 않고 보관값을 그대로 쓴다."""
    lines = [
        LINE,
        " 전체 Selection Trace (Rule 결정)",
        LINE,
    ]
    for mp in plan.month_periods:
        key = mp.period_key.value
        trace = traces.get(key)
        month = mp.period_key.calendar_month
        if trace is None:
            lines.append(f" {month:02d} | (trace 없음 — 이 세션에서 생성/재생성되지 않음)")
            continue
        short = trace.selected_theme_id.removeprefix("yr_theme_")
        lines.append(f" {month:02d} | {short:26s} | {trace.reason}")
    lines.append(LINE)
    return "\n".join(lines)


# --------------------------------------------------------- Audit History


def format_audit_history(plan: YearlyPlan) -> str:
    """Plan-level + Item-level Audit을 발생 순서대로 보여준다."""
    lines = [
        LINE,
        " Audit History",
        LINE,
        " [Plan level]",
    ]
    if len(plan.audit) == 0:
        lines.append("   기록 없음")
    for ev in plan.audit:
        lines.append(
            f"   - {ev.event_type.value:15s} {ev.occurred_at.isoformat()}"
            f"  by {ev.actor_display}"
        )

    lines.append("")
    lines.append(" [Item level]")
    any_item = False
    for mp in plan.month_periods:
        item = mp.theme
        if len(item.audit) <= 1:
            continue
        any_item = True
        lines.append(f"   {mp.period_key.value}  ({item.item_id.value})")
        for ev in item.audit:
            line = (
                f"     - {ev.event_type.value:15s} {ev.occurred_at.isoformat()}"
                f"  by {ev.actor_display}"
            )
            lines.append(line)
            if ev.previous_value is not None and ev.new_value is not None:
                lines.append(f"         {ev.previous_value!r} → {ev.new_value!r}")
    if not any_item:
        lines.append("   CREATED 외 변경 없음")

    lines.append(LINE)
    return "\n".join(lines)


# ------------------------------------------------------- 동작 결과 출력


def format_edit_result(
    period_key: str,
    item: PlanItem,
    *,
    previous_value: str,
    previous_method: GenerationMethod,
) -> str:
    lines = [
        f"[성공] {period_key} 수정",
        f"  이전 value       : {previous_value}",
        f"  새 value         : {item.value}",
        f"  generation_method: {item.generation.method.value} (변경 없음)"
        if item.generation.method is previous_method
        else f"  generation_method: {previous_method.value} → {item.generation.method.value}",
        f"  → {_method_explanation(item.generation.method)}",
        f"  Evidence         : {len(item.evidence)}건 보존",
        f"  audit            : {' → '.join(e.event_type.value for e in item.audit)}",
        "",
        "  ℹ 교사 수정은 Evidence Source를 만들지 않고 Generation Method도",
        "    덮어쓰지 않습니다. TEACHER_EDITED Audit Event로만 남습니다.",
    ]
    return "\n".join(lines)


def format_regenerate_result(
    period_key: str,
    item: PlanItem,
    *,
    previous_value: str,
    previous_theme_id: str | None,
    new_theme_id: str | None,
    trace: ThemeSelectionTrace | None,
    run: GenerationRun | None,
) -> str:
    theme_changed = previous_theme_id != new_theme_id
    value_changed = previous_value != item.value

    lines = [
        f"[성공] {period_key} 재생성",
        f"  theme_id         : {new_theme_id}"
        + ("" if theme_changed else "  (변경 없음)"),
    ]
    if theme_changed:
        lines.append(f"    이전 theme_id  : {previous_theme_id}")
    lines += [
        f"  이전 value       : {previous_value}",
        f"  새 value         : {item.value}",
        f"  selection        : {trace.reason if trace else '-'}",
        f"  generation_method: {item.generation.method.value}",
        f"  → {_method_explanation(item.generation.method)}",
        f"  LLM 호출          : {'예' if run and run.llm_invoked else '아니오'}"
        + (f" ({format_llm_summary(run)})" if run and run.llm_invoked else ""),
        f"  audit            : {' → '.join(e.event_type.value for e in item.audit)}",
    ]

    if not value_changed:
        lines += [
            "",
            "  ℹ 재생성은 성공했지만 생성된 표현이 기존 값과 동일합니다.",
            "    Contract상 Regenerate가 값을 반드시 바꿔야 하는 것은 아니므로",
            "    이것은 오류가 아닙니다.",
        ]
    return "\n".join(lines)


# -------------------------------------------------------------- 오류 출력


def format_planning_error(operation: str, error: PlanningError) -> str:
    """PlanningError를 개발자가 읽을 수 있게 정리한다. traceback을 쓰지 않는다."""
    lines = [
        f"[실패] {operation}",
        f"  outcome  : {error.outcome.value}",
    ]
    for violation in error.violations:
        lines.append(f"  category : {violation.category.value}")
        lines.append(f"  rule     : {violation.violated_rule}")
        if violation.period_key:
            lines.append(f"  period   : {violation.period_key}")
        if violation.detail:
            lines.append(f"  message  : {violation.detail}")
    return "\n".join(lines)
