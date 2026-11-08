"""엘리스 MLAPI 를 부르는 곳. **backend 에서 LLM 으로 나가는 문은 여기 하나다.**

기능마다 따로 부르면 한쪽만 `real` 로 바뀌는 사고가 난다 — 교사는 같은 계획안인데
연간은 AI 가 쓰고 월간은 가짜가 쓴 상태를 구분할 방법이 없다.

`p0-planning` 은 자기 어댑터(`elice_openai_monthly.py`)를 따로 갖는다. 그쪽은
도메인 패키지라 backend 를 import 할 수 없어서다 — 설정(`ELICE_MLAPI_*`)과
모델 이름은 같은 것을 쓴다.
"""

from __future__ import annotations

import http.client
import json
import logging
import socket
import threading
import time
from collections.abc import Mapping
from contextlib import contextmanager
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from ssuksak import timing

from app.config import settings
from app.shared.llm.errors import LlmBudgetExceeded, LlmFailed, LlmUnavailable

# #100 이 만든 로거를 그대로 쓴다. 한 줄로 남기고 아동 정보는 찍지 않는다.
logger = logging.getLogger("app.server")
# 시간 줄(`llm_call` · `plan_timing`)은 자식 로거로 — `app.server` handler 로 같이 나가고,
# `llm_usage` 한 줄만 세는 테스트 · 스크립트와 섞이지 않는다.
timing_logger = logging.getLogger("app.server.timing")

# 층마다 다른 모델을 쓰면 같은 문서 안에서 문체가 갈린다. p0-planning 과 같은 값이다.
#
# **엘리스는 모델마다 주소가 다르다.** `ELICE_MLAPI_BASE_URL` 이 이 모델의 주소를
# 가리키고 있어야 한다 — 주소와 이름이 어긋나면 `model_not_found` 가 난다.
MODEL = "openai/gpt-6.1-sol"
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


