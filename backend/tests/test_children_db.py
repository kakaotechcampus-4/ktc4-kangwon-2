"""아동 부르는 이름 수정 — PATCH /api/children/{id} (docs/api-spec.md §2-1). 실제 DB 를 쓴다.

test_children.py 는 세션을 스텁으로 갈아끼워 흐름만 본다. 그 스텁은 where 절을 무시해서
「반 안에서만 겹침을 본다」(children/router.py 의 `_children_of`)와 「남의 원 아이는 못 고친다」를
못 본다 — 그 둘이 이 파일의 몫이다.

아동 이름은 가명이다 — 개발 DB 에 실제 아동 실명을 넣지 않는다 (CLAUDE.md 개인정보).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.centers.models import Center, Child, Class
from app.main import app
from app.shared.childCode import load_pool

client = TestClient(app)


def _center(session, name):
    center = Center(name=name, director_name="김원장", region_sido="강원", region_sigungu="춘천시")
    session.add(center)
    session.flush()
    return center


def _class(session, center, name):
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


def _child(session, classroom, name, call_name=None):
    used = set(session.scalars(select(Child.code).where(Child.class_id == classroom.id)))
    code = load_pool().allocate(name, used)
    child = Child(class_id=classroom.id, name=name, code=code, call_name=call_name)
    session.add(child)
    session.flush()
    return child


def _call_name(session, child):
    # 질의로 다시 읽는다. 같은 세션 객체를 꺼내면 SQL 이 안 나가 저장 여부를 못 본다.
    return session.scalar(select(Child.call_name).where(Child.id == child.id))


@pytest.fixture
def roster(db_session, teacher):
    center = _center(db_session, "쓱싹 어린이집")
    teacher.center_id = center.id
    sun = _class(db_session, center, "햇살반")
    moon = _class(db_session, center, "달님반")
    other_class = _class(db_session, _center(db_session, "다른 어린이집"), "별빛반")
    return {
        "kim": _child(db_session, sun, "김민"),
        "park": _child(db_session, sun, "박민"),
        "lee": _child(db_session, moon, "이민", call_name="민이"),
        "foreign": _child(db_session, other_class, "최민"),
    }


def test_부르는_이름을_저장하고_지운다(db_session, roster):
    kim = roster["kim"]

    saved = client.patch(f"/api/children/{kim.id}", json={"call_name": "민이"})
    assert saved.status_code == 200
    assert saved.json()["call_name"] == "민이"
    assert _call_name(db_session, kim) == "민이"

    cleared = client.patch(f"/api/children/{kim.id}", json={"call_name": None})
    assert cleared.status_code == 200
    assert _call_name(db_session, kim) is None


def test_같은_반_아이가_쓰는_이름은_겹쳐서_422(db_session, roster):
    kim, park = roster["kim"], roster["park"]
    park.call_name = "민이"
    db_session.flush()

    response = client.patch(f"/api/children/{kim.id}", json={"call_name": "민이"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["fields"] == ["call_name"]
    assert "겹쳐" in error["message"]  # 외자 · 접두 검사의 422 와 구별한다
    assert _call_name(db_session, kim) is None


def test_다른_반_아이가_쓰는_이름은_겹치지_않는다(db_session, roster):
    kim = roster["kim"]  # 달님반의 이민이 이미 「민이」를 쓴다

    response = client.patch(f"/api/children/{kim.id}", json={"call_name": "민이"})

    assert response.status_code == 200
    assert _call_name(db_session, kim) == "민이"


def test_남의_원_아이는_고칠_수_없다(db_session, roster):
    foreign = roster["foreign"]

    response = client.patch(f"/api/children/{foreign.id}", json={"call_name": "민이"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert _call_name(db_session, foreign) is None
