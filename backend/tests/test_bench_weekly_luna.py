"""주간 bench — 실제 엘리스를 부르지 않고 흐름 · 예산 · 출력 허용 목록 · 서버 가드를 본다.

가짜 전송이 요청 본문을 읽어 mock 과 같은 답을 만든다(그래서 실제 strict 스키마를 통과한다).
진짜 urlopen 은 불리면 실패하도록 바꿔 끼운다.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))  # bench_weekly_luna 가 bench_monthly_luna 를 가져다 쓴다
_spec = importlib.util.spec_from_file_location(
    "bench_weekly_luna", _SCRIPTS / "bench_weekly_luna.py"
)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

USAGE = {"prompt_tokens": 12000, "completion_tokens": 2000, "total_tokens": 14000}
MARKER = "SYNTHETIC-PROVIDER-MARKER"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("실제 네트워크 호출")

    monkeypatch.setattr(urllib_request, "urlopen", refuse)
    monkeypatch.setenv("ELICE_MLAPI_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("ELICE_MLAPI_API_KEY", "test-only-not-a-key")


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake(usage=USAGE, edit=None):
    """mock 과 같은 답. `edit(answer, n)` 으로 n 번째 답을 바꿀 수 있다."""
    model = bench.MonthlyLlmConfig.from_env().model
    sent = []

    def post(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        user = payload["messages"][-1]["content"]
        answer = json.loads(
            RequestAwareWeeklyLlm().generate_weekly(SimpleNamespace(user_content=user)).content
        )
        if edit is not None:
            edit(answer, len(sent))
        assert payload["max_completion_tokens"] == bench.OUTPUT_RESERVE_TOKENS  # 결정 C
        sent.append(payload)
        body = {"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}]}
        body["model"] = model
        if usage is not None:
            body["usage"] = usage(len(sent)) if callable(usage) else usage
        return _Response(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    return post


def _date_once(answer, n):
    if n == 0:  # 첫 답에 입력에 없는 날짜 → 수리 요청
        answer["sections"][0]["value"] = "10월 3일 개천절 행사 준비"


def _run(post, won=1000.0, max_calls=24):
    transport = bench.BudgetedTransport(
        bench.TimedTransport(post=post), won=won, max_calls=max_calls
    )
    out = bench.report(transport, bench.run(transport))
    return transport, out


def test_서버가_아니면_실제_전송을_만들지_않고_live_없이는_부르지_않는다(monkeypatch):
    monkeypatch.delenv("IS_SERVER", raising=False)
    with pytest.raises(RuntimeError, match="IS_SERVER"):
        bench.TimedTransport()
    assert bench.main([]) == 2
    assert bench.main(["--live"]) == 2
    assert bench.main(["--live", "--budget-won", "5000"]) == 2  # 상한 1,000원을 못 넘긴다


def test_요청_아홉개를_돌리고_주간_호출만_센다():
    transport, out = _run(_fake())

    assert (out["requests"], out["saved"], out["skipped_budget"]) == (9, 9, 0)
    assert out["calls"] == 9 and out["repaired"] == 0 and out["stopped"] is None
    schemas = [c["schema"] for c in transport.calls]
    assert schemas.count("weekly_plan_proposal") == 5
    assert schemas.count("weekly_cell_proposal") == 4
    # 단가: 12k 입력 · 2k 출력 = ₩34.02 + ₩28.35 = ₩62.37 / 호출 (gpt-6.1-sol)
    assert out["won"] == pytest.approx(9 * 62.37, abs=0.01)
    decision_b = next(r for r in out["results"] if "결정 B" in r["case"])
    assert decision_b["result"] == "SAVED"
    saturday = next(r for r in out["results"] if r["case"].endswith("토"))
    assert "SAT" in saturday["plan"]["operating_days"]
    # 문장은 --show-values 일 때만 나온다.
    assert all("value" not in c for c in saturday["plan"]["cells"].values())


# ── 예산: 전송마다 예약 (Codex W7b-01 재현 사례) ─────────────────────────────


def test_첫_전송도_예약이_예산을_넘으면_보내지_않는다():
    transport, out = _run(_fake(), won=0.5)
    assert out["calls"] == 0 and out["won"] == 0
    assert out["stopped"] == "budget"
    assert out["saved"] == 0


def test_전송마다_출력_상한을_붙이고_운영_어댑터_요청은_바꾸지_않는다(monkeypatch):
    payloads = []
    fake = _fake(edit=_date_once)

    def post(request, timeout):
        payloads.append(json.loads(request.data.decode("utf-8")))
        return fake(request, timeout)

    # 어댑터가 실제로 만든 요청 — bench 가 상한을 붙이기 전.
    from_adapter = []
    budgeted = bench.BudgetedTransport.post_json

    def record(self, url, *, headers, payload, timeout):
        from_adapter.append(dict(payload))
        return budgeted(self, url, headers=headers, payload=payload, timeout=timeout)

    monkeypatch.setattr(bench.BudgetedTransport, "post_json", record)
    _run(post, max_calls=3)
    assert payloads and all(
        p["max_completion_tokens"] == bench.OUTPUT_RESERVE_TOKENS for p in payloads
    )
    # 운영 주간 요청(문서 · 수리)에는 이 칸들이 없다 — bench 의 전송에서만 붙인다.
    # (놀이 프로젝트 요청만 스트리밍 · 자기 상한을 붙인다 — 2026-10-24 결정.)
    schemas = [p["response_format"]["json_schema"]["name"] for p in from_adapter]
    assert schemas[:2] == ["weekly_plan_proposal"] * 2  # 첫 문서 + 그 수리
    assert all(
        not {"stream", "stream_options", "max_completion_tokens"} & set(p) for p in from_adapter
    )


def test_응답이_예약보다_크면_그_뒤로_멈춘다():
    huge = {"prompt_tokens": 1_000_000, "completion_tokens": 600_000, "total_tokens": 1_600_000}
    transport, out = _run(_fake(huge))  # 한 호출 ≈ ₩11,340 — 예약(수십 원)을 넘는다
    assert out["calls"] == 1
    assert out["stopped"] == "over_reservation"
    assert out["skipped_budget"] >= 1


def test_수리_전송_직전에도_예산을_본다():
    probe, _ = _run(_fake(edit=_date_once), max_calls=1)
    first_reserve = probe.calls[0]["reserved_won"]
    # 표시 예약액의 소수 4자리 반올림 오차만 허용하고, 쓴 돈 + 수리 예약은 넘게 둔다.
    transport, out = _run(_fake(edit=_date_once), won=first_reserve + 0.001)
    assert out["calls"] == 1
    assert out["results"][0]["result"] == "STOPPED_BUDGET"
    assert out["won"] <= out["budget_won"]


def test_usage_를_모르면_예약액을_쓴_것으로_치고_멈춘다():
    transport, out = _run(_fake(usage=None))
    assert out["calls"] == 1
    assert out["stopped"] == "usage_unknown"
    assert transport.spent == pytest.approx(transport.calls[0]["reserved_won"], abs=0.001)


def test_어떤_이력이든_예산을_넘지_않는다():
    def growing(n):  # 뒤로 갈수록 커지는 응답
        return {"prompt_tokens": 12000 * n, "completion_tokens": 2000 * n, "total_tokens": 0}

    for won in (3.0, 5.0, 20.0, 1000.0):
        transport, out = _run(_fake(usage=growing), won=won)
        assert transport.spent <= won + max((c["won"] for c in transport.calls), default=0)
        # 예약을 넘은 호출 뒤로는 더 보내지 않는다.
        over = [i for i, c in enumerate(transport.calls) if c["won"] > c["reserved_won"]]
        assert not over or over[0] == len(transport.calls) - 1


# ── 출력 허용 목록 (Codex W7b-02) ────────────────────────────────────────────


def test_usage_의_추가_문자열은_결과에_남지_않는다():
    usage = {**USAGE, "note": MARKER, "prompt_tokens_details": {"cached_tokens": 0, "x": MARKER}}
    transport, out = _run(_fake(usage=usage), max_calls=1)
    assert out["calls"] == 1
    assert MARKER not in json.dumps(out, ensure_ascii=False)


def test_공급자_오류_본문은_결과에_남지_않는다():
    def fail(request, timeout):
        raise urllib_error.HTTPError(
            "https://llm.invalid/v1", 400, "Bad Request", {}, io.BytesIO(MARKER.encode())
        )

    transport, out = _run(fail)
    assert out["calls"] == 1 and out["http_status"] == {400: 1}
    assert out["stopped"] == "usage_unknown"
    assert MARKER not in json.dumps(out, ensure_ascii=False)
