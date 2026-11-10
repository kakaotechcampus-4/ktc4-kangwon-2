"""부하 측정 스크립트(scripts/load_check.py)의 순수 함수 — 서버도 LLM 도 부르지 않는다."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "load_check.py"
_spec = importlib.util.spec_from_file_location("load_check", _PATH)
lc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lc)

_GATE = Path(__file__).resolve().parents[1] / "scripts" / "loadtest_gate.py"
_gate_spec = importlib.util.spec_from_file_location("loadtest_gate", _GATE)
gate = importlib.util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(gate)

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


def test_원화_계산과_사후_집계의_시간초과는_호출_최대_단가로_센다():
    assert lc.cost_won(1000, 1000) == pytest.approx(2.835 + 14.175)

    def event(kind, **kv):
        return {"kind": kind, "kv": kv, "rnd": {"scenario": "s2"}}

    sp = lc.spend(
        [
            event("llm_usage", prompt="1000", completion="1000"),
            event("llm_usage", prompt="2000", completion="1000"),
            event("llm_usage", prompt="-", completion="-"),  # 숫자가 아니면 세지 않는다
            event("llm_call", outcome="timeout"),
            event("llm_call", outcome="failed"),  # failed 도 과금됐을 수 있어 같이 센다
            event("llm_call", outcome="ok"),
        ]
    )
    assert sp["calls"] == 2 and sp["timeouts"] == 2
    assert sp["timeout_won"] == pytest.approx(2 * lc.cost_won(2000, 1000))


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
    _refused(_resolver("172.29.0.1"))  # 게이트웨이(호스트로 나가는 문)는 backend 가 아니다
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


def _event(kind, **kv):
    return {"kind": kind, "kv": kv}


def _ok_call(outcome="ok"):
    return _event("llm_call", outcome=outcome)


def _usage(prompt="11140", completion="1011"):
    return _event("llm_usage", prompt=prompt, completion=completion)


def _baseline(scenario, events_by_request, status=201):
    return [
        lc.baseline_request(scenario, {"status": status}, events) for events in events_by_request
    ]


def test_기준선_요청은_성공_호출마다_usage_가_있어야_비용을_안다():
    one = lc.cost_won(11140, 1011)
    s1 = lc.baseline_request("s1", {"status": 201}, [_ok_call(), _usage()])
    assert s1 == {"won": pytest.approx(one), "attempts": 1}
    # 전송 재시도(not_delivered)는 과금 없는 시도로 센다
    retried = lc.baseline_request(
        "s1", {"status": 201}, [_ok_call("not_delivered"), _ok_call(), _usage()]
    )
    # 시도 수는 성공 호출만 센다 — 재시도 1 + 성공 1 도 1 이라 배율(최대 시도 ÷ 시도)이 안 준다
    assert retried["attempts"] == 1 and retried["won"] == pytest.approx(one)
    judged = lc.judge_budget(
        {
            "s1": [retried] * 4,
            "s2": [
                lc.baseline_request(
                    "s2", {"status": 201}, [_ok_call(), _ok_call(), _usage(), _usage()]
                )
            ]
            * 4,
        }
    )
    assert judged["detail"]["s1"]["factor"] == 2.0
    s2 = lc.baseline_request("s2", {"status": 201}, [_ok_call(), _ok_call(), _usage(), _usage()])
    assert s2 == {"won": pytest.approx(2 * one), "attempts": 2}
    # 모르는 경우: usage 없음 · 불완전 · llm_call 없음 · failed · timeout · 201 아님 · S2 호출 부족
    assert "stop" in lc.baseline_request("s1", {"status": 201}, [_ok_call()])
    assert "stop" in lc.baseline_request("s1", {"status": 201}, [_ok_call(), _usage("-", "-")])
    assert "stop" in lc.baseline_request("s1", {"status": 201}, [])
    assert "stop" in lc.baseline_request("s1", {"status": 201}, [_ok_call("failed"), _usage()])
    assert "stop" in lc.baseline_request("s1", {"status": 201}, [_ok_call("timeout")])
    assert "stop" in lc.baseline_request("s1", {"status": 500, "code": "X"}, [_ok_call(), _usage()])
    assert "stop" in lc.baseline_request("s2", {"status": 201}, [_ok_call(), _usage()])


def test_budget_판정_정상_usage없음_failed_상한초과():
    assert lc.MAX_ATTEMPTS == {
        "s1": 2,
        "s2": 6,
    }  # S2: 주제 · 소주제 · 개수 수리 3호출 × 전송 재시도
    # 남은 계획: S1 (10+20+40)×2 = 140건, S2 (10+20+40)×1 = 70건
    assert sum(n * r for n, r in lc.PLAN["s1"]) == 140
    assert sum(n * r for n, r in lc.PLAN["s2"]) == 70

    def good(won, attempts):
        return {"won": won, "attempts": attempts}

    # 정상: S1 최대 5원(시도 1) → ×2 = 10원 × 140건. S2 최대 40원(시도 2) → ×3 = 120원 × 70건
    ok = lc.judge_budget(
        {"s1": [good(4, 1), good(5, 1), good(4, 1), good(5, 1)], "s2": [good(40, 2)] * 4}
    )
    assert ok["verdict"] == "진행 가능"
    assert ok["worst"] == pytest.approx(140 * 10 + 70 * 120)
    assert ok["spent"] == pytest.approx(18 + 160)
    assert ok["room"] == pytest.approx(30_000 - 178)
    # usage 없음 · failed 있음: 기준선 요청 하나만 비용을 몰라도 멈춘다
    unknown = {"stop": "usage 가 없거나 불완전하다"}
    bad = lc.judge_budget({"s1": [good(4, 1)] * 3 + [unknown], "s2": [good(40, 2)] * 4})
    assert bad["verdict"] == "멈춤(단가 모름)" and bad["reasons"]
    # 기준선 요청이 모자라도(4건이 아니면) 모른다
    assert lc.judge_budget({"s1": [good(4, 1)] * 4, "s2": [good(40, 2)] * 3})["reasons"]
    # 상한 초과: S2 요청당 최대 400원 → ×3 = 1,200 × 70 = 84,000
    big = lc.judge_budget({"s1": [good(4, 1)] * 4, "s2": [good(400, 2)] * 4})
    assert big["verdict"] == "멈춤(상한 초과 가능)"
    # 계산식 경계: 최악 == 여유면 진행 가능, 1원이라도 넘으면 멈춤
    edge = {"s1": [good(0, 1)] * 4, "s2": [good(0, 2)] * 4}
    edge["s1"][0] = good(1, 1)  # 기준선 지출 1원 → 여유 29,999
    edge["s2"][0] = good(0.0, 2)
    assert lc.judge_budget(edge)["verdict"] == "진행 가능"


def test_DB_URL_에_쿼리_옵션이_있으면_거절한다():
    lc.check_db("postgresql://u:p@db:5432/ssuksak", _resolver("172.29.0.2"))
    for url in (
        "postgresql://u:p@db:5432/ssuksak?host=203.0.113.9",
        "postgresql://u:p@db:5432/ssuksak?sslmode=disable",
    ):
        with pytest.raises(SystemExit):
            lc.check_db(url, _resolver("172.29.0.2"))


def _good_config():
    mib = 1 << 20
    default_net = {"default": None}
    return {
        "name": "loadtest",
        "services": {
            "db": {
                "image": "postgres:15",
                "restart": "no",
                "mem_limit": 512 * mib,
                "memswap_limit": 512 * mib,
                "networks": dict(default_net),
                "volumes": [
                    {"type": "volume", "source": "pgdata", "target": "/var/lib/postgresql"}
                ],
            },
            "backend": {
                "image": gate.IMAGE,
                "restart": "no",
                "mem_limit": 1024 * mib,
                "memswap_limit": 1024 * mib,
                "networks": dict(default_net),
                "environment": {
                    "LOADTEST": "1",
                    "LLM_MODE": "real",
                    "IS_SERVER": "1",
                    "ALLOW_TEST_RESET": "0",
                    "DATABASE_URL": "postgresql+psycopg://ssuksak:pw@db:5432/ssuksak",
                },
            },
            "loadgen": {
                "image": gate.IMAGE,
                "restart": "no",
                "mem_limit": 256 * mib,
                "memswap_limit": 256 * mib,
                "networks": dict(default_net),
                "environment": {"LOADTEST": "1", "DATABASE_URL": "postgresql://ssuksak:pw@db/x"},
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/lt/dir/load_check.py",
                        "target": "/lt/load_check.py",
                    },
                    {"type": "bind", "source": "/lt/dir/out", "target": "/lt/out"},
                ],
            },
        },
        "networks": {
            "default": {
                "name": "loadtest_default",
                "ipam": {"config": [{"subnet": "172.29.0.0/16", "gateway": "172.29.0.1"}]},
            }
        },
        "volumes": {"pgdata": {"name": "loadtest_pgdata"}},
    }


def _failures(cfg):
    res = gate.results(cfg, json.dumps(cfg), "real", "1", "/lt/dir")
    return [label for ok, label in res if not ok]


def test_gate_는_정상_설정을_통과시키고_위험한_변형_하나하나를_거절한다():
    assert _failures(_good_config()) == []

    def mutated(change):
        cfg = _good_config()
        change(cfg)
        return _failures(cfg)

    host_net = mutated(lambda c: c["services"]["backend"].update(network_mode="host"))
    assert any("network_mode" in f for f in host_net)
    extra_net = mutated(
        lambda c: c["services"]["backend"]["networks"].update({"ktc4_default": None})
    )
    assert any("default 하나뿐" in f for f in extra_net)
    bind = mutated(
        lambda c: c["services"]["backend"].update(
            volumes=[{"type": "bind", "source": "/var/run/docker.sock", "target": "/s"}]
        )
    )
    assert any("bind mount" in f for f in bind)
    # 허용 목록의 경로라도 다른 서비스가 마운트하면 거절
    other = mutated(
        lambda c: c["services"]["db"].update(
            volumes=[{"type": "bind", "source": "/lt/dir/out", "target": "/lt/out"}]
        )
    )
    assert any("bind mount" in f for f in other)
    latest = mutated(lambda c: c["services"]["db"].update(image="postgres:latest"))
    assert any("postgres:15" in f for f in latest)
    opts = mutated(
        lambda c: c["volumes"]["pgdata"].update(driver_opts={"type": "nfs", "device": ":/prod"})
    )
    assert any("driver_opts" in f for f in opts)
    named = mutated(lambda c: c["volumes"].update({"other": {"name": "x"}}))
    assert any("pgdata 하나뿐" in f for f in named)

    def set_url(service, url):
        def change(c):
            c["services"][service]["environment"]["DATABASE_URL"] = url

        return change

    host = mutated(set_url("backend", "postgresql+psycopg://u:p@db:5432/x?host=172.29.0.1"))
    assert any("backend DATABASE_URL 에 쿼리" in f for f in host)
    assert any(
        "loadgen DATABASE_URL 에 쿼리" in f
        for f in mutated(set_url("loadgen", "postgresql://u@db/x?host=h"))
    )
    pghost = mutated(
        lambda c: c["services"]["backend"]["environment"].update({"PGHOST": "203.0.113.9"})
    )
    assert any("PG* 변수" in f for f in pghost)


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
