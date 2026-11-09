"""`post_json` 은 일시 오류에서 **한 번만** 더 부르고, 생성 요청 하나의 호출 수엔 상한이 있다.

ADR-076. 진짜 엘리스는 부르지 않는다. `urlopen` 과 `time.sleep` 만 갈아끼운다 — 실제로 자지 않는다.
"""

import email.message
import io
import json
from urllib import error as urllib_error

import pytest
from ssuksak import timing

from app.shared.llm import LlmBudgetExceeded, LlmFailed
from app.shared.llm import client as llm

OK = {"choices": [{"message": {"content": "{}"}}]}
BODY = json.dumps(OK).encode()


@pytest.fixture
def sleeps(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://mlapi.example.com/v1")
    monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-secret")
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "is_server", True)
    slept = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    return slept


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


def http_error(code, retry_after=None, body=b""):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib_error.HTTPError("u", code, "msg", headers, io.BytesIO(body))


def post():
    return llm.post_json("https://x", headers={}, payload={"model": "m"}, timeout=1)


def in_run(body):
    """생성 요청 하나(`timing` 실행)를 열고 안에서 `body(run)` 을 부른다."""
    box = {}

    @timing.timed("annual_theme", lambda line: None)
    def handler():
        run = box["run"] = timing.current()
        try:
            box["result"] = body(run)
        except (LlmFailed, LlmBudgetExceeded) as error:
            box["error"] = error

    handler()
    return box


def test_연결이_끊기면_1초_뒤_한_번_더_부른다(monkeypatch, sleeps):
    net = Net(monkeypatch, urllib_error.URLError("refused"), BODY)

    assert post() == OK
    assert net.calls == 2
    assert sleeps == [1.0]


def test_읽다가_시간이_지나도_한_번_더_부른다(monkeypatch, sleeps):
    net = Net(monkeypatch, TimeoutError("read timed out"), BODY)

    assert post() == OK
    assert net.calls == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize("code", [502, 503, 504])
def test_게이트웨이_오류는_한_번_더_부르고_풀리면_성공한다(monkeypatch, sleeps, code):
    net = Net(monkeypatch, http_error(code), BODY)

    assert post() == OK
    assert net.calls == 2
    assert sleeps == [1.0]


def test_503_이_두_번_나오면_실패하고_더_부르지_않는다(monkeypatch, sleeps):
    net = Net(monkeypatch, http_error(503), http_error(503))

    with pytest.raises(LlmFailed, match="503"):
        post()
    assert net.calls == 2


def test_연결이_두_번_끊기면_실패한다(monkeypatch, sleeps):
    net = Net(monkeypatch, urllib_error.URLError("a"), urllib_error.URLError("b"))

    with pytest.raises(LlmFailed, match="엘리스 호출이 실패했다"):
        post()
    assert net.calls == 2


def test_429_는_한_번_더_부르고_풀리면_성공한다(monkeypatch, sleeps):
    net = Net(monkeypatch, http_error(429), BODY)

    assert post() == OK
    assert net.calls == 2
    assert sleeps == [1.0]


def test_429_가_두_번_나오면_예산_오류로_분류한다(monkeypatch, sleeps):
    net = Net(monkeypatch, http_error(429), http_error(429))

    with pytest.raises(LlmBudgetExceeded, match="429"):
        post()
    assert net.calls == 2


def test_한도_소진_본문이면_429_도_다시_부르지_않는다(monkeypatch, sleeps):
    net = Net(monkeypatch, http_error(429, body=b'{"error": {"code": "insufficient_quota"}}'))

    with pytest.raises(LlmBudgetExceeded):
        post()
    assert net.calls == 1
    assert sleeps == []


def test_긴_message_뒤에_온_한도_소진_표시도_찾는다(monkeypatch, sleeps):
    body = json.dumps(
        {"error": {"message": "가" * 3000, "code": "insufficient_quota"}}, ensure_ascii=False
    ).encode()
    assert body.index(b"insufficient_quota") > 4096
    net = Net(monkeypatch, http_error(429, body=body))

    with pytest.raises(LlmBudgetExceeded):
        post()
    assert net.calls == 1


def test_Retry_After_가_5초를_넘으면_다시_부르지_않는다(monkeypatch, sleeps):
    net = Net(monkeypatch, http_error(429, retry_after="30"))

    with pytest.raises(LlmBudgetExceeded):
        post()
    assert net.calls == 1
    assert sleeps == []


def test_Retry_After_가_5초_이하면_그_값만큼_기다린다(monkeypatch, sleeps):
    net = Net(monkeypatch, http_error(429, retry_after="2"), BODY)

    assert post() == OK
    assert net.calls == 2
    assert sleeps == [2.0]


