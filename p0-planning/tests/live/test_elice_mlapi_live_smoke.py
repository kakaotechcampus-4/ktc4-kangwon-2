"""Elice MLAPI Live Smoke Test — 기본 실행에서 제외된다.

실행 조건 **둘 다** 필요하다.

    1. 환경변수: ELICE_MLAPI_BASE_URL, ELICE_MLAPI_API_KEY, LLM_MODEL,
       LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES
    2. 명시적 opt-in: RUN_LIVE_LLM_TESTS=1

실행 방법:

    RUN_LIVE_LLM_TESTS=1 \\
    ELICE_MLAPI_BASE_URL=... ELICE_MLAPI_API_KEY=... \\
    LLM_MODEL=gpt-4.1-mini LLM_TIMEOUT_SECONDS=60 LLM_MAX_RETRIES=2 \\
    LLM_REASONING_EFFORT=none \\
    python -m pytest tests/live -m live -q

`pyproject.toml`의 `addopts`에 `-m "not live"`가 있으므로 일반 실행에서는
수집되지 않는다. API Key는 커밋하지 않는다.

이 테스트의 목적은 품질 평가가 아니라 **문서와 실제 endpoint 동작의 차이를
드러내는 것**이다. 차이가 있으면 추측으로 우회하지 말고 보고한다.
"""

from __future__ import annotations

import os

import pytest

from ssuksak.adapters.elice_mlapi_adapter import EliceMLAPIAdapter
from ssuksak.shared.llm.batch import (
    ThemeBatchPolishItem,
    ThemeBatchPolishRequest,
    reconcile_batch,
)
from ssuksak.shared.llm.config import LLMApiStyle, LLMConfig, load_project_dotenv
from ssuksak.shared.llm.port import ThemePolishConstraints, ThemePolishRequest
from ssuksak.shared.llm.telemetry import LLMCallRecord

# 가드를 평가하기 전에 프로젝트 `.env`를 먼저 로드한다.
# `LLMConfig.from_env()` 안에서만 로드하면 이 모듈의 import 시점에는 아직
# 환경이 비어 있어 실제 설정이 있어도 skip된다.
# `override=False`이므로 인라인으로 준 환경변수가 `.env`보다 우선한다.
load_project_dotenv()

_OPT_IN = os.environ.get("RUN_LIVE_LLM_TESTS") == "1"
_REQUIRED = (
    "ELICE_MLAPI_BASE_URL",
    "ELICE_MLAPI_API_KEY",
    "LLM_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
)
_HAS_ENV = all(os.environ.get(k) for k in _REQUIRED)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not _OPT_IN,
        reason="RUN_LIVE_LLM_TESTS=1로 명시적 opt-in해야 실행된다",
    ),
    pytest.mark.skipif(
        not _HAS_ENV,
        reason=f"필수 환경변수 누락: {_REQUIRED}",
    ),
]


def _records() -> list[LLMCallRecord]:
    return []


def _adapter(records: list[LLMCallRecord], **overrides) -> EliceMLAPIAdapter:
    config = LLMConfig.from_env()
    if overrides:
        from dataclasses import replace

        config = replace(config, **overrides)
    return EliceMLAPIAdapter(config, telemetry_sink=records.append)


def _twelve_month_request() -> ThemeBatchPolishRequest:
    months = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]
    labels = {
        3: "우리 원과 친구",
        4: "봄과 동식물·자연",
        5: "나와 가족",
        6: "우리 동네",
        7: "여름과 건강·안전",
        8: "교통기관",
        9: "우리나라와 세계 여러 나라",
        10: "가을과 자연",
        11: "환경과 생활",
        12: "겨울과 겨울 놀이",
        1: "생활도구",
        2: "성장한 우리",
    }
    items = tuple(
        ThemeBatchPolishItem(
            period_key=f"{2026 if m >= 3 else 2027}-{m:02d}",
            theme_id=f"yr_theme_live_{m:02d}",
            label=labels[m],
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


def test_live_batch_twelve_months_round_trip():
    """12개월 Batch가 1회 요청으로 완결되고 reconcile을 통과하는지."""
    records = _records()
    adapter = _adapter(records)
    request = _twelve_month_request()

    response = adapter.polish_themes(request)
    values = reconcile_batch(response, request.expected)

    assert len(values) == 12
    assert all(v.strip() for v in values.values())

    record = records[0]
    print("\n[live telemetry]", record.to_log_dict())
    assert record.success is True
    assert record.item_count == 12


def test_live_single_regenerate_path():
    records = _records()
    adapter = _adapter(records)

    result = adapter.polish_theme(
        ThemePolishRequest(
            task="polish_yearly_theme_label",
            selected_theme_id="yr_theme_live_10",
            selected_theme_label="가을과 자연",
            period_key="2026-10",
            ages=(3,),
        )
    )

    assert result.theme_id == "yr_theme_live_10"
    assert result.value.strip()
    print("\n[live single]", result.value)


def test_live_chat_completions_style_also_works():
    """Responses API와 Chat Completions 중 실제로 동작하는 쪽을 확인한다."""
    records = _records()
    adapter = _adapter(records, api_style=LLMApiStyle.CHAT_COMPLETIONS)
    request = _twelve_month_request()

    response = adapter.polish_themes(request)
    values = reconcile_batch(response, request.expected)

    assert len(values) == 12
    print("\n[live chat_completions telemetry]", records[0].to_log_dict())


def test_live_models_endpoint_lists_configured_model():
    """GET /v1/models에 설정한 LLM_MODEL이 실제로 있는지 확인한다."""
    from ssuksak.adapters.elice_mlapi_adapter import build_openai_client

    config = LLMConfig.from_env()
    client = build_openai_client(config)

    listed = [m.id for m in client.models.list().data]
    print(f"\n[live models] {len(listed)}개: {sorted(listed)[:20]}")

    assert config.model in listed, (
        f"LLM_MODEL={config.model!r}이 GET /v1/models 목록에 없다. "
        f"모델 ID를 endpoint 값과 일치시켜야 한다."
    )
