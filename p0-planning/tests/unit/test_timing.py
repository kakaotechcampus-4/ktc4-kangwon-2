"""생성 요청 시간 기록: 구간 합 = 전체, 실행 밖에서는 아무것도 안 함, 실패도 요약 한 줄."""

import re
import threading
from concurrent.futures import ThreadPoolExecutor

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
    lines, seen = [], []

    def call():
        with timing.span("llm") as previous:
            run = timing.current()
            assert timing.reserve_llm_call(100) is True
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


def test_실행이_없으면_호출을_세지_않고_None_을_준다():
    assert timing.reserve_llm_call(1) is None


def test_상한에_닿으면_세지_않고_False_를_준다():
    @timing.timed("annual_play", lambda line: None)
    def handler():
        results = [timing.reserve_llm_call(2) for _ in range(4)]
        return results, timing.current().llm_calls

    assert handler() == ([True, True, False, False], 2)


def test_작업_스레드가_세는_수는_요청_실행_하나에_쌓인다():
    """스레드마다 따로 세지 않는다 — 아직 도는 작업의 호출도 요청 스레드가 바로 본다."""
    inside = threading.Event()
    leave = threading.Event()

    def job():
        assert timing.reserve_llm_call(10) is True
        inside.set()
        leave.wait(5)

    @timing.timed("annual_play", lambda line: None)
    def handler():
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(timing.in_thread(job))
            assert inside.wait(5)
            seen = timing.current().llm_calls  # 작업이 끝나기 전이다
            leave.set()
            future.result()
        return seen

    assert handler() == 1


def test_스레드_여럿이_동시에_와도_합이_상한을_넘지_않는다():
    limit, threads = 20, 64
    start = threading.Barrier(threads)

    def job():
        start.wait(5)  # 한꺼번에 몰아 경합을 만든다
        return timing.reserve_llm_call(limit)

    @timing.timed("annual_play", lambda line: None)
    def handler():
        with ThreadPoolExecutor(threads) as pool:
            jobs = [pool.submit(timing.in_thread(job)) for _ in range(threads)]
            results = [j.result() for j in jobs]
        return results, timing.current().llm_calls

    results, total = handler()
    assert results.count(True) == limit and results.count(False) == threads - limit
    assert total == limit


def test_작업_스레드가_연_스레드도_같은_실행을_센다():
    def inner():
        return timing.reserve_llm_call(2)

    def outer():
        with ThreadPoolExecutor(1) as pool:
            nested = pool.submit(timing.in_thread(inner)).result()
        return nested, timing.reserve_llm_call(2)

    @timing.timed("annual_play", lambda line: None)
    def handler():
        with ThreadPoolExecutor(1) as pool:
            results = pool.submit(timing.in_thread(outer)).result()
        return results, timing.current().llm_calls

    assert handler() == ((True, True), 2)


def test_실행_둘은_서로의_횟수를_모른다():
    @timing.timed("annual_play", lambda line: None)
    def handler():
        return [timing.reserve_llm_call(1), timing.reserve_llm_call(1)]

    assert handler() == [True, False]
    assert handler() == [True, False]  # 앞 실행이 찬 것이 다음 실행에 남지 않는다


def test_작업이_실패해도_스레드의_실행을_되돌리고_세던_수는_남는다():
    class Boom(Exception):
        pass

    def job():
        assert timing.reserve_llm_call(5) is True
        raise Boom

    def probe():
        return timing.current() is None

    @timing.timed("annual_play", lambda line: None)
    def handler():
        with ThreadPoolExecutor(1) as pool:  # 같은 스레드를 다시 쓴다
            with pytest.raises(Boom):
                pool.submit(timing.in_thread(job)).result()
            assert pool.submit(probe).result() is True  # 실패한 작업의 실행이 스레드에 남지 않았다
        return timing.current().llm_calls

    assert handler() == 1
    assert timing.current() is None


