"""생성 요청 시간 기록: 구간 합 = 전체, 실행 밖에서는 아무것도 안 함, 실패도 요약 한 줄."""

import re

import pytest

from ssuksak import timing


def _fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", line))


def test_구간은_겹치지_않고_합이_전체와_같다():
    lines = []

    @timing.timed("monthly_theme", lines.append)
    def handler():
        timing.phase("select")
        with timing.span("llm") as previous:
            assert previous == "select"
            timing.current().llm_calls += 1
        timing.phase("save")
        return "done"

    assert handler() == "done"
    assert len(lines) == 1
    fields = _fields(lines[0])
    assert lines[0].startswith("plan_timing ")
    assert fields["kind"] == "monthly_theme" and fields["outcome"] == "ok"
    assert fields["llm_calls"] == "1"
    phases = {k: int(v) for k, v in fields.items() if k.endswith("_ms") and k != "total_ms"}
    assert set(phases) == {"db_read_ms", "select_ms", "llm_ms", "save_ms"}
    # 반올림 오차만큼(구간마다 0.5ms) 어긋날 수 있다.
    assert abs(sum(phases.values()) - int(fields["total_ms"])) <= len(phases)
    assert timing.current() is None


def test_실행이_없으면_아무것도_안_한다():
    timing.phase("select")
    timing.set_kind("weekly")
    with timing.span("llm") as previous:
        assert previous is None
    assert timing.current() is None


def test_실패해도_요약_한_줄을_남기고_오류는_그대로_난다():
    lines = []

    class Conflict(Exception):
        status_code = 409

    @timing.timed("annual_theme", lines.append)
    def handler():
        timing.set_kind("annual_play")
        raise Conflict

    with pytest.raises(Conflict):
        handler()
    fields = _fields(lines[0])
    assert fields["kind"] == "annual_play" and fields["outcome"] == "http_409"
    assert timing.current() is None


def test_작업_스레드의_호출은_같은_실행으로_세고_구간은_요청_스레드만_나눈다():
    from concurrent.futures import ThreadPoolExecutor

    lines, seen = [], []

    def call():
        with timing.span("llm") as previous:
            run = timing.current()
            run.llm_calls += 1
            seen.append((run.id, run.kind, previous))
        timing.phase("parse")  # 작업 스레드 안의 구간 이름은 요청 실행에 닿지 않는다

    @timing.timed("annual_play", lines.append)
    def handler():
        timing.phase("llm")
        with ThreadPoolExecutor(4) as pool:
            jobs = [pool.submit(timing.in_thread(call)) for _ in range(4)]
            [job.result() for job in jobs]
        timing.phase("save")
        return timing.current().id

    run_id = handler()
    fields = _fields(lines[0])
    assert fields["llm_calls"] == "4"
    assert seen == [(run_id, "annual_play", "llm")] * 4
    phases = {k for k in fields if k.endswith("_ms") and k != "total_ms"}
    assert phases == {"db_read_ms", "llm_ms", "save_ms"}
    assert timing.in_thread(call) is call  # 실행이 없으면 감싸지 않는다