def test_날짜_모양_Retry_After_는_읽지_않고_기본_1초다(monkeypatch, sleeps):
    Net(monkeypatch, http_error(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT"), BODY)

    assert post() == OK
    assert sleeps == [1.0]


def test_429_가_아니면_Retry_After_를_보지_않는다(monkeypatch, sleeps):
    Net(monkeypatch, http_error(503, retry_after="2"), BODY)

    assert post() == OK
    assert sleeps == [1.0]


@pytest.mark.parametrize(
    ("step", "error", "match"),
    [
        (http_error(401), LlmBudgetExceeded, "401"),
        (http_error(403), LlmBudgetExceeded, "403"),
        (http_error(400), LlmFailed, "400"),
        (http_error(404), LlmFailed, "404"),
        (http_error(500), LlmFailed, "500"),
        (http_error(501), LlmFailed, "501"),
        (b"{not json", LlmFailed, "엘리스 호출이 실패했다"),
    ],
)
def test_다시_불러도_같은_오류는_한_번만_부른다(monkeypatch, sleeps, step, error, match):
    net = Net(monkeypatch, step)

    with pytest.raises(error, match=match):
        post()
    assert net.calls == 1
    assert sleeps == []


def test_시도마다_llm_call_줄과_호출_수를_남긴다(monkeypatch, sleeps):
    """실패한 시도와 성공한 시도가 따로 센다. `llm_usage` 는 성공한 한 번뿐이다."""
    timing_lines, usage_lines = [], []
    monkeypatch.setattr(
        llm.timing_logger, "info", lambda fmt, *args: timing_lines.append(fmt % args)
    )
    monkeypatch.setattr(llm.logger, "info", lambda fmt, *args: usage_lines.append(fmt % args))
    usage = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    Net(monkeypatch, urllib_error.URLError("refused"), json.dumps({**OK, "usage": usage}).encode())

    box = in_run(lambda run: post())

    assert box["result"] == {**OK, "usage": usage}
    assert box["run"].llm_calls == 2
    outcomes = [dict(p.split("=", 1) for p in line.split()[1:])["outcome"] for line in timing_lines]
    assert outcomes == ["failed", "ok"]
    assert sum(line.startswith("llm_usage") for line in usage_lines) == 1


def test_재시도_사이에_기다리는_시간은_llm_구간에_들지_않는다(monkeypatch, sleeps):
    phases = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: phases.append(timing.current().phase))
    Net(monkeypatch, urllib_error.URLError("refused"), BODY)

    in_run(lambda run: post())

    assert phases == ["db_read"]


def test_호출_수가_상한에_닿았으면_부르지_않고_멈춘다(monkeypatch, sleeps):
    net = Net(monkeypatch, BODY)

    def body(run):
        run.llm_calls = llm.MAX_LLM_CALLS_PER_RUN
        return post()

    box = in_run(body)

    assert isinstance(box["error"], LlmFailed)
    assert str(box["error"]) == "생성 요청 하나의 LLM 호출 상한(6회)을 넘었다"
    assert net.calls == 0
    assert box["run"].llm_calls == 6  # 막힌 시도는 세지 않는다


def test_상한_하나_앞이면_호출이_나간다(monkeypatch, sleeps):
    net = Net(monkeypatch, BODY)

    def body(run):
        run.llm_calls = llm.MAX_LLM_CALLS_PER_RUN - 1
        return post()

    box = in_run(body)

    assert box["result"] == OK
    assert net.calls == 1
    assert box["run"].llm_calls == 6


def test_재시도도_상한에_센다(monkeypatch, sleeps):
    net = Net(monkeypatch, http_error(503))

    def body(run):
        run.llm_calls = llm.MAX_LLM_CALLS_PER_RUN - 1
        return post()

    box = in_run(body)

    assert isinstance(box["error"], LlmFailed) and "상한" in str(box["error"])
    assert net.calls == 1


def test_스트림_호출에도_상한이_걸린다(monkeypatch, sleeps):
    monkeypatch.setattr(
        llm.http.client,
        "HTTPSConnection",
        lambda *a, **k: pytest.fail("상한을 넘었는데 연결했다"),
    )

    def body(run):
        run.llm_calls = llm.MAX_LLM_CALLS_PER_RUN
        return llm.post_stream(
            "https://x/v1/chat/completions",
            headers={},
            payload={"model": "m"},
            timeout=1,
            fold=list,
            deadline=1,
        )

    assert isinstance(in_run(body)["error"], LlmFailed)


def test_생성_요청_밖에서는_상한이_없다(monkeypatch, sleeps):
    """문서 초안 · jev 검증은 센 실행이 없다."""
    net = Net(monkeypatch, *[BODY] * (llm.MAX_LLM_CALLS_PER_RUN + 2))

    for _ in range(llm.MAX_LLM_CALLS_PER_RUN + 2):
        assert post() == OK
    assert net.calls == llm.MAX_LLM_CALLS_PER_RUN + 2
