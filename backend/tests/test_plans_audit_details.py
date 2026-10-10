"""연간 변경 이력의 값 · 생성 방식 변화 (BE-Y3). 진짜 Postgres 위에서 HTTP 로 부른다.

기존 `GET /api/plans/annual/{id}/audit` 응답에 `value_change` · `generation_change` 두 키를 더했다.
기존 다섯 키(`type` · `occurred_at` · `month` · `actor` · `system_actor`)와 `{items}` 봉투 · 순서는
그대로다. 두 키는 **Core 이벤트에 저장된 것만** 옮긴다 — 없으면 null 이다. 생성기는 mock 이다
(유료 호출 없음). 재생성(BE-Y2b)은 잠정 계약이다(docs/provisional-policy-decisions.md).
"""

import copy
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from ssuksak.adapters.deterministic_theme_text_generator import DeterministicThemeTextGenerator
from ssuksak.planning.rules.yearly_theme_selection import RULE_ID as THEME_SELECTION_RULE_ID

from app.features.centers.models import Center, Class
from app.features.plans import router as annual_router
from app.features.plans.models import Plan
from app.main import app
from app.shared.auth.dependency import current_user
from app.shared.llm import LlmFailed

client = TestClient(app)
SUFFIX = " · 다시"
OLD_KEYS = ["type", "occurred_at", "month", "actor", "system_actor"]
KEYS = [*OLD_KEYS, "value_change", "generation_change"]
ACADEMIC_ORDER = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2]


@pytest.fixture(autouse=True)
def _mock_generator(monkeypatch):
    monkeypatch.setattr(
        annual_router,
        "theme_text_generator",
        lambda: DeterministicThemeTextGenerator(suffix=SUFFIX),
    )


def _class(session, name: str) -> dict:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=3,
        age_max=4,
        teacher_name="김선생",
    )
    session.add(klass)
    session.flush()
    return {"center": center.id, "class": klass.id}


def _create(class_id: int) -> int:
    response = client.post("/api/plans/annual", json={"class_id": class_id, "form_id": None})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def world(db_session, teacher):
    mine, theirs = _class(db_session, "가원"), _class(db_session, "나원")
    teacher.center_id = theirs["center"]
    their_plan = _create(theirs["class"])
    teacher.center_id = mine["center"]
    return {
        "session": db_session,
        "plan": _create(mine["class"]),
        "their_plan": their_plan,
        "actor": f"user_{teacher.id}",
    }


def _audit(plan_id) -> list[dict]:
    response = client.get(f"/api/plans/annual/{plan_id}/audit")
    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == ["items"]  # 봉투는 그대로
    return body["items"]


def _theme(plan_id, month) -> str:
    months = client.get(f"/api/plans/annual/{plan_id}").json()["months"]
    return next(m for m in months if m["month"] == month)["theme"]


def _put(plan_id, month, theme, sub_themes=()):
    return client.put(
        f"/api/plans/annual/{plan_id}/months/{month}",
        json={"theme": theme, "sub_themes": list(sub_themes)},
    )


def _row(session, plan_id) -> tuple:
    session.expunge_all()
    row = session.get(Plan, plan_id)
    return (row.body, row.status, row.sub_themes, row.confirmed_at, row.updated_at)


def _error(response):
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


# ── A · H. 생성 직후 — 키 · null · 순서 ────────────────────────────────────


def test_생성_직후에는_계획안_CREATED_와_12개월_CREATED_가_값_변화_없이_온다(world):
    items = _audit(world["plan"])

    assert all(list(item) == KEYS for item in items)  # 기존 다섯 키 뒤에 두 키, 늘 온다
    assert [(i["type"], i["month"]) for i in items] == [("CREATED", None)] + [
        ("CREATED", month) for month in ACADEMIC_ORDER
    ]  # 같은 시각 — 계획안 먼저, 그다음 3월 ~ 2월
    assert len({i["occurred_at"] for i in items}) == 1
    for item in items:
        assert (item["actor"], item["system_actor"]) == (None, "yearly_application")
        assert (item["value_change"], item["generation_change"]) == (None, None)


# ── B · C · D. 수정 · 재생성 · 확정 ───────────────────────────────────────


