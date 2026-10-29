"""주간계획안 생성 · 조회 · 목록 · 삭제 API. 진짜 Postgres 위에서 HTTP 로 부른다.

계약은 docs/api-spec.md §9-6 · 주간 계약(docs/weekly-plan-contract.md) §4-1 · §13 이다.
부모 연간 · 월간도 API 로 만들어 확정한다. LLM 은 기본 mock 이다 — **실제 LLM 은 부르지 않는다.**
"""

import importlib.util
import zipfile
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from ssuksak.adapters import weekly_composition
from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.adapters.weekly_composition import WEEKLY_TEMPLATE_PATH
from ssuksak.planning import MonthlyApplicationError, WeeklyPlan
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef

from app.config import settings
from app.features.auth.models import User
from app.features.centers.models import Center, Class
from app.features.plans import monthly_llm, weekly_router
from app.features.plans.codec import from_jsonable, to_jsonable
from app.features.plans.models import Plan
from app.features.template_profiles import service as profile_service
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
WEEK = "2026-09-W2"
TEACHER_INPUT = {"family_link", "event_schedule", "special_program"}


class ApprovedTemplates:
    """월간 lifecycle 테스트와 같다 — 실제 파일을 읽어 테스트 안에서만 승인 상태로 바꾼다."""

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
        "class": klass.id,
        "profile": {"profile_id": ref.profile_id, "profile_version": ref.profile_version},
    }


