"""같은 원 다른 반 열람 요청 · 승인과 반 단위 권한 검사 (docs/api-spec.md §2-2, ADR-059).

실제 DB 를 쓴다. 계정은 DB 에 넣는다 — 요청 표가 `users.id` 를 외래키로 가리킨다.
아동 이름은 가명이다 (CLAUDE.md 개인정보).
"""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.features.auth.models import User
from app.features.centers.models import Center, Child, Class, ClassAccessRequest
from app.features.documents.models import Document
from app.features.plans.models import Plan
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)


def as_(user):
    app.dependency_overrides[current_user] = lambda: user


def _class(center, name, teacher_id):
    return Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김",
        teacher_id=teacher_id,
    )


def _extras(session, klass, tag):
    """반 하나에 딸린 아이 · 문서 · 계획안. 반마다 plan_ref 가 달라야 한다."""
    child = Child(class_id=klass.id, name=f"가{tag}", code=f"민{tag}")
    document = Document(
        kind="dailyLog",
        title="t",
        class_id=klass.id,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        origin="AI",
    )
    plan = Plan(
        plan_ref=f"a-{tag}",
        center_id=klass.center_id,
        kind="annual",
        school_year=2026,
        classroom_ref=str(klass.id),
        status="DRAFT",
        body={},
    )
    session.add_all([child, document, plan])
    session.flush()
    return {"class": klass, "child": child, "doc": document, "plan": plan}


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
    peer2 = user("peer2@example.com", home)
    stranger = user("stranger@example.com", other)
    db_session.flush()
    mine = _class(home, "달님반", owner.id)
    mine2 = _class(home, "별님반", owner.id)
    legacy = _class(home, "옛반", None)
    db_session.add_all([mine, mine2, legacy])
    db_session.flush()
    try:
        yield {
            "home": home,
            "owner": owner,
            "peer": peer,
            "peer2": peer2,
            "stranger": stranger,
            "mine": _extras(db_session, mine, "1"),
            "mine2": _extras(db_session, mine2, "2"),
            "legacy": _extras(db_session, legacy, "3"),
        }
    finally:
        app.dependency_overrides.pop(current_user, None)


def _request(session, klass, requester, status, updated_at=None):
    row = ClassAccessRequest(class_id=klass.id, requester_id=requester.id, status=status)
    if updated_at is not None:
        row.updated_at = updated_at
    session.add(row)
    session.flush()
    return row


def _error(response):
    return response.json()["error"]


# 읽기 · 쓰기 대표 엔드포인트 — 문서 · 아이 명단 · 관찰 · 일과 · 계획안.
# 계획안은 본문이 비어 있어 통과한 뒤에는 읽을 수 없으니 리스트로만 읽기를 본다.
READS = {
    "문서 단건": lambda w: client.get(f"/api/documents/{w['doc'].id}"),
    "문서 내려받기": lambda w: client.get(f"/api/documents/{w['doc'].id}/export/hwp"),
    "문서 목록": lambda w: client.get(f"/api/documents?class_id={w['class'].id}"),
    "아이 명단": lambda w: client.get(f"/api/classes/{w['class'].id}/children"),
    "관찰 목록": lambda w: client.get(f"/api/observations?class_id={w['class'].id}"),
    "일과 목록": lambda w: client.get(f"/api/routines?class_id={w['class'].id}"),
    "계획안 목록": lambda w: client.get(f"/api/plans/annual?class_id={w['class'].id}"),
}
SAFE_WRITES = {
    "문서 수정": lambda w: client.put(
        f"/api/documents/{w['doc'].id}",
        json={
            "sections": [{"heading": "사실", "body": "x"}],
            "updated_at": datetime.now(UTC).isoformat(),
        },
    ),
    "아이 등록": lambda w: client.post(
        f"/api/classes/{w['class'].id}/children", json={"name": "다새아"}
    ),
    "관찰 만들기": lambda w: client.post(
        "/api/observations",
        json={
            "class_id": w["class"].id,
            "child_id": w["child"].id,
            "date": "2026-09-22",
            "domain": "자연탐구",
            "context": "바깥놀이",
            "fact": "화단 앞에 앉아 개미가 줄지어 가는 것을 바라보았다.",
        },
    ),
    "일과 만들기": lambda w: client.post(
        "/api/routines",
        json={
            "class_id": w["class"].id,
            "date": "2026-09-22",
            "position": 1,
            "start": "09:20",
            "end": "10:40",
            "name": "오전 실내놀이",
            "plan": "블록",
            "execution": "블록 3개",
        },
    ),
}
# 막히는 쪽만 본다 — 통과하면 본문이 없는 계획안 때문에 다른 이유로 실패한다.
DENIED_ONLY_WRITES = {
    "계획안 확정": lambda w: client.post(f"/api/plans/annual/{w['plan'].id}/confirm", json={}),
}
NOT_SHOWN = {403, 404}


