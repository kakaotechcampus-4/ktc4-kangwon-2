"""놀이 중심 월간 생성 — Core 연결. 계약은 api-spec §9-7 · ADR-046 §5.

유료 호출은 없다. 자료는 실제 승인 파일을 쓰고, AI 자리는 mock provider 나 가짜를 끼운다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import json

import pytest
from fastapi.testclient import TestClient
from play_monthly_factory import _parent, make_play_monthly, save_play_monthly
from sqlalchemy import func, select
from ssuksak.adapters import play_monthly_composition
from ssuksak.adapters.elice_openai_monthly import (
    MonthlyLlmConfigurationError,
    MonthlyLlmProviderError,
)
from ssuksak.planning.domain.identifiers import PlanId
from ssuksak.planning.domain.play_monthly_plan import PlayMonthlyPlan
from ssuksak.planning.domain.play_project_plan import PlayProjectYearlyPlan
from ssuksak.planning.planner.contracts import RawLlmResponse
from test_weekly_plans_api import _error, world  # noqa: F401

from app.features.plans import monthly_llm
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.main import app
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable

client = TestClient(app)
URL = "/api/plans/monthly/play"


@pytest.fixture(autouse=True)
def _mock(monkeypatch):
    monkeypatch.setattr(monthly_llm, "is_mock", lambda: True)


@pytest.fixture
def parent(world):
    """반의 연간을 확정된 놀이 프로젝트형으로 바꾼다(확정 기록 있음). 월간은 비운다."""
    return _annual(world)


def _annual(world, **changes):
    mine, session = world["mine"], world["session"]
    session.query(Plan).filter(Plan.center_id == mine["center"]).delete()
    plan = _parent(classroom_ref=str(mine["class"]), school_year=2026, **changes)
    PostgresPlanRepository(
        session, center_id=mine["center"], kind="annual", plan_type=PlayProjectYearlyPlan
    ).save(plan.plan_id, plan)
    session.commit()
    return plan


def _post(world, **body):
    return client.post(URL, json={"class_id": world["mine"]["class"], "month": 10, **body})


def _monthly_count(world):
    return world["session"].scalar(
        select(func.count()).select_from(Plan).where(Plan.kind == "monthly")
    )


def _provider(monkeypatch, provider):
    monkeypatch.setattr(monthly_llm, "play_monthly_provider", lambda: provider)


class _Calls:
    """mock 답을 부를 때마다 고친다. 고칠 것이 없으면 mock 그대로다."""

    def __init__(self, *edits):
        self.edits, self.count = edits, 0

    def generate_play_monthly(self, request):
        data = json.loads(
            monthly_llm.MockPlayMonthlyProvider().generate_play_monthly(request).content
        )
        edit = self.edits[self.count] if self.count < len(self.edits) else None
        self.count += 1
        if edit is not None:
            result = edit(data)
            if isinstance(result, Exception):
                raise result
            if isinstance(result, str):
                return RawLlmResponse(result, "fake")
        return RawLlmResponse(json.dumps(data, ensure_ascii=False), "fake")


def _wrapped(cause):
    try:
        raise cause
    except Exception as inner:
        try:
            raise MonthlyLlmProviderError("Elice MLAPI request failed") from inner
        except MonthlyLlmProviderError as error:
            return error


# ── 성공 ───────────────────────────────────────────────────────────────────


def test_생성하면_DRAFT_로_저장되고_다시_읽어도_같다(world, parent):
    response = _post(world, emphasized_row_keys=["cand9"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["status"], body["revision"], body["target_month"]) == ("DRAFT", 1, "2026-10")
    assert body["format"] == "PLAY_MONTHLY"
    assert body["parent"]["period_key"] == "m09_m11"
    assert [p["row_key"] for p in body["parent"]["plays"] if p["emphasized"]] == ["cand9"]
    assert _monthly_count(world) == 1

    again = client.get(f"{URL}/{body['id']}")

    assert again.status_code == 200, again.text
    assert again.json() == body
    row = world["session"].scalar(select(Plan).where(Plan.id == body["id"]))
    assert (row.kind, row.status, row.classroom_ref) == (
        "monthly",
        "DRAFT",
        str(world["mine"]["class"]),
    )
    stored = PostgresPlanRepository(
        world["session"],
        center_id=world["mine"]["center"],
        kind="monthly",
        plan_type=PlayMonthlyPlan,
    ).get(PlanId(row.plan_ref))
    assert stored.parent.lineage.parent_plan_id == parent.plan_id
    refs = stored.references
    assert (refs.curriculum_catalog_id, refs.curriculum_catalog_version) == (
        play_monthly_composition.CURRICULUM_CATALOG
    )
    assert (refs.daily_life_catalog_id, refs.daily_life_catalog_version) == (
        play_monthly_composition.DAILY_LIFE_CATALOG
    )
    assert (
        refs.drill_catalog_id,
        refs.drill_catalog_version,
    ) == play_monthly_composition.DRILL_CATALOG
    assert stored.display.class_name.value  # 반 이름이 문서 머리칸에 들어간다


def test_첫_답이_검사에_걸리면_수리_1회로_만든다(world, parent, monkeypatch):
    def unknown_id(data):
        data["together"][0]["content_ids"] = ["no.such.id"]

    calls = _Calls(unknown_id)
    _provider(monkeypatch, calls)

    response = _post(world)

    assert response.status_code == 201, response.text
    assert calls.count == 2
    assert _monthly_count(world) == 1


# ── 실패: 아무것도 저장하지 않는다 ──────────────────────────────────────────


def test_강조가_그_구간에서_고른_놀이가_아니면_422(world, parent):
    response = _post(world, emphasized_row_keys=["cand1"])  # cand1 은 교사가 고르지 않았다

    assert _error(response) == (422, "VALIDATION_FAILED", ["emphasized_row_keys"])
    assert _monthly_count(world) == 0


@pytest.mark.parametrize(
    "name", ["JsonDailyLifeReferenceRepository", "JsonDrillTopicReferenceRepository"]
)
def test_자료를_쓸_수_없으면_503(world, parent, monkeypatch, name):
    class _Missing:
        def get_catalog(self, catalog_id, catalog_version):
            return None

    monkeypatch.setattr(play_monthly_composition, name, _Missing)

    response = _post(world)

    assert _error(response) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert response.json()["error"]["message"] == (
        "지금은 이 반의 놀이 중심 월간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요."
    )
    assert _monthly_count(world) == 0


def test_LLM_설정이_없으면_부르기_전에_503(world, parent, monkeypatch):
    def _unavailable():
        raise LlmUnavailable("ELICE_MLAPI_BASE_URL")

    monkeypatch.setattr(monthly_llm, "play_monthly_provider", _unavailable)

    assert _error(_post(world)) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert _monthly_count(world) == 0


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (lambda d: _wrapped(LlmBudgetExceeded("429")), (503, "LLM_BUDGET_EXCEEDED", [])),
        (lambda d: MonthlyLlmConfigurationError("stream"), (503, "DEPENDENCY_UNAVAILABLE", [])),
        (lambda d: _wrapped(LlmFailed("timeout")), (500, "GENERATION_FAILED", [])),
        (lambda d: MonthlyLlmProviderError("stream ended"), (500, "GENERATION_FAILED", [])),
        (lambda d: "not json", (500, "GENERATION_FAILED", [])),
    ],
    ids=["budget", "config", "llm-failed", "stream-broken", "parse"],
)
def test_AI_호출_실패는_계약_오류로_바꾼다(world, parent, monkeypatch, edit, expected):
    _provider(monkeypatch, _Calls(edit))

    assert _error(_post(world)) == expected
    assert _monthly_count(world) == 0


def test_수리_뒤에도_검사에_걸리면_500(world, parent, monkeypatch):
    def unknown_id(data):
        data["together"][0]["content_ids"] = ["no.such.id"]

    calls = _Calls(unknown_id, unknown_id)
    _provider(monkeypatch, calls)

    assert _error(_post(world)) == (500, "GENERATION_FAILED", [])
    assert calls.count == 2
    assert _monthly_count(world) == 0


def test_기다리는_사이_그_달_월간이_생기면_409(world, parent, monkeypatch):
    def meanwhile(data):
        other = make_play_monthly(str(world["mine"]["class"]), 2026, 10)
        save_play_monthly(world["session"], world["mine"]["center"], other)

    _provider(monkeypatch, _Calls(meanwhile))

    assert _error(_post(world)) == (409, "ALREADY_EXISTS", ["class_id", "month"])
    assert _monthly_count(world) == 1  # 끼어든 것만 있다


def test_부모_본문에_확정_기록이_없으면_공통_500(world, monkeypatch):
    _annual(world, confirmed=False)  # 행은 확정인데 본문에 CONFIRMED 이벤트가 없다
    calls = _Calls()
    _provider(monkeypatch, calls)

    response = _post(world)

    assert _error(response) == (500, "INTERNAL_ERROR", [])
    assert calls.count == 0
    assert _monthly_count(world) == 0
