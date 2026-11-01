"""v1 월간 응답의 안전 후보 세 목록 (api-spec §9-1) — safety_candidates · safety_weeks · notices.

계획은 실제 `POST /api/plans/monthly` 로 만든다 — 기본이 후보 모드다(ADR-052). 예전 자동 배치
계획이 필요한 테스트만 `legacy_mode` 로 생성 명령을 바꾼다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

from datetime import UTC, datetime

import pytest
from ssuksak.planning import ActorId, MonthlyPlan, SafetyPlacementSelector
from ssuksak.planning.domain.safety_placement import STATUTORY_SHORT_LABELS
from test_monthly_lifecycle_api import (  # noqa: F401
    _approved,
    _edit,
    _get,
    _monthly,
    _seed,
    _stored,
)

from app.features.plans import monthly_router
from app.features.plans.repository import PostgresPlanRepository


@pytest.fixture
def seed(db_session, teacher):
    made = _seed(db_session, "가원", "a@example.com")
    teacher.center_id = made["center"]
    return made


@pytest.fixture
def legacy_mode(monkeypatch):
    """2026-10-31 이전의 자동 배치 계획을 만든다. 둘은 배타라 (monthly_dto) 후보 선택자를 끈다."""
    original = monthly_router.GenerateMonthlyPlanCommand
    placement = SafetyPlacementSelector("ssuksak-safety-placement-v2", supplemental=False)

    def command(**fields):
        return original(**{**fields, "safety_placement": placement, "safety_candidates": None})

    monkeypatch.setattr(monthly_router, "GenerateMonthlyPlanCommand", command)


def _active_weeks(plan: dict) -> list[str]:
    return [w["week_id"] for w in plan["weeks"] if w["active"]]


def test_기존_계획은_세_목록이_비어_있다(seed, legacy_mode):
    plan = _monthly(seed)

    assert (plan["safety_candidates"], plan["safety_weeks"], plan["notices"]) == ([], [], [])
    got = _get(plan["id"])
    assert (got["safety_candidates"], got["safety_weeks"], got["notices"]) == ([], [], [])


def test_후보_모드로_만들면_후보_8개와_주마다_빈_배치와_안내가_온다(seed):
    plan = _monthly(seed)

    candidates = plan["safety_candidates"]
    assert [c["kind"] for c in candidates] == ["STATUTORY"] * 6 + ["SUPPLEMENTAL"] * 2
    for c in candidates:
        statutory = c["kind"] == "STATUTORY"
        assert (c["category_id"] is not None, c["topic_group"] is None) == (statutory, statutory)
        assert c["cell"]["week_id"] is None
    weeks = _active_weeks(plan)
    assert plan["safety_weeks"] == [
        {"week_id": w, "candidate_item_id": None, "display_value": ""} for w in weeks
    ]
    assert plan["notices"] == [{"code": "SAFETY_UNPLACED", "week_id": w} for w in weeks]


def test_저장했다_읽어도_세_목록과_sections_가_생성_응답과_같다(seed):
    plan = _monthly(seed)
    got = _get(plan["id"])

    for key in ("safety_candidates", "safety_weeks", "notices", "sections"):
        assert got[key] == plan[key]


def _place(session, seed, plan: dict, week_id: str, item_id: str) -> None:
    """교사의 배치 화면은 아직 없다 — Core 로 배치하고 저장소로 저장한다."""
    _, domain = _stored(session, seed["center"], plan["id"])
    placed = domain.place_safety(
        next(s.week_id for s in domain.safety_weeks if s.week_id.value == week_id),
        next(c.cell.item_id for c in domain.safety_candidates if c.cell.item_id.value == item_id),
        actor_id=ActorId(f"user_{seed['user']}"),
        occurred_at=datetime.now(UTC),
    )
    repo = PostgresPlanRepository(
        session, center_id=seed["center"], kind="monthly", plan_type=MonthlyPlan
    )
    assert repo.update_if_revision(domain.plan_id, placed, expected_revision=plan["revision"])


def test_후보를_배치하면_그_주에_표시값이_붙고_안내가_빠진다(db_session, seed):
    plan = _monthly(seed)
    statutory, supplemental = plan["safety_candidates"][0], plan["safety_candidates"][-1]
    week1, week2 = _active_weeks(plan)[:2]
    _place(db_session, seed, plan, week1, statutory["cell"]["item_id"])
    _place(
        db_session,
        seed,
        {**plan, "revision": plan["revision"] + 1},
        week2,
        supplemental["cell"]["item_id"],
    )

    got = _get(plan["id"])
    by_week = {w["week_id"]: w for w in got["safety_weeks"]}
    label = STATUTORY_SHORT_LABELS[statutory["category_id"]]
    assert by_week[week1]["candidate_item_id"] == statutory["cell"]["item_id"]
    assert by_week[week1]["display_value"] == f"[{label}] - {statutory['cell']['value']}"
    assert by_week[week2]["display_value"] == f"[생활안전] - {supplemental['cell']['value']}"
    assert {n["week_id"] for n in got["notices"]}.isdisjoint({week1, week2})


def test_배치한_후보_문장을_비우면_SAFETY_BLANK_이고_표시값은_빈_문자열이다(db_session, seed):
    plan = _monthly(seed)
    candidate = plan["safety_candidates"][0]["cell"]
    week = _active_weeks(plan)[0]
    _place(db_session, seed, plan, week, candidate["item_id"])

    edited = _edit(plan["id"], candidate["item_id"], "", plan["revision"] + 1)

    assert edited.status_code == 200, edited.json()
    got = _get(plan["id"])
    assert {"code": "SAFETY_BLANK", "week_id": week} in got["notices"]
    assert next(w for w in got["safety_weeks"] if w["week_id"] == week)["display_value"] == ""
