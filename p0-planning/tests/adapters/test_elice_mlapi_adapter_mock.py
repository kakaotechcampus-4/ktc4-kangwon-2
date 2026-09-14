"""EliceMLAPIAdapter Mock 테스트 — 네트워크 없음.

client를 주입해 Adapter의 전 경로(요청 조립·응답 추출·오류 분류·재시도·
telemetry)를 실제 HTTP 없이 검증한다.

Live 호출은 `tests/live/`에 분리되어 있고 opt-in에서만 실행된다.
"""

from __future__ import annotations

import pytest

from ssuksak.adapters.elice_mlapi_adapter import (
    PROVIDER_NAME,
    EliceMLAPIAdapter,
)
from ssuksak.shared.llm.batch import (
    PolishedThemeOut,
    ThemeBatchPolishItem,
    ThemeBatchPolishRequest,
    ThemeBatchPolishResponse,
)
from ssuksak.shared.llm.config import LLMApiStyle, LLMConfig
from ssuksak.shared.llm.port import (
    LLMConfigurationError,
    LLMUnavailableError,
    ThemePolishConstraints,
    ThemePolishRequest,
)
from ssuksak.shared.llm.telemetry import LLMCallRecord

MODEL = "gpt-4.1-mini"
API_KEY = "test-key-not-a-real-secret"


def _config(**overrides) -> LLMConfig:
    base = {
        "base_url": "https://mlapi.example.test/v1",
        "model": MODEL,
        "timeout_seconds": 5.0,
        "max_retries": 2,
        "api_key": API_KEY,
        "reasoning_effort": None,
        "api_style": LLMApiStyle.RESPONSES,
    }
    base.update(overrides)
    return LLMConfig(**base)


def _batch_request(n: int = 3) -> ThemeBatchPolishRequest:
    months = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2][:n]
    items = tuple(
        ThemeBatchPolishItem(
            period_key=f"{2026 if m >= 3 else 2027}-{m:02d}",
            theme_id=f"yr_theme_{m}",
            label=f"주제{m}",
        )
        for m in months
    )
    return ThemeBatchPolishRequest(
        task="polish_yearly_theme_labels",
        school_year=2026,
        ages=(3,),
        items=items,
        constraints=ThemePolishConstraints(),
    )


# ------------------------------------------------------------ Stub client


class _Usage:
    def __init__(self, i=100, o=50, style="responses"):
        if style == "responses":
            self.input_tokens, self.output_tokens = i, o
        else:
            self.prompt_tokens, self.completion_tokens = i, o


class _ParsedResponses:
    def __init__(self, parsed, rid="resp_mock_1"):
        self.output_parsed = parsed
        self.id = rid
        self.usage = _Usage(style="responses")


class _Msg:
    def __init__(self, parsed, refusal=None):
        self.parsed = parsed
        self.refusal = refusal
        self.content = None


class _Choice:
    def __init__(self, msg):
        self.message = msg


class _ParsedChat:
    def __init__(self, parsed, rid="chatcmpl_mock_1", refusal=None):
        self.choices = [_Choice(_Msg(parsed, refusal))]
        self.id = rid
        self.usage = _Usage(style="chat")


class StubClient:
    """openai client 표면만 흉내내는 stub. 네트워크를 쓰지 않는다."""

    def __init__(self, *, responses_result=None, chat_result=None, style=None):
        self.calls: list[dict] = []
        self._responses_result = responses_result
        self._chat_result = chat_result
        self._style = style or ("chat" if chat_result is not None else "responses")
        outer = self

        class _Responses:
            def parse(self, **kwargs):
                outer.calls.append({"api": "responses", **kwargs})
                return outer._resolve(outer._responses_result)

        class _Completions:
            def parse(self, **kwargs):
                outer.calls.append({"api": "chat", **kwargs})
                return outer._resolve(outer._chat_result)

        class _Chat:
            completions = _Completions()

        self.responses = _Responses()
        self.chat = _Chat()

    def _resolve(self, result):
        if isinstance(result, list):
            item = result.pop(0)
        else:
            item = result
        if isinstance(item, Exception):
            raise item
        # 편의: 스키마 객체를 그대로 주면 API 응답 봉투로 감싼다.
        if isinstance(item, ThemeBatchPolishResponse):
            return (
                _ParsedResponses(item)
                if self._style == "responses"
                else _ParsedChat(item)
            )
        return item


