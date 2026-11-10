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


def _resolver(*ips):
    return lambda host, port: [(None, None, None, "", (ip, 0)) for ip in ips]


def _refused(resolver=None, base="http://backend:8000", environ=None):
    resolver = resolver or _resolver("172.29.0.3")
    environ = {"LOADTEST": "1"} if environ is None else environ
    with pytest.raises(SystemExit):
        lc.check_target(base, environ, resolver)


def test_부하_대상은_loadtest_망_안의_backend_뿐이다():
    lc.check_target("http://backend:8000", {"LOADTEST": "1"}, _resolver("172.29.0.3"))
    # 이름이 backend 가 아니면 거절 — loopback 도(운영 8000 이 열려 있다), 운영 주소는 더더욱
    for base in (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://10.0.0.5:8000",
        "https://ssample.duckdns.org",
        "http://ssample.duckdns.org:80",
    ):
        _refused(base=base)
    # backend 가 운영 망(172.28)이나 망 밖으로 풀리거나, 하나라도 밖이거나, 풀리지 않으면 거절
    _refused(_resolver("172.28.0.3"))
    _refused(_resolver("172.29.0.3", "172.28.0.9"))
    _refused(_resolver("::1"))
    _refused(_resolver())

    def broken(host, port):
        raise OSError("Name or service not known")

    _refused(broken)
    _refused(environ={})  # LOADTEST=1 이 없다


def test_DB_호스트도_loadtest_망_안이어야_한다():
    lc.check_db("postgresql://u:p@db:5432/ssuksak", _resolver("172.29.0.2"))
    with pytest.raises(SystemExit):
        lc.check_db("postgresql://u:p@db:5432/ssuksak", _resolver("172.28.0.2"))
    with pytest.raises(SystemExit):
        lc.check_db("postgresql://u:p@localhost:5432/ssuksak", _resolver("127.0.0.1"))


def test_다음_단계_추정은_반복과_S2_최대_시도를_곱한다():
    assert lc.MAX_ATTEMPTS == {
        "s1": 2,
        "s2": 6,
    }  # S2: 주제 · 소주제 · 개수 수리 3호출 × 전송 재시도
    assert lc.parse_next("s2:10x2") == ("s2", 10, 2)
    with pytest.raises(SystemExit):
        lc.parse_next("s2:10")
    assert lc.worst_case_won("s2", 10, 2, 50.0) == 10 * 2 * 6 * 50.0
    assert lc.worst_case_won("s1", 40, 3, 10.0) == 40 * 3 * 2 * 10.0


def _event(kind, scenario="s1", **kv):
    return {"kind": kind, "kv": kv, "rnd": {"scenario": scenario}}


def test_비용을_모르는_호출이_있으면_다음_단계는_멈춘다():
    known = {k: 0 for k in ("usage_incomplete", "usage_missing", "log_gap", "timeout_unpriced")}
    assert lc.next_verdict(0, 100, 50, known) == "진행 가능"
    assert lc.next_verdict(29_950, 100, 50, known) == "멈춤(상한 초과 가능)"
    assert lc.next_verdict(0, 0, 0, known) == "멈춤(단가 모름)"  # 단가를 한 번도 못 봤다

    ok = _event("llm_call", outcome="ok")
    # usage 가 불완전한 성공 호출
    sp = lc.spend([ok, _event("llm_usage", prompt="-", completion="-")], {"s1": 1})
    assert sp["unknown"]["usage_incomplete"] == 1
    assert lc.next_verdict(0, 100, 50, sp["unknown"]) == "멈춤(단가 모름)"
    # llm_usage 줄이 아예 없는 성공 호출
    assert lc.spend([ok], {"s1": 1})["unknown"]["usage_missing"] == 1
    # 단가를 아직 못 본 timeout 만 있는 로그
    sp = lc.spend([_event("llm_call", outcome="timeout")], {})
    assert sp["unknown"]["timeout_unpriced"] == 1 and sp["timeout_won"] == 0
    # 로그 수집 실패: 201 이 있는데 성공 호출 줄이 없다(S2 는 201 하나에 성공 호출 2 이상)
    assert lc.spend([], {"s1": 1, "s2": 3})["unknown"]["log_gap"] == 7
    # 아무 문제 없는 로그
    good = [ok, _event("llm_usage", prompt="1000", completion="1000")]
    assert not any(lc.spend(good, {"s1": 1})["unknown"].values())


def test_한도_오류가_있는_회차는_남은_회차를_멈춘다():
    rnd = {"requests": [{"status": 201}, {"status": 503, "code": "LLM_BUDGET_EXCEEDED"}]}
    assert lc.budget_exceeded(rnd)
    assert not lc.budget_exceeded({"requests": [{"status": 201}, {"status": 500, "code": "X"}]})


def test_plan_timing_total_ms_는_요청과_짝짓지_않고_분포로_본다():
    timings = [_event("plan_timing", total_ms="10000"), _event("plan_timing", total_ms="100")]
    assert lc.plan_totals(timings) == [10000.0, 100.0]  # 끝 시각 순서와 무관하다
    assert not hasattr(lc, "rtt_gaps")  # 종료 시각으로 짝짓던 계산은 순서가 바뀌면 틀려서 없앴다


def test_요청_하나가_여러_번_불러도_첫_시작만_센다():
    def call(run, end_s, ms):
        ts = datetime(2026, 11, 10, 11, 0, end_s, tzinfo=UTC)
        return {"ts": ts, "kv": {"run": run, "ms": str(ms)}}

    # S2: run a 는 9초 호출 뒤에 또 9초 호출. S1(run=-)은 요청마다 하나라 전부 센다.
    starts = lc.first_starts(
        [call("a", 10, 9000), call("a", 19, 9000), call("-", 12, 9000), call("-", 12, 9000)]
    )
    assert sorted(starts) == [
        datetime(2026, 11, 10, 11, 0, 1, tzinfo=UTC),
        datetime(2026, 11, 10, 11, 0, 3, tzinfo=UTC),
        datetime(2026, 11, 10, 11, 0, 3, tzinfo=UTC),
    ]
