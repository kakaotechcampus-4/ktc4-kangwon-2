"""관찰 기록 API 를 진짜 Postgres 로 확인한다 (docs/api-spec.md §10).

`db_session` 을 받는 테스트는 끝나면 전부 롤백된다(`conftest.py`).
아동 이름은 가명이다 — 개발 DB 에 실제 아동 실명을 넣지 않는다 (CLAUDE.md 개인정보).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Center, Child, Class
from app.features.observations.models import Observation
from app.main import app

client = TestClient(app)


def _center(session, name: str) -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _class(session, center: Center, name: str) -> Class:
    classroom = Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    session.add(classroom)
    session.flush()
    return classroom


def _child(session, classroom: Class, name: str, code: str) -> Child:
    child = Child(class_id=classroom.id, name=name, code=code)
    session.add(child)
    session.flush()
    return child


@pytest.fixture
def mine(db_session, teacher):
    """로그인한 교사의 원 · 반 둘 · 아이 둘."""
    center = _center(db_session, "쓱싹 어린이집")
    teacher.center_id = center.id
    sun = _class(db_session, center, "햇살반")
    moon = _class(db_session, center, "달님반")
    return {
        "sun": sun,
        "moon": moon,
        "seojun": _child(db_session, sun, "가서준", "민준"),
        "haeun": _child(db_session, moon, "나하은", "지안"),
    }


def _post(classroom, child, **overrides):
    body = {
        "class_id": classroom.id,
        "child_id": child.id,
        "date": "2026-09-22",
        "domain": "자연탐구",
        "context": "바깥놀이",
        "fact": "화단 앞에 앉아 개미가 줄지어 가는 것을 3분 동안 바라보았다.",
        **overrides,
    }
    return client.post("/api/observations", json=body)


def test_기록을_넣으면_행이_남고_반_아이_이름과_코드가_같이_온다(db_session, mine):
    response = _post(mine["sun"], mine["seojun"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["class_name"], body["child_name"], body["child_code"]) == (
        "햇살반",
        "가서준",
        "민준",
    )
    row = db_session.get(Observation, body["id"])
    assert row.fact == body["fact"]
    assert row.domain == "자연탐구"


def test_상황을_안_적으면_null_이_아니라_빈_문자열이다(db_session, mine):
    """PR #42 리뷰에서 물은 것. `expire_on_commit=False` 여도 None 이 나가지 않는다 —
    SQLAlchemy 2.0 이 Postgres 에서 INSERT … RETURNING 으로 server_default 를 받아온다.
    그 동작에 기대는 것을 여기서 고정한다."""
    body = {"class_id": mine["sun"].id, "child_id": mine["seojun"].id, "date": "2026-09-22"}
    body |= {"domain": "의사소통", "fact": "친구에게 그림책 내용을 이야기했다."}

    response = client.post("/api/observations", json=body)

    assert response.status_code == 201, response.text
    assert response.json()["context"] == ""


def test_반_아이_날짜로_다시_꺼낸다_최신순(db_session, mine):
    _post(mine["sun"], mine["seojun"], date="2026-09-01")
    _post(mine["sun"], mine["seojun"], date="2026-09-20")
    _post(mine["sun"], mine["seojun"], date="2026-10-02")
    _post(mine["moon"], mine["haeun"], date="2026-09-10")

    def dates(**params):
        response = client.get("/api/observations", params=params)
        assert response.status_code == 200, response.text
        return [item["date"] for item in response.json()["items"]]

    assert dates() == ["2026-10-02", "2026-09-20", "2026-09-10", "2026-09-01"]
    assert dates(class_id=mine["moon"].id) == ["2026-09-10"]
    assert dates(child_id=mine["seojun"].id) == ["2026-10-02", "2026-09-20", "2026-09-01"]
    assert dates(**{"from": "2026-09-01", "to": "2026-09-30"}) == [
        "2026-09-20",
        "2026-09-10",
        "2026-09-01",
    ]


def test_다른_원의_기록은_안_보이고_고치지도_지우지도_못한다(db_session, mine):
    other = _center(db_session, "다른 어린이집")
    their_class = _class(db_session, other, "별님반")
    their_child = _child(db_session, their_class, "다도윤", "서윤")
    theirs = Observation(
        class_id=their_class.id,
        child_id=their_child.id,
        date="2026-09-22",
        domain="사회관계",
        fact="x",
    )
    db_session.add(theirs)
    db_session.flush()

    assert client.get("/api/observations").json() == {"items": []}
    update = {"date": "2026-09-22", "domain": "사회관계", "fact": "y"}
    assert client.put(f"/api/observations/{theirs.id}", json=update).status_code == 404
    assert client.delete(f"/api/observations/{theirs.id}").status_code == 404
    # 남의 반에 쓰는 것도 막는다.
    assert _post(their_class, their_child).status_code == 404


def test_그_반의_아이가_아니면_422(db_session, mine):
    response = _post(mine["sun"], mine["haeun"])

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["child_id"]


def test_사실이_공백뿐이거나_5영역_밖이면_422_를_한꺼번에(db_session, mine):
    response = _post(mine["sun"], mine["seojun"], fact="   ", domain="수학")

    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"fact", "domain"}


def test_고치면_네_칸만_바뀌고_대상은_못_바꾼다(db_session, mine):
    created = _post(mine["sun"], mine["seojun"]).json()
    update = {
        "date": "2026-09-23",
        "domain": "예술경험",
        "context": "",
        "fact": "블록으로 탑을 쌓았다.",
    }

    response = client.put(f"/api/observations/{created['id']}", json=update)

    assert response.status_code == 200, response.text
    assert {k: response.json()[k] for k in update} == update
    moved = client.put(f"/api/observations/{created['id']}", json={**update, "child_id": 1})
    assert moved.status_code == 422


def test_지우면_204_이고_목록에서_사라진다(db_session, mine):
    created = _post(mine["sun"], mine["seojun"]).json()

    assert client.delete(f"/api/observations/{created['id']}").status_code == 204
    assert client.get("/api/observations").json() == {"items": []}
    assert client.delete(f"/api/observations/{created['id']}").status_code == 404


def test_DB_가_5영역_밖의_값을_직접_막는다(db_session, mine):
    """라우터를 안 지나는 INSERT(스크립트·수동)도 CHECK 가 막는다."""
    db_session.add(
        Observation(
            class_id=mine["sun"].id,
            child_id=mine["seojun"].id,
            date="2026-09-22",
            domain="수학",
            fact="x",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