def _monthly(seed: dict, *, confirm: bool = True) -> dict:
    """부모 연간을 만들어 확정하고 9월 월간을 만든다(확정까지) — 전부 API 로."""
    annual = client.post(
        "/api/plans/annual",
        json={"format": "MONTHLY_THEME", "class_id": seed["class"], "form_id": None},
    )
    assert annual.status_code == 201, annual.json()
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    monthly = client.post(
        "/api/plans/monthly",
        json={"class_id": seed["class"], "month": 9, "profile_ref": seed["profile"]},
    )
    assert monthly.status_code == 201, monthly.json()
    if not confirm:
        return monthly.json()
    confirmed = client.post(
        f"/api/plans/monthly/{monthly.json()['id']}/confirm",
        json={"expected_revision": monthly.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.json()
    return confirmed.json()


@pytest.fixture
def world(db_session, teacher):
    """원 둘. 교사는 가원 소속이고 가원 반에 확정된 9월 월간이 있다."""
    mine = _seed(db_session, "가원", "a@example.com")
    other = _seed(db_session, "나원", "b@example.com")
    teacher.center_id = mine["center"]
    return {"session": db_session, "mine": mine, "other": other, "monthly": _monthly(mine)}


def _create(world, week: str = WEEK):
    return client.post(
        "/api/plans/weekly", json={"class_id": world["mine"]["class"], "week_id": week}
    )


def _error(response) -> tuple[int, str, list[str]]:
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


def _weekly_rows(session) -> list[Plan]:
    return list(session.scalars(select(Plan).where(Plan.kind == "weekly")))


def test_만들면_DRAFT_로_저장하고_계약_모양으로_준다(world):
    response = _create(world)
    assert response.status_code == 201, response.json()
    plan = response.json()

    assert (plan["status"], plan["revision"], plan["week_id"], plan["target_month"]) == (
        "DRAFT",
        1,
        WEEK,
        "2026-09",
    )
    assert plan["generation_mode"] == "LLM_PLANNER"
    assert plan["operating_days"] == ["MON", "TUE", "WED", "THU", "FRI"]
    assert plan["display_end_date"] == plan["week_period"]["end_date"]
    assert plan["parent"]["monthly_plan_id"] == world["monthly"]["id"]
    assert plan["base_template_ref"]["template_id"] == "ssuksak.weekly-template-a"
    cells = {s["section_key"]: s["cells"] for s in plan["sections"]}
    assert all(len(c) == 1 for c in cells.values())  # Section 당 칸 하나
    # 교사 입력 칸은 첫 입력 전에 만든 방식이 없다 — null 로 그대로 내려간다(주간 계약 §10-2).
    assert {key for key, c in cells.items() if c[0]["generation"] is None} == TEACHER_INPUT
    assert cells["theme"][0]["parent_snapshots"]  # 부모 월간 주제 칸 인용
    assert "safety" not in cells["safety_education"][0]

    row = world["session"].get(Plan, plan["id"])
    assert (row.kind, row.week_id, row.target_month, row.status) == (
        "weekly",
        WEEK,
        "2026-09",
        "DRAFT",
    )


def test_저장한_본문은_도메인_객체로_되돌렸다가_다시_같은_본문이_된다(world):
    """codec 이 WeeklyPlan 을 손대지 않고 왕복한다 — generation null · 부모 인용 · 토요일."""
    client.put(
        f"/api/centers/{world['mine']['center']}/settings", json={"weekly_saturday_enabled": True}
    )
    row = world["session"].get(Plan, _create(world).json()["id"])

    plan = from_jsonable(WeeklyPlan, row.body)
    assert to_jsonable(plan) == row.body
    assert from_jsonable(WeeklyPlan, to_jsonable(plan)) == plan
    assert any(cell.generation is None for cell in plan.cells)
    assert any(cell.parent_snapshots for cell in plan.cells)
    assert plan.operating_days[-1].value == "SAT"


def test_토요일_설정은_만들_때_복사되고_뒤에_바꿔도_그대로다(world):
    settings_url = f"/api/centers/{world['mine']['center']}/settings"
    client.put(settings_url, json={"weekly_saturday_enabled": True})
    plan = _create(world).json()
    assert plan["operating_days"][-1] == "SAT"
    start = date.fromisoformat(plan["week_period"]["start_date"])
    assert plan["display_end_date"] == (start + timedelta(days=5)).isoformat()

    client.put(settings_url, json={"weekly_saturday_enabled": False})
    again = client.get(f"/api/plans/weekly/{plan['id']}").json()
    assert again["operating_days"][-1] == "SAT"


def test_조회는_만든_것과_같고_남의_원_것_월간은_404(world):
    created = _create(world).json()
    assert client.get(f"/api/plans/weekly/{created['id']}").json() == created
    assert _error(client.get(f"/api/plans/weekly/{world['monthly']['id']}")) == (
        404,
        "NOT_FOUND",
        ["id"],
    )


def test_남의_원에서는_보이지_않는다(world, teacher):
    created = _create(world).json()
    teacher.center_id = world["other"]["center"]
    assert client.get(f"/api/plans/weekly/{created['id']}").status_code == 404
    assert client.delete(f"/api/plans/weekly/{created['id']}").status_code == 404


@pytest.mark.parametrize("week", ["2026-9-W2", "W2", "2027-03-W1", "2026-02-W1"])
def test_주_모양이_틀리거나_반_학년도_밖이면_422(world, week):
    assert _error(_create(world, week)) == (422, "VALIDATION_FAILED", ["week_id"])
    assert _weekly_rows(world["session"]) == []


def test_부모_월간에_없는_주는_422(world):
    weeks = {w["week_id"] for w in world["monthly"]["weeks"]}
    missing = next(f"2026-09-W{n}" for n in range(1, 7) if f"2026-09-W{n}" not in weeks)
    assert _error(_create(world, missing)) == (422, "VALIDATION_FAILED", ["week_id"])


def test_남의_원_반이면_404(world):
    response = client.post(
        "/api/plans/weekly", json={"class_id": world["other"]["class"], "week_id": WEEK}
    )
    assert _error(response) == (404, "NOT_FOUND", ["class_id"])


def test_월간이_없거나_확정_전이면_GATE_BLOCKED(world, db_session):
    none = _create(world, "2026-10-W2")
    assert _error(none) == (409, "GATE_BLOCKED", ["class_id"])
    assert none.json()["error"]["message"] == "월간계획안을 먼저 만들어 확정해주세요."

    # 확정 상태는 본문이 원본이다 — 칸만 바꾸지 않고 확정 전 월간을 새로 만든다.
    db_session.execute(delete(Plan).where(Plan.id == world["monthly"]["id"]))
    monthly = client.post(
        "/api/plans/monthly",
        json={
            "class_id": world["mine"]["class"],
            "month": 9,
            "profile_ref": world["mine"]["profile"],
        },
    )
    assert monthly.status_code == 201
    draft = _create(world)
    assert _error(draft) == (409, "GATE_BLOCKED", ["class_id"])
    assert draft.json()["error"]["message"] == "월간계획안을 먼저 확정해주세요."


def test_같은_반_같은_주는_하나다(world):
    assert _create(world).status_code == 201
    assert _error(_create(world)) == (409, "ALREADY_EXISTS", ["class_id", "week_id"])


def test_동시_요청이_둘_다_중복_확인을_지나도_유일_인덱스가_409_로_막는다(world, monkeypatch):
    """중복 확인을 둘 다 지난 경우를 만든다 — 저장에서 유일 인덱스에 걸려 500 이 아니라 409 다."""
    assert _create(world).status_code == 201
    monkeypatch.setattr(weekly_router, "_existing", lambda *args: None)
    assert _error(_create(world)) == (409, "ALREADY_EXISTS", ["class_id", "week_id"])
    assert len(_weekly_rows(world["session"])) == 1


class _Failing:
    def __init__(self, error):
        self._error = error

    def generate_weekly(self, request):
        raise self._error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LlmFailed("timeout"), (500, "GENERATION_FAILED", [])),
        (LlmBudgetExceeded("429"), (503, "LLM_BUDGET_EXCEEDED", [])),
    ],
)
def test_LLM_이_실패하면_저장하지_않고_Rule_결과로_대신하지_않는다(
    world, monkeypatch, error, expected
):
    monkeypatch.setattr(weekly_router, "_weekly_provider", lambda: _Failing(error))
    assert _error(_create(world)) == expected
    assert _weekly_rows(world["session"]) == []