@pytest.mark.parametrize("state", [None, "PENDING", "REJECTED", "REVOKED"])
def test_승인_없는_같은_원_교사는_읽기도_쓰기도_403_REQUIRED(db_session, world, state):
    if state:
        _request(db_session, world["mine"]["class"], world["peer"], state)
    as_(world["peer"])
    for name, call in {**READS, **SAFE_WRITES, **DENIED_ONLY_WRITES}.items():
        response = call(world["mine"])
        assert response.status_code == 403, name
        assert _error(response)["code"] == "CLASS_ACCESS_REQUIRED", name
        assert _error(response)["fields"] == ["class_id"], name


def test_승인된_교사는_읽을_수_있고_쓰면_403_READ_ONLY(db_session, world):
    _request(db_session, world["mine"]["class"], world["peer"], "APPROVED")
    as_(world["peer"])
    for name, call in READS.items():
        assert call(world["mine"]).status_code not in NOT_SHOWN, name
    for name, call in {**SAFE_WRITES, **DENIED_ONLY_WRITES}.items():
        response = call(world["mine"])
        assert response.status_code == 403, name
        assert _error(response)["code"] == "CLASS_READ_ONLY", name


def test_승인을_취소하면_다시_403_REQUIRED(db_session, world):
    row = _request(db_session, world["mine"]["class"], world["peer"], "APPROVED")
    as_(world["peer"])
    assert client.get(f"/api/documents/{world['mine']['doc'].id}").status_code == 200
    row.status = "REVOKED"
    db_session.flush()
    response = client.get(f"/api/documents/{world['mine']['doc'].id}")
    assert (response.status_code, _error(response)["code"]) == (403, "CLASS_ACCESS_REQUIRED")


@pytest.mark.parametrize("who, which", [("owner", "mine"), ("peer", "legacy"), ("owner", "legacy")])
def test_주인과_옛_반은_읽고_쓴다(world, who, which):
    as_(world[who])
    for name, call in {**READS, **SAFE_WRITES}.items():
        assert call(world[which]).status_code not in NOT_SHOWN, name


def test_다른_원은_읽기도_쓰기도_404(world):
    as_(world["stranger"])
    for name, call in {**READS, **SAFE_WRITES, **DENIED_ONLY_WRITES}.items():
        response = call(world["mine"])
        assert response.status_code == 404, name


def test_반을_안_짚은_목록은_내_반과_옛_반만_준다_승인받은_반도_빠진다(db_session, world):
    _request(db_session, world["mine"]["class"], world["peer"], "APPROVED")
    as_(world["peer"])
    documents = client.get("/api/documents").json()["items"]
    assert {d["id"] for d in documents} == {world["legacy"]["doc"].id}
    plans = client.get("/api/plans/annual").json()["items"]
    assert {p["id"] for p in plans} == {world["legacy"]["plan"].id}
    as_(world["owner"])
    documents = client.get("/api/documents").json()["items"]
    assert {d["id"] for d in documents} == {world[k]["doc"].id for k in ("mine", "mine2", "legacy")}


