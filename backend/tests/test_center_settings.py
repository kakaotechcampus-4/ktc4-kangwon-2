"""원 설정 — 트렌드봇 켜고 끄기 (api-spec.md §3-1 · FR-808)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
CENTER = {
    "name": "설정 어린이집",
    "director_name": "김원장",
    "region_sido": "강원특별자치도",
    "region_sigungu": "춘천시",
}


@pytest.fixture
def own_center(db_session, teacher):
    response = client.post("/api/centers", json=CENTER)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_설정한_적_없으면_꺼짐을_채워_준다(own_center):
    """빈 객체를 주지 않는다. 화면이 「설정 없음」을 따로 그리지 않아도 된다."""
    response = client.get(f"/api/centers/{own_center}/settings")
    assert response.status_code == 200
    assert response.json() == {"trends_enabled": False}


def test_켜고_끌_수_있다(own_center):
    assert (
        client.put(f"/api/centers/{own_center}/settings", json={"trends_enabled": True}).json()
        == {"trends_enabled": True}
    )
    assert client.get(f"/api/centers/{own_center}/settings").json() == {"trends_enabled": True}
    assert (
        client.put(f"/api/centers/{own_center}/settings", json={"trends_enabled": False}).json()
        == {"trends_enabled": False}
    )


def test_빈_요청은_아무것도_바꾸지_않는다(own_center):
    """보낸 칸만 바꾼다. 토글이 늘어나도 서로를 덮지 않는다 (§3-1)."""
    client.put(f"/api/centers/{own_center}/settings", json={"trends_enabled": True})
    assert client.put(f"/api/centers/{own_center}/settings", json={}).json() == {
        "trends_enabled": True
    }


def test_참거짓이_아니면_422(own_center):
    response = client.put(f"/api/centers/{own_center}/settings", json={"trends_enabled": "yes"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_모르는_칸은_거절한다(own_center):
    response = client.put(f"/api/centers/{own_center}/settings", json={"trend_enabled": True})
    assert response.status_code == 422


def test_남의_원은_404(own_center, db_session):
    """없는 원과 남의 원을 구분하지 않는다 — 있는지 알려주는 것도 정보다."""
    assert client.get(f"/api/centers/{own_center + 999}/settings").status_code == 404
    assert (
        client.put(
            f"/api/centers/{own_center + 999}/settings", json={"trends_enabled": True}
        ).status_code
        == 404
    )


def test_null_은_422(own_center):
    """안 보낸 것과 null 을 보낸 것은 다르다.

    안 보내면 그 칸을 안 바꾼다. null 은 참/거짓이 아니므로 거절한다 —
    그냥 받으면 화면이 null 을 보내고도 저장됐다고 읽는다.
    """
    response = client.put(f"/api/centers/{own_center}/settings", json={"trends_enabled": None})
    assert response.status_code == 422
