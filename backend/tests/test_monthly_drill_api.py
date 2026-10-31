"""v1 월간 훈련(소방대피 · 재난대비) 후보 API (api-spec §9-1 · §9-3 · §9-5).

서버는 아직 v0.2.3 · drill 을 고를 수 있게 열지 않았다(MONTHLY_TEMPLATE_REFS · SELECTABLE_KEYS).
생성 게이트는 그 둘을 보지 않으므로, 테스트는 v0.2.3 + drill 을 고른 READY Profile 을 저장소로
직접 만들고 실제 `POST /api/plans/monthly` 를 거친다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

import pytest
from ssuksak.planning import MonthlyApplicationError
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef
from test_monthly_lifecycle_api import (  # noqa: F401
    LABELS,
    ApprovedTemplates,
    _approved,
    _confirm,
    _edit,
    _error,
    _get,
    _seed,
    client,
)
from test_monthly_plans_api import _exported_table
from test_monthly_safety_read_api import seed as plain_seed  # noqa: F401

from app.features.plans import monthly_router
from app.features.template_profiles.repository import PostgresTemplateProfileRepository

DRILL = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.2.3")


@pytest.fixture
def seed(db_session, teacher):
    """v0.2.3 에 소주제 · 훈련 칸을 고른 READY Profile 이 있는 원 · 반."""
    made = _seed(db_session, "가원", "a@example.com")
    teacher.center_id = made["center"]
    ref = PostgresTemplateProfileRepository(
        db_session, center_id=made["center"]
    ).start_from_reference(
        ApprovedTemplates(),
        DRILL,
        selected_optional_keys=("focus", "drill"),
        display_labels={**LABELS, "drill": "소방대피/재난대비"},
        focus_variant=SemanticVariant.SUBTHEME,
        actor_id=made["user"],
    )
    made["drill_profile"] = {"profile_id": ref.profile_id, "profile_version": ref.profile_version}
    return made


def _annual_confirmed(seed) -> None:
    annual = client.post(
        "/api/plans/annual",
        json={"format": "MONTHLY_THEME", "class_id": seed["class"], "form_id": None},
    )
    assert annual.status_code == 201, annual.json()
    assert client.post(f"/api/plans/annual/{annual.json()['id']}/confirm").status_code == 200


def _create(seed, month=9, profile="drill_profile"):
    return client.post(
        "/api/plans/monthly",
        json={"class_id": seed["class"], "month": month, "profile_ref": seed[profile]},
    )


@pytest.fixture
def plan(seed) -> dict:
    _annual_confirmed(seed)
    created = _create(seed)
    assert created.status_code == 201, created.json()
    return created.json()


def _drill_cell(plan: dict) -> dict:
    section = next(s for s in plan["sections"] if s["section_key"] == "drill")
    assert len(section["cells"]) == 1
    return section["cells"][0]


def _copy(plan_id, item_id, revision):
    return client.post(
        f"/api/plans/monthly/{plan_id}/drill-candidates/{item_id}/copy",
        json={"expected_revision": revision},
    )


def _audit(plan_id, item_id=None) -> list[dict]:
    params = {} if item_id is None else {"item_id": item_id}
    response = client.get(f"/api/plans/monthly/{plan_id}/audit", params=params)
    assert response.status_code == 200, response.json()
    return response.json()["items"]


# ── 생성 ──────────────────────────────────────────────────────────────────


def test_훈련_칸을_켠_Profile_로_만들면_후보가_오고_훈련_문서_칸은_비어_있다(plan):
    assert plan["drill_candidates"]
    for candidate in plan["drill_candidates"]:
        assert candidate["topic_id"] and candidate["label"]
        assert candidate["cell"]["value"].strip()
        assert candidate["cell"]["week_id"] is None
    cell = _drill_cell(plan)
    assert (cell["value"], cell["generation"]) == ("", None)
    assert _get(plan["id"]) == plan


def test_1월부터_12월까지_모든_달에_훈련_후보가_만들어진다(seed):
    _annual_confirmed(seed)
    for month in range(1, 13):
        created = _create(seed, month=month)
        assert created.status_code == 201, (month, created.json())
        candidates = created.json()["drill_candidates"]
        assert candidates, month
        assert all(c["cell"]["value"].strip() for c in candidates), month


def test_훈련_칸이_없는_계획은_후보가_비어_있고_복사하면_422_다(plain_seed):
    _annual_confirmed(plain_seed)
    plan = _create(plain_seed, profile="profile").json()

    assert plan["drill_candidates"] == []
    response = _copy(plan["id"], "item_아무거나", plan["revision"])
    assert _error(response) == (422, "VALIDATION_FAILED", [])
    assert (
        response.json()["error"]["message"]
        == "이 월간계획안에는 소방대피 · 재난대비 칸이 없습니다."
    )


# ── 복사 ──────────────────────────────────────────────────────────────────


def test_복사하면_칸에_후보_문장이_들어가고_RULE_ONLY_이고_revision_이_오른다(plan):
    candidate = plan["drill_candidates"][0]["cell"]

    response = _copy(plan["id"], candidate["item_id"], plan["revision"])

    assert response.status_code == 200, response.json()
    copied = response.json()
    cell = _drill_cell(copied)
    assert cell["value"] == candidate["value"]
    assert cell["generation"]["method"] == "RULE_ONLY"
    assert cell["evidence"] == candidate["evidence"]
    assert copied["revision"] == plan["revision"] + 1
    assert _get(plan["id"]) == copied


def test_같은_후보를_다시_복사하면_저장하지_않고_revision_과_이력이_그대로다(plan):
    candidate_id = plan["drill_candidates"][0]["cell"]["item_id"]
    copied = _copy(plan["id"], candidate_id, plan["revision"]).json()
    history = _audit(plan["id"])

    again = _copy(plan["id"], candidate_id, copied["revision"])

    assert again.status_code == 200, again.json()
    assert again.json() == copied
    assert _audit(plan["id"]) == history


def test_복사_거절은_저장하지_않는다(plan):
    candidate_id = plan["drill_candidates"][0]["cell"]["item_id"]

    missing = _copy(plan["id"], "item_없는후보", plan["revision"])
    bad_format = _copy(plan["id"], "%20", plan["revision"])
    stale = _copy(plan["id"], candidate_id, plan["revision"] + 1)

    assert _error(missing) == (404, "NOT_FOUND", ["item_id"])
    assert _error(bad_format) == (422, "VALIDATION_FAILED", ["item_id"])
    assert _error(stale) == (409, "STALE_WRITE", ["expected_revision"])
    assert _get(plan["id"])["revision"] == plan["revision"]


def test_확정_뒤에는_복사가_409_ALREADY_CONFIRMED_다(plan):
    assert _confirm(plan["id"], plan["revision"]).status_code == 200
    candidate_id = plan["drill_candidates"][0]["cell"]["item_id"]

    response = _copy(plan["id"], candidate_id, plan["revision"] + 1)

    assert _error(response) == (409, "ALREADY_CONFIRMED", [])


def test_빈_후보는_422_다(plan, db_session, seed):
    # 후보 문장을 비워 저장한 계획을 만든다 — 생성 경로는 늘 문장을 채우므로 저장소를 직접 고친다.
    from dataclasses import replace

    from ssuksak.planning import MonthlyPlan
    from ssuksak.planning.domain.monthly_constraint import CellState
    from test_monthly_lifecycle_api import _stored

    from app.features.plans.repository import PostgresPlanRepository

    _, domain = _stored(db_session, seed["center"], plan["id"])
    first = domain.drill_candidates[0]
    blanked = replace(
        domain,
        drill_candidates=(
            replace(first, cell=replace(first.cell, value="", cell_state=CellState.EMPTY_VALID)),
            *domain.drill_candidates[1:],
        ),
    )
    repo = PostgresPlanRepository(
        db_session, center_id=seed["center"], kind="monthly", plan_type=MonthlyPlan
    )
    assert repo.update_if_revision(blanked.plan_id, blanked, expected_revision=plan["revision"])

    response = _copy(plan["id"], first.cell.item_id.value, plan["revision"] + 1)

    assert _error(response) == (422, "VALIDATION_FAILED", ["item_id"])


def test_빈_훈련_칸에_교사가_처음_쓰면_MANUAL_이다(plan):
    cell = _drill_cell(plan)

    response = _edit(plan["id"], cell["item_id"], "교사가 쓴 훈련", plan["revision"])

    assert response.status_code == 200, response.json()
    edited = _drill_cell(response.json())
    assert (edited["value"], edited["generation"]["method"]) == ("교사가 쓴 훈련", "MANUAL")


def test_복사한_칸도_교사가_고칠_수_있고_생성_방식은_그대로다(plan):
    candidate_id = plan["drill_candidates"][0]["cell"]["item_id"]
    copied = _copy(plan["id"], candidate_id, plan["revision"]).json()

    response = _edit(plan["id"], _drill_cell(copied)["item_id"], "고친 훈련", copied["revision"])

    assert response.status_code == 200, response.json()
    cell = _drill_cell(response.json())
    assert (cell["value"], cell["generation"]["method"]) == ("고친 훈련", "RULE_ONLY")


# ── 이력 ──────────────────────────────────────────────────────────────────


def test_이력에_훈련_후보_칸_CREATED_와_복사의_copied_from_이_있다(plan):
    candidates = plan["drill_candidates"]
    candidate_id = candidates[0]["cell"]["item_id"]
    created = _audit(plan["id"])
    for candidate in candidates:
        assert any(
            i["item_id"] == candidate["cell"]["item_id"]
            and i["type"] == "CREATED"
            and i["section_key"] == "drill"
            for i in created
        )

    copied = _copy(plan["id"], candidate_id, plan["revision"]).json()
    drill_item = _drill_cell(copied)["item_id"]
    events = [i for i in _audit(plan["id"]) if i["type"] == "CANDIDATE_COPIED"]

    assert len(events) == 1
    event = events[0]
    assert (event["scope"], event["item_id"], event["section_key"]) == ("CELL", drill_item, "drill")
    assert event["copied_from"] == candidate_id
    assert event["value_change"] == {"before": "", "after": candidates[0]["cell"]["value"]}
    assert all(
        i["copied_from"] is None for i in _audit(plan["id"]) if i["type"] != "CANDIDATE_COPIED"
    )


def test_item_id_로_훈련_후보_칸_이력을_거를_수_있다(plan):
    candidate_id = plan["drill_candidates"][0]["cell"]["item_id"]
    assert _copy(plan["id"], candidate_id, plan["revision"]).status_code == 200

    items = _audit(plan["id"], candidate_id)

    assert [(i["type"], i["item_id"]) for i in items] == [("CREATED", candidate_id)]


# ── 내보내기 ──────────────────────────────────────────────────────────────


def _drill_row_text(response) -> str:
    from app.shared.hwpx import NS, _cells

    table, _ = _exported_table(response.content)
    cells = _cells(table)
    return "\n".join("".join(p.itertext()) for p in cells[(12, 1)].iterfind("hp:subList/hp:p", NS))


@pytest.mark.parametrize("month", [9, 10])  # 2026-09 는 5주, 2026-10 은 4주다
def test_내보내면_소방대피_재난대비_줄이_훈련_칸_값이다(seed, month):
    _annual_confirmed(seed)
    plan = _create(seed, month=month).json()
    candidate = plan["drill_candidates"][0]["cell"]
    copied = _copy(plan["id"], candidate["item_id"], plan["revision"]).json()
    assert _confirm(plan["id"], copied["revision"]).status_code == 200

    response = client.get(f"/api/plans/monthly/{plan['id']}/export/hwp")

    assert response.status_code == 200, response.text
    assert _drill_row_text(response) == candidate["value"]


def test_훈련_칸이_비어_있으면_그_줄은_빈칸이다(seed):
    _annual_confirmed(seed)
    plan = _create(seed).json()
    assert _confirm(plan["id"], plan["revision"]).status_code == 200

    response = client.get(f"/api/plans/monthly/{plan['id']}/export/hwp")

    assert response.status_code == 200, response.text
    assert _drill_row_text(response) == ""


def test_훈련_칸이_없는_Profile_의_내보내기는_그_줄이_빈칸이다(plain_seed):
    _annual_confirmed(plain_seed)
    plan = _create(plain_seed, profile="profile").json()
    assert plan["drill_candidates"] == []
    assert _confirm(plan["id"], plan["revision"]).status_code == 200

    response = client.get(f"/api/plans/monthly/{plan['id']}/export/hwp")

    assert response.status_code == 200, response.text
    assert _drill_row_text(response) == ""


# ── CANDIDATE_COPIED 의 generation_change ──────────────────────────────────


def _copied_event(plan_id) -> list[dict]:
    return [i for i in _audit(plan_id) if i["type"] == "CANDIDATE_COPIED"]


def test_빈_칸에_처음_복사하면_generation_change_가_null_이다(plan):
    candidate_id = plan["drill_candidates"][0]["cell"]["item_id"]
    assert _copy(plan["id"], candidate_id, plan["revision"]).status_code == 200

    (event,) = _copied_event(plan["id"])
    assert event["generation_change"] is None


def test_이미_쓴_칸에_다른_후보를_복사하면_이전_방식과_RULE_ONLY_가_온다(plan):
    first, second = (c["cell"]["item_id"] for c in plan["drill_candidates"][:2])
    copied = _copy(plan["id"], first, plan["revision"]).json()
    assert _copy(plan["id"], second, copied["revision"]).status_code == 200

    last = _copied_event(plan["id"])[-1]
    assert last["copied_from"] == second
    change = last["generation_change"]
    assert (change["before"]["method"], change["after"]["method"]) == ("RULE_ONLY", "RULE_ONLY")


def test_교사가_쓴_칸에_복사하면_before_가_MANUAL_이다(plan):
    written = _edit(plan["id"], _drill_cell(plan)["item_id"], "직접 쓴 훈련", plan["revision"])
    candidate = plan["drill_candidates"][0]["cell"]["item_id"]
    assert _copy(plan["id"], candidate, written.json()["revision"]).status_code == 200

    (event,) = _copied_event(plan["id"])
    change = event["generation_change"]
    assert (change["before"]["method"], change["after"]["method"]) == ("MANUAL", "RULE_ONLY")


# ── 오류 매핑 ─────────────────────────────────────────────────────────────


class _Raises:
    def __init__(self, code):
        self.code = code

    def execute(self, *args, **kwargs):
        raise MonthlyApplicationError(self.code, "테스트")


@pytest.mark.parametrize(
    "code",
    [
        "monthly_drill_reference_not_found",
        "monthly_drill_reference_not_active",
        "monthly_drill_curriculum_mismatch",
        "monthly_drill_unknown_content_id",
        "monthly_drill_topics_insufficient",
    ],
)
def test_훈련_자료_오류는_생성에서_503_이고_아무것도_저장하지_않는다(seed, monkeypatch, code):
    _annual_confirmed(seed)
    monkeypatch.setattr(monthly_router, "monthly_generation", lambda **kwargs: _Raises(code))

    response = _create(seed)

    assert _error(response) == (503, "DEPENDENCY_UNAVAILABLE", [])
    monkeypatch.undo()
    assert (
        client.get("/api/plans/monthly", params={"class_id": seed["class"]}).json()["items"] == []
    )


@pytest.mark.parametrize("code", ["activity_catalog_not_found", "activity_catalog_not_approved"])
def test_복사_뒤_활동_Catalog_오류는_503_이다(plan, monkeypatch, code):
    monkeypatch.setattr(monthly_router, "CopyMonthlyDrillCandidate", lambda **kwargs: _Raises(code))
    candidate_id = plan["drill_candidates"][0]["cell"]["item_id"]

    response = _copy(plan["id"], candidate_id, plan["revision"])

    assert _error(response) == (503, "DEPENDENCY_UNAVAILABLE", [])
    monkeypatch.undo()
    assert _get(plan["id"])["revision"] == plan["revision"]
