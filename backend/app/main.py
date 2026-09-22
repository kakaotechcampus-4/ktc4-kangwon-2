from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import SessionLocal
from app.features.centers.router import router as centers_router
from app.features.forms.router import router as forms_router

app = FastAPI(title="쓱싹요정 API")

# docs/api-spec.md 가 계약이고 모든 엔드포인트가 /api 아래다.
# /health · /health/ready 는 배포 판정용이라 루트에 둔다.
app.include_router(forms_router, prefix="/api")
app.include_router(centers_router, prefix="/api")


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
    내부 DB 예외처럼 우리가 내지 않은 오류는 여기서 다루지 않는다(정책 미정).
    """
    detail = exc.detail
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
