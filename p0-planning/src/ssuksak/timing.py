"""생성 요청 한 번이 어디서 시간을 쓰는지 잰다. **숫자와 구간 이름만 모은다** — 프롬프트 · 생성 글 ·
반 이름 · 아이 정보는 여기 들어오지 않는다(CLAUDE.md §21).

구간은 겹치지 않는다. 지금 구간은 언제나 하나고 `phase()` 가 다음 구간으로 넘긴다. `span()` 은 잠깐
다른 구간으로 갔다가 돌아온다(LLM 호출 · 참조 파일 읽기). 그래서 구간 합 = 전체 시간이다.

**열린 실행이 없으면 아무것도 안 한다.** 테스트 · 편집 · 다른 기능에서 불려도 영향이 없다. 실행은
요청이 도는 스레드의 `contextvars` 에만 보인다.

**밖에서 볼 수 있게 세 가지를 열어 둔다**(`observe` · `note_prompt` · `note_attempt`) — 구간이 바뀔 때와
끝날 때 관측 쪽을 부르고, 요청이 보낸 프롬프트 판 이름과 요청 안의 다시 하기(`attempt`)를 모은다. 이것도
숫자 · 이름뿐이다 — 시도 기록은 종류 · 구간 · 번호 · 예외 **클래스 이름**만 받는다. 관측 쪽이 예외를 내지
않는 것은 관측 쪽 몫이다 — 여기서 삼키지 않는다.
"""

from __future__ import annotations

import contextvars
import functools
import json
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

_current: contextvars.ContextVar[Run | None] = contextvars.ContextVar("ssuksak_timing", default=None)


class Run:
    def __init__(self, kind: str, first_phase: str) -> None:
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.phase = first_phase
        self.ms: dict[str, float] = {}
        self.llm_calls = 0
        # 관측 쪽은 구간이 바뀔 때 `phase(name)`, 끝날 때 `end(run, result, error)` 를 받는다.
        self.observer = None
        self.prompts: list[str] = []  # 이 실행이 보낸 프롬프트 판 이름 — 처음 쓴 순서, 중복 없이
        self.attempts: list[dict] = []  # 요청 안의 다시 하기 — 적힌 순서
        self._started = self._mark = time.perf_counter()

    def switch(self, name: str) -> str:
        """지금 구간에 시간을 붙이고 `name` 으로 넘긴다. 앞 구간 이름을 돌려준다."""
        now = time.perf_counter()
        self.ms[self.phase] = self.ms.get(self.phase, 0.0) + (now - self._mark) * 1000
        self._mark, previous, self.phase = now, self.phase, name
        if self.observer is not None and name != previous:
            self.observer.phase(name)
        return previous

    def summary(self, outcome: str) -> str:
        self.switch(self.phase)
        total = (time.perf_counter() - self._started) * 1000
        parts = " ".join(f"{name}_ms={ms:.0f}" for name, ms in self.ms.items())
        return (
            f"plan_timing run={self.id} kind={self.kind} outcome={outcome} total_ms={total:.0f} "
            f"{parts} llm_calls={self.llm_calls}"
        )


class _Worker:
    """다른 스레드에서 본 실행 — 같은 run id · kind 로 `llm_call` 줄을 남기되 시간 구간은 나누지 않는다.

    여러 스레드가 한 `Run` 의 구간을 번갈아 바꾸면 구간 이름이 섞인다. 그래서 구간은 요청 스레드만 나누고,
    여기서는 이름만 따라간다(`llm_call` 의 phase). **부른 수는 세지 않고 `root` 의 것을 같이 쓴다** —
    스레드마다 따로 세면 상한이 스레드 수만큼 늘어난다. 작업 스레드가 또 스레드를 열어도 `root` 는 같다.
    """

    def __init__(self, run: Run | _Worker) -> None:
        self.id, self.kind, self.phase = run.id, run.kind, run.phase
        self.root = run.root if isinstance(run, _Worker) else run

    def switch(self, name: str) -> str:
        previous, self.phase = self.phase, name
        return previous


_count = threading.Lock()


def in_thread(fn: Callable) -> Callable:
    """`fn` 을 다른 스레드(ThreadPoolExecutor)에서 부를 수 있게 감싼다 — 지금 실행이 그 스레드에도 보인다."""
    run = _current.get()
    if run is None:
        return fn

    def call(*args, **kwargs):
        token = _current.set(_Worker(run))
        try:
            return fn(*args, **kwargs)
        finally:
            _current.reset(token)

    return call


