"""생성 기록 — 전송 재시도 · 연간 소주제 수리의 시도 기록(`attempts`, ADR-096).

원래 시험(`test_llm_usage_log.py` · `test_llm_stream.py` · `test_annual_content.py`)의 장면을
생성 요청(`timing` 실행) 안에서 다시 돌려 무엇이 적히는지 본다. 생성 동작(예외 · 부른 수)은
원래 시험이 지킨다. 놀이 연간의 구간 다시 부르기는 `test_generation_runs_play_annual.py`,
월간 · 주간 · 놀이 월간의 수리는 세계가 있는 `test_generation_runs_{monthly,weekly}.py` 가 본다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import json
from types import SimpleNamespace
from urllib import error as urllib_error

import pytest
from ssuksak import timing
from ssuksak.planning.domain.year_month import YearMonth
from test_generation_runs import assert_attempts_shape
from test_llm_stream import _connection, _post_stream, _sse
from test_llm_usage_log import OK, _replies, usage_lines  # noqa: F401

from app.features.plans import annual_content
from app.shared.llm import LlmFailed
from app.shared.llm import client as llm

MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)
TRANSPORT_OK = {"kind": "transport", "phase": "db_read", "result": "ok"}


def _in_run(fn):
    """생성 요청 하나(`timing` 실행 하나) 안에서 `fn` 을 돌리고 실행 · 결과 · 예외를 돌려준다."""
    box = {}

    @timing.timed("weekly", lambda line: None)
    def handler():
        box["run"] = timing.current()
        try:
            box["result"] = fn()
        except Exception as error:
            box["error"] = error

    handler()
    return box


def _post_json():
    return llm.post_json("https://x", headers={}, payload={"model": "m"}, timeout=1)


# ── 전송 재시도 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "first",
    [
        urllib_error.HTTPError("u", 503, "busy", {}, None),
        urllib_error.URLError(ConnectionRefusedError()),
    ],
)
def test_다시_보내서_닿으면_전송_시도_하나가_ok_로_남는다(monkeypatch, usage_lines, first):
    calls = _replies(monkeypatch, first, OK)

    box = _in_run(_post_json)

    assert box["result"] == OK and len(calls) == 2
    assert box["run"].attempts == [TRANSPORT_OK]
    assert_attempts_shape(box["run"].attempts)
    assert box["run"].llm_calls == 2  # 시도 기록은 상한 셈을 바꾸지 않는다


def test_다시_보낸_것도_닿지_못하면_예외_이름이_남고_같은_실패가_난다(monkeypatch, usage_lines):
    refused = urllib_error.URLError(ConnectionRefusedError())
    calls = _replies(monkeypatch, refused, refused, OK)

    box = _in_run(_post_json)

    assert isinstance(box["error"], llm._NotDelivered) and len(calls) == 2
    assert box["run"].attempts == [{**TRANSPORT_OK, "result": "_NotDelivered"}]
    assert_attempts_shape(box["run"].attempts)


@pytest.mark.parametrize(
    "first",
    [
        None,  # 첫 시도에 닿았다
        urllib_error.HTTPError("u", 429, "limit", {}, None),
        urllib_error.HTTPError("u", 500, "boom", {}, None),
        urllib_error.URLError(TimeoutError()),
    ],
)
def test_다시_보내지_않았으면_전송_시도는_없다(monkeypatch, usage_lines, first):
    _replies(monkeypatch, first or OK, OK)

    box = _in_run(_post_json)

    assert box["run"].attempts == []


def test_실행_밖에서_다시_보내도_아무것도_적지_않고_결과는_같다(monkeypatch, usage_lines):
    calls = _replies(monkeypatch, urllib_error.HTTPError("u", 503, "busy", {}, None), OK)

    assert _post_json() == OK and len(calls) == 2


def test_스트림_503_을_다시_보내도_전송_시도_하나가_남는다(monkeypatch, usage_lines):
    monkeypatch.setattr(llm, "RETRY_DELAY_SECONDS", 0)
    statuses = iter((503, 200))
    connections = _connection(monkeypatch, [*_sse("{}"), b"data: [DONE]\n\n"])
    fake = llm.http.client.HTTPSConnection
    real_init = fake.__init__

    def init(self, host, port, timeout):
        real_init(self, host, port, timeout)
        self.response.status = next(statuses)

    monkeypatch.setattr(fake, "__init__", init)

    box = _in_run(_post_stream)

    assert box["result"]["lines"] and len(connections) == 2
    assert box["run"].attempts == [TRANSPORT_OK]


# ── 연간 소주제 수리 ───────────────────────────────────────────────────────


def _plan():
    return SimpleNamespace(
        target_ages=frozenset({3}),
        periods=tuple(
            SimpleNamespace(
                period=YearMonth(2026 if m >= 3 else 2027, m),
                theme=SimpleNamespace(value="월별 주제"),
            )
            for m in MONTHS
        ),
    )


def _items(payload, wrong=()):
    return [
        {
            "month": m["month"],
            "sub_themes": [f"경험 {i}" for i in range(m["week_count"] - (m["month"] in wrong))],
        }
        for m in payload["months"]
    ]


def _subthemes(monkeypatch, second):
    """첫 답은 9 · 10월 개수가 틀리고, 수리 호출(두 번째)은 `second(payload)` 가 낸다."""
    calls = []

    def complete(system, user, **kwargs):
        payload = json.loads(user)
        calls.append(payload)
        if len(calls) == 1:
            return json.dumps({"months": _items(payload, wrong=(9, 10))}, ensure_ascii=False)
        return second(payload)

    monkeypatch.setattr(annual_content, "is_mock", lambda: False)
    monkeypatch.setattr(annual_content, "complete_json", complete)
    return calls


def test_개수를_고치는_수리_호출은_수리_구간의_시도_하나로_남는다(monkeypatch):
    calls = _subthemes(monkeypatch, lambda p: json.dumps({"months": _items(p)}, ensure_ascii=False))

    box = _in_run(lambda: annual_content.generate_subthemes_with_memo(_plan(), ""))

    assert "error" not in box and len(calls) == 2
    assert box["run"].attempts == [{"kind": "repair", "phase": "repair", "result": "ok"}]
    assert_attempts_shape(box["run"].attempts)


@pytest.mark.parametrize("fault", ["count", "extra_month", "venue"])
def test_수리_답이_나빠도_수리_호출은_ok_고_원래_예외가_그대로_난다(monkeypatch, fault):
    """`repair.result` 는 호출 결과다 — 수리한 답이 검사를 통과했는지는 실행의 끝으로 본다."""

    def bad(payload):
        items = _items(payload, wrong=(9,) if fault == "count" else ())
        if fault == "extra_month":
            items.append({"month": 2, "sub_themes": ["다른 달", "추가 값"]})
        elif fault == "venue":
            items[0]["sub_themes"][0] = "배산유아숲터 숲 체험"
        return json.dumps({"months": items}, ensure_ascii=False)

    calls = _subthemes(monkeypatch, bad)

    box = _in_run(lambda: annual_content.generate_subthemes_with_memo(_plan(), ""))

    assert isinstance(box["error"], LlmFailed) and len(calls) == 2  # 세 번째 호출은 없다
    assert box["run"].attempts == [{"kind": "repair", "phase": "repair", "result": "ok"}]


def test_수리_호출이_실패하면_그_예외_이름이_남고_같은_예외가_난다(monkeypatch):
    failure = LlmFailed("엘리스가 502 를 냈다")

    def broken(payload):
        raise failure

    _subthemes(monkeypatch, broken)

    box = _in_run(lambda: annual_content.generate_subthemes_with_memo(_plan(), ""))

    assert box["error"] is failure
    assert box["run"].attempts == [{"kind": "repair", "phase": "repair", "result": "LlmFailed"}]
    assert "엘리스가" not in str(box["run"].attempts)  # 메시지는 적지 않는다
