"""놀이 프로젝트형 확정 · 변경 이력 API (api-spec §7 · §7-1, ADR-044 §4 · §6)."""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from test_plans_play_project import _blocked, saved, world  # noqa: F401
from test_play_project_save_api import (  # noqa: F401
    EMPTY,
    KEYS,
    _error,
    _events,
    _item_id,
    _put_cell,
    _put_selection,
    _stored,
    _unchanged,
    live,
)

from app.db import engine
from app.features.centers.models import Center
from app.features.plans import play_project
from app.features.plans import router as plans_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.main import app

from ssuksak.planning import ActorId, PlanId  # isort: skip
from ssuksak.planning.domain.play_project_plan import PlayProjectYearlyPlan  # isort: skip

client = TestClient(app)
FIVE = [f"cand{n}" for n in range(1, 6)]
FULL = {key: FIVE for key in KEYS}


def _confirm(row, revision=None):
    body = None if revision is None else {"expected_revision": revision}
    return client.post(f"/api/plans/annual/{row.id}/confirm", json=body)


def _select_all(row, revision=1):
    assert _put_selection(row, FULL, revision).status_code == 200


def test_확정_성공은_상태_revision_actor_이벤트_confirmed_at_을_남긴다(world, saved):
    _, row = saved
    _select_all(row)

    response = _confirm(row, 2)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["revision"], body["format"]) == ("CONFIRMED", 3, "PLAY_PROJECT")
    stored = _stored(world, row)
    confirmed = _events(stored, "CONFIRMED")
    assert [e.actor_id.value for e in confirmed] == ["user_1"]  # 본문에 이벤트가 남는다
    assert (row.status, row.revision) == ("CONFIRMED", 3)
    assert row.confirmed_at is not None


def test_구간이_부족하면_422_에_접두사_없는_구간_키가_구간_순서대로(world, saved):
    plan, row = saved
    _put_selection(row, {**FULL, "m09_m11": FIVE[:3], "m12_m02": []})
    before = _stored(world, row)  # 실패 전에 잡는다

    _error(_confirm(row, 2), 422, "VALIDATION_FAILED", ["m09_m11", "m12_m02"])

    _unchanged(world, row, before, revision=2)
    assert row.status == "DRAFT" and row.confirmed_at is None


def test_이미_확정이면_본문이_없어도_옛_revision_이어도_200_이고_쓰지_않는다(
    world, saved, monkeypatch
):
    _, row = saved
    _select_all(row)
    first = _confirm(row, 2).json()
    confirmed_at, body = row.confirmed_at, row.body

    def boom(*args, **kwargs):
        raise AssertionError("확정된 계획안에 Core · 쓰기가 불렸다")

    monkeypatch.setattr(plans_router.ConfirmPlayProjectPlan, "execute", boom)
    monkeypatch.setattr(PostgresPlanRepository, "update_if_revision", boom)

    for revision in (None, 1, 2, 99):
        again = _confirm(row, revision)
        assert again.status_code == 200, again.text
        assert again.json() == first

    world["session"].refresh(row)
    assert (row.revision, row.confirmed_at, row.body) == (3, confirmed_at, body)


def test_미확정_놀이형_본문_검사(world, saved):
    _, row = saved
    _select_all(row)
    plan = _stored(world, row)

    _error(_confirm(row), 422, "VALIDATION_FAILED", ["expected_revision"])
    _error(
        client.post(f"/api/plans/annual/{row.id}/confirm", json={}),
        422,
        "VALIDATION_FAILED",
        ["expected_revision"],
    )
    _error(_confirm(row, 1), 409, "STALE_WRITE", ["expected_revision"])
    _error(
        client.post(f"/api/plans/annual/{row.id}/confirm", json={"expected_revision": "3"}),
        422,
        "VALIDATION_FAILED",
        ["expected_revision"],
    )
    _unchanged(world, row, plan, revision=2)


