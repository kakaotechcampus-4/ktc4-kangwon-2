"""월간계획안 변경 이력 조회 API (BE-2). 진짜 Postgres 위에서 HTTP 로 부른다. 계약은 §9-5.

이력은 M5 API(편집 · 재생성 · 확정)를 실제로 불러 만든다 — 테스트가 이벤트를 지어내지 않는다.
LLM 은 기본 mock(요청 기반 결정적 provider)이다. **실제 Luna-6 는 부르지 않는다.**
Template v0.1.1 · v0.2.1 은 사람 승인 대기라 OD-N11 (A) 객체로만 Profile 을 만든다.
"""

from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef

from app.config import settings
from app.features.auth.models import User
from app.features.centers.models import Center, Class
from app.features.plans import monthly_llm
from app.features.plans.models import Plan
from app.features.template_profiles import service as profile_service
from app.features.template_profiles.repository import PostgresTemplateProfileRepository
from app.main import app
from app.shared.auth.dependency import current_user
from app.shared.llm import LlmFailed

client = TestClient(app)

FOCUS = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.2.1")
LABELS = {
    "theme": "주제",
    "week_axis": "주",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
    "focus": "소주제",
}


class ApprovedTemplates:
    """OD-N11 (A): 실제 파일을 읽어 테스트 안에서만 승인 상태로 바꾼다."""

    def __init__(self):
        self._real = JsonMonthlyTemplateRepository()

    def get_template(self, template_id, template_version):
        template = self._real.get_template(template_id, template_version)
        return None if template is None else replace(template, runtime_active=True)


@pytest.fixture(autouse=True)
def _approved(monkeypatch):
    monkeypatch.setattr(profile_service, "TEMPLATES", ApprovedTemplates())


def _seed(session, name: str, email: str) -> dict:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    user = User(
        email=email,
        name="선생",
        password_hash=b"x" * 64,
        password_salt=b"y" * 16,
        center_id=center.id,
    )
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=3,
        age_max=4,
        teacher_name="선생",
    )
    session.add_all([user, klass])
    session.flush()
    ref = PostgresTemplateProfileRepository(session, center_id=center.id).start_from_reference(
        ApprovedTemplates(),
        FOCUS,
        selected_optional_keys=("focus",),
        display_labels=LABELS,
        focus_variant=SemanticVariant.SUBTHEME,
        actor_id=user.id,
    )
    return {
        "center": center.id,
        "user": user.id,
        "class": klass.id,
        "profile": {"profile_id": ref.profile_id, "profile_version": ref.profile_version},
    }


def _annual(seed: dict) -> int:
    annual = client.post("/api/plans/annual", json={"class_id": seed["class"], "form_id": None})
    assert annual.status_code == 201, annual.json()
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    return annual.json()["id"]


def _monthly(seed: dict) -> dict:
    created = client.post(
        "/api/plans/monthly",
        json={"class_id": seed["class"], "month": 9, "profile_ref": seed["profile"]},
    )
    assert created.status_code == 201, created.json()
    return created.json()


@pytest.fixture
def world(db_session, teacher):
    """원 둘. 교사는 가원 소속이고 가원 · 나원에 DRAFT 월간이 하나씩 있다."""
    mine = _seed(db_session, "가원", "a@example.com")
    other = _seed(db_session, "나원", "b@example.com")
    teacher.center_id = other["center"]
    _annual(other)
    theirs = _monthly(other)
    teacher.center_id = mine["center"]
    annual_id = _annual(mine)
    return {
        "session": db_session,
        "mine": mine,
        "plan": _monthly(mine),
        "theirs": theirs,
        "annual_id": annual_id,
        "actor": f"user_{teacher.id}",
    }


def _cell(plan: dict, key: str, index: int = 0) -> dict:
    return next(s for s in plan["sections"] if s["section_key"] == key)["cells"][index]


def _located(plan: dict) -> list[tuple[str, str, str | None]]:
    """계획안 안의 칸 순서 그대로 (item_id, section_key, week_id)."""
    return [
        (c["item_id"], s["section_key"], c["week_id"]) for s in plan["sections"] for c in s["cells"]
    ]


def _audit(plan_id, item_id=None) -> list[dict]:
    params = {} if item_id is None else {"item_id": item_id}
    response = client.get(f"/api/plans/monthly/{plan_id}/audit", params=params)
    assert response.status_code == 200, response.json()
    return response.json()["items"]


def _edit(plan_id, item_id, value, revision):
    return client.put(
        f"/api/plans/monthly/{plan_id}/cells/{item_id}",
        json={"value": value, "expected_revision": revision},
    )


def _regenerate(plan_id, item_id, revision):
    return client.post(
        f"/api/plans/monthly/{plan_id}/cells/{item_id}/regenerate",
        json={"expected_revision": revision},
    )


def _confirm(plan_id, revision):
    return client.post(
        f"/api/plans/monthly/{plan_id}/confirm", json={"expected_revision": revision}
    )