def test_real_모드는_W7_전까지_503(world, monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "real")
    assert _error(_create(world)) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert _weekly_rows(world["session"]) == []


def test_주간_Template_이_승인_전이면_503(world, monkeypatch):
    """주간은 Profile 이 없어 교사가 고를 것이 없다 — 서버 참조자료 문제다(결정 ④)."""

    class Pending:
        def __init__(self):
            self._real = JsonMonthlyTemplateRepository(paths=(WEEKLY_TEMPLATE_PATH,))

        def get_template(self, template_id, template_version):
            template = self._real.get_template(template_id, template_version)
            return None if template is None else replace(template, runtime_active=False)

    real = weekly_router.weekly_generation
    monkeypatch.setattr(
        weekly_router,
        "weekly_generation",
        lambda **kwargs: real(**kwargs, template_repository=Pending()),
    )
    assert _error(_create(world)) == (503, "DEPENDENCY_UNAVAILABLE", [])


def test_주간_Template_파일이_없어도_500_이_아니라_503(world, monkeypatch, tmp_path):
    """파일이 없는 것도 승인 전과 같은 참조자료 문제다(Codex W5-02)."""
    monkeypatch.setattr(weekly_composition, "WEEKLY_TEMPLATE_PATH", tmp_path / "missing.json")
    assert _error(_create(world)) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert _weekly_rows(world["session"]) == []


