"""LLM Config 경계 테스트.

- 필수 환경변수 누락을 기본값으로 보정하지 않는다.
- 모델 문자열이 코드에 확정되어 있지 않다.
- API Key가 repr·str·telemetry 요약에 노출되지 않는다.
"""

from __future__ import annotations

import pytest

from ssuksak.shared.llm.config import (
    REASONING_EFFORT_VALUES,
    LLMApiStyle,
    LLMConfig,
    LLMConfigError,
)

SECRET = "elice-key-should-never-be-logged"

VALID_ENV = {
    "ELICE_MLAPI_BASE_URL": "https://mlapi.elice.io/v1",
    "ELICE_MLAPI_API_KEY": SECRET,
    "LLM_MODEL": "gpt-4.1-mini",
    "LLM_TIMEOUT_SECONDS": "30",
    "LLM_MAX_RETRIES": "2",
}

REQUIRED_KEYS = list(VALID_ENV)


def test_valid_env_loads():
    config = LLMConfig.from_env(dict(VALID_ENV))

    assert config.base_url == "https://mlapi.elice.io/v1"
    assert config.model == "gpt-4.1-mini"
    assert config.timeout_seconds == 30.0
    assert config.max_retries == 2
    assert config.api_style is LLMApiStyle.RESPONSES


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_missing_required_env_fails_fast(key: str):
    env = dict(VALID_ENV)
    del env[key]
    with pytest.raises(LLMConfigError, match=key):
        LLMConfig.from_env(env)


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_blank_required_env_fails_fast(key: str):
    env = dict(VALID_ENV)
    env[key] = "   "
    with pytest.raises(LLMConfigError, match=key):
        LLMConfig.from_env(env)


def test_no_model_default_exists_in_code():
    """모델은 코드 기본값이 없다. 특정 모델을 확정하지 않는다."""
    env = dict(VALID_ENV)
    del env["LLM_MODEL"]
    with pytest.raises(LLMConfigError, match="LLM_MODEL"):
        LLMConfig.from_env(env)


def test_model_is_passed_through_verbatim():
    """Terra / Sol / Sonnet 등을 Config만 바꿔 교체할 수 있어야 한다."""
    for model in ("gpt-4.1-mini", "gpt-5.6-terra", "gpt-5.6-sol", "claude-sonnet-5"):
        env = dict(VALID_ENV) | {"LLM_MODEL": model}
        assert LLMConfig.from_env(env).model == model


def test_no_timeout_or_retry_default_in_code():
    """수치는 제품 결정 전이므로 코드 기본값을 두지 않는다."""
    for key in ("LLM_TIMEOUT_SECONDS", "LLM_MAX_RETRIES"):
        env = dict(VALID_ENV)
        del env[key]
        with pytest.raises(LLMConfigError, match=key):
            LLMConfig.from_env(env)


@pytest.mark.parametrize("bad", ["abc", "", "  ", "3s"])
def test_non_numeric_timeout_is_rejected(bad: str):
    env = dict(VALID_ENV) | {"LLM_TIMEOUT_SECONDS": bad}
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env(env)


@pytest.mark.parametrize("bad", ["0", "-1", "-0.5"])
def test_non_positive_timeout_is_rejected(bad: str):
    env = dict(VALID_ENV) | {"LLM_TIMEOUT_SECONDS": bad}
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env(env)


def test_negative_retries_is_rejected():
    env = dict(VALID_ENV) | {"LLM_MAX_RETRIES": "-1"}
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env(env)


def test_zero_retries_is_allowed():
    env = dict(VALID_ENV) | {"LLM_MAX_RETRIES": "0"}
    assert LLMConfig.from_env(env).max_retries == 0


# ------------------------------------------------------- reasoning effort


def test_reasoning_effort_defaults_to_provisional_low():
    """P0 초기값은 low이며 provisional이다."""
    assert LLMConfig.from_env(dict(VALID_ENV)).reasoning_effort == "low"


@pytest.mark.parametrize("effort", REASONING_EFFORT_VALUES)
def test_supported_reasoning_efforts(effort: str):
    env = dict(VALID_ENV) | {"LLM_REASONING_EFFORT": effort}
    assert LLMConfig.from_env(env).reasoning_effort == effort


def test_reasoning_effort_can_be_disabled():
    """reasoning 미지원 모델(예: gpt-4.1-mini)을 위해 none을 허용한다."""
    env = dict(VALID_ENV) | {"LLM_REASONING_EFFORT": "none"}
    assert LLMConfig.from_env(env).reasoning_effort is None


def test_unknown_reasoning_effort_is_rejected():
    env = dict(VALID_ENV) | {"LLM_REASONING_EFFORT": "turbo"}
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env(env)


# ------------------------------------------------------------- api style


@pytest.mark.parametrize("style", ["responses", "chat_completions"])
def test_api_style_is_configurable(style: str):
    env = dict(VALID_ENV) | {"LLM_API_STYLE": style}
    assert LLMConfig.from_env(env).api_style.value == style


def test_unknown_api_style_is_rejected():
    env = dict(VALID_ENV) | {"LLM_API_STYLE": "grpc"}
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env(env)


def test_max_output_tokens_is_optional():
    assert LLMConfig.from_env(dict(VALID_ENV)).max_output_tokens is None
    env = dict(VALID_ENV) | {"LLM_MAX_OUTPUT_TOKENS": "2048"}
    assert LLMConfig.from_env(env).max_output_tokens == 2048


def test_non_numeric_max_output_tokens_is_rejected():
    env = dict(VALID_ENV) | {"LLM_MAX_OUTPUT_TOKENS": "many"}
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env(env)


# ------------------------------------------------------------- Key 비노출


def test_api_key_is_not_in_repr_or_str():
    config = LLMConfig.from_env(dict(VALID_ENV))
    assert SECRET not in repr(config)
    assert SECRET not in str(config)


def test_api_key_is_not_in_safe_summary():
    config = LLMConfig.from_env(dict(VALID_ENV))
    summary = config.safe_summary
    assert "api_key" not in summary
    assert SECRET not in repr(summary)
    # 진단에 필요한 값은 남는다.
    assert summary["model"] == "gpt-4.1-mini"
    assert summary["base_url"] == "https://mlapi.elice.io/v1"


def test_api_key_is_still_available_to_the_adapter():
    config = LLMConfig.from_env(dict(VALID_ENV))
    assert config.api_key == SECRET


def test_direct_construction_validates_too():
    with pytest.raises(LLMConfigError):
        LLMConfig(
            base_url="https://x/v1",
            model="m",
            timeout_seconds=1.0,
            max_retries=0,
            api_key="",
        )