def _error(response):
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


def _when(item: dict) -> datetime:
    return datetime.fromisoformat(item["occurred_at"])


EVENT_KEYS = {
    "type",
    "occurred_at",
    "scope",
    "item_id",
    "section_key",
    "week_id",
    "actor",
    "system_actor",
    "value_change",
    "generation_change",
}


# ── A. 생성 직후 ───────────────────────────────────────────────────────────


def test_생성_직후에는_계획안_CREATED_하나와_칸마다_CREATED_가_있다(world):
    plan = world["plan"]
    items = _audit(plan["id"])
    assert all(set(item) == EVENT_KEYS for item in items)  # 이전 근거 · revision 칸은 없다

    plan_events = [i for i in items if i["scope"] == "PLAN"]
    assert plan_events == [
        {
            "type": "CREATED",
            "occurred_at": plan_events[0]["occurred_at"],
            "scope": "PLAN",
            "item_id": None,
            "section_key": None,
            "week_id": None,
            "actor": None,
            "system_actor": "monthly_application",
            "value_change": None,
            "generation_change": None,
        }
    ]
    cell_events = [i for i in items if i["scope"] == "CELL"]
    assert {i["type"] for i in cell_events} == {"CREATED"}
    # 칸 수와 같고, 위치는 계획안이 준 그대로다. 같은 시각이면 계획안 → 칸(계획안 순서).
    assert [(i["item_id"], i["section_key"], i["week_id"]) for i in cell_events] == _located(plan)
    assert items[0]["scope"] == "PLAN"
    assert [_when(i) for i in items] == sorted(_when(i) for i in items)
    assert _audit(plan["id"]) == items  # 다시 읽어도 같은 순서


# ── B. 교사 수정 ───────────────────────────────────────────────────────────


def test_교사_수정은_TEACHER_EDITED_와_이전_이후_값으로_남는다(world):
    plan = world["plan"]
    target = _cell(plan, "focus", 1)
    before_items = _audit(plan["id"])
    assert _edit(plan["id"], target["item_id"], "교사가 고친 소주제", 1).status_code == 200

    items = _audit(plan["id"])
    assert items[: len(before_items)] == before_items  # 앞의 이력은 그대로, 하나만 늘었다
    (edited,) = items[len(before_items) :]
    assert target["week_id"] is not None  # focus 는 주마다 있는 칸이다
    assert edited == {
        "type": "TEACHER_EDITED",
        "occurred_at": edited["occurred_at"],
        "scope": "CELL",
        "item_id": target["item_id"],
        "section_key": "focus",
        "week_id": target["week_id"],
        "actor": world["actor"],
        "system_actor": None,
        "value_change": {"before": target["value"], "after": "교사가 고친 소주제"},
        "generation_change": None,
    }


# ── C. AI 재생성 (mock provider) ──────────────────────────────────────────


def test_재생성은_REGENERATED_와_저장된_생성_방식_변화로_남는다(world):
    plan = world["plan"]
    target = _cell(plan, "focus", 0)
    response = _regenerate(plan["id"], target["item_id"], 1)
    assert response.status_code == 200, response.json()
    after = next(
        c
        for s in response.json()["sections"]
        for c in s["cells"]
        if c["item_id"] == target["item_id"]
    )

    regenerated = [i for i in _audit(plan["id"]) if i["type"] == "REGENERATED"]
    assert regenerated == [
        {
            "type": "REGENERATED",
            "occurred_at": regenerated[0]["occurred_at"],
            "scope": "CELL",
            "item_id": target["item_id"],
            "section_key": "focus",
            "week_id": target["week_id"],
            "actor": world["actor"],
            "system_actor": None,
            "value_change": {"before": target["value"], "after": after["value"]},
            "generation_change": {"before": target["generation"], "after": after["generation"]},
        }
    ]


# ── D. 확정 ───────────────────────────────────────────────────────────────


def test_확정은_계획안_단위_CONFIRMED_하나로_남고_재호출해도_늘지_않는다(world):
    plan = world["plan"]
    confirmed = _confirm(plan["id"], 1)
    assert confirmed.status_code == 200
    items = _audit(plan["id"])
    (event,) = [i for i in items if i["type"] == "CONFIRMED"]
    assert (event["scope"], event["item_id"], event["actor"], event["system_actor"]) == (
        "PLAN",
        None,
        world["actor"],
        None,
    )
    assert _when(event) == datetime.fromisoformat(confirmed.json()["confirmed_at"])
    assert items[-1] == event

    assert _confirm(plan["id"], 1).status_code == 200  # 정책 B: 재호출은 200 · 저장 없음
    assert _audit(plan["id"]) == items
    assert client.get(f"/api/plans/monthly/{plan['id']}").json()["status"] == "CONFIRMED"


# ── E. 실패하면 이력이 늘지 않는다 ─────────────────────────────────────────


