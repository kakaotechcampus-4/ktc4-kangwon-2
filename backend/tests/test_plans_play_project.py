"""놀이 프로젝트형 연간계획안의 조회 계약 (api-spec §4 「놀이 프로젝트형 응답」 · ADR-043).

생성 API 는 아직 없다. 도메인 객체를 저장소로 직접 저장해 읽기 · 막기만 본다. LLM 은 부르지 않는다.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from ssuksak.planning import PlanId
from ssuksak.planning.planner.play_project import PLAY_PROJECT_PROMPT_VERSION

from app.features.centers.models import Center, Class
from app.features.plans import monthly_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import UuidGenerator
from app.main import app

# Core 가 공개 창구(`ssuksak.planning`)에 아직 안 내놓아 안쪽에서 가져온다 — router.py 와 같다.
from ssuksak.planning.application.generate_play_project_plan import (  # isort: skip
    PLAY_PROJECT_LAYOUT_V0_2 as LAYOUT,
)
from ssuksak.planning.domain.plan import PlanItem, PlanStatus  # isort: skip
from ssuksak.planning.domain.play_project_plan import (  # isort: skip
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
        "/api/plans/annual", json={"class_id": world["theme"].id, "form_id": None}
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