def _others_row(world, confirmed):
    from test_plans_play_project import _klass, _plan

    session = world["session"]
    other = Center(
        name="다른어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    session.add(other)
    session.flush()
    plan = _plan(str(_klass(session, other, "남의반").id))
    if confirmed:
        plan = plan.confirm(actor_id=ActorId("user_9"), occurred_at=datetime.now(UTC))
    PostgresPlanRepository(
        session, center_id=other.id, kind="annual", plan_type=PlayProjectYearlyPlan
    ).save(plan.plan_id, plan)
    session.commit()
    return session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))


@pytest.mark.parametrize("confirmed", [False, True], ids=["DRAFT", "CONFIRMED"])
def test_남의_원_계획안의_확정_이력은_404(world, confirmed):
    row = _others_row(world, confirmed)
    before = (row.body, row.revision, row.status)

    _error(_confirm(row, 1), 404, "NOT_FOUND", ["id"])
    _error(_confirm(row), 404, "NOT_FOUND", ["id"])
    _error(client.get(f"/api/plans/annual/{row.id}/audit"), 404, "NOT_FOUND", ["id"])

    world["session"].refresh(row)
    assert (row.body, row.revision, row.status) == before


def test_없는_계획안은_404(world):
    _error(
        client.post("/api/plans/annual/999999/confirm", json={"expected_revision": 1}),
        404,
        "NOT_FOUND",
        ["id"],
    )
    _error(client.get("/api/plans/annual/999999/audit"), 404, "NOT_FOUND", ["id"])


def test_검사_순서_스키마_다음_revision_다음_Core(world, saved):
    plan, row = saved
    _put_selection(row, {**FULL, "m09_m11": FIVE[:3]})  # 부족한 DRAFT, revision 2
    url = f"/api/plans/annual/{row.id}/confirm"
    snapshot = (_stored(world, row), row.revision)

    # 구간이 부족해도 옛 revision 이 먼저다
    _error(_confirm(row, 1), 409, "STALE_WRITE", ["expected_revision"])
    _error(_confirm(row, 2), 422, "VALIDATION_FAILED", ["m09_m11"])
    # 타입이 틀리면 스키마가 먼저다 — 없는 계획안이어도
    bad = {"expected_revision": "3"}
    _error(client.post(url, json=bad), 422, "VALIDATION_FAILED", ["expected_revision"])
    _error(
        client.post("/api/plans/annual/999999/confirm", json=bad),
        422,
        "VALIDATION_FAILED",
        ["expected_revision"],
    )
    assert snapshot == (_stored(world, row), row.revision)

    _put_selection(row, FULL, revision=2)
    _confirm(row, 3)
    _error(client.post(url, json=bad), 422, "VALIDATION_FAILED", ["expected_revision"])
    assert client.post(url, json={}).status_code == 200  # 확정 재호출은 본문이 비어도 200


def _bump(i):
    with Session(engine) as other:
        other.execute(update(Plan).where(Plan.id == i).values(revision=Plan.revision + 1))
        other.commit()


def _really_confirm(i):
    """다른 연결이 Core 확정 결과 본문을 저장 · 커밋한다(더블클릭의 첫 요청)."""
    with Session(engine) as other:
        row = other.scalar(select(Plan).where(Plan.id == i))
        repo = PostgresPlanRepository(
            other, center_id=row.center_id, kind="annual", plan_type=PlayProjectYearlyPlan
        )
        plan = repo.get(PlanId(row.plan_ref))
        done = plan.confirm(actor_id=ActorId("user_1"), occurred_at=datetime.now(UTC))
        assert repo.update_if_revision(plan.plan_id, done, expected_revision=row.revision)
        other.commit()


def _delete(i):
    with Session(engine) as other:
        other.execute(delete(Plan).where(Plan.id == i))
        other.commit()


