"""설정 화면 성품인사 계약 · 실제 PostgreSQL 영속화 (api-spec.md §3)."""

import pytest
from fastapi.testclient import TestClient

from app.features.centers.greetings import default_greetings
from app.features.centers.models import Center, Greetings
from app.main import app

client = TestClient(app)
CENTER = {
    "name": "성품 어린이집",
    "director_name": "김원장",
    "region_sido": "충청북도",
    "region_sigungu": "충주시",
}


@pytest.fixture
def own_center(db_session, teacher):
    response = client.post("/api/centers", json=CENTER)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def payload(enabled=True):
    return {
        "enabled": enabled,
        "items": [{"month": month, "text": f"{month}월 문구"} for month in range(1, 13)],
    }


def test_최초_GET은_off와_기본_12개월을_반환한다(own_center):
    response = client.get(f"/api/centers/{own_center}/greetings")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json() == default_greetings().model_dump()
    assert all(item["text"] for item in response.json()["items"])
    assert {item["month"] for item in response.json()["items"]} == set(range(1, 13))


def test_12개월_활성화_저장후_다시_조회한다(own_center, db_session):
    body = payload()
    # 순서는 계약의 검증 대상이 아니다. 월만 각각 한 번 있어야 한다.
    body["items"].reverse()
    response = client.put(f"/api/centers/{own_center}/greetings", json=body)
    assert response.status_code == 200, response.text
    assert response.json() == body
    db_session.expire_all()
    assert db_session.get(Greetings, own_center).items == body["items"]
    assert client.get(f"/api/centers/{own_center}/greetings").json() == body


def test_전체_교체와_off_전환은_기존_문구를_보존한다(own_center, db_session):
    path = f"/api/centers/{own_center}/greetings"
    assert client.put(path, json=payload()).status_code == 200
    replacement = payload()
    replacement["items"][0]["text"] = "새 문구\n둘째 줄"
    replacement["items"][1]["text"] = ""  # 계약은 빈 문구를 금지하지 않는다.
    assert client.put(path, json=replacement).json() == replacement
    off = payload(False)
    for item in off["items"]:
        item["text"] = "이 값으로 덮어쓰면 안 됩니다."
    expected = {**replacement, "enabled": False}
    assert client.put(path, json=off).json() == expected
    db_session.expire_all()
    assert db_session.get(Greetings, own_center).enabled is False
    assert client.get(path).json() == expected


def test_최초_off_저장도_기본_문구를_지우지_않는다(own_center):
    path = f"/api/centers/{own_center}/greetings"
    expected = default_greetings().model_dump()
    assert client.put(path, json=payload(False)).json() == expected
    assert client.get(path).json() == expected


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    ("invalid", "fields"),
    [
        ([], ["items"]),
        (payload()["items"][:-1], ["items"]),
        (payload()["items"] + [{"month": 1, "text": "추가"}], ["items"]),
        ([{"month": 1, "text": "중복"}] * 12, ["items"]),
        *[
            ([{"month": month, "text": "잘못된 월"}, *payload()["items"][1:]], ["items"])
            for month in [0, 13, "1", True, 1.5]
        ],
        ([{"month": 1, "text": None}, *payload()["items"][1:]], ["items.1.text"]),
    ],
)
def test_잘못된_month_items는_422이며_기존값을_유지한다(own_center, invalid, fields, enabled):
    path = f"/api/centers/{own_center}/greetings"
    before = payload()
    client.put(path, json=before)
    response = client.put(path, json={"enabled": enabled, "items": invalid})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["fields"] == fields
    assert client.get(path).json() == before


@pytest.mark.parametrize("enabled", [True, False])
def test_항목_오류는_월로_표시하고_식별할_수_없는_월도_함께_모은다(own_center, enabled):
    body = payload(enabled)
    body["items"].reverse()
    body["items"][0]["text"] = None  # 12월. 배열 인덱스 0을 쓰면 안 된다.
    body["items"][1]["month"] = 13  # 유효한 월이 없으므로 items 전체를 가리킨다.
    body["items"][-1]["text"] = None  # 1월. 배열 인덱스 11을 쓰면 안 된다.
    response = client.put(f"/api/centers/{own_center}/greetings", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["items.12.text", "items", "items.1.text"]


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_남의_원과_없는_원은_동일한_404다(own_center, db_session, method):
    other = Center(**{**CENTER, "name": "다른 원"})
    db_session.add(other)
    db_session.flush()
    original = payload()
    db_session.add(Greetings(center_id=other.id, **original))
    db_session.flush()
    for center_id in [other.id, 999999]:
        response = client.request(
            method,
            f"/api/centers/{center_id}/greetings",
            **({"json": payload(False)} if method == "PUT" else {}),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    assert db_session.get(Greetings, other.id).items == original["items"]
    assert db_session.get(Greetings, other.id).enabled is True


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_미인증은_401다(db_session, method):
    response = client.request(
        method,
        "/api/centers/1/greetings",
        **({"json": payload()} if method == "PUT" else {}),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_원번호만_일치해도_실제_없는_원은_404다(db_session, teacher):
    teacher.center_id = 999999
    for method in ["GET", "PUT"]:
        response = client.request(
            method,
            "/api/centers/999999/greetings",
            **({"json": payload()} if method == "PUT" else {}),
        )
        assert response.status_code == 404


def test_성품인사_문구는_80자를_넘기면_거부한다(own_center):
    """저장소가 JSONB 라 DB 가 길이를 막아 주지 않는다. 여기서 안 막으면 아무 데서도 안 막힌다."""
    body = payload()
    body["items"][0]["text"] = "ㄱ" * 81

    response = client.put(f"/api/centers/{own_center}/greetings", json=body)

    assert response.status_code == 422
    # 서버가 월 순서로 다시 세어 자리를 매긴다. 몇 번째인지가 아니라 그 칸이 지목됐는지를 본다.
    assert any(field.endswith(".text") for field in response.json()["error"]["fields"])


def test_성품인사_문구의_앞뒤_공백은_털어서_저장한다(own_center):
    """공백만 든 값은 빈 값과 같은 것으로 저장된다.

    §3 은 빈 문구를 금지하지 않는다 — 그 달에 성품인사를 안 쓰는 원이 칸을 비운다.
    다만 「공백 세 칸」과 「빈 칸」이 화면에서 같아 보이는데 저장된 값이 다르면 안 된다.

    `enabled: true` 로 보낸다 — `false` 면 서버가 items 를 무시한다(§3).
    """
    body = payload()
    body["items"][0]["text"] = "  앞뒤 공백  "
    body["items"][1]["text"] = "   "
    first, second = body["items"][0]["month"], body["items"][1]["month"]

    assert client.put(f"/api/centers/{own_center}/greetings", json=body).status_code == 200
    saved = {
        item["month"]: item["text"]
        for item in client.get(f"/api/centers/{own_center}/greetings").json()["items"]
    }
    assert saved[first] == "앞뒤 공백"
    assert saved[second] == ""
