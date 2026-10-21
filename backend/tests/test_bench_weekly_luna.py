"""주간 bench — 실제 엘리스를 부르지 않고 흐름 · 예산 멈춤 · 서버 가드를 본다.

가짜 전송이 요청 본문을 읽어 mock 과 같은 답을 만든다(그래서 실제 strict 스키마를 통과한다).
진짜 urlopen 은 불리면 실패하도록 바꿔 끼운다.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
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


def _fake(usage=USAGE):
    model = bench.MonthlyLlmConfig.from_env().model

    def post(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        user = payload["messages"][-1]["content"]
        answer = RequestAwareWeeklyLlm().generate_weekly(SimpleNamespace(user_content=user)).content
        body = {"choices": [{"message": {"content": answer}}], "model": model, "usage": usage}
        return _Response(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    return post


def test_서버가_아니면_실제_전송을_만들지_않고_live_없이는_부르지_않는다(monkeypatch):
    monkeypatch.delenv("IS_SERVER", raising=False)
    with pytest.raises(RuntimeError, match="IS_SERVER"):
        bench.TimedTransport()
    assert bench.main([]) == 2
    assert bench.main(["--live"]) == 2
    assert bench.main(["--live", "--budget-won", "5000"]) == 2  # 상한 1,000원을 못 넘긴다


def test_요청_아홉개를_돌리고_주간_호출만_센다():
    transport = bench.TimedTransport(post=_fake())
    budget = bench.Budget(transport, won=1000, max_calls=24)
    out = bench.report(transport, bench.run(transport, budget))

    assert (out["requests"], out["saved"], out["skipped_budget"]) == (9, 9, 0)
    # 부모 연간 · 월간은 mock 이라 호출이 없다 — 전송은 주간 9번뿐(수리 없음).
    assert out["calls"] == 9 and out["repaired"] == 0
    schemas = [c["schema"] for c in transport.calls]
    assert schemas.count("weekly_plan_proposal") == 5
    assert schemas.count("weekly_cell_proposal") == 4
    # 단가: 12k 입력 · 2k 출력 = ₩1.692 + ₩1.416 = ₩3.108 / 호출
    assert out["won"] == pytest.approx(9 * 3.108, abs=0.01)
    decision_b = next(r for r in out["results"] if "결정 B" in r["case"])
    assert decision_b["result"] == "SAVED"
    saturday = next(r for r in out["results"] if r["case"].endswith("토"))
    assert "SAT" in saturday["plan"]["operating_days"]
    # 문장은 --show-values 일 때만 나온다.
    assert all("value" not in c for c in saturday["plan"]["cells"].values())


def test_예산을_넘을_것_같으면_남은_요청을_하지_않는다():
    huge = {"prompt_tokens": 1_000_000, "completion_tokens": 600_000, "total_tokens": 1_600_000}
    transport = bench.TimedTransport(post=_fake(huge))  # 한 호출 ≈ ₩565
    budget = bench.Budget(transport, won=1000, max_calls=24)
    out = bench.report(transport, bench.run(transport, budget))

    assert out["calls"] == 1  # 첫 호출 뒤 「수리까지 하면 넘는다」로 멈춘다
    assert out["skipped_budget"] >= 1
    assert out["won"] < 1000