def test_교사_수정은_이전_이후_theme_를_주고_생성_방식_변화는_없다(world):
    plan_id = world["plan"]
    before = _theme(plan_id, 10)
    assert _put(plan_id, 10, "교사가 쓴 10월 주제").status_code == 200

    (edited,) = [i for i in _audit(plan_id) if i["type"] == "TEACHER_EDITED"]
    assert edited == {
        "type": "TEACHER_EDITED",
        "occurred_at": edited["occurred_at"],
        "month": 10,
        "actor": world["actor"],
        "system_actor": None,
        "value_change": {"before": before, "after": "교사가 쓴 10월 주제"},
        "generation_change": None,
    }


def test_재생성은_덮어쓴_교사_문구와_생성_방식_변화를_DB_그대로_준다(world):
    session, plan_id = world["session"], world["plan"]
    original = client.get(f"/api/plans/annual/{plan_id}").json()["months"]
    created_generation = next(m for m in original if m["month"] == 10)["generation"]
    assert _put(plan_id, 10, "교사가 쓴 10월 주제").status_code == 200

    regenerated = client.post(f"/api/plans/annual/{plan_id}/months/10/regenerate")
    assert regenerated.status_code == 200, regenerated.text

    items = _audit(plan_id)
    (event,) = [i for i in items if i["type"] == "REGENERATED"]
    assert (event["month"], event["actor"], event["system_actor"]) == (10, world["actor"], None)
    assert event["value_change"] == {
        "before": "교사가 쓴 10월 주제",
        "after": regenerated.json()["theme"],
    }
    assert event["value_change"]["after"].endswith(SUFFIX)
    # 교사 수정은 생성 방식을 바꾸지 않으므로, 재생성 전 생성 방식은 처음 만든 것과 같다.
    assert event["generation_change"] == {
        "before": created_generation,
        "after": regenerated.json()["generation"],
    }
    assert event["generation_change"]["after"]["rule_id"] == THEME_SELECTION_RULE_ID
    assert event["generation_change"]["after"]["rule_version"] == "v2"
    # HTTP 가 준 값이 DB 에 저장된 이벤트와 같다.
    body = _row(session, plan_id)[0]
    period = next(p for p in body["periods"] if p["period"]["calendar_month"] == 10)
    stored = period["theme"]["audit"]["events"][-1]
    assert stored["value_change"] == event["value_change"]
    assert stored["generation_change"]["after"]["rule_id"] == THEME_SELECTION_RULE_ID
    assert _audit(plan_id) == items  # 다시 읽어도 같다


def test_확정은_값_변화_없이_오고_재확정은_이력과_DB_를_바꾸지_않는다(world):
    session, plan_id = world["session"], world["plan"]
    confirmed = client.post(f"/api/plans/annual/{plan_id}/confirm")
    assert confirmed.status_code == 200
    items = _audit(plan_id)
    (event,) = [i for i in items if i["type"] == "CONFIRMED"]
    assert (event["month"], event["actor"]) == (None, world["actor"])
    assert (event["value_change"], event["generation_change"]) == (None, None)
    assert datetime.fromisoformat(event["occurred_at"]) == datetime.fromisoformat(
        confirmed.json()["confirmed_at"]
    )

    before = _row(session, plan_id)
    assert client.post(f"/api/plans/annual/{plan_id}/confirm").json() == confirmed.json()
    assert _audit(plan_id) == items
    assert _row(session, plan_id) == before


# ── F. 소주제만 고친 PUT ────────────────────────────────────────────────


def test_소주제만_고쳐도_theme_가_같은_TEACHER_EDITED_가_그대로_보인다(world):
    plan_id = world["plan"]
    theme = _theme(plan_id, 5)
    assert _put(plan_id, 5, theme, ["봄 소풍"]).status_code == 200

    (edited,) = [i for i in _audit(plan_id) if i["type"] == "TEACHER_EDITED"]
    # theme 이전 · 이후가 같다. 소주제 값은 이력에 없다 — 이 이벤트로 소주제 변화를 알 수 없다.
    assert (edited["month"], edited["value_change"]) == (5, {"before": theme, "after": theme})
    assert "봄 소풍" not in str(edited)


# ── G. 실패 · 격리 · 불변 ───────────────────────────────────────────────


def test_실패한_재생성과_반복_조회는_이력도_DB_도_바꾸지_않는다(world, monkeypatch):
    session, plan_id = world["session"], world["plan"]
    before_items, before_row = _audit(plan_id), _row(session, plan_id)

    class Broken:
        def generate(self, requests):
            raise LlmFailed("timeout")

    monkeypatch.setattr(annual_router, "theme_text_generator", lambda: Broken())
    failed = client.post(f"/api/plans/annual/{plan_id}/months/9/regenerate")
    assert _error(failed) == (500, "GENERATION_FAILED", [])
    for _ in range(3):
        assert _audit(plan_id) == before_items
    assert _row(session, plan_id) == before_row


