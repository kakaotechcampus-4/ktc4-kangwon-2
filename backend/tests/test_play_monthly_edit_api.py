"""놀이 중심 월간 변경 API 6개 (api-spec §9-7). 확정 · 이력은 후속 PR 이라 여기 없다."""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from play_monthly_factory import CURRICULUM, _Catalogs
from sqlalchemy import select, update
from ssuksak.planning import PlanId
from ssuksak.planning.application.play_monthly_lifecycle import EditPlayMonthlyCell
from ssuksak.planning.domain.play_monthly_plan import PlayMonthlyPlan
from ssuksak.planning.domain.provenance import AuditEventType, GenerationMethod
from ssuksak.planning.domain.theme_reference import ActivationStatus
from test_play_monthly_read_api import LEGACY, _play
from test_weekly_plans_api import _error, world  # noqa: F401

from app.features.plans import play_project
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import SystemClock
from app.main import app

client = TestClient(app)
URL = "/api/plans/monthly/play"
KINDS = ("cell", "content", "add", "delete", "safety", "drill")


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    """공장 계획안의 CREATED 는 2027-02-20 이다. 실제 시각이 앞서면 이력 순서가 깨진다."""
    monkeypatch.setattr(SystemClock, "now", lambda self: datetime(2027, 3, 1, tzinfo=UTC))


@pytest.fixture(autouse=True)
def _approved_curriculum(monkeypatch):
    """운영 자료는 승인 전이라 503 이다. 승인된 가짜 자료를 라우터가 쓰는 저장소 자리에 끼운다."""
    monkeypatch.setattr(play_project, "curriculum_repository", lambda: _Catalogs(CURRICULUM))


def _req(plan, kind, rev, *, item=None):
    """(method, path, kwargs). 그 계획안에서 실제로 바뀌는 입력을 만든다."""
    act = plan.together[0]
    name = act.cell.item_id.value
    week = plan.safety_weeks[0].week_id.value
    if kind == "cell":
        return (
            "PUT",
            f"/cells/{item or plan.theme.item_id.value}",
            {"json": {"value": "새 주제", "expected_revision": rev}},
        )
    if kind == "content":
        ids = ["t.5", "t.6"] if act.content_ids != ("t.5", "t.6") else ["t.1"]
        return (
            "PUT",
            f"/activities/{item or name}/content-ids",
            {"json": {"content_ids": ids, "expected_revision": rev}},
        )
    if kind == "add":
        return "POST", "/activities", {"json": {"section": "together", "expected_revision": rev}}
    if kind == "delete":
        return "DELETE", f"/activities/{item or name}", {"params": {"expected_revision": rev}}
    if kind == "safety":
        cand = plan.safety_candidates[0].cell.item_id.value
        return (
            "PUT",
            f"/safety-weeks/{week}",
            {"json": {"candidate_item_id": cand, "expected_revision": rev}},
        )
    drill = item or plan.drill_candidates[0].cell.item_id.value
    path = f"/drill-candidates/{drill}/copy"
    return "POST", path, {"json": {"expected_revision": rev}}


def _call(row_id, plan, kind, rev=1, **kw):
    method, path, args = _req(plan, kind, rev, **kw)
    return client.request(method, f"{URL}/{row_id}{path}", **args)


def _stored(world, row) -> PlayMonthlyPlan:
    world["session"].expire_all()
    return PostgresPlanRepository(
        world["session"], center_id=row.center_id, kind="monthly", plan_type=PlayMonthlyPlan
    ).get(PlanId(row.plan_ref))


def _row(world, row) -> Plan:
    world["session"].expire_all()
    return world["session"].scalar(select(Plan).where(Plan.id == row.id))


def _last(cell):
    return cell.audit.events[-1]


# ── 모든 경로 공통 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", KINDS)
def test_성공하면_revision_이_하나_오르고_저장된다(world, kind):
    plan, row = _play(world)
    response = _call(row.id, plan, kind)
    assert response.status_code == 200, response.json()
    assert response.json()["revision"] == 2
    assert _row(world, row).revision == 2


@pytest.mark.parametrize("kind", KINDS)
def test_낡은_revision_은_409_이고_아무것도_바꾸지_않는다(world, kind):
    plan, row = _play(world)
    response = _call(row.id, plan, kind, rev=7)
    assert _error(response) == (409, "STALE_WRITE", ["expected_revision"])
    assert _row(world, row).revision == 1 and _stored(world, row) == plan


