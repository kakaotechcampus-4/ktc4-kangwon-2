"""부하 측정 스크립트(scripts/load_check.py)의 순수 함수 — 서버도 LLM 도 부르지 않는다."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "load_check.py"
_spec = importlib.util.spec_from_file_location("load_check", _PATH)
lc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lc)

DOCKER_LINE = (
    "backend-1  | 2026-11-10T11:35:41.250000000Z 2026-11-10 11:35:41,249 INFO app.server.timing "
    "llm_call run=ab12cd34 kind=annual_theme phase=prompt model=openai/gpt-6.1-sol "
    "outcome=ok ms=9000 first_byte_ms=- prompt=11140 completion=1011"
)


def test_결과_분류_열쇠():
    assert lc.classify({"status": 201}) == (201, "", "")
    err = {"status": 500, "code": "INTERNAL_ERROR", "message": "일시적인 문제"}
    assert lc.classify(err) == (500, "INTERNAL_ERROR", "일시적인 문제")
    assert (
        lc.classify({"status": None, "timeout": True, "exc": "ReadTimeout"})[0] == "CLIENT_TIMEOUT"
    )
    assert lc.classify({"status": None, "exc": "ConnectError"}) == (
        "CONN_ERROR",
        "ConnectError",
        "",
    )


def test_백분위():
    assert lc.percentile([], 50) is None
    assert lc.percentile([7], 95) == 7
    assert lc.percentile([5, 1, 3, 2, 4], 50) == 3
    assert lc.percentile([1, 2, 3, 4, 5], 95) == pytest.approx(4.8)


def test_LLM_시작_시각은_찍힌_시각에서_걸린_시간을_뺀다():
    ev = lc.parse_log_line(DOCKER_LINE)
    assert ev["kind"] == "llm_call" and ev["kv"]["outcome"] == "ok"
    assert ev["ts"] == datetime(2026, 11, 10, 11, 35, 41, 250000, tzinfo=UTC)
    start = lc.llm_start_time(ev["ts"], float(ev["kv"]["ms"]))
    assert start == datetime(2026, 11, 10, 11, 35, 32, 250000, tzinfo=UTC)


def test_docker_시각이_없으면_앱_시각을_쓰고_관심없는_줄은_버린다():
    line = "2026-11-10 11:35:41,249 INFO app.server plan_timing run=a kind=annual_theme total_ms=12"
    assert lc.parse_log_line(line)["ts"] == datetime(2026, 11, 10, 11, 35, 41, 249000, tzinfo=UTC)
    assert lc.parse_log_line("INFO:     Application startup complete.") is None


def test_원화_계산과_시간초과는_최대_단가로_센다():
    assert lc.cost_won(1000, 1000) == pytest.approx(2.835 + 14.175)

    def event(kind, **kv):
        return {"kind": kind, "kv": kv, "rnd": {"scenario": "s2"}}

    sp = lc.spend(
        [
            event("llm_usage", prompt="1000", completion="1000"),
            event("llm_usage", prompt="2000", completion="1000"),
            event("llm_usage", prompt="-", completion="-"),  # 숫자가 아니면 세지 않는다
            event("llm_call", outcome="timeout"),
        ]
    )
    biggest = lc.cost_won(2000, 1000)
    assert sp["calls"] == 2
    assert sp["timeout_won"] == pytest.approx(biggest)
    assert sp["per_max"] == {"s2": pytest.approx(biggest)}


def test_부하_대상_호스트_가드():
    for ok in ("http://backend:8000", "http://localhost:8000", "http://127.0.0.1:8000"):
        lc.check_base(ok, False)
    with pytest.raises(SystemExit):
        lc.check_base("http://10.0.0.5:8000", False)
    lc.check_base("http://10.0.0.5:8000", True)
    for prod in ("https://ssample.duckdns.org", "http://ssample.duckdns.org:80"):
        with pytest.raises(SystemExit):
            lc.check_base(prod, True)  # 플래그가 있어도 운영은 거절


def test_LOADTEST_환경이_없으면_거절한다():
    with pytest.raises(SystemExit):
        lc.check_env({}, False)
    lc.check_env({"LOADTEST": "1"}, False)
    lc.check_env({}, True)
