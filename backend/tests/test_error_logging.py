import asyncio
import logging

import pytest
from fastapi import Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.background import BackgroundTask

import app.main as main
from app.db import engine
from app.main import app

PATH = "/__test_error_logging__"


@pytest.fixture
def client(caplog, monkeypatch):
    routes = list(app.router.routes)
    # _schema 의 Alembic fileConfig 가 기존 앱 로거를 끄는 테스트 간 간섭을 격리한다.
    monkeypatch.setattr(main.logger, "disabled", False)
    caplog.set_level(logging.WARNING)
    main.logger.addHandler(caplog.handler)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.router.routes[:] = routes
        main.logger.removeHandler(caplog.handler)


def server_records(caplog):
    return [record for record in caplog.records if record.name == "app.server"]


@pytest.mark.parametrize("send_error", [OSError("김가명 연결 끊김"), asyncio.CancelledError()])
def test_500_send_failure_does_not_chain_private_error(caplog, capsys, monkeypatch, send_error):
    async def fail(scope, receive, send):
        raise RuntimeError("김가명 처리 실패")

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        raise send_error

    monkeypatch.setattr(main.logger, "disabled", False)
    monkeypatch.setattr(main.logger, "handlers", [*main.logger.handlers, caplog.handler])
    scope = {"type": "http", "method": "GET", "path": PATH}
    try:
        asyncio.run(main._UnexpectedErrorMiddleware(fail)(scope, receive, send))
    except asyncio.CancelledError as exc:
        assert exc.__context__ is None
    assert "김가명" not in caplog.text + "".join(capsys.readouterr())


def test_unexpected_error_contains_only_safe_metadata(client, caplog):
    async def fail(request: Request):
        body = await request.json()
        raise RuntimeError(f"{body['name']} 처리 실패")

    app.add_api_route(PATH, fail, methods=["POST"])
    response = client.post(
        PATH,
        params={"q": "김가명", "marker": "private-query-value"},
        json={"name": "김가명"},
        headers={b"Authorization": "Bearer 비밀토큰xyz".encode()},
    )
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    records = server_records(caplog)
    assert main.logger.propagate is False
    assert len(records) == 1 and records[0].levelno == logging.ERROR
    message = records[0].getMessage()
    for expected in (
        "unexpected_error",
        "method=POST",
        f"path={PATH}",
        "user_id=- center_id=-",
        "error=builtins.RuntimeError",
        "at=",
    ):
        assert expected in message
    assert "caused_by=" not in message
    assert records[0].exc_info is None
    assert "김가명" not in caplog.text and "비밀토큰xyz" not in caplog.text
    assert "?q=" not in caplog.text
    assert "private-query-value" not in caplog.text


def test_authenticated_error_records_identity(client, caplog, teacher):
    def fail():
        raise RuntimeError("김가명")

    teacher.center_id = 7
    app.add_api_route(PATH, fail, dependencies=main._authenticated)
    assert client.get(PATH).status_code == 500
    assert "user_id=1 center_id=7" in server_records(caplog)[0].getMessage()


@pytest.mark.parametrize("failure", ["cleanup", "stream", "background"])
def test_errors_after_response_started_do_not_escape(client, caplog, failure):
    async def cleanup():
        yield
        raise RuntimeError("김가명 정리 실패")

    async def stream():
        yield b"ok"
        raise RuntimeError("김가명 스트리밍 실패")

    async def background():
        raise RuntimeError("김가명 백그라운드 실패")

    async def respond():
        if failure == "stream":
            return StreamingResponse(stream())
        return PlainTextResponse(
            "ok", background=BackgroundTask(background) if failure == "background" else None
        )

    dependencies = [Depends(cleanup)] if failure == "cleanup" else []
    app.add_api_route(PATH, respond, dependencies=dependencies)
    assert client.get(PATH).status_code == 200
    records = server_records(caplog)
    assert len(records) == 1 and records[0].levelno == logging.ERROR
    assert "response_started=true" in records[0].getMessage()
    assert "error=builtins.RuntimeError" in records[0].getMessage()
    assert records[0].exc_info is None and "김가명" not in caplog.text


