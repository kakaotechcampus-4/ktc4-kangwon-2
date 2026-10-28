"""놀이 중심 월간 서버 ② — 조회 · 목록 · 삭제 · 생성 게이트(503). 계약은 api-spec §9-7."""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from play_monthly_factory import make_play_monthly, save_play_monthly
from sqlalchemy import func, select
from ssuksak.planning.domain.plan import PlanStatus
from test_plans_play_project import _approved as _approved_play  # noqa: F401
from test_plans_play_project import _plan
from test_weekly_plans_api import _approved, _create, _error, world  # noqa: F401

from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.main import app

client = TestClient(app)
URL = "/api/plans/monthly/play"
LEGACY = "기존 월간계획안은 /api/plans/monthly 경로로 다룹니다."
SINGLE_KEYS = {
    "id", "class_id", "school_year", "month", "target_month", "status", "revision", "format",
    "format_version", "created_at", "confirmed_at", "target_ages", "weeks", "parent", "theme",
    "rationale", "together", "free_play", "habits", "safety_candidates", "safety_weeks", "health",
    "nutrition", "drill_candidates", "teacher_inputs", "notices",
}  # fmt: skip


def _play(world, *, month=4, mine=True, confirmed=False, year=2027, edit=None):
    side = world["mine" if mine else "other"]
    plan = make_play_monthly(str(side["class"]), year, month)
    if confirmed:
        plan = replace(plan, status=PlanStatus.CONFIRMED)
    if edit is not None:
        plan = edit(plan)
    # 부모 plan_ref(parent-1)를 가진 연간 행이 있어야 annual_plan_id 가 정수로 나온다
    annual = world["session"].scalar(
        select(Plan).where(Plan.kind == "annual", Plan.center_id == side["center"])
    )
    if annual is not None:
        annual.plan_ref = "parent-1"
    return plan, save_play_monthly(world["session"], side["center"], plan)


def _annual(world, *, confirmed):
    """반의 연간을 놀이 프로젝트형으로 바꿔 놓는다. 월간은 비운다."""
    mine, session = world["mine"], world["session"]
    session.query(Plan).filter(Plan.center_id == mine["center"]).delete()
    plan = _plan(str(mine["class"]))
    if confirmed:
        plan = replace(plan, status=PlanStatus.CONFIRMED)
    PostgresPlanRepository(
        session, center_id=mine["center"], kind="annual", plan_type=type(plan)
    ).save(plan.plan_id, plan)
    session.commit()


def _post(world, **body):
    return client.post(URL, json={"class_id": world["mine"]["class"], "month": 10, **body})


def _count(world):
    return world["session"].scalar(select(func.count()).select_from(Plan))


# ── 생성 게이트 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"month": 0}, "month"),
        ({"month": 13}, "month"),
        ({"month": "10"}, "month"),
        ({"month": "abc"}, "month"),
        ({"month": True}, "month"),
        ({"month": 10.5}, "month"),
        ({"class_id": "x"}, "class_id"),
        ({"class_id": "1"}, "class_id"),
        ({"class_id": True}, "class_id"),
        ({"class_id": 1.5}, "class_id"),
        ({"emphasized_row_keys": ["a", "a"]}, "emphasized_row_keys"),
        ({"emphasized_row_keys": ["  "]}, "emphasized_row_keys.0"),
        ({"emphasized_row_keys": "a"}, "emphasized_row_keys"),
    ],
)
def test_스키마는_소유보다_먼저_422(world, body, field):
    response = client.post(
        URL, json={"class_id": world["other"]["class"], "month": 10} | body
    )  # 남의 반이어도 422 가 먼저다

    assert _error(response) == (422, "VALIDATION_FAILED", [field])


def test_남의_반은_404(world):
    response = client.post(URL, json={"class_id": world["other"]["class"], "month": 10})

    assert _error(response) == (404, "NOT_FOUND", ["class_id"])


def test_그_달_월간이_있으면_409_이고_연간_게이트보다_먼저다(world):
    # world 에는 월별 주제형 연간 + 확정 9월 월간이 있다 — 연간 게이트였다면 다른 409 가 난다
    response = _post(world, month=9)

    assert _error(response) == (409, "ALREADY_EXISTS", ["class_id", "month"])