def test_주간_행이_있으면_downgrade_가_지우지_않고_멈춘다(world):
    """rollback 이 확정본까지 지우면 다시 upgrade 해도 돌아오지 않는다(Codex W5-01)."""
    assert _create(world).status_code == 201
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    path = next(versions.glob("*_d0d30e826c87_plans_weekly.py"))
    spec = importlib.util.spec_from_file_location("plans_weekly_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with Operations.context(MigrationContext.configure(world["session"].connection())):
        with pytest.raises(RuntimeError, match="주간계획안 1건"):
            migration.downgrade()
    assert len(_weekly_rows(world["session"])) == 1


def test_목록은_반과_달로_거르고_주_순서다(world):
    second = _create(world, WEEK).json()
    weeks = [w["week_id"] for w in world["monthly"]["weeks"] if w["active"]]
    later = next(w for w in weeks if w > WEEK)
    third = _create(world, later).json()

    listed = client.get(
        "/api/plans/weekly", params={"class_id": world["mine"]["class"], "month": 9}
    ).json()
    assert [item["id"] for item in listed["items"]] == [second["id"], third["id"]]
    assert listed["items"][0]["week_id"] == WEEK
    october = client.get(
        "/api/plans/weekly", params={"class_id": world["mine"]["class"], "month": 10}
    ).json()
    assert october["items"] == []


@pytest.mark.parametrize(("with_class", "month"), [(False, 9), (True, 13)])
def test_목록_달은_반과_함께_1에서_12만(world, with_class, month):
    params = {"month": month, **({"class_id": world["mine"]["class"]} if with_class else {})}
    response = client.get("/api/plans/weekly", params=params)
    assert _error(response) == (422, "VALIDATION_FAILED", ["month"])


def test_목록_남의_원_반은_404(world):
    response = client.get("/api/plans/weekly", params={"class_id": world["other"]["class"]})
    assert response.status_code == 404


def test_DRAFT_는_지우고_다시_만들_수_있다_확정본은_못_지운다(world, db_session):
    created = _create(world).json()
    assert client.delete(f"/api/plans/weekly/{created['id']}").status_code == 204
    again = _create(world)
    assert again.status_code == 201

    db_session.execute(update(Plan).where(Plan.id == again.json()["id"]).values(status="CONFIRMED"))
    assert _error(client.delete(f"/api/plans/weekly/{again.json()['id']}")) == (
        409,
        "GATE_BLOCKED",
        [],
    )


def test_삭제가_읽은_뒤_다른_요청이_확정하면_확정본을_지우지_않는다(world, db_session, monkeypatch):
    """읽기와 지우기 사이에 확정이 끼면 409 · 행이 남는다(Codex W5b-01 실제 경합 재현)."""
    created = _create(world).json()
    real = weekly_router._own_row

    def read_then_confirmed_elsewhere(session, user, plan_id):
        row = real(session, user, plan_id)
        session.expunge(row)  # 삭제는 DRAFT 로 읽은 값을 그대로 들고 간다
        # 다른 요청의 확정은 이미 commit 됐다 — 이 요청이 409 로 되돌려도 남아야 한다.
        session.execute(update(Plan).where(Plan.id == plan_id).values(status="CONFIRMED"))
        session.commit()
        return row

    monkeypatch.setattr(weekly_router, "_own_row", read_then_confirmed_elsewhere)
    assert _error(client.delete(f"/api/plans/weekly/{created['id']}")) == (409, "GATE_BLOCKED", [])
    # 확정본 행이 그대로 남는다(상태 칸만 바꿔 흉내 냈으므로 칸을 본다).
    assert db_session.scalar(select(Plan.status).where(Plan.id == created["id"])) == "CONFIRMED"


@pytest.mark.parametrize("code", ["opaque_actor_required", "repository_contract_violation"])
def test_서버_버그_코드는_생성_실패가_아니라_공통_500(world, monkeypatch, code):
    """정상 경로에 없는 계약 위반은 C2 공통 응답이다 — 원문 비노출 · 저장 없음(Codex W5b-02)."""
    plan = _create(world).json()

    class Broken:
        def execute(self, command):
            raise MonthlyApplicationError(code, "secret detail must not leak")

    monkeypatch.setattr(weekly_router, "weekly_edit", lambda **kwargs: Broken())
    response = TestClient(app, raise_server_exceptions=False).put(
        f"/api/plans/weekly/{plan['id']}/cells/{_cell(plan, 'goals')['item_id']}",
        json={"value": "다른 값", "expected_revision": plan["revision"]},
    )
    assert (response.status_code, response.json()["error"]["code"]) == (500, "INTERNAL_ERROR")
    assert "secret" not in response.text
    assert client.get(f"/api/plans/weekly/{plan['id']}").json()["revision"] == plan["revision"]


def test_연간_test_reset_은_주간까지_지운다(world, monkeypatch):
    monkeypatch.setattr(settings, "allow_test_reset", True)
    assert _create(world).status_code == 201
    annual_id = world["session"].scalar(
        select(Plan.id).where(Plan.kind == "annual", Plan.center_id == world["mine"]["center"])
    )
    assert client.delete(f"/api/plans/annual/{annual_id}/test-reset").status_code == 204
    assert _weekly_rows(world["session"]) == []


# ── W5b 편집 · 재생성 · 확정 · 이력 ──────────────────────────────────────────


def _cell(plan: dict, key: str) -> dict:
    return next(s for s in plan["sections"] if s["section_key"] == key)["cells"][0]


def _put(plan: dict, key: str, value: str, revision: int | None = None):
    return client.put(
        f"/api/plans/weekly/{plan['id']}/cells/{_cell(plan, key)['item_id']}",
        json={"value": value, "expected_revision": revision or plan["revision"]},
    )


def _regenerate(plan: dict, key: str, revision: int | None = None):
    return client.post(
        f"/api/plans/weekly/{plan['id']}/cells/{_cell(plan, key)['item_id']}/regenerate",
        json={"expected_revision": revision or plan["revision"]},
    )


def _confirm(plan: dict, revision: int | None = None):
    return client.post(
        f"/api/plans/weekly/{plan['id']}/confirm",
        json={"expected_revision": revision or plan["revision"]},
    )


def test_교사_입력_칸만_teacher_input_이다(world):
    plan = _create(world).json()
    flags = {s["section_key"]: s["cells"][0]["teacher_input"] for s in plan["sections"]}
    assert {key for key, flag in flags.items() if flag} == {
        "family_link",
        "event_schedule",
        "special_program",
    }


def test_칸을_고치면_revision_이_오르고_교사_수정이_남는다(world):
    plan = _create(world).json()
    before = _cell(plan, "goals")

    response = _put(plan, "goals", "친구와 규칙을 정해 함께 놀이한다.")

    assert response.status_code == 200, response.json()
    after = response.json()
    assert after["revision"] == plan["revision"] + 1
    edited = _cell(after, "goals")
    assert (edited["item_id"], edited["value"]) == (
        before["item_id"],
        "친구와 규칙을 정해 함께 놀이한다.",
    )
    assert edited["generation"] == before["generation"]  # 고쳐도 만든 방식은 그대로
    assert _cell(after, "theme") == _cell(plan, "theme")
    audit = client.get(
        f"/api/plans/weekly/{plan['id']}/audit", params={"item_id": edited["item_id"]}
    )
    assert [e["type"] for e in audit.json()["items"]] == ["CREATED", "TEACHER_EDITED"]
    assert audit.json()["items"][-1]["value_change"]["after"] == "친구와 규칙을 정해 함께 놀이한다."


def test_교사_입력_칸은_첫_입력에_MANUAL_이_되고_teacher_input_은_그대로다(world):
    plan = _create(world).json()
    assert _cell(plan, "event_schedule")["generation"] is None

    cell = _cell(_put(plan, "event_schedule", "10월 9일 한글날 행사").json(), "event_schedule")

    assert cell["generation"]["method"] == "MANUAL"
    assert cell["teacher_input"] is True


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (
            lambda plan: _put(plan, "goals", _cell(plan, "goals")["value"]),
            (422, "VALIDATION_FAILED", ["value"]),
        ),
        (lambda plan: _put(plan, "theme", ""), (422, "VALIDATION_FAILED", ["value"])),
        (
            lambda plan: _put(plan, "goals", "새 목표", revision=plan["revision"] + 1),
            (409, "STALE_WRITE", ["expected_revision"]),
        ),
        (
            lambda plan: client.put(
                f"/api/plans/weekly/{plan['id']}/cells/item_없는_칸",
                json={"value": "x", "expected_revision": plan["revision"]},
            ),
            (404, "NOT_FOUND", ["item_id"]),
        ),
        (
            lambda plan: client.put(
                f"/api/plans/weekly/{plan['id'] + 999}/cells/{_cell(plan, 'goals')['item_id']}",
                json={"value": "x", "expected_revision": plan["revision"]},
            ),
            (404, "NOT_FOUND", ["id"]),
        ),
    ],
    ids=["같은 값", "빈 주제", "옛 revision", "없는 칸", "없는 계획안"],
)
def test_편집_거절은_아무것도_바꾸지_않는다(world, change, expected):
    plan = _create(world).json()
    assert _error(change(plan)) == expected
    assert client.get(f"/api/plans/weekly/{plan['id']}").json()["revision"] == plan["revision"]


