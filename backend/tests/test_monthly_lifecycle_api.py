"""월간계획안 칸 편집 · 칸 재생성 · 확정 API. 진짜 Postgres 위에서 HTTP 로 부른다.

계약은 docs/api-spec.md §9-3 · 결정 문서 12.10(D-M5-CONFIRM-01)이다. 핵심은 `expected_revision`
— 비교와 저장이 조건부 UPDATE 한 문장이라, 같은 revision 을 본 두 요청 중 하나만 저장된다.
동시성은 **서로 다른 연결 두 개**로 보고, 두 요청을 Core 단계(읽기 뒤 · 쓰기 전)에 붙잡아 둔다.

Template v0.1.1 · v0.2.1 은 사람 승인 대기라 OD-N11 (A) 객체로만 Profile 을 만든다. LLM 은 기본
mock(요청 기반 결정적 provider)이다 — **실제 Luna-6 는 부르지 않는다.**
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.orm import Session
from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning import ItemId, MonthlyPlan, PlanId
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef

from app.config import settings
from app.db import engine
from app.features.auth.models import User
from app.features.centers.models import Center, Class
from app.features.plans import monthly_llm, monthly_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.template_profiles import service as profile_service
from app.features.template_profiles.models import TemplateProfileVersion
from app.features.template_profiles.repository import PostgresTemplateProfileRepository
from app.main import app
from app.shared.llm import LlmBudgetExceeded, LlmFailed

client = TestClient(app)

FOCUS = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.2.1")
LABELS = {
    "theme": "주제",
    "week_axis": "주",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
    "focus": "소주제",
}
IDLE_IN_TRANSACTION = (
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
    "AND state LIKE 'idle in transaction%'"
)


class ApprovedTemplates:
    """OD-N11 (A): 실제 파일을 읽어 테스트 안에서만 승인 상태로 바꾼다."""

    def __init__(self):
        self._real = JsonMonthlyTemplateRepository()

    def get_template(self, template_id, template_version):
        template = self._real.get_template(template_id, template_version)
        return None if template is None else replace(template, runtime_active=True)


@pytest.fixture(autouse=True)
def _approved(teacher, monkeypatch):
    monkeypatch.setattr(profile_service, "TEMPLATES", ApprovedTemplates())
    return teacher


def _seed(session, name: str, email: str) -> dict:
    """원 · 계정 · 반 · READY Profile. id 만 돌려준다 — commit 뒤 ORM 객체는 만료된다."""
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


def _monthly(seed: dict) -> dict:
    """부모 연간을 만들어 확정하고 9월 월간을 만든다 — 전부 API 로."""
    annual = client.post("/api/plans/annual", json={"class_id": seed["class"], "form_id": None})
    assert annual.status_code == 201, annual.json()
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    created = client.post(
        "/api/plans/monthly",
        json={"class_id": seed["class"], "month": 9, "profile_ref": seed["profile"]},
    )
    assert created.status_code == 201, created.json()
    return created.json()


@pytest.fixture
def world(db_session, teacher):
    """원 둘. 교사는 가원 소속이고 가원에 DRAFT 월간이 하나 있다."""
    mine = _seed(db_session, "가원", "a@example.com")
    other = _seed(db_session, "나원", "b@example.com")
    teacher.center_id = mine["center"]
    return {"session": db_session, "mine": mine, "other": other, "plan": _monthly(mine)}


def _cell(plan: dict, key: str, index: int = 0) -> dict:
    return next(s for s in plan["sections"] if s["section_key"] == key)["cells"][index]


def _cells(plan: dict) -> dict:
    return {c["item_id"]: c for s in plan["sections"] for c in s["cells"]}


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


def _get(plan_id):
    return client.get(f"/api/plans/monthly/{plan_id}").json()


def _error(response):
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


def _stored(session, center_id: int, plan_id: int) -> tuple[Plan, MonthlyPlan]:
    """DB 에 실제로 들어 있는 행과 도메인 객체 (identity map 을 비우고 읽는다)."""
    session.expunge_all()
    row = session.get(Plan, plan_id)
    repo = PostgresPlanRepository(
        session, center_id=center_id, kind="monthly", plan_type=MonthlyPlan
    )
    return row, repo.get(PlanId(row.plan_ref))


# ── 칸 편집 ──────────────────────────────────────────────────────────────


def test_칸을_고치면_그_칸만_바뀌고_revision_이_하나_오른다(world):
    session, plan = world["session"], world["plan"]
    target = _cell(plan, "outdoor_play")
    _, before = _stored(session, world["mine"]["center"], plan["id"])
    original = before.find_cell(_item(target))[3]

    response = _edit(plan["id"], target["item_id"], "교사가 쓴 바깥놀이", 1)
    assert response.status_code == 200, response.json()
    edited = response.json()
    assert edited["revision"] == 2
    assert _get(plan["id"]) == edited  # 응답이 곧 DB 상태다

    cell = _cells(edited)[target["item_id"]]
    assert (cell["item_id"], cell["week_id"], cell["value"]) == (
        target["item_id"],
        target["week_id"],
        "교사가 쓴 바깥놀이",
    )
    assert (cell["evidence"], cell["generation"]) == (target["evidence"], target["generation"])
    others = {k: v for k, v in _cells(edited).items() if k != target["item_id"]}
    assert others == {k: v for k, v in _cells(plan).items() if k != target["item_id"]}

    row, stored = _stored(session, world["mine"]["center"], plan["id"])
    assert row.revision == 2
    stored_cell = stored.find_cell(_item(target))[3]
    event = stored_cell.audit.events[-1]
    assert event.event_type.value == "TEACHER_EDITED"
    assert (event.value_change.before, event.value_change.after) == (
        original.value,
        "교사가 쓴 바깥놀이",
    )
    assert (stored_cell.generation, stored_cell.evidence) == (
        original.generation,
        original.evidence,
    )


def _item(cell: dict) -> ItemId:
    return ItemId(cell["item_id"])


def test_편집_입력_오류는_저장하지_않는다(world, teacher):
    session, plan = world["session"], world["plan"]
    target = _cell(plan, "focus")
    cases = (
        (
            _edit(plan["id"], target["item_id"], target["value"], 1),
            (422, "VALIDATION_FAILED", ["value"]),
        ),
        (_edit(plan["id"], "item_없는칸", "x", 1), (404, "NOT_FOUND", ["item_id"])),
        (_edit(999_999, target["item_id"], "x", 1), (404, "NOT_FOUND", ["id"])),
        (_edit(plan["id"], target["item_id"], "x", 2), (409, "STALE_WRITE", ["expected_revision"])),
    )
    for response, expected in cases:
        assert _error(response) == expected
    for body, field in (
        ({"value": "x"}, "expected_revision"),
        ({"value": "x", "expected_revision": "1"}, "expected_revision"),
        ({"value": "x", "expected_revision": True}, "expected_revision"),
        ({"value": "x", "expected_revision": 0}, "expected_revision"),
        ({"value": 7, "expected_revision": 1}, "value"),
    ):
        response = client.put(
            f"/api/plans/monthly/{plan['id']}/cells/{target['item_id']}", json=body
        )
        assert _error(response) == (422, "VALIDATION_FAILED", [field])

    teacher.center_id = world["other"]["center"]  # 남의 원은 없는 것과 같다
    assert _error(_edit(plan["id"], target["item_id"], "x", 1)) == (404, "NOT_FOUND", ["id"])
    teacher.center_id = world["mine"]["center"]
    assert _get(plan["id"]) == plan
    assert _stored(session, world["mine"]["center"], plan["id"])[0].revision == 1


# ── 칸 재생성 ────────────────────────────────────────────────────────────


def test_칸을_다시_만들면_주소는_그대로_근거는_새_결과로_바뀐다(world):
    session, plan = world["session"], world["plan"]
    target = _cell(plan, "focus")
    _, before = _stored(session, world["mine"]["center"], plan["id"])
    original = before.find_cell(_item(target))[3]

    response = _regenerate(plan["id"], target["item_id"], 1)
    assert response.status_code == 200, response.json()
    regenerated = response.json()
    assert regenerated["revision"] == 2
    assert _get(plan["id"]) == regenerated
    cell = _cells(regenerated)[target["item_id"]]
    assert (cell["item_id"], cell["week_id"], cell["value"]) == (
        target["item_id"],
        target["week_id"],
        "다시 만든 focus",
    )
    assert {e["source_type"] for e in cell["evidence"]} >= {"INSTITUTION_SAMPLE"}
    others = {k: v for k, v in _cells(regenerated).items() if k != target["item_id"]}
    assert others == {k: v for k, v in _cells(plan).items() if k != target["item_id"]}

    _, stored = _stored(session, world["mine"]["center"], plan["id"])
    event = stored.find_cell(_item(target))[3].audit.events[-1]
    assert event.event_type.value == "REGENERATED"
    assert event.value_change.before == original.value
    assert event.generation_change.before == original.generation


def test_교사가_고친_칸도_요청하면_다시_만든다(world):
    session, plan = world["session"], world["plan"]
    target = _cell(plan, "outdoor_play", 1)
    assert _edit(plan["id"], target["item_id"], "교사 값", 1).status_code == 200

    response = _regenerate(plan["id"], target["item_id"], 2)
    assert response.status_code == 200, response.json()
    assert response.json()["revision"] == 3
    assert _cells(response.json())[target["item_id"]]["value"] != "교사 값"
    _, stored = _stored(session, world["mine"]["center"], plan["id"])
    events = [e.event_type.value for e in stored.find_cell(_item(target))[3].audit.events]
    assert events[-2:] == ["TEACHER_EDITED", "REGENERATED"]


def test_다시_만들_수_없는_칸과_남의_원은_거절한다(world, teacher):
    plan = world["plan"]
    for key in ("theme", "safety_education"):
        response = _regenerate(plan["id"], _cell(plan, key)["item_id"], 1)
        assert _error(response) == (422, "VALIDATION_FAILED", ["item_id"])
    assert _error(_regenerate(plan["id"], "item_없는칸", 1)) == (404, "NOT_FOUND", ["item_id"])
    teacher.center_id = world["other"]["center"]
    focus = _cell(plan, "focus")["item_id"]
    assert _error(_regenerate(plan["id"], focus, 1)) == (404, "NOT_FOUND", ["id"])
    teacher.center_id = world["mine"]["center"]
    assert _get(plan["id"]) == plan


def test_재생성_LLM_이_실패하면_칸도_revision_도_그대로다(world, monkeypatch):
    session, plan = world["session"], world["plan"]
    focus = _cell(plan, "focus")["item_id"]
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-key")
    for error, expected in (
        (LlmFailed("timeout"), (500, "GENERATION_FAILED", [])),
        (LlmBudgetExceeded("429"), (503, "LLM_BUDGET_EXCEEDED", [])),
    ):

        def post_json(url, *, headers, payload, timeout, error=error):
            assert payload["model"] == "openai/gpt-6-luna"
            raise error

        monkeypatch.setattr(monthly_llm, "post_json", post_json)
        assert _error(_regenerate(plan["id"], focus, 1)) == expected
        assert _get(plan["id"]) == plan  # mock 으로 대신하지도, 일부만 저장하지도 않는다
    monkeypatch.setattr(settings, "elice_mlapi_base_url", None)
    assert _error(_regenerate(plan["id"], focus, 1)) == (503, "DEPENDENCY_UNAVAILABLE", [])
    row, _ = _stored(session, world["mine"]["center"], plan["id"])
    assert row.revision == 1


# ── 확정 ────────────────────────────────────────────────────────────────


def test_확정은_한_번만_저장되고_재호출은_revision_과_무관하게_200(world, teacher):
    session, plan = world["session"], world["plan"]
    response = _confirm(plan["id"], 1)
    assert response.status_code == 200, response.json()
    confirmed = response.json()
    assert (confirmed["status"], confirmed["revision"]) == ("CONFIRMED", 2)
    assert confirmed["confirmed_at"] is not None
    assert _get(plan["id"]) == confirmed
    # 안전교육 「근거 필요」 상태로도 확정된다 — 충족했다는 뜻이 아니다.
    safety = next(s for s in confirmed["sections"] if s["section_key"] == "safety_education")
    assert {c["state"] for c in safety["cells"]} == {"EMPTY_UNRESOLVED"}
    constraint = next(
        c for c in confirmed["constraints"] if c["code"] == "STATUTORY_SAFETY_EDUCATION"
    )
    assert constraint["verification"] == "NOT_VERIFIED_SOURCE_REQUIRED"

    # D-M5-CONFIRM-01: 같은 revision · 옛 revision · 엉뚱한 revision 모두 200, 아무것도 안 바뀐다.
    for revision in (1, 2, 99):
        again = _confirm(plan["id"], revision)
        assert again.status_code == 200
        assert again.json() == confirmed
    row, stored = _stored(session, world["mine"]["center"], plan["id"])
    assert row.revision == 2
    confirmations = [e for e in stored.audit.events if e.event_type.value == "CONFIRMED"]
    assert len(confirmations) == 1
    assert confirmations[0].actor_id.value == f"user_{teacher.id}"

    focus = _cell(plan, "focus")["item_id"]
    assert _error(_edit(plan["id"], focus, "확정 뒤", 2)) == (409, "ALREADY_CONFIRMED", [])
    assert _error(_regenerate(plan["id"], focus, 2)) == (409, "ALREADY_CONFIRMED", [])
    # 멱등이어도 소유 검사가 먼저다.
    teacher.center_id = world["other"]["center"]
    assert _error(_confirm(plan["id"], 2)) == (404, "NOT_FOUND", ["id"])
    teacher.center_id = world["mine"]["center"]
    assert _stored(session, world["mine"]["center"], plan["id"])[0].revision == 2


def test_DRAFT_에_옛_revision_으로_확정하면_409(world):
    session, plan = world["session"], world["plan"]
    edited = _edit(plan["id"], _cell(plan, "focus")["item_id"], "교사 값", 1).json()
    assert _error(_confirm(plan["id"], 1)) == (409, "STALE_WRITE", ["expected_revision"])
    assert _get(plan["id"]) == edited
    row, _ = _stored(session, world["mine"]["center"], plan["id"])
    assert (row.status, row.revision) == ("DRAFT", 2)


def test_조건부_UPDATE_는_DRAFT_와_revision_이_맞을_때만_쓴다(world):
    """Repository 단위 — 비교와 +1 이 한 문장이다. 못 쓰면 행이 그대로다."""
    session, plan = world["session"], world["plan"]
    center = world["mine"]["center"]
    row, stored = _stored(session, center, plan["id"])
    repo = PostgresPlanRepository(session, center_id=center, kind="monthly", plan_type=MonthlyPlan)
    other = PostgresPlanRepository(
        session, center_id=world["other"]["center"], kind="monthly", plan_type=MonthlyPlan
    )
    assert repo.update_if_revision(stored.plan_id, stored, expected_revision=7) is None
    assert other.update_if_revision(stored.plan_id, stored, expected_revision=1) is None
    assert repo.update_if_revision(stored.plan_id, stored, expected_revision=1) == 2
    assert repo.update_if_revision(stored.plan_id, stored, expected_revision=1) is None
    assert _stored(session, center, plan["id"])[0].revision == 2


# ── 실제 동시 요청 (서로 다른 연결) ─────────────────────────────────────────


@pytest.fixture
def live(_schema, teacher, monkeypatch):
    """커밋된 원 · 반 · DRAFT 월간.

    요청마다 진짜 session 을 쓴다(get_session 을 갈아끼우지 않는다).
    """
    with Session(engine) as session:
        seed = _seed(session, "월간 생애주기 동시성 테스트원", "monthly-lifecycle-race@example.com")
        session.commit()
    teacher.center_id = seed["center"]
    idle = []

    def measure():
        """두 요청이 모두 Core 단계(읽기 뒤 · 쓰기 전)에 있을 때 센다."""
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as watcher:
            idle.append(watcher.scalar(text(IDLE_IN_TRANSACTION)))

    barrier = Barrier(2, action=measure)

    def waiting(factory):
        def build(**kwargs):
            use_case = factory(**kwargs)

            class Waiting:
                def execute(self, command):
                    barrier.wait(timeout=20)
                    return use_case.execute(command)

            return Waiting()

        return build

    class WaitingLlm(RequestAwareMonthlyLlm):
        def generate_cell(self, request):
            barrier.wait(timeout=20)  # LLM 을 기다리는 중
            return super().generate_cell(request)

    try:
        plan = _monthly(seed)
        monkeypatch.setattr(monthly_router, "monthly_edit", waiting(monthly_router.monthly_edit))
        monkeypatch.setattr(
            monthly_router, "monthly_confirmation", waiting(monthly_router.monthly_confirmation)
        )
        monkeypatch.setattr(monthly_router, "monthly_llm_provider", WaitingLlm)
        yield {"seed": seed, "plan": plan, "idle": idle}
    finally:
        with Session(engine) as session:
            for model in (Plan, TemplateProfileVersion):
                session.execute(delete(model).where(model.center_id == seed["center"]))
            session.execute(delete(Class).where(Class.center_id == seed["center"]))
            session.execute(delete(User).where(User.id == seed["user"]))
            session.execute(delete(Center).where(Center.id == seed["center"]))
            session.commit()


def _together(*calls):
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result(timeout=60) for future in futures]


def _db(live) -> tuple[Plan, MonthlyPlan]:
    with Session(engine) as session:
        return _stored(session, live["seed"]["center"], live["plan"]["id"])


def test_동시_편집은_하나만_저장된다(live):
    plan = live["plan"]
    item = _cell(plan, "focus")["item_id"]
    a, b = _together(
        lambda: _edit(plan["id"], item, "A 의 값", 1), lambda: _edit(plan["id"], item, "B 의 값", 1)
    )
    assert sorted(r.status_code for r in (a, b)) == [200, 409]
    winner, loser = (a, b) if a.status_code == 200 else (b, a)
    assert _error(loser) == (409, "STALE_WRITE", ["expected_revision"])
    assert live["idle"] == [0]
    row, stored = _db(live)
    assert row.revision == 2
    assert _cells(_get(plan["id"]))[item]["value"] == _cells(winner.json())[item]["value"]
    edits = [e for e in stored.cells if e.audit.events[-1].event_type.value == "TEACHER_EDITED"]
    assert len(edits) == 1  # 진 쪽의 이벤트는 남지 않는다


def test_편집과_확정이_겹치면_먼저_쓴_쪽만_남는다(live):
    plan = live["plan"]
    item = _cell(plan, "focus")["item_id"]
    edit, confirm = _together(
        lambda: _edit(plan["id"], item, "확정 직전 수정", 1), lambda: _confirm(plan["id"], 1)
    )
    assert sorted(r.status_code for r in (edit, confirm)) == [200, 409]
    row, stored = _db(live)
    assert row.revision == 2
    if confirm.status_code == 200:  # 확정이 이겼다 — 수정은 확정된 계획안을 건드리지 못한다
        assert _error(edit) == (409, "ALREADY_CONFIRMED", [])
        assert row.status == "CONFIRMED"
        assert stored.find_cell(_item({"item_id": item}))[3].value != "확정 직전 수정"
    else:  # 수정이 이겼다 — 확정은 수정 전 화면을 본 것이다
        assert _error(confirm) == (409, "STALE_WRITE", ["expected_revision"])
        assert row.status == "DRAFT"


def test_재생성_중에_다른_칸을_고치면_재생성_결과를_버린다(live):
    """교사 A 가 재생성을 기다리는 사이 교사 B 가 다른 칸을 고쳤다 — B 의 수정을 지킨다."""
    plan = live["plan"]
    focus, outdoor = _cell(plan, "focus")["item_id"], _cell(plan, "outdoor_play")["item_id"]
    regenerate, edit = _together(
        lambda: _regenerate(plan["id"], focus, 1),
        lambda: _edit(plan["id"], outdoor, "B 가 고친 바깥놀이", 1),
    )
    assert sorted(r.status_code for r in (regenerate, edit)) == [200, 409]
    assert live["idle"] == [0]  # LLM 을 기다리는 동안 열린 transaction 이 없다
    current = _cells(_get(plan["id"]))
    row, _ = _db(live)
    assert row.revision == 2
    if edit.status_code == 200:
        assert _error(regenerate) == (409, "STALE_WRITE", ["expected_revision"])
        assert current[outdoor]["value"] == "B 가 고친 바깥놀이"
        assert current[focus] == _cells(plan)[focus]  # 늦게 온 재생성 결과는 버려졌다
    else:
        assert _error(edit) == (409, "STALE_WRITE", ["expected_revision"])
        assert current[outdoor] == _cells(plan)[outdoor]


def test_재생성과_확정이_겹치면_확정된_계획안을_덮지_않는다(live):
    plan = live["plan"]
    focus = _cell(plan, "focus")["item_id"]
    regenerate, confirm = _together(
        lambda: _regenerate(plan["id"], focus, 1), lambda: _confirm(plan["id"], 1)
    )
    assert sorted(r.status_code for r in (regenerate, confirm)) == [200, 409]
    row, _ = _db(live)
    assert row.revision == 2
    if confirm.status_code == 200:
        assert _error(regenerate) == (409, "ALREADY_CONFIRMED", [])
        assert row.status == "CONFIRMED"
        assert _cells(_get(plan["id"]))[focus]["value"] == _cells(plan)[focus]["value"]
    else:
        assert _error(confirm) == (409, "STALE_WRITE", ["expected_revision"])
        assert row.status == "DRAFT"


def test_동시_확정은_둘_다_200_이고_확정은_한_번만_저장된다(live):
    plan = live["plan"]
    a, b = _together(lambda: _confirm(plan["id"], 1), lambda: _confirm(plan["id"], 1))
    assert (a.status_code, b.status_code) == (200, 200)
    assert a.json() == b.json()  # 진 쪽은 이긴 쪽이 저장한 것을 그대로 받는다
    row, stored = _db(live)
    assert (row.status, row.revision) == ("CONFIRMED", 2)
    assert [e.event_type.value for e in stored.audit.events].count("CONFIRMED") == 1
    assert _get(plan["id"])["confirmed_at"] == a.json()["confirmed_at"]  # 최초 확정 시각 그대로
