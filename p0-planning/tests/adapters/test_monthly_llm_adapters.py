from __future__ import annotations

import json

import pytest

from ssuksak.adapters.deterministic_monthly_llm import DeterministicMonthlyLlm
from ssuksak.adapters.elice_openai_monthly import (
    EliceOpenAiMonthlyAdapter,
    MonthlyLlmConfig,
    MonthlyLlmConfigurationError,
    MonthlyLlmProviderError,
)
from ssuksak.planning.planner.contracts import (
    MONTHLY_MODEL,
    MonthlyPlanningRequest,
)


def request() -> MonthlyPlanningRequest:
    return MonthlyPlanningRequest(
        task="monthly_plan_proposal",
        prompt_version="v1",
        system_prompt="system",
        user_content="{}",
        target_month="2026-09",
        expected_theme_id="theme",
        expected_week_ids=("W1",),
        packet_fingerprint="1" * 64,
    )


class RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, *, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        return self.response


def test_config_is_explicit_safe_and_pins_monthly_model():
    config = MonthlyLlmConfig("https://mlapi.elice.io/v1", "secret")
    assert config.model == MONTHLY_MODEL
    assert "secret" not in repr(config)
    assert config.endpoint.endswith("/chat/completions")

    with pytest.raises(MonthlyLlmConfigurationError, match="model"):
        MonthlyLlmConfig("https://mlapi.elice.io/v1", "secret", "other")


def test_config_from_env_fails_only_when_called():
    with pytest.raises(MonthlyLlmConfigurationError, match="BASE_URL"):
        MonthlyLlmConfig.from_env({})
    with pytest.raises(MonthlyLlmConfigurationError, match="HTTPS"):
        MonthlyLlmConfig("http://mlapi.elice.io/v1", "secret")


def test_elice_adapter_uses_openai_compatible_json_without_network():
    response_content = json.dumps({"ok": True})
    transport = RecordingTransport(
        {
            "id": "req-1",
            "model": MONTHLY_MODEL,
            "choices": [{"message": {"content": response_content}}],
        }
    )
    adapter = EliceOpenAiMonthlyAdapter(
        MonthlyLlmConfig("https://mlapi.elice.io/v1", "secret"),
        transport=transport,
    )
    response = adapter.generate_monthly(request())
    url, headers, payload, timeout = transport.calls[0]
    assert response.content == response_content
    assert response.request_id == "req-1"
    assert url == "https://mlapi.elice.io/v1/chat/completions"
    assert headers["Authorization"] == "Bearer secret"
    assert payload["model"] == MONTHLY_MODEL
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert timeout == 30.0


def test_elice_adapter_rejects_malformed_response():
    adapter = EliceOpenAiMonthlyAdapter(
        MonthlyLlmConfig("https://mlapi.elice.io/v1", "secret"),
        transport=RecordingTransport({"choices": []}),
    )
    with pytest.raises(MonthlyLlmProviderError, match="choices"):
        adapter.generate_monthly(request())


def test_fake_is_monthly_specific_and_deterministic():
    fake = DeterministicMonthlyLlm("{}", "{}")
    first = fake.generate_monthly(request())
    second = fake.generate_monthly(request())
    assert first.content == second.content == "{}"
    assert len(fake.monthly_requests) == 2
    assert not hasattr(fake, "polish_themes")
