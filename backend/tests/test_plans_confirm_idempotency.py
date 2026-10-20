"""연간 확정 재호출은 멱등이다 (docs/api-spec.md §7). 진짜 Postgres 위에서 HTTP 로 부른다.

이미 CONFIRMED 인 계획안에 확정이 다시 오면 200 에 저장된 그대로를 준다 — Core 확정을 다시
부르지 않고, 저장도 commit 도 하지 않는다. 월간 확정의 정책 B(결정 문서 12.10)와 같은 뜻이다.
**소유 검사가 먼저다** — 확정됐어도 남의 원 것은 404 다.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.db import engine
from app.features.centers.models import Center, Class
from app.features.plans import router as annual_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.main import app
from app.shared.auth.dependency import current_user

client = TestClient(app)


def _class(session, center_name: str) -> int:
    center = Center(
        name=center_name,
        director_name="김원장",
        region_sido="강원특별자치도",
        region_sigungu="춘천시",
    )
    session.add(center)
    session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="김선생",
    )
    session.add(klass)
    session.flush()
    return klass.id


@pytest.fixture
def world(db_session, teacher):
    """원 둘. 교사는 가원 소속이고, 나원에는 이미 확정된 연간이 하나 있다."""
    mine, theirs = _class(db_session, "가원"), _class(db_session, "나원")
    teacher.center_id = db_session.get(Class, theirs).center_id
    their_plan = _create(theirs)
    assert client.post(f"/api/plans/annual/{their_plan}/confirm").status_code == 200
    teacher.center_id = db_session.get(Class, mine).center_id
    return {"session": db_session, "plan": _create(mine), "their_plan": their_plan}


def _create(class_id: int) -> int:
    response = client.post("/api/plans/annual", json={"class_id": class_id, "form_id": None})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _confirm(plan_id):
    return client.post(f"/api/plans/annual/{plan_id}/confirm")


def _snapshot(session, plan_id: int) -> tuple:
    """DB 에 실제로 있는 값 (identity map 을 비우고 읽는다)."""
    session.expunge_all()
    row = session.get(Plan, plan_id)
    rows = session.scalar(select(func.count()).select_from(Plan))
    return (row.body, row.status, row.confirmed_at, row.updated_at, row.sub_themes, rows)


def _confirmed_events(session, plan_id: int) -> list[dict]:
    session.expunge_all()
    body = session.get(Plan, plan_id).body
    return [e for e in body["audit"]["events"] if e["event_type"] == "CONFIRMED"]


def _error(response):
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


# ── A. 처음 확정 ───────────────────────────────────────────────────────────


def test_처음_확정하면_CONFIRMED_와_확정자_시각_이력이_남는다(world, teacher):
    session, plan_id = world["session"], world["plan"]
    response = _confirm(plan_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"id", "status", "confirmed_at"}  # 기존 응답 그대로
    assert (body["id"], body["status"]) == (plan_id, "CONFIRMED")
    (confirmed,) = _confirmed_events(session, plan_id)
    assert confirmed["actor_id"]["value"] == f"user_{teacher.id}"
    row = session.get(Plan, plan_id)
    assert row.status == "CONFIRMED"
    assert row.confirmed_at == datetime.fromisoformat(confirmed["occurred_at"])
    assert client.get(f"/api/plans/annual/{plan_id}").json()["status"] == "CONFIRMED"
    audit = client.get(f"/api/plans/annual/{plan_id}/audit").json()["items"]
    assert [(e["type"], e["actor"]) for e in audit if e["type"] == "CONFIRMED"] == [
        ("CONFIRMED", f"user_{teacher.id}")
    ]


# ── B · C. 다시 확정 ───────────────────────────────────────────────────────


def test_다시_확정하면_200_이고_저장된_그대로다(world):
    session, plan_id = world["session"], world["plan"]
    first = _confirm(plan_id).json()
    before = _snapshot(session, plan_id)
    detail = client.get(f"/api/plans/annual/{plan_id}").json()
    audit = client.get(f"/api/plans/annual/{plan_id}/audit").json()

    for _ in range(3):
        again = _confirm(plan_id)
        assert again.status_code == 200, again.text
        assert again.json() == first  # 같은 id · status · 최초 confirmed_at

    assert _snapshot(session, plan_id) == before  # body · 상태 · 시각 · updated_at · 행 수
    assert len(_confirmed_events(session, plan_id)) == 1
    assert client.get(f"/api/plans/annual/{plan_id}").json() == detail
    assert client.get(f"/api/plans/annual/{plan_id}/audit").json() == audit


def test_다시_확정은_Core_확정도_저장도_쓰기_SQL_도_하지_않는다(world, monkeypatch):
    """값이 우연히 같은 UPDATE 를 멱등으로 치지 않는다 — 쓰기 경로 자체를 타지 않아야 한다."""
    plan_id = world["plan"]
    assert _confirm(plan_id).status_code == 200

    def forbidden(*args, **kwargs):
        raise AssertionError("재확정이 쓰기 경로를 탔다")

    monkeypatch.setattr(annual_router, "ConfirmYearlyPlan", forbidden)
    monkeypatch.setattr(PostgresPlanRepository, "save", forbidden)
    writes = []

    def watch(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", watch)
    try:
        assert _confirm(plan_id).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", watch)
    assert writes == []


# ── D. 원 단위 격리 ───────────────────────────────────────────────────────


def test_확정된_것이어도_남의_원_없는_id_연간이_아닌_id_는_404(world):
    session = world["session"]
    monthly = Plan(
        plan_ref="plan_monthly_for_be_y1",
        center_id=session.get(Plan, world["plan"]).center_id,
        kind="monthly",
        school_year=2026,
        classroom_ref="0",
        status="CONFIRMED",
        body={},
        sub_themes={},
        # 월간 저장(M3) 뒤로는 월간 행에 target_month 가 있어야 한다. 그 전 스키마에는 칸이 없다.
        **({"target_month": "2026-09"} if hasattr(Plan, "target_month") else {}),
    )
    session.add(monthly)
    session.flush()
    before = _snapshot(session, world["their_plan"])

    for plan_id in (world["their_plan"], 999999, monthly.id):
        assert _error(_confirm(plan_id)) == (404, "NOT_FOUND", ["id"])
    assert _snapshot(session, world["their_plan"]) == before


def test_로그인하지_않으면_401(world):
    assert _confirm(world["plan"]).status_code == 200
    app.dependency_overrides.pop(current_user)
    response = _confirm(world["plan"])
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


# ── E · F. 처음 확정 경로와 확정 뒤 편집 ───────────────────────────────────


def test_처음_확정은_여전히_Core_확정을_거친다(world, monkeypatch):
    """조기 반환은 CONFIRMED 일 때만이다. DRAFT 는 기존 경로(Core · 저장 · commit) 그대로다."""
    calls = []
    original = annual_router.ConfirmYearlyPlan

    class Counting(original):
        def execute(self, command):
            calls.append(command.plan_id)
            return super().execute(command)

    monkeypatch.setattr(annual_router, "ConfirmYearlyPlan", Counting)
    assert _confirm(world["plan"]).status_code == 200
    assert _confirm(world["plan"]).status_code == 200
    assert len(calls) == 1


def test_다시_확정해도_확정_뒤_편집은_막힌다(world):
    plan_id = world["plan"]
    _confirm(plan_id)
    _confirm(plan_id)
    before = _snapshot(world["session"], plan_id)
    response = client.put(
        f"/api/plans/annual/{plan_id}/months/3", json={"theme": "금지", "sub_themes": []}
    )
    assert _error(response) == (409, "ALREADY_CONFIRMED", [])
    assert _snapshot(world["session"], plan_id) == before
