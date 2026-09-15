from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_does_not_touch_db():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_reports_ok_when_db_reachable():
    # 모의 없이 job 의 postgres 에 실제로 붙는다.
    # deploy.yml 의 HEALTHCHECK_URL 이 판정에 쓰는 응답이 이것이다.
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_ready_reports_503_when_db_unreachable(monkeypatch):
    # main.py 가 `from app.db import SessionLocal` 로 이름을 자기 네임스페이스에
    # 복사했다. app.db 를 패치하면 안 먹는다.
    def boom():
        raise RuntimeError("DB down")

    monkeypatch.setattr("app.main.SessionLocal", boom)
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "error"
    assert r.json()["db"] == "RuntimeError"  # type(exc).__name__ 이 실린다
