from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_does_not_touch_db():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_reports_503_when_db_unreachable():
    # conftest 가 DATABASE_URL 을 못 붙는 주소로 박아둔다.
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "error"