def _after(monkeypatch, name, act, row_id):
    original = getattr(plans_router, name)

    done = []

    def wrapped(*args, **kwargs):
        result = original(*args, **kwargs)
        if not done:  # 처음 한 번만 끼어든다
            done.append(1)
            act(row_id)
        return result

    monkeypatch.setattr(plans_router, name, wrapped)


def test_읽은_뒤_쓰기_전에_revision_이_오르면_409(live, monkeypatch):
    row = type("R", (), {"id": live["row"]})()
    assert _put_selection(row, FULL).status_code == 200
    _after(monkeypatch, "_play_plan", _bump, live["row"])

    _error(_confirm(row, 2), 409, "STALE_WRITE", ["expected_revision"])


def test_읽은_뒤_쓰기_전에_삭제되면_404(live, monkeypatch):
    row = type("R", (), {"id": live["row"]})()
    assert _put_selection(row, FULL).status_code == 200
    _after(monkeypatch, "_play_plan", _delete, live["row"])

    _error(_confirm(row, 2), 404, "NOT_FOUND", ["id"])


def test_더블클릭_두_번째_요청은_첫_요청이_확정한_본문으로_200(live, monkeypatch):
    row = type("R", (), {"id": live["row"]})()
    assert _put_selection(row, FULL).status_code == 200
    _after(monkeypatch, "_play_plan", _really_confirm, live["row"])

    response = _confirm(row, 2)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["revision"]) == ("CONFIRMED", 3)
    with Session(engine) as session:
        stored = session.scalar(select(Plan).where(Plan.id == live["row"]))
        assert (stored.status, stored.revision) == ("CONFIRMED", 3)
        kinds = [e["event_type"] for e in stored.body["audit"]["events"]]
        assert kinds.count("CONFIRMED") == 1


def test_읽은_뒤_다른_연결이_확정하면_선택_저장은_409(live, monkeypatch):
    row = type("R", (), {"id": live["row"]})()
    _after(monkeypatch, "_play_read", _really_confirm, live["row"])

    _error(_put_selection(row, FULL), 409, "ALREADY_CONFIRMED", [])


def test_월별_확정은_조회와_잠금_사이에_지워지면_404(live, monkeypatch):
    row = type("R", (), {"id": live["row"]})()
    monkeypatch.setattr(plans_router, "format_of", lambda r: "MONTHLY_THEME")
    _after(monkeypatch, "_row", _delete, live["row"])  # 첫 읽기 직후 삭제

    _error(_confirm(row), 404, "NOT_FOUND", ["id"])


def test_확정_뒤_선택_저장도_칸_편집도_409(world, saved):
    plan, row = saved
    _select_all(row)
    _confirm(row, 2)

    _error(_put_selection(row, EMPTY, 3), 409, "ALREADY_CONFIRMED", [])
    _error(_put_cell(row, _item_id(plan, 0, 1), "새 값", 3), 409, "ALREADY_CONFIRMED", [])


def test_월별_주제형_확정은_본문이_없어도_빈_객체여도_기존_응답(world):
    created = client.post(
        "/api/plans/annual",
        json={"format": "MONTHLY_THEME", "class_id": world["theme"].id, "form_id": None},
    ).json()
    url = f"/api/plans/annual/{created['id']}/confirm"

    first = client.post(url)
    again = client.post(url, json={})

    assert first.status_code == again.status_code == 200, first.text
    assert set(first.json()) == {"id", "status", "confirmed_at"}
    assert first.json()["status"] == "CONFIRMED"
    assert again.json() == first.json()