def test_칸을_다시_만들면_그_칸만_바뀐다(world):
    plan = _create(world).json()

    response = _regenerate(plan, "goals")

    assert response.status_code == 200, response.json()
    after = response.json()
    assert after["revision"] == plan["revision"] + 1
    assert _cell(after, "goals")["item_id"] == _cell(plan, "goals")["item_id"]
    assert _cell(after, "goals")["value"] != _cell(plan, "goals")["value"]
    for key in ("theme", "focus", "outdoor_play", "indoor_play"):
        assert _cell(after, key) == _cell(plan, key)
    audit = client.get(
        f"/api/plans/weekly/{plan['id']}/audit", params={"item_id": _cell(plan, "goals")["item_id"]}
    ).json()["items"]
    assert audit[-1]["type"] == "REGENERATED"
    assert audit[-1]["generation_change"]["after"]["rule_version"] == "weekly-cell-planner-v1"


@pytest.mark.parametrize("key", ["family_link", "event_schedule", "special_program"])
def test_교사_입력_칸은_다시_만들지_않는다(world, key):
    plan = _create(world).json()
    assert _error(_regenerate(plan, key)) == (422, "VALIDATION_FAILED", ["item_id"])


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LlmFailed("timeout"), (500, "GENERATION_FAILED", [])),
        (LlmBudgetExceeded("429"), (503, "LLM_BUDGET_EXCEEDED", [])),
    ],
)
def test_재생성이_실패하면_칸도_revision_도_그대로다(world, monkeypatch, error, expected):
    plan = _create(world).json()
    monkeypatch.setattr(weekly_router, "_weekly_provider", lambda: _Failing(error))
    assert _error(_regenerate(plan, "goals")) == expected
    assert client.get(f"/api/plans/weekly/{plan['id']}").json() == plan


