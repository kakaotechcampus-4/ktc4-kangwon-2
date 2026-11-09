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
from ssuksak.planning.planner.weekly import WEEKLY_CONTEXT_CELL_PROMPT_VERSION
from ssuksak.planning.venue_policy import VENUE_POLICY_TAG

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


@pytest.mark.parametrize("enabled", [False, True])
def test_trend_applied_follows_the_center_setting_and_the_candidate_evidence(
    world, enabled, monkeypatch
):
    """ADR-072: 원이 켜면 트렌드를 넘기고, 반영한 후보만 trend_applied · TREND Evidence."""
    from ssuksak.planning.application.ports import OptionalContextResult, OptionalContextStatus
    from ssuksak.planning.domain.trend import TrendItem, TrendKind

    items = tuple(
        TrendItem(
            f"youtube:t{n}", kind, f"{kind.value} 자료", "", "채널", "2026-W36", date(2026, 9, 1)
        )
        for n, kind in enumerate(TrendKind)
    )
    seen = []

    class Trends:
        def __init__(self, *, enabled, today):
            seen.append(enabled)
            self._enabled = enabled

        def fetch(self, name):
            if not self._enabled:
                return OptionalContextResult(name, OptionalContextStatus.UNAVAILABLE)
            return OptionalContextResult(name, OptionalContextStatus.AVAILABLE, items)

    monkeypatch.setattr(weekly_router, "TrendContextProvider", Trends)
    world["session"].get(Center, world["mine"]["center"]).trends_enabled = enabled
    world["session"].flush()
    response = client.post(
        "/api/plans/weekly",
        json={"class_id": world["mine"]["class"], "week_id": WEEK, "indoor_play_candidates": True},
    )
    assert response.status_code == 201, response.text
    candidates = response.json()["activity_candidates"]
    assert seen == [enabled]
    assert sum(c["trend_applied"] for c in candidates) == enabled  # mock: 맞는 첫 후보 하나에만
    for c in candidates:
        assert c["trend_applied"] == any(e["source_type"] == "TREND" for e in c["cell"]["evidence"])


def test_앞_주차가_후보에_쓴_근거는_다음_주가_뒤로_미룬다(world, monkeypatch):
    """2026-11-09 하민: 같은 반 · 같은 달 앞 주차 후보 근거만 넘긴다.

    뒤 주차 · 다른 칸은 넘기지 않는다."""
    seen = []
    original = weekly_router._prior_week_evidence
    monkeypatch.setattr(
        weekly_router, "_prior_week_evidence", lambda *a: seen.append(original(*a)) or seen[-1]
    )

    def create(week):
        response = client.post(
            "/api/plans/weekly",
            json={
                "class_id": world["mine"]["class"],
                "week_id": week,
                "indoor_play_candidates": True,
            },
        )
        assert response.status_code == 201, response.text
        return {
            e["source_id"]
            for c in response.json()["activity_candidates"]
            for e in c["cell"]["evidence"]
            if e["source_type"] == "INSTITUTION_SAMPLE"
        }

    second = create(WEEK)
    third = create("2026-09-W3")
    create("2026-09-W1")
    assert seen[0] == () and seen[2] == ()  # 앞 주차가 없거나 뒤 주차만 있다
    assert second and set(seen[1]) == second
    assert len(third & second) < len(second)
    # 11-10 하민: 후보 검색에 준 seed · 앞 주차 근거가 본문에 남는다 — 로그 없이 재현한다.
    stored = (
        world["session"]
        .scalars(select(Plan).where(Plan.kind == "weekly", Plan.week_id == "2026-09-W3"))
        .one()
    )
    plan = from_jsonable(WeeklyPlan, stored.body)
    assert plan.prior_week_evidence == seen[1]
    assert type(plan.candidate_sample_seed) is int and plan.candidate_sample_seed >= 0


