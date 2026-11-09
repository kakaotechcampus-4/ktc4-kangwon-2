"""원 단위 설정 · 성품인사 · 양식 지우기는 원을 만든 교사만 한다 (ADR-087).

합류 승인이 없어(ADR-068) 원 이름만 알면 누구나 그 원 교사가 된다. 들어온 첫날 같은 원
모든 반에 쓰이는 설정을 바꾸거나 남이 올린 양식을 지우면 안 된다. 읽기는 연다.
"""

import pytest
from fastapi.testclient import TestClient

from app.features.auth.models import User
from app.features.centers import registry
from app.features.forms.models import Form
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)


def as_(user):
    app.dependency_overrides[current_user] = lambda: user


@pytest.fixture
def center(db_session):
    """같은 원(정부 목록 춘천 한 곳)에 먼저 만든 교사와 뒤에 들어온 교사."""

    def make(email):
        u = User(email=email, name=email[0], password_hash=b"x" * 64, password_salt=b"y" * 16)
        db_session.add(u)
        return u

    first, joiner = make("a@example.com"), make("b@example.com")
    db_session.flush()
    daycare = registry.search("강원특별자치도", "춘천시", "리틀빌리지")[0]
    body = {
        "name": daycare.name,
        "director_name": "김원장",
        "region_sido": daycare.sido,
        "region_sigungu": daycare.sigungu,
        "registry_key": daycare.key,
    }
    try:
        as_(first)
        center_id = client.post("/api/centers", json=body).json()["id"]
        as_(joiner)
        assert client.post("/api/centers", json=body).json()["joined"] is True
        yield {"id": center_id, "first": first, "joiner": joiner}
    finally:
        app.dependency_overrides.pop(current_user, None)


def _form(session, center_id, uploaded_by):
    form = Form(
        center_id=center_id,
        name="월간.hwpx",
        filename="월간.hwpx",
        tables=[],
        labels=[],
        label_map={},
        uploaded_by=uploaded_by,
    )
    session.add(form)
    session.flush()
    return form.id


def test_뒤에_들어온_교사는_원_설정을_못_바꾸고_읽기만_한다(center):
    as_(center["joiner"])
    url = f"/api/centers/{center['id']}/settings"

    response = client.put(url, json={"trends_enabled": True, "observation_axis": "DAILY_PLAY_2"})

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "CENTER_CREATOR_ONLY"
    read = client.get(url)
    assert read.status_code == 200
    assert read.json()["can_edit"] is False
    assert read.json()["trends_enabled"] is False
    assert read.json()["observation_axis"] == "NURI_5"


def test_원을_만든_교사는_원_설정을_바꾼다(center):
    as_(center["first"])
    url = f"/api/centers/{center['id']}/settings"

    response = client.put(url, json={"trends_enabled": True})

    assert response.status_code == 200, response.text
    assert response.json()["trends_enabled"] is True
    assert response.json()["can_edit"] is True


def test_뒤에_들어온_교사는_성품인사를_못_바꾸고_읽기만_한다(center):
    as_(center["joiner"])
    url = f"/api/centers/{center['id']}/greetings"
    body = {"enabled": True, "items": [{"month": m, "text": f"{m}월"} for m in range(1, 13)]}

    response = client.put(url, json=body)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "CENTER_CREATOR_ONLY"
    assert client.get(url).json()["enabled"] is False
    as_(center["first"])
    assert client.put(url, json=body).status_code == 200


def test_양식은_올린_교사와_원을_만든_교사만_지운다(db_session, center):
    first, joiner = center["first"], center["joiner"]
    by_first = _form(db_session, center["id"], first.id)
    by_joiner = _form(db_session, center["id"], joiner.id)
    unknown = _form(db_session, center["id"], None)  # 이 결정 전에 올린 양식

    as_(joiner)
    listed = client.get(f"/api/centers/{center['id']}/forms").json()["items"]
    assert {f["id"]: f["can_delete"] for f in listed} == {
        by_first: False,
        by_joiner: True,
        unknown: False,
    }
    for form_id in (by_first, unknown):
        response = client.delete(f"/api/forms/{form_id}")
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "CENTER_CREATOR_ONLY"
    assert client.delete(f"/api/forms/{by_joiner}").status_code == 204

    as_(first)
    assert client.delete(f"/api/forms/{unknown}").status_code == 204
    assert client.delete(f"/api/forms/{by_first}").status_code == 204


def test_뒤에_들어온_교사는_원_기본_양식을_못_바꾼다(center):
    """원 기본 월간 양식은 원 모든 반의 다음 월간에 걸린다 (§9-4)."""
    url = f"/api/centers/{center['id']}/template-profile-default"
    body = {"profile_ref": None, "expected_profile_ref": None}

    as_(center["joiner"])
    response = client.put(url, json=body)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "CENTER_CREATOR_ONLY"
    assert client.get(url).status_code == 200  # 읽기는 연다
    # 원을 만든 교사는 권한 검사를 지나 본문 검사까지 간다(바꿀 것 없는 본문이라 422).
    as_(center["first"])
    assert client.put(url, json=body).status_code == 422


def test_뒤에_들어온_교사는_원장_서류_체크를_못_바꾼다(center):
    """원장 서류 체크는 원 단위다 (ADR-074 결정 4)."""
    url = f"/api/centers/{center['id']}/evaluation-checklist"
    body = {"checks": [{"item": "annual-plan", "checked": True}]}

    as_(center["joiner"])
    response = client.put(url + "/director", json=body)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "CENTER_CREATOR_ONLY"
    assert not any(d["checked"] for d in client.get(url).json()["director"])
    as_(center["first"])
    assert client.put(url + "/director", json=body).status_code == 200