def reserve_llm_call(limit: int) -> bool | None:
    """LLM 호출 한 번을 센다. 실행이 없으면 `None`, 이미 `limit` 번이면 세지 않고 `False`, 아니면 세고 `True`.

    검사와 증가를 한 락 안에서 한다 — 스레드 여러 개가 동시에 와도 합이 `limit` 을 넘지 않는다.
    세는 곳은 요청의 `Run` 하나다(`in_thread` 로 열린 스레드도 같은 것을 쓴다).
    """
    run = _current.get()
    if run is None:
        return None
    root = run.root if isinstance(run, _Worker) else run
    with _count:
        if root.llm_calls >= limit:
            return False
        root.llm_calls += 1
    return True


def current() -> Run | None:
    return _current.get()


def observe(observer) -> None:
    """지금 실행의 구간 변화와 끝을 `observer` 가 받게 한다. 실행이 없거나 작업 스레드면 아무것도 안 한다."""
    run = _current.get()
    if isinstance(run, Run):
        run.observer = observer


def note_prompt(version: str | None) -> None:
    """이 실행이 보낸 프롬프트 판 이름을 적는다 — 같은 이름은 한 번만, 처음 쓴 순서대로.

    `reserve_llm_call` 처럼 작업 스레드에서도 루트 실행에 적고, 같은 락을 쓴다. 실행이 없으면 아무것도 안 한다.
    """
    run = _current.get()
    if run is None or not version:
        return
    root = run.root if isinstance(run, _Worker) else run
    with _count:
        if version not in root.prompts:
            root.prompts.append(version)


def note_attempt(kind: str, result: str, **names: str | int) -> None:
    """요청 안의 다시 하기 하나를 적는다 — `kind` · 지금 구간 · `names`(구간 키 · 번호) · `result`.

    `result` 는 `"ok"` 나 예외 **클래스 이름**이다 — 메시지는 받지 않는다. `note_prompt` 처럼 작업 스레드에서도
    루트 실행에 적고 같은 락을 쓴다. 실행이 없으면 아무것도 안 한다.
    """
    run = _current.get()
    if run is None:
        return
    root = run.root if isinstance(run, _Worker) else run
    with _count:
        root.attempts.append({"kind": kind, "phase": run.phase, **names, "result": result})


@contextmanager
def attempt(kind: str, **names: str | int):
    """몸통을 시도 하나로 적는다 — 끝나면 `ok`, 예외가 나면 그 클래스 이름. 예외는 그대로 다시 올린다."""
    try:
        yield
    except Exception as error:
        note_attempt(kind, type(error).__name__, **names)
        raise
    note_attempt(kind, "ok", **names)


def phase(name: str) -> None:
    run = _current.get()
    if run is not None:
        run.switch(name)


def set_kind(kind: str) -> None:
    run = _current.get()
    if run is not None:
        run.kind = kind


@contextmanager
def span(name: str):
    """잠깐 `name` 구간에 있다가 앞 구간으로 돌아온다. 앞 구간 이름을 준다(실행이 없으면 None)."""
    run = _current.get()
    if run is None:
        yield None
        return
    previous = run.switch(name)
    try:
        yield previous
    finally:
        run.switch(previous)


def timed(kind: str, emit: Callable[[str], None], first_phase: str = "db_read"):
    """생성 API 하나를 실행 하나로 감싸고, 끝날 때(성공 · 실패 모두) 요약 한 줄을 `emit` 한다."""

    def decorate(handler):
        @functools.wraps(handler)
        def wrapper(*args, **kwargs):
            run = Run(kind, first_phase)
            token = _current.set(run)
            outcome = "ok"
            result = failure = None
            try:
                result = handler(*args, **kwargs)
                return result
            except BaseException as error:
                failure = error
                code = getattr(error, "status_code", None)
                outcome = f"http_{code}" if isinstance(code, int) else type(error).__name__
                raise
            finally:
                _current.reset(token)
                emit(run.summary(outcome))
                if run.observer is not None:
                    run.observer.end(run, result, failure)

        return wrapper

    return decorate


def read_json(path) -> object:
    """참조 파일 하나를 읽는다(읽기 + JSON 해독만 `reference_load` 에 든다. 스키마 검사는 부른 구간)."""
    with span("reference_load"):
        return json.loads(Path(path).read_text(encoding="utf-8"))
