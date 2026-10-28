"""놀이 중심 월간 서버 ④ — 확정 · 변경 이력 (api-spec §9-7)."""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from ssuksak.planning.domain.provenance import AuditEventType
from test_play_monthly_edit_api import (  # noqa: F401
    LEGACY,
    URL,
    _approved_curriculum,
    _call,
    _clock,
    _row,
    _stored,
)
from test_play_monthly_read_api import _play
from test_weekly_plans_api import _error, world  # noqa: F401

from app.features.plans.models import Plan
from app.features.plans.queries import confirmed_monthly_plans
from app.main import app

client = TestClient(app)
KEYS = {
    "type", "occurred_at", "scope", "item_id", "actor", "system_actor", "value_change",
    "generation_change", "link_change", "arrangement_change", "copied_from",
}  # fmt: skip


def _confirm(row_id, rev=None):
    return client.post(
        f"{URL}/{row_id}/confirm", json={} if rev is None else {"expected_revision": rev}
    )


def _audit(row_id):
    response = client.get(f"{URL}/{row_id}/audit")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _step(row_id, rev, method, path, **kw):
    """변경 하나를 부르고 새 revision 을 돌려준다."""
    response = client.request(method, f"{URL}/{row_id}{path}", **kw)
    assert response.status_code == 200, response.json()
    return response.json()["revision"]


def _blank_cell(row_id, rev, item):
    return _step(row_id, rev, "PUT", f"/cells/{item}", json={"value": "", "expected_revision": rev})


# ── 확정 ────────────────────────────────────────────────────────────────────


def test_확정하면_본문_전체가_저장된다(world):
    plan, row = _play(world)
    response = _confirm(row.id, 1)
    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["status"], body["revision"]) == ("CONFIRMED", 2) and body["confirmed_at"]
    stored = _stored(world, row)
    assert stored.audit.events[-1].event_type is AuditEventType.CONFIRMED
    assert (_row(world, row).status, _row(world, row).revision) == ("CONFIRMED", 2)


def test_확정_재호출은_옛_revision_이나_본문_없이도_200_이고_Core_를_안_부른다(world, monkeypatch):
    _, row = _play(world)
    assert _confirm(row.id, 1).status_code == 200
    saved = _row(world, row).body

    def boom(*a, **k):
        raise AssertionError("재호출이 Core 를 불렀다")

    monkeypatch.setattr(
        "app.features.plans.play_monthly_router.ConfirmPlayMonthlyPlan.execute", boom
    )
    for rev in (None, 1, 99):
        again = _confirm(row.id, rev)
        assert again.status_code == 200 and again.json()["revision"] == 2
    assert _row(world, row).body == saved and _row(world, row).revision == 2


def test_초안은_revision_이_없으면_422_옛_revision_이면_409(world):
    _, row = _play(world)
    assert _error(_confirm(row.id)) == (422, "VALIDATION_FAILED", ["expected_revision"])
    assert _error(client.post(f"{URL}/{row.id}/confirm")) == (
        422,
        "VALIDATION_FAILED",
        ["expected_revision"],
    )
    for bad in ("1", True, 0, 1.5):
        response = client.post(f"{URL}/{row.id}/confirm", json={"expected_revision": bad})
        assert _error(response) == (422, "VALIDATION_FAILED", ["expected_revision"])
    assert _error(_confirm(row.id, 7)) == (409, "STALE_WRITE", ["expected_revision"])
    assert _row(world, row).status == "DRAFT" and _row(world, row).revision == 1


def test_남의_원은_404_기존_월간_id_는_409(world):
    _, theirs = _play(world, mine=False)
    assert _error(_confirm(theirs.id, 1)) == (404, "NOT_FOUND", ["id"])
    assert _error(_confirm(999999, 1)) == (404, "NOT_FOUND", ["id"])
    legacy = _confirm(world["monthly"]["id"], 1)
    assert (_error(legacy), legacy.json()["error"]["message"]) == (
        (409, "GATE_BLOCKED", []),
        LEGACY,
    )


