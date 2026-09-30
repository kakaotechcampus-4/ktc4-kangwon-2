"""연간 주제 문장을 만드는 것. mock 과 real 을 여기 한 곳에서 가른다.

**월간도 이 파일을 쓴다.** 각자 고르게 두면 한쪽만 real 로 바뀌는 사고가 난다 —
교사는 같은 계획안인데 연간은 AI 가 쓰고 월간은 가짜가 쓴 상태를 구분할 방법이 없다.

`p0-planning` 을 건드리지 않는다. 포트(`ThemeTextGenerator`)는 그쪽에 있고 구현은
여기 둔다 — 도메인이 어디서 문장을 얻는지 몰라야 공급자를 갈아끼울 수 있다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from ssuksak.planning.application.yearly_ports import ThemeTextRequest, ThemeTextResult

from app.config import settings

# 월간과 같은 모델을 쓴다. 층마다 다른 모델을 쓰면 같은 계획안 안에서 문체가 갈린다.
MODEL = "openai/gpt-4.1-mini"
TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = """너는 어린이집 교사의 연간보육계획안 작성을 돕는다.

주어진 달마다 **주제 문장 하나**를 쓴다. 규칙:

1. 반드시 참고자료의 주제(reference_label)를 벗어나지 않는다. 새 주제를 지어내지 않는다.
2. 한국어로 쓴다. 15자 이내의 명사구로 끝낸다.
3. 대상 연령(target_ages)이 알아들을 수 있는 말을 쓴다.
4. 활동·교구·날짜를 쓰지 않는다. 그건 월간계획안이 정한다.
5. 요청받은 달만 답한다. 빼거나 더하지 않는다.

반드시 아래 JSON 으로만 답한다.

{"themes": [{"theme_id": "<요청받은 그대로>", "value": "<주제 문장>"}]}"""


class ThemeTextUnavailable(RuntimeError):
    """설정이 없어 부를 수 없다. 재시도해도 같다 — 운영이 고쳐야 한다."""


class ThemeTextFailed(RuntimeError):
    """불렀는데 실패했거나 답이 계약을 어겼다. 재시도하면 될 수도 있다."""


class ThemeTextBudgetExceeded(RuntimeError):
    """예산·한도에 걸렸다. 키가 삭제됐을 수 있다 — 운영 문의."""


class EliceThemeTextGenerator:
    """엘리스 MLAPI 로 12개월 주제를 **한 번에** 받는다.

    달마다 따로 부르면 호출이 12배고, 그때마다 문체가 갈린다. 한 번에 보내면
    모델이 열두 달을 같이 보고 흐름을 맞춘다.
    """

    def __init__(self, base_url: str, api_key: str, *, transport=None) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ThemeTextUnavailable("ELICE_MLAPI_BASE_URL 은 https 주소여야 한다")
        if not api_key.strip():
            raise ThemeTextUnavailable("ELICE_MLAPI_API_KEY 가 없다")
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._post = transport or _post_json

    def generate(self, requests: tuple[ThemeTextRequest, ...]) -> tuple[ThemeTextResult, ...]:
        if not requests:
            return ()
        asked = {request.theme_id: request for request in requests}
        content = self._call(_user_content(requests))
        return tuple(_parse(content, asked))

    def _call(self, user_content: str) -> str:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            # 0 이어야 같은 입력에 같은 답이 온다. 계획안은 매번 달라지면 안 된다.
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        result = self._post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout=TIMEOUT_SECONDS,
        )
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ThemeTextFailed("응답에 choices[0].message.content 가 없다") from exc
        if not isinstance(content, str) or not content.strip():
            raise ThemeTextFailed("응답이 비었다")
        return content


def _user_content(requests: tuple[ThemeTextRequest, ...]) -> str:
    return json.dumps(
        {
            "months": [
                {
                    "theme_id": request.theme_id,
                    "reference_label": request.reference_label,
                    "month": request.period.calendar_month,
                    "target_ages": list(request.target_ages),
                }
                for request in requests
            ]
        },
        ensure_ascii=False,
    )


def _parse(content: str, asked: Mapping[str, ThemeTextRequest]) -> list[ThemeTextResult]:
    """**모델이 준 것을 그대로 믿지 않는다.**

    요청한 달이 빠지거나 없던 달이 끼면 거부한다. 조용히 채우면 교사는 열두 달이
    다 있는 줄 알고 확정한다 — 빈 달은 §7 확정에서야 드러난다.
    """
    try:
        parsed = json.loads(content)
        themes = parsed["themes"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ThemeTextFailed('응답이 {"themes": [...]} 형식이 아니다') from exc
    if not isinstance(themes, list):
        raise ThemeTextFailed("themes 는 배열이어야 한다")

    results: list[ThemeTextResult] = []
    seen: set[str] = set()
    for item in themes:
        if not isinstance(item, dict):
            raise ThemeTextFailed("themes 항목은 객체여야 한다")
        theme_id = item.get("theme_id")
        value = item.get("value")
        if theme_id not in asked:
            raise ThemeTextFailed(f"요청하지 않은 주제가 왔다: {theme_id!r}")
        if theme_id in seen:
            raise ThemeTextFailed(f"같은 주제가 두 번 왔다: {theme_id!r}")
        if not isinstance(value, str) or not value.strip():
            raise ThemeTextFailed(f"주제 문장이 비었다: {theme_id!r}")
        seen.add(theme_id)
        results.append(
            ThemeTextResult(period=asked[theme_id].period, theme_id=theme_id, value=value.strip())
        )
    missing = sorted(set(asked) - seen)
    if missing:
        raise ThemeTextFailed(f"빠진 달이 있다: {missing}")
    return results


def _post_json(url, *, headers, payload, timeout):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        # 401 은 키가 지워졌다는 뜻이고 429 는 한도다. 둘 다 재시도로 안 풀린다.
        if exc.code in (401, 403, 429):
            raise ThemeTextBudgetExceeded(f"엘리스가 {exc.code} 를 냈다") from exc
        raise ThemeTextFailed(f"엘리스가 {exc.code} 를 냈다") from exc
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ThemeTextFailed("엘리스 호출이 실패했다") from exc


def theme_text_generator():
    """설정을 보고 진짜와 가짜를 고른다.

    **기본이 mock 이다.** 키가 없는 채로 real 이 돌면 매번 401 을 받고, 원인을
    찾기까지 오래 걸린다. 반대로 mock 인 채 배포되면 교사가 받는 문장이
    참고자료 라벨 그대로지만 **근거가 흐려지지는 않는다** — 더 안전한 쪽이 기본이다.
    """
    if settings.llm_mode == "mock":
        from ssuksak.adapters.deterministic_theme_text_generator import (
            DeterministicThemeTextGenerator,
        )

        return DeterministicThemeTextGenerator()
    if not settings.elice_mlapi_base_url or not settings.elice_mlapi_api_key:
        raise ThemeTextUnavailable(
            "LLM_MODE=real 인데 ELICE_MLAPI_BASE_URL · ELICE_MLAPI_API_KEY 가 없다"
        )
    return EliceThemeTextGenerator(settings.elice_mlapi_base_url, settings.elice_mlapi_api_key)