@pytest.mark.parametrize("kind", KINDS)
def test_확정본은_409_ALREADY_CONFIRMED(world, kind):
    plan, row = _play(world, confirmed=True)
    assert _error(_call(row.id, plan, kind)) == (409, "ALREADY_CONFIRMED", [])
    assert _row(world, row).revision == 1


@pytest.mark.parametrize("kind", KINDS)
def test_남의_원은_404_없는_id_도_404_기존_월간은_409(world, kind):
    plan, _ = _play(world)
    _, theirs = _play(world, mine=False)
    assert _error(_call(theirs.id, plan, kind)) == (404, "NOT_FOUND", ["id"])
    assert _error(_call(999999, plan, kind)) == (404, "NOT_FOUND", ["id"])
    legacy = _call(world["monthly"]["id"], plan, kind)
    assert (_error(legacy), legacy.json()["error"]["message"]) == (
        (409, "GATE_BLOCKED", []),
        LEGACY,
    )


@pytest.mark.parametrize("kind", ("cell", "content", "delete", "drill"))
def test_없는_item_id_는_404(world, kind):
    plan, row = _play(world)
    response = _call(row.id, plan, kind, item="item_nope")
    assert _error(response) == (404, "NOT_FOUND", ["item_id"])


@pytest.mark.parametrize("kind", ("cell", "content", "delete", "drill"))
def test_형식부터_틀린_item_id_는_422_이고_소유보다_먼저다(world, kind):
    plan, row = _play(world)
    assert _error(_call(row.id, plan, kind, item=" ")) == (422, "VALIDATION_FAILED", ["item_id"])
    assert _error(_call(999999, plan, kind, item=" ")) == (422, "VALIDATION_FAILED", ["item_id"])


# ── 칸 글 ─────────────────────────────────────────────────────────────────


def test_칸_글을_고치면_근거_생성방식은_그대로_TEACHER_EDITED_가_남는다(world):
    plan, row = _play(world)
    before = plan.theme
    shown = client.get(f"{URL}/{row.id}").json()["theme"]
    response = client.put(
        f"{URL}/{row.id}/cells/{before.item_id.value}",
        json={"value": "  새 주제  ", "expected_revision": 1},
    )
    theme = response.json()["theme"]
    assert theme["value"] == "새 주제"  # 앞뒤 공백을 턴다
    assert (theme["evidence"], theme["generation"]) == (shown["evidence"], shown["generation"])
    assert theme["generation"]["method"] == before.generation.method.value
    saved = _stored(world, row).theme
    assert (saved.evidence, saved.generation) == (before.evidence, before.generation)
    event = _last(saved)
    assert event.event_type is AuditEventType.TEACHER_EDITED
    assert (event.actor_id.value, event.value_change.before, event.value_change.after) == (
        "user_1",
        before.value,
        "새 주제",
    )


def test_빈_값으로_비울_수_있고_그_다음_빈_값은_422(world):
    plan, row = _play(world)
    url = f"{URL}/{row.id}/cells/{plan.theme.item_id.value}"
    assert (
        client.put(url, json={"value": "   ", "expected_revision": 1}).json()["theme"]["value"]
        == ""
    )
    again = client.put(url, json={"value": "", "expected_revision": 2})
    assert _error(again) == (422, "VALIDATION_FAILED", ["value"])
    assert _row(world, row).revision == 2


def test_현재_값과_같으면_422_이고_낡은_revision_이_먼저다(world):
    plan, row = _play(world)
    url = f"{URL}/{row.id}/cells/{plan.theme.item_id.value}"
    same = {"value": f" {plan.theme.value} "}
    assert _error(client.put(url, json={**same, "expected_revision": 1})) == (
        422,
        "VALIDATION_FAILED",
        ["value"],
    )
    assert _error(client.put(url, json={**same, "expected_revision": 5}))[:2] == (
        409,
        "STALE_WRITE",
    )
    assert _row(world, row).revision == 1


def test_빈_칸을_빈_값으로_고치면_422_이고_쓰지_않은_교사_입력_칸은_MANUAL_이_된다(world):
    plan, row = _play(world)
    cell = plan.teacher_inputs[0]
    assert cell.generation is None
    url = f"{URL}/{row.id}/cells/{cell.item_id.value}"
    assert _error(client.put(url, json={"value": "", "expected_revision": 1}))[0] == 422
    written = client.put(url, json={"value": "직접 씀", "expected_revision": 1})
    assert written.json()["teacher_inputs"][0]["cell"]["generation"]["method"] == "MANUAL"