@pytest.mark.parametrize("saturday", [False, True])
def test_activity_candidates_copy_split_reload_and_export(world, saturday):
    center = world["session"].get(Center, world["mine"]["center"])
    center.weekly_saturday_enabled = saturday
    world["session"].flush()
    response = client.post(
        "/api/plans/weekly",
        json={"class_id": world["mine"]["class"], "week_id": WEEK, "activity_candidates": True},
    )
    assert response.status_code == 201, response.text
    plan = response.json()
    assert 2 <= len(plan["activity_candidates"]) <= 10

    def group(p):
        return next(s["cells"] for s in p["sections"] if s["section_key"] == "group_activity")

    assert len(group(plan)) == 5 + saturday
    assert all(not c["value"] and c["day"] for c in group(plan))
    item = group(plan)[0]["item_id"]
    url = f"/api/plans/weekly/{plan['id']}/cells/{item}"
    candidate = plan["activity_candidates"][0]
    body = {
        "candidate_item_id": candidate["cell"]["item_id"],
        "expected_revision": plan["revision"],
    }
    result = client.post(url + "/copy-activity", json=body)
    assert result.status_code == 200, result.text
    plan = result.json()
    assert group(plan)[0]["value"] == f"[{candidate['activity_type']}] {candidate['name']}"
    assert client.post(url + "/copy-activity", json=body).status_code == 409
    body["expected_revision"] = plan["revision"]
    assert client.post(url + "/copy-activity", json=body).json()["revision"] == plan["revision"]
    result = client.post(
        url + "/split", json={"axis": "VERTICAL", "expected_revision": plan["revision"]}
    )
    assert result.status_code == 200, result.text
    plan = result.json()
    assert len(group(plan)) == 6 + saturday
    new_id = group(plan)[1]["item_id"]
    second = plan["activity_candidates"][1]
    result = client.post(
        f"/api/plans/weekly/{plan['id']}/cells/{new_id}/copy-activity",
        json={
            "candidate_item_id": second["cell"]["item_id"],
            "expected_revision": plan["revision"],
        },
    )
    assert result.status_code == 200, result.text
    plan = result.json()
    fetched = client.get(f"/api/plans/weekly/{plan['id']}").json()
    assert fetched == plan
    events = client.get(f"/api/plans/weekly/{plan['id']}/audit").json()["items"]
    assert any(
        e["type"] == "TIMETABLE_CHANGED" and e["timetable_change"]["new_cell_id"] == new_id
        for e in events
    )
    assert any(
        e["copied_from"] == candidate["cell"]["item_id"] and e["day"] == "MON" for e in events
    )
    # Delete a spare leaf with a query revision, leaving the two selected leaves intact.
    spare = client.post(
        url + "/split", json={"axis": "VERTICAL", "expected_revision": plan["revision"]}
    ).json()
    spare_id = next(
        c["item_id"]
        for c in group(spare)
        if c["item_id"] not in {x["item_id"] for x in group(plan)}
    )
    delete_url = f"/api/plans/weekly/{plan['id']}/cells/{spare_id}/split"
    assert client.delete(delete_url).status_code == 422
    assert client.delete(delete_url, params={"expected_revision": 0}).status_code == 422
    assert (
        client.delete(delete_url, params={"expected_revision": plan["revision"]}).status_code == 409
    )
    removed = client.delete(delete_url, params={"expected_revision": spare["revision"]})
    assert removed.status_code == 200, removed.text
    plan = removed.json()
    assert all(c["item_id"] != spare_id for c in group(plan))
    assert client.get(f"/api/plans/weekly/{plan['id']}").json() == plan
    result = client.post(
        f"/api/plans/weekly/{plan['id']}/confirm", json={"expected_revision": plan["revision"]}
    )
    assert result.status_code == 200, result.text
    export = client.get(f"/api/plans/weekly/{plan['id']}/export/hwp")
    assert export.status_code == 200, export.text
    with zipfile.ZipFile(BytesIO(export.content)) as archive:
        text = archive.read("Contents/section0.xml").decode()
        assert candidate["name"] in text and second["name"] in text
        assert 'rowSpan="2"' in text
    assert (
        client.post(
            url + "/split",
            json={"axis": "VERTICAL", "expected_revision": result.json()["revision"]},
        ).status_code
        == 409
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
    assert all(s["repeat_by"] == "NONE" for s in plan["sections"])
    cells = {s["section_key"]: s["cells"] for s in plan["sections"]}
    assert all(len(c) == 1 for c in cells.values())  # Section 당 칸 하나
    assert all(c[0]["day"] is None for c in cells.values())
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


def test_DRAFT_도_확정본도_지우고_다시_만들_수_있다(world, db_session):
    """확정본도 지운다(ADR-064, Human Decision 2026-11-05 하민)."""
    created = _create(world).json()
    assert client.delete(f"/api/plans/weekly/{created['id']}").status_code == 204
    again = _create(world).json()
    confirmed = _confirm(again)
    assert confirmed.status_code == 200, confirmed.text

    assert client.delete(f"/api/plans/weekly/{again['id']}").status_code == 204
    assert client.get(f"/api/plans/weekly/{again['id']}").status_code == 404
    assert _create(world).status_code == 201


def test_주간이_딸린_월간은_확정본이어도_지우지_못하고_주간을_지우면_지운다(world):
    """주간은 월간을 부모로 든다. 부모만 지우면 주간 조회가 깨진다(ADR-064)."""
    monthly_id = world["monthly"]["id"]
    weekly = _create(world).json()

    response = client.delete(f"/api/plans/monthly/{monthly_id}")
    assert _error(response) == (409, "IN_USE", [])
    assert response.json()["error"]["message"] == (
        "이 월간계획안으로 만든 주간계획안이 있습니다. 먼저 지워주세요."
    )
    assert client.get(f"/api/plans/monthly/{monthly_id}").status_code == 200

    assert client.delete(f"/api/plans/weekly/{weekly['id']}").status_code == 204
    assert client.delete(f"/api/plans/monthly/{monthly_id}").status_code == 204
    assert client.get(f"/api/plans/monthly/{monthly_id}").status_code == 404


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
    assert (
        audit[-1]["generation_change"]["after"]["rule_version"]
        == WEEKLY_CONTEXT_CELL_PROMPT_VERSION + VENUE_POLICY_TAG
    )


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


def _unconfirm(path: str, revision: int):
    return client.post(f"{path}/unconfirm", json={"expected_revision": revision})


def test_확정을_풀면_다시_고칠_수_있고_부모_월간을_풀면_parent_changed(world):
    plan = _create(world).json()
    path = f"/api/plans/weekly/{plan['id']}"
    assert plan["parent_changed"] is False
    assert _unconfirm(path, 99).json() == plan  # 이미 DRAFT — 아무것도 안 바뀐다
    confirmed = _confirm(plan).json()
    assert _error(_unconfirm(path, plan["revision"]))[:2] == (409, "STALE_WRITE")

    reopened = _unconfirm(path, confirmed["revision"]).json()
    assert (reopened["status"], reopened["confirmed_at"]) == ("DRAFT", None)
    assert reopened["revision"] == confirmed["revision"] + 1
    assert reopened["sections"] == confirmed["sections"]
    goals = _cell(reopened, "goals")["item_id"]
    events = client.get(f"{path}/audit", params={"item_id": goals}).json()["items"]
    assert [e["type"] for e in events if e["scope"] == "PLAN"] == ["CONFIRMED", "UNCONFIRMED"]
    assert _put(reopened, "goals", "다시 고친 목표").status_code == 200

    monthly = world["monthly"]
    unconfirmed = _unconfirm(f"/api/plans/monthly/{monthly['id']}", monthly["revision"])
    assert unconfirmed.status_code == 200, unconfirmed.json()
    assert client.get(path).json()["parent_changed"] is True


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
    assert [e["day"] for e in items] == [None, None]
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
    # 한글 문서의 날짜는 「2026.11.02」 모양이다(하민 결정 2026-11-06).
    assert any(str(edited["display_end_date"]).replace("-", ".") in (t or "") for t in printed)


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


# ── 요일 칸 (Template v0.2.0) ─────────────────────────────────────────────

V0_2_0_PATH = WEEKLY_TEMPLATE_PATH.with_name("weekly_template_a_v0_2_0.json")
V0_2_0_REF = TemplateRef("ssuksak.weekly-template-a", "weekly-template-a-v0.2.0")
DAY_SECTIONS = {"group_activity", "special_program"}


def _use_v0_2_0(monkeypatch) -> None:
    monkeypatch.setattr(weekly_composition, "WEEKLY_TEMPLATE_PATH", V0_2_0_PATH)
    monkeypatch.setattr(weekly_router, "WEEKLY_TEMPLATE_REF", V0_2_0_REF)


def _section(plan: dict, key: str) -> dict:
    return next(s for s in plan["sections"] if s["section_key"] == key)


def _day_cell(plan: dict, key: str, day: str) -> dict:
    return next(c for c in _section(plan, key)["cells"] if c["day"] == day)


@pytest.mark.parametrize(
    ("saturday", "expected_days"),
    [
        (False, ["MON", "TUE", "WED", "THU", "FRI"]),
        (True, ["MON", "TUE", "WED", "THU", "FRI", "SAT"]),
    ],
)
def test_v0_2_0_요일_칸은_운영_요일_순서로_내려가고_조회도_같다(
    world, monkeypatch, saturday, expected_days
):
    _use_v0_2_0(monkeypatch)
    if saturday:
        client.put(
            f"/api/centers/{world['mine']['center']}/settings",
            json={"weekly_saturday_enabled": True},
        )

    response = _create(world)
    assert response.status_code == 201, response.json()
    plan = response.json()

    assert plan["base_template_ref"] == {
        "template_id": "ssuksak.weekly-template-a",
        "template_version": "weekly-template-a-v0.2.0",
    }
    assert plan["operating_days"] == expected_days
    assert {s["section_key"] for s in plan["sections"] if s["repeat_by"] == "DAY"} == DAY_SECTIONS
    none_sections = [s for s in plan["sections"] if s["repeat_by"] == "NONE"]
    assert len(none_sections) == 10
    for section in none_sections:
        assert len(section["cells"]) == 1
        assert section["cells"][0]["day"] is None
    for key in DAY_SECTIONS:
        cells = _section(plan, key)["cells"]
        assert [c["day"] for c in cells] == expected_days
        assert len({c["item_id"] for c in cells}) == len(expected_days)

    assert client.get(f"/api/plans/weekly/{plan['id']}").json() == plan


def test_v0_2_0_요일_칸을_고치면_그_요일만_바뀌고_이력에_요일이_남는다(world, monkeypatch):
    _use_v0_2_0(monkeypatch)
    plan = _create(world).json()
    wed = _section(plan, "group_activity")["cells"][2]

    response = client.put(
        f"/api/plans/weekly/{plan['id']}/cells/{wed['item_id']}",
        json={
            "value": "수요일에 친구와 가을 열매 분류 놀이를 한다.",
            "expected_revision": plan["revision"],
        },
    )

    assert response.status_code == 200, response.json()
    after = response.json()
    assert after["revision"] == plan["revision"] + 1
    assert [c["day"] for c in _section(after, "group_activity")["cells"]] == [
        "MON",
        "TUE",
        "WED",
        "THU",
        "FRI",
    ]
    edited = _section(after, "group_activity")["cells"][2]
    assert (edited["item_id"], edited["day"], edited["value"]) == (
        wed["item_id"],
        "WED",
        "수요일에 친구와 가을 열매 분류 놀이를 한다.",
    )
    assert edited == {**wed, "value": "수요일에 친구와 가을 열매 분류 놀이를 한다."}
    assert [
        (s["section_key"], [c for c in s["cells"] if c["item_id"] != wed["item_id"]])
        for s in after["sections"]
    ] == [
        (s["section_key"], [c for c in s["cells"] if c["item_id"] != wed["item_id"]])
        for s in plan["sections"]
    ]

    items = client.get(
        f"/api/plans/weekly/{plan['id']}/audit", params={"item_id": wed["item_id"]}
    ).json()["items"]
    assert [e["type"] for e in items] == ["CREATED", "TEACHER_EDITED"]
    assert all(
        (e["scope"], e["section_key"], e["day"], e["week_id"], e["item_id"])
        == ("CELL", "group_activity", "WED", WEEK, wed["item_id"])
        for e in items
    )
    assert items[-1]["value_change"]["after"] == "수요일에 친구와 가을 열매 분류 놀이를 한다."


def test_v0_2_0_특별활동_요일_칸은_다시_만들지_않는다(world, monkeypatch):
    _use_v0_2_0(monkeypatch)
    plan = _create(world).json()
    tue = _day_cell(plan, "special_program", "TUE")

    response = client.post(
        f"/api/plans/weekly/{plan['id']}/cells/{tue['item_id']}/regenerate",
        json={"expected_revision": plan["revision"]},
    )

    assert _error(response) == (422, "VALIDATION_FAILED", ["item_id"])
    assert response.json()["error"]["message"] == "이 칸은 다시 만들 수 없습니다."


def test_v0_2_0_대소집단_요일_칸을_다시_만들면_그_요일만_바뀐다(world, monkeypatch):
    _use_v0_2_0(monkeypatch)
    plan = _create(world).json()
    thu = _section(plan, "group_activity")["cells"][3]

    response = client.post(
        f"/api/plans/weekly/{plan['id']}/cells/{thu['item_id']}/regenerate",
        json={"expected_revision": plan["revision"]},
    )

    assert response.status_code == 200, response.json()
    after = response.json()
    assert after["revision"] == plan["revision"] + 1
    assert [c["day"] for c in _section(after, "group_activity")["cells"]] == [
        "MON",
        "TUE",
        "WED",
        "THU",
        "FRI",
    ]
    regenerated = _section(after, "group_activity")["cells"][3]
    assert (regenerated["item_id"], regenerated["day"]) == (thu["item_id"], "THU")
    assert regenerated["value"] != thu["value"]
    assert [
        (s["section_key"], [c for c in s["cells"] if c["item_id"] != thu["item_id"]])
        for s in after["sections"]
    ] == [
        (s["section_key"], [c for c in s["cells"] if c["item_id"] != thu["item_id"]])
        for s in plan["sections"]
    ]

    items = client.get(
        f"/api/plans/weekly/{plan['id']}/audit", params={"item_id": thu["item_id"]}
    ).json()["items"]
    assert [e["type"] for e in items] == ["CREATED", "REGENERATED"]
    assert (items[-1]["section_key"], items[-1]["day"], items[-1]["week_id"]) == (
        "group_activity",
        "THU",
        WEEK,
    )


def test_월간에서_후보를_배치해_확정하면_주간_안전_칸이_그_표시값이다(db_session, teacher):
    """후보 모드 월간(기본) → 배치 → 확정 → 주간. Core 의 후보 복사 분기를 서버 경로로 지난다."""
    seed = _seed(db_session, "가원", "a@example.com")
    teacher.center_id = seed["center"]
    monthly = _monthly(seed, confirm=False)
    candidate = monthly["safety_candidates"][0]
    placed = client.put(
        f"/api/plans/monthly/{monthly['id']}/safety-weeks/{WEEK}",
        json={
            "expected_revision": monthly["revision"],
            "candidate_item_id": candidate["cell"]["item_id"],
        },
    )
    assert placed.status_code == 200, placed.json()
    display = next(w for w in placed.json()["safety_weeks"] if w["week_id"] == WEEK)[
        "display_value"
    ]
    assert display
    confirmed = client.post(
        f"/api/plans/monthly/{monthly['id']}/confirm",
        json={"expected_revision": placed.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.json()

    weekly = client.post("/api/plans/weekly", json={"class_id": seed["class"], "week_id": WEEK})

    assert weekly.status_code == 201, weekly.json()
    safety = next(s for s in weekly.json()["sections"] if s["section_key"] == "safety_education")
    assert safety["cells"][0]["value"] == display


def test_요일_양식_주간은_고정_양식의_요일_칸에_채운다(world, monkeypatch):
    """ADR-051 WD-4 — v0.2.0 계획은 월~토 양식에 (section_key, day) 로 채운다(§9-6)."""
    from lxml import etree

    from app.shared.hwpx import NS, _cells

    monkeypatch.setattr(
        weekly_composition,
        "WEEKLY_TEMPLATE_PATH",
        WEEKLY_TEMPLATE_PATH.with_name("weekly_template_a_v0_2_0.json"),
    )
    monkeypatch.setattr(
        weekly_router,
        "WEEKLY_TEMPLATE_REF",
        replace(weekly_router.WEEKLY_TEMPLATE_REF, template_version="weekly-template-a-v0.2.0"),
    )
    client.put(
        f"/api/centers/{world['mine']['center']}/settings", json={"weekly_saturday_enabled": True}
    )
    plan = _create(world).json()
    row = world["session"].get(Plan, plan["id"])
    saturday = from_jsonable(WeeklyPlan, row.body).operating_days[-1]
    item = from_jsonable(WeeklyPlan, row.body).cell("special_program", saturday).item_id.value
    edited = client.put(
        f"/api/plans/weekly/{plan['id']}/cells/{item}",
        json={"value": "토요 체육", "expected_revision": plan["revision"]},
    ).json()
    indoor = from_jsonable(WeeklyPlan, row.body).cell("indoor_play").item_id.value
    edited = client.put(
        f"/api/plans/weekly/{plan['id']}/cells/{indoor}",
        json={
            "value": "[역할놀이] 가을 가게\n[쌓기놀이]: 열매 길\n분류 없는 교사 메모",
            "expected_revision": edited["revision"],
        },
    ).json()
    assert _confirm(edited).status_code == 200

    response = client.get(f"/api/plans/weekly/{plan['id']}/export/hwp")
    assert response.status_code == 200, response.text
    pdf = client.get(f"/api/plans/weekly/{plan['id']}/export/hwp?format=pdf")  # ADR-061
    assert (pdf.status_code, pdf.headers["content-type"]) == (200, "application/pdf"), pdf.text
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        table = etree.fromstring(archive.read("Contents/section0.xml")).find(".//hp:tbl", NS)
    cells = _cells(table)

    def text(address):
        return "".join(t.text or "" for t in cells[address].iter(f"{{{NS['hp']}}}t"))

    world["session"].refresh(row)
    core = from_jsonable(WeeklyPlan, row.body)
    assert table.get("colCnt") == "7"
    assert [text((10, col)) for col in range(1, 7)] == list("월화수목금토")
    for col, day in enumerate(core.operating_days, start=1):
        assert text((11, col)) == core.cell("group_activity", day).value
    assert [text((19, col)) for col in range(1, 7)] == ["", "", "", "", "", "토요 체육"]
    assert text((2, 1)) == core.cell("theme").value
    assert text((0, 0)).startswith(f"{plan['week_period']['label']} 주간놀이계획안")
    paragraphs = cells[(7, 1)].findall("hp:subList/hp:p", NS)
    assert ["".join(p.itertext()) for p in paragraphs] == [
        "[역할놀이] 가을 가게",
        "[쌓기놀이] 열매 길",
        "분류 없는 교사 메모",
    ]
    assert core.cell("indoor_play").value.startswith("[역할놀이] 가을 가게")
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        header = etree.fromstring(archive.read("Contents/header.xml"))
        assert "[역할놀이] 가을 가게" in archive.read("Preview/PrvText.txt").decode()
    namespaces = {
        **NS,
        "hh": "http://www.hancom.co.kr/hwpml/2011/head",
        "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    }
    style = header.find(f".//hh:paraPr[@id='{paragraphs[0].get('paraPrIDRef')}']", namespaces)
    assert {s.get("value") for s in style.findall(".//hh:lineSpacing", namespaces)} == {"140"}
    assert {s.get("value") for s in style.findall(".//hh:margin/hc:next", namespaces)} == {"100"}
    font_id = paragraphs[0].find("hp:run", NS).get("charPrIDRef")
    assert header.find(f".//hh:charPr[@id='{font_id}']", namespaces).get("height") == "900"


def test_주간_안전교육은_옛_값의_줄표를_떼고_한_줄이다():
    from app.features.plans.export import _weekly_text

    old, new = "[교통안전] - 길을 건너요 - 천천히", "[교통안전] 길을 건너요 - 천천히"
    assert _weekly_text("safety_education", old) == new
    assert _weekly_text("safety_education", new) == new
    assert _weekly_text("safety_education", "") == ""


def test_indoor_display_keeps_blank_and_untagged_teacher_text():
    from app.features.plans.export import _indoor_play_text

    for value in ("", "교사가 직접 쓴 놀이", "[역할놀이] 가게 놀이", "[역할놀이]\n가게 놀이"):
        assert _indoor_play_text(value) == value
    # 2026-11-06 전 값의 「 - 」는 뗀다.
    assert _indoor_play_text("[역할놀이] - 가게 놀이") == "[역할놀이] 가게 놀이"


@pytest.mark.parametrize("saturday", [False, True])
def test_indoor_candidates_select_edit_order_export_and_archive(
    world, saturday, tmp_path, monkeypatch
):
    world["session"].get(Center, world["mine"]["center"]).weekly_saturday_enabled = saturday
    world["session"].flush()
    response = client.post(
        "/api/plans/weekly",
        json={
            "class_id": world["mine"]["class"],
            "week_id": WEEK,
            "indoor_play_candidates": True,
        },
    )
    assert response.status_code == 201, response.text
    plan = response.json()
    assert plan["indoor_play_selection"]
    candidates = [c for c in plan["activity_candidates"] if c["section_key"] == "indoor_play"]
    assert 2 <= len(candidates) <= 10

    def rows(p):
        return next(s["cells"] for s in p["sections"] if s["section_key"] == "indoor_play")

    def add(p, candidate):
        return client.post(
            f"/api/plans/weekly/{p['id']}/indoor-plays",
            json={
                "candidate_item_id": candidate,
                "expected_revision": p["revision"],
            },
        )

    assert len(rows(plan)) == 1 and not rows(plan)[0]["value"]
    assert (
        add(
            {**plan, "revision": plan["revision"] + 1}, candidates[0]["cell"]["item_id"]
        ).status_code
        == 409
    )
    plan = add(plan, candidates[0]["cell"]["item_id"]).json()
    first = rows(plan)[0]
    assert first["value"] == f"[{candidates[0]['activity_type']}] {candidates[0]['name']}"
    plan = add(plan, candidates[1]["cell"]["item_id"]).json()
    assert len(rows(plan)) == 2
    for candidate in candidates[2:7]:
        plan = add(plan, candidate["cell"]["item_id"]).json()
    plan = client.put(
        f"/api/plans/weekly/{plan['id']}/cells/{first['item_id']}",
        json={
            "value": "[역할놀이] 교사가 다듬은 가게 놀이",
            "expected_revision": plan["revision"],
        },
    ).json()
    duplicate = add(plan, candidates[0]["cell"]["item_id"])
    assert duplicate.status_code == 200 and duplicate.json() == plan
    ids = [c["item_id"] for c in reversed(rows(plan))]
    ordered = client.put(
        f"/api/plans/weekly/{plan['id']}/indoor-plays/order",
        json={
            "item_ids": ids,
            "expected_revision": plan["revision"],
        },
    )
    assert ordered.status_code == 200, ordered.text
    plan = ordered.json()
    assert [c["item_id"] for c in rows(plan)] == ids
    assert client.get(f"/api/plans/weekly/{plan['id']}").json() == plan
    other = next(c for c in plan["activity_candidates"] if c["section_key"] == "group_activity")
    assert add(plan, other["cell"]["item_id"]).status_code == 422
    group_cell = next(
        s["cells"][0] for s in plan["sections"] if s["section_key"] == "group_activity"
    )
    copied_group = client.post(
        f"/api/plans/weekly/{plan['id']}/cells/{group_cell['item_id']}/copy-activity",
        json={
            "candidate_item_id": other["cell"]["item_id"],
            "expected_revision": plan["revision"],
        },
    )
    assert copied_group.status_code == 200, copied_group.text
    plan = copied_group.json()
    assert (
        client.put(
            f"/api/plans/weekly/{plan['id']}/indoor-plays/order",
            json={
                "item_ids": [ids[0], ids[0]],
                "expected_revision": plan["revision"],
            },
        ).status_code
        == 422
    )
    with monkeypatch.context() as blocked:
        blocked.setattr(
            weekly_router,
            "_weekly_provider",
            lambda: pytest.fail("No provider needed for a read-only regeneration target"),
        )
        assert (
            client.post(
                f"/api/plans/weekly/{plan['id']}/cells/{ids[0]}/regenerate",
                json={
                    "expected_revision": plan["revision"],
                },
            ).status_code
            == 422
        )
    confirmed = _confirm(plan)
    assert confirmed.status_code == 200, confirmed.text
    response = client.get(f"/api/plans/weekly/{plan['id']}/export/hwp")
    assert response.status_code == 200, response.text
    (tmp_path / f"selected_{6 if saturday else 5}days.hwpx").write_bytes(response.content)
    from lxml import etree

    from app.shared.hwpx import NS, _cells

    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        table = etree.fromstring(archive.read("Contents/section0.xml")).find(".//hp:tbl", NS)
        assert candidates[0]["description"] not in archive.read("Preview/PrvText.txt").decode()
    paragraphs = _cells(table)[(7, 1)].findall("hp:subList/hp:p", NS)
    assert ["".join(p.itertext()) for p in paragraphs] == [c["value"] for c in rows(plan)]
    assert add(confirmed.json(), None).status_code == 409
    plan = client.post(
        f"/api/plans/weekly/{plan['id']}/unconfirm",
        json={
            "expected_revision": confirmed.json()["revision"],
        },
    ).json()
    for item_id in ids:
        deleted = client.delete(
            f"/api/plans/weekly/{plan['id']}/indoor-plays/{item_id}",
            params={"expected_revision": plan["revision"]},
        )
        assert deleted.status_code == 200, deleted.text
        plan = deleted.json()
    assert len(rows(plan)) == 1 and rows(plan)[0]["value"] == ""
    events = client.get(f"/api/plans/weekly/{plan['id']}/audit").json()["items"]
    assert any(e["copied_from"] == candidates[0]["cell"]["item_id"] for e in events)
    assert any(
        e["arrangement_change"] and e["arrangement_change"]["scope"] == "indoor_play"
        for e in events
    )
    manual = client.put(
        f"/api/plans/weekly/{plan['id']}/cells/{rows(plan)[0]['item_id']}",
        json={
            "value": "직접 정한 자유놀이",
            "expected_revision": plan["revision"],
        },
    )
    assert manual.status_code == 200, manual.text
    assert rows(manual.json())[0]["generation"]["method"] == "RULE_ONLY"
    manual_events = client.get(
        f"/api/plans/weekly/{plan['id']}/audit",
        params={
            "item_id": rows(plan)[0]["item_id"],
        },
    ).json()["items"]
    assert manual_events[-1]["type"] == "TEACHER_EDITED"
    assert manual_events[-1]["value_change"]["after"] == "직접 정한 자유놀이"