# openai 예외 이름을 그대로 쓰는 가짜 예외 (분류는 클래스 이름 기반)
def _make_exc(name: str, message: str = "boom", headers: dict | None = None):
    def _init(self, msg=message):
        Exception.__init__(self, msg)
        if headers is not None:
            self.response = type("R", (), {"headers": headers})()

    return type(name, (Exception,), {"__init__": _init})()


def _ok_batch(n: int = 3) -> ThemeBatchPolishResponse:
    req = _batch_request(n)
    return ThemeBatchPolishResponse(
        themes=[
            PolishedThemeOut(
                period_key=i.period_key, theme_id=i.theme_id, value=f"{i.label} 표현"
            )
            for i in req.items
        ]
    )


def _adapter(client, config=None, records=None, sleeps=None):
    return EliceMLAPIAdapter(
        config or _config(),
        client=client,
        telemetry_sink=(records.append if records is not None else lambda r: None),
        sleep=(sleeps.append if sleeps is not None else lambda d: None),
        monotonic=iter_monotonic(),
    )


def iter_monotonic():
    state = {"t": 0.0}

    def _now():
        state["t"] += 0.010
        return state["t"]

    return _now


# ==================================================================== 정상


def test_normal_batch_returns_all_items():
    records: list[LLMCallRecord] = []
    client = StubClient(responses_result=_ok_batch(3))
    adapter = _adapter(client, records=records)

    result = adapter.polish_themes(_batch_request(3))

    assert len(result.themes) == 3
    assert {t.period_key for t in result.themes} == {"2026-03", "2026-04", "2026-05"}
    assert len(client.calls) == 1, "Batch는 요청 1회여야 한다"
    assert records[0].success is True
    assert records[0].validation_result == "OK"


def test_request_uses_responses_api_and_carries_schema():
    client = StubClient(responses_result=_ok_batch(3))
    _adapter(client).polish_themes(_batch_request(3))

    call = client.calls[0]
    assert call["api"] == "responses"
    assert call["model"] == MODEL
    assert call["text_format"] is ThemeBatchPolishResponse
    assert "instructions" in call
    # 후보 목록이 프롬프트에 없어야 한다.
    assert "candidates" not in call["input"]
    assert "eligible" not in call["input"]


def test_chat_completions_style_is_supported():
    client = StubClient(chat_result=_ParsedChat(_ok_batch(3)))
    adapter = _adapter(client, config=_config(api_style=LLMApiStyle.CHAT_COMPLETIONS))

    result = adapter.polish_themes(_batch_request(3))

    assert len(result.themes) == 3
    assert client.calls[0]["api"] == "chat"
    assert client.calls[0]["response_format"] is ThemeBatchPolishResponse


def test_responses_result_is_unwrapped_from_output_parsed():
    client = StubClient(responses_result=_ParsedResponses(_ok_batch(3)))
    result = _adapter(client).polish_themes(_batch_request(3))
    assert len(result.themes) == 3


def test_reasoning_effort_is_sent_only_when_configured():
    client = StubClient(responses_result=_ok_batch(3))
    _adapter(client, config=_config(reasoning_effort=None)).polish_themes(
        _batch_request(3)
    )
    assert "reasoning" not in client.calls[0]

    client2 = StubClient(responses_result=_ok_batch(3))
    _adapter(client2, config=_config(reasoning_effort="low")).polish_themes(
        _batch_request(3)
    )
    assert client2.calls[0]["reasoning"] == {"effort": "low"}


def test_model_is_never_hardcoded_in_adapter():
    """모델은 Config에서만 들어온다."""
    client = StubClient(responses_result=_ok_batch(3))
    _adapter(client, config=_config(model="some-other-model")).polish_themes(
        _batch_request(3)
    )
    assert client.calls[0]["model"] == "some-other-model"


# ============================================================ 출력 이상


