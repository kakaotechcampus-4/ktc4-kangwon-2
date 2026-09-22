"""아동 명단 API 가 실제 PostgreSQL 에 남기는 것. 계약은 docs/api-spec.md §2-1 이다.

tests/test_children.py 는 스텁 세션이라 SQL 을 해석하지 않는다 — `WHERE class_id`,
`ORDER BY id`, 실제 저장, `UNIQUE(class_id, code)`, 삭제는 여기서만 확인된다.

행 확인은 ORM 이 아니라 raw SQL 로 한다. 세션의 identity map 을 거치면 방금 만든
파이썬 객체를 다시 읽을 뿐이고, 테이블에 실제로 들어갔는지는 알 수 없다.

`issue_code` 는 받침이 같은 쪽 Pool 에서 **아직 안 쓴 첫 값**을 고르는 결정적 함수다.
그래서 code 를 기대값으로 직접 쓰지 않고 "같다 / 다르다" 로만 단언한다 — Pool 순서가
바뀌어도 깨지지 않으면서 랜덤에 기대지도 않는다.
"""

from sqlalchemy import text

from app.features.centers.models import Center, Class

ROW_SQL = text("SELECT class_id, name, code FROM children WHERE id = :id")
CODES_SQL = text("SELECT code FROM children WHERE class_id = :class_id ORDER BY id")


def _make_class(db_session, name: str = "햇님반") -> int:
    """반 하나를 만들어 id 를 준다.

    원 생성·반 생성 API 는 이 파일의 대상이 아니라 ORM 으로 직접 넣는다.
    """
    center = Center(
        name="테스트어린이집",
        director_name="테스트원장",
        region_sido="강원특별자치도",
        region_sigungu="춘천시",
    )
    db_session.add(center)
    db_session.flush()
    classroom = Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=3,
        age_max=4,
        teacher_name="김선생",
    )
    db_session.add(classroom)
    db_session.flush()
    return classroom.id


