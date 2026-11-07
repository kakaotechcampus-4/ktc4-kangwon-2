"""반 수정 `PATCH /api/classes/{class_id}` 와 동의 전 아이 추가 막기 (api-spec §2 · §2-1, ADR-062).

실제 DB 를 쓴다. 계정은 DB 에 넣는다 — 반이 `users.id` 를 외래키로 가리킨다.
아동 이름은 가명이다 (CLAUDE.md 개인정보).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.features.auth.models import User
from app.features.centers.models import Center, Child, Class, ClassAccessRequest
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)


def as_(user):
    app.dependency_overrides[current_user] = lambda: user


@pytest.fixture
def world(db_session):
    def user(email, center):
        u = User(email=email, name=email[0], password_hash=b"x" * 64, password_salt=b"y" * 16)
        u.center_id = center.id
        db_session.add(u)
        return u

    def center(name):
        c = Center(name=name, director_name="김원장", region_sido="강원", region_sigungu="춘천시")
        db_session.add(c)
        db_session.flush()
        return c

    home, other = center("햇살어린이집"), center("다른어린이집")
    owner = user("owner@example.com", home)
    peer = user("peer@example.com", home)
    stranger = user("stranger@example.com", other)
    db_session.flush()
    mine = _class(home, "달님반", owner.id)
    sibling = _class(home, "별님반", owner.id)
    db_session.add_all([mine, sibling])
    # 커밋해 둔다. 이름 충돌 테스트의 rollback 이 이 세션의 미커밋 행까지 지운다.
    db_session.commit()
    as_(owner)
    try:
        yield {
            "owner": owner,
            "peer": peer,
            "stranger": stranger,
            "mine": mine,
            "sibling": sibling,
        }
    finally:
        app.dependency_overrides.pop(current_user, None)


def _class(center, name, teacher_id, consent=None):
    return Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=4,
        age_max=4,
        child_count=12,
        teacher_name="김",
        teacher_id=teacher_id,
        consent_confirmed_at=consent,
    )


def _patch(klass, body):
    return client.patch(f"/api/classes/{klass.id}", json=body)


def _row(db_session, klass):
    db_session.expire_all()
    return db_session.get(Class, klass.id)


def _error(response):
    return response.json()["error"]


# ── 이름 · 연령 · 담임 ───────────────────────────────────────────────────────
def test_이름을_고치면_ClassResponse_모양으로_200(db_session, world):
    response = _patch(world["mine"], {"name": "  해님반  "})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "해님반"
    assert body["my_access"] == "OWNER"
    assert set(body) == {
        "id",
        "center_id",
        "name",
        "school_year",
        "age_min",
        "age_max",
        "child_count",
        "teacher_name",
        "consent_confirmed_at",
        "created_at",
        "my_access",
    }
    assert _row(db_session, world["mine"]).name == "해님반"


def test_같은_원_같은_학년도에_같은_이름이면_409이고_행은_그대로(db_session, world):
    response = _patch(world["mine"], {"name": "별님반", "teacher_name": "박"})

    assert response.status_code == 409
    assert _error(response)["code"] == "ALREADY_EXISTS"
    assert _error(response)["fields"] == ["name"]
    row = _row(db_session, world["mine"])
    assert (row.name, row.teacher_name) == ("달님반", "김")


@pytest.mark.parametrize("name", ["   ", "", "가" * 51])
def test_이름이_비었거나_50자를_넘으면_422(world, name):
    response = _patch(world["mine"], {"name": name})

    assert response.status_code == 422
    assert _error(response)["fields"] == ["name"]


@pytest.mark.parametrize(
    "body",
    [{"age_min": 3}, {"age_max": 5}, {"age_min": 5, "age_max": 4}],
    ids=["min만", "max만", "min>max"],
)
def test_연령은_둘을_같이_보내고_min이_max를_넘지_않아야_한다(db_session, world, body):
    response = _patch(world["mine"], body)

    assert response.status_code == 422
    assert _error(response)["fields"] == ["age_min", "age_max"]
    row = _row(db_session, world["mine"])
    assert (row.age_min, row.age_max) == (4, 4)


@pytest.mark.parametrize(
    "body",
    [{"name": "", "age_min": 5, "age_max": 3}, {"name": "", "age_min": 3}],
    ids=["이름+min>max", "이름+한쪽만"],
)
def test_다른_칸이_틀려도_연령_관계_오류를_함께_돌려준다(db_session, world, body):
    # 서버는 첫 오류에서 멈추지 않는다(api-spec 「공통」). 생성(ClassCreate)과 같다.
    response = _patch(world["mine"], body)

    assert response.status_code == 422
    assert sorted(_error(response)["fields"]) == ["age_max", "age_min", "name"]


def test_연령_쌍을_보내면_바뀐다(db_session, world):
    response = _patch(world["mine"], {"age_min": 3, "age_max": 5})

    assert response.status_code == 200, response.text
    assert (response.json()["age_min"], response.json()["age_max"]) == (3, 5)
    row = _row(db_session, world["mine"])
    assert (row.age_min, row.age_max) == (3, 5)


def test_담임_이름만_바뀌고_반_주인은_그대로(db_session, world):
    response = _patch(world["mine"], {"teacher_name": "박선생"})

    assert response.status_code == 200, response.text
    row = _row(db_session, world["mine"])
    assert row.teacher_name == "박선생"
    assert row.teacher_id == world["owner"].id


@pytest.mark.parametrize("field", ["child_count", "school_year", "teacher_id"])
def test_계약에_없는_칸은_422(db_session, world, field):
    response = _patch(world["mine"], {field: 3})

    assert response.status_code == 422
    assert _error(response)["fields"] == [field]


def test_빈_본문은_아무것도_안_바꾸고_200(db_session, world):
    response = _patch(world["mine"], {})

    assert response.status_code == 200, response.text
    row = _row(db_session, world["mine"])
    assert (row.name, row.age_min, row.age_max, row.teacher_name, row.child_count) == (
        "달님반",
        4,
        4,
        "김",
        12,
    )


def test_null로_보낸_칸은_그대로다(db_session, world):
    body = {k: None for k in ("name", "age_min", "age_max", "teacher_name", "consent_confirmed")}

    response = _patch(world["mine"], body)

    assert response.status_code == 200, response.text
    row = _row(db_session, world["mine"])
    assert (row.name, row.age_min, row.age_max, row.teacher_name) == ("달님반", 4, 4, "김")
    assert row.consent_confirmed_at is None


# ── 동의 ─────────────────────────────────────────────────────────────────────
def test_동의를_켜면_시각이_들어가고_다시_켜도_처음_시각이다(db_session, world):
    first = _patch(world["mine"], {"consent_confirmed": True})
    assert first.status_code == 200, first.text
    stamp = _row(db_session, world["mine"]).consent_confirmed_at
    assert stamp is not None

    again = _patch(world["mine"], {"consent_confirmed": True})

    assert again.status_code == 200, again.text
    assert _row(db_session, world["mine"]).consent_confirmed_at == stamp
    assert again.json()["consent_confirmed_at"] == first.json()["consent_confirmed_at"]


def test_아이가_없으면_동의를_끌_수_있다(db_session, world):
    world["mine"].consent_confirmed_at = datetime.now(UTC)
    db_session.flush()

    response = _patch(world["mine"], {"consent_confirmed": False})

    assert response.status_code == 200, response.text
    assert response.json()["consent_confirmed_at"] is None
    assert _row(db_session, world["mine"]).consent_confirmed_at is None


def test_아이가_있으면_동의를_못_끄고_같이_보낸_칸도_안_바뀐다(db_session, world):
    stamp = datetime.now(UTC)
    world["mine"].consent_confirmed_at = stamp
    db_session.add(Child(class_id=world["mine"].id, name="가나", code="다라"))
    db_session.flush()

    response = _patch(world["mine"], {"name": "해님반", "consent_confirmed": False})

    assert response.status_code == 409
    assert _error(response)["code"] == "GATE_BLOCKED"
    assert _error(response)["fields"] == ["consent_confirmed"]
    row = _row(db_session, world["mine"])
    assert row.name == "달님반"
    assert row.consent_confirmed_at == stamp


# ── 권한 ─────────────────────────────────────────────────────────────────────
def test_승인된_교사는_읽기_전용이라_403(db_session, world):
    db_session.add(
        ClassAccessRequest(
            class_id=world["mine"].id, requester_id=world["peer"].id, status="APPROVED"
        )
    )
    db_session.flush()
    as_(world["peer"])

    response = _patch(world["mine"], {"name": "해님반"})

    assert response.status_code == 403
    assert _error(response)["code"] == "CLASS_READ_ONLY"
    assert _error(response)["fields"] == ["class_id"]


def test_승인_없는_같은_원_교사는_403(world):
    as_(world["peer"])

    response = _patch(world["mine"], {"name": "해님반"})

    assert response.status_code == 403
    assert _error(response)["code"] == "CLASS_ACCESS_REQUIRED"


def test_다른_원과_없는_반은_404(world):
    as_(world["stranger"])
    assert _patch(world["mine"], {"name": "해님반"}).status_code == 404
    as_(world["owner"])
    assert client.patch("/api/classes/999999", json={"name": "해님반"}).status_code == 404


# ── 동의 전 아이 추가 (§2-1) ─────────────────────────────────────────────────
def test_동의_확인_전인_반에는_아이를_못_넣는다(db_session, world):
    response = client.post(f"/api/classes/{world['mine'].id}/children", json={"name": "김하나"})

    assert response.status_code == 409
    assert _error(response)["code"] == "GATE_BLOCKED"
    assert _error(response)["fields"] == ["class_id"]
    assert db_session.query(Child).filter_by(class_id=world["mine"].id).count() == 0


def test_동의를_확인한_반에는_아이를_넣는다(db_session, world):
    assert _patch(world["mine"], {"consent_confirmed": True}).status_code == 200

    response = client.post(f"/api/classes/{world['mine'].id}/children", json={"name": "김하나"})

    assert response.status_code == 201, response.text
