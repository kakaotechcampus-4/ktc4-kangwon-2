"""관찰 축이 두 갈래다 (docs/references/관찰일지-서술-기준.md).

교사가 쓴 관찰일지 3건을 재 보니 **2건이 누리과정 5영역이 아니라 일상생활 · 놀이활동**
2축이었다. 원이 어느 축을 쓸지 고르고(`centers.observation_axis`), DB 는 두 축의 값을
모두 받는다 — 원이 축을 바꿔도 전에 쌓은 기록이 CHECK 에 걸려 못 읽히면 안 된다.
「지금 이 원이 쓸 수 있는 값인가」는 라우터가 본다.

아동 이름은 가명이다 — 개발 DB 에 실제 아동 실명을 넣지 않는다 (CLAUDE.md 개인정보).
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Center, Child, Class
from app.features.observations.models import DAILY_PLAY_DOMAINS, NURI_DOMAINS, Observation
from app.main import app

client = TestClient(app)


@pytest.fixture
def two_axis(db_session, teacher):
    """2축을 쓰는 원. 반 하나 · 아이 하나."""
    center = Center(
        name="놀이 어린이집",
        director_name="김원장",
        region_sido="강원",
        region_sigungu="춘천시",
        observation_axis="DAILY_PLAY_2",
    )
    db_session.add(center)
    db_session.flush()
    teacher.center_id = center.id
    classroom = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    db_session.add(classroom)
    db_session.flush()
    child = Child(class_id=classroom.id, name="가서준", code="민준")
    db_session.add(child)
    db_session.flush()
    return {"center": center, "class": classroom, "child": child}


def _post(scope, domain):
    return client.post(
        "/api/observations",
        json={
            "class_id": scope["class"].id,
            "child_id": scope["child"].id,
            "date": "2026-09-03",
            "domain": domain,
            "fact": "블록을 쌓았다.",
        },
    )


def test_2축_원은_일상생활_놀이활동을_넣을_수_있다(two_axis):
    for domain in DAILY_PLAY_DOMAINS:
        assert _post(two_axis, domain).status_code == 201


def test_2축_원에_5영역_이름을_넣으면_422_다(two_axis):
    response = _post(two_axis, "의사소통")
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_FAILED"
    assert body["fields"] == ["domain"]
    # 무엇을 쓸 수 있는지 문구에 적는다 — 「틀렸다」만 말하면 교사가 뭘 고칠지 모른다.
    assert "일상생활" in body["message"] and "놀이활동" in body["message"]


def test_기본_원은_5영역만_받는다(db_session, teacher):
    center = Center(
        name="쓱싹 어린이집", director_name="김원장", region_sido="강원", region_sigungu="춘천시"
    )
    db_session.add(center)
    db_session.flush()
    assert center.observation_axis == "NURI_5"
    teacher.center_id = center.id
    classroom = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    db_session.add(classroom)
    db_session.flush()
    child = Child(class_id=classroom.id, name="가서준", code="민준")
    db_session.add(child)
    db_session.flush()
    scope = {"class": classroom, "child": child}
    assert _post(scope, "의사소통").status_code == 201
    assert _post(scope, "놀이활동").status_code == 422


def test_발달_추적은_그_원의_축만_센다(two_axis):
    _post(two_axis, "놀이활동")
    by_domain = client.get(f"/api/classes/{two_axis['class'].id}/children/tracking").json()[
        "items"
    ][0]["by_domain"]
    assert list(by_domain) == list(DAILY_PLAY_DOMAINS)
    assert by_domain["놀이활동"] == 1


def test_축을_바꿔도_전에_쓴_기록은_살아_있다(db_session, two_axis):
    """**DB 가 두 축을 다 받는 이유.** 축을 바꿀 때 교사가 쓴 사실을 지우지 않는다."""
    _post(two_axis, "놀이활동")
    two_axis["center"].observation_axis = "NURI_5"
    db_session.flush()
    _post(two_axis, "의사소통")

    rows = client.get(f"/api/observations?class_id={two_axis['class'].id}").json()["items"]
    assert sorted(r["domain"] for r in rows) == ["놀이활동", "의사소통"]
    # 집계는 지금 축이 앞에 서고, 옛 축으로 쓴 기록은 뒤에 붙는다 — 0 은 안 붙인다.
    by_domain = client.get(f"/api/classes/{two_axis['class'].id}/children/tracking").json()[
        "items"
    ][0]["by_domain"]
    assert list(by_domain)[: len(NURI_DOMAINS)] == list(NURI_DOMAINS)
    assert by_domain["놀이활동"] == 1
    assert "일상생활" not in by_domain


def test_DB_는_두_축_밖의_값을_막는다(db_session, two_axis):
    """라우터를 지나지 않는 스크립트 · 수동 INSERT 도 CHECK 가 막는다."""
    db_session.add(
        Observation(
            class_id=two_axis["class"].id,
            child_id=two_axis["child"].id,
            date=datetime.date(2026, 9, 3),
            domain="없는영역",
            fact="블록을 쌓았다.",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
