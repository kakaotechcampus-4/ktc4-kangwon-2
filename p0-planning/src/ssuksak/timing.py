"""생성 요청 한 번이 어디서 시간을 쓰는지 잰다. **숫자와 구간 이름만 모은다** — 프롬프트 · 생성 글 ·
반 이름 · 아이 정보는 여기 들어오지 않는다(CLAUDE.md §21).

구간은 겹치지 않는다. 지금 구간은 언제나 하나고 `phase()` 가 다음 구간으로 넘긴다. `span()` 은 잠깐
다른 구간으로 갔다가 돌아온다(LLM 호출 · 참조 파일 읽기). 그래서 구간 합 = 전체 시간이다.

**열린 실행이 없으면 아무것도 안 한다.** 테스트 · 편집 · 다른 기능에서 불려도 영향이 없다. 실행은
요청이 도는 스레드의 `contextvars` 에만 보인다.
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
        self._started = self._mark = time.perf_counter()

    def switch(self, name: str) -> str:
        """지금 구간에 시간을 붙이고 `name` 으로 넘긴다. 앞 구간 이름을 돌려준다."""
        now = time.perf_counter()
        self.ms[self.phase] = self.ms.get(self.phase, 0.0) + (now - self._mark) * 1000
        self._mark, previous, self.phase = now, self.phase, name
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
    여기서는 이름만 따라가며(`llm_call` 의 phase) 부른 수는 따로 세어 끝날 때 더한다.
    """

    def __init__(self, run: Run) -> None:
        self.id, self.kind, self.phase, self.llm_calls = run.id, run.kind, run.phase, 0

    def switch(self, name: str) -> str:
        previous, self.phase = self.phase, name
        return previous


_merge = threading.Lock()


def in_thread(fn: Callable) -> Callable:
    """`fn` 을 다른 스레드(ThreadPoolExecutor)에서 부를 수 있게 감싼다 — 지금 실행이 그 스레드에도 보인다."""
    run = _current.get()
    if run is None:
        return fn

    def call(*args, **kwargs):
        worker = _Worker(run)
        token = _current.set(worker)
        try:
            return fn(*args, **kwargs)
        finally:
            _current.reset(token)
            with _merge:
                run.llm_calls += worker.llm_calls

    return call


def current() -> Run | None:
    return _current.get()


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
            try:
                return handler(*args, **kwargs)
            except BaseException as error:
                code = getattr(error, "status_code", None)
                outcome = f"http_{code}" if isinstance(code, int) else type(error).__name__
                raise
            finally:
                _current.reset(token)
                emit(run.summary(outcome))

        return wrapper

    return decorate


def read_json(path) -> object:
    """참조 파일 하나를 읽는다(읽기 + JSON 해독만 `reference_load` 에 든다. 스키마 검사는 부른 구간)."""
    with span("reference_load"):
        return json.loads(Path(path).read_text(encoding="utf-8"))