@pytest.mark.parametrize(
    "body, field",
    [
        ({"value": "가" * 601, "expected_revision": 1}, "value"),
        ({"value": 3, "expected_revision": 1}, "value"),
        ({"expected_revision": 1}, "value"),
        ({"value": "가", "expected_revision": "1"}, "expected_revision"),
        ({"value": "가", "expected_revision": 0}, "expected_revision"),
        ({"value": "가"}, "expected_revision"),
    ],
)
def test_칸_스키마_422_는_소유보다_먼저다(world, body, field):
    plan, row = _play(world)
    for plan_id in (row.id, 999999):
        response = client.put(f"{URL}/{plan_id}/cells/{plan.theme.item_id.value}", json=body)
        assert _error(response) == (422, "VALIDATION_FAILED", [field])


# ── 누리과정 연결 ───────────────────────────────────────────────────────────


def test_연결을_바꾸면_CURRICULUM_근거는_그대로_link_change_만_남는다(world):
    plan, row = _play(world)
    act = plan.together[0]
    response = _call(row.id, plan, "content")
    assert response.json()["together"][0]["content_ids"] == ["t.5", "t.6"]
    saved = _stored(world, row).together[0]
    assert (saved.cell.evidence, saved.cell.generation, saved.cell.value) == (
        act.cell.evidence,
        act.cell.generation,
        act.cell.value,
    )
    event = _last(saved.cell)
    assert event.event_type is AuditEventType.TEACHER_EDITED and event.value_change is None
    assert (event.link_change.before, event.link_change.after) == (act.content_ids, ("t.5", "t.6"))


def test_같은_연결은_200_이고_쓰기_이벤트_revision_이_그대로다(world):
    plan, row = _play(world)
    same = {"content_ids": list(plan.together[0].content_ids), "expected_revision": 1}
    url = f"{URL}/{row.id}/activities/{plan.together[0].cell.item_id.value}/content-ids"
    response = client.put(url, json=same)
    assert response.status_code == 200 and response.json()["revision"] == 1
    assert _row(world, row).revision == 1 and _stored(world, row) == plan
    assert _error(client.put(url, json={**same, "expected_revision": 4}))[:2] == (
        409,
        "STALE_WRITE",
    )


def test_누리과정_판에_없는_ID_는_422(world):
    plan, row = _play(world)
    url = f"{URL}/{row.id}/activities/{plan.together[0].cell.item_id.value}/content-ids"
    response = client.put(url, json={"content_ids": ["t.1", "zzz"], "expected_revision": 1})
    assert _error(response) == (422, "VALIDATION_FAILED", ["content_ids"])
    assert _row(world, row).revision == 1


def test_누리과정_판을_쓸_수_없으면_503(world, monkeypatch):
    plan, row = _play(world)
    pending = replace(CURRICULUM, activation_status=ActivationStatus.PENDING_HUMAN_REVIEW)
    for repository in (_Catalogs(), _Catalogs(pending)):  # 판이 없다 · 승인 전이다
        monkeypatch.setattr(play_project, "curriculum_repository", lambda r=repository: r)
        assert _error(_call(row.id, plan, "content")) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert _row(world, row).revision == 1


def test_운영_자료는_승인_전이라_503(world, monkeypatch):
    monkeypatch.undo()  # 주입을 걷어내면 운영 저장소(승인 전)다
    plan, row = _play(world)
    assert _error(_call(row.id, plan, "content"))[:2] == (503, "DEPENDENCY_UNAVAILABLE")


@pytest.mark.parametrize(
    "ids",
    [[], ["t.1", "t.2", "t.3", "t.4"], ["t.1", "t.1"], [""], ["   "], ["t" * 21], "t.1", [1], None],
)
def test_연결_스키마_422(world, ids):
    plan, row = _play(world)
    url = f"{URL}/{row.id}/activities/{plan.together[0].cell.item_id.value}/content-ids"
    response = client.put(url, json={"content_ids": ids, "expected_revision": 1})
    status, code, fields = _error(response)
    # 원소가 틀리면 위치가 `content_ids.0` 처럼 점 표기로 온다(main.py 공통 변환)
    assert (status, code, {f.split(".")[0] for f in fields}) == (
        422,
        "VALIDATION_FAILED",
        {"content_ids"},
    )


