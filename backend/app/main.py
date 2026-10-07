import logging
import sys
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.db import SessionLocal
from app.features.auth.models import User
from app.features.auth.router import router as auth_router
from app.features.centers.router import router as centers_router
from app.features.children.router import router as children_router
from app.features.documents.router import router as documents_router
from app.features.forms.router import center_router as center_forms_router
from app.features.forms.router import router as forms_router
from app.features.observations.router import router as observations_router
from app.features.plans.export import router as plans_export_router
from app.features.plans.router import router as plans_router
from app.features.routines.router import router as routines_router
from app.shared.auth.dependency import current_user


class _SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        # 기본 handleError 는 현재 예외 체인의 메시지까지 stderr 에 출력한다.
        raise


app = FastAPI(title="쌤플 API")
logger = logging.getLogger("app.server")
logger.propagate = False
if not logger.handlers:
    handler = _SafeStreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _one_line(value: str) -> str:
    return value.translate(
        str.maketrans({"\n": r"\n", "\r": r"\r", "\u2028": r"\u2028", "\u2029": r"\u2029"})
    )


def _request_context(scope: Scope) -> str:
    state = scope.get("state", {})
    return _one_line(
        f"method={scope['method']} path={scope['path']} "
        f"user_id={state.get('user_id', '-')} center_id={state.get('center_id', '-')}"
    )


def _exception_class(exc: Exception) -> str:
    return _one_line(f"{type(exc).__module__}.{type(exc).__name__}")


def _frames(exc: Exception) -> str:
    at = raised = "-"
    trace = exc.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        filename = "/" + code.co_filename.replace("\\", "/").lstrip("/")
        for marker in ("/site-packages/", "/app/", "/ssuksak/"):
            if marker in filename:
                filename = ("" if marker == "/site-packages/" else marker[1:]) + filename.rsplit(
                    marker, 1
                )[1]
                break
        else:
            filename = filename.rsplit("/", 1)[-1]
        raised = _one_line(f"{filename}:{trace.tb_lineno}:{code.co_name}")
        if filename.startswith(("app/", "ssuksak/")):
            at = raised
        trace = trace.tb_next
    return f"at={at}" + (f" raised={raised}" if raised != at else "")


def _logging_failed() -> None:
    try:
        logger.error("unexpected_error logging_failed")
    except Exception:
        try:
            sys.stderr.write("unexpected_error logging_failed\n")
        except Exception:
            pass


class _UnexpectedErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = failed = False

        async def track_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_start)
        except Exception as exc:
            # ADR-004: 예외 메시지·본문·쿼리·헤더에는 아동 실명이나 토큰이 섞일 수 있다.
            try:
                cause = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
                caused_by = f" caused_by={_exception_class(cause)}" if cause is not None else ""
                logger.error(
                    "unexpected_error %s error=%s%s %s%s",
                    _request_context(scope),
                    _exception_class(exc),
                    caused_by,
                    _frames(exc),
                    " response_started=true" if response_started else "",
                )
            except Exception:
                _logging_failed()
            failed = True  # except 밖에서 보내 원래 예외의 __context__ 연결을 막는다.
        if failed and not response_started:
            try:
                await PlainTextResponse("Internal Server Error", 500)(scope, receive, send)
            except Exception:
                pass


app.add_middleware(_UnexpectedErrorMiddleware)


def _authenticated_user(request: Request, user: Annotated[User, Depends(current_user)]) -> User:
    request.state.user_id = user.id
    request.state.center_id = user.center_id if user.center_id is not None else "-"
    return user


