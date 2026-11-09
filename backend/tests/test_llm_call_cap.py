"""생성 요청 하나가 부를 수 있는 LLM 횟수엔 상한이 있다 — 재시도도 센다(ADR-081).

진짜 엘리스는 부르지 않는다. `urlopen` · `HTTPSConnection` · `time.sleep` 만 갈아끼운다.
"""

import io
import json
from urllib import error as urllib_error

import pytest
from ssuksak import timing

from app.shared.llm import LlmFailed
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
        monkeypatch.setattr(llm.urllib_request, "urlopen", self)

    def __call__(self, *args, **kwargs):
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
        except LlmFailed as error:
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