def _register(db_client, class_id: int, name: str) -> dict:
    response = db_client.post(f"/api/classes/{class_id}/children", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


# A. 등록이 행을 남긴다 ────────────────────────────────────────────────
def test_registering_a_child_persists_the_row(db_client, db_session):
    class_id = _make_class(db_session)

    response = db_client.post(f"/api/classes/{class_id}/children", json={"name": "박서준"})

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["class_id"] == class_id
    assert body["name"] == "박서준"
    assert body["code"]
    assert body["created_at"]

    # 응답을 믿지 않고 같은 id 를 DB 에서 다시 읽는다.
    row = db_session.execute(ROW_SQL, {"id": body["id"]}).one()
    assert row == (class_id, "박서준", body["code"])


# B. 같은 반에서는 code 가 겹치지 않는다 ─────────────────────────────────
def test_codes_do_not_repeat_inside_one_class(db_client, db_session):
    class_id = _make_class(db_session)

    codes = [_register(db_client, class_id, n)["code"] for n in ("박서준", "이승석", "김동혁")]

    assert len(set(codes)) == 3
    # UNIQUE(class_id, code) 를 건드리지 않고 세 행이 다 들어갔다.
    stored = list(db_session.execute(CODES_SQL, {"class_id": class_id}).scalars())
    assert stored == codes


# C. 다른 반에서는 같은 code 를 다시 쓴다 ────────────────────────────────
def test_another_class_may_reuse_the_same_code(db_client, db_session):
    mine, other = _make_class(db_session, "햇님반"), _make_class(db_session, "달님반")

    # 두 반 모두 첫 아동이고 받침이 있는 이름이라, 결정적으로 같은 가명이 나온다.
    first = _register(db_client, mine, "박서준")["code"]
    second = _register(db_client, other, "이승석")["code"]

    assert first == second
    # 전역 UNIQUE 였다면 두 번째 INSERT 가 터졌을 것이다. 제약 범위가 (class_id, code) 다.
    same_code_rows = db_session.execute(
        text("SELECT count(*) FROM children WHERE code = :code"), {"code": first}
    ).scalar()
    assert same_code_rows == 2


# D. 목록은 그 반 아동만 준다 ───────────────────────────────────────────
def test_listing_returns_only_that_class(db_client, db_session):
    mine, other = _make_class(db_session, "햇님반"), _make_class(db_session, "달님반")
    _register(db_client, mine, "박서준")
    outsider = _register(db_client, other, "이승석")

    items = db_client.get(f"/api/classes/{mine}/children").json()["items"]

    assert [c["name"] for c in items] == ["박서준"]
    assert outsider["id"] not in [c["id"] for c in items]
    assert {c["class_id"] for c in items} == {mine}


# E. 목록은 id 오름차순이다 ─────────────────────────────────────────────
def test_listing_is_ordered_by_id(db_client, db_session):
    """물리적 행 순서를 id 순서와 어긋나게 만들어 놓고 본다.

    API 로 차례로 등록하면 힙에 쌓인 순서와 id 순서가 같아져서, `ORDER BY` 를 빼도
    테스트가 통과한다. 그래서 id 를 직접 지정해 3 · 1 · 2 순으로 넣는다 — 정렬이 없으면
    Postgres 는 넣은 순서대로 돌려준다.
    """
    class_id = _make_class(db_session)
    base = db_session.execute(text("SELECT coalesce(max(id), 0) FROM children")).scalar()
    for offset in (3, 1, 2):
        db_session.execute(
            text("INSERT INTO children (id, class_id, name, code) VALUES (:i, :c, :n, :k)"),
            {"i": base + offset, "c": class_id, "n": f"아동{offset}", "k": f"가명{offset}"},
        )

    items = db_client.get(f"/api/classes/{class_id}/children").json()["items"]

    assert [c["id"] for c in items] == [base + 1, base + 2, base + 3]
    assert [c["name"] for c in items] == ["아동1", "아동2", "아동3"]


# F. 빈 반과 없는 반은 다르다 ───────────────────────────────────────────
def test_an_empty_class_returns_an_empty_items_envelope(db_client, db_session):
    class_id = _make_class(db_session)

    response = db_client.get(f"/api/classes/{class_id}/children")

    assert response.status_code == 200
    # count 를 따로 보내지 않는다 (§2-1).
    assert response.json() == {"items": []}


def test_a_missing_class_returns_the_not_found_envelope(db_client, db_session):
    missing = db_session.execute(text("SELECT coalesce(max(id), 0) + 1000 FROM classes")).scalar()

    response = db_client.get(f"/api/classes/{missing}/children")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "반을 찾을 수 없습니다.",
            "fields": ["class_id"],
        }
    }


# G. 삭제가 행을 지운다 ─────────────────────────────────────────────────
def test_deleting_a_child_removes_the_row(db_client, db_session):
    class_id = _make_class(db_session)
    child = _register(db_client, class_id, "박서준")

    assert db_client.delete(f"/api/children/{child['id']}").status_code == 204

    assert db_session.execute(ROW_SQL, {"id": child["id"]}).one_or_none() is None
    assert db_client.get(f"/api/classes/{class_id}/children").json() == {"items": []}


# H. 삭제된 code 는 다시 발급된다 ───────────────────────────────────────
def test_a_deleted_code_becomes_available_again(db_client, db_session):
    class_id = _make_class(db_session)
    first = _register(db_client, class_id, "박서준")

    db_client.delete(f"/api/children/{first['id']}")
    # 같은 받침 쪽 이름이라 Pool 순서상 같은 자리를 다시 고른다. 발급 이력을 남기지 않는다(§2-1).
    again = _register(db_client, class_id, "한지훈")

    assert again["code"] == first["code"]
    assert again["id"] != first["id"]
    row = db_session.execute(ROW_SQL, {"id": again["id"]}).one()
    assert row.code == first["code"]


# I. 없는 아동 삭제 ─────────────────────────────────────────────────────
def test_deleting_a_missing_child_returns_the_not_found_envelope(db_client, db_session):
    missing = db_session.execute(text("SELECT coalesce(max(id), 0) + 1000 FROM children")).scalar()

    response = db_client.delete(f"/api/children/{missing}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "아동을 찾을 수 없습니다.",
            "fields": ["child_id"],
        }
    }