# docs/api-spec.md 가 계약이고 모든 엔드포인트가 /api 아래다.
# /health · /health/ready 는 배포 판정용이라 루트에 둔다.
#
# **인증은 라우터 단위로 한 번에 건다.** 엔드포인트마다 붙이면 새 API 를 만들 때
# 반드시 빠뜨리고, 빠뜨린 그 하나가 구멍이 된다.
#
#   auth    회원가입·로그인이라 열려 있어야 한다
#   forms   parse 만 연다. 업로드한 파일을 그대로 돌려줄 뿐 저장하지 않는다.
#           등록·목록·삭제(center_forms)는 원의 자산이라 막는다 (ADR-020)
#   나머지   원·반·아동·문서·관찰 기록·계획안. 아동 실명이 내려오므로 반드시 막는다
_authenticated = [Depends(_authenticated_user)]

app.include_router(auth_router, prefix="/api")
app.include_router(forms_router, prefix="/api")
app.include_router(centers_router, prefix="/api", dependencies=_authenticated)
app.include_router(children_router, prefix="/api", dependencies=_authenticated)
app.include_router(documents_router, prefix="/api", dependencies=_authenticated)
app.include_router(observations_router, prefix="/api", dependencies=_authenticated)
app.include_router(routines_router, prefix="/api", dependencies=_authenticated)
app.include_router(plans_router, prefix="/api", dependencies=_authenticated)
app.include_router(plans_export_router, prefix="/api", dependencies=_authenticated)
app.include_router(center_forms_router, prefix="/api", dependencies=_authenticated)


def _error(status_code: int, code: str, message: str, fields: list[str]) -> JSONResponse:
    """계약의 공통 에러 봉투 (docs/api-spec.md 「공통」). fields 는 항상 배열이다."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "fields": fields}},
    )


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI 기본 `{"detail": [...]}` 를 계약 형식으로 바꾼다.

    **첫 번째에서 멈추지 않고 전부 모은다** — FE 가 칸마다 표시할 수 있어야 한다.
    loc 의 body·query·path 접두사는 떼고, 점 표기로 위치를 가리킨다(months.3).
    """
    fields: list[str] = []
    for error in exc.errors():
        parts = [
            str(p)
            for p in error.get("loc", ())
            if p not in ("body", "query", "path", "header", "cookie")
        ]
        name = ".".join(parts)
        if name and name not in fields:
            fields.append(name)
    return _error(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "VALIDATION_FAILED",
        "입력값을 확인해주세요.",
        fields,
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> Response:
    """우리가 계약 형식으로 낸 HTTPException 만 공통 봉투로 내보낸다.

    detail 이 `{"code", "message", "fields"}` 인 것만 변환한다. forms 처럼 문자열 detail 을
    쓰는 기존 라우터는 지금 형식(`{"detail": ...}`)을 그대로 유지한다 — 계약에 없는 code 를
    지어내지 않고, 이번 범위 밖 엔드포인트의 응답도 바꾸지 않기 위해서다.
    내부 DB 예외처럼 우리가 내지 않은 오류는 unexpected_error 미들웨어가 다룬다.
    """
    detail = exc.detail
    if exc.status_code >= 500:
        try:
            logger.warning(
                "server_error status=%s code=%s %s",
                exc.status_code,
                _one_line(str(detail.get("code", "-"))) if isinstance(detail, dict) else "-",
                _request_context(request.scope),
            )
        except Exception:
            _logging_failed()
    if not isinstance(detail, dict) or "code" not in detail:
        return await http_exception_handler(request, exc)

    raw_fields = detail.get("fields", [])
    fields = [str(f) for f in raw_fields] if isinstance(raw_fields, list) else [str(raw_fields)]
    return _error(exc.status_code, str(detail["code"]), str(detail.get("message", "")), fields)


@app.get("/health")
def health() -> dict[str, str]:
    """프로세스가 살아 있나. DB 는 보지 않는다."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(response: Response) -> dict[str, str]:
    """DB 까지 붙나. 배포 성공 판정은 이쪽을 본다.

    /health 만 보면 DB 가 죽어도 배포가 성공으로 찍힌다.
    """
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "db": type(exc).__name__}
    return {"status": "ok", "db": "ok"}
