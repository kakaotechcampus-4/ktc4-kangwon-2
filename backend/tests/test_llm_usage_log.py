"""`llm_usage` 줄은 **호출 한 번에 한 줄**이다. `scripts/llm-usage.sh` 가 이 줄로 돈을 센다.

연간(`complete_json`)과 월간(`SharedLlmTransport`)이 모두 `post_json` 을 지나므로 기록도
거기 하나다 — 두 곳에서 남기면 두 배로 세고, 한 곳이 빠지면 월간 비용이 안 보인다.
진짜 엘리스는 부르지 않는다. `urlopen` 만 갈아끼운다.
"""

import io
import json
from urllib import error as urllib_error

import pytest
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning.application.yearly_ports import ThemeTextRequest
from ssuksak.planning.domain.year_month import YearMonth

from app.features.plans import monthly_llm
from app.features.plans.llm import EliceThemeTextGenerator
from app.shared.llm import LlmFailed
from app.shared.llm import client as llm

USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}


@pytest.fixture
def usage_lines(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://mlapi.example.com/v1")
    monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-secret")
    monkeypatch.setattr(settings, "llm_mode", "real")
    # `post_json` 은 로컬에서 real 을 막는다(AGENTS.md). 여기서 보려는 것은 사용량 기록이지
    # 그 가드가 아니라서 서버에 선 것처럼 둔다. 가드 자체는 test_plans_llm 이 본다.
    monkeypatch.setattr(settings, "is_server", True)
    lines = []
    # `app.server` 로거는 propagate=False 라 caplog 가 못 본다.
    monkeypatch.setattr(llm.logger, "info", lambda fmt, *args: lines.append(fmt % args))
    return lines


def _answer(monkeypatch, body):
    monkeypatch.setattr(
        llm.urllib_request,
        "urlopen",
        lambda *a, **k: io.BytesIO(json.dumps(body, ensure_ascii=False).encode()),
    )


def test_연간_호출은_한_줄을_남긴다(monkeypatch, usage_lines):
    content = json.dumps({"themes": [{"theme_id": "t", "value": "새 친구"}]}, ensure_ascii=False)
    _answer(monkeypatch, {"choices": [{"message": {"content": content}}], "usage": USAGE})

    request = ThemeTextRequest(
        period=YearMonth(2026, 3), theme_id="t", reference_label="참고", target_ages=(3,)
    )
    EliceThemeTextGenerator().generate((request,))

    assert usage_lines == ["llm_usage model=openai/gpt-6-luna prompt=120 completion=30 total=150"]


def test_월간_호출은_보낸_모델_이름으로_한_줄을_남긴다(monkeypatch, usage_lines):
    _answer(monkeypatch, {"choices": [{"message": {"content": "{}"}}], "usage": USAGE})

    monthly_llm.SharedLlmTransport().post_json(
        "https://mlapi.example.com/v1/chat/completions",
        headers={},
        payload={"model": "monthly-model", "response_format": {}},
        timeout=1,
    )

    assert usage_lines == ["llm_usage model=monthly-model prompt=120 completion=30 total=150"]


def test_전송_성공_줄은_응답_usage_원문을_남기지_않는다(monkeypatch, usage_lines):
    """usage 에 섞여 온 문자열이 일반 로그로 새지 않는다(Codex W7a2-02)."""
    marker = "SYNTHETIC-USAGE-MARKER"
    _answer(
        monkeypatch,
        {"choices": [{"message": {"content": "{}"}}], "usage": {**USAGE, "note": marker}},
    )
    transport_lines = []
    monkeypatch.setattr(
        monthly_llm._log, "info", lambda fmt, *args: transport_lines.append(fmt % args)
    )

    monthly_llm.SharedLlmTransport().post_json(
        "https://mlapi.example.com/v1/chat/completions",
        headers={},
        payload={"model": "weekly-model", "response_format": {}},
        timeout=1,
    )

    assert transport_lines and transport_lines[0].startswith("monthly llm call ok")
    assert all(marker not in line for line in transport_lines + usage_lines)


def test_실패한_호출은_남기지_않는다(monkeypatch, usage_lines):
    def fail(*a, **k):
        raise urllib_error.HTTPError("u", 500, "boom", {}, None)

    monkeypatch.setattr(llm.urllib_request, "urlopen", fail)

    with pytest.raises(LlmFailed):
        llm.post_json("https://x", headers={}, payload={"model": "m"}, timeout=1)
    assert usage_lines == []


def test_mock_이면_엘리스를_부르지_않는다(monkeypatch, usage_lines):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(
        llm.urllib_request, "urlopen", lambda *a, **k: pytest.fail("mock 인데 엘리스를 불렀다")
    )

    assert isinstance(monthly_llm.monthly_llm_provider(), RequestAwareMonthlyLlm)
    assert usage_lines == []
