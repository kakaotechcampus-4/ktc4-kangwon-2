"""월간 LLM provider 를 고른다 (결정 문서 12.3 D-2).

**요청 모양 · strict 스키마 · 응답 해석은 p0-planning 어댑터(`EliceOpenAiMonthlyAdapter`)가
한다.** Backend 는 다시 만들지 않고 전송만 꽂는다 — `shared/llm.post_json` 이 주소 · 키 설정과
오류 3종(`LlmBudgetExceeded` · `LlmUnavailable` · `LlmFailed`) 분류를 맡는 유일한 문이다.

**mock 과 real 은 설정이 가른다. 실패했다고 mock 으로 갈아타지 않는다** — 가짜 결과를 진짜
생성으로 저장하게 된다(결정 문서 12.5).
"""

from __future__ import annotations

import logging
import time

from ssuksak.adapters.elice_openai_monthly import EliceOpenAiMonthlyAdapter, MonthlyLlmConfig
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm

from app.shared.llm import TIMEOUT_SECONDS, is_mock, post_json, require_config

_log = logging.getLogger(__name__)


class SharedLlmTransport:
    """Core `JsonTransport` 모양으로 `shared/llm.post_json` 을 부른다.

    호출마다 스키마 이름 · 모델 · 걸린 시간 · 토큰 · 성공 여부를 남긴다(CLAUDE.md §21).
    **프롬프트 · 응답 본문 · 키는 남기지 않는다.**
    """

    def post_json(self, url, *, headers, payload, timeout):
        schema = payload.get("response_format", {}).get("json_schema", {}).get("name")
        started = time.perf_counter()
        try:
            result = post_json(url, headers=headers, payload=payload, timeout=timeout)
        except Exception as error:
            _log.warning(
                "monthly llm call failed schema=%s model=%s seconds=%.2f error=%s",
                schema,
                payload.get("model"),
                time.perf_counter() - started,
                type(error).__name__,
            )
            raise
        usage = result.get("usage") if isinstance(result, dict) else None
        _log.info(
            "monthly llm call ok schema=%s model=%s seconds=%.2f usage=%s",
            schema,
            payload.get("model"),
            time.perf_counter() - started,
            usage,
        )
        return result


def monthly_llm_provider():
    """mock 이면 요청 기반 결정적 provider, real 이면 Luna-6.

    real 인데 설정이 없으면 `LlmUnavailable` 를 그대로 낸다 — 부르기 전에 멈춘다.
    """
    if is_mock():
        return RequestAwareMonthlyLlm()
    base_url, api_key = require_config()
    return EliceOpenAiMonthlyAdapter(
        MonthlyLlmConfig(base_url, api_key, timeout_seconds=TIMEOUT_SECONDS),
        transport=SharedLlmTransport(),
    )
