"""PLAY_PROJECT 의 SSE 전송. 진짜 엘리스는 부르지 않는다."""

import json
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from ssuksak.adapters.elice_openai_monthly import MonthlyLlmProviderError

from app.config import settings
from app.features.plans import monthly_llm
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable
from app.shared.llm import client as llm

BASE = "https://mlapi.example.com/v1"
USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}


class _Response:
    def __init__(self, status, lines):
        self.status = status
        self.lines = iter(lines)

    def readline(self):
        return next(self.lines, b"")


def _connection(monkeypatch, lines=(), status=200):
    connections = []

    class FakeConnection:
        def __init__(self, host, port, timeout):
            self.sock = object()
            self.response = _Response(status, lines)
            connections.append(self)

        def request(self, method, path, *, body, headers):
            self.requested = method, path, body, headers

        def getresponse(self):
            return self.response

        def close(self):
            self.closed = True

    monkeypatch.setattr(llm.http.client, "HTTPSConnection", FakeConnection)
    return connections


@pytest.fixture
def usage_lines(monkeypatch):
    monkeypatch.setattr(settings, "is_server", True)
    lines = []
    monkeypatch.setattr(llm.logger, "info", lambda fmt, *args: lines.append(fmt % args))
    return lines


def _sse(content, *, usage=USAGE):
    chunks = [
        {"choices": [{"delta": {"content": content}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": usage},
    ]
    return [f"data: {json.dumps(chunk)}\n\n".encode() for chunk in chunks]


def _post_stream(**kwargs):
    return llm.post_stream(
        f"{BASE}/chat/completions",
        headers={},
        payload={"model": "test-model"},
        timeout=30,
        fold=lambda lines: {"lines": list(lines)},
        deadline=kwargs.get("deadline", 120),
    )


@contextmanager
def _local_server(monkeypatch, *, body=b"", trickle=False):
    monkeypatch.setattr(llm.http.client, "HTTPSConnection", llm.http.client.HTTPConnection)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if trickle:
                time.sleep(0.25)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                if trickle:
                    for _ in range(50):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.1)
                else:
                    self.wfile.write(body)
                    self.wfile.flush()
            except OSError:
                pass

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/chat/completions"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_valid_sse_returns_assembled_content_and_logs_usage_once(monkeypatch, usage_lines):
    content = '{"period_key":"m03_m05","rows":[]}'
    _connection(monkeypatch, [*_sse(content), b"data: [DONE]\n\n"])

    result = monthly_llm.SharedLlmTransport().post_stream(
        f"{BASE}/chat/completions",
        headers={},
        payload={"model": "test-model", "response_format": {"json_schema": {"name": "play"}}},
        timeout=30,
    )

    assert result["choices"][0]["message"]["content"] == content
    assert usage_lines == ["llm_usage model=test-model prompt=120 completion=30 total=150"]


@pytest.mark.parametrize(("status", "error"), [(429, LlmBudgetExceeded), (500, LlmFailed)])
def test_http_status_is_mapped(monkeypatch, usage_lines, status, error):
    _connection(monkeypatch, status=status)

    with pytest.raises(error):
        _post_stream()
    assert usage_lines == []


def test_local_real_is_blocked_before_open(monkeypatch, usage_lines):
    monkeypatch.setattr(settings, "is_server", False)
    monkeypatch.setattr(
        llm.http.client,
        "HTTPSConnection",
        lambda *args, **kwargs: pytest.fail("로컬에서 연결하면 안 된다"),
    )

    with pytest.raises(LlmUnavailable):
        _post_stream()


def test_missing_done_propagates_core_error_without_usage(monkeypatch, usage_lines):
    _connection(monkeypatch, _sse('{"period_key":"m03_m05","rows":[]}'))

    with pytest.raises(MonthlyLlmProviderError, match="before \\[DONE\\]"):
        monthly_llm.SharedLlmTransport().post_stream(
            f"{BASE}/chat/completions",
            headers={},
            payload={"model": "test-model", "response_format": {}},
            timeout=30,
        )
    assert usage_lines == []


def test_deadline_aborts_a_trickling_read(monkeypatch, usage_lines):
    monkeypatch.setattr(settings, "is_server", True)
    with _local_server(monkeypatch, trickle=True) as url:
        started = time.perf_counter()

        # 0.1초마다 바이트가 와서 소켓 읽기 제한(0.5초)은 끝나지 않고 watchdog만 읽기를 끝낸다.
        with pytest.raises(LlmFailed, match="제한 시간"):
            llm.post_stream(
                url,
                headers={},
                payload={"model": "test-model"},
                timeout=30,
                fold=lambda lines: {"lines": list(lines)},
                deadline=0.5,
            )

        assert time.perf_counter() - started < 2.0


def test_close_delimited_response_keeps_socket_and_logs_usage(monkeypatch, usage_lines):
    monkeypatch.setattr(settings, "is_server", True)
    content = '{"period_key":"m03_m05","rows":[]}'
    body = b"".join([*_sse(content), b"data: [DONE]\n\n"])
    with _local_server(monkeypatch, body=body) as url:
        result = monthly_llm.SharedLlmTransport().post_stream(
            url,
            headers={},
            payload={"model": "test-model", "response_format": {}},
            timeout=30,
        )

    assert result["choices"][0]["message"]["content"] == content
    assert usage_lines == ["llm_usage model=test-model prompt=120 completion=30 total=150"]
