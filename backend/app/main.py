from fastapi import FastAPI

from app.features.forms.router import router as forms_router

app = FastAPI(title="쓱싹요정 API")

app.include_router(forms_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