def complete_json(
    system_prompt: str, user_content: str, *, transport=None, max_completion_tokens=None
) -> str:
    """JSON 으로만 답하게 하고 그 글자를 그대로 돌려준다. 파싱은 부르는 쪽이 한다.

    **온도를 보내지 않는다.** `gpt-6.1-sol` 는 기본값(1)만 받고 0 을 거부한다
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
            # 출력 상한. 안 주는 기존 호출은 모델 기본값 그대로다.
            **({"max_completion_tokens": max_completion_tokens} if max_completion_tokens else {}),
        },
        timeout=TIMEOUT_SECONDS,
    )
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmFailed("응답에 choices[0].message.content 가 없다") from exc
    if not isinstance(content, str) or not content.strip():
        raise LlmFailed("응답이 비었다")
    return content


# 판정 전용 모델(ADR-071). 글을 쓰지 않고 정해 둔 질문에 보기 · 확률로만 답한다.
# **버전을 고정한다** — `jev-latest` 는 새 버전이 나오면 같은 문장에 다른 판정을 낼 수 있다.
# 실측(판정 기준값)은 이 버전으로 했다. 올리면 다시 잰다.
JEV_MODEL = "typesafe/jev-1.14"
# 문장 6개(질문 40여 개)가 1초 안쪽이다. 화면이 기다리는 호출이라 생성보다 짧게 끊는다.
# 한 문서가 많아야 6번 부른다(judge.MAX_SENTENCES 36 / CHUNK 6) — 최악에도 1분 안에 끝난다.
JEV_TIMEOUT_SECONDS = 10.0


def require_jev_config() -> tuple[str, str]:
    base_url = settings.elice_jev_base_url or ""
    api_key = settings.elice_mlapi_api_key or ""
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise LlmUnavailable("ELICE_JEV_BASE_URL 이 없거나 https 주소가 아니다")
    if not api_key.strip():
        raise LlmUnavailable("ELICE_MLAPI_API_KEY 가 없다")
    return base_url, api_key


def decide(state: Mapping[str, object], questions: Mapping[str, object], *, transport=None) -> dict:
    """jev 에 판정을 묻고 `answers` 를 돌려준다. OpenAI 형식이 아니라 `/v1/decisions` 다.

    **가명으로 바꾼 글만 넘긴다.** 이름 처리는 부르는 쪽(shared/childCode)이 한다.
    """
    base_url, api_key = require_jev_config()
    post = transport or post_json
    result = post(
        f"{base_url.rstrip('/')}/v1/decisions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload={"model": JEV_MODEL, "state": dict(state), "questions": dict(questions)},
        timeout=JEV_TIMEOUT_SECONDS,
    )
    answers = result.get("answers") if isinstance(result, Mapping) else None
    if not isinstance(answers, Mapping):
        raise LlmFailed("응답에 answers 가 없다")
    return dict(answers)


def _log_usage(result: object, model: object) -> None:
    """성공한 호출에 쓴 토큰을 한 줄 남긴다.

    **숫자 네 개만 적는다.** 프롬프트에는 아동 이름이 들어갈 수 있어서 내용은 한 글자도
    찍지 않는다 (ADR-004). 로거와 「한 줄로 남긴다」 규칙은 #100 이 깔아 둔 것을 쓴다.

    **키가 팀 공용이라 이것 말고는 누가 얼마나 썼는지 볼 방법이 없다.** 엘리스 대시보드는
    팀 전체 합계만 준다 — 생성 한 번이 얼마인지, 파일럿 30건이 얼마인지 알 수 없다.
    합계는 `scripts/llm-usage.sh` 가 이 줄들을 긁어서 낸다.
    """
    usage = result.get("usage") if isinstance(result, Mapping) else None
    if not isinstance(usage, Mapping):
        # 모델이 usage 를 안 줄 수도 있다. 그것 때문에 생성을 실패시키지 않는다.
        return "-", "-"
    values = []
    invalid = False
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key not in usage:
            values.append("-")
            continue
        value = usage[key]
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            values.append(value)
        else:
            values.append("-")
            invalid = True
    if invalid:
        logger.warning("llm_usage: 잘못된 토큰 값을 '-' 로 남겼다 model=%s", model)
    logger.info(
        "llm_usage model=%s prompt=%s completion=%s total=%s",
        model,
        *values,
    )
    return values[0], values[1]


def _outcome(error: BaseException) -> str:
    if isinstance(error, LlmBudgetExceeded):
        return "budget"
    if "제한 시간" in str(error) or isinstance(error.__cause__, (TimeoutError, socket.timeout)):
        return "timeout"
    return "failed"


@contextmanager
def _llm_call(model: object):
    """호출 한 번의 시간을 `llm_call` 한 줄로 남긴다. **실패한 호출도 남긴다.**

    숫자와 이름만 적는다 — 내용은 없다. `run` 은 생성 요청 하나(`ssuksak.timing`)를 가리키고,
    `phase` 는 이 호출이 불린 구간이다(수리 호출이면 `repair`). 생성 요청 밖이면 `-` 다.
    """
    call = {"first_byte_ms": "-", "tokens": ("-", "-")}
    started = time.perf_counter()
    outcome = "ok"
    with timing.span("llm") as phase:
        run = timing.current()
        if run is not None:
            run.llm_calls += 1
        try:
            yield call
        except BaseException as error:
            outcome = _outcome(error)
            raise
        finally:
            timing_logger.info(
                "llm_call run=%s kind=%s phase=%s model=%s outcome=%s ms=%.0f first_byte_ms=%s "
                "prompt=%s completion=%s",
                run.id if run else "-",
                run.kind if run else "-",
                phase or "-",
                model,
                outcome,
                (time.perf_counter() - started) * 1000,
                call["first_byte_ms"],
                *call["tokens"],
            )


def post_json(
    url: str, *, headers: Mapping[str, str], payload: Mapping[str, object], timeout: float
):
    """엘리스에 JSON 을 보내고 JSON 을 받는다.

    오류 3종 분류와 사용량 기록은 여기 하나다 — 월간 Core 어댑터도 이 함수를 전송으로
    쓴다. 그래서 `llm_usage` 는 연간 · 문서 · 월간 모두 호출당 한 줄이고, 모델 이름은
    실제로 보낸 `payload["model"]` 을 적는다.

    **로컬에서 real 은 여기서 막는다** (AGENTS.md). 키가 팀 공유라 6명이 각자 로컬에서
    부르면 예산이 어디로 새는지 아무도 모르고, 초과하면 키가 지워진다. 서버와 주간
    작업만 `IS_SERVER` 를 들고 있다.

    **설정을 읽는 자리가 아니라 망을 타는 자리에 건다.** `require_config` 에 걸었더니
    가짜 transport 를 끼워 쓰는 테스트 47개가 같이 막혔다 — 그쪽은 망을 타지 않는다.
    월간 어댑터도 이 함수를 쓰므로 같은 가드에 걸린다.
    """
    if not settings.is_server:
        raise LlmUnavailable("로컬에서 real 모드 금지. 배포된 서버 엔드포인트를 호출한다")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(url, data=body, headers=dict(headers), method="POST")
    with _llm_call(payload.get("model")) as call:
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            # 401 은 키가 지워졌다는 뜻이고 429 는 한도다. 둘 다 재시도로 안 풀린다.
            if exc.code in (401, 403, 429):
                raise LlmBudgetExceeded(f"엘리스가 {exc.code} 를 냈다") from exc
            raise LlmFailed(f"엘리스가 {exc.code} 를 냈다") from exc
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LlmFailed("엘리스 호출이 실패했다") from exc
        call["tokens"] = _log_usage(result, payload.get("model"))
    return result


def post_stream(
    url: str,
    *,
    headers: Mapping[str, str],
    payload: Mapping[str, object],
    timeout: float,
    fold,
    deadline: float,
):
    """SSE 를 읽어 조립하고 성공한 호출의 토큰 사용량을 남긴다."""
    if not settings.is_server:
        raise LlmUnavailable("로컬에서 real 모드 금지. 배포된 서버 엔드포인트를 호출한다")
    with _llm_call(payload.get("model")) as call:
        return _post_stream(
            url,
            headers=headers,
            payload=payload,
            timeout=timeout,
            fold=fold,
            deadline=deadline,
            call=call,
        )


def _post_stream(url, *, headers, payload, timeout, fold, deadline, call):

    started = time.monotonic()
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    connection = None
    watchdog = None
    lines = []
    expired = threading.Event()
    try:
        connection = http.client.HTTPSConnection(
            parsed.hostname, parsed.port, timeout=min(timeout, deadline)
        )
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request("POST", path, body=body, headers=dict(headers))
        sock = connection.sock
        remaining = deadline - (time.monotonic() - started)
        if remaining <= 0:
            raise LlmFailed("엘리스 스트림 제한 시간이 지났다")

        def abort():
            expired.set()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        watchdog = threading.Timer(remaining, abort)
        watchdog.daemon = True
        watchdog.start()
        response = connection.getresponse()
        if response.status in (401, 403, 429):
            raise LlmBudgetExceeded(f"엘리스가 {response.status} 를 냈다")
        if not 200 <= response.status < 300:
            raise LlmFailed(f"엘리스가 {response.status} 를 냈다")
        while True:
            line = response.readline()
            if expired.is_set():
                raise LlmFailed("엘리스 스트림 제한 시간이 지났다")
            if not line:
                break
            if not lines:
                # 첫 줄이 올 때까지 — 모델이 쓰기 시작하기 전 기다린 시간이다.
                call["first_byte_ms"] = f"{(time.monotonic() - started) * 1000:.0f}"
            lines.append(line.decode("utf-8").rstrip("\r\n"))
    except (
        http.client.HTTPException,
        UnicodeDecodeError,
        TimeoutError,
        OSError,
    ) as exc:
        if expired.is_set():
            raise LlmFailed("엘리스 스트림 제한 시간이 지났다") from exc
        raise LlmFailed("엘리스 스트림 호출이 실패했다") from exc
    finally:
        if watchdog is not None:
            watchdog.cancel()
            watchdog.join()
        if connection is not None:
            connection.close()

    result = fold(lines)
    call["tokens"] = _log_usage(result, payload.get("model"))
    if not isinstance(result.get("usage"), Mapping):
        logger.warning("llm stream finished without usage model=%s", payload.get("model"))
    return result
