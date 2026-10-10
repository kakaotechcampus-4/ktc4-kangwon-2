"""엘리스 MLAPI 를 부르는 곳. **backend 에서 LLM 으로 나가는 문은 여기 하나다.**

기능마다 따로 부르면 한쪽만 `real` 로 바뀌는 사고가 난다 — 교사는 같은 계획안인데
연간은 AI 가 쓰고 월간은 가짜가 쓴 상태를 구분할 방법이 없다.

`p0-planning` 은 자기 어댑터(`elice_openai_monthly.py`)를 따로 갖는다. 그쪽은
도메인 패키지라 backend 를 import 할 수 없어서다 — 설정(`ELICE_MLAPI_*`)과
모델 이름은 같은 것을 쓴다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from app.config import settings
from app.shared.llm.errors import LlmBudgetExceeded, LlmFailed, LlmUnavailable

# #100 이 만든 로거를 그대로 쓴다. 한 줄로 남기고 아동 정보는 찍지 않는다.
logger = logging.getLogger("app.server")

# 층마다 다른 모델을 쓰면 같은 문서 안에서 문체가 갈린다. p0-planning 과 같은 값이다.
#
# **엘리스는 모델마다 주소가 다르다.** `ELICE_MLAPI_BASE_URL` 이 이 모델의 주소를
# 가리키고 있어야 한다 — 주소와 이름이 어긋나면 `model_not_found` 가 난다.
MODEL = "openai/gpt-6-luna"
TIMEOUT_SECONDS = 30.0


def is_mock() -> bool:
    """**기본이 mock 이다.** 키가 없는 채로 real 이 돌면 매번 401 을 받고 원인을 못 찾는다."""
    return settings.llm_mode == "mock"


def require_config() -> tuple[str, str]:
    """`real` 인데 설정이 없으면 부르기 전에 멈춘다."""
    base_url = settings.elice_mlapi_base_url or ""
    api_key = settings.elice_mlapi_api_key or ""
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise LlmUnavailable("ELICE_MLAPI_BASE_URL 이 없거나 https 주소가 아니다")
    if not api_key.strip():
        raise LlmUnavailable("ELICE_MLAPI_API_KEY 가 없다")
    return base_url, api_key


def complete_json(system_prompt: str, user_content: str, *, transport=None) -> str:
    """JSON 으로만 답하게 하고 그 글자를 그대로 돌려준다. 파싱은 부르는 쪽이 한다.

    **온도를 보내지 않는다.** `gpt-6-luna` 는 기본값(1)만 받고 0 을 거부한다
    (`Unsupported value: 'temperature' does not support 0 with this model`).
    그래서 같은 입력에 같은 답이 온다고 가정하면 안 된다.

    교사가 겪는 일은 거의 없다 — 연간은 반당 하나라 다시 만들 수 없고(§4),
    만든 뒤에는 `body` JSONB 에 그대로 남는다. 달라지는 것은 **새로 만들 때뿐**이다.

    **`system_prompt` 나 `user_content` 에 「JSON」이라는 낱말이 있어야 한다.**
    `response_format: json_object` 는 그 낱말이 없으면 400 으로 거부한다.
    """
    base_url, api_key = require_config()
    post = transport or post_json
    result = post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=TIMEOUT_SECONDS,
    )
    _log_usage(result)
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmFailed("응답에 choices[0].message.content 가 없다") from exc
    if not isinstance(content, str) or not content.strip():
        raise LlmFailed("응답이 비었다")
    return content


def _log_usage(result: object) -> None:
    """이번 호출에 쓴 토큰을 한 줄 남긴다.

    **숫자 네 개만 적는다.** 프롬프트에는 아동 이름이 들어갈 수 있어서 내용은 한 글자도
    찍지 않는다 (ADR-004). 로거와 「한 줄로 남긴다」 규칙은 #100 이 깔아 둔 것을 쓴다.

    **키가 팀 공용이라 이것 말고는 누가 얼마나 썼는지 볼 방법이 없다.** 엘리스 대시보드는
    팀 전체 합계만 준다 — 생성 한 번이 얼마인지, 파일럿 30건이 얼마인지 알 수 없다.
    합계는 `scripts/llm-usage.sh` 가 이 줄들을 긁어서 낸다.
    """
    usage = result.get("usage") if isinstance(result, Mapping) else None
    if not isinstance(usage, Mapping):
        # 모델이 usage 를 안 줄 수도 있다. 그것 때문에 생성을 실패시키지 않는다.
        return
    logger.info(
        "llm_usage model=%s prompt=%s completion=%s total=%s",
        MODEL,
        usage.get("prompt_tokens", "-"),
        usage.get("completion_tokens", "-"),
        usage.get("total_tokens", "-"),
    )


def post_json(
    url: str, *, headers: Mapping[str, str], payload: Mapping[str, object], timeout: float
):
    """엘리스에 JSON 을 보내고 JSON 을 받는다.

    오류 3종 분류는 여기 하나다 — 월간 Core 어댑터도 이 함수를 전송으로 쓴다.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        # 401 은 키가 지워졌다는 뜻이고 429 는 한도다. 둘 다 재시도로 안 풀린다.
        if exc.code in (401, 403, 429):
            raise LlmBudgetExceeded(f"엘리스가 {exc.code} 를 냈다") from exc
        raise LlmFailed(f"엘리스가 {exc.code} 를 냈다") from exc
    except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LlmFailed("엘리스 호출이 실패했다") from exc