def test_놀이_월간이_있어도_같은_달이면_409(world):
    _play(world, month=10, year=2026)  # 반의 학년도(2026)의 10월

    assert _error(_post(world, month=10)) == (409, "ALREADY_EXISTS", ["class_id", "month"])


def test_연간이_없으면_409(world):
    world["session"].query(Plan).delete()

    response = _post(world)

    assert _error(response) == (409, "GATE_BLOCKED", ["class_id"])
    assert response.json()["error"]["message"] == "연간계획안을 먼저 만들어 확정해주세요."


def test_월별_주제형_연간이면_409(world):
    response = _post(world)  # world 의 연간은 확정된 월별 주제형이다

    assert _error(response) == (409, "GATE_BLOCKED", ["class_id"])
    assert response.json()["error"]["message"] == (
        "월별 주제형 연간계획안으로는 놀이 중심 월간계획안을 만들 수 없습니다."
    )


def test_월별_주제형_거절은_확정_여부보다_먼저다(world):
    annual = world["session"].scalar(select(Plan).where(Plan.kind == "annual"))
    annual.status = "DRAFT"
    world["session"].commit()

    response = _post(world)

    assert response.json()["error"]["message"].startswith("월별 주제형 연간계획안으로는")


def test_놀이형_연간이_확정_전이면_409(world):
    _annual(world, confirmed=False)

    response = _post(world)

    assert _error(response) == (409, "GATE_BLOCKED", ["class_id"])
    assert response.json()["error"]["message"] == "연간계획안을 먼저 확정해주세요."


def test_게이트를_다_지나면_503_이고_아무것도_저장하지_않는다(world):
    _annual(world, confirmed=True)
    before = _count(world)

    response = _post(world, emphasized_row_keys=["cand1"])

    assert _error(response) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert response.json()["error"]["message"] == (
        "지금은 이 반의 놀이 중심 월간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요."
    )
    assert _count(world) == before


# ── 단건 ───────────────────────────────────────────────────────────────────