def test_거절되거나_실패한_변경은_이력에_남지_않는다(world, monkeypatch):
    plan = world["plan"]
    focus = _cell(plan, "focus")
    before = _audit(plan["id"])

    assert _error(_edit(plan["id"], focus["item_id"], focus["value"], 1)) == (
        422,
        "VALIDATION_FAILED",
        ["value"],
    )
    assert _error(_edit(plan["id"], focus["item_id"], "다른 값", 2)) == (
        409,
        "STALE_WRITE",
        ["expected_revision"],
    )
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-key")

    def post_json(url, *, headers, payload, timeout):
        raise LlmFailed("timeout")

    monkeypatch.setattr(monthly_llm, "post_json", post_json)
    assert _error(_regenerate(plan["id"], focus["item_id"], 1)) == (500, "GENERATION_FAILED", [])
    assert _audit(plan["id"]) == before

    monkeypatch.setattr(settings, "llm_mode", "mock")
    assert _confirm(plan["id"], 1).status_code == 200
    confirmed = _audit(plan["id"])
    assert _error(_edit(plan["id"], focus["item_id"], "확정 뒤 수정", 2)) == (
        409,
        "ALREADY_CONFIRMED",
        [],
    )
    assert _audit(plan["id"]) == confirmed


# ── F. item_id 필터 ───────────────────────────────────────────────────────


def test_item_id_로_고르면_그_칸_이벤트와_계획안_CONFIRMED_만_준다(world):
    plan = world["plan"]
    target, other = _cell(plan, "focus", 0), _cell(plan, "focus", 1)
    assert _edit(plan["id"], target["item_id"], "고친 첫 주", 1).status_code == 200
    assert _edit(plan["id"], other["item_id"], "고친 둘째 주", 2).status_code == 200

    # 확정 전 — 없는 CONFIRMED 를 만들어 주지 않는다. 계획안 CREATED 도 빠진다.
    draft = _audit(plan["id"], target["item_id"])
    assert [(i["type"], i["scope"]) for i in draft] == [
        ("CREATED", "CELL"),
        ("TEACHER_EDITED", "CELL"),
    ]
    assert {i["item_id"] for i in draft} == {target["item_id"]}

    assert _confirm(plan["id"], 3).status_code == 200
    confirmed = _audit(plan["id"], target["item_id"])
    assert confirmed[:2] == draft
    assert [(i["type"], i["scope"]) for i in confirmed[2:]] == [("CONFIRMED", "PLAN")]
    full = _audit(plan["id"])
    assert [
        i
        for i in full
        if i["item_id"] in (None, target["item_id"])
        and not (i["scope"] == "PLAN" and i["type"] == "CREATED")
    ] == confirmed

    assert _error(
        client.get(f"/api/plans/monthly/{plan['id']}/audit", params={"item_id": "item_none"})
    ) == (
        404,
        "NOT_FOUND",
        ["item_id"],
    )
    # 다른 계획안의 칸 id 는 이 계획안에서 없는 칸이다.
    foreign = _cell(world["theirs"], "focus")["item_id"]
    assert _error(
        client.get(f"/api/plans/monthly/{plan['id']}/audit", params={"item_id": foreign})
    ) == (
        404,
        "NOT_FOUND",
        ["item_id"],
    )


# ── G. 원 단위 격리 ───────────────────────────────────────────────────────


def test_남의_원_없는_계획안_연간_id_는_404_로그인_안_하면_401(world):
    theirs = world["theirs"]
    foreign_item = _cell(theirs, "focus")["item_id"]
    for url, params in (
        (f"/api/plans/monthly/{theirs['id']}/audit", {}),
        (f"/api/plans/monthly/{theirs['id']}/audit", {"item_id": foreign_item}),
        ("/api/plans/monthly/999999/audit", {}),
        (f"/api/plans/monthly/{world['annual_id']}/audit", {}),
    ):
        assert _error(client.get(url, params=params)) == (404, "NOT_FOUND", ["id"])

    app.dependency_overrides.pop(current_user)
    response = client.get(f"/api/plans/monthly/{world['plan']['id']}/audit")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


# ── H. 조회는 아무것도 바꾸지 않는다 ───────────────────────────────────────


def test_이력_조회는_DB_를_바꾸지_않는다(world):
    session, plan = world["session"], world["plan"]
    assert _edit(plan["id"], _cell(plan, "focus")["item_id"], "고친 값", 1).status_code == 200

    def snapshot():
        session.expunge_all()
        row = session.execute(
            select(Plan.body, Plan.revision, Plan.updated_at, Plan.status, Plan.confirmed_at).where(
                Plan.id == plan["id"]
            )
        ).one()
        return tuple(row)

    before = snapshot()
    current = client.get(f"/api/plans/monthly/{plan['id']}").json()
    for _ in range(3):
        _audit(plan["id"])
        _audit(plan["id"], _cell(plan, "focus")["item_id"])
    assert snapshot() == before
    assert client.get(f"/api/plans/monthly/{plan['id']}").json() == current
