from fastapi import FastAPI, Response, status
from sqlalchemy import text

from app.db import SessionLocal
from app.features.forms.router import router as forms_router

app = FastAPI(title="쓱싹요정 API")

# docs/api-spec.md 가 계약이고 모든 엔드포인트가 /api 아래다.
# /health · /health/ready 는 배포 판정용이라 루트에 둔다.
app.include_router(forms_router, prefix="/api")


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
