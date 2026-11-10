"""생성 요청 하나가 부를 수 있는 LLM 횟수엔 상한이 있다 — 재시도도 센다(ADR-081).

진짜 엘리스는 부르지 않는다. `urlopen` · `HTTPSConnection` · `time.sleep` 만 갈아끼운다.
"""

import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib import error as urllib_error

import pytest
from ssuksak import timing
from ssuksak.planning import YearlyApplicationError
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError

from app.features.plans import monthly_router, play_monthly_router, weekly_router
from app.features.plans import router as plans_router
from app.shared.llm import LlmCallCapExceeded, LlmFailed
from app.shared.llm import client as llm

BODY = json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()


@pytest.fixture(autouse=True)
def server(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "is_server", True)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)


class Net:
    """`urlopen` 대역. 차례대로 예외를 던지거나 본문을 돌려주고 부른 횟수를 센다."""

    def __init__(self, monkeypatch, *steps):
        self.steps = list(steps)
        self.calls = 0
        self._lock = threading.Lock()  # 스레드 여럿이 부르는 테스트가 있다
        monkeypatch.setattr(llm.urllib_request, "urlopen", self)

    def __call__(self, *args, **kwargs):
        with self._lock:
            self.calls += 1
            step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return io.BytesIO(step)


def post():
    return llm.post_json("https://x", headers={}, payload={"model": "m"}, timeout=1)


def in_run(used, call):
    """생성 요청 하나(`timing` 실행)를 열고 이미 `used` 번 부른 것으로 둔 뒤 `call()` 을 부른다."""
    box = {}

    @timing.timed("annual_play", lambda line: None)
    def handler():
        box["run"] = run = timing.current()
        run.llm_calls = used
        try:
            box["result"] = call()
        except LlmCallCapExceeded as error:
            box["error"] = error

    handler()
    return box


def test_상한에_닿으면_부르지_않고_실패한다(monkeypatch):
    net = Net(monkeypatch, BODY)

    box = in_run(llm.MAX_LLM_CALLS_PER_RUN, post)

    assert "상한" in str(box["error"])
    assert net.calls == 0
    assert box["run"].llm_calls == llm.MAX_LLM_CALLS_PER_RUN


def test_상한_바로_아래면_부른다(monkeypatch):
    net = Net(monkeypatch, BODY)

    box = in_run(llm.MAX_LLM_CALLS_PER_RUN - 1, post)

    assert "error" not in box
    assert net.calls == 1
    assert box["run"].llm_calls == llm.MAX_LLM_CALLS_PER_RUN


def test_재시도도_상한에_센다(monkeypatch):
    """모델에 닿지 못해 다시 보내려는데 상한이면 두 번째는 안 나간다."""
    net = Net(monkeypatch, urllib_error.URLError(ConnectionRefusedError()), BODY)

    box = in_run(llm.MAX_LLM_CALLS_PER_RUN - 1, post)

    assert "상한" in str(box["error"])
    assert net.calls == 1
    assert box["run"].llm_calls == llm.MAX_LLM_CALLS_PER_RUN


def test_스트림에도_상한이_걸린다(monkeypatch):
    monkeypatch.setattr(
        llm.http.client,
        "HTTPSConnection",
        lambda *a, **k: pytest.fail("상한을 넘었는데 연결했다"),
    )

    def stream():
        return llm.post_stream(
            "https://x/v1/chat/completions",
            headers={},
            payload={"model": "m"},
            timeout=1,
            fold=list,
            deadline=1,
        )

    assert "상한" in str(in_run(llm.MAX_LLM_CALLS_PER_RUN, stream)["error"])


def test_생성_요청_밖에서는_상한이_없다(monkeypatch):
    """문서 초안 · 칸 재생성 · jev 판정은 센 실행이 없다."""
    count = llm.MAX_LLM_CALLS_PER_RUN + 2
    net = Net(monkeypatch, *[BODY] * count)

    for _ in range(count):
        post()
    assert net.calls == count


def test_상한은_스레드로_나뉜_작업을_합쳐서_센다(monkeypatch):
    """놀이형 연간처럼 `in_thread` 로 연 스레드도 요청 하나의 횟수에 쌓인다."""
    net = Net(monkeypatch, *[BODY] * 4)
    threads = 4
    start = threading.Barrier(threads)

    def worker():
        start.wait(5)
        try:
            post()
        except LlmCallCapExceeded as error:
            return error
        return None

    def fan_out():
        with ThreadPoolExecutor(threads) as pool:
            jobs = [pool.submit(timing.in_thread(worker)) for _ in range(threads)]
            return [job.result() for job in jobs]

    box = in_run(llm.MAX_LLM_CALLS_PER_RUN - 2, fan_out)

    results = box["result"]
    assert sum(error is None for error in results) == 2
    assert sum(isinstance(error, LlmCallCapExceeded) for error in results) == 2
    assert net.calls == 2  # 막힌 둘은 망에 나가지 않았다
    assert box["run"].llm_calls == llm.MAX_LLM_CALLS_PER_RUN


def test_상한에_걸리면_내용_없는_한_줄을_남기고_llm_call_줄은_남기지_않는다(monkeypatch):
    Net(monkeypatch, BODY)
    # app.main 이 불린 뒤엔 `app.server` 가 propagate 하지 않아 caplog 가 못 본다 — 로거를 갈아낀다.
    lines = []
    for level in ("info", "warning"):
        monkeypatch.setattr(llm.timing_logger, level, lambda fmt, *args: lines.append(fmt % args))

    box = in_run(llm.MAX_LLM_CALLS_PER_RUN, post)

    assert lines == [
        f"llm_cap_hit run={box['run'].id} kind=annual_play "
        f"used={llm.MAX_LLM_CALLS_PER_RUN} limit={llm.MAX_LLM_CALLS_PER_RUN}"
    ]


def test_상한_오류는_다시_보내지_않는다():
    calls = []

    def send():
        calls.append(1)
        raise LlmCallCapExceeded("상한")

    with pytest.raises(LlmCallCapExceeded):
        llm._once_more(send)
    assert calls == [1]
    assert not issubclass(LlmCallCapExceeded, llm._NotDelivered)


def _wrapped(error_type, cause):
    """Core 가 provider 오류를 자기 것으로 감싼 모양 — 원인은 `__cause__` 에 있다."""
    error = error_type("theme_text_generation_failed", "wrapped")
    error.__cause__ = cause
    return error


def test_상한_오류는_LlmFailed_와_같은_계약_코드로_간다():
    """생성 라우터는 `isinstance` 로 거른다 — 하위 클래스도 `GENERATION_FAILED`(500) 로 같다."""
    mappers = (
        # 놀이형 연간 · 놀이 월간은 원인 사슬을, 나머지는 Core 가 감싼 오류의 `__cause__` 를 본다.
        lambda cause: plans_router._play_project_generation_error(cause),
        lambda cause: plans_router._generation_error(_wrapped(YearlyApplicationError, cause)),
        lambda cause: monthly_router._generation_error(_wrapped(MonthlyApplicationError, cause)),
        lambda cause: weekly_router._generation_error(_wrapped(MonthlyApplicationError, cause)),
        lambda cause: play_monthly_router._generation_error(cause),
    )
    for map_error in mappers:
        capped, plain = map_error(LlmCallCapExceeded("상한")), map_error(LlmFailed("실패"))
        assert capped.status_code == plain.status_code == 500
        assert capped.detail == plain.detail
        assert capped.detail["code"] == "GENERATION_FAILED"