@pytest.mark.parametrize("status", [404, 422, 503])
@pytest.mark.parametrize("structured", [False, True])
def test_http_errors_log_only_server_metadata(client, caplog, status, structured):
    detail = (
        {"code": "DEPENDENCY_UNAVAILABLE", "message": "김가명 변환기 없음", "fields": []}
        if structured
        else "김가명 변환기 없음"
    )

    def fail():
        raise HTTPException(status, detail=detail)

    app.add_api_route(PATH, fail)
    response = client.get(PATH)
    assert response.status_code == status
    assert response.json() == ({"error": detail} if structured else {"detail": detail})
    records = server_records(caplog)
    if status < 500:
        assert records == []
    else:
        assert len(records) == 1 and records[0].levelno == logging.WARNING
        code = "DEPENDENCY_UNAVAILABLE" if structured else "-"
        assert f"server_error status=503 code={code} method=GET path={PATH}" in caplog.text
    assert "김가명" not in caplog.text


def test_request_validation_error_is_not_logged(client, caplog):
    def validate(count: int):
        return count

    app.add_api_route(PATH, validate)
    assert client.get(PATH).status_code == 422
    assert server_records(caplog) == []


@pytest.mark.parametrize("cause", ["explicit", "implicit"])
def test_causes_are_metadata_only(client, caplog, cause):
    def fail():
        try:
            raise ValueError("김가명 원인")
        except ValueError as exc:
            if cause == "explicit":
                raise RuntimeError("김가명 오류") from exc
            raise RuntimeError("김가명 오류")  # noqa: B904 - 암묵적 원인도 메시지 없이 남긴다.

    app.add_api_route(PATH, fail)
    assert client.get(PATH).status_code == 500
    message = server_records(caplog)[0].getMessage()
    assert "caused_by=builtins.ValueError" in message
    assert "at=app/main.py:" in message and " raised=test_error_logging.py:" in message
    assert "김가명" not in caplog.text


@pytest.mark.parametrize(
    "package,library",
    [("app", True), ("ssuksak", False), ("tests", True), ("site-packages/vendor/app", True)],
)
@pytest.mark.parametrize("prefix", ["/repo/", ""])
def test_frames_keep_our_innermost_location(package, library, prefix):
    namespace = {}
    exec(
        compile(
            'def library():\n    raise RuntimeError("김가명 오류")',
            "/repo/site-packages/vendor.py",
            "exec",
        ),
        namespace,
    )
    body = "library()" if library else 'raise RuntimeError("김가명 오류")'
    exec(compile(f"def fail():\n    {body}", f"{prefix}{package}/source.py", "exec"), namespace)
    with pytest.raises(RuntimeError) as error:
        namespace["fail"]()
    at = f"{package}/source.py:2:fail" if package in ("app", "ssuksak") else "-"
    raised = "vendor.py:2:library" if library else at
    assert main._frames(error.value) == f"at={at}" + (f" raised={raised}" if raised != at else "")


def test_logging_failure_still_returns_500(client, caplog, capsys, monkeypatch):
    def logging_failure(*args, **kwargs):
        raise RuntimeError("김가명 비밀토큰xyz 처리 실패")

    monkeypatch.setattr(main.handler.formatter, "format", logging_failure)
    app.add_api_route(PATH, lambda: logging_failure())
    assert (res := client.get(PATH)).status_code == 500 and res.text == "Internal Server Error"
    captured = caplog.text + capsys.readouterr().err
    assert "unexpected_error logging_failed" in captured
    assert "김가명" not in captured and "비밀토큰xyz" not in captured


def test_path_controls_cannot_create_log_lines(client, caplog):
    def fail():
        raise RuntimeError("김가명")

    app.add_api_route(PATH + "\u2028private-path", fail)
    assert client.get(PATH + "%E2%80%A8private-path").status_code == 500
    message = server_records(caplog)[0].getMessage()
    assert "\\u2028private-path" in message and "\u2028" not in message


def test_database_error_hides_parameters(_schema):
    with engine.connect() as connection, pytest.raises(IntegrityError) as error:
        connection.execute(
            text(
                "INSERT INTO forms (center_id, name, filename, tables, labels, label_map) "
                "VALUES (:center_id, :name, :filename, '[]', '[]', '{}')"
            ),
            {"center_id": 999999, "name": "김가명", "filename": "sample.hwp"},
        )
    message = str(error.value)
    assert "김가명" not in message and "[parameters:" not in message
