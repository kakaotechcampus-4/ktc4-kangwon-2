"""Harness 출력 포맷 테스트.

검증 축:
- 사람이 읽을 표 형태이고 JSON dump가 아니다
- API Key·프롬프트·base_url이 출력에 없다
- Provenance 3축이 분리되어 보인다
- RULE_LLM일 때 "Rule이 선택, LLM은 value만" 설명이 붙는다
- PlanningError가 traceback 없이 정리되어 나온다
"""

from __future__ import annotations

from ssuksak.dev import formatting as fmt
from ssuksak.dev.wiring import build_wiring
from ssuksak.planning.application.dto import (
    ClassroomContext,
    DaycareContext,
    GenerateYearlyPlanCommand,
    PlanningSetup,
)
from ssuksak.planning.domain.errors import (
    FailureCategory,
    PlanningError,
    validation_failed,
)
from ssuksak.planning.domain.provenance import GenerationMethod
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode

SECRET = "elice-key-must-never-appear"
BASE_URL = "https://secret-host.internal/v1"


def _generated(llm_mode: FakeLLMMode = FakeLLMMode.POLISH, ages=frozenset({4})):
    wiring = build_wiring(llm=FakeLLM(llm_mode))
    result = wiring.generate.execute(
        GenerateYearlyPlanCommand(
            school_year=2026,
            daycare=DaycareContext(daycare_ref="dev_daycare_001"),
            classroom=ClassroomContext(classroom_ref="dev_classroom_001", ages=ages),
            planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
            catalog=wiring.selector,
        )
    )
    return wiring, result


# ------------------------------------------------------------------ 배너


def test_banner_hides_api_key_and_base_url():
    wiring, _ = _generated()
    text = fmt.format_banner(
        provider="Elice MLAPI",
        model="openai/gpt-4.1-mini",
        live_api=True,
        catalog=wiring.catalog,
        api_style="responses",
    )
    assert SECRET not in text
    assert BASE_URL not in text
    assert "api_key" not in text.lower()
    assert "Elice MLAPI" in text
    assert "openai/gpt-4.1-mini" in text
    assert "theme-reference-v0.1.2" in text
    assert "HUMAN_APPROVED" in text
    assert "제품 FE가 아님" in text


def test_banner_marks_live_api_cost():
    wiring, _ = _generated()
    live = fmt.format_banner(
        provider="Elice MLAPI", model="m", live_api=True, catalog=wiring.catalog
    )
    off = fmt.format_banner(
        provider="-", model="-", live_api=False, catalog=wiring.catalog
    )
    assert "비용" in live
    assert "ENABLED" in live
    assert "DISABLED" in off


def test_config_error_message_has_no_secret():
    text = fmt.format_config_error("필수 환경변수 ELICE_MLAPI_API_KEY가 설정되지 않았다.")
    assert SECRET not in text
    assert "ELICE_MLAPI_API_KEY" in text  # 변수 이름은 안내해도 된다
    assert ".env.example" in text
    assert "--no-llm" in text


# ------------------------------------------------------------- Plan 출력


def test_yearly_plan_renders_twelve_rows_not_json():
    wiring, result = _generated()
    text = fmt.format_yearly_plan(result.plan, catalog=wiring.catalog, run=result.run)

    for month in ("03월", "04월", "09월", "10월", "01월", "02월"):
        assert month in text
    assert text.count("월 |") == 12

    assert "Yearly Plan 2026" in text
    assert "만 4세" in text
    assert "DRAFT" in text
    assert "theme-reference-v0.1.2" in text
    # JSON dump가 아니다
    assert '"month_periods"' not in text
    assert '"period_key"' not in text


def test_mixed_age_label():
    wiring, result = _generated(ages=frozenset({3, 4}))
    text = fmt.format_yearly_plan(result.plan, catalog=wiring.catalog)
    assert "만 3·4세 혼합" in text


# ------------------------------------------------------- Evidence 상세


def test_evidence_detail_separates_three_provenance_axes():
    wiring, result = _generated()
    mp = result.plan.period("2026-04")
    text = fmt.format_evidence_detail(
        "2026-04", mp.theme, catalog=wiring.catalog, trace=result.run.trace_for("2026-04")
    )

    assert "[1축] Evidence Source" in text
    assert "[2축] Generation Method" in text
    assert "[3축] Audit History" in text

    assert "THEME_REFERENCE" in text
    assert "yr_theme_spring" in text
    assert "theme-reference-v0.1.2" in text
    assert "observed_month" not in text or "월" in text
    assert "CREATED" in text
    assert "ONLY_ELIGIBLE_CANDIDATE" in text


def test_evidence_detail_shows_observed_labels_and_matched_via_context():
    wiring, result = _generated()
    mp = result.plan.period("2026-06")
    text = fmt.format_evidence_detail(
        "2026-06", mp.theme, catalog=wiring.catalog, trace=None
    )
    # 소답의 6월 관찰 라벨(주제)이 그대로 보인다
    assert "여러 가지 직업" in text
    assert "applicable_months" in text
    assert "supported_ages" in text
    assert "origin_id(lineage)" in text


def test_evidence_detail_marks_curriculum_link_as_alignment_only():
    wiring, result = _generated()
    mp = result.plan.period("2026-04")
    text = fmt.format_evidence_detail(
        "2026-04", mp.theme, catalog=wiring.catalog, trace=None
    )
    assert "curriculum_links" in text
    assert "국가 지정 출처가 아닙니다" in text


