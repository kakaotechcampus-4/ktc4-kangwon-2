"""생성 기록 — 놀이 연간의 구간 다시 부르기 · 전송 재시도 · 시도 기록(`attempts`) (ADR-096).

`test_plans_play_project.py` 의 두 장면(거절된 구간 한 번 더 · 다시 불러도 거절)과
`test_play_project_llm_cap.py` 의 실제 전송 경로를 기록과 함께 다시 돌린다. 이 장면의 `world` 가
다른 생성 기록 시험의 세계와 이름이 겹쳐 파일을 나눴다. 생성 동작은 원래 시험이 그대로 지킨다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import random
import uuid

import pytest
from fastapi.testclient import TestClient
from ssuksak import timing
from test_generation_runs import (  # noqa: F401
    _rows,
    assert_attempts_shape,
    captured_run,
    committed,
)
from test_plans_play_project import (  # noqa: F401 — _logged_in 은 autouse
    _approved,
    _FailingProvider,
    _InvalidPeriodProvider,
    _logged_in,
    _Recording,
    _wrapped_budget_error,
    world,
)
from test_play_project_llm_cap import Scripted, generate, server  # noqa: F401 — server 는 autouse

from app.features.plans import play_project
from app.features.plans.generation_runs import RUN_HEADER
from app.main import app

client = TestClient(app)
KEYS = ("m03_m05", "m06_m08", "m09_m11", "m12_m02")
REJECTED = "ProposalRejectedError"  # 후보가 0개인 답을 Core 가 거절할 때의 예외 클래스 이름


def _period(key, attempt, result="ok"):
    return {"kind": "period", "phase": "llm", "period": key, "attempt": attempt, "result": result}


def _post(world):
    return client.post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    )


def test_다시_부르지_않으면_첫_시도_넷만_구간_키_순서로_남는다(world, captured_run, monkeypatch):
    _approved(monkeypatch, _Recording())

    response = _post(world)

    assert response.status_code == 201, response.text
    attempts = captured_run[-1].final["attempts"]
    assert attempts == [_period(key, 1) for key in KEYS]
    assert_attempts_shape(attempts)


def test_거절된_구간만_다시_부른_것이_첫_시도_뒤에_남는다(world, captured_run, monkeypatch):
    _approved(monkeypatch, _InvalidPeriodProvider(times=1))

    response = _post(world)

    assert response.status_code == 201, response.text
    attempts = captured_run[-1].final["attempts"]
    assert attempts == [
        _period("m03_m05", 1),
        _period("m06_m08", 1),
        _period("m09_m11", 1, REJECTED),
        _period("m12_m02", 1),
        _period("m09_m11", 2),
    ]
    assert_attempts_shape(attempts)


def test_다시_불러도_거절되면_두_번째_시도의_실패_이름이_남고_실행은_실패로_끝난다(
    world, captured_run, monkeypatch
):
    _approved(monkeypatch, _InvalidPeriodProvider(times=2))

    response = _post(world)

    assert response.status_code == 500
    final = captured_run[-1].final
    assert (final["status"], final["error_code"], final["plan_id"]) == (
        "FAILED",
        "GENERATION_FAILED",
        None,
    )
    assert final["attempts"] == [
        _period("m03_m05", 1),
        _period("m06_m08", 1),
        _period("m09_m11", 1, REJECTED),
        _period("m12_m02", 1),
        _period("m09_m11", 2, REJECTED),
    ]
    assert_attempts_shape(final["attempts"])


def test_다시_불러도_풀리지_않는_첫_실패는_두_번째_시도_없이_끝난다(
    world, captured_run, monkeypatch
):
    """한도 · 키 · 호출 상한 같은 실패(`_final`)는 구간을 다시 부르지 않는다."""
    error = _wrapped_budget_error()
    provider = _FailingProvider(error)
    _approved(monkeypatch, provider)

    response = _post(world)

    assert response.status_code == 503
    assert provider.calls == 4  # 다시 부르지 않았다
    attempts = captured_run[-1].final["attempts"]
    assert attempts == [_period(key, 1, type(error).__name__) for key in KEYS]
    assert_attempts_shape(attempts)


def test_다시_부르기_앞에서_멈추면_첫_시도_넷만_남는다(monkeypatch):
    _approved(monkeypatch, _InvalidPeriodProvider(times=1))
    asked = iter([False, True])  # 동시 호출 앞은 지나고 다시 부르기 앞에서 멈춘다
    box = {}

    @timing.timed("annual_play", lambda line: None)
    def handler():
        box["run"] = timing.current()
        with pytest.raises(play_project.GenerationStopped, match="recall"):
            play_project.generate(
                2026, "1", frozenset({3}), stopped=lambda: next(asked), rng=random.Random(0)
            )

    handler()

    assert box["run"].attempts == [
        _period("m03_m05", 1),
        _period("m06_m08", 1),
        _period("m09_m11", 1, REJECTED),
        _period("m12_m02", 1),
    ]


def test_실제_전송_경로에서는_구간_다시_부르기와_전송_재시도가_한_줄에_같이_남는다(monkeypatch):
    """모든 구간이 거절되고 모든 호출의 첫 전송이 끊긴다. 부른 수(설계 최대 쪽)는 지금 그대로다."""
    provider = Scripted(monkeypatch, reject_first=True, undelivered_first=True)

    box = generate()

    assert "error" not in box, repr(box.get("error"))
    attempts = box["run"].attempts
    # 전송 재시도는 작업 스레드에서 적혀 한 라운드 안의 순서는 정해져 있지 않다.
    assert [a["kind"] for a in attempts] == (
        ["transport"] * 4 + ["period"] * 4 + ["transport"] * 4 + ["period"] * 4
    )
    assert all(
        a == {"kind": "transport", "phase": "prompt", "result": "ok"}
        for a in attempts
        if a["kind"] == "transport"
    )  # 작업 스레드가 부른 쪽의 구간 이름이다 — 어느 구간인지는 모른다
    assert [a for a in attempts if a["kind"] == "period"] == [
        *(_period(key, 1, REJECTED) for key in KEYS),
        *(_period(key, 2) for key in KEYS),
    ]
    assert_attempts_shape(attempts)
    assert len(provider.attempts) == 16 and box["run"].llm_calls == 16  # 요청 8개 × 전송 2번


def test_다시_부른_구간은_새_연결로_읽어도_그대로고_조회가_준다(committed, monkeypatch):
    _approved(monkeypatch, _InvalidPeriodProvider(times=1))
    rid = uuid.uuid4()

    created = client.post(
        "/api/plans/annual",
        json={"format": "PLAY_PROJECT", "class_id": committed.klass},
        headers={RUN_HEADER: str(rid)},
    )

    assert created.status_code == 201, created.text
    expected = [
        _period("m03_m05", 1),
        _period("m06_m08", 1),
        _period("m09_m11", 1, REJECTED),
        _period("m12_m02", 1),
        _period("m09_m11", 2),
    ]
    (row,) = _rows(id=rid)
    assert row.attempts == expected  # jsonb 로 저장되고 같은 모양으로 돌아온다
    assert_attempts_shape(row.attempts)
    got = client.get(f"/api/generation-runs/{rid}")
    assert got.status_code == 200, got.text
    assert got.json()["attempts"] == expected
    listed = client.get(f"/api/generation-runs?class_id={committed.klass}").json()["items"]
    assert [item["attempts"] for item in listed] == [expected]