def test_이력은_네_종류를_시간순으로_주소와_변화를_싣는다(world, saved):
    plan, row = saved
    item_id = _item_id(plan, 0, 1)
    _put_selection(row, {**FULL, "m03_m05": ["cand5", "cand1", "cand2", "cand3", "cand4"]})
    _put_cell(row, item_id, "고친 놀이", revision=2)
    _confirm(row, 3)

    response = client.get(f"/api/plans/annual/{row.id}/audit")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert all(
        set(i) == {
            "type", "occurred_at", "month", "actor", "system_actor", "value_change",
            "item_id", "selection_change",
        }
        for i in items
    )  # fmt: skip
    times = [i["occurred_at"] for i in items]
    assert times == sorted(times)
    assert all(i["month"] is None for i in items)
    by_type = {}
    for i in items:
        by_type.setdefault(i["type"], []).append(i)
    assert set(by_type) == {"CREATED", "CANDIDATES_SELECTED", "TEACHER_EDITED", "CONFIRMED"}
    assert [i["type"] for i in items if i["type"] != "CREATED"] == [
        "CANDIDATES_SELECTED",
        "CANDIDATES_SELECTED",
        "CANDIDATES_SELECTED",
        "CANDIDATES_SELECTED",
        "TEACHER_EDITED",
        "CONFIRMED",
    ]
    first = by_type["CANDIDATES_SELECTED"][0]
    assert first["selection_change"] == {
        "period_key": "m03_m05",
        "before": [],
        "after": ["cand5", "cand1", "cand2", "cand3", "cand4"],
    }
    assert (first["item_id"], first["value_change"], first["actor"]) == (None, None, "user_1")
    (edited,) = by_type["TEACHER_EDITED"]
    assert (edited["item_id"], edited["value_change"]) == (
        item_id,
        {"before": "m03_m05 놀이 1", "after": "고친 놀이"},
    )
    assert edited["selection_change"] is None
    (done,) = by_type["CONFIRMED"]
    assert (done["actor"], done["item_id"], done["value_change"], done["selection_change"]) == (
        "user_1",
        None,
        None,
        None,
    )


def test_이력_순서는_고르기_칸_편집_확정이고_시각이_오름차순(world, saved):
    plan, row = saved
    _select_all(row)
    _put_cell(row, _item_id(plan, 0, 1), "고친 놀이", revision=2)
    _confirm(row, 3)

    items = client.get(f"/api/plans/annual/{row.id}/audit").json()["items"]

    real = [i for i in items if i["type"] != "CREATED"]
    assert [i["type"] for i in real] == ["CANDIDATES_SELECTED"] * 4 + [
        "TEACHER_EDITED",
        "CONFIRMED",
    ]
    times = [i["occurred_at"] for i in items]
    assert times == sorted(times)


def test_선택을_풀어도_그_칸의_TEACHER_EDITED_가_이력에_남는다(world, saved):
    plan, row = saved
    item_id = _item_id(plan, 0, 1)
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    _put_cell(row, item_id, "고친 놀이", revision=2)
    _put_selection(row, EMPTY, revision=3)

    items = client.get(f"/api/plans/annual/{row.id}/audit").json()["items"]

    edited = [i for i in items if i["type"] == "TEACHER_EDITED"]
    assert [(i["item_id"], i["value_change"]["after"]) for i in edited] == [(item_id, "고친 놀이")]


def test_이력은_DRAFT_에도_열린다(world, saved):
    _, row = saved
    items = client.get(f"/api/plans/annual/{row.id}/audit").json()["items"]
    assert items and {i["type"] for i in items} == {"CREATED"}


def test_월별_주제형_이력은_여섯_키_그대로(world):
    created = client.post(
        "/api/plans/annual",
        json={"format": "MONTHLY_THEME", "class_id": world["theme"].id, "form_id": None},
    ).json()

    items = client.get(f"/api/plans/annual/{created['id']}/audit").json()["items"]

    assert items
    assert all(
        set(i) == {"type", "occurred_at", "month", "actor", "system_actor", "value_change"}
        for i in items
    )


def test_이력_모음은_계획안과_모든_칸을_안정_정렬한다(world, saved):
    plan, _ = saved
    out = play_project.audit_out(plan)
    # 후보 40개 × 칸 4개 = 160 CREATED. 계획안 단위 이벤트가 없으면 칸 것만 온다
    assert len(out.items) == len(plan.audit.events) + 160
