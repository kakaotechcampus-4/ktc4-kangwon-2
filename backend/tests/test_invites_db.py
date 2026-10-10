"""초대 코드로 같은 원에 교사를 더한다 (docs/api-spec.md §1-1 · ADR-029). 실제 DB 를 쓴다.

초대 행이 `users.id` 를 외래키로 가리키므로 `teacher` fixture(세션 밖 객체) 대신
교사를 DB 에 넣고 쓴다.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.auth.models import User
from app.features.centers.models import Center, CenterInvite, Class
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)


@pytest.fixture
def people(db_session):
    def user(email):
        u = User(email=email, name="가명", password_hash=b"x" * 64, password_salt=b"y" * 16)
        db_session.add(u)
        return u

    def center(name):
        c = Center(name=name, director_name="김원장", region_sido="강원", region_sigungu="춘천시")
        db_session.add(c)
        db_session.flush()
        return c

    home, other = center("햇살어린이집"), center("다른어린이집")
    owner, newbie, stranger = user("a@example.com"), user("b@example.com"), user("c@example.com")
    owner.center_id, stranger.center_id = home.id, other.id
    db_session.add(
        Class(
            center_id=home.id,
            name="햇님반",
            school_year=2026,
            age_min=4,
            age_max=4,
            teacher_name="김",
        )
    )
    db_session.flush()
    try:
        yield {"home": home, "other": other, "owner": owner, "newbie": newbie, "stranger": stranger}
    finally:
        app.dependency_overrides.pop(current_user, None)


def as_(user):
    app.dependency_overrides[current_user] = lambda: user


def invite(center):
    response = client.post(f"/api/centers/{center.id}/invites")
    assert response.status_code == 201, response.text
    return response.json()


def join(code):
    return client.post("/api/centers/join", json={"code": code})


def test_invite_then_join_shares_classes(people):
    as_(people["owner"])
    body = invite(people["home"])
    assert len(body["code"]) == 10
    assert datetime.fromisoformat(body["expires_at"]) > datetime.now(UTC) + timedelta(days=6)

    as_(people["newbie"])
    # 대소문자·공백을 맞춰 준다. 단톡방에서 옮겨 적다 보면 섞인다.
    response = join(f"  {body['code'].lower()} ")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == people["home"].id
    assert people["newbie"].center_id == people["home"].id

    classes = client.get(f"/api/centers/{people['home'].id}/classes")
    assert [c["name"] for c in classes.json()["items"]] == ["햇님반"]


def test_code_is_single_use(people, db_session):
    as_(people["owner"])
    code = invite(people["home"])["code"]
    as_(people["newbie"])
    assert join(code).status_code == 200

    late = User(
        email="d@example.com", name="가명", password_hash=b"x" * 64, password_salt=b"y" * 16
    )
    db_session.add(late)
    db_session.flush()
    as_(late)
    response = join(code)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert late.center_id is None
    row = db_session.scalar(select(CenterInvite).where(CenterInvite.code == code))
    assert row.used_by == people["newbie"].id


def test_expired_and_unknown_codes_are_rejected(people, db_session):
    as_(people["owner"])
    code = invite(people["home"])["code"]
    row = db_session.scalar(select(CenterInvite).where(CenterInvite.code == code))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()

    as_(people["newbie"])
    for bad in (code, "NOSUCHCODE"):
        response = join(bad)
        assert response.status_code == 404
        assert response.json()["error"] == {
            "code": "NOT_FOUND",
            "message": "초대 코드가 없거나 만료됐습니다.",
            "fields": ["code"],
        }
    assert people["newbie"].center_id is None


def test_teacher_with_center_cannot_join(people):
    as_(people["owner"])
    code = invite(people["home"])["code"]
    as_(people["stranger"])
    response = join(code)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_EXISTS"
    assert people["stranger"].center_id == people["other"].id


def test_teacher_without_center_cannot_invite(people):
    as_(people["newbie"])
    response = client.post(f"/api/centers/{people['home'].id}/invites")
    assert response.status_code == 404


def test_cannot_invite_into_another_center(people, db_session):
    as_(people["stranger"])
    response = client.post(f"/api/centers/{people['home'].id}/invites")
    assert response.status_code == 404
    assert response.json()["error"]["fields"] == ["center_id"]
    assert db_session.scalars(select(CenterInvite)).all() == []


def test_join_rejects_empty_code(people):
    as_(people["newbie"])
    assert join("   ").status_code == 422
