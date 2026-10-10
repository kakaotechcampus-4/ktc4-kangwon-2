"""TemplateProfile 관리 API (BE-1). 진짜 Postgres 위에서 HTTP 로 부른다.

계약은 docs/api-spec.md §9-4.

기반 Template v0.1.1 · v0.2.1 은 **사람 승인 대기**다. 승인된 경로는 OD-N11 (A) — 테스트 안에서만
`replace(template, runtime_active=True)` — 로 본다(`service.TEMPLATES` 를 바꿔 낀다). 데이터 파일과
운영 코드는 그대로이고, 승인 대기 상태로 부르면 막혀야 한다. **실제 Luna-6 는 부르지 않는다**
(월간 생성은 기본 mock provider).
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from ssuksak.adapters.monthly_reference_repositories import (
    DEFAULT_TEMPLATE_PATH,
    FOCUS_TEMPLATE_PATH,
    JsonMonthlyTemplateRepository,
)
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef

from app.db import engine
from app.features.auth.models import User
from app.features.centers.models import Center, Class
from app.features.template_profiles import service as profile_service
from app.features.template_profiles.models import (
    TemplateProfileDefault,
    TemplateProfileOverride,
    TemplateProfileVersion,
)
from app.features.template_profiles.repository import PostgresTemplateProfileRepository
from app.main import app

client = TestClient(app)

PLAIN = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.1.1")
FOCUS = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.2.1")
# 보이는 칸은 표시 이름을 직접 받아야 한다(Core). 고른 칸의 이름만 보낸다.
LABELS = {
    "theme": "생활주제",
    "week_axis": "주",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
    "focus": "소주제",
    "goals": "목표",
    "basic_habit": "기본생활",
}


def _labels(*optional) -> dict:
    keys = ("theme", "week_axis", "outdoor_play", "safety_education", *optional)
    return {key: LABELS[key] for key in keys}


class ApprovedTemplates:
    """OD-N11 (A): 실제 파일을 읽어 테스트 안에서만 승인 상태로 바꾼다."""

    def __init__(self):
        self._real = JsonMonthlyTemplateRepository()

    def get_template(self, template_id, template_version):
        template = self._real.get_template(template_id, template_version)
        return None if template is None else replace(template, runtime_active=True)


@pytest.fixture
def approved(monkeypatch):
    monkeypatch.setattr(profile_service, "TEMPLATES", ApprovedTemplates())


def _center(session, name) -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _member(session, center, email) -> User:
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
        center_id=center.id, name=name, school_year=2026, age_min=3, age_max=4, teacher_name="선생"
    )
    session.add(klass)
    session.flush()
    return klass


def _ready(repo, user_id, template=FOCUS):
    optional = ("focus",) if template == FOCUS else ()
    return repo.start_from_reference(
        ApprovedTemplates(),
        template,
        selected_optional_keys=optional,
        display_labels=LABELS,
        focus_variant=SemanticVariant.SUBTHEME if optional else None,
        actor_id=user_id,
    )


def _json(ref) -> dict:
    return {"profile_id": ref.profile_id, "profile_version": ref.profile_version}


@pytest.fixture
def world(db_session, teacher):
    """원 둘. 교사는 가원 소속의 진짜 계정이다(포인터 `changed_by` 가 FK 다)."""
    a, b = _center(db_session, "가원"), _center(db_session, "나원")
    user_a, user_b = (
        _member(db_session, a, "a@example.com"),
        _member(db_session, b, "b@example.com"),
    )
    class_a, class_b = _class(db_session, a), _class(db_session, b)
    repo_a = PostgresTemplateProfileRepository(db_session, center_id=a.id)
    p1, p2 = _ready(repo_a, user_a.id), _ready(repo_a, user_a.id, PLAIN)
    archived = _ready(repo_a, user_a.id)
    repo_a.archive(archived)
    draft = repo_a.derive_draft(p1, actor_id=user_a.id)
    pb = _ready(PostgresTemplateProfileRepository(db_session, center_id=b.id), user_b.id)
    teacher.id, teacher.center_id = user_a.id, a.id
    # id 만 들고 다닌다 — 라우터가 commit 하면 ORM 객체가 만료된다.
    return {
        "session": db_session,
        "a": a.id,
        "b": b.id,
        "user_a": user_a.id,
        "class_a": class_a.id,
        "class_b": class_b.id,
        "p1": _json(p1),
        "p2": _json(p2),
        "archived": _json(archived),
        "draft": _json(draft),
        "pb": _json(pb),
    }


def _error(response):
    body = response.json()["error"]
    return response.status_code, body["code"], body["fields"]


def _versions(session, center_id) -> int:
    return session.scalar(select(func.count()).where(TemplateProfileVersion.center_id == center_id))


def _start(world, **overrides):
    body = {
        "base_template_ref": {
            "template_id": FOCUS.template_id,
            "template_version": FOCUS.template_version,
        },
        "selected_optional_keys": ["focus", "goals"],
        "display_labels": _labels("focus", "goals"),
        "focus_variant": "SUBTHEME",
    }
    return client.post(f"/api/centers/{world['a']}/template-profiles", json={**body, **overrides})


def _default(world, profile_ref, expected, center=None):
    return client.put(
        f"/api/centers/{center or world['a']}/template-profile-default",
        json={"profile_ref": profile_ref, "expected_profile_ref": expected},
    )


def _override(world, profile_ref, expected, class_id=None):
    return client.put(
        f"/api/classes/{class_id or world['class_a']}/template-profile-override",
        json={"profile_ref": profile_ref, "expected_profile_ref": expected},
    )


def _resolution(world, class_id=None) -> dict:
    response = client.get(f"/api/classes/{class_id or world['class_a']}/template-profile")
    assert response.status_code == 200
    return response.json()


# ── A. 기반 Template 목록 ──────────────────────────────────────────────────


def _template_files() -> list[str]:
    return [
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (DEFAULT_TEMPLATE_PATH, FOCUS_TEMPLATE_PATH)
    ]


def test_기반_Template_목록은_실제_데이터의_승인_대기를_그대로_보인다(world):
    before = _template_files()
    response = client.get("/api/monthly-templates")
    assert response.status_code == 200
    items = response.json()["items"]
    real = JsonMonthlyTemplateRepository()
    assert [
        (i["template_ref"]["template_id"], i["template_ref"]["template_version"]) for i in items
    ] == [(ref.template_id, ref.template_version) for ref in profile_service.MONTHLY_TEMPLATE_REFS]
    for item in items:
        template = real.get_template(**item["template_ref"])
        assert item["approved"] is False is template.is_active  # 승인 대기 — 바꾸지 않는다
        assert len(item["sections"]) == len(template.sections)
        selection = {s["section_key"]: s["selection"] for s in item["sections"]}
        assert {k for k, v in selection.items() if v == "REQUIRED"} == {
            "theme",
            "week_axis",
            "outdoor_play",
            "safety_education",
        }
        assert {k for k, v in selection.items() if v == "OPTIONAL"} == {
            "focus",
            "goals",
            "basic_habit",
        }
        assert {k for k, v in selection.items() if v == "INSTITUTION_INPUT"} == {
            "event_schedule",
            "drill",
        }
        assert {k for k, v in selection.items() if v == "NOT_SUPPORTED"} == {
            "emergency_response",
            "indoor_alternative",
            "special_program",
        }
        assert "habits" not in selection  # Template 의 habits 는 Profile 이름으로 보인다
        week = next(s for s in item["sections"] if s["section_key"] == "week_axis")
        assert (week["role"], week["repeat_by"]) == ("AXIS", None)
        assert item["focus_variants"] == ["SUBTHEME", "EXPECTED_PLAY", "WEEKLY_THEME"]
    assert _template_files() == before


def test_기반_Template_목록은_승인_객체를_바꿔_끼우면_승인으로_보인다(world, approved):
    items = client.get("/api/monthly-templates").json()["items"]
    assert {item["approved"] for item in items} == {True}


def test_로그인하지_않으면_기반_Template_목록도_401(db_session):
    response = client.get("/api/monthly-templates")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


# ── B. Reference 기반 시작 ─────────────────────────────────────────────────


def test_승인_대기_Template_으로_시작하면_409_GATE_BLOCKED_이고_아무것도_남지_않는다(world):
    before = _versions(world["session"], world["a"])
    assert _error(_start(world)) == (409, "GATE_BLOCKED", ["base_template_ref"])
    assert _versions(world["session"], world["a"]) == before


def test_승인된_Template_으로_시작하면_READY_v1_이_생기고_기본은_그대로다(world, approved):
    session = world["session"]
    response = _start(world)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["status"], body["profile_ref"]["profile_version"]) == ("READY", "v1")
    assert body["base_template_ref"] == {
        "template_id": FOCUS.template_id,
        "template_version": FOCUS.template_version,
    }
    assert sorted(body["selected_optional_keys"]) == ["focus", "goals"]
    labels = {s["section_key"]: s["label"] for s in body["sections"]}
    assert (labels["focus"], labels["theme"]) == ("소주제", "생활주제")
    assert {"event_schedule", "drill"}.isdisjoint(labels)

    session.expunge_all()
    row = session.scalar(
        select(TemplateProfileVersion).where(
            TemplateProfileVersion.profile_id == body["profile_ref"]["profile_id"]
        )
    )
    assert (row.status, row.center_id, row.created_by) == ("READY", world["a"], world["user_a"])
    assert row.body["classroom_ref"] is None
    assert row.body["institution_ref"] == str(world["a"])
    # 만들기만 한다 — 원 기본 · 해석은 그대로다.
    assert (
        client.get(f"/api/centers/{world['a']}/template-profile-default").json()["profile_ref"]
        is None
    )
    assert _resolution(world)["source"] == "SELECTION_REQUIRED"
    listed = client.get(f"/api/centers/{world['a']}/template-profiles").json()["items"]
    assert body in listed


def test_같은_시작_요청을_두_번_보내면_Profile_이_두_개_생긴다(world, approved):
    first, second = _start(world), _start(world)
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["profile_ref"]["profile_id"] != second.json()["profile_ref"]["profile_id"]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"selected_optional_keys": ["focus", "unknown"]}, "selected_optional_keys"),
        ({"selected_optional_keys": ["focus", "theme"]}, "selected_optional_keys"),
        ({"selected_optional_keys": ["focus", "focus"]}, "selected_optional_keys"),
        ({"selected_optional_keys": ["focus", "habits"]}, "selected_optional_keys"),
        ({"selected_optional_keys": ["focus", "event_schedule"]}, "selected_optional_keys"),
        ({"selected_optional_keys": ["focus", "drill"]}, "selected_optional_keys"),
        ({"display_labels": {"event_schedule": "행사"}}, "display_labels.event_schedule"),
        ({"display_labels": {"basic_habit": "기본생활"}}, "display_labels.basic_habit"),
        ({"display_labels": {**_labels("focus", "goals"), "focus": "   "}}, "display_labels.focus"),
        ({"display_labels": _labels("focus")}, "display_labels.goals"),
        ({"focus_variant": None}, "focus_variant"),
        ({"focus_variant": "NEUTRAL"}, "focus_variant"),
        ({"focus_variant": "OTHER"}, "focus_variant"),
        (
            {
                "selected_optional_keys": ["goals"],
                "display_labels": _labels("goals"),
                "focus_variant": "SUBTHEME",
            },
            "focus_variant",
        ),
        (
            {"base_template_ref": {"template_id": "", "template_version": "x"}},
            "base_template_ref.template_id",
        ),
    ],
)
def test_잘못된_시작_요청은_422_이고_아무것도_남지_않는다(world, approved, overrides, field):
    before = _versions(world["session"], world["a"])
    assert _error(_start(world, **overrides)) == (422, "VALIDATION_FAILED", [field])
    assert _versions(world["session"], world["a"]) == before


def test_없는_Template_과_남의_원은_404(world, approved):
    missing = {"template_id": FOCUS.template_id, "template_version": "monthly-template-a-v9.9.9"}
    assert _error(_start(world, base_template_ref=missing)) == (
        404,
        "NOT_FOUND",
        ["base_template_ref"],
    )
    other = client.post(
        f"/api/centers/{world['b']}/template-profiles",
        json={
            "base_template_ref": {
                "template_id": PLAIN.template_id,
                "template_version": PLAIN.template_version,
            }
        },
    )
    assert _error(other) == (404, "NOT_FOUND", ["center_id"])
    assert _versions(world["session"], world["b"]) == 1


# ── C. 원 기본 ─────────────────────────────────────────────────────────────


def test_원_기본은_본_값이_맞을_때만_바뀌고_해제된다(world):
    url = f"/api/centers/{world['a']}/template-profile-default"
    assert client.get(url).json() == {"profile_ref": None, "changed_by": None, "changed_at": None}

    first = _default(world, world["p1"], None)
    assert first.status_code == 200, first.json()
    assert first.json()["profile_ref"] == world["p1"]
    assert first.json()["changed_by"] == world["user_a"]
    assert first.json()["changed_at"] is not None
    assert client.get(url).json() == first.json()
    assert _resolution(world) == {
        "source": "INSTITUTION_DEFAULT",
        "profile_ref": world["p1"],
        "reason": None,
    }

    # 「기본 없음」을 본 오래된 화면은 덮어쓰지 못한다.
    assert _error(_default(world, world["p2"], None)) == (
        409,
        "STALE_WRITE",
        ["expected_profile_ref"],
    )
    assert client.get(url).json()["profile_ref"] == world["p1"]

    moved = _default(world, world["p2"], world["p1"])
    assert moved.json()["profile_ref"] == world["p2"]
    assert _resolution(world)["profile_ref"] == world["p2"]

    assert _error(_default(world, None, world["p1"])) == (
        409,
        "STALE_WRITE",
        ["expected_profile_ref"],
    )
    assert _error(_default(world, None, None)) == (
        422,
        "VALIDATION_FAILED",
        ["expected_profile_ref"],
    )
    cleared = _default(world, None, world["p2"])
    assert cleared.json() == {"profile_ref": None, "changed_by": None, "changed_at": None}
    assert client.get(url).json()["profile_ref"] is None
    assert _resolution(world) == {
        "source": "SELECTION_REQUIRED",
        "profile_ref": None,
        "reason": "NO_POINTER",
    }


@pytest.mark.parametrize("target", ["pb", "draft", "archived"])
def test_원_기본은_내_원의_READY_만_가리킨다(world, target):
    assert _error(_default(world, world[target], None)) == (404, "NOT_FOUND", ["profile_ref"])
    session = world["session"]
    assert session.scalar(select(TemplateProfileDefault).filter_by(center_id=world["a"])) is None


def test_원_기본_입력_모양과_남의_원(world):
    url = f"/api/centers/{world['a']}/template-profile-default"
    missing_key = client.put(url, json={"profile_ref": world["p1"]})
    assert _error(missing_key) == (422, "VALIDATION_FAILED", ["expected_profile_ref"])
    other = f"/api/centers/{world['b']}/template-profile-default"
    assert _error(client.get(other)) == (404, "NOT_FOUND", ["center_id"])
    assert _error(_default(world, world["pb"], None, center=world["b"])) == (
        404,
        "NOT_FOUND",
        ["center_id"],
    )


# ── D. 반 override ─────────────────────────────────────────────────────────


def test_반_override_는_원_기본보다_먼저고_해제하면_원_기본으로_돌아간다(world):
    url = f"/api/classes/{world['class_a']}/template-profile-override"
    assert client.get(url).json() == {"profile_ref": None, "changed_by": None, "changed_at": None}
    _default(world, world["p1"], None)

    set_ = _override(world, world["p2"], None)
    assert set_.status_code == 200, set_.json()
    assert (set_.json()["profile_ref"], set_.json()["changed_by"]) == (world["p2"], world["user_a"])
    assert client.get(url).json() == set_.json()
    assert _resolution(world) == {
        "source": "CLASSROOM_OVERRIDE",
        "profile_ref": world["p2"],
        "reason": None,
    }

    assert _error(_override(world, world["p1"], None)) == (
        409,
        "STALE_WRITE",
        ["expected_profile_ref"],
    )
    assert _error(_override(world, None, world["p1"])) == (
        409,
        "STALE_WRITE",
        ["expected_profile_ref"],
    )
    assert _override(world, None, world["p2"]).json()["profile_ref"] is None
    assert _resolution(world) == {
        "source": "INSTITUTION_DEFAULT",
        "profile_ref": world["p1"],
        "reason": None,
    }


def test_반_override_도_내_원의_반과_READY_만(world):
    for target in ("pb", "draft", "archived"):
        assert _error(_override(world, world[target], None)) == (404, "NOT_FOUND", ["profile_ref"])
    other = f"/api/classes/{world['class_b']}/template-profile-override"
    assert _error(client.get(other)) == (404, "NOT_FOUND", ["class_id"])
    assert _error(_override(world, world["p1"], None, class_id=world["class_b"])) == (
        404,
        "NOT_FOUND",
        ["class_id"],
    )
    session = world["session"]
    assert (
        session.scalar(
            select(func.count()).where(
                TemplateProfileOverride.center_id.in_([world["a"], world["b"]])
            )
        )
        == 0
    )


# ── G. 연간 → 월간 연결 ────────────────────────────────────────────────────


def test_관리_API_로_건_Profile_로_확정된_연간_뒤에만_월간을_만든다(world, approved):
    created = _start(world, selected_optional_keys=["focus"], display_labels=_labels("focus"))
    ref = created.json()["profile_ref"]
    _default(world, ref, None)
    resolved = _resolution(world)
    assert resolved == {"source": "INSTITUTION_DEFAULT", "profile_ref": ref, "reason": None}

    annual = client.post("/api/plans/annual", json={"class_id": world["class_a"], "form_id": None})
    assert annual.status_code == 201
    body = {"class_id": world["class_a"], "month": 9, "profile_ref": resolved["profile_ref"]}
    assert _error(client.post("/api/plans/monthly", json=body)) == (
        409,
        "GATE_BLOCKED",
        ["class_id"],
    )

    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200
    monthly = client.post("/api/plans/monthly", json=body)
    assert monthly.status_code == 201, monthly.json()
    assert monthly.json()["profile_ref"] == ref
    assert monthly.json()["base_template_ref"] == created.json()["base_template_ref"]

    # 반 override 를 걸면 다음 달은 그 Profile 을 쓴다. 이미 만든 계획안은 그대로다.
    _override(world, world["p1"], None)
    next_ref = _resolution(world)["profile_ref"]
    october = client.post("/api/plans/monthly", json={**body, "month": 10, "profile_ref": next_ref})
    assert october.status_code == 201, october.json()
    assert october.json()["profile_ref"] == world["p1"]
    assert client.get(f"/api/plans/monthly/{monthly.json()['id']}").json()["profile_ref"] == ref


# ── E. 실제 동시 요청 (서로 다른 연결) ───────────────────────────────────────


@pytest.fixture
def live(_schema, teacher, monkeypatch):
    """커밋된 원 · 계정 · 반 · READY 셋. 요청마다 진짜 session 을 쓴다.

    두 요청이 CAS 문장 바로 앞에서 서로를 기다린다 — 둘 다 같은 `expected` 를 본 상태다.
    """
    with Session(engine) as session:
        center = _center(session, "BE-1 동시성 테스트원")
        user = _member(session, center, "be1-race@example.com")
        klass = _class(session, center)
        repo = PostgresTemplateProfileRepository(session, center_id=center.id)
        refs = [_json(_ready(repo, user.id)) for _ in range(3)]
        session.commit()
        seed = {"center": center.id, "user": user.id, "class": klass.id, "refs": refs}
    teacher.id, teacher.center_id = seed["user"], seed["center"]
    barrier = Barrier(2)
    raced = []
    original = PostgresTemplateProfileRepository._require_one_changed

    def racing(self, statement):
        raced.append(barrier.wait(timeout=20))
        return original(self, statement)

    try:
        yield {
            **seed,
            "racing": lambda: monkeypatch.setattr(
                PostgresTemplateProfileRepository, "_require_one_changed", racing
            ),
            "raced": raced,
        }
    finally:
        with Session(engine) as session:
            session.execute(
                delete(TemplateProfileOverride).where(
                    TemplateProfileOverride.class_id == seed["class"]
                )
            )
            for model in (TemplateProfileDefault, TemplateProfileVersion):
                session.execute(delete(model).where(model.center_id == seed["center"]))
            session.execute(delete(Class).where(Class.id == seed["class"]))
            session.execute(delete(User).where(User.id == seed["user"]))
            session.execute(delete(Center).where(Center.id == seed["center"]))
            session.commit()


def _together(*calls):
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(call) for call in calls]
        return [future.result(timeout=60) for future in futures]


def _outcome(responses) -> list[tuple]:
    return sorted((r.status_code, r.json().get("error", {}).get("code")) for r in responses)


def test_같은_expected_로_원_기본을_동시에_바꾸면_하나만_성공한다(live):
    url = f"/api/centers/{live['center']}/template-profile-default"
    first, second, third = live["refs"]
    assert (
        client.put(url, json={"profile_ref": first, "expected_profile_ref": None}).status_code
        == 200
    )
    live["racing"]()

    responses = _together(
        lambda: client.put(url, json={"profile_ref": second, "expected_profile_ref": first}),
        lambda: client.put(url, json={"profile_ref": third, "expected_profile_ref": first}),
    )
    assert sorted(live["raced"]) == [0, 1]  # 실제로 겹쳤다
    assert _outcome(responses) == [(200, None), (409, "STALE_WRITE")]
    winner = next(r.json()["profile_ref"] for r in responses if r.status_code == 200)
    with Session(engine) as session:
        rows = session.scalars(
            select(TemplateProfileDefault).filter_by(center_id=live["center"])
        ).all()
    assert [{"profile_id": r.profile_id, "profile_version": r.profile_version} for r in rows] == [
        winner
    ]


def test_같은_expected_로_반_override_를_동시에_걸면_하나만_성공한다(live):
    url = f"/api/classes/{live['class']}/template-profile-override"
    first, second, _ = live["refs"]
    live["racing"]()

    responses = _together(
        lambda: client.put(url, json={"profile_ref": first, "expected_profile_ref": None}),
        lambda: client.put(url, json={"profile_ref": second, "expected_profile_ref": None}),
    )
    assert sorted(live["raced"]) == [0, 1]
    assert _outcome(responses) == [(200, None), (409, "STALE_WRITE")]
    winner = next(r.json()["profile_ref"] for r in responses if r.status_code == 200)
    with Session(engine) as session:
        rows = session.scalars(
            select(TemplateProfileOverride).filter_by(class_id=live["class"])
        ).all()
    assert [{"profile_id": r.profile_id, "profile_version": r.profile_version} for r in rows] == [
        winner
    ]
    assert rows[0].changed_by == live["user"]