def test_theme_id_swap_is_visible_to_caller():
    """Adapter는 값을 그대로 전달하고 reconcile이 잡는다."""
    bad = ThemeBatchPolishResponse(
        themes=[
            PolishedThemeOut(period_key="2026-03", theme_id="SWAPPED", value="x"),
            PolishedThemeOut(period_key="2026-04", theme_id="yr_theme_4", value="y"),
            PolishedThemeOut(period_key="2026-05", theme_id="yr_theme_5", value="z"),
        ]
    )
    result = _adapter(StubClient(responses_result=bad)).polish_themes(_batch_request(3))

    from ssuksak.shared.llm.batch import BatchReconcileError, reconcile_batch

    with pytest.raises(BatchReconcileError):
        reconcile_batch(result, _batch_request(3).expected)


def test_missing_parsed_output_is_schema_error():
    client = StubClient(responses_result=_ParsedResponses(None))
    with pytest.raises(ValueError, match="parsed"):
        _adapter(client).polish_themes(_batch_request(3))


def test_chat_refusal_is_schema_error():
    client = StubClient(chat_result=_ParsedChat(None, refusal="거부합니다"))
    adapter = _adapter(client, config=_config(api_style=LLMApiStyle.CHAT_COMPLETIONS))
    with pytest.raises(ValueError, match="거부"):
        adapter.polish_themes(_batch_request(3))


def test_malformed_output_is_not_retried():
    records: list[LLMCallRecord] = []
    client = StubClient(responses_result=_ParsedResponses(None))
    with pytest.raises(ValueError):
        _adapter(client, records=records).polish_themes(_batch_request(3))

    assert len(client.calls) == 1, "스키마 오류는 재시도하지 않는다"
    assert records[0].success is False
    assert records[0].failure_kind == "SCHEMA"


# ============================================================ Provider 오류


def test_timeout_is_retried_then_raises_unavailable():
    records: list[LLMCallRecord] = []
    sleeps: list[float] = []
    client = StubClient(
        responses_result=[_make_exc("APITimeoutError") for _ in range(3)]
    )
    with pytest.raises(LLMUnavailableError) as exc:
        _adapter(client, records=records, sleeps=sleeps).polish_themes(_batch_request(3))

    assert len(client.calls) == 3, "max_retries=2 이므로 총 3회 시도"
    assert len(sleeps) == 2
    assert exc.value.kind == "TIMEOUT"
    assert records[0].retry_count == 2
    assert records[0].success is False


def test_rate_limit_honours_retry_after_header():
    sleeps: list[float] = []
    client = StubClient(
        responses_result=[
            _make_exc("RateLimitError", headers={"retry-after": "2.5"}),
            _ok_batch(3),
        ]
    )
    result = _adapter(client, sleeps=sleeps).polish_themes(_batch_request(3))

    assert len(result.themes) == 3
    assert sleeps == [2.5], "retry-after 헤더를 존중해야 한다"


def test_retry_succeeds_and_records_retry_count():
    records: list[LLMCallRecord] = []
    client = StubClient(
        responses_result=[_make_exc("APIConnectionError"), _ok_batch(3)]
    )
    _adapter(client, records=records).polish_themes(_batch_request(3))

    assert records[0].success is True
    assert records[0].retry_count == 1


def test_authentication_failure_is_config_error_and_not_retried():
    records: list[LLMCallRecord] = []
    client = StubClient(responses_result=_make_exc("AuthenticationError"))

    with pytest.raises(LLMConfigurationError) as exc:
        _adapter(client, records=records).polish_themes(_batch_request(3))

    assert len(client.calls) == 1, "인증 실패는 재시도하지 않는다"
    assert exc.value.kind == "AUTH"
    assert records[0].failure_kind == "AUTH"
    # 메시지에 API Key가 들어가지 않는다.
    assert API_KEY not in str(exc.value)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("PermissionDeniedError", "PERMISSION"),
        ("NotFoundError", "NOT_FOUND"),
        ("BadRequestError", "BAD_REQUEST"),
    ],
)
def test_non_retryable_provider_errors_are_config_errors(name: str, kind: str):
    client = StubClient(responses_result=_make_exc(name))
    with pytest.raises(LLMConfigurationError) as exc:
        _adapter(client).polish_themes(_batch_request(3))
    assert exc.value.kind == kind
    assert len(client.calls) == 1


