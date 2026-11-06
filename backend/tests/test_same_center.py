"""정부 어린이집 목록으로 같은 원에 들어가고, 승인하면 두 반이 서로 보인다 (ADR-068).

실제 DB 를 쓴다. 어린이집은 `resources/daycares/daycares.csv` 사본의 실제 한 곳(춘천)을 쓰고,
교사 · 반 · 아이 이름은 가명이다(CLAUDE.md 개인정보).
"""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.features.auth.models import User
from app.features.centers import registry
from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)
SIDO, SIGUNGU = "강원특별자치도", "춘천시"


def as_(user):
    app.dependency_overrides[current_user] = lambda: user


@pytest.fixture
def teachers(db_session):
    def make(email):
        u = User(email=email, name=email[0], password_hash=b"x" * 64, password_salt=b"y" * 16)
        db_session.add(u)
        return u

    first, second = make("a@example.com"), make("b@example.com")
    db_session.flush()
    try:
        yield first, second
    finally:
        app.dependency_overrides.pop(current_user, None)


def _daycare():
    found = registry.search(SIDO, SIGUNGU, "리틀빌리지")
    assert found, "사본에 춘천 리틀빌리지어린이집이 있어야 한다"
    return found[0]


def _join(daycare, director="김원장"):
    body = {
        # 이름 · 지역은 목록 값으로 바뀐다. 다르게 보내도 목록 값이 남는지 본다.
        "name": "아무 이름",
        "director_name": director,
        "region_sido": "서울특별시",
        "region_sigungu": "중구",
        "registry_key": daycare.key,
    }
    return client.post("/api/centers", json=body)


def test_그_시군구_목록에서_이름으로_찾고_앞부분이_맞는_곳이_먼저다(teachers):
    as_(teachers[0])
    response = client.get(
        "/api/daycares", params={"sido": SIDO, "sigungu": SIGUNGU, "q": "리틀 빌리지"}
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items[0]["name"] == "리틀빌리지어린이집"
    assert items[0]["teacher_count"] == 0
    assert all(SIGUNGU in item["address"] for item in items)


def test_목록에서_고르면_목록_값으로_원이_생긴다(db_session, teachers):
    as_(teachers[0])
    daycare = _daycare()

    response = _join(daycare)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["joined"] is False
    assert (body["name"], body["region_sido"], body["region_sigungu"]) == (
        daycare.name,
        SIDO,
        SIGUNGU,
    )
    assert (body["kind"], body["address"], body["teacher_count"]) == (
        daycare.kind,
        daycare.address,
        1,
    )
    assert db_session.get(Center, body["id"]).registry_key == daycare.key


def test_같은_원을_고른_두_번째_교사는_그_원으로_들어간다(db_session, teachers):
    first, second = teachers
    daycare = _daycare()
    as_(first)
    center_id = _join(daycare).json()["id"]

    as_(second)
    response = _join(daycare, director="다른원장")

    assert response.status_code == 200, response.text
    assert response.json()["joined"] is True
    assert response.json()["id"] == center_id
    assert second.center_id == center_id
    # 보낸 원장 이름은 쓰지 않는다 — 원 정보는 먼저 가입한 교사가 적은 그대로다.
    assert db_session.get(Center, center_id).director_name == "김원장"
    found = client.get(
        "/api/daycares", params={"sido": SIDO, "sigungu": SIGUNGU, "q": "리틀빌리지"}
    ).json()["items"][0]
    assert found["teacher_count"] == 2
    assert client.get(f"/api/centers/{center_id}").json()["teacher_count"] == 2


def test_목록에_없는_열쇠는_422(teachers):
    as_(teachers[0])
    response = client.post(
        "/api/centers",
        json={
            "name": "x",
            "director_name": "x",
            "region_sido": SIDO,
            "region_sigungu": SIGUNGU,
            "registry_key": "없는|열쇠",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["registry_key"]


def test_열쇠_없이_직접_적은_원은_따로_생긴다(db_session, teachers):
    as_(teachers[0])
    response = client.post(
        "/api/centers",
        json={
            "name": "새로연어린이집",
            "director_name": "김원장",
            "region_sido": SIDO,
            "region_sigungu": SIGUNGU,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["registry_key"] is None
    assert response.json()["kind"] is None


def _class(session, center_id, name, teacher):
    klass = Class(
        center_id=center_id,
        name=name,
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name=teacher.name,
        teacher_id=teacher.id,
        consent_confirmed_at=datetime.now(UTC),
    )
    session.add(klass)
    session.flush()
    session.add(Child(class_id=klass.id, name=f"가{name}", code=f"민{name}"))
    session.add(
        Document(
            kind="dailyLog",
            title="t",
            class_id=klass.id,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
            origin="AI",
        )
    )
    session.flush()
    return klass


def test_승인하면_두_반이_서로_보이고_취소하면_같이_닫힌다(db_session, teachers):
    first, second = teachers
    center = Center(name="원", director_name="김", region_sido=SIDO, region_sigungu=SIGUNGU)
    db_session.add(center)
    db_session.flush()
    first.center_id = second.center_id = center.id
    mine = _class(db_session, center.id, "달님반", first)
    theirs = _class(db_session, center.id, "햇살반", second)

    as_(second)
    request_id = client.post(f"/api/classes/{mine.id}/access-requests").json()["id"]
    as_(first)
    assert client.get(f"/api/classes/{theirs.id}/children").status_code == 403

    approved = client.patch(f"/api/access-requests/{request_id}", json={"status": "APPROVED"})
    assert approved.status_code == 200, approved.text
    # 승인한 쪽도 요청한 쪽 반을 본다.
    assert client.get(f"/api/classes/{theirs.id}/children").status_code == 200
    as_(second)
    assert client.get(f"/api/classes/{mine.id}/children").status_code == 200
    # 보기만 — 남의 반 아이 이름은 못 고친다.
    assert (
        client.post(f"/api/classes/{mine.id}/children", json={"name": "다새아"}).status_code == 403
    )

    as_(first)
    client.patch(f"/api/access-requests/{request_id}", json={"status": "REVOKED"})
    assert client.get(f"/api/classes/{theirs.id}/children").status_code == 403
    as_(second)
    assert client.get(f"/api/classes/{mine.id}/children").status_code == 403