def test_단건은_계약_모양이고_싣지_않는_것은_없다(world):
    plan, row = _play(world)

    response = client.get(f"{URL}/{row.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == SINGLE_KEYS  # references · removed_activities 없음
    assert (body["id"], body["class_id"], body["month"], body["target_month"]) == (
        row.id,
        world["mine"]["class"],
        4,
        "2027-04",
    )
    assert (body["status"], body["revision"], body["format"]) == ("DRAFT", 1, "PLAY_MONTHLY")
    assert body["format_version"] == plan.layout.layout_version
    assert body["created_at"].endswith("Z") or body["created_at"].endswith("+00:00")
    assert body["confirmed_at"] is None
    assert body["weeks"][0] == {
        "week_id": plan.weeks[0].week_id.value,
        "label": plan.weeks[0].display_label,
        "start_date": plan.weeks[0].start_date.isoformat(),
        "end_date": plan.weeks[0].end_date.isoformat(),
        "active": True,
    }
    assert set(body["parent"]) == {
        "annual_plan_id", "period_key", "layout_version", "confirmed_at", "plays"
    }  # fmt: skip
    assert set(body["parent"]["plays"][0]) == {
        "row_key", "play_name_item_id", "play_name", "materials", "support_direction", "emphasized"
    }  # fmt: skip
    cell = {"item_id", "value", "evidence", "generation"}
    assert set(body["theme"]) == cell
    assert set(body["together"][0]) == {
        "activity_id", "name", "description", "content_ids", "parent_item_id"
    }  # fmt: skip
    assert body["together"][0]["activity_id"] == body["together"][0]["name"]["item_id"]
    assert set(body["habits"][0]) == {"week_id", "entry_id", "cell"}
    assert set(body["safety_candidates"][0]) == {"kind", "category_id", "topic_group", "cell"}
    assert set(body["safety_weeks"][0]) == {"week_id", "candidate_item_id"}
    assert set(body["health"]) == {"entry_id", "cell"}
    assert set(body["drill_candidates"][0]) == {"topic_id", "label", "cell"}
    assert set(body["teacher_inputs"][0]) == {"key", "cell"}
    assert all(set(n) == {"code", "week_id"} for n in body["notices"])


def test_evidence_와_generation_은_세_축_규칙을_따른다(world):
    _, row = _play(world)
    body = client.get(f"{URL}/{row.id}").json()

    def types(cell):
        return {e["source_type"] for e in cell["evidence"]}

    assert types(body["theme"]) == types(body["rationale"]) == {"PARENT_PLAN"}
    for activity in (*body["together"], *body["free_play"]):
        for name in ("name", "description"):
            assert "CURRICULUM" in types(activity[name])
            assert types(activity[name]) <= {"CURRICULUM", "PARENT_PLAN"}
        has_parent = "PARENT_PLAN" in types(activity["name"])
        assert (activity["parent_item_id"] is not None) == has_parent
    for candidate in body["safety_candidates"]:
        expected = {"STATUTORY": "SAFETY_RULE", "SUPPLEMENTAL": "INSTITUTION_SAMPLE"}
        assert types(candidate["cell"]) == {expected[candidate["kind"]]}
    for item in (*body["habits"], body["health"], body["nutrition"], *body["drill_candidates"]):
        assert types(item["cell"]) == {"CURRICULUM"}
    for teacher in body["teacher_inputs"]:  # 쓴 적 없는 교사 입력 칸
        assert teacher["cell"]["evidence"] == [] and teacher["cell"]["generation"] is None
    generated = [body["theme"], body["rationale"], body["health"]["cell"]]
    for cell in generated:
        assert cell["generation"]["method"] == "RULE_LLM"
        assert set(cell["generation"]) == {"method", "rule_id", "rule_version"}


def test_annual_plan_id_는_연간_행의_정수_id(world):
    _, row = _play(world)
    annual = world["session"].scalar(select(Plan).where(Plan.kind == "annual"))

    parent = client.get(f"{URL}/{row.id}").json()["parent"]

    assert annual.plan_ref == "parent-1"
    assert parent["annual_plan_id"] == annual.id
    assert isinstance(parent["annual_plan_id"], int)


def _blank(cell):
    return replace(cell, value="")


def _with_blanks(plan):
    """습관 첫 주 · 건강 · 영양 칸을 비우고, 안전 후보 하나의 글을 비운 채 첫 주에 둔다."""
    first = plan.safety_candidates[0]
    placed = (replace(plan.safety_weeks[0], candidate_item_id=first.cell.item_id),)
    habit = replace(
        plan.habits[0], habit=replace(plan.habits[0].habit, cell=_blank(plan.habits[0].habit.cell))
    )
    return replace(
        plan,
        habits=(habit, *plan.habits[1:]),
        health=replace(plan.health, cell=_blank(plan.health.cell)),
        nutrition=replace(plan.nutrition, cell=_blank(plan.nutrition.cell)),
        safety_candidates=(replace(first, cell=_blank(first.cell)), *plan.safety_candidates[1:]),
        safety_weeks=(*placed, *plan.safety_weeks[1:]),
    )


def test_notices_는_응답마다_계산한다(world):
    plan, row = _play(world, edit=_with_blanks)
    weeks = [w.week_id.value for w in plan.weeks]
    assert len(weeks) >= 2  # 둔 주와 안 둔 주가 모두 있어야 한다

    notices = client.get(f"{URL}/{row.id}").json()["notices"]

    assert {(n["code"], n["week_id"]) for n in notices} == {
        ("SAFETY_BLANK", weeks[0]),
        *(("SAFETY_UNPLACED", w) for w in weeks[1:]),
        ("HABIT_BLANK", weeks[0]),
        ("HEALTH_BLANK", None),
        ("NUTRITION_BLANK", None),
    }


def test_기존_월간_id_는_409_이고_남의_원_없는_id_는_404(world):
    _, theirs = _play(world, mine=False)

    legacy = client.get(f"{URL}/{world['monthly']['id']}")
    assert (_error(legacy), legacy.json()["error"]["message"]) == (
        (409, "GATE_BLOCKED", []),
        LEGACY,
    )
    assert _error(client.get(f"{URL}/{theirs.id}")) == (404, "NOT_FOUND", ["id"])
    assert _error(client.get(f"{URL}/999999")) == (404, "NOT_FOUND", ["id"])


# ── 목록 ───────────────────────────────────────────────────────────────────


def test_목록은_놀이_월간만_대상_달_오름차순으로(world):
    _, june = _play(world, month=6)
    _, april = _play(world, month=4)
    _, other = _play(world, mine=False, month=5)

    items = client.get(URL).json()["items"]

    assert [i["id"] for i in items] == [april.id, june.id]  # 기존 월간 · 남의 원 없음
    assert set(items[0]) == {
        "id", "class_id", "school_year", "month", "target_month", "status", "revision",
        "created_at", "confirmed_at",
    }  # fmt: skip
    assert (items[0]["month"], items[0]["target_month"]) == (4, "2027-04")
    assert other.id not in {i["id"] for i in items}


def test_목록_class_id_필터와_남의_반(world):
    _, row = _play(world, month=4)
    mine, other = world["mine"]["class"], world["other"]["class"]

    assert [i["id"] for i in client.get(URL, params={"class_id": mine}).json()["items"]] == [row.id]
    assert _error(client.get(URL, params={"class_id": other})) == (404, "NOT_FOUND", ["class_id"])


# ── 삭제 ───────────────────────────────────────────────────────────────────


def test_초안은_지워지고_204(world):
    _, row = _play(world)

    response = client.delete(f"{URL}/{row.id}")

    assert (response.status_code, response.content) == (204, b"")
    assert world["session"].scalar(select(Plan).where(Plan.id == row.id)) is None


def test_확정본은_409_이고_행이_남는다(world):
    _, row = _play(world, confirmed=True)

    response = client.delete(f"{URL}/{row.id}")

    assert _error(response) == (409, "GATE_BLOCKED", [])
    assert response.json()["error"]["message"] == "확정된 계획안은 지울 수 없습니다."
    assert world["session"].scalar(select(Plan).where(Plan.id == row.id)) is not None


def test_읽은_뒤_확정되어도_DRAFT_조건이_확정본을_지키지_않게_막는다(world, monkeypatch):
    from types import SimpleNamespace

    from app.features.plans import play_monthly_router as router

    _, row = _play(world, confirmed=True)
    real, calls = router._own_row, []

    def stale_first(session, user, plan_id):  # 첫 읽기는 아직 DRAFT 로 보였던 때다
        calls.append(plan_id)
        return (
            SimpleNamespace(id=row.id, status="DRAFT")
            if len(calls) == 1
            else real(session, user, plan_id)
        )

    monkeypatch.setattr(router, "_own_row", stale_first)

    response = client.delete(f"{URL}/{row.id}")

    assert _error(response) == (409, "GATE_BLOCKED", [])
    assert world["session"].scalar(select(Plan).where(Plan.id == row.id)) is not None


def test_삭제_남의_원_없는_id_는_404_기존_월간은_409(world):
    _, theirs = _play(world, mine=False)

    assert _error(client.delete(f"{URL}/{theirs.id}")) == (404, "NOT_FOUND", ["id"])
    assert _error(client.delete(f"{URL}/999999")) == (404, "NOT_FOUND", ["id"])
    legacy = client.delete(f"{URL}/{world['monthly']['id']}")
    assert (_error(legacy), legacy.json()["error"]["message"]) == (
        (409, "GATE_BLOCKED", []),
        LEGACY,
    )
    assert world["session"].get(Plan, world["monthly"]["id"]) is not None


# ── 경로 등록 순서 ─────────────────────────────────────────────────────────


def test_play_고정_경로가_monthly_id_경로보다_먼저_등록된다(world):
    # 뒤집히면 `play` 가 `/{plan_id}` 의 정수 검사에 걸려 422 가 된다
    assert client.get(URL).status_code == 200
    assert (
        client.post(URL, json={}).status_code == 422
    )  # 이 경로의 스키마다 — 기존 월간 것이 아니다
    assert client.get(f"{URL}/999999").json()["error"]["fields"] == ["id"]
