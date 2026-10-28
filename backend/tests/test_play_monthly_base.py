"""놀이 중심 월간 서버 ① 바탕 — 기존 경로가 놀이 월간 행을 잘못 읽지 않는다(ADR-046 §2~§4).

월간 계획안 행은 `plans` kind='monthly' 로 같이 저장된다. 새 경로는 이 PR 에 없다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import pytest
from fastapi.testclient import TestClient
from play_monthly_factory import make_play_monthly, save_play_monthly
from sqlalchemy import select
from ssuksak.planning import PlanId
from ssuksak.planning.domain.play_monthly_plan import PlayMonthlyPlan
from test_plans_play_project import _approved as _approved_play  # noqa: F401
from test_weekly_plans_api import _approved, _create, _error, world  # noqa: F401

from app.features.plans import monthly_router, weekly_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.main import app

client = TestClient(app)
MESSAGE = "놀이 중심 월간계획안은 /api/plans/monthly/play 경로로 다룹니다."
PATHS = {
    "단건": ("get", "/api/plans/monthly/{id}", None),
    "칸 수정": ("put", "/api/plans/monthly/{id}/cells/x", {"value": "v", "expected_revision": 1}),
    "칸 재생성": ("post", "/api/plans/monthly/{id}/cells/x/regenerate", {"expected_revision": 1}),
    "확정": ("post", "/api/plans/monthly/{id}/confirm", {"expected_revision": 1}),
    "이력": ("get", "/api/plans/monthly/{id}/audit", None),
    "삭제": ("delete", "/api/plans/monthly/{id}", None),
    "내보내기": ("get", "/api/plans/monthly/{id}/export/hwp", None),
}


def _call(name, row_id):
    method, path, body = PATHS[name]
    return getattr(client, method)(
        path.format(id=row_id), **({} if body is None else {"json": body})
    )


def _play(world, *, school_year=2027, month=4, mine=True):
    side = world["mine" if mine else "other"]
    plan = make_play_monthly(str(side["class"]), school_year, month)
    return plan, save_play_monthly(world["session"], side["center"], plan)


def _snapshot(row):
    return (row.body, row.revision, row.status)


@pytest.mark.parametrize("name", PATHS)
def test_기존_월간_경로는_놀이_월간_id_를_409_로_막고_행을_안_건드린다(world, name):
    _, row = _play(world)
    before = _snapshot(row)

    response = _call(name, row.id)

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert (error["code"], error["message"], error["fields"]) == ("GATE_BLOCKED", MESSAGE, [])
    world["session"].refresh(row)
    assert _snapshot(row) == before


@pytest.mark.parametrize("name", PATHS)
def test_남의_원_놀이_월간은_409_보다_먼저_404(world, name):
    _, row = _play(world, mine=False)

    assert _call(name, row.id).status_code == 404


def test_기존_월간_목록은_놀이_월간을_경고_없이_뺀다(world, monkeypatch):
    _play(world)
    warned = []
    monkeypatch.setattr(monthly_router._log, "warning", lambda *a, **k: warned.append(a))

    items = client.get("/api/plans/monthly", params={"class_id": world["mine"]["class"]}).json()[
        "items"
    ]

    assert [i["id"] for i in items] == [world["monthly"]["id"]]
    assert warned == []  # 형식으로 뺀다 — 못 읽는 행의 경고가 아니다


def test_주간_생성은_부모가_놀이_월간이면_읽기_전에_409(world, monkeypatch):
    session = world["session"]
    session.delete(session.get(Plan, world["monthly"]["id"]))
    session.flush()
    _play(world, school_year=2026, month=9)

    def _boom(*args, **kwargs):
        raise AssertionError("놀이 월간을 MonthlyPlan 으로 읽었다")

    monkeypatch.setattr(weekly_router, "PostgresPlanRepository", _boom)
    response = _create(world)

    assert _error(response) == (409, "GATE_BLOCKED", ["class_id"])
    assert (
        response.json()["error"]["message"]
        == "놀이 중심 월간계획안 아래에서는 주간계획안을 만들 수 없습니다."
    )


def test_기존_월간_생성은_놀이형_연간_부모의_409_문구_끝에_안내를_붙인다(world):
    from test_plans_play_project import _plan

    mine = world["mine"]
    session = world["session"]
    session.delete(session.get(Plan, world["monthly"]["id"]))
    session.query(Plan).filter(Plan.kind == "annual", Plan.center_id == mine["center"]).delete()
    plan = _plan(str(mine["class"]))
    PostgresPlanRepository(
        session, center_id=mine["center"], kind="annual", plan_type=type(plan)
    ).save(plan.plan_id, plan)
    session.commit()

    response = client.post(
        "/api/plans/monthly",
        json={"class_id": mine["class"], "month": 9, "profile_ref": mine["profile"]},
    )

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert (error["code"], error["fields"]) == ("GATE_BLOCKED", ["class_id"])
    assert error["message"] == (
        "놀이 프로젝트형 연간계획안으로는 기존 월간계획안을 만들 수 없습니다. "
        "놀이 중심 월간계획안으로 만들어 주세요."
    )


def test_팩토리가_만든_계획안을_행으로_넣고_읽으면_같다(world):
    plan, row = _play(world)

    assert (row.kind, row.status, row.body["format"]) == ("monthly", "DRAFT", "PLAY_MONTHLY")
    assert row.classroom_ref == str(world["mine"]["class"])
    back = PostgresPlanRepository(
        world["session"],
        center_id=world["mine"]["center"],
        kind="monthly",
        plan_type=PlayMonthlyPlan,
    ).get(PlanId(row.plan_ref))
    assert back == plan
    assert world["session"].scalar(select(Plan).where(Plan.id == row.id)) is row
