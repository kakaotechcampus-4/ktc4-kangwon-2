"""평가제 HTTP 계약 · 실제 PostgreSQL 저장 (api-spec.md §12)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.centers.models import Center, Class
from app.features.documents.models import Document
from app.features.evaluation import catalog, router
from app.features.evaluation.models import EvaluationCheck
from app.features.evaluation.service import save_checks
from app.main import app

client = TestClient(app)
PATH = "/api/centers/{}/evaluation-checklist"
CENTER = {
    "name": "평가 테스트 가상 어린이집",
    "director_name": "가상 원장",
    "region_sido": "충청북도",
    "region_sigungu": "충주시",
}


@pytest.fixture
def own_center(db_session, teacher):
    response = client.post("/api/centers", json=CENTER)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(value=datetime(2026, 10, 9, tzinfo=UTC))
    monkeypatch.setattr(router, "datetime", SimpleNamespace(now=lambda tz: clock.value))
    return clock


@pytest.fixture
def elements(monkeypatch):
    real = catalog.load_catalog()
    values = (catalog.Element("6-3-1", "가상 요소 하나"), catalog.Element("6-3-2", "가상 요소 둘"))
    fake = replace(
        real,
        indicators=tuple(
            replace(i, elements=values) if i.indicator == "6-3" else i for i in real.indicators
        ),
    )
    monkeypatch.setattr(router, "load_catalog", lambda: fake)


def rows(session, center_id):
    return session.execute(
        select(EvaluationCheck.__table__).where(EvaluationCheck.center_id == center_id)
    ).all()


def test_GET은_파일_순서의_9개_지표와_종류별_필드를_반환한다(own_center, clock):
    response = client.get(PATH.format(own_center))
    assert response.status_code == 200, response.text
    body = response.json()
    expected = [i for i in catalog.load_catalog().indicators if i.kind != "EXCLUDED"]
    assert type(body["school_year"]) is int and body["school_year"] == 2026
    assert [i["indicator"] for i in body["items"]] == [i.indicator for i in expected]
    assert len(body["items"]) == 9
    common = {"indicator", "area", "title", "content", "kind"}
    auto = {"verdict", "required", "count", "children", "classes"}
    auto |= {"plan_ids", "document_ids", "period"}
    for item, indicator in zip(body["items"], expected, strict=True):
        assert all(
            item[key] == getattr(indicator, "area_title" if key == "area" else key)
            for key in common
        )
        if item["kind"] == "AUTO":
            assert set(item) == common | auto
            assert set(item["period"]) == {"from", "to"}
            assert all(date.fromisoformat(v).isoformat() == v for v in item["period"].values())
            assert item["plan_ids"] == item["document_ids"] == []
            assert item["count"] == 0 and item["verdict"] == "NONE"
        else:
            assert set(item) == common | {"elements", "progress", "complete"}
            assert item["elements"] == [] and item["progress"] == {"checked": 0, "total": 0}
            assert item["complete"] is False
    four_one, four_two = body["items"][:2]
    assert four_one["required"] is None and four_one["children"] is None
    assert four_one["classes"] == {"met": 0, "total": 0}
    assert four_two["classes"] is None and four_two["children"] == {"met": 0, "total": 0}
    assert four_two["required"] == 2


def test_GET은_자동_판정의_문서_번호와_개수를_그대로_싣는다(own_center, db_session, clock):
    sun = Class(
        center_id=own_center,
        name="해님반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="가상 교사",
    )
    db_session.add(sun)
    db_session.flush()
    day = date(2026, 10, 6)  # 4-1 기간 2026-09-01 ~ 2026-10-08 안
    log = Document(
        class_id=sun.id,
        kind="dailyLog",
        title="가상 일지",
        status="CONFIRMED",
        origin="TEACHER",
        start_date=day,
        end_date=day,
    )
    db_session.add(log)
    db_session.flush()

    four_one = client.get(PATH.format(own_center)).json()["items"][0]
    assert four_one["verdict"] == "INSUFFICIENT"
    assert four_one["document_ids"] == [log.id] and four_one["plan_ids"] == []
    assert four_one["count"] == 1 and four_one["classes"] == {"met": 0, "total": 1}


def test_PUT은_응답을_다_만든_뒤_한_번_저장한다(own_center, db_session, clock, monkeypatch):
    calls = []
    build, commit = router._checklist, db_session.commit

    def recorded_build(*args):
        calls.append("build")
        return build(*args)

    def recorded_commit():
        calls.append("commit")
        return commit()

    monkeypatch.setattr(router, "_checklist", recorded_build)
    monkeypatch.setattr(db_session, "commit", recorded_commit)
    response = client.put(PATH.format(own_center) + "/checks", json={"checks": []})
    assert response.status_code == 200
    assert calls == ["build", "commit"]  # 멘토 리뷰 #82 — 응답을 다 만든 뒤 저장


def test_빈_PUT은_GET_전체_응답을_주고_저장된_행을_유지한다(own_center, db_session, clock):
    path = PATH.format(own_center)
    before = client.get(path).json()
    save_checks(db_session, own_center, clock.value, [("6-3-1", True)], {"6-3-1"})
    saved = rows(db_session, own_center)
    response = client.put(path + "/checks", json={"checks": []})
    assert response.status_code == 200 and response.json() == before
    assert rows(db_session, own_center) == saved


def test_체크를_풀었다가_다시_체크하면_새_시각이다(own_center, db_session, elements, clock):
    path = PATH.format(own_center)

    def update(checked):
        response = client.put(
            path + "/checks", json={"checks": [{"element": "6-3-1", "checked": checked}]}
        )
        assert response.status_code == 200, response.text
        item = next(i for i in response.json()["items"] if i["indicator"] == "6-3")
        assert item["progress"] == {"checked": int(checked), "total": 2}
        assert item["complete"] is False and item["elements"][0]["checked"] is checked
        assert item["elements"][1] == {
            "element": "6-3-2",
            "text": "가상 요소 둘",
            "checked": False,
            "checked_at": None,
        }
        assert client.get(path).json() == response.json()
        return item["elements"][0]["checked_at"]

    first = update(True)
    assert datetime.fromisoformat(first) == clock.value and len(rows(db_session, own_center)) == 1
    assert update(False) is None and rows(db_session, own_center) == []
    clock.value += timedelta(seconds=1)
    assert datetime.fromisoformat(update(True)) == clock.value


def test_요소_오류를_모으고_유효한_요소도_저장하지_않는다(own_center, db_session, elements):
    keys = ["6-3-1", "9-9-1", "4-1-1", "6-3-2", "6-3-2"]
    response = client.put(
        PATH.format(own_center) + "/checks",
        json={"checks": [{"element": key, "checked": True} for key in keys]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["fields"] == ["checks.9-9-1", "checks.4-1-1", "checks.6-3-2"]
    assert rows(db_session, own_center) == []


@pytest.mark.parametrize(
    "checks,extra,fields",
    [
        ([{"element": "6-3-1", "checked": "yes"}], {}, ["checks.6-3-1.checked"]),
        ([{"element": "body", "checked": "yes"}], {}, ["checks.body.checked"]),
        ([{"element": "6-3-1", "checked": True, "extra": 1}], {}, ["checks.6-3-1.extra"]),
        ([{"element": "6-3-1", "checked": True, "body": 1}], {}, ["checks.6-3-1.body"]),
        ([], {"extra": 1}, ["extra"]),
        (
            [
                {"element": "6-3-1", "checked": "yes"},
                {"checked": True},
                {"element": 1, "checked": True},
                {"element": "", "checked": "yes"},
                {"element": "6-3-2", "checked": None},
            ],
            {},
            ["checks.6-3-1.checked", "checks", "checks.6-3-2.checked"],
        ),
    ],
)
def test_모양_오류는_키로_모아서_422다(own_center, db_session, checks, extra, fields):
    response = client.put(PATH.format(own_center) + "/checks", json={"checks": checks, **extra})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["fields"] == fields
    assert rows(db_session, own_center) == []


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_남의_원과_없는_원은_center_id_오류의_404다(own_center, db_session, method):
    other = Center(**{**CENTER, "name": "다른 평가 테스트 가상 어린이집"})
    db_session.add(other)
    db_session.flush()
    for center_id in [other.id, 999999]:
        path = PATH.format(center_id) + ("/checks" if method == "PUT" else "")
        response = client.request(
            method, path, **({"json": {"checks": []}} if method == "PUT" else {})
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
        assert response.json()["error"]["fields"] == ["center_id"]


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_미인증은_401다(db_session, method):
    path = PATH.format(1) + ("/checks" if method == "PUT" else "")
    response = client.request(method, path, **({"json": {"checks": []}} if method == "PUT" else {}))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
