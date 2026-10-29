"""월간 LLM provider 를 고른다 (결정 문서 12.3 D-2).

**요청 모양 · strict 스키마 · 응답 해석은 p0-planning 어댑터(`EliceOpenAiMonthlyAdapter`)가
한다.** Backend 는 다시 만들지 않고 전송만 꽂는다 — `shared/llm.post_json` 이 주소 · 키 설정과
오류 3종(`LlmBudgetExceeded` · `LlmUnavailable` · `LlmFailed`) 분류를 맡는 유일한 문이다.

**mock 과 real 은 설정이 가른다. 실패했다고 mock 으로 갈아타지 않는다** — 가짜 결과를 진짜
생성으로 저장하게 된다(결정 문서 12.5).
"""

from __future__ import annotations

import json
import logging
import time

from ssuksak.adapters.elice_openai_monthly import (
    EliceOpenAiMonthlyAdapter,
    MonthlyLlmConfig,
    assemble_chat_stream,
)
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning.planner.contracts import RawLlmResponse
from ssuksak.planning.planner.play_monthly import PlayMonthlyRequest

from app.shared.llm import TIMEOUT_SECONDS, is_mock, post_json, post_stream, require_config

_log = logging.getLogger(__name__)
# 스트림 한 번의 전체 시간이다(read 제한 아님). 놀이 프로젝트는 구간마다(ADR-043 §5),
# 놀이 월간은 첫 요청 · 수리마다(ADR-046 §5) 한 번씩이다. nginx 대기 시간이 이 값에 맞춰져 있다.
PLAY_PROJECT_STREAM_DEADLINE_SECONDS = 120


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
        # 응답의 usage 객체는 남기지 않는다(Codex W7a2-02) — 모델이 어떤 문자열 필드를 붙여 올지
        # 모른다. 토큰 수는 `post_json` 의 `llm_usage` 줄이 숫자로 남긴다.
        _log.info(
            "monthly llm call ok schema=%s model=%s seconds=%.2f",
            schema,
            payload.get("model"),
            time.perf_counter() - started,
        )
        return result

    def post_stream(self, url, *, headers, payload, timeout):
        """놀이 프로젝트(구간별)와 놀이 월간(첫 요청 · 수리)이 스트리밍한다."""
        schema = payload.get("response_format", {}).get("json_schema", {}).get("name")
        started = time.perf_counter()
        try:
            result = post_stream(
                url,
                headers=headers,
                payload=payload,
                timeout=timeout,
                fold=assemble_chat_stream,
                deadline=PLAY_PROJECT_STREAM_DEADLINE_SECONDS,
            )
        except Exception as error:
            _log.warning(
                "monthly llm call failed schema=%s model=%s seconds=%.2f error=%s",
                schema,
                payload.get("model"),
                time.perf_counter() - started,
                type(error).__name__,
            )
            raise
        _log.info(
            "monthly llm call ok schema=%s model=%s seconds=%.2f",
            schema,
            payload.get("model"),
            time.perf_counter() - started,
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


class MockPlayMonthlyProvider:
    """mock 모드의 놀이 중심 월간. 요청이 허용한 ID 만 써서 Core 검사를 통과하는 답을 만든다.

    자료 승인 검사는 Core 가 그대로 한다 — mock 이어도 미승인 자료로는 만들지 않는다.
    """

    def generate_play_monthly(self, request: PlayMonthlyRequest) -> RawLlmResponse:
        ids = sorted(request.allowed_content_ids)

        def rows(section: str, label: str, content_ids: list[str]) -> list[dict]:
            return [
                {
                    "name": f"{label} {n}",
                    "description": f"{label} {n}을 설명해요.",
                    "content_ids": content_ids,
                    "parent_ref": None,
                }
                for n in range(1, request.counts[section] + 1)
            ]

        data = {
            "target_month": request.target_month,
            "theme": "주변을 살피며 놀아요",
            "rationale": "이번 달에는 주변에서 찾은 것을 이어 가는 놀이가 이어질 것 같습니다.",
            "together": rows("together", "함께 놀이", ids[:2]),
            "free_play": rows("free_play", "자유놀이", ids[2:3]),
            "safety": [
                {
                    "slot": s.slot,
                    "text": f"{s.label} 약속을 함께 알아보아요",
                    "refs": [s.allowed[0][0]],
                }
                for s in request.safety_slots
            ],
            "habits": [
                {
                    "week_id": w,
                    "entry_id": request.habit_entry_ids[i % len(request.habit_entry_ids)],
                }
                for i, w in enumerate(request.week_ids)
            ],
            "health_entry_id": min(request.health_entry_ids),
            "nutrition_entry_id": min(request.nutrition_entry_ids),
            "drills": [
                {"topic_id": t, "text": f"{n}번째 상황을 가정해 대피 훈련을 해요"}
                for n, t in enumerate(request.drill_topic_ids, 1)
            ],
        }
        return RawLlmResponse(json.dumps(data, ensure_ascii=False), "mock")


def play_monthly_provider():
    """mock 이면 위의 가짜, real 이면 `monthly_llm_provider()` 와 같은 Elice 어댑터다."""
    return MockPlayMonthlyProvider() if is_mock() else monthly_llm_provider()
