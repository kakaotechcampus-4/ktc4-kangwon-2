"""놀이 프로젝트형 연간계획안 생성 · 조회 계약 (api-spec §4 · ADR-043)."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ssuksak.adapters.elice_openai_monthly import (
    MonthlyLlmConfigurationError,
    MonthlyLlmProviderError,
)
from ssuksak.adapters.json_curriculum_reference_repository import JsonCurriculumReferenceRepository
from ssuksak.planning import PlanId
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.planner.contracts import RawLlmResponse
from ssuksak.planning.planner.play_project import PLAY_PROJECT_PROMPT_VERSION

from app.features.centers.models import Center, Class
from app.features.plans import monthly_router, play_project
from app.features.plans import router as plans_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import UuidGenerator
from app.main import app
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable

# Core 가 공개 창구(`ssuksak.planning`)에 아직 안 내놓아 안쪽에서 가져온다 — router.py 와 같다.
from ssuksak.planning.application.generate_play_project_plan import (  # isort: skip
    PLAY_PROJECT_LAYOUT_V0_2 as LAYOUT,
)
from ssuksak.planning.domain.plan import PlanItem, PlanStatus  # isort: skip
from ssuksak.planning.domain.play_project_plan import (  # isort: skip
    ROW_FIELDS,
    PlayPeriodRows,
    PlayProjectYearlyPlan,
    PlayRow,
)
from ssuksak.planning.domain.provenance import (  # isort: skip
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)

client = TestClient(app)
NOW = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
BLOCKED = "놀이 프로젝트형 연간계획안은 아직 수정 · 확정 · 내려받기를 지원하지 않습니다."
GENERATION = GenerationMethodDetail(
    GenerationMethod.RULE_LLM, "play_project.generate", PLAY_PROJECT_PROMPT_VERSION
)


@pytest.fixture(autouse=True)
def _logged_in(teacher):
    return teacher


class _Approved:
    def __init__(self):
        self._inner = JsonCurriculumReferenceRepository()

    def get_catalog(self, catalog_id, catalog_version):
        catalog = self._inner.get_catalog(catalog_id, catalog_version)
        return replace(catalog, activation_status=ActivationStatus.HUMAN_APPROVED)


class _FailingProvider:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def generate_play_project(self, request):
        self.calls += 1
        raise self.error


class _ThirdPeriodInvalidProvider:
    def __init__(self):
        self.calls = []

    def generate_play_project(self, request):
        self.calls.append(request.period_key)
        if len(self.calls) == 3:
            content = json.dumps({"period_key": request.period_key, "rows": []})
            return RawLlmResponse(content=content, model="mock")
        return play_project.MockPlayProjectProvider().generate_play_project(request)


def _approved(monkeypatch, provider=None):
    monkeypatch.setattr(play_project, "curriculum_repository", lambda: _Approved())
    if provider is not None:
        monkeypatch.setattr(play_project, "provider", lambda: provider)
    else:
        monkeypatch.setattr(play_project, "is_mock", lambda: True)


def _wrapped_budget_error():
    try:
        raise LlmBudgetExceeded("429")
    except LlmBudgetExceeded as cause:
        try:
            raise MonthlyLlmProviderError("monthly provider failed") from cause
        except MonthlyLlmProviderError as error:
            return error


def _klass(db_session, center, name) -> Class:
    klass = Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="김선생",
    )
    db_session.add(klass)
    db_session.flush()
    return klass


@pytest.fixture
def world(db_session, teacher):
    """교사의 원 · 놀이 프로젝트형 반 · 월별 주제형 반."""
    center = Center(
        name="테스트어린이집",
        director_name="김원장",
        region_sido="강원특별자치도",
        region_sigungu="춘천시",
    )
    db_session.add(center)
    db_session.flush()
    teacher.center_id = center.id
    return {
        "session": db_session,
        "center_id": center.id,
        "play": _klass(db_session, center, "놀이반"),
        "theme": _klass(db_session, center, "주제반"),
    }


def _plan(classroom_ref: str) -> PlayProjectYearlyPlan:
    """생성 유스케이스가 만드는 모양 그대로 — 구간 4 × 후보 10."""
    ids = UuidGenerator()
    plan_id = ids.new_plan_id()

    def item(value, evidence=()):
        item_id = ids.new_item_id()
        created = AuditEvent(
            event_type=AuditEventType.CREATED,
            occurred_at=NOW,
            plan_id=plan_id,
            item_id=item_id,
            system_actor="play_project_application",
        )
        return PlanItem(item_id, value, evidence, GENERATION, AuditHistory((created,)))

    def row(period_key, n):
        return PlayRow(
            row_key=f"cand{n}",
            play_name=item(f"{period_key} 놀이 {n}"),
            materials=item("종이"),
            support_direction=item("지켜본다"),
            learning=item(
                "자연탐구 - 자연과 더불어 살기 - 자연을 탐구하며\n신체운동·건강 - 몸 - 움직임",
                tuple(
                    EvidenceSource(
                        EvidenceSourceType.CURRICULUM,
                        f"nuri2019.1.1.{k}",
                        source_version="nuri-curriculum-content-v0.1.0",
                    )
                    for k in (1, 2)
                ),
            ),
        )

    return PlayProjectYearlyPlan(
        plan_id=plan_id,
        school_year=2026,
        classroom_ref=classroom_ref,
        target_ages=frozenset({3}),
        status=PlanStatus.DRAFT,
        layout_version=LAYOUT.layout_version,
        periods=tuple(
            PlayPeriodRows(p, tuple(row(p.key, n) for n in range(1, 11))) for p in LAYOUT.periods
        ),
        audit=AuditHistory(
            (
                AuditEvent(
                    event_type=AuditEventType.CREATED,
                    occurred_at=NOW,
                    plan_id=plan_id,
                    system_actor="play_project_application",
                ),
            )
        ),
    )


@pytest.fixture
def saved(world):
    """저장된 놀이 프로젝트형 계획안 (도메인 객체, 행)."""
    session = world["session"]
    plan = _plan(str(world["play"].id))
    PostgresPlanRepository(
        session, center_id=world["center_id"], kind="annual", plan_type=PlayProjectYearlyPlan
    ).save(plan.plan_id, plan)
    session.commit()
    row = session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))
    return plan, row


def _blocked(response):
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert (error["code"], error["message"], error["fields"]) == ("GATE_BLOCKED", BLOCKED, [])


def test_저장한_계획안을_그대로_읽어온다(world, saved):
    plan, row = saved
    repo = PostgresPlanRepository(
        world["session"],
        center_id=world["center_id"],
        kind="annual",
        plan_type=PlayProjectYearlyPlan,
    )
    assert repo.get(PlanId(row.plan_ref)) == plan


def test_단건_조회는_구간_넷과_후보_열을_계약_모양으로_준다(world, saved):
    _, row = saved
    response = client.get(f"/api/plans/annual/{row.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "PLAY_PROJECT"
    assert body["format_version"] == "play-project-layout-v0.2.0"
    assert body["class_id"] == world["play"].id
    assert body["status"] == "DRAFT"
    assert "months" not in body and "audit" not in body
    assert [(p["period_key"], p["label"], p["months"]) for p in body["periods"]] == [
        ("m03_m05", "3월~5월", [3, 4, 5]),
        ("m06_m08", "6월~8월", [6, 7, 8]),
        ("m09_m11", "9월~11월", [9, 10, 11]),
        ("m12_m02", "12월~2월", [12, 1, 2]),
    ]
    for period in body["periods"]:
        assert [c["row_key"] for c in period["candidates"]] == [f"cand{n}" for n in range(1, 11)]
    first = body["periods"][0]["candidates"][0]
    assert set(first) == {"row_key", "play_name", "materials", "support_direction", "learning"}
    assert first["play_name"] == {
        "value": "m03_m05 놀이 1",
        "evidence": [],
        "generation": {
            "method": "RULE_LLM",
            "rule_id": "play_project.generate",
            "rule_version": PLAY_PROJECT_PROMPT_VERSION,
        },
    }
    assert [
        (e["source_type"], e["source_id"], e["source_version"])
        for e in first["learning"]["evidence"]
    ] == [
        ("CURRICULUM", "nuri2019.1.1.1", "nuri-curriculum-content-v0.1.0"),
        ("CURRICULUM", "nuri2019.1.1.2", "nuri-curriculum-content-v0.1.0"),
    ]


def test_월별_주제형은_format_이_MONTHLY_THEME_이고_목록은_둘을_가른다(world, saved):
    created = client.post(
        "/api/plans/annual",
        json={"format": "MONTHLY_THEME", "class_id": world["theme"].id, "form_id": None},
    )
    assert created.status_code == 201, created.text
    assert created.json()["format"] == "MONTHLY_THEME"

    assert (
        client.get(f"/api/plans/annual/{created.json()['id']}").json()["format"] == "MONTHLY_THEME"
    )
    items = client.get("/api/plans/annual").json()["items"]
    assert {i["class_id"]: i["format"] for i in items} == {
        world["theme"].id: "MONTHLY_THEME",
        world["play"].id: "PLAY_PROJECT",
    }


def test_생성은_승인된_누리과정으로_네_구간을_저장하고_읽는다(world, monkeypatch):
    _approved(monkeypatch)

    response = client.post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["format"] == "PLAY_PROJECT"
    assert body["format_version"] == "play-project-layout-v0.2.0"
    assert [(p["period_key"], p["label"], p["months"]) for p in body["periods"]] == [
        ("m03_m05", "3월~5월", [3, 4, 5]),
        ("m06_m08", "6월~8월", [6, 7, 8]),
        ("m09_m11", "9월~11월", [9, 10, 11]),
        ("m12_m02", "12월~2월", [12, 1, 2]),
    ]
    candidates = [candidate for period in body["periods"] for candidate in period["candidates"]]
    assert [len(period["candidates"]) for period in body["periods"]] == [10] * 4
    assert len({candidate["play_name"]["value"] for candidate in candidates}) == 40
    assert all(
        candidate["play_name"]["value"].startswith(label)
        for period, label in zip(
            body["periods"], ("3~5월", "6~8월", "9~11월", "12~2월"), strict=True
        )
        for candidate in period["candidates"]
    )
    for candidate in candidates:
        for key in ("play_name", "materials", "support_direction", "learning"):
            cell = candidate[key]
            assert cell["generation"] == {
                "method": "RULE_LLM",
                "rule_id": "play_project.generate",
                "rule_version": PLAY_PROJECT_PROMPT_VERSION,
            }
            if key == "learning":
                assert 2 <= len(cell["evidence"]) <= 3
                assert all(
                    evidence["source_type"] == "CURRICULUM"
                    and evidence["source_version"] == "nuri-curriculum-content-v0.1.0"
                    for evidence in cell["evidence"]
                )
            else:
                assert cell["evidence"] == []

    row = world["session"].get(Plan, body["id"])
    stored = PostgresPlanRepository(
        world["session"],
        center_id=world["center_id"],
        kind="annual",
        plan_type=PlayProjectYearlyPlan,
    ).get(PlanId(row.plan_ref))
    for period in stored.periods:
        for candidate in period.candidates:
            for key in ROW_FIELDS:
                created = [
                    event
                    for event in getattr(candidate, key).audit.events
                    if event.event_type is AuditEventType.CREATED
                ]
                assert created and all(event.plan_id.value == row.plan_ref for event in created)

    assert client.get(f"/api/plans/annual/{body['id']}").json() == body


def test_요청마다_고정한_계획안_id는_서로_다르다(world, monkeypatch):
    _approved(monkeypatch)
    plans = [
        client.post("/api/plans/annual", json={"class_id": klass.id, "format": "PLAY_PROJECT"})
        for klass in (world["play"], world["theme"])
    ]

    assert [response.status_code for response in plans] == [201, 201]
    refs = [world["session"].get(Plan, response.json()["id"]).plan_ref for response in plans]
    assert refs[0] != refs[1]


def test_승인_전_누리과정이면_503이고_행을_저장하지_않는다(world, monkeypatch):
    monkeypatch.setattr(play_project, "provider", lambda: play_project.MockPlayProjectProvider())

    response = client.post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert response.json()["error"]["message"] == (
        "지금은 이 반의 연간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요."
    )
    assert world["session"].scalar(select(Plan.id).where(Plan.kind == "annual")) is None


def test_세번째_구간이_거절되면_아무것도_저장하지_않는다(world, monkeypatch):
    provider = _ThirdPeriodInvalidProvider()
    _approved(monkeypatch, provider)

    response = client.post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "GENERATION_FAILED"
    assert provider.calls == ["m03_m05", "m06_m08", "m09_m11"]
    assert world["session"].scalar(select(Plan.id).where(Plan.kind == "annual")) is None


def test_이미_연간이_있으면_provider를_부르지_않는다(world, saved, monkeypatch):
    def fail():
        raise AssertionError("중복 반에서 provider를 불렀다")

    monkeypatch.setattr(play_project, "provider", fail)
    response = client.post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_EXISTS"


@pytest.mark.parametrize(
    ("constraint_name", "status_code", "error_code"),
    [
        (plans_router.ANNUAL_UNIQUE, 409, "ALREADY_EXISTS"),
        ("uq_other_constraint", 500, None),
    ],
)
def test_저장_중_유니크_제약_오류만_409로_변환된다(
    world, monkeypatch, constraint_name, status_code, error_code
):
    _approved(monkeypatch)

    def fail_save(*args, **kwargs):
        raise IntegrityError(
            "INSERT",
            {},
            SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint_name)),
        )

    monkeypatch.setattr(PostgresPlanRepository, "save", fail_save)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    )

    assert response.status_code == status_code
    if error_code:
        assert response.json()["error"]["code"] == error_code
    assert (
        world["session"].scalar(
            select(Plan.id).where(
                Plan.kind == "annual", Plan.classroom_ref == str(world["play"].id)
            )
        )
        is None
    )


def test_format과_form_id_요청을_검증한다(world):
    for payload, fields in (
        ({"class_id": world["play"].id}, ["format"]),
        ({"class_id": world["play"].id, "format": "UNKNOWN"}, ["format"]),
        (
            {"class_id": world["play"].id, "format": "PLAY_PROJECT", "form_id": 1},
            ["form_id"],
        ),
    ):
        response = client.post("/api/plans/annual", json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["fields"] == fields


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            MonthlyLlmConfigurationError("this LLM transport cannot stream"),
            503,
            "DEPENDENCY_UNAVAILABLE",
        ),
        (LlmUnavailable("missing configuration"), 503, "DEPENDENCY_UNAVAILABLE"),
        (_wrapped_budget_error(), 503, "LLM_BUDGET_EXCEEDED"),
        (LlmFailed("provider failed"), 500, "GENERATION_FAILED"),
    ],
)
def test_provider_오류가_계약_코드로_변환된다(world, monkeypatch, error, status_code, code):
    _approved(monkeypatch, _FailingProvider(error))

    response = client.post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert world["session"].scalar(select(Plan.id).where(Plan.kind == "annual")) is None


def test_수정_확정_감사_내보내기는_409_이고_행은_그대로다(world, saved):
    _, row = saved
    session = world["session"]
    before = (row.body, row.revision, row.status)

    _blocked(
        client.put(
            f"/api/plans/annual/{row.id}/months/3", json={"theme": "새 주제", "sub_themes": []}
        )
    )
    _blocked(client.post(f"/api/plans/annual/{row.id}/confirm"))
    _blocked(client.get(f"/api/plans/annual/{row.id}/audit"))
    _blocked(client.get(f"/api/plans/{row.id}/export/hwp"))

    session.refresh(row)
    assert (row.body, row.revision, row.status) == before


def test_놀이_프로젝트형_반의_월간_생성은_LLM_앞에서_409(world, saved, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("월간 생성이 부모 검사를 지나 Profile · LLM 경로까지 갔다")

    monkeypatch.setattr(monthly_router, "ready_profile_for_generation", boom)
    monkeypatch.setattr(monthly_router, "monthly_llm_provider", boom)

    response = client.post(
        "/api/plans/monthly",
        json={
            "class_id": world["play"].id,
            "month": 9,
            "profile_ref": {"profile_id": "p", "profile_version": "v"},
        },
    )

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "GATE_BLOCKED"
    assert error["fields"] == ["class_id"]
    assert error["message"] == "놀이 프로젝트형 연간계획안은 월간계획안으로 이어지지 않습니다."
    assert world["session"].scalar(select(Plan.id).where(Plan.kind == "monthly")) is None


def test_지우기는_놀이_프로젝트형도_지난다(world, saved):
    _, row = saved
    row_id = row.id

    assert client.delete(f"/api/plans/annual/{row_id}").status_code == 204
    world["session"].expire_all()
    assert world["session"].get(Plan, row_id) is None
