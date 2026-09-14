"""LLM 경계 단위 테스트.

CLAUDE.md §5·§15·§20:
- LLM은 Theme를 선택하거나 theme_id를 바꾸지 못한다.
- 문장 전체를 exact match하지 않고 Schema·필수 필드·Reference 범위·theme_id 유지를 본다.
- max_chars 등 미확정 수치를 하드코딩하지 않는다.
"""

from __future__ import annotations

import pytest

from ssuksak.planning.application.dto import (
    ClassroomContext,
    DaycareContext,
    GenerateYearlyPlanCommand,
    PlanningSetup,
)
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode
from ssuksak.shared.llm.port import (
    ThemePolishConstraints,
    ThemePolishRequest,
    parse_theme_polish_response,
)

from tests.golden import harness as H


def _command(hn: H.Harness, ages=frozenset({3})) -> GenerateYearlyPlanCommand:
    return GenerateYearlyPlanCommand(
        school_year=2026,
        daycare=DaycareContext(daycare_ref="d1"),
        classroom=ClassroomContext(classroom_ref="c1", ages=ages),
        planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
        catalog=hn.selector,
    )


# ------------------------------------------------------ Structured Output


def test_response_schema_accepts_valid_payload():
    parsed = parse_theme_polish_response({"theme_id": "t1", "value": "봄이 왔어요"})
    assert parsed.theme_id == "t1"
    assert parsed.value == "봄이 왔어요"


def test_response_schema_rejects_missing_required_field():
    with pytest.raises(ValueError):
        parse_theme_polish_response({"theme_id": "t1"})
    with pytest.raises(ValueError):
        parse_theme_polish_response({"value": "x"})


def test_response_schema_rejects_empty_strings():
    with pytest.raises(ValueError):
        parse_theme_polish_response({"theme_id": "", "value": "x"})
    with pytest.raises(ValueError):
        parse_theme_polish_response({"theme_id": "t", "value": ""})


def test_response_schema_forbids_extra_fields():
    """LLM이 스키마 밖 필드로 정책을 밀어 넣지 못하게 한다."""
    with pytest.raises(ValueError):
        parse_theme_polish_response(
            {"theme_id": "t", "value": "v", "applicable_months": [1, 2]}
        )


# ------------------------------------- 방어 1: 후보 목록을 전달하지 않는다


def test_llm_request_carries_only_the_single_selected_theme():
    """Generate는 요청 1회로 12항목을 보낸다. 후보 목록은 어디에도 없다."""
    hn = H.make_harness()
    hn.generate().execute(_command(hn))

    # 요청 1회, 항목 12개
    assert hn.llm.batch_call_count == 1
    assert hn.llm.request_count == 1
    assert hn.llm.call_count == 12

    batch = hn.llm.batch_calls[0]
    assert len(batch.items) == 12
    # Batch 요청·항목에 후보 배열 필드가 존재하지 않는다.
    assert not hasattr(batch, "candidates")
    assert not hasattr(batch, "eligible_theme_ids")
    for item in batch.items:
        assert not hasattr(item, "candidates")
        assert item.theme_id
        assert item.label
        assert item.period_key

    for request in hn.llm.calls:
        assert isinstance(request, ThemePolishRequest)
        assert not hasattr(request, "candidates")
        assert not hasattr(request, "eligible_theme_ids")
        assert request.selected_theme_id
        assert request.selected_theme_label


# --------------------------------- 방어 2: 반환 theme_id 불일치를 거부한다


def test_llm_swapping_theme_id_is_rejected():
    hn = H.make_harness(llm_mode=FakeLLMMode.WRONG_THEME_ID)

    with pytest.raises(PlanningError) as exc:
        hn.generate().execute(_command(hn))

    assert exc.value.failure_category is FailureCategory.LLM_OUTPUT_VALIDATION
    assert exc.value.violated_rule == "llm_must_not_select_or_replace_theme"
    assert hn.plans.save_count == 0, "theme_id 교체 시도가 저장되었다"