# ── 요청 · 승인 ──────────────────────────────────────────────────────────────
def _ask(klass):
    return client.post(f"/api/classes/{klass.id}/access-requests")


def test_요청하면_201_PENDING_이고_두_번째는_409(world):
    as_(world["peer"])
    response = _ask(world["mine"]["class"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["class_id"], body["status"]) == (world["mine"]["class"].id, "PENDING")
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    again = _ask(world["mine"]["class"])
    assert (again.status_code, _error(again)["code"]) == (409, "ALREADY_EXISTS")
    assert _error(again)["fields"] == ["class_id"]


def test_이미_읽을_수_있는_반은_409_다른_원과_없는_반은_404(world):
    as_(world["owner"])
    assert _ask(world["mine"]["class"]).status_code == 409
    as_(world["peer"])
    assert _ask(world["legacy"]["class"]).status_code == 409
    as_(world["stranger"])
    response = _ask(world["mine"]["class"])
    assert (response.status_code, _error(response)["fields"]) == (404, ["class_id"])
    as_(world["peer"])
    assert client.post("/api/classes/999999/access-requests").status_code == 404


def test_승인된_교사의_요청도_409(db_session, world):
    _request(db_session, world["mine"]["class"], world["peer"], "APPROVED")
    as_(world["peer"])
    assert _ask(world["mine"]["class"]).status_code == 409


def test_거절_뒤_다시_요청하면_같은_줄이_PENDING_으로_돌아온다(world):
    as_(world["peer"])
    first = _ask(world["mine"]["class"]).json()
    as_(world["owner"])
    patched = client.patch(f"/api/access-requests/{first['id']}", json={"status": "REJECTED"})
    assert patched.status_code == 200, patched.text
    as_(world["peer"])
    second = _ask(world["mine"]["class"])
    assert second.status_code == 201
    assert (second.json()["id"], second.json()["status"]) == (first["id"], "PENDING")


def test_주인이_승인하면_열리고_취소하면_닫힌다(world):
    as_(world["peer"])
    request_id = _ask(world["mine"]["class"]).json()["id"]
    doc = f"/api/documents/{world['mine']['doc'].id}"
    assert client.get(doc).status_code == 403

    as_(world["owner"])
    approved = client.patch(f"/api/access-requests/{request_id}", json={"status": "APPROVED"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    as_(world["peer"])
    assert client.get(doc).status_code == 200

    as_(world["owner"])
    revoked = client.patch(f"/api/access-requests/{request_id}", json={"status": "REVOKED"})
    assert revoked.json()["status"] == "REVOKED"
    as_(world["peer"])
    assert client.get(doc).status_code == 403


def test_내_반_요청이_아니면_PATCH_는_404(world):
    as_(world["peer"])
    request_id = _ask(world["mine"]["class"]).json()["id"]
    for who in ("peer", "peer2", "stranger"):
        as_(world[who])
        response = client.patch(f"/api/access-requests/{request_id}", json={"status": "APPROVED"})
        assert response.status_code == 404, who
    as_(world["owner"])
    missing = client.patch("/api/access-requests/999999", json={"status": "APPROVED"})
    assert missing.status_code == 404


def test_허용되지_않는_전환은_409_STALE_WRITE(world):
    as_(world["peer"])
    request_id = _ask(world["mine"]["class"]).json()["id"]
    as_(world["owner"])
    path = f"/api/access-requests/{request_id}"
    # PENDING 을 바로 취소할 수는 없다.
    response = client.patch(path, json={"status": "REVOKED"})
    assert (response.status_code, _error(response)["code"]) == (409, "STALE_WRITE")
    assert _error(response)["fields"] == ["status"]
    assert client.patch(path, json={"status": "REJECTED"}).status_code == 200
    # 이미 처리된 요청을 다시 승인할 수 없다.
    assert client.patch(path, json={"status": "APPROVED"}).status_code == 409


@pytest.mark.parametrize(
    "body", [{"status": "APPROVED", "note": "x"}, {"status": "PENDING"}, {"status": "x"}, {}]
)
def test_PATCH_본문은_세_값만_받고_다른_칸은_422(world, body):
    as_(world["peer"])
    request_id = _ask(world["mine"]["class"]).json()["id"]
    as_(world["owner"])
    assert client.patch(f"/api/access-requests/{request_id}", json=body).status_code == 422


def test_받은_요청은_PENDING_먼저_그_안에서_최근_순이고_요청자_이름이_붙는다(db_session, world):
    old, new = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC)
    approved = _request(db_session, world["mine"]["class"], world["peer"], "APPROVED", new)
    older = _request(db_session, world["mine"]["class"], world["peer2"], "PENDING", old)
    newer = _request(db_session, world["mine2"]["class"], world["peer"], "PENDING", new)
    as_(world["owner"])
    items = client.get("/api/access-requests/received").json()["items"]
    assert [i["id"] for i in items] == [newer.id, older.id, approved.id]
    assert items[0]["class_name"] == "별님반"
    assert items[1]["requester_name"] == world["peer2"].name
    # 주인이 아닌 교사에게는 받은 요청이 없다.
    as_(world["peer"])
    assert client.get("/api/access-requests/received").json() == {"items": []}


# ── 반 요약 · 반 목록 ─────────────────────────────────────────────────────────
def test_요약은_열람_권한이_없어도_주고_제목_이름_id_는_없다(db_session, world):
    klass = world["mine"]["class"]
    db_session.add_all(
        [
            Plan(
                plan_ref="m-1",
                center_id=klass.center_id,
                kind="monthly",
                school_year=2026,
                classroom_ref=str(klass.id),
                status="CONFIRMED",
                class_name=klass.name,
                teacher_name=klass.teacher_name,
                target_month="2026-10",
                body={},
            ),
            Plan(
                plan_ref="w-1",
                center_id=klass.center_id,
                kind="weekly",
                school_year=2026,
                classroom_ref=str(klass.id),
                status="DRAFT",
                target_month="2026-10",
                week_id="2026-10-W1",
                body={},
            ),
        ]
    )
    db_session.flush()
    as_(world["peer"])
    response = client.get(f"/api/classes/{klass.id}/archive-summary")
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"kind": "weekly", "start": "2026-10-05", "end": "2026-10-09", "status": "DRAFT"},
        {"kind": "monthly", "start": "2026-10-01", "end": "2026-10-31", "status": "CONFIRMED"},
        {"kind": "dailyLog", "start": "2026-09-01", "end": "2026-09-01", "status": "DRAFT"},
        {"kind": "annual", "start": "2026-03-01", "end": "2027-02-28", "status": "DRAFT"},
    ]
    assert "가1" not in response.text and "title" not in response.text


