"""증빙 등록 — `POST /api/documents/import` (docs/api-spec.md §11 「증빙 등록」).

평가제 4-1 · 4-2 는 확정 문서를 센다(§12). 우리 서비스로 만든 적 없는 문서는 이 경로로만
집계에 들어간다 — 영유아 평가가 특히 그렇다.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document, DocumentSection
from app.main import app

client = TestClient(app)

_ORIGINAL = (
    "이가명은 3월부터 8월까지 쌓기놀이에서 친구와 역할을 나누는 모습이 늘었습니다. "
    "말로 먼저 제안하는 일이 많아졌고, 다툼이 생겨도 교사를 부르는 대신 스스로 "
    "차례를 정하려 합니다. 신체 활동에서는 높은 곳에 오르려는 시도가 꾸준했습니다."
)
_ALL_CHECKED = {"original": True, "meta": True, "not_a_pass": True}


@pytest.fixture(autouse=True)
def _logged_in(db_session, teacher):
    db_session.info["teacher"] = teacher


def _center_class_child(session):
    center = Center(
        name="테스트어린이집",
        director_name="김원장",
        region_sido="충청북도",
        region_sigungu="충주시",
    )
    session.add(center)
    session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    session.add(klass)
    session.flush()
    child = Child(class_id=klass.id, name="이가명", code="도담")
    session.add(child)
    session.flush()
    teacher = session.info.get("teacher")
    if teacher is not None:
        teacher.center_id = center.id
    return center, klass, child


def _recent_period():
    """평가제 4-2 가 보는 12개월 안에 들어오는 기간. `end` 는 어제까지만 센다."""
    end = date.today() - timedelta(days=1)
    return (end - timedelta(days=60)).isoformat(), end.isoformat()


def _payload(klass, child, **overrides):
    start, end = _recent_period()
    body = {
        "kind": "assessment",
        "class_id": klass.id,
        "child_id": child.id if child else None,
        "start": start,
        "end": end,
        "title": "이가명 영유아 평가 (1학기).hwp",
        "body": _ORIGINAL,
        "checks": dict(_ALL_CHECKED),
    }
    body.update(overrides)
    return body


def test_확인_셋을_다_켜면_확정으로_저장된다(db_session):
    _, klass, child = _center_class_child(db_session)

    response = client.post("/api/documents/import", json=_payload(klass, child))

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["origin"] == "IMPORT"
    assert data["status"] == "CONFIRMED"
    assert data["title"] == "이가명 영유아 평가 (1학기).hwp"
    assert data["sections"] == [{"heading": "첨부 원문", "body": _ORIGINAL, "source_ids": []}]
    assert data["sources"] == []
    assert data["notices"] == []


def test_확인을_하나라도_끄면_초안으로_둔다(db_session):
    """초안은 집계에 안 들어간다(§12). 확정은 교사가 확인했을 때만이다."""
    _, klass, child = _center_class_child(db_session)

    response = client.post(
        "/api/documents/import",
        json=_payload(klass, child, checks={**_ALL_CHECKED, "not_a_pass": False}),
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "DRAFT"


def test_사실_대조를_하지_않는다(db_session):
    """우리가 만든 문서가 아니다. 사실·해석·지원 규격을 들이대면 아무것도 못 올린다."""
    _, klass, child = _center_class_child(db_session)

    response = client.post("/api/documents/import", json=_payload(klass, child))

    assert response.status_code == 201, response.text
    headings = db_session.scalars(
        DocumentSection.__table__.select().with_only_columns(DocumentSection.heading)
    ).all()
    assert headings == ["첨부 원문"]


def test_제목이_비면_서버가_만든다(db_session):
    _, klass, child = _center_class_child(db_session)

    response = client.post("/api/documents/import", json=_payload(klass, child, title=""))

    assert response.status_code == 201, response.text
    assert response.json()["title"].startswith("이가명 영유아 평가 (")


def test_영유아_평가인데_아동이_없으면_422(db_session):
    _, klass, _ = _center_class_child(db_session)

    response = client.post("/api/documents/import", json=_payload(klass, None))

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["child_id"]


def test_원문이_비면_422(db_session):
    _, klass, child = _center_class_child(db_session)

    response = client.post("/api/documents/import", json=_payload(klass, child, body="   "))

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["body"]


def test_남의_반에는_못_올린다(db_session):
    _, klass, child = _center_class_child(db_session)
    other = Center(
        name="남의집", director_name="박원장", region_sido="서울특별시", region_sigungu="강남구"
    )
    db_session.add(other)
    db_session.flush()
    other_class = Class(
        center_id=other.id,
        name="달님반",
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="최선생",
    )
    db_session.add(other_class)
    db_session.flush()

    day = (date.today() - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/documents/import",
        json=_payload(other_class, None, kind="dailyLog", start=day, end=day),
    )

    assert response.status_code == 404


def test_검토_기간_밖이면_알려주되_막지_않는다(db_session):
    """원에서 쓰던 서류는 우리 규격을 모르고 쓰였다. 못 올리게 하면 화면을 포기한다."""
    _, klass, child = _center_class_child(db_session)

    response = client.post(
        "/api/documents/import",
        json=_payload(klass, child, start="2020-03-01", end="2020-08-31"),
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "CONFIRMED"
    assert [n["code"] for n in data["notices"]] == ["OUT_OF_REVIEW_PERIOD"]


def test_원문이_너무_짧으면_알려준다(db_session):
    _, klass, child = _center_class_child(db_session)

    response = client.post("/api/documents/import", json=_payload(klass, child, body="평가함"))

    assert response.status_code == 201, response.text
    assert [n["code"] for n in response.json()["notices"]] == ["BODY_TOO_SHORT"]


def test_같은_기간_증빙이_이미_있으면_알려준다(db_session):
    _, klass, child = _center_class_child(db_session)
    first = client.post("/api/documents/import", json=_payload(klass, child))
    assert first.status_code == 201, first.text

    second = client.post("/api/documents/import", json=_payload(klass, child))

    assert second.status_code == 201, second.text
    assert "ALREADY_REGISTERED" in [n["code"] for n in second.json()["notices"]]


def test_등록한_증빙은_확정_취소와_수정이_된다(db_session):
    """IMPORT 도 보통 문서다 — 잘못 올렸으면 교사가 되돌릴 수 있어야 한다."""
    _, klass, child = _center_class_child(db_session)
    created = client.post("/api/documents/import", json=_payload(klass, child)).json()

    response = client.post(f"/api/documents/{created['id']}/unconfirm")

    assert response.status_code == 200, response.text
    assert db_session.get(Document, created["id"]).status == "DRAFT"