def test_확정_뒤_고치기는_409(world):
    plan, row = _play(world)
    assert _confirm(row.id, 1).status_code == 200
    for kind in ("cell", "content", "add", "delete", "safety", "drill"):
        assert _error(_call(row.id, plan, kind, rev=2)) == (409, "ALREADY_CONFIRMED", [])


def test_주제를_비우면_422_theme(world):
    plan, row = _play(world)
    rev = _blank_cell(row.id, 1, plan.theme.item_id.value)
    assert _error(_confirm(row.id, rev)) == (422, "VALIDATION_FAILED", ["theme"])
    assert _row(world, row).status == "DRAFT" and _row(world, row).revision == rev


@pytest.mark.parametrize("section", ("together", "free_play"))
def test_한_구역의_행이_0이면_422_그_구역(world, section):
    plan, row = _play(world)
    rev = 1
    for act in getattr(plan, section):
        rev = _step(
            row.id, rev, "DELETE", f"/activities/{act.cell.item_id.value}",
            params={"expected_revision": rev},
        )  # fmt: skip
    assert _error(_confirm(row.id, rev)) == (422, "VALIDATION_FAILED", [section])


@pytest.mark.parametrize("section", ("together", "free_play"))
def test_이름이_빈_행은_422_구역_점_item_id(world, section):
    plan, row = _play(world)
    item = getattr(plan, section)[0].cell.item_id.value
    rev = _blank_cell(row.id, 1, item)
    assert _error(_confirm(row.id, rev)) == (422, "VALIDATION_FAILED", [f"{section}.{item}"])


@pytest.mark.parametrize("section", ("together", "free_play"))
def test_연결이_0개인_행은_422_content_ids(world, section):
    plan, row = _play(world)
    added = client.post(
        f"{URL}/{row.id}/activities", json={"section": section, "expected_revision": 1}
    ).json()
    new = added[section][-1]
    rev = _step(
        row.id, 2, "PUT", f"/cells/{new['name']['item_id']}",
        json={"value": "이름만", "expected_revision": 2},
    )  # fmt: skip
    response = _confirm(row.id, rev)
    assert _error(response) == (
        422,
        "VALIDATION_FAILED",
        [f"{section}.{new['activity_id']}.content_ids"],
    )


# ── 변경 이력 ───────────────────────────────────────────────────────────────


def test_이력은_키_11개가_늘_오고_CREATED_는_계획안_1건_칸마다_1건(world):
    plan, row = _play(world)
    items = _audit(row.id)
    assert all(set(e) == KEYS for e in items)
    created = [e for e in items if e["type"] == "CREATED"]
    assert [e["scope"] for e in created].count("PLAN") == 1
    cells = [e for e in created if e["scope"] == "CELL"]
    assert [e["item_id"] for e in cells] == [c.item_id.value for c in plan.cells()]
    assert created[0]["scope"] == "PLAN" and created[0]["system_actor"] and not created[0]["actor"]


def test_칸_고치기_안전_배치_훈련_복사가_이력에_남는다(world):
    plan, row = _play(world)
    for kind, rev in (("cell", 1), ("safety", 2), ("drill", 3)):
        assert _call(row.id, plan, kind, rev=rev).status_code == 200
    items = _audit(row.id)
    edited, arranged, copied = (
        next(e for e in items if e["type"] == t)
        for t in ("TEACHER_EDITED", "ARRANGEMENT_CHANGED", "CANDIDATE_COPIED")
    )
    assert edited["scope"] == "CELL" and edited["item_id"] == plan.theme.item_id.value
    assert edited["actor"].startswith("user_") and edited["system_actor"] is None
    assert edited["value_change"]["after"] == "새 주제"
    assert arranged["scope"] == "PLAN" and arranged["item_id"] is None
    assert arranged["arrangement_change"]["after"] == [plan.safety_candidates[0].cell.item_id.value]
    drill = plan.drill_candidates[0].cell.item_id.value
    assert copied["scope"] == "CELL" and copied["copied_from"] == drill
    assert copied["value_change"] and copied["item_id"] != drill


def test_연결을_바꾸면_link_change(world):
    plan, row = _play(world)
    assert _call(row.id, plan, "content").status_code == 200
    edited = next(e for e in _audit(row.id) if e["type"] == "TEACHER_EDITED")
    assert edited["link_change"]["after"] and edited["link_change"]["catalog_version"]
    assert edited["value_change"] is None