def test_남의_것_없는_것_월간_id_는_404_로그인_안_하면_401(world):
    session, plan_id = world["session"], world["plan"]
    monthly = Plan(
        plan_ref="plan_monthly_for_be_y3",
        center_id=session.get(Plan, plan_id).center_id,
        kind="monthly",
        school_year=2026,
        classroom_ref="0",
        status="DRAFT",
        body={},
        sub_themes={},
        # 월간 저장(M3) 뒤로는 월간 행에 target_month 가 있어야 한다. 그 전 스키마에는 칸이 없다.
        **({"target_month": "2026-09"} if hasattr(Plan, "target_month") else {}),
    )
    session.add(monthly)
    session.flush()
    for other in (world["their_plan"], 999999, monthly.id):
        assert _error(client.get(f"/api/plans/annual/{other}/audit")) == (404, "NOT_FOUND", ["id"])

    app.dependency_overrides.pop(current_user)
    response = client.get(f"/api/plans/annual/{plan_id}/audit")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


# ── 과거 데이터 · 같은 시각 순서 ─────────────────────────────────────────


def test_두_키가_없는_옛_이벤트는_null_로_오고_있는_값은_그대로다(world):
    """키가 없는 이벤트는 codec 이 기본값(None)으로 되돌린다 — 지어내지 않고 null 로 준다.

    TEACHER_EDITED 는 Core 가 `value_change` 를 반드시 요구한다(provenance.AuditEvent) — 값 없는
    교사 수정은 저장될 수 없으므로 여기서도 지우지 않는다. 나머지 종류는 키가 없어도 읽힌다.
    """
    session, plan_id = world["session"], world["plan"]
    assert _put(plan_id, 3, "고친 3월").status_code == 200
    assert client.post(f"/api/plans/annual/{plan_id}/months/9/regenerate").status_code == 200
    assert client.post(f"/api/plans/annual/{plan_id}/confirm").status_code == 200
    body = copy.deepcopy(_row(session, plan_id)[0])
    events = [*body["audit"]["events"]]
    for period in body["periods"]:
        events += period["theme"]["audit"]["events"]
    for event in events:
        if event["event_type"] != "TEACHER_EDITED":
            event.pop("value_change", None)
            event.pop("generation_change", None)
    session.execute(update(Plan).where(Plan.id == plan_id).values(body=body))
    session.flush()
    session.expire_all()

    items = _audit(plan_id)
    assert all(list(item) == KEYS for item in items)
    by_type = {i["type"]: i for i in items if i["type"] != "CREATED"}
    assert (
        by_type["REGENERATED"]["value_change"],
        by_type["REGENERATED"]["generation_change"],
    ) == (
        None,
        None,
    )
    assert by_type["CONFIRMED"]["value_change"] is None
    assert by_type["TEACHER_EDITED"]["value_change"]["after"] == "고친 3월"


def test_같은_시각이면_계획안_먼저_그다음_3월부터_2월_한_달_안에서는_저장_순서(world):
    session, plan_id = world["session"], world["plan"]
    assert _put(plan_id, 10, "교사가 쓴 10월").status_code == 200
    assert client.post(f"/api/plans/annual/{plan_id}/months/10/regenerate").status_code == 200
    assert client.post(f"/api/plans/annual/{plan_id}/confirm").status_code == 200
    body = copy.deepcopy(_row(session, plan_id)[0])
    same = "2026-10-10T00:00:00+00:00"
    for event in body["audit"]["events"]:
        event["occurred_at"] = same
    for period in body["periods"]:
        for event in period["theme"]["audit"]["events"]:
            event["occurred_at"] = same
    session.execute(update(Plan).where(Plan.id == plan_id).values(body=body))
    session.flush()
    session.expire_all()

    order = [(i["type"], i["month"]) for i in _audit(plan_id)]
    assert order[:2] == [("CREATED", None), ("CONFIRMED", None)]
    assert [month for _, month in order[2:]] == [
        m for m in ACADEMIC_ORDER for _ in range(3 if m == 10 else 1)
    ]
    assert [t for t, month in order if month == 10] == ["CREATED", "TEACHER_EDITED", "REGENERATED"]