def test_zero_retries_config_attempts_once():
    client = StubClient(
        responses_result=[_make_exc("APITimeoutError") for _ in range(2)]
    )
    with pytest.raises(LLMUnavailableError):
        _adapter(client, config=_config(max_retries=0)).polish_themes(_batch_request(3))
    assert len(client.calls) == 1


# ============================================================ 단건 경로


def test_single_polish_theme_path_works():
    single = ThemeBatchPolishResponse(
        themes=[
            PolishedThemeOut(
                period_key="2026-10", theme_id="yr_theme_autumn", value="가을 표현"
            )
        ]
    )
    client = StubClient(responses_result=single)
    request = ThemePolishRequest(
        task="polish_yearly_theme_label",
        selected_theme_id="yr_theme_autumn",
        selected_theme_label="가을과 자연",
        period_key="2026-10",
        ages=(3,),
    )
    result = _adapter(client).polish_theme(request)

    assert result.theme_id == "yr_theme_autumn"
    assert result.value == "가을 표현"
    assert len(client.calls) == 1


def test_single_path_rejects_multi_item_response():
    client = StubClient(responses_result=_ok_batch(3))
    request = ThemePolishRequest(
        task="polish_yearly_theme_label",
        selected_theme_id="yr_theme_3",
        selected_theme_label="주제3",
        period_key="2026-03",
        ages=(3,),
    )
    with pytest.raises(ValueError, match="단건"):
        _adapter(client).polish_theme(request)


# ============================================================ Telemetry


def test_telemetry_record_has_all_required_fields():
    records: list[LLMCallRecord] = []
    client = StubClient(responses_result=_ParsedResponses(_ok_batch(3)))
    _adapter(client, records=records).polish_themes(_batch_request(3))

    r = records[0]
    assert r.operation == "polish_themes"
    assert r.provider == PROVIDER_NAME
    assert r.model == MODEL
    assert r.input_tokens == 100
    assert r.output_tokens == 50
    assert r.total_tokens == 150
    assert r.latency_ms >= 0
    assert r.success is True
    assert r.retry_count == 0
    assert r.validation_result == "OK"
    assert r.item_count == 3
    assert r.request_id == "resp_mock_1"


def test_telemetry_never_contains_api_key_or_prompt():
    records: list[LLMCallRecord] = []
    client = StubClient(responses_result=_ok_batch(3))
    _adapter(client, records=records).polish_themes(_batch_request(3))

    payload = records[0].to_log_dict()
    serialized = repr(payload)

    assert API_KEY not in serialized
    assert "instructions" not in payload
    assert "input" not in payload
    assert "prompt" not in payload
    assert "messages" not in payload
    # Reference 식별자는 남아도 된다.
    assert payload["theme_ids"]
    assert payload["period_keys"]


def test_telemetry_rejects_sensitive_extra_keys():
    with pytest.raises(ValueError, match="민감"):
        LLMCallRecord(
            operation="op",
            provider="p",
            model="m",
            success=True,
            latency_ms=1,
            retry_count=0,
            item_count=1,
            extra={"api_key": "leak"},
        )


def test_chat_style_usage_fields_are_mapped():
    client = StubClient(chat_result=_ParsedChat(_ok_batch(3)))
    records: list[LLMCallRecord] = []
    adapter = EliceMLAPIAdapter(
        _config(api_style=LLMApiStyle.CHAT_COMPLETIONS),
        client=client,
        telemetry_sink=records.append,
        sleep=lambda d: None,
        monotonic=iter_monotonic(),
    )
    adapter.polish_themes(_batch_request(3))

    assert records[0].input_tokens == 100
    assert records[0].output_tokens == 50
    assert records[0].api_style == "chat_completions"


def test_config_summary_and_str_hide_api_key():
    config = _config()
    assert API_KEY not in str(config)
    assert API_KEY not in repr(config)
    assert "api_key" not in config.safe_summary