# ------------------- 방어 3: Evidence는 Rule 결과에서만 세팅한다


def test_evidence_theme_id_always_equals_rule_selection():
    hn = H.make_harness(llm_mode=FakeLLMMode.ECHO_LABEL)
    result = hn.generate().execute(_command(hn))

    rule_choice = {t.period_key: t.selected_theme_id for t in result.run.selection_traces}
    for period_key, theme_id in H.theme_ids_of(result.plan).items():
        assert theme_id == rule_choice[period_key]


def test_llm_only_changes_expression_not_theme_identity():
    """같은 Rule 선택에서 LLM mode만 바꾸면 표현은 달라지고 theme_id는 같다."""
    echo = H.make_harness(llm_mode=FakeLLMMode.ECHO_LABEL)
    echo_result = echo.generate().execute(_command(echo))

    polish = H.make_harness(llm_mode=FakeLLMMode.POLISH)
    polish_result = polish.generate().execute(_command(polish))

    assert H.theme_ids_of(echo_result.plan) == H.theme_ids_of(polish_result.plan)

    echo_values = [mp.theme.value for mp in echo_result.plan.month_periods]
    polish_values = [mp.theme.value for mp in polish_result.plan.month_periods]
    assert echo_values != polish_values, "표현이 전혀 달라지지 않았다"


# ----------------------------------------------------- 실패·빈 값 처리


def test_llm_schema_violation_fails_and_does_not_persist():
    hn = H.make_harness(llm_mode=FakeLLMMode.SCHEMA_VIOLATION)

    with pytest.raises(PlanningError) as exc:
        hn.generate().execute(_command(hn))

    assert exc.value.failure_category is FailureCategory.LLM_OUTPUT_VALIDATION
    assert hn.plans.save_count == 0


def test_llm_final_failure_is_not_a_successful_plan():
    """OD-N04: 재시도 후 실패를 잘못된 Plan 성공으로 처리하지 않는다."""
    hn = H.make_harness(llm_mode=FakeLLMMode.UNAVAILABLE)

    with pytest.raises(PlanningError) as exc:
        hn.generate().execute(_command(hn))

    assert exc.value.failure_category is FailureCategory.LLM_FAILURE
    assert hn.plans.save_count == 0


def test_llm_blank_value_is_rejected():
    hn = H.make_harness(llm_mode=FakeLLMMode.BLANK_VALUE)

    with pytest.raises(PlanningError) as exc:
        hn.generate().execute(_command(hn))

    assert exc.value.failure_category is FailureCategory.REQUIRED_VALUE_VALIDATION
    assert hn.plans.save_count == 0


# ----------------------------------------------- 미확정 수치 하드코딩 금지


def test_max_chars_has_no_hardcoded_default():
    """max_chars는 Source of Truth 미확정이므로 기본값이 없어야 한다."""
    assert ThemePolishConstraints().max_chars is None


def test_generate_does_not_inject_a_max_chars_value_by_default():
    hn = H.make_harness()
    hn.generate().execute(_command(hn))

    for request in hn.llm.calls:
        assert request.constraints.max_chars is None


def test_max_chars_can_be_injected_as_configurable_constraint():
    hn = H.make_harness()
    hn.generate(polish_constraints=ThemePolishConstraints(max_chars=12)).execute(
        _command(hn)
    )

    for request in hn.llm.calls:
        assert request.constraints.max_chars == 12


# --------------------------------------------------- LLM 없는 모드 (RULE_ONLY)


def test_no_llm_mode_produces_rule_only_and_never_calls_llm():
    hn = H.make_harness()
    result = hn.generate(use_llm=False).execute(_command(hn))

    assert not hn.llm.was_called
    assert result.run.llm_invoked is False
    for mp in result.plan.month_periods:
        assert mp.theme.generation.method.value == "RULE_ONLY"


def test_fake_llm_records_calls_for_observability():
    llm = FakeLLM(FakeLLMMode.POLISH)
    assert llm.call_count == 0
    assert not llm.was_called