def test_지운_행의_칸_이벤트도_싣고_순서는_시각_계획안_활성_칸_지운_칸(world):
    plan, row = _play(world)
    gone = plan.together[0]
    ids = {gone.cell.item_id.value, gone.description.item_id.value}
    assert _call(row.id, plan, "delete").status_code == 200
    items = _audit(row.id)
    assert ids <= {e["item_id"] for e in items}
    shown = {a["activity_id"] for a in client.get(f"{URL}/{row.id}").json()["together"]}
    assert gone.cell.item_id.value not in shown
    created = [e for e in items if e["type"] == "CREATED" and e["scope"] == "CELL"]
    flags = [e["item_id"] in ids for e in created]
    assert flags == sorted(flags) and flags[-2:] == [True, True]  # 지운 칸은 맨 뒤
    times = [e["occurred_at"] for e in items]
    assert times == sorted(times)
    # 같은 시각이면 계획안 단위가 칸 단위보다 앞이다 — 칸 고치기 뒤에 배치를 해도 그렇다
    assert _call(row.id, plan, "cell", rev=2, item=plan.theme.item_id.value).status_code == 200
    assert _call(row.id, plan, "safety", rev=3).status_code == 200
    tail = [(e["type"], e["scope"]) for e in _audit(row.id)[-3:]]
    assert tail == [
        ("ARRANGEMENT_CHANGED", "PLAN"),
        ("ARRANGEMENT_CHANGED", "PLAN"),
        ("TEACHER_EDITED", "CELL"),
    ]


def test_확정하면_이력_끝에_CONFIRMED_가_붙는다(world):
    _, row = _play(world)
    assert _confirm(row.id, 1).status_code == 200
    last = _audit(row.id)[-1]
    assert (last["type"], last["scope"], last["item_id"]) == ("CONFIRMED", "PLAN", None)
    assert last["actor"].startswith("user_")
    assert _confirm(row.id, 2).status_code == 200  # 재호출도 이력을 안 더한다
    assert [e["type"] for e in _audit(row.id)].count("CONFIRMED") == 1


def test_무변경_실패_요청은_이력을_더하지_않는다(world):
    plan, row = _play(world)
    before = _audit(row.id)
    week = plan.safety_weeks[0].week_id.value
    same = client.put(
        f"{URL}/{row.id}/safety-weeks/{week}",
        json={"candidate_item_id": None, "expected_revision": 1},
    )
    assert same.status_code == 200
    assert _call(row.id, plan, "cell", rev=9).status_code == 409
    same_value = client.put(
        f"{URL}/{row.id}/cells/{plan.theme.item_id.value}",
        json={"value": plan.theme.value, "expected_revision": 1},
    )
    assert same_value.status_code == 422
    assert _confirm(row.id, 9).status_code == 409
    assert _audit(row.id) == before


def test_이력의_소유_404_기존_월간_409(world):
    _, theirs = _play(world, mine=False)
    assert client.get(f"{URL}/{theirs.id}/audit").status_code == 404
    assert client.get(f"{URL}/999999/audit").status_code == 404
    assert client.get(f"{URL}/{world['monthly']['id']}/audit").status_code == 409


def test_이력_시각은_UTC_Z(world):
    _, row = _play(world)
    assert all(e["occurred_at"].endswith("Z") for e in _audit(row.id))


# ── 평가제 4-1 ──────────────────────────────────────────────────────────────


def test_놀이_월간_확정본은_평가제_4_1_에_센다(world):
    _, row = _play(world)
    center = world["mine"]["center"]
    before = confirmed_monthly_plans(world["session"], center)  # 기존 월간 확정본이 하나 있다
    assert _confirm(row.id, 1).status_code == 200
    world["session"].expire_all()
    added = [p for p in confirmed_monthly_plans(world["session"], center) if p not in before]
    stored = world["session"].scalar(select(Plan).where(Plan.id == row.id))
    assert [(p.plan_id, p.class_id, p.year, p.month) for p in added] == [
        (row.id, int(stored.classroom_ref), 2027, 4)
    ]
