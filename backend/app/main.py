from fastapi import FastAPI

app = FastAPI(title="쓱싹요정 API")

# feature router 는 여기서 app.include_router(...) 로 연결한다.


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
