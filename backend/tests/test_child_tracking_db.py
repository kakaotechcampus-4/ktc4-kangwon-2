"""발달 추적 — 반 아이들의 관찰 기록 집계 (docs/api-spec.md §2-1). 실제 DB 를 쓴다.

아동 이름은 가명이다 — 개발 DB 에 실제 아동 실명을 넣지 않는다 (CLAUDE.md 개인정보).
"""

import datetime

import pytest
from fastapi.testclient import TestClient

from app.features.centers.models import Center, Child, Class
from app.features.observations.models import DOMAINS, Observation
from app.main import app

client = TestClient(app)


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


def _child(session, classroom, name, code):
    child = Child(class_id=classroom.id, name=name, code=code)
    session.add(child)
    session.flush()
    return child


def _obs(session, child, day, domain):
    session.add(
        Observation(
            class_id=child.class_id,
            child_id=child.id,
            date=datetime.date(2026, 9, day),
            domain=domain,
            fact="블록을 쌓았다.",
        )
    )
    session.flush()


@pytest.fixture
def mine(db_session, teacher):
    center = Center(
        name="쓱싹 어린이집", director_name="김원장", region_sido="강원", region_sigungu="춘천시"
    )
    db_session.add(center)
    db_session.flush()
    teacher.center_id = center.id
    sun = _class(db_session, center, "햇살반")
    moon = _class(db_session, center, "달님반")
    return {
        "sun": sun,
        "moon": moon,
        "seojun": _child(db_session, sun, "가서준", "민준"),
        "doyun": _child(db_session, sun, "다도윤", "지안"),
        "haeun": _child(db_session, moon, "나하은", "서윤"),
    }


def _track(classroom):
    return client.get(f"/api/classes/{classroom.id}/children/tracking")


def test_아이_영역별로_세고_마지막_관찰일을_준다(db_session, mine):
    _obs(db_session, mine["seojun"], 3, "의사소통")
    _obs(db_session, mine["seojun"], 9, "의사소통")
    _obs(db_session, mine["seojun"], 5, "자연탐구")
    _obs(db_session, mine["haeun"], 20, "의사소통")  # 다른 반 — 섞이면 안 된다

    response = _track(mine["sun"])

    assert response.status_code == 200
    seojun, doyun = response.json()["items"]
    assert seojun["child_id"] == mine["seojun"].id
    assert seojun["name"] == "가서준"
    assert seojun["code"] == "민준"
    assert seojun["total"] == 3
    assert seojun["last_date"] == "2026-09-09"
    assert seojun["by_domain"] == {
        "신체운동·건강": 0,
        "의사소통": 2,
        "사회관계": 0,
        "예술경험": 0,
        "자연탐구": 1,
    }
    # 기록이 없는 아이도 빠지지 않는다 — 「아직 한 번도 안 본 아이」가 이 화면의 목적이다.
    assert doyun["total"] == 0
    assert doyun["last_date"] is None
    assert list(doyun["by_domain"]) == list(DOMAINS)
    assert set(doyun["by_domain"].values()) == {0}


def test_기록_본문은_내려주지_않는다(db_session, mine):
    _obs(db_session, mine["seojun"], 3, "의사소통")

    item = _track(mine["sun"]).json()["items"][0]

    assert "블록을 쌓았다." not in str(item)


def test_아동이_없는_반은_빈_목록(db_session, mine):
    star = Class(
        center_id=mine["sun"].center_id,
        name="별님반",
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="박",
    )
    db_session.add(star)
    db_session.flush()

    assert _track(star).json() == {"items": []}


def test_남의_원_반은_404(db_session, mine):
    other = Center(
        name="다른 어린이집", director_name="이원장", region_sido="강원", region_sigungu="원주시"
    )
    db_session.add(other)
    db_session.flush()
    theirs = _class(db_session, other, "남의반")

    assert _track(theirs).status_code == 404