@pytest.fixture
def real_weekly_llm(monkeypatch):
    """real + `weekly_llm_enabled` + 가짜 주소. 전송 함수만 바꿔 낀다 — 오류 분류 · 어댑터는 진짜다.

    네트워크를 부르지 않는다. 답은 요청을 보고 mock 과 같은 방식으로 만든다 —
    strict schema 에 맞는다.
    """
    calls = []

    def install(behaviour, *, enabled=True):
        monkeypatch.setattr(settings, "llm_mode", "real")
        monkeypatch.setattr(settings, "weekly_llm_enabled", enabled)
        monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://llm.invalid/v1")
        monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-key")

        def post_json(url, *, headers, payload, timeout):
            calls.append(payload)
            return behaviour(payload)

        monkeypatch.setattr(monthly_llm, "post_json", post_json)

    return install, calls


def _answer(payload):
    user = payload["messages"][1]["content"]
    content = RequestAwareWeeklyLlm().generate_weekly(SimpleNamespace(user_content=user)).content
    return {"choices": [{"message": {"content": content}}]}


def _schema(payload) -> str:
    return payload["response_format"]["json_schema"]["name"]


def test_WEEKLY_LLM_ENABLED_가_꺼져_있으면_real_이어도_부르지_않고_503(world, real_weekly_llm):
    install, calls = real_weekly_llm
    plan = _create(world).json()  # mock 으로 하나 만들어 둔다
    install(_answer, enabled=False)
    assert _error(_regenerate(plan, "goals")) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert client.delete(f"/api/plans/weekly/{plan['id']}").status_code == 204
    assert _error(_create(world)) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert calls == []


