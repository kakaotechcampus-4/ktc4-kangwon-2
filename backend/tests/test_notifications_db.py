"""상단바 알림함 — 열람 요청 · 결과 알림과 읽음 처리 (docs/api-spec.md 「알림함」).

실제 DB 를 쓴다. 알림은 `class_access_requests` 를 외래키로 가리키고, 요청은 `users` 를 가리킨다.
모델 클래스를 import 하지 않는다 — 계약(표 이름 · 칸 이름 · 응답 모양)만 보고 쓴다.

테스트는 바깥 트랜잭션 하나 안에서 돈다(conftest `db_session`). 그 안에서 Postgres `now()` 는 늘
같은 값이라, 「덮지 않음」은 시각을 미리 박아 두고 확인하고 정렬은 id 로만 본다.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.features.auth.models import User
from app.features.centers.models import Center, Class
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)
API = "/api/me/notifications"
FIELDS = {
    "id",
    "kind",
    "request_id",
    "class_id",
    "class_name",
    "requester_name",
    "created_at",
    "read_at",
}
EARLIER = datetime(2026, 1, 1, tzinfo=UTC)


def as_(user):
    app.dependency_overrides[current_user] = lambda: user


@pytest.fixture
def world(db_session):
    """같은 원: 주인(달님반) · 반 없는 요청자 · 반 있는 요청자(해님반).

    그 밖에 다른 원 교사와 원 없는 교사.
    """

    def center(name):
        c = Center(name=name, director_name="김원장", region_sido="강원", region_sigungu="춘천시")
        db_session.add(c)
        db_session.flush()
        return c

    def user(email, name, home):
        u = User(email=email, name=name, password_hash=b"x" * 64, password_salt=b"y" * 16)
        u.center_id = home.id if home else None
        db_session.add(u)
        return u

    def klass(home, name, teacher):
        return Class(
            center_id=home.id,
            name=name,
            school_year=2026,
            age_min=4,
            age_max=4,
            teacher_name=teacher.name,
            teacher_id=teacher.id,
        )

    home, other = center("햇살어린이집"), center("다른어린이집")
    owner = user("owner@example.com", "김주인", home)
    peer = user("peer@example.com", "이요청", home)
    peer2 = user("peer2@example.com", "박맞반", home)
    stranger = user("stranger@example.com", "최남원", other)
    lonely = user("lonely@example.com", "정혼자", None)
    db_session.flush()
    mine, theirs = klass(home, "달님반", owner), klass(home, "해님반", peer2)
    db_session.add_all([mine, theirs])
    db_session.flush()
    try:
        yield {
            "owner": owner,
            "peer": peer,
            "peer2": peer2,
            "stranger": stranger,
            "lonely": lonely,
            "mine": mine,
            "theirs": theirs,
        }
    finally:
        app.dependency_overrides.pop(current_user, None)


def _ask(user, classroom):
    as_(user)
    return client.post(f"/api/classes/{classroom.id}/access-requests")


def _decide(user, request_id, status):
    as_(user)
    response = client.patch(f"/api/access-requests/{request_id}", json={"status": status})
    assert response.status_code == 200, response.text
    return response


def _items(user):
    as_(user)
    response = client.get(API)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _read(user, body):
    as_(user)
    return client.post(f"{API}/read", json=body)


# ── 만들어지는 알림 ──────────────────────────────────────────────────────────
def test_첫_요청은_201_이고_주인에게_안_읽은_알림_하나가_생긴다(world):
    response = _ask(world["peer"], world["mine"])
    assert response.status_code == 201, response.text
    [item] = _items(world["owner"])
    assert set(item) == FIELDS
    assert item["kind"] == "ACCESS_REQUESTED"
    assert item["request_id"] == response.json()["id"]
    assert (item["class_id"], item["class_name"]) == (world["mine"].id, "달님반")
    assert item["requester_name"] == "이요청"
    assert item["read_at"] is None
    assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
    # 요청한 쪽은 자기 요청으로 알림을 받지 않는다.
    assert _items(world["peer"]) == []


@pytest.mark.parametrize(
    "steps, kinds",
    [
        (["APPROVED"], ["ACCESS_APPROVED"]),
        (["REJECTED"], ["ACCESS_REJECTED"]),
        (["APPROVED", "REVOKED"], ["ACCESS_REVOKED", "ACCESS_APPROVED"]),
    ],
)
def test_승인_거절_취소는_요청자에게_하나씩_간다(world, steps, kinds):
    # 요청자(peer)에게 반이 없어 맞승인(_mirror)이 끼지 않는다.
    request_id = _ask(world["peer"], world["mine"]).json()["id"]
    for step in steps:
        _decide(world["owner"], request_id, step)
    items = _items(world["peer"])
    assert [i["kind"] for i in items] == kinds
    for i in items:
        assert (i["request_id"], i["class_id"], i["class_name"]) == (
            request_id,
            world["mine"].id,
            "달님반",
        )
        assert i["requester_name"] == "이요청"
        assert i["read_at"] is None
    # 결과 알림은 요청자에게만 간다 — 주인에게는 처음 받은 요청 하나뿐이다.
    assert [i["kind"] for i in _items(world["owner"])] == ["ACCESS_REQUESTED"]


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_보관함에서_승인_거절하면_주인의_요청_알림이_읽음이_된다(world, decision):
    request_id = _ask(world["peer"], world["mine"]).json()["id"]
    assert _items(world["owner"])[0]["read_at"] is None
    _decide(world["owner"], request_id, decision)
    [item] = _items(world["owner"])
    assert (item["kind"], item["request_id"]) == ("ACCESS_REQUESTED", request_id)
    assert item["read_at"] is not None


def test_맞승인으로_열린_반대_요청의_알림도_읽음이_되고_새_알림은_없다(world):
    # 주인이 먼저 peer2 의 해님반을 청해 두었다 → peer2 에게 안 읽은 요청 알림.
    back_id = _ask(world["owner"], world["theirs"]).json()["id"]
    request_id = _ask(world["peer2"], world["mine"]).json()["id"]
    assert [(i["kind"], i["request_id"], i["read_at"]) for i in _items(world["peer2"])] == [
        ("ACCESS_REQUESTED", back_id, None)
    ]
    # 주인이 peer2 의 요청을 승인하면 _mirror 가 주인의 해님반 요청(back)도 APPROVED 로 연다.
    _decide(world["owner"], request_id, "APPROVED")
    items = _items(world["peer2"])
    assert [(i["kind"], i["request_id"]) for i in items] == [
        ("ACCESS_APPROVED", request_id),
        ("ACCESS_REQUESTED", back_id),
    ]
    assert items[0]["read_at"] is None
    assert items[1]["read_at"] is not None
    # 거울로 열린 줄은 알리지 않는다 — 주인에게 ACCESS_APPROVED 가 없다.
    owner_items = _items(world["owner"])
    assert [(i["kind"], i["request_id"]) for i in owner_items] == [("ACCESS_REQUESTED", request_id)]
    assert owner_items[0]["read_at"] is not None


@pytest.mark.parametrize("closing", [["REJECTED"], ["APPROVED", "REVOKED"]])
def test_거절_취소_뒤_다시_요청하면_주인에게_새_안_읽은_알림이_하나_생긴다(world, closing):
    request_id = _ask(world["peer"], world["mine"]).json()["id"]
    for step in closing:
        _decide(world["owner"], request_id, step)
    again = _ask(world["peer"], world["mine"])
    assert again.status_code == 201, again.text
    assert again.json()["id"] == request_id
    items = _items(world["owner"])
    assert [(i["kind"], i["request_id"]) for i in items] == [("ACCESS_REQUESTED", request_id)] * 2
    assert [i["read_at"] is None for i in items] == [True, False]


# ── 읽음 처리 ────────────────────────────────────────────────────────────────
def test_읽음으로_보내면_204_이고_read_at_이_채워진다(world):
    _ask(world["peer"], world["mine"])
    [item] = _items(world["owner"])
    response = _read(world["owner"], {"ids": [item["id"]]})
    assert response.status_code == 204, response.text
    assert response.content == b""
    [after] = _items(world["owner"])
    assert after["read_at"] is not None


def test_이미_읽은_알림은_read_at_을_덮지_않는다(db_session, world):
    _ask(world["peer"], world["mine"])
    [item] = _items(world["owner"])
    db_session.execute(
        text("UPDATE notifications SET read_at = :at WHERE id = :id"),
        {"at": EARLIER, "id": item["id"]},
    )
    # 앞 GET 이 세션에 올려 둔 객체가 옛 read_at 을 들고 있지 않게 한다.
    db_session.expire_all()
    assert _read(world["owner"], {"ids": [item["id"]]}).status_code == 204
    [after] = _items(world["owner"])
    assert datetime.fromisoformat(after["read_at"]) == EARLIER


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"ids": []},
        {"ids": list(range(1, 32))},
        {"ids": [1], "all": True},
        {"ids": [0]},
        {"ids": [-1]},
        {"ids": "1"},
        {"ids": [2**31]},  # id 칸이 INTEGER 라 그보다 크면 DB 가 500 을 낸다
    ],
    ids=["본문없음", "칸없음", "빈배열", "31개", "모르는칸", "0", "음수", "배열아님", "INT초과"],
)
def test_읽음_본문이_없거나_비거나_31개거나_모르는_칸이면_422(world, body):
    as_(world["owner"])
    path = f"{API}/read"
    response = client.post(path) if body is None else client.post(path, json=body)
    assert response.status_code == 422, response.text


def test_읽음은_30개까지_받고_없는_id_는_조용히_넘긴다(world):
    response = _read(world["owner"], {"ids": list(range(999_971, 1_000_001))})
    assert response.status_code == 204, response.text


def test_남의_알림_id_는_조용히_무시한다(world):
    _ask(world["peer"], world["mine"])
    [item] = _items(world["owner"])
    assert _read(world["peer"], {"ids": [item["id"]]}).status_code == 204
    assert _read(world["stranger"], {"ids": [item["id"]]}).status_code == 204
    assert _items(world["owner"])[0]["read_at"] is None


# ── 목록 ─────────────────────────────────────────────────────────────────────
def test_남의_알림은_목록에_안_보인다(world):
    _ask(world["peer"], world["mine"])
    assert len(_items(world["owner"])) == 1
    for who in ("peer", "peer2", "stranger", "lonely"):
        assert _items(world[who]) == [], who


def test_원도_반도_없는_계정은_200_빈_목록(world):
    as_(world["lonely"])
    response = client.get(API)
    assert (response.status_code, response.json()) == (200, {"items": []})


def test_목록은_id_내림차순으로_최근_30개만_준다(db_session, world):
    request_id = _ask(world["peer"], world["mine"]).json()["id"]
    insert = text(
        "INSERT INTO notifications (user_id, kind, request_id) "
        "VALUES (:user_id, 'ACCESS_REQUESTED', :request_id) RETURNING id"
    )

    def add(user):
        return db_session.execute(
            insert, {"user_id": user.id, "request_id": request_id}
        ).scalar_one()

    owned = [i["id"] for i in _items(world["owner"])]
    for n in range(34):
        owned.append(add(world["owner"]))
        if n % 5 == 0:
            add(world["peer2"])  # 남의 알림이 사이사이 끼어 있다
    ids = [i["id"] for i in _items(world["owner"])]
    assert ids == sorted(owned, reverse=True)[:30]
