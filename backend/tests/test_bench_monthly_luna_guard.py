"""월간 bench 의 실제 호출 가드 — 서버(IS_SERVER=1)가 아니면 전송을 만들지 않는다.

실제 엘리스를 부르지 않는다. 진짜 urlopen 은 불리면 실패하도록 바꿔 끼운다.
"""

import importlib.util
from pathlib import Path
from urllib import request as urllib_request

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bench_monthly_luna.py"
_spec = importlib.util.spec_from_file_location("bench_monthly_luna", _PATH)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("실제 네트워크 호출")

    monkeypatch.setattr(urllib_request, "urlopen", refuse)
    monkeypatch.setattr(bench.urllib_request, "urlopen", refuse)


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", " 0 "])
def test_서버가_아니면_실제_전송을_만들지_않는다(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("IS_SERVER", raising=False)
    else:
        monkeypatch.setenv("IS_SERVER", value)
    monkeypatch.setenv("ELICE_MLAPI_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("ELICE_MLAPI_API_KEY", "test-only-not-a-key")

    assert not bench.on_server()
    with pytest.raises(RuntimeError, match="IS_SERVER"):
        bench.TimedTransport()
    assert bench.main(["--live"]) == 2


@pytest.mark.parametrize("value", ["1", "true", "TRUE"])
def test_서버에서만_실제_전송을_허용한다(monkeypatch, value):
    monkeypatch.setenv("IS_SERVER", value)
    assert bench.on_server()
    bench.TimedTransport()  # 만들기만 한다 — 부르지 않는다


def test_가짜_전송은_로컬에서도_쓸_수_있고_live_없이는_부르지_않는다(monkeypatch):
    monkeypatch.delenv("IS_SERVER", raising=False)
    assert bench.TimedTransport(post=lambda *a, **k: None).calls == []
    assert bench.main([]) == 2