def test_켜면_생성과_재생성이_실제_어댑터로_간다(world, real_weekly_llm):
    install, calls = real_weekly_llm
    install(_answer)
    created = _create(world)
    assert created.status_code == 201, created.json()
    assert [_schema(c) for c in calls] == ["weekly_plan_proposal"]
    assert all(c["response_format"]["json_schema"]["strict"] for c in calls)

    regenerated = _regenerate(created.json(), "goals")
    assert regenerated.status_code == 200, regenerated.json()
    assert [_schema(c) for c in calls] == ["weekly_plan_proposal", "weekly_cell_proposal"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LlmBudgetExceeded("429"), (503, "LLM_BUDGET_EXCEEDED", [])),
        (LlmFailed("timeout"), (500, "GENERATION_FAILED", [])),
    ],
)
def test_켠_실제_LLM_오류는_계약_코드로_가르고_저장하지_않는다(
    world, real_weekly_llm, error, expected
):
    install, _ = real_weekly_llm

    def fail(payload):
        raise error

    install(fail)
    assert _error(_create(world)) == expected
    assert _weekly_rows(world["session"]) == []


def test_real_모드_재생성도_W7_전까지_503(world, monkeypatch):
    plan = _create(world).json()
    monkeypatch.setattr(settings, "llm_mode", "real")
    assert _error(_regenerate(plan, "goals")) == (503, "DEPENDENCY_UNAVAILABLE", [])


def test_LLM_을_기다리는_사이_누가_고쳤으면_재생성_결과를_버린다(world, monkeypatch):
    plan = _create(world).json()
    session = world["session"]

    class Meanwhile(RequestAwareWeeklyLlm):
        def generate_weekly(self, request):
            # 다른 화면의 편집이 먼저 저장됐다 — revision 이 올라간다.
            session.execute(
                update(Plan).where(Plan.id == plan["id"]).values(revision=Plan.revision + 1)
            )
            return super().generate_weekly(request)

    monkeypatch.setattr(weekly_router, "_weekly_provider", Meanwhile)
    assert _error(_regenerate(plan, "goals")) == (409, "STALE_WRITE", ["expected_revision"])
    assert _cell(client.get(f"/api/plans/weekly/{plan['id']}").json(), "goals") == _cell(
        plan, "goals"
    )


def test_확정은_한_번만_저장되고_재호출은_revision_과_무관하게_200(world):
    plan = _create(world).json()

    first = _confirm(plan)

    assert first.status_code == 200, first.json()
    confirmed = first.json()
    assert confirmed["status"] == "CONFIRMED" and confirmed["confirmed_at"] is not None
    again = _confirm(plan, revision=99)
    assert again.status_code == 200 and again.json() == confirmed
    plan_events = [
        e["type"]
        for e in client.get(f"/api/plans/weekly/{plan['id']}/audit").json()["items"]
        if e["scope"] == "PLAN"
    ]
    assert plan_events.count("CONFIRMED") == 1


def test_확정된_주간은_고치지도_다시_만들지도_않는다(world):
    plan = _create(world).json()
    assert _confirm(plan).status_code == 200
    assert _error(_put(plan, "goals", "새 목표"))[:2] == (409, "ALREADY_CONFIRMED")
    assert _error(_regenerate(plan, "goals"))[:2] == (409, "ALREADY_CONFIRMED")


def test_DRAFT_를_옛_revision_으로_확정하면_409(world):
    plan = _create(world).json()
    assert _error(_confirm(plan, revision=plan["revision"] + 1)) == (
        409,
        "STALE_WRITE",
        ["expected_revision"],
    )


