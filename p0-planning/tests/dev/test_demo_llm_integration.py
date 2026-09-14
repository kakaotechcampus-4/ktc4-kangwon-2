"""Demo Integration — LLM Planner 경로 (L8).

**실제 API를 호출하지 않는다.** Composition이 무엇을 조립하는지와, Demo Backend
route가 그 결과를 어떻게 다루는지를 확인한다. 실제 호출 결과는
`analysis/experiments/...` Live Smoke가 담당한다.

Demo는 Business Logic을 갖지 않는다. 여기서 검증하는 것은 **조립과 표시**다.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

DEMO_BACKEND = pathlib.Path(__file__).resolve().parents[2] / "demo-planning" / "backend"
if str(DEMO_BACKEND) not in sys.path:
    sys.path.insert(0, str(DEMO_BACKEND))

from ssuksak.planning.application.monthly_dto import (  # noqa: E402
    MonthlyGenerationMode,
)
from ssuksak.shared.llm.config import LLMConfigError  # noqa: E402

import composition as demo_composition  # noqa: E402
import views as demo_views  # noqa: E402


def _has_llm_config() -> bool:
    from ssuksak.shared.llm.config import LLMConfig

    try:
        LLMConfig.from_env()
    except LLMConfigError:
        return False
    return True


needs_config = pytest.mark.skipif(
    not _has_llm_config(), reason="LLM 설정 없음 (Demo는 설정을 요구한다)"
)


# ============================================== Composition


@needs_config
def test_demo_uses_llm_planner_by_default():
    """L8 기본 시연 경로는 LLM_PLANNER다."""
    wiring = demo_composition.build_demo_wiring()
    assert wiring.monthly_generation_mode is MonthlyGenerationMode.LLM_PLANNER
    assert wiring.monthly_generate._llm_planner is not None
    assert wiring.monthly_regenerate._llm_cells is not None


@needs_config
def test_demo_uses_the_week_experience_template():
    wiring = demo_composition.build_demo_wiring()
    assert wiring.template_ref.template_version == "monthly-template-a-v0.2.0"


@needs_config
def test_demo_records_the_model_without_exposing_credentials():
    wiring = demo_composition.build_demo_wiring()
    assert wiring.monthly_model
    blob = repr(wiring.monthly_model) + repr(wiring.template_ref)
    assert "ELICE_MLAPI_API_KEY" not in blob
    assert "sk-" not in blob


@needs_config
def test_rule_only_option_is_preserved():
    """기존 Rule-only Demo 경로를 삭제하지 않았다."""
    wiring = demo_composition.build_demo_wiring(monthly_llm=False)
    assert wiring.monthly_generation_mode is MonthlyGenerationMode.RULE_ONLY
    assert wiring.monthly_generate._llm_planner is None
    assert wiring.monthly_regenerate._llm_cells is None
    assert wiring.template_ref.template_version == "monthly-template-a-v0.1.0"


@needs_config
def test_the_two_modes_pick_different_templates():
    llm = demo_composition.build_demo_wiring()
    rule = demo_composition.build_demo_wiring(monthly_llm=False)
    assert llm.template_ref.template_version != rule.template_ref.template_version


def test_demo_does_not_read_pdfs_at_runtime():
    """Evidence는 Store JSON으로 읽는다. Runtime에 PDF를 파싱하지 않는다."""
    source = (DEMO_BACKEND / "composition.py").read_text("utf-8")
    for banned in ("pymupdf", "pdfplumber", "pdftotext", ".pdf"):
        assert banned not in source.lower()


# ============================================== 화면 표시


def test_focus_is_labelled_for_teachers_not_by_internal_name():
    """`focus` · `week_axis` 같은 내부 이름을 사용자에게 노출하지 않는다."""
    assert demo_views.SECTION_LABELS["focus"] == "중심 경험"
    assert "focus" not in demo_views.SECTION_LABELS.values()
    assert "week_axis" not in demo_views.SECTION_LABELS.values()


def test_row_display_order_puts_focus_before_outdoor():
    order = demo_views.ROW_DISPLAY_ORDER
    assert order["focus"] < order["outdoor_play"] < order["safety_education"]


def test_week_axis_is_never_rendered_as_a_content_row():
    source = (DEMO_BACKEND / "views.py").read_text("utf-8")
    assert '"week_axis"' in source  # 제외 목록에 있다
    assert "week_axis" not in demo_views.ROW_DISPLAY_ORDER


def test_safety_note_does_not_claim_ai_generated_content():
    """AI가 안전교육을 만든 것처럼 보이면 안 된다."""
    note = demo_views.CELL_STATE_NOTE["EMPTY_UNRESOLVED"]
    assert "source" in note or "근거" in note
    assert "AI" not in note


# ============================================== Backend route


@needs_config
def test_monthly_generate_route_passes_the_composition_mode():
    """Frontend가 mode나 template 문자열을 보내지 않는다."""
    source = (DEMO_BACKEND / "app.py").read_text("utf-8")
    assert "generation_mode=w.monthly_generation_mode" in source
    assert "template_ref=w.template_ref" in source
    # Frontend는 **보내지** 않는다. 화면에 모드를 표시하는 것은 별개다.
    frontend = (DEMO_BACKEND.parent / "frontend" / "app.js").read_text("utf-8")
    assert "monthly-template-a" not in frontend
    generate_call = frontend.split('"/api/monthly/generate"')[1][:200]
    assert "target_month" in generate_call
    assert "generation_mode" not in generate_call
    assert "template" not in generate_call


def test_llm_failures_are_classified_not_generic_500():
    """실패 UX가 500 UNEXPECTED로 떨어지지 않는다."""
    source = (DEMO_BACKEND / "app.py").read_text("utf-8")
    assert "except LLMUnavailableError" in source
    assert "except LLMConfigurationError" in source
    assert '"kind": "LLM_UNAVAILABLE"' in source


def test_demo_never_falls_back_to_rule_only_on_llm_failure():
    """조용한 fallback이 없다."""
    source = (DEMO_BACKEND / "app.py").read_text("utf-8")
    # 실패 handler 어디에도 RULE_ONLY 재실행이 없다.
    assert "RULE_ONLY" not in source.split("except LLMUnavailableError")[1][:1500]


def test_cell_regeneration_payload_carries_no_prompt_or_source_text():
    source = (DEMO_BACKEND / "app.py").read_text("utf-8")
    block = source.split('state["last_cell_regeneration"]')[1][:900]
    for banned in ("user_content", "system_prompt", "packet", "grounding_source_ids"):
        assert banned not in block


def test_frontend_offers_regenerate_only_for_focus_and_outdoor():
    frontend = (DEMO_BACKEND.parent / "frontend" / "app.js").read_text("utf-8")
    assert 'sectionKey === "outdoor_play" || sectionKey === "focus"' in frontend
    # theme / safety 재생성 버튼을 만들지 않는다.
    assert 'sectionKey === "theme"' not in frontend
    assert 'sectionKey === "safety_education"' not in frontend


def test_frontend_disables_actions_when_not_editable():
    frontend = (DEMO_BACKEND.parent / "frontend" / "app.js").read_text("utf-8")
    assert "regen.disabled = !editable" in frontend
    assert 'monthlyConfirm").disabled = m.status === "CONFIRMED"' in frontend


def test_frontend_guards_against_concurrent_mutations():
    """같은 Plan에 동시 요청을 날리지 않는다 (§12·§27)."""
    frontend = (DEMO_BACKEND.parent / "frontend" / "app.js").read_text("utf-8")
    assert "cell__tools button" in frontend
    assert "if (btn.disabled) return;" in frontend


def test_frontend_shows_a_loading_state_for_generate_and_regenerate():
    frontend = (DEMO_BACKEND.parent / "frontend" / "app.js").read_text("utf-8")
    assert "월간계획을 생성하고 있습니다" in frontend
    assert "이 항목을 다시 생성하고 있습니다" in frontend


def test_frontend_does_not_expose_technical_origin_terms_to_teachers():
    """REFERENCE / LLM_SYNTHESIZED를 교사 화면 문구로 쓰지 않는다."""
    frontend = (DEMO_BACKEND.parent / "frontend" / "app.js").read_text("utf-8")
    for banned in ("LLM_SYNTHESIZED", "RULE_LLM", "packet_fingerprint"):
        assert banned not in frontend


def test_frontend_has_no_provider_picker():
    """교사가 모델이나 생성 경로를 고르는 UI를 만들지 않는다 (§37).

    모델 이름을 화면에 **표시**하는 것과 교사가 **고르게** 하는 것은 다르다.
    금지 대상은 후자다 — select/radio/checkbox로 모델이나 경로를 바꾸는 입력.
    """
    frontend = (DEMO_BACKEND.parent / "frontend" / "app.js").read_text("utf-8")
    index = (DEMO_BACKEND.parent / "frontend" / "index.html").read_text("utf-8")

    # 모델 문자열을 코드에 박아 두지 않는다.
    for banned in ("gpt-4.1", "gpt-5", "claude-"):
        assert banned not in frontend.lower()
        assert banned not in index.lower()

    # 경로를 고르는 입력이 없다.
    for banned in ("모델 선택", "생성 방식", "id=\"llmMode\"", "name=\"provider\""):
        assert banned not in index

    # mode를 바꾸는 요청을 보내지 않는다.
    assert "generation_mode:" not in frontend
    assert "monthly_llm" not in frontend