def test_rule_llm_method_gets_explicit_explanation():
    """Rule이 theme_id를 선택했고 LLM은 value만 썼다는 구분이 보여야 한다."""
    wiring, result = _generated()
    mp = result.plan.period("2026-04")
    assert mp.theme.generation.method is GenerationMethod.RULE_LLM

    text = fmt.format_evidence_detail(
        "2026-04", mp.theme, catalog=wiring.catalog, trace=None
    )
    assert "RULE_LLM" in text
    assert fmt.RULE_LLM_EXPLANATION in text
    assert "LLM_ASSISTED" not in text  # 새 Enum을 만들지 않았다
    assert "applied rule" in text


def test_rule_only_method_explanation_differs():
    wiring = build_wiring(use_llm=False, llm=FakeLLM())
    result = wiring.generate.execute(
        GenerateYearlyPlanCommand(
            school_year=2026,
            daycare=DaycareContext(daycare_ref="d"),
            classroom=ClassroomContext(classroom_ref="c", ages=frozenset({3})),
            planning_setup=PlanningSetup(completed=True),
            catalog=wiring.selector,
        )
    )
    mp = result.plan.period("2026-04")
    assert mp.theme.generation.method is GenerationMethod.RULE_ONLY

    text = fmt.format_evidence_detail("2026-04", mp.theme, catalog=wiring.catalog, trace=None)
    assert fmt.RULE_ONLY_EXPLANATION in text


# ------------------------------------------------------- Selection Trace


def test_selection_traces_use_stored_reasons():
    wiring, result = _generated()
    traces = {t.period_key: t for t in result.run.selection_traces}
    text = fmt.format_selection_traces(result.plan, traces)

    assert "09 | korea_and_world_cultures" in text
    assert "STRONGER_MONTH_EVIDENCE" in text
    assert "10 | autumn_and_nature" in text
    assert "AVOIDED_ADJACENT_REPEAT" in text
    assert text.count("ONLY_ELIGIBLE_CANDIDATE") == 10


def test_selection_traces_marks_missing_trace():
    wiring, result = _generated()
    text = fmt.format_selection_traces(result.plan, {})
    assert "trace 없음" in text


# ---------------------------------------------------------------- 오류


def test_planning_error_is_formatted_without_traceback():
    error = validation_failed(
        "confirmed_yearly_plan_is_read_only",
        FailureCategory.PLAN_STATE_GATE,
        "EditYearlyPlanItem은 CONFIRMED Plan에서 허용되지 않는다",
        period_key="2026-05",
    )
    text = fmt.format_planning_error("MonthPeriod 수정", error)

    assert "[실패] MonthPeriod 수정" in text
    assert "PLAN_STATE_GATE" in text
    assert "confirmed_yearly_plan_is_read_only" in text
    assert "2026-05" in text
    assert "Traceback" not in text
    assert "File \"" not in text


def test_planning_error_reports_every_violation():
    from ssuksak.planning.domain.errors import Outcome, Violation

    error = PlanningError(
        Outcome.VALIDATION_FAILED,
        [
            Violation(FailureCategory.PERIOD_VALIDATION, "rule_a", "상세 A"),
            Violation(FailureCategory.REQUIRED_VALUE_VALIDATION, "rule_b", "상세 B"),
        ],
    )
    text = fmt.format_planning_error("검증", error)
    assert "rule_a" in text and "rule_b" in text
    assert "상세 A" in text and "상세 B" in text


# ------------------------------------------------------------- telemetry


def test_llm_records_summary_has_no_prompt_or_key():
    from ssuksak.shared.llm.telemetry import LLMCallRecord

    record = LLMCallRecord(
        operation="polish_themes",
        provider="elice-mlapi",
        model="openai/gpt-4.1-mini",
        success=True,
        latency_ms=7025,
        retry_count=0,
        item_count=12,
        input_tokens=905,
        output_tokens=302,
    )
    text = fmt.format_llm_records([record])
    assert "12항목" in text
    assert "905/302" in text
    assert SECRET not in text
    assert "prompt" not in text.lower()


def test_empty_llm_records():
    assert "기록 없음" in fmt.format_llm_records([])


def test_llm_summary_omits_item_count_for_single_call():
    """Regenerate는 llm_item_count가 0이므로 항목 수를 표시하지 않는다."""
    from datetime import UTC, datetime

    from ssuksak.planning.application.dto import GenerationRun

    single = GenerationRun(
        run_id="r", started_at=datetime(2026, 9, 11, tzinfo=UTC),
        catalog_id="c", catalog_version="v",
        llm_invoked=True, llm_call_count=1, llm_item_count=0,
    )
    text = fmt.format_llm_summary(single)
    assert "요청 1회" in text
    assert "0항목" not in text

    batch = GenerationRun(
        run_id="r", started_at=datetime(2026, 9, 11, tzinfo=UTC),
        catalog_id="c", catalog_version="v",
        llm_invoked=True, llm_call_count=1, llm_item_count=12,
    )
    assert "12항목" in fmt.format_llm_summary(batch)


def test_llm_summary_reports_no_call():
    from datetime import UTC, datetime

    from ssuksak.planning.application.dto import GenerationRun

    run = GenerationRun(
        run_id="r", started_at=datetime(2026, 9, 11, tzinfo=UTC),
        catalog_id="c", catalog_version="v", llm_invoked=False,
    )
    assert "호출 없음" in fmt.format_llm_summary(run)
    assert "RULE_ONLY" in fmt.format_llm_summary(run)