def test_이력은_칸으로_거르고_없는_칸은_404(world):
    plan = _create(world).json()
    _confirm(plan)
    goals = _cell(plan, "goals")["item_id"]

    items = client.get(f"/api/plans/weekly/{plan['id']}/audit", params={"item_id": goals}).json()[
        "items"
    ]

    assert [(e["scope"], e["type"]) for e in items] == [("CELL", "CREATED"), ("PLAN", "CONFIRMED")]
    assert items[0]["week_id"] == WEEK and items[0]["section_key"] == "goals"
    assert _error(
        client.get(f"/api/plans/weekly/{plan['id']}/audit", params={"item_id": "item_없는_칸"})
    ) == (404, "NOT_FOUND", ["item_id"])


# ── 내보내기 (W5c) ────────────────────────────────────────────────────────


def _exported(content: bytes) -> tuple[int, list[str]]:
    from lxml import etree

    from app.shared.hwpx import NS

    with zipfile.ZipFile(BytesIO(content)) as archive:
        section = etree.fromstring(archive.read("Contents/section0.xml"))
    table = section.find(".//hp:tbl", NS)
    return int(table.get("rowCnt")), [t.text for t in section.iter(f"{{{NS['hp']}}}t")]


def test_확정된_주간을_표_양식_hwpx_로_내려준다(world):
    plan = _create(world).json()
    edited = _put(plan, "event_schedule", "운동회 준비").json()
    confirmed = _confirm(edited)
    assert confirmed.status_code == 200, confirmed.text

    response = client.get(f"/api/plans/weekly/{plan['id']}/export/hwp")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/hwp+zip"
    assert f'filename="weekly-plan-{plan["id"]}.hwpx"' in response.headers["content-disposition"]

    rows, printed = _exported(response.content)
    sections = [s for s in edited["sections"] if s["visible"] and s["role"] == "CONTENT"]
    assert rows == 3 + len(sections)  # 머리 3 · Section 마다 한 줄
    for section in sections:
        assert (section["label"] or section["section_key"]) in printed
    assert "운동회 준비" in printed  # 교사 입력 칸도 실린다
    assert _cell(edited, "theme")["value"] in printed
    assert any((t or "").endswith("(만 3·4세)") for t in printed)  # 혼합반 연령 (Codex W5c-01)
    assert any(edited["week_period"]["label"] in (t or "") for t in printed)
    assert any(str(edited["display_end_date"]) in (t or "") for t in printed)


def test_내보내기_연령은_단일과_혼합을_만_N세로_쓴다():
    from app.features.plans.export import _ages_label

    assert _ages_label(frozenset({4})) == "만 4세"
    assert _ages_label(frozenset({5, 3, 4})) == "만 3·4·5세"


def test_주간은_확정_전에_내보낼_수_없다(world):
    plan = _create(world).json()
    response = client.get(f"/api/plans/weekly/{plan['id']}/export/hwp")
    assert _error(response) == (409, "GATE_BLOCKED", [])


def test_남의_원_주간은_내보낼_수_없고_404(world):
    plan = _create(world).json()
    assert _confirm(plan).status_code == 200
    world["session"].execute(
        update(Plan).where(Plan.id == plan["id"]).values(center_id=world["other"]["center"])
    )
    world["session"].commit()
    assert client.get(f"/api/plans/weekly/{plan['id']}/export/hwp").status_code == 404


def test_주간_제출_문서에_출처가_섞이지_않는다(world):
    plan = _create(world).json()
    assert _confirm(plan).status_code == 200
    response = client.get(f"/api/plans/weekly/{plan['id']}/export/hwp")
    _, printed = _exported(response.content)
    joined = "\n".join(text for text in printed if text)
    for banned in ("evidence", "generation", "INSTITUTION_SAMPLE", "RULE_LLM", "mock"):
        assert banned not in joined