class _Watcher:
    """관측 쪽 — 받은 것을 적는다. 끝에서 구간 합을 같이 적어 `summary` 뒤에 불렸는지 본다."""

    def __init__(self):
        self.phases, self.ends = [], []

    def phase(self, name):
        self.phases.append(name)

    def end(self, run, result, error):
        self.ends.append((result, error, sum(run.ms.values())))


def test_관측_쪽이_루트_구간_전환을_순서대로_받는다():
    watcher = _Watcher()

    @timing.timed("weekly", lambda line: None)
    def handler():
        timing.observe(watcher)
        timing.phase("select")
        with timing.span("llm"):  # 갔다 돌아오는 전환도 받는다
            pass
        timing.phase("select")  # 이미 있는 구간으로 넘기는 것은 전환이 아니다
        timing.phase("save")

    handler()
    assert watcher.phases == ["select", "llm", "select", "save"]


def test_작업_스레드의_구간_전환은_관측_쪽에_가지_않는다():
    watcher = _Watcher()

    def job():
        timing.phase("parse")
        with timing.span("llm"):
            pass

    @timing.timed("annual_play", lambda line: None)
    def handler():
        timing.observe(watcher)
        with ThreadPoolExecutor(2) as pool:
            [f.result() for f in [pool.submit(timing.in_thread(job)) for _ in range(2)]]

    handler()
    assert watcher.phases == []


def test_성공하면_끝을_한_번_받고_그때_구간_합이_다_차_있다():
    watcher, lines = _Watcher(), []

    @timing.timed("monthly_theme", lines.append)
    def handler():
        timing.observe(watcher)
        timing.phase("save")
        return "done"

    assert handler() == "done"
    assert len(watcher.ends) == 1
    result, error, ms_sum = watcher.ends[0]
    assert (result, error) == ("done", None)
    assert abs(ms_sum - int(_fields(lines[0])["total_ms"])) <= 3  # summary 가 마지막 구간을 붙인 뒤다


def test_실패하면_오류를_받고_원래_오류가_그대로_난다():
    class Stopped(Exception):
        status_code = 499

    watcher, boom = _Watcher(), Stopped()

    @timing.timed("annual_play", lambda line: None)
    def handler():
        timing.observe(watcher)
        raise boom

    with pytest.raises(Stopped):
        handler()
    assert [(r, e) for r, e, _ in watcher.ends] == [(None, boom)]


def test_관측은_실행_밖과_작업_스레드에서는_아무_일도_안_하고_없으면_기존_그대로다():
    timing.observe(_Watcher())  # 실행 밖

    seen = []

    def job():
        timing.observe(_Watcher())
        seen.append(timing.current().root.observer)

    @timing.timed("annual_play", lambda line: None)
    def handler():
        with ThreadPoolExecutor(1) as pool:
            pool.submit(timing.in_thread(job)).result()
        timing.phase("save")  # 관측 쪽이 없어도 그대로 돈다
        return timing.current().observer

    assert handler() is None
    assert seen == [None]  # 작업 스레드에서 단 관측 쪽은 루트에 닿지 않았다


def test_프롬프트_판은_순서를_지키고_같은_값은_한_번만_둔다():
    timing.note_prompt("실행 밖")  # 아무 일도 없다

    @timing.timed("monthly_theme", lambda line: None)
    def handler():
        for version in ("a", "b", "a", None, "", "c", "b"):
            timing.note_prompt(version)
        return timing.current().prompts

    assert handler() == ["a", "b", "c"]


def test_작업_스레드_넷이_동시에_프롬프트_판을_적어도_루트_하나에_빠짐없이_쌓인다():
    threads = 4
    start = threading.Barrier(threads)

    def job(n):
        start.wait(5)
        timing.note_prompt(f"v{n}")
        timing.note_prompt("shared")

    @timing.timed("annual_play", lambda line: None)
    def handler():
        with ThreadPoolExecutor(threads) as pool:
            jobs = [pool.submit(timing.in_thread(job), n) for n in range(threads)]
            [j.result() for j in jobs]
        return timing.current().prompts

    assert sorted(handler()) == ["shared", "v0", "v1", "v2", "v3"]