# ── 행 추가 · 삭제 ──────────────────────────────────────────────────────────


def test_행을_더하면_맨_끝에_빈_행이_붙고_새_칸은_generation_null(world):
    plan, row = _play(world)
    body = client.post(
        f"{URL}/{row.id}/activities", json={"section": "free_play", "expected_revision": 1}
    ).json()
    new = body["free_play"][-1]
    assert len(body["free_play"]) == len(plan.free_play) + 1 and len(body["together"]) == len(
        plan.together
    )
    assert (new["name"]["generation"], new["name"]["value"], new["content_ids"]) == (None, "", [])
    assert new["description"]["generation"] is None
    stored = _stored(world, row)
    created = _last(stored.free_play[-1].cell)
    assert created.event_type is AuditEventType.CREATED and created.actor_id.value == "user_1"
    assert _last(stored).event_type is AuditEventType.ARRANGEMENT_CHANGED


def test_행을_지우면_문서에서_빠지고_그_칸은_404_이고_id_는_다시_안_쓴다(world):
    plan, row = _play(world)
    gone = plan.together[0]
    response = _call(row.id, plan, "delete")
    assert response.status_code == 200
    assert gone.cell.item_id.value not in [a["activity_id"] for a in response.json()["together"]]
    assert _last(_stored(world, row)).event_type is AuditEventType.ARRANGEMENT_CHANGED
    url = f"{URL}/{row.id}/cells/{gone.cell.item_id.value}"
    assert _error(client.put(url, json={"value": "x", "expected_revision": 2})) == (
        404,
        "NOT_FOUND",
        ["item_id"],
    )
    again = _call(row.id, plan, "delete", rev=2)
    assert _error(again) == (404, "NOT_FOUND", ["item_id"])
    added = client.post(
        f"{URL}/{row.id}/activities", json={"section": "together", "expected_revision": 2}
    ).json()["together"][-1]
    assert added["activity_id"] != gone.cell.item_id.value


@pytest.mark.parametrize("bad", [None, "0", "abc", "3.5", "-1", ""])
def test_삭제의_쿼리_revision_은_1_이상_정수만(world, bad):
    plan, row = _play(world)
    params = {} if bad is None else {"expected_revision": bad}
    url = f"{URL}/{row.id}/activities/{plan.together[0].cell.item_id.value}"
    response = client.delete(url, params=params)
    assert _error(response) == (422, "VALIDATION_FAILED", ["expected_revision"])
    assert _row(world, row).revision == 1


def test_행_추가_스키마_422(world):
    _, row = _play(world)
    for body in ({"section": "both", "expected_revision": 1}, {"expected_revision": 1}):
        response = client.post(f"{URL}/{row.id}/activities", json=body)
        assert _error(response) == (422, "VALIDATION_FAILED", ["section"])


# ── 안전교육 주별 배치 ───────────────────────────────────────────────────────


def test_안전_후보를_두고_null_로_비운다(world):
    plan, row = _play(world)
    placed = _call(row.id, plan, "safety").json()["safety_weeks"][0]
    cand = plan.safety_candidates[0].cell.item_id.value
    assert placed["candidate_item_id"] == cand
    assert _last(_stored(world, row)).event_type is AuditEventType.ARRANGEMENT_CHANGED
    url = f"{URL}/{row.id}/safety-weeks/{placed['week_id']}"
    cleared = client.put(url, json={"candidate_item_id": None, "expected_revision": 2})
    assert (
        cleared.status_code == 200
        and cleared.json()["safety_weeks"][0]["candidate_item_id"] is None
    )
    assert cleared.json()["revision"] == 3


def test_같은_배치는_200_이고_무변경_낡은_revision_이_먼저다(world):
    plan, row = _play(world)
    url = f"{URL}/{row.id}/safety-weeks/{plan.safety_weeks[0].week_id.value}"
    same = {"candidate_item_id": None}  # 처음에는 비어 있다
    ok = client.put(url, json={**same, "expected_revision": 1})
    assert ok.status_code == 200 and ok.json()["revision"] == 1 and _stored(world, row) == plan
    assert _error(client.put(url, json={**same, "expected_revision": 3}))[:2] == (
        409,
        "STALE_WRITE",
    )


