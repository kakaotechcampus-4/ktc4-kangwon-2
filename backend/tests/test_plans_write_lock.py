"""연간 PUT · 확정은 계획안 행을 잠그고 읽는다 — 겹친 쓰기가 서로를 지우지 않는다.

진짜 Postgres, **서로 다른 연결 두 개**로 본다. 한 요청을 「읽은 뒤 · 저장 전」에 붙잡아 두고 다른
요청을 보낸다. 잠금이 있으면 두 번째 요청은 첫 요청이 끝날 때까지 기다렸다가 최신 값을 읽는다.
잠금이 없으면 나중에 저장한 쪽이 본문 전체를 덮어써 먼저 쓴 것이 사라진다(확정이 DRAFT 로
되돌아가는 것 포함). 응답 계약(코드 · 모양)은 바뀌지 않는다.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import engine
from app.features.centers.models import Center, Class
from app.features.plans import router as annual_router
from app.features.plans.models import Plan
from app.main import app

client = TestClient(app)
HOLD = 1.0  # 두 번째 요청이 잠금에 막혀 있는지 보는 시간(초)


@pytest.fixture
def live(_schema, teacher):
    """커밋된 원 · 반 · DRAFT 연간. 요청마다 진짜 session 을 쓴다(get_session 을 바꾸지 않는다)."""
    with Session(engine) as session:
        center = Center(
            name="연간 잠금 테스트원",
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
        session.commit()
        ids = {"center": center.id, "class": klass.id}
    teacher.center_id = ids["center"]
    try:
        created = client.post("/api/plans/annual", json={"class_id": ids["class"], "form_id": None})
        assert created.status_code == 201, created.text
        yield {**ids, "plan": created.json()["id"]}
    finally:
        with Session(engine) as session:
            session.execute(delete(Plan).where(Plan.center_id == ids["center"]))
            session.execute(delete(Class).where(Class.id == ids["class"]))
            session.execute(delete(Center).where(Center.id == ids["center"]))
            session.commit()


def _paused(monkeypatch, name: str, *, first_only: bool = False):
    """라우터의 use case 를 「읽은 뒤 · 저장 전」에서 멈추게 한다. (도착 신호, 풀기 신호)를 준다."""
    reached, release = threading.Event(), threading.Event()
    original = getattr(annual_router, name)
    calls = []

    class Paused(original):
        def execute(self, command):
            calls.append(command)
            if not first_only or len(calls) == 1:
                reached.set()
                assert release.wait(timeout=20)
            return super().execute(command)

    monkeypatch.setattr(annual_router, name, Paused)
    return reached, release


def _put(plan_id, month, theme, sub_themes=()):
    return client.put(
        f"/api/plans/annual/{plan_id}/months/{month}",
        json={"theme": theme, "sub_themes": list(sub_themes)},
    )


def _confirm(plan_id):
    return client.post(f"/api/plans/annual/{plan_id}/confirm")


def _race(first, second, reached, release):
    """first 를 멈춘 지점까지 보내고 second 를 보낸 뒤, second 가 막혀 있는지 보고 first 를 푼다."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(first)
        assert reached.wait(timeout=20)
        b = executor.submit(second)
        time.sleep(HOLD)
        second_blocked = not b.done()
        release.set()
        return a.result(timeout=30), b.result(timeout=30), second_blocked


def _stored(plan_id) -> tuple[Plan, list[str], dict]:
    with Session(engine) as session:
        row = session.get(Plan, plan_id)
        events = [e["event_type"] for e in row.body["audit"]["events"]]
        themes = {p["period"]["calendar_month"]: p["theme"]["value"] for p in row.body["periods"]}
        return row, events, themes


def _month_events(plan_id, month: int) -> list[str]:
    with Session(engine) as session:
        body = session.get(Plan, plan_id).body
    period = next(p for p in body["periods"] if p["period"]["calendar_month"] == month)
    return [e["event_type"] for e in period["theme"]["audit"]["events"]]