def test_요약은_자료가_없으면_빈_배열_다른_원이면_404(db_session, world):
    empty = _class(world["home"], "빈반", world["owner"].id)
    db_session.add(empty)
    db_session.flush()
    as_(world["peer"])
    assert client.get(f"/api/classes/{empty.id}/archive-summary").json() == {"items": []}
    as_(world["stranger"])
    assert client.get(f"/api/classes/{empty.id}/archive-summary").status_code == 404
    assert client.get("/api/classes/999999/archive-summary").status_code == 404


@pytest.mark.parametrize("state", ["APPROVED", "PENDING", "REJECTED", "REVOKED", None])
def test_반_목록의_my_access_는_요청_상태를_따른다(db_session, world, state):
    if state:
        _request(db_session, world["mine"]["class"], world["peer"], state)
    as_(world["peer"])
    items = client.get(f"/api/centers/{world['home'].id}/classes").json()["items"]
    access = {i["name"]: i["my_access"] for i in items}
    assert access["달님반"] == (state or "NONE")
    assert access["별님반"] == "NONE"
    assert access["옛반"] == "OPEN"
    as_(world["owner"])
    items = client.get(f"/api/centers/{world['home'].id}/classes").json()["items"]
    assert {i["name"]: i["my_access"] for i in items}["달님반"] == "OWNER"
