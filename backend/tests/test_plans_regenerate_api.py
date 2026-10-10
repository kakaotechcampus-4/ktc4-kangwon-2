"""연간 선택 월 재생성 API (BE-Y2b, 잠정 계약 — docs/provisional-policy-decisions.md).

진짜 Postgres 위에서 HTTP 로 부른다. 생성기는 mock 이다(**유료 LLM 호출 없음**). 앞부분은 한 연결
(롤백되는 db_session), 뒷부분은 **서로 다른 연결**로 LLM 을 기다리는 재생성과 PUT · 확정 · 다른
재생성을 겹친다. 재생성은 LLM 을 기다리는 동안 행을 잠그지 않고, 저장을 「DRAFT 이고 본문 ·
소주제가 읽은 그대로일 때만」 한 문장으로 한다 — 못 쓰면 아무것도 쓰지 않고 409 다.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.orm import Session
from ssuksak.adapters.deterministic_theme_text_generator import DeterministicThemeTextGenerator
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository
from ssuksak.planning import CatalogSelector
from ssuksak.planning.application import regenerate_yearly_plan_item as core_regenerate
from ssuksak.planning.application.yearly_ports import ThemeTextResult
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.rules.errors import YearlyRuleError
from ssuksak.planning.rules.yearly_theme_selection import RULE_ID as THEME_SELECTION_RULE_ID

from app.db import engine
from app.features.centers.models import Center, Class
from app.features.plans import router as annual_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.main import app
from app.shared.auth.dependency import current_user
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable

client = TestClient(app)
SUFFIX = " · 다시"
HOLD = 1.0
MONTH_OUT_KEYS = {
    "month",
    "theme",
    "sub_themes",
    "safety_education",
    "safety_education_state",
    "evidence",
    "generation",
}


@pytest.fixture(autouse=True)
def _mock_generator(monkeypatch):
    """mock 생성기에 꼬리를 붙여 다시 만든 값이 눈에 보이게 한다."""
    monkeypatch.setattr(
        annual_router,
        "theme_text_generator",
        lambda: DeterministicThemeTextGenerator(suffix=SUFFIX),
    )


def _center_class(session, name: str) -> dict:
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


def _regenerate(plan_id, month):
    return client.post(f"/api/plans/annual/{plan_id}/months/{month}/regenerate")


def _put(plan_id, month, theme, sub_themes=()):
    return client.put(
        f"/api/plans/annual/{plan_id}/months/{month}",
        json={"theme": theme, "sub_themes": list(sub_themes)},
    )


def _confirm(plan_id):
    return client.post(f"/api/plans/annual/{plan_id}/confirm")


def _months(plan_id) -> dict:
    return {m["month"]: m for m in client.get(f"/api/plans/annual/{plan_id}").json()["months"]}


def _error(response):
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


def _row_snapshot(session_or_none, plan_id) -> tuple:
    """저장된 칸 전부. 재생성이 실패하면 이것이 그대로여야 한다."""
    if session_or_none is None:
        with Session(engine) as session:
            row = session.get(Plan, plan_id)
            return (row.body, row.status, row.sub_themes, row.confirmed_at, row.updated_at)
    session_or_none.expunge_all()
    row = session_or_none.get(Plan, plan_id)
    return (row.body, row.status, row.sub_themes, row.confirmed_at, row.updated_at)


def _events(body: dict, kind: str) -> list[int]:
    """그 종류의 이벤트가 붙은 달(계획안 단위면 0)."""
    months = [0 for e in body["audit"]["events"] if e["event_type"] == kind]
    for period in body["periods"]:
        months += [
            period["period"]["calendar_month"]
            for e in period["theme"]["audit"]["events"]
            if e["event_type"] == kind
        ]
    return months


# ── 한 연결 — 계약 · 소주제 · 실패 ─────────────────────────────────────────


@pytest.fixture
def world(db_session, teacher):
    mine = _center_class(db_session, "가원")
    theirs = _center_class(db_session, "나원")
    teacher.center_id = theirs["center"]
    their_plan = _create(theirs["class"])
    teacher.center_id = mine["center"]
    return {"session": db_session, "plan": _create(mine["class"]), "their_plan": their_plan}


def test_그_달만_다시_만들고_다른_11개월은_그대로다(world, teacher):
    session, plan_id = world["session"], world["plan"]
    before = _months(plan_id)

    response = _regenerate(plan_id, 9)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == MONTH_OUT_KEYS  # 기존 MonthOut 그대로
    assert body["month"] == 9 and body["theme"].endswith(SUFFIX)
    assert body["generation"] == {
        "method": "RULE_LLM",
        "rule_id": THEME_SELECTION_RULE_ID,
        "rule_version": "v2",
    }
    (reference,) = [e for e in body["evidence"] if e["source_type"] == "THEME_REFERENCE"]
    assert reference["source_version"] == "theme-reference-v0.1.2"
    after = _months(plan_id)
    assert after[9] == body
    assert {m: v for m, v in after.items() if m != 9} == {m: v for m, v in before.items() if m != 9}
    stored = _row_snapshot(session, plan_id)[0]
    assert _events(stored, "REGENERATED") == [9]
    period = next(p for p in stored["periods"] if p["period"]["calendar_month"] == 9)
    event = period["theme"]["audit"]["events"][-1]
    assert event["actor_id"]["value"] == f"user_{teacher.id}"
    assert event["value_change"] == {"before": before[9]["theme"], "after": body["theme"]}
    assert event["generation_change"]["after"]["rule_id"] == THEME_SELECTION_RULE_ID
    audit = client.get(f"/api/plans/annual/{plan_id}/audit").json()["items"]
    assert [(e["type"], e["month"]) for e in audit if e["type"] == "REGENERATED"] == [
        ("REGENERATED", 9)
    ]


def test_교사가_고친_주제도_명시적으로_다시_만들면_바뀌고_이전_값은_Audit_에_남는다(world):
    session, plan_id = world["session"], world["plan"]
    assert _put(plan_id, 10, "교사가 쓴 10월 주제").status_code == 200

    response = _regenerate(plan_id, 10)

    assert response.status_code == 200, response.text
    assert response.json()["theme"] != "교사가 쓴 10월 주제"
    stored = _row_snapshot(session, plan_id)[0]
    period = next(p for p in stored["periods"] if p["period"]["calendar_month"] == 10)
    events = period["theme"]["audit"]["events"]
    assert [e["event_type"] for e in events][-2:] == ["TEACHER_EDITED", "REGENERATED"]
    assert events[-1]["value_change"]["before"] == "교사가 쓴 10월 주제"


@pytest.mark.parametrize("sub_themes", [None, [], ["", "   "]])
def test_의미_있는_소주제가_없으면_다시_만든다(world, sub_themes):
    plan_id = world["plan"]
    if sub_themes is not None:
        theme = _months(plan_id)[4]["theme"]
        assert _put(plan_id, 4, theme, sub_themes).status_code == 200
    assert _regenerate(plan_id, 4).status_code == 200


@pytest.mark.parametrize("sub_themes", [["낙엽 관찰"], ["", "가을 곤충"]])
def test_의미_있는_소주제가_있으면_422_이고_아무것도_바뀌지_않는다(world, sub_themes):
    session, plan_id = world["session"], world["plan"]
    theme = _months(plan_id)[11]["theme"]
    assert _put(plan_id, 11, theme, sub_themes).status_code == 200
    before = _row_snapshot(session, plan_id)

    assert _error(_regenerate(plan_id, 11)) == (422, "VALIDATION_FAILED", ["sub_themes"])
    assert _row_snapshot(session, plan_id) == before


def test_없는_것_남의_것_확정된_것(world):
    session, plan_id = world["session"], world["plan"]
    monthly = Plan(
        plan_ref="plan_monthly_for_be_y2b",
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
        assert _error(_regenerate(other, 9)) == (404, "NOT_FOUND", ["id"])
    assert _error(_regenerate(plan_id, 13)) == (404, "NOT_FOUND", ["month"])

    assert _confirm(plan_id).status_code == 200
    before = _row_snapshot(session, plan_id)
    assert _error(_regenerate(plan_id, 9)) == (409, "ALREADY_CONFIRMED", [])
    assert _row_snapshot(session, plan_id) == before


def test_로그인하지_않으면_401(world):
    app.dependency_overrides.pop(current_user)
    response = _regenerate(world["plan"], 9)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def _breaks_generation(monkeypatch, generate):
    class Broken:
        def generate(self, requests):
            return generate(requests)

    monkeypatch.setattr(annual_router, "theme_text_generator", lambda: Broken())


def _wrong_theme(requests):
    return tuple(ThemeTextResult(r.period, r.theme_id + "_x", "엉뚱한 주제") for r in requests)


def _no_config():
    """생성기를 **만드는 단계**가 실패한다(설정 없음)."""
    raise LlmUnavailable("키가 없다")


def _raise(error):
    def generate(requests):
        raise error

    return generate


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (
            lambda mp: _breaks_generation(mp, _raise(LlmFailed("timeout"))),
            (500, "GENERATION_FAILED"),
        ),
        (
            lambda mp: _breaks_generation(mp, _raise(LlmBudgetExceeded("429"))),
            (503, "LLM_BUDGET_EXCEEDED"),
        ),
        (
            lambda mp: mp.setattr(annual_router, "theme_text_generator", _no_config),
            (503, "DEPENDENCY_UNAVAILABLE"),
        ),
        (lambda mp: _breaks_generation(mp, _wrong_theme), (500, "GENERATION_FAILED")),
        (
            lambda mp: mp.setattr(
                annual_router,
                "CATALOG",
                CatalogSelector("ssuksak.yearly-theme-reference", "theme-reference-v9.9.9"),
            ),
            (503, "DEPENDENCY_UNAVAILABLE"),
        ),
        (
            lambda mp: mp.setattr(
                JsonThemeReferenceRepository,
                "get_catalog",
                lambda self, i, v, _o=JsonThemeReferenceRepository.get_catalog: replace(
                    _o(self, i, v), activation_status=ActivationStatus.PENDING_HUMAN_REVIEW
                ),
            ),
            (503, "DEPENDENCY_UNAVAILABLE"),
        ),
        (
            lambda mp: mp.setattr(
                core_regenerate,
                "select_theme_for_period",
                lambda **_: (_ for _ in ()).throw(YearlyRuleError(THEME_SELECTION_RULE_ID, "x")),
            ),
            (422, "VALIDATION_FAILED"),
        ),
    ],
    ids=[
        "llm-failed",
        "budget",
        "no-config",
        "wrong-result",
        "unknown-catalog",
        "unapproved-catalog",
        "no-candidate",
    ],
)
def test_재생성이_실패하면_아무것도_바뀌지_않고_Core_문구도_내보내지_않는다(
    world, monkeypatch, setup, expected
):
    session, plan_id = world["session"], world["plan"]
    before = _row_snapshot(session, plan_id)
    setup(monkeypatch)

    response = _regenerate(plan_id, 9)

    assert (response.status_code, response.json()["error"]["code"]) == expected
    message = response.json()["error"]["message"]
    assert all(token not in message for token in ("Yearly", "catalog", "Catalog", "theme_id", "_"))
    if expected[0] == 422:
        assert response.json()["error"]["fields"] == ["month"]
    assert _row_snapshot(session, plan_id) == before


def test_저장이_깨지면_롤백되고_아무것도_남지_않는다(world, monkeypatch):
    session, plan_id = world["session"], world["plan"]
    before = _row_snapshot(session, plan_id)

    def boom(self, *args, **kwargs):
        raise RuntimeError("저장 중 끊김")

    monkeypatch.setattr(PostgresPlanRepository, "update_if_unchanged", boom)
    response = TestClient(app, raise_server_exceptions=False).post(
        f"/api/plans/annual/{plan_id}/months/9/regenerate"
    )
    assert response.status_code == 500
    assert _row_snapshot(session, plan_id) == before


# ── 서로 다른 연결 — LLM 을 기다리는 재생성과 다른 쓰기 ─────────────────────


@pytest.fixture
def live(_schema, teacher):
    with Session(engine) as session:
        ids = _center_class(session, "연간 재생성 동시성 테스트원")
        session.commit()
    teacher.center_id = ids["center"]
    try:
        yield {**ids, "plan": _create(ids["class"])}
    finally:
        with Session(engine) as session:
            session.execute(delete(Plan).where(Plan.center_id == ids["center"]))
            session.execute(delete(Class).where(Class.id == ids["class"]))
            session.execute(delete(Center).where(Center.id == ids["center"]))
            session.commit()


class _Waiting:
    """LLM 을 기다리는 생성기. `pause` 만큼의 호출을 풀릴 때까지 붙잡는다."""

    def __init__(self, pause: int = 1):
        self.reached = threading.Semaphore(0)
        self.release = threading.Event()
        self._left = pause
        self._lock = threading.Lock()

    def generate(self, requests):
        with self._lock:
            hold, self._left = self._left > 0, self._left - 1
        if hold:
            self.reached.release()
            assert self.release.wait(timeout=20)
        return DeterministicThemeTextGenerator(suffix=SUFFIX).generate(requests)

    def wait_reached(self, count: int = 1):
        for _ in range(count):
            assert self.reached.acquire(timeout=20)


@pytest.fixture
def waiting(monkeypatch):
    generator = _Waiting()
    monkeypatch.setattr(annual_router, "theme_text_generator", lambda: generator)
    return generator


def _paused(monkeypatch, name: str):
    """라우터의 PUT · 확정 use case 를 「잠그고 읽은 뒤 · 저장 전」에 멈춘다."""
    reached, release = threading.Event(), threading.Event()
    original = getattr(annual_router, name)

    class Paused(original):
        def execute(self, command):
            reached.set()
            assert release.wait(timeout=20)
            return super().execute(command)

    monkeypatch.setattr(annual_router, name, Paused)
    return reached, release


def _stored(plan_id) -> dict:
    with Session(engine) as session:
        return session.get(Plan, plan_id).body


def test_A_재생성_중에_확정되면_409_이고_확정이_남는다(live, waiting):
    plan_id = live["plan"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        regen = executor.submit(_regenerate, plan_id, 9)
        waiting.wait_reached()
        # LLM 을 기다리는 동안 행이 잠겨 있지 않다 — 확정이 바로 끝난다.
        assert _confirm(plan_id).status_code == 200
        waiting.release.set()
        response = regen.result(timeout=30)

    assert _error(response) == (409, "ALREADY_CONFIRMED", [])
    body = _stored(plan_id)
    assert body["status"] == "CONFIRMED"
    assert (_events(body, "CONFIRMED"), _events(body, "REGENERATED")) == ([0], [])


def test_B_재생성_중에_다른_달을_고치면_409_이고_고친_것이_남는다(live, waiting):
    plan_id = live["plan"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        regen = executor.submit(_regenerate, plan_id, 9)
        waiting.wait_reached()
        assert _put(plan_id, 3, "고친 3월", ["첫 주"]).status_code == 200
        waiting.release.set()
        response = regen.result(timeout=30)

    assert _error(response) == (409, "STALE_WRITE", [])
    body = _stored(plan_id)
    assert _months(plan_id)[3]["theme"] == "고친 3월"
    assert _events(body, "REGENERATED") == []
    assert _events(body, "TEACHER_EDITED") == [3]


def test_C_먼저_끝난_재생성만_남는다(live, waiting):
    plan_id = live["plan"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(_regenerate, plan_id, 9)
        waiting.wait_reached()
        second = _regenerate(plan_id, 10)  # 이 호출은 붙잡지 않는다
        waiting.release.set()
        first = first.result(timeout=30)

    assert second.status_code == 200
    assert _error(first) == (409, "STALE_WRITE", [])
    assert _events(_stored(plan_id), "REGENERATED") == [10]


def test_D_PUT_이_잠금을_쥐고_있으면_재생성_저장은_기다렸다가_409(live, waiting, monkeypatch):
    plan_id = live["plan"]
    put_reached, put_release = _paused(monkeypatch, "EditYearlyPlanItem")
    with ThreadPoolExecutor(max_workers=2) as executor:
        regen = executor.submit(_regenerate, plan_id, 9)
        waiting.wait_reached()
        put = executor.submit(_put, plan_id, 3, "잠근 PUT")
        assert put_reached.wait(timeout=20)  # PUT 이 행을 잠그고 읽었다
        waiting.release.set()  # 재생성이 저장하러 간다
        time.sleep(HOLD)
        regen_blocked = not regen.done()
        put_release.set()
        put, regen = put.result(timeout=30), regen.result(timeout=30)

    assert regen_blocked  # 조건부 UPDATE 가 PUT 의 잠금을 기다렸다
    assert put.status_code == 200
    assert _error(regen) == (409, "STALE_WRITE", [])
    body = _stored(plan_id)
    assert _months(plan_id)[3]["theme"] == "잠근 PUT"
    assert _events(body, "REGENERATED") == []


def test_E_확정이_잠금을_쥐고_있으면_재생성_저장은_기다렸다가_409(live, waiting, monkeypatch):
    plan_id = live["plan"]
    confirm_reached, confirm_release = _paused(monkeypatch, "ConfirmYearlyPlan")
    with ThreadPoolExecutor(max_workers=2) as executor:
        regen = executor.submit(_regenerate, plan_id, 9)
        waiting.wait_reached()
        confirm = executor.submit(_confirm, plan_id)
        assert confirm_reached.wait(timeout=20)
        waiting.release.set()
        time.sleep(HOLD)
        regen_blocked = not regen.done()
        confirm_release.set()
        confirm, regen = confirm.result(timeout=30), regen.result(timeout=30)

    assert regen_blocked
    assert confirm.status_code == 200
    assert _error(regen) == (409, "ALREADY_CONFIRMED", [])
    body = _stored(plan_id)
    assert body["status"] == "CONFIRMED"
    assert (_events(body, "CONFIRMED"), _events(body, "REGENERATED")) == ([0], [])


def test_F_재생성_중에_그_달_소주제가_생기면_저장하지_않는다(live, waiting):
    plan_id = live["plan"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        regen = executor.submit(_regenerate, plan_id, 9)
        waiting.wait_reached()
        # 본문은 그대로 두고 소주제만 바꾼다 — 저장 조건의 소주제 비교만으로 막혀야 한다.
        with Session(engine) as session:
            session.execute(
                update(Plan).where(Plan.id == plan_id).values(sub_themes={"9": ["새 소주제"]})
            )
            session.commit()
        before = _row_snapshot(None, plan_id)
        waiting.release.set()
        response = regen.result(timeout=30)

    assert _error(response) == (409, "STALE_WRITE", [])
    assert _row_snapshot(None, plan_id) == before
    assert _events(before[0], "REGENERATED") == []


def test_F2_재생성_중에_PUT_으로_소주제를_적어도_저장하지_않는다(live, waiting):
    plan_id = live["plan"]
    theme = _months(plan_id)[9]["theme"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        regen = executor.submit(_regenerate, plan_id, 9)
        waiting.wait_reached()
        assert _put(plan_id, 9, theme, ["가을 소풍"]).status_code == 200
        waiting.release.set()
        response = regen.result(timeout=30)

    assert _error(response) == (409, "STALE_WRITE", [])
    assert _months(plan_id)[9]["sub_themes"] == ["가을 소풍"]
    assert _events(_stored(plan_id), "REGENERATED") == []


def test_G_같은_달을_동시에_다시_만들면_하나만_저장된다(live, monkeypatch):
    plan_id = live["plan"]
    generator = _Waiting(pause=2)
    monkeypatch.setattr(annual_router, "theme_text_generator", lambda: generator)
    with ThreadPoolExecutor(max_workers=2) as executor:
        calls = [executor.submit(_regenerate, plan_id, 9) for _ in range(2)]
        generator.wait_reached(2)  # 둘 다 같은 본문을 읽고 LLM 을 기다린다
        generator.release.set()
        responses = [call.result(timeout=30) for call in calls]

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["error"]["code"] == "STALE_WRITE"
    assert _events(_stored(plan_id), "REGENERATED") == [9]