def test_안전_배치_404_와_422(world):
    plan, row = _play(world)
    week = plan.safety_weeks[0].week_id.value
    put = lambda wk, body: client.put(f"{URL}/{row.id}/safety-weeks/{wk}", json=body)  # noqa: E731
    base = {"expected_revision": 1}
    assert _error(put("2027-04-W9", {**base, "candidate_item_id": None})) == (
        404,
        "NOT_FOUND",
        ["week_id"],
    )
    assert _error(put(week, {**base, "candidate_item_id": "item_nope"})) == (
        422,
        "VALIDATION_FAILED",
        ["candidate_item_id"],
    )
    assert _error(put(week, {**base, "candidate_item_id": ""}))[2] == ["candidate_item_id"]
    assert _error(put("not-a-week", {**base, "candidate_item_id": None})) == (
        422,
        "VALIDATION_FAILED",
        ["week_id"],
    )
    # 키가 없다 · 문자열이 아니다
    assert _error(put(week, base)) == (422, "VALIDATION_FAILED", ["candidate_item_id"])
    assert _error(put(week, {**base, "candidate_item_id": 5}))[2] == ["candidate_item_id"]
    assert _row(world, row).revision == 1


# ── 훈련 후보 복사 ──────────────────────────────────────────────────────────


def test_훈련_후보를_복사하면_RULE_ONLY_drill_copy_이고_CANDIDATE_COPIED_가_남는다(world):
    plan, row = _play(world)
    source = plan.drill_candidates[0].cell
    body = _call(row.id, plan, "drill").json()
    cell = next(t for t in body["teacher_inputs"] if t["key"] == "fire_disaster_drill")["cell"]
    assert (cell["value"], cell["generation"]["method"], cell["generation"]["rule_id"]) == (
        source.value,
        "RULE_ONLY",
        "play_monthly.drill_copy",
    )
    assert cell["evidence"] == [e for e in body["drill_candidates"][0]["cell"]["evidence"]]
    stored = next(
        t for t in _stored(world, row).teacher_inputs if t.semantic_key == "fire_disaster_drill"
    )
    event = _last(stored)
    assert event.event_type is AuditEventType.CANDIDATE_COPIED
    assert (event.copied_from, event.actor_id.value) == (source.item_id, "user_1")
    assert stored.generation.method is GenerationMethod.RULE_ONLY


def test_이미_복사한_후보는_200_이고_무변경_낡은_revision_이_먼저다(world):
    plan, row = _play(world)
    assert _call(row.id, plan, "drill").json()["revision"] == 2
    again = _call(row.id, plan, "drill", rev=2)
    assert again.status_code == 200 and again.json()["revision"] == 2
    assert _row(world, row).revision == 2
    assert _error(_call(row.id, plan, "drill", rev=1))[:2] == (409, "STALE_WRITE")


def test_빈_훈련_후보를_복사하면_422(world):
    def blank_first(plan):
        first = plan.drill_candidates[0]
        return replace(
            plan,
            drill_candidates=(
                replace(first, cell=replace(first.cell, value="")),
                *plan.drill_candidates[1:],
            ),
        )

    plan, row = _play(world, edit=blank_first)
    response = _call(row.id, plan, "drill")
    assert _error(response) == (422, "VALIDATION_FAILED", ["item_id"])
    assert _row(world, row).revision == 1


# ── 조건부 저장 ─────────────────────────────────────────────────────────────


def test_읽은_뒤_다른_화면이_먼저_저장하면_409_이고_덮어쓰지_않는다(world, monkeypatch):
    plan, row = _play(world)
    original = EditPlayMonthlyCell.execute

    def bumped_first(self, command):  # Core 가 도는 사이 다른 요청이 revision 을 올린다
        world["session"].execute(update(Plan).where(Plan.id == row.id).values(revision=2))
        world["session"].commit()
        return original(self, command)

    monkeypatch.setattr(EditPlayMonthlyCell, "execute", bumped_first)
    response = _call(row.id, plan, "cell")
    assert _error(response) == (409, "STALE_WRITE", ["expected_revision"])
    assert _row(world, row).revision == 2 and _stored(world, row) == plan


def test_공백뿐인_연결_ID_는_없는_계획안에도_먼저_422(world):
    response = client.put(
        f"{URL}/999999/activities/item_1/content-ids",
        json={"content_ids": ["   "], "expected_revision": 1},
    )
    status, code, fields = _error(response)
    assert (status, code, {f.split(".")[0] for f in fields}) == (
        422,
        "VALIDATION_FAILED",
        {"content_ids"},
    )
