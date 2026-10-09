"""월간계획안 생성 · 조회 API 와 양식 설정 조회 API. 진짜 Postgres 위에서 HTTP 로 부른다.

계약은 docs/api-spec.md §9-1 · §9-2 다. 부모 연간도 API 로 만들고 확정한다.

기반 Template v0.1.1 · v0.2.1 은 **사람 승인 대기**다. Profile 은 OD-N11 (A) — 테스트 안에서만
`replace(template, runtime_active=True)` — 로 만들고, 생성 직전 승인 검사도 같은 객체로 바꿔 낀다
(`service.TEMPLATES`). 데이터 파일과 운영 코드는 그대로다. LLM 은 기본 `mock`(요청 기반 결정적
provider)이고, real 경로는 전송 함수를 바꿔 껴서 오류 분류만 본다.
**실제 Luna-6 는 부르지 않는다.**
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning import ActivityCatalogSelector, MonthlyPlan, PlanId, TemplateProfileRef
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

PLAIN = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.1.1")
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
def _approved(teacher, monkeypatch):
    """로그인한 교사로 고정하고, 생성 직전 승인 검사를 OD-N11 (A) 객체로 본다."""
    monkeypatch.setattr(profile_service, "TEMPLATES", ApprovedTemplates())
    return teacher


def _center(session, name) -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _member(session, center, email) -> User:
    """Profile 의 `created_by` 가 가리킬 진짜 계정."""
    user = User(
        email=email,
        name="선생",
        password_hash=b"x" * 64,
        password_salt=b"y" * 16,
        center_id=center.id,
    )
    session.add(user)
    session.flush()
    return user


def _class(session, center, name="햇살반") -> Class:
    klass = Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=3,
        age_max=4,
        teacher_name="선생",
    )
    session.add(klass)
    session.flush()
    return klass


def _profile(session, center_id: int, user_id: int, template=FOCUS):
    """원 소유 READY v1. RULE 이 아닌 LLM 경로라 focus(소주제)를 켠다."""
    optional = ("focus",) if template == FOCUS else ()
    ref = PostgresTemplateProfileRepository(session, center_id=center_id).start_from_reference(
        ApprovedTemplates(),
        template,
        selected_optional_keys=optional,
        display_labels=LABELS,
        focus_variant=SemanticVariant.SUBTHEME if optional else None,
        actor_id=user_id,
    )
    return {"profile_id": ref.profile_id, "profile_version": ref.profile_version}


def _annual(class_id: int, *, confirm=True) -> int:
    response = client.post("/api/plans/annual", json={"class_id": class_id, "form_id": None})
    assert response.status_code == 201, response.json()
    plan_id = response.json()["id"]
    if confirm:
        assert client.post(f"/api/plans/annual/{plan_id}/confirm").status_code == 200
    return plan_id


@pytest.fixture
def world(db_session, teacher):
    """원 둘. 교사는 가원 소속이다."""
    a, b = _center(db_session, "가원"), _center(db_session, "나원")
    user_a, user_b = (
        _member(db_session, a, "a@example.com"),
        _member(db_session, b, "b@example.com"),
    )
    class_a, class_b = _class(db_session, a), _class(db_session, b)
    teacher.center_id = a.id
    # id 만 들고 다닌다 — 라우터가 commit 하면 ORM 객체가 만료된다.
    return {
        "session": db_session,
        "a": a.id,
        "b": b.id,
        "user_a": user_a.id,
        "class_a": class_a.id,
        "class_b": class_b.id,
        "profile_a": _profile(db_session, a.id, user_a.id),
        "profile_b": _profile(db_session, b.id, user_b.id),
    }


def _create(world, month=9, **overrides):
    body = {"class_id": world["class_a"], "month": month, "profile_ref": world["profile_a"]}
    return client.post("/api/plans/monthly", json={**body, **overrides})


def _monthly_rows(session) -> list[Plan]:
    return list(session.scalars(select(Plan).where(Plan.kind == "monthly")))


def _error(response):
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


# ── 생성 · 조회 ───────────────────────────────────────────────────────────


def test_생성하면_201_이고_단건_조회가_같은_계약을_준다(world):
    session = world["session"]
    annual_id = _annual(world["class_a"])

    created = _create(world)
    assert created.status_code == 201, created.json()
    body = created.json()
    session.expunge_all()  # 메모리 객체가 아니라 DB 에서 다시 읽는다
    fetched = client.get(f"/api/plans/monthly/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    row = session.get(Plan, body["id"])
    stored = PostgresPlanRepository(
        session, center_id=world["a"], kind="monthly", plan_type=MonthlyPlan
    ).get(PlanId(row.plan_ref))
    assert (body["status"], body["revision"], row.revision) == ("DRAFT", 1, 1)
    assert (body["school_year"], body["month"], body["target_month"]) == (2026, 9, "2026-09")
    assert body["class_id"] == world["class_a"]
    assert body["generation_mode"] == "LLM_PLANNER"
    assert body["profile_ref"] == world["profile_a"]
    assert body["base_template_ref"] == {
        "template_id": FOCUS.template_id,
        "template_version": FOCUS.template_version,
    }
    assert body["parent"]["annual_plan_id"] == annual_id
    assert body["parent"]["theme"] == stored.parent_lineage.snapshot_value
    assert "audit" not in body

    # 주 · Section · 칸은 Core 가 정한 그대로다(칸 수 고정 없음).
    assert [w["week_id"] for w in body["weeks"]] == [w.week_id.value for w in stored.week_periods]
    sections = {s["section_key"]: s for s in body["sections"]}
    assert {key: s["repeat_by"] for key, s in sections.items()} == {
        "theme": "NONE",
        "week_axis": None,
        "outdoor_play": "WEEK",
        "safety_education": "WEEK",
        "focus": "WEEK",
    }
    assert sections["week_axis"]["cells"] == []
    active = [w["week_id"] for w in body["weeks"] if w["active"]]
    for key in ("outdoor_play", "safety_education", "focus"):
        assert [c["week_id"] for c in sections[key]["cells"]] == active
    assert sections["focus"]["label"] == "소주제"
    assert sections["focus"]["semantic_variant"] == "SUBTHEME"
    item_ids = [c["item_id"] for s in body["sections"] for c in s["cells"]]
    assert item_ids == [c.item_id.value for c in stored.cells]
    assert len(set(item_ids)) == len(item_ids)

    # 출처 세 축 · 생성 방식.
    theme = sections["theme"]["cells"][0]
    assert {e["source_type"] for e in theme["evidence"]} >= {"PARENT_PLAN", "THEME_REFERENCE"}
    methods = {c["generation"]["method"] for s in body["sections"] for c in s["cells"]}
    assert "RULE_LLM" in methods
    focus_sources = {e["source_type"] for c in sections["focus"]["cells"] for e in c["evidence"]}
    assert "INSTITUTION_SAMPLE" in focus_sources  # LLM 이 쓴 칸의 Grounding

    # 안전교육은 근거가 없으니 비워 두고 그렇다고 표시한다 — 충족도 위반도 말하지 않는다.
    safety = sections["safety_education"]["cells"]
    assert {(c["state"], c["value"]) for c in safety} == {("EMPTY_UNRESOLVED", "")}
    constraints = {c["code"]: c for c in body["constraints"]}
    assert constraints["STATUTORY_SAFETY_EDUCATION"]["verification"] == (
        "NOT_VERIFIED_SOURCE_REQUIRED"
    )
    assert body["verification"]["executed_rules"]
    assert [f["code"] for f in body["verification"]["findings"]] == [
        f.code for f in stored.verification_report.findings
    ]


def test_목록은_대상_달_순이고_1_2월은_다음_해다(world):
    _annual(world["class_a"])
    for month in (1, 9, 3):
        assert _create(world, month=month).status_code == 201

    items = client.get(f"/api/plans/monthly?class_id={world['class_a']}").json()["items"]
    assert [i["target_month"] for i in items] == ["2026-03", "2026-09", "2027-01"]
    assert [i["month"] for i in items] == [3, 9, 1]
    assert {i["school_year"] for i in items} == {2026}
    assert all(i["revision"] == 1 and i["profile_ref"] == world["profile_a"] for i in items)
    assert client.get("/api/plans/monthly").json()["items"] == items
    weeks = {len(client.get(f"/api/plans/monthly/{i['id']}").json()["weeks"]) for i in items}
    assert len(weeks) > 1  # 달마다 주 수가 다르다


# ── 권한 · 게이트 · Profile ───────────────────────────────────────────────


def test_다른_원은_계획안을_보지도_남의_반_Profile_을_쓰지도_못한다(world, teacher):
    _annual(world["class_a"])
    plan_id = _create(world).json()["id"]
    # 남의 원 Profile 은 없는 것과 같다 (다른 달이라 중복 검사에 걸리지 않는다).
    assert _error(_create(world, month=10, profile_ref=world["profile_b"])) == (
        404,
        "NOT_FOUND",
        ["profile_ref"],
    )

    teacher.center_id = world["b"]
    assert _error(client.get(f"/api/plans/monthly/{plan_id}")) == (404, "NOT_FOUND", ["id"])
    assert client.get("/api/plans/monthly").json() == {"items": []}
    assert _error(client.get(f"/api/plans/monthly?class_id={world['class_a']}"))[0] == 404
    assert _error(_create(world, profile_ref=world["profile_b"])) == (
        404,
        "NOT_FOUND",
        ["class_id"],
    )
    # 연간 id 를 월간으로 읽지도 못한다.
    teacher.center_id = world["a"]
    annual_id = client.get("/api/plans/annual").json()["items"][0]["id"]
    assert client.get(f"/api/plans/monthly/{annual_id}").status_code == 404


def test_연간이_없거나_확정_전이면_GATE_BLOCKED(world):
    session = world["session"]
    response = _create(world)
    assert _error(response) == (409, "GATE_BLOCKED", ["class_id"])
    assert "만들어" in response.json()["error"]["message"]

    _annual(world["class_a"], confirm=False)
    response = _create(world)
    assert _error(response) == (409, "GATE_BLOCKED", ["class_id"])
    assert "확정" in response.json()["error"]["message"]
    assert _monthly_rows(session) == []


def test_READY_가_아니거나_승인_전_Template_이면_만들지_않는다(world, monkeypatch):
    session = world["session"]
    _annual(world["class_a"])
    repo = PostgresTemplateProfileRepository(session, center_id=world["a"])
    ready = world["profile_a"]
    draft = repo.derive_draft(_ref(ready), actor_id=world["user_a"])  # READY → DRAFT
    for profile_ref in (
        {"profile_id": "tprofile_없음", "profile_version": "v1"},
        {"profile_id": ready["profile_id"], "profile_version": "v9"},
        {"profile_id": draft.profile_id, "profile_version": draft.profile_version},
    ):
        assert _error(_create(world, profile_ref=profile_ref)) == (
            404,
            "NOT_FOUND",
            ["profile_ref"],
        )
    # 실제 데이터 파일 그대로면 v0.2.1 은 승인 대기다 — READY 여도 생성 직전에 막는다.
    monkeypatch.setattr(profile_service, "TEMPLATES", JsonMonthlyTemplateRepository())
    assert _error(_create(world)) == (422, "VALIDATION_FAILED", ["profile_ref"])
    assert _monthly_rows(session) == []


def _ref(ref: dict) -> TemplateProfileRef:
    return TemplateProfileRef(ref["profile_id"], ref["profile_version"])


@pytest.mark.parametrize(
    ("override", "fields"),
    [
        ({"month": 0}, ["month"]),
        ({"month": 13}, ["month"]),
        ({"profile_ref": None}, ["profile_ref"]),
        ({"profile_ref": {"profile_id": "", "profile_version": "v1"}}, ["profile_ref.profile_id"]),
        ({"profile_ref": {"profile_id": "  ", "profile_version": "v1"}}, ["profile_ref"]),
        ({"class_id": "한"}, ["class_id"]),
    ],
)
def test_입력이_틀리면_422(world, override, fields):
    _annual(world["class_a"])
    assert _error(_create(world, **override)) == (422, "VALIDATION_FAILED", fields)


def test_없는_반은_404(world):
    assert _error(_create(world, class_id=999_999)) == (404, "NOT_FOUND", ["class_id"])


# ── 중복 · Transaction ────────────────────────────────────────────────────


def test_같은_반_같은_달은_409_이고_있던_계획안은_그대로다(world):
    _annual(world["class_a"])
    first = _create(world).json()
    assert _error(_create(world)) == (409, "ALREADY_EXISTS", ["class_id", "month"])
    world["session"].expunge_all()
    assert client.get(f"/api/plans/monthly/{first['id']}").json() == first
    assert len(_monthly_rows(world["session"])) == 1


def test_사전_조회를_지나도_DB_유일_제약이_409_로_막는다(world, monkeypatch):
    """동시 요청처럼 두 번째가 「없다」를 본 상황 — 마지막 방어선은 부분 유일 인덱스다."""
    _annual(world["class_a"])
    first = _create(world).json()
    monkeypatch.setattr(monthly_router, "_existing", lambda *args: None)
    assert _error(_create(world)) == (409, "ALREADY_EXISTS", ["class_id", "month"])
    # rollback 뒤에도 같은 session 으로 다음 요청이 된다. 있던 계획안은 그대로다.
    world["session"].expunge_all()
    assert client.get(f"/api/plans/monthly/{first['id']}").json() == first
    assert _create(world, month=10).status_code == 201


def test_다른_무결성_오류는_409_로_바꾸지_않는다(world, monkeypatch):
    _annual(world["class_a"])

    class Other:
        class diag:
            constraint_name = "fk_plans_center_id_centers"

    def broken_save(self, plan_id, plan):
        raise IntegrityError("INSERT", {}, Other())

    monkeypatch.setattr(PostgresPlanRepository, "save", broken_save)
    response = _create(world)
    # 처리하지 않은 오류는 middleware 가 평문 500 으로 바꾼다 — 409 로 숨기지 않는다.
    assert (response.status_code, response.text) == (500, "Internal Server Error")


# ── LLM real 경로 (실제 엘리스를 부르지 않는다) ──────────────────────────────


@pytest.fixture
def real_llm(monkeypatch):
    """real 모드 + 가짜 주소. 전송 함수만 바꿔 낀다 — 오류 분류는 진짜 코드를 탄다.

    `install` 을 부를 때 real 로 바꾼다 — 부모 연간은 그 전에 mock 으로 만든다.
    """
    calls = []

    def install(behaviour):
        monkeypatch.setattr(settings, "llm_mode", "real")
        monkeypatch.setattr(settings, "elice_mlapi_base_url", "https://llm.invalid/v1")
        monkeypatch.setattr(settings, "elice_mlapi_api_key", "test-only-not-a-key")

        def post_json(url, *, headers, payload, timeout):
            calls.append({"url": url, "payload": payload, "timeout": timeout})
            return behaviour()

        monkeypatch.setattr(monthly_llm, "post_json", post_json)

    return install, calls


def _raise(error):
    def behaviour():
        raise error

    return behaviour


def test_real_LLM_오류는_계약_코드로_가르고_mock_으로_대신하지_않는다(world, real_llm, monkeypatch):
    session = world["session"]
    install, calls = real_llm
    _annual(world["class_a"])
    cases = (
        (_raise(LlmBudgetExceeded("429")), (503, "LLM_BUDGET_EXCEEDED", [])),
        (_raise(LlmFailed("timeout")), (500, "GENERATION_FAILED", [])),
        # 계약을 어긴 답 — 수리 1회 뒤에도 틀리면 실패다.
        (lambda: {"choices": [{"message": {"content": "{}"}}]}, (500, "GENERATION_FAILED", [])),
        (lambda: {"unexpected": True}, (500, "GENERATION_FAILED", [])),
    )
    for behaviour, expected in cases:
        calls.clear()
        install(behaviour)
        assert _error(_create(world)) == expected
        assert 1 <= len(calls) <= 2  # 수리는 최대 1회
        assert _monthly_rows(session) == []  # 부분 결과가 남지 않는다

    # 요청은 ADR-023 그대로다: Luna-6 · strict · temperature 없음 · 30초.
    sent = calls[0]
    assert sent["url"] == "https://llm.invalid/v1/chat/completions"
    assert sent["payload"]["model"] == "openai/gpt-6-luna"
    assert sent["payload"]["response_format"]["json_schema"]["strict"] is True
    assert "temperature" not in sent["payload"]
    assert sent["timeout"] == 30.0

    # 설정이 없으면 부르기 전에 멈춘다.
    calls.clear()
    monkeypatch.setattr(settings, "elice_mlapi_base_url", None)
    assert _error(_create(world)) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert calls == []

    # 실패 뒤에도 같은 반 · 같은 달을 다시 만들 수 있다 — 실패가 아무것도 남기지 않았다.
    monkeypatch.setattr(settings, "llm_mode", "mock")
    assert _create(world).status_code == 201


def test_승인_참조자료를_못_읽으면_DEPENDENCY_UNAVAILABLE(world, monkeypatch):
    _annual(world["class_a"])
    monkeypatch.setattr(
        monthly_router,
        "ACTIVITY_CATALOG",
        ActivityCatalogSelector("ssuksak.outdoor-activity-reference", "activity-reference-v9.9.9"),
    )
    assert _error(_create(world)) == (503, "DEPENDENCY_UNAVAILABLE", [])
    assert _monthly_rows(world["session"]) == []


# ── 양식 설정 조회 ─────────────────────────────────────────────────────────


def test_원의_READY_목록만_준다(world, teacher):
    session = world["session"]
    second = _profile(session, world["a"], world["user_a"], template=PLAIN)
    repo = PostgresTemplateProfileRepository(session, center_id=world["a"])
    repo.derive_draft(_ref(second), actor_id=world["user_a"])  # DRAFT 는 목록에 없다

    items = client.get(f"/api/centers/{world['a']}/template-profiles").json()["items"]
    assert [i["profile_ref"] for i in items] == [world["profile_a"], second]
    assert {i["status"] for i in items} == {"READY"}
    assert items[0]["base_template_ref"]["template_version"] == FOCUS.template_version
    assert items[0]["selected_optional_keys"] == ["focus"]
    assert {s["section_key"]: s["label"] for s in items[0]["sections"]} == LABELS
    assert "name" not in items[0]  # Core 에 없는 표시 이름을 지어내지 않는다

    assert _error(client.get(f"/api/centers/{world['b']}/template-profiles")) == (
        404,
        "NOT_FOUND",
        ["center_id"],
    )


def test_반에_적용되는_Profile_은_override_다음_원_기본이고_못_쓰면_내려가지_않는다(world):
    session = world["session"]
    class_a, user_id = world["class_a"], world["user_a"]
    repo = PostgresTemplateProfileRepository(session, center_id=world["a"])
    url = f"/api/classes/{class_a}/template-profile"

    assert client.get(url).json() == {
        "source": "SELECTION_REQUIRED",
        "profile_ref": None,
        "reason": "NO_POINTER",
    }
    base = _ref(world["profile_a"])
    special = _ref(_profile(session, world["a"], world["user_a"], template=PLAIN))
    repo.set_default(base, expected=None, actor_id=user_id)
    assert client.get(url).json()["source"] == "INSTITUTION_DEFAULT"
    repo.set_override(class_a, special, expected=None, actor_id=user_id)
    resolved = client.get(url).json()
    assert (resolved["source"], resolved["profile_ref"]["profile_id"]) == (
        "CLASSROOM_OVERRIDE",
        special.profile_id,
    )
    # R3: override 대상을 못 쓰게 되면 원 기본으로 내려가지 않고 「선택 필요」다.
    session.execute(
        update(TemplateProfileVersion)
        .where(TemplateProfileVersion.profile_id == special.profile_id)
        .values(status="ARCHIVED")
    )
    assert client.get(url).json() == {
        "source": "SELECTION_REQUIRED",
        "profile_ref": None,
        "reason": "CLASSROOM_OVERRIDE_NOT_READY",
    }
    assert _error(client.get(f"/api/classes/{world['class_b']}/template-profile"))[0] == 404


# ── 실제 동시 요청 · LLM 대기 중 DB 점유 ────────────────────────────────────


def test_동시에_같은_달을_만들면_하나만_남고_LLM_대기_중_transaction_을_잡지_않는다(
    _schema, teacher, monkeypatch
):
    """서로 다른 연결 두 개. 두 요청이 모두 「없다」를 보고 LLM 단계에서 서로를 기다린다."""
    with Session(engine) as session:
        center = _center(session, "월간 API 동시성 테스트원")
        member = _member(session, center, "monthly-api-race@example.com")
        klass = _class(session, center)
        profile = _profile(session, center.id, member.id)
        session.commit()
        center_id, member_id, class_id = center.id, member.id, klass.id
    teacher.center_id = center_id
    idle_in_transaction = []

    def measure():
        """두 요청이 모두 LLM 단계에 있을 때 한 번 센다. 세는 연결은 transaction 을 열지 않는다."""
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as watcher:
            idle_in_transaction.append(
                watcher.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = "
                        "current_database() AND state LIKE 'idle in transaction%'"
                    )
                )
            )

    barrier = Barrier(2, action=measure)

    class WaitingLlm(RequestAwareMonthlyLlm):
        def generate_monthly(self, request):
            barrier.wait(timeout=20)  # 둘 다 A 단계를 지나 LLM 을 기다린다
            return super().generate_monthly(request)

    monkeypatch.setattr(monthly_router, "monthly_llm_provider", WaitingLlm)
    body = {"class_id": class_id, "month": 9, "profile_ref": profile}
    try:
        _annual(class_id)
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(lambda _: client.post("/api/plans/monthly", json=body), range(2))
            )
        assert sorted(r.status_code for r in responses) == [201, 409]
        assert idle_in_transaction == [0]  # LLM 을 기다리는 동안 열린 transaction 이 없다
        loser = next(r for r in responses if r.status_code == 409)
        assert loser.json()["error"]["code"] == "ALREADY_EXISTS"
        winner = next(r for r in responses if r.status_code == 201).json()
        # 새 연결 · 새 session 으로 다시 읽어도 같다.
        assert client.get(f"/api/plans/monthly/{winner['id']}").json() == winner
        with Session(engine) as session:
            rows = session.scalars(
                select(Plan).where(Plan.center_id == center_id, Plan.kind == "monthly")
            ).all()
            assert [row.id for row in rows] == [winner["id"]]
    finally:
        with Session(engine) as session:
            for model in (Plan, TemplateProfileVersion):
                session.execute(delete(model).where(model.center_id == center_id))
            session.execute(delete(Class).where(Class.center_id == center_id))
            session.execute(delete(User).where(User.id == member_id))
            session.execute(delete(Center).where(Center.id == center_id))
            session.commit()