def test_PUT_중에_온_확정은_기다렸다가_고친_본문을_확정한다(live, monkeypatch):
    plan_id = live["plan"]
    reached, release = _paused(monkeypatch, "EditYearlyPlanItem")
    seen_during_hold = []

    def confirm_after_peek():
        # 잠금은 쓰기만 막는다 — 그 사이 단순 조회는 기다리지 않는다.
        seen_during_hold.append(client.get(f"/api/plans/annual/{plan_id}").status_code)
        return _confirm(plan_id)

    put, confirm, blocked = _race(
        lambda: _put(plan_id, 3, "고친 3월 주제", ["첫 주"]), confirm_after_peek, reached, release
    )

    assert seen_during_hold == [200]
    assert blocked  # 확정이 PUT 의 잠금을 기다렸다
    assert (put.status_code, confirm.status_code) == (200, 200)
    row, events, themes = _stored(plan_id)
    assert row.status == "CONFIRMED"  # DRAFT 로 되돌아가지 않는다
    assert events.count("CONFIRMED") == 1
    assert themes[3] == "고친 3월 주제"  # 확정된 본문에 교사 수정이 들어 있다
    assert "TEACHER_EDITED" in _month_events(plan_id, 3)
    assert row.sub_themes["3"] == ["첫 주"]


def test_확정_중에_온_PUT_은_기다렸다가_409_이고_사라지는_수정이_없다(live, monkeypatch):
    plan_id = live["plan"]
    reached, release = _paused(monkeypatch, "ConfirmYearlyPlan")

    confirm, put, blocked = _race(
        lambda: _confirm(plan_id), lambda: _put(plan_id, 3, "늦은 수정"), reached, release
    )

    assert blocked  # PUT 이 확정의 잠금을 기다렸다
    assert confirm.status_code == 200
    # 200 을 받고도 수정이 사라지는 일(잃어버린 업데이트) 대신 409 를 받는다.
    assert put.status_code == 409, put.text
    assert put.json()["error"]["code"] == "ALREADY_CONFIRMED"
    row, events, themes = _stored(plan_id)
    assert row.status == "CONFIRMED"
    assert themes[3] != "늦은 수정"
    assert "TEACHER_EDITED" not in _month_events(plan_id, 3)


def test_다른_달을_동시에_고친_PUT_둘은_둘_다_남는다(live, monkeypatch):
    plan_id = live["plan"]
    reached, release = _paused(monkeypatch, "EditYearlyPlanItem", first_only=True)

    march, april, blocked = _race(
        lambda: _put(plan_id, 3, "고친 3월", ["3월 소주제"]),
        lambda: _put(plan_id, 4, "고친 4월", ["4월 소주제"]),
        reached,
        release,
    )

    assert blocked
    assert (march.status_code, april.status_code) == (200, 200)
    row, _, themes = _stored(plan_id)
    assert (themes[3], themes[4]) == ("고친 3월", "고친 4월")
    assert row.sub_themes["3"] == ["3월 소주제"] and row.sub_themes["4"] == ["4월 소주제"]
    assert "TEACHER_EDITED" in _month_events(plan_id, 3)
    assert "TEACHER_EDITED" in _month_events(plan_id, 4)


def test_확정을_두_번_동시에_보내도_확정은_한_번이고_둘_다_200(live, monkeypatch):
    plan_id = live["plan"]
    reached, release = _paused(monkeypatch, "ConfirmYearlyPlan", first_only=True)

    first, second, blocked = _race(
        lambda: _confirm(plan_id), lambda: _confirm(plan_id), reached, release
    )

    assert blocked
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json()  # 두 번째는 첫 확정을 그대로 받는다(BE-Y1 · §7)
    _, events, _ = _stored(plan_id)
    assert events.count("CONFIRMED") == 1
