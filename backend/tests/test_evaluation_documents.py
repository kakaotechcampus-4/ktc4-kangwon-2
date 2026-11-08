"""평가 서류 도장 근거 — 직접확인 · 폴더 결과(교사 단위) · 원장 서류 체크(원 단위). ADR-074."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.auth.models import User
from app.features.evaluation import router
from app.features.evaluation.models import EvaluationDocMark
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)
PATH = "/api/centers/{}/evaluation-checklist"
CENTER = {
    "name": "도장 테스트 가상 어린이집",
    "director_name": "가상 원장",
    "region_sido": "충청북도",
    "region_sigungu": "충주시",
}
PERIOD = {"from": "2026-09-01", "to": "2026-10-08"}


@pytest.fixture
def own_center(db_session, teacher):
    # 서류 줄이 users 를 가리킨다 — 진짜 행이어야 한다.
    db_session.add(teacher)
    db_session.flush()
    response = client.post("/api/centers", json=CENTER)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(value=datetime(2026, 10, 9, tzinfo=UTC))
    monkeypatch.setattr(router, "datetime", SimpleNamespace(now=lambda tz: clock.value))
    return clock


def docs(body):
    return {d["doc"]: d for d in body["documents"]}


def scan(*results):
    return {"folder_scan": {"results": [dict(period=PERIOD, **r) for r in results]}}


def put(center_id, kind, body):
    return client.put(f"{PATH.format(center_id)}/{kind}", json=body)


def test_직접확인은_처음_누른_시각을_지키고_풀면_줄이_없어진다(own_center, db_session, clock):
    first = clock.value
    body = put(own_center, "documents", {"checks": [{"doc": "parent", "checked": True}]}).json()
    assert docs(body)["parent"]["checked"] is True
    assert docs(body)["parent"]["checked_at"] == first.isoformat().replace("+00:00", "Z")

    clock.value = first + timedelta(hours=1)
    body = put(own_center, "documents", {"checks": [{"doc": "parent", "checked": True}]}).json()
    assert docs(body)["parent"]["checked_at"] == first.isoformat().replace("+00:00", "Z")

    body = put(own_center, "documents", {"checks": [{"doc": "parent", "checked": False}]}).json()
    assert docs(body)["parent"] == {
        "doc": "parent",
        "checked": False,
        "checked_at": None,
        "folder": None,
    }
    assert db_session.scalars(select(EvaluationDocMark)).all() == []


def test_폴더_검사는_통째로_바꾸고_직접확인은_남긴다(own_center, db_session, clock):
    put(own_center, "documents", {"checks": [{"doc": "training", "checked": True}]})
    body = put(
        own_center,
        "documents",
        scan(
            {"doc": "journal", "status": "partial", "files": 4, "gaps": 20},
            {"doc": "plan", "status": "found", "files": 2, "gaps": 0},
            {"doc": "training", "status": "found", "files": 1, "gaps": 0},
        ),
    ).json()
    assert docs(body)["journal"]["folder"] == {
        "status": "partial",
        "scanned_at": "2026-10-09T00:00:00Z",
        "period": PERIOD,
        "files": 4,
        "gaps": 20,
    }
    assert docs(body)["training"]["checked"] is True
    assert docs(body)["training"]["folder"]["status"] == "found"

    # 새 폴더에는 보육일지만 있다 — 이수증의 옛 폴더 결과는 지우고 직접확인은 그대로,
    # 체크 없이 폴더 결과만 있던 계획안은 줄째 지운다
    body = put(
        own_center, "documents", scan({"doc": "journal", "status": "found", "files": 9, "gaps": 0})
    ).json()
    assert docs(body)["journal"]["folder"]["files"] == 9
    assert docs(body)["training"]["folder"] is None
    assert docs(body)["training"]["checked"] is True
    assert docs(body)["plan"]["folder"] is None
    assert {row.doc for row in db_session.scalars(select(EvaluationDocMark))} == {
        "journal",
        "training",
    }


def test_서류_줄은_교사마다_따로다(own_center, db_session, teacher, clock):
    put(own_center, "documents", {"checks": [{"doc": "parent", "checked": True}]})
    other = User(
        id=2,
        email="other@example.com",
        name="박선생",
        password_hash=b"x" * 64,
        password_salt=b"y" * 16,
        center_id=own_center,
    )
    db_session.add(other)
    db_session.flush()
    app.dependency_overrides[current_user] = lambda: other
    try:
        body = client.get(PATH.format(own_center)).json()
        assert docs(body)["parent"]["checked"] is False
        put(own_center, "documents", {"checks": [{"doc": "iep", "checked": True}]})
    finally:
        app.dependency_overrides[current_user] = lambda: teacher
    body = client.get(PATH.format(own_center)).json()
    assert docs(body)["parent"]["checked"] is True
    assert docs(body)["iep"]["checked"] is False


def test_원장_서류_체크는_원에_하나다(own_center, db_session, teacher, clock):
    body = put(
        own_center,
        "director",
        {
            "checks": [
                {"item": "annual-plan", "checked": True},
                {"item": "day-papers", "checked": True},
            ]
        },
    ).json()
    checked = {d["item"] for d in body["director"] if d["checked"]}
    assert checked == {"annual-plan", "day-papers"}

    other = User(
        id=2,
        email="other@example.com",
        name="박선생",
        password_hash=b"x" * 64,
        password_salt=b"y" * 16,
        center_id=own_center,
    )
    db_session.add(other)
    db_session.flush()
    app.dependency_overrides[current_user] = lambda: other
    try:
        body = put(own_center, "director", {"checks": [{"item": "day-papers", "checked": False}]})
    finally:
        app.dependency_overrides[current_user] = lambda: teacher
    body = client.get(PATH.format(own_center)).json()
    assert {d["item"] for d in body["director"] if d["checked"]} == {"annual-plan"}


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("documents", {}),
        ("documents", {"checks": []}),
        # 쌤플이 만드는 서류는 직접확인을 받지 않는다(ADR-074 결정 3)
        ("documents", {"checks": [{"doc": "journal", "checked": True}]}),
        ("documents", {"checks": [{"doc": "parent", "checked": "true"}]}),
        ("documents", {"checks": [{"doc": "parent", "checked": True}] * 2}),
        ("documents", scan({"doc": "plan", "status": "found", "files": 0, "gaps": 0})),
        ("documents", scan({"doc": "plan", "status": "missing", "files": 1, "gaps": 0})),
        ("documents", scan({"doc": "plan", "status": "partial", "files": 1, "gaps": 0})),
        ("documents", scan({"doc": "plan", "status": "found", "files": 1, "gaps": 1})),
        ("documents", scan({"doc": "plan", "status": "found", "files": -1, "gaps": 0})),
        ("documents", scan(*[{"doc": "plan", "status": "found", "files": 1, "gaps": 0}] * 2)),
        # 파일 이름은 받지 않는다(ADR-045)
        (
            "documents",
            scan({"doc": "plan", "status": "found", "files": 1, "gaps": 0, "names": ["a.hwp"]}),
        ),
        (
            "documents",
            {
                "folder_scan": {
                    "results": [
                        {
                            "doc": "plan",
                            "status": "found",
                            "files": 1,
                            "gaps": 0,
                            "period": {"from": "2026-10-09", "to": "2026-10-08"},
                        }
                    ]
                }
            },
        ),
        ("director", {"checks": []}),
        ("director", {"checks": [{"item": "unknown", "checked": True}]}),
    ],
)
def test_모양이_틀린_요청은_422다(own_center, db_session, clock, kind, body):
    response = put(own_center, kind, body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert db_session.scalars(select(EvaluationDocMark)).all() == []


@pytest.mark.parametrize("kind", ["documents", "director"])
def test_다른_원에는_쓰지_못한다(own_center, clock, kind):
    body = (
        {"checks": [{"doc": "parent", "checked": True}]}
        if kind == "documents"
        else {"checks": [{"item": "annual-plan", "checked": True}]}
    )
    response = put(own_center + 1, kind, body)
    assert response.status_code == 404, response.text
