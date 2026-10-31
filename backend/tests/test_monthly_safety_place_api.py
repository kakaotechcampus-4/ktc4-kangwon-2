"""v1 월간 안전 배치 API (api-spec §9-3) — `PUT /api/plans/monthly/{id}/safety-weeks/{week_id}`.

후보 모드 계획은 test_monthly_safety_read_api.py 의 가짜 LLM 으로 실제 POST 를 거쳐 만든다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

from test_monthly_lifecycle_api import (  # noqa: F401
    _approved,
    _confirm,
    _edit,
    _error,
    _get,
    _monthly,
    _regenerate,
    _seed,
    _stored,
    client,
)
from test_monthly_safety_read_api import _active_weeks, candidate_mode, seed  # noqa: F401


def _place(plan_id, week_id, candidate_item_id, revision):
    return client.put(
        f"/api/plans/monthly/{plan_id}/safety-weeks/{week_id}",
        json={"expected_revision": revision, "candidate_item_id": candidate_item_id},
    )


def _audit(plan_id, item_id=None) -> list[dict]:
    params = {} if item_id is None else {"item_id": item_id}
    response = client.get(f"/api/plans/monthly/{plan_id}/audit", params=params)
    assert response.status_code == 200, response.json()
    return response.json()["items"]


def _week(plan: dict, week_id: str) -> dict:
    return next(w for w in plan["safety_weeks"] if w["week_id"] == week_id)


def test_배치하면_그_주에_후보가_붙고_revision_이_오르고_안내가_빠진다(seed, candidate_mode):
    plan = _monthly(seed)
    week = _active_weeks(plan)[0]
    candidate = plan["safety_candidates"][0]["cell"]

    response = _place(plan["id"], week, candidate["item_id"], plan["revision"])

    assert response.status_code == 200, response.json()
    placed = response.json()
    assert placed["revision"] == plan["revision"] + 1
    assert _week(placed, week)["candidate_item_id"] == candidate["item_id"]
    assert _week(placed, week)["display_value"].endswith(candidate["value"])
    assert week not in {n["week_id"] for n in placed["notices"]}
    assert _get(plan["id"]) == placed


def test_null_로_비우면_다시_SAFETY_UNPLACED_이고_표시값은_빈_문자열이다(seed, candidate_mode):
    plan = _monthly(seed)
    week = _active_weeks(plan)[0]
    placed = _place(plan["id"], week, plan["safety_candidates"][0]["cell"]["item_id"], 1).json()

    response = _place(plan["id"], week, None, placed["revision"])

    assert response.status_code == 200, response.json()
    cleared = response.json()
    assert _week(cleared, week) == {"week_id": week, "candidate_item_id": None, "display_value": ""}
    assert {"code": "SAFETY_UNPLACED", "week_id": week} in cleared["notices"]


def test_같은_선택을_다시_하면_저장하지_않고_revision_과_이력이_그대로다(seed, candidate_mode):
    plan = _monthly(seed)
    week = _active_weeks(plan)[0]
    candidate_id = plan["safety_candidates"][0]["cell"]["item_id"]
    placed = _place(plan["id"], week, candidate_id, 1).json()
    history = _audit(plan["id"])

    again = _place(plan["id"], week, candidate_id, placed["revision"])
    cleared_again = _place(plan["id"], _active_weeks(plan)[1], None, placed["revision"])

    assert again.status_code == 200, again.json()
    assert again.json() == placed
    assert cleared_again.json() == placed  # 이미 빈 주를 또 비워도 같다
    assert _audit(plan["id"]) == history


def test_옛_revision_은_409_STALE_WRITE_이고_확정된_계획은_409_ALREADY_CONFIRMED_다(
    seed, candidate_mode
):
    plan = _monthly(seed)
    week = _active_weeks(plan)[0]
    candidate_id = plan["safety_candidates"][0]["cell"]["item_id"]

    stale = _place(plan["id"], week, candidate_id, plan["revision"] + 1)
    assert _error(stale) == (409, "STALE_WRITE", ["expected_revision"])

    assert _confirm(plan["id"], plan["revision"]).status_code == 200
    confirmed = _place(plan["id"], week, candidate_id, plan["revision"] + 1)
    assert _error(confirmed) == (409, "ALREADY_CONFIRMED", [])


def test_형식이_틀린_주는_422_이고_없는_주는_404_다(seed, candidate_mode):
    plan = _monthly(seed)
    candidate_id = plan["safety_candidates"][0]["cell"]["item_id"]

    bad_format = _place(plan["id"], "not-a-week", candidate_id, 1)
    other_month = _place(plan["id"], "2026-10-W1", candidate_id, 1)

    assert _error(bad_format) == (422, "VALIDATION_FAILED", ["week_id"])
    assert _error(other_month) == (404, "NOT_FOUND", ["week_id"])


def test_후보_id_가_틀리거나_본문에_키가_없으면_422_다(seed, candidate_mode):
    plan = _monthly(seed)
    week = _active_weeks(plan)[0]

    blank = _place(plan["id"], week, "", 1)
    missing = _place(plan["id"], week, "item_없는후보", 1)
    no_key = client.put(
        f"/api/plans/monthly/{plan['id']}/safety-weeks/{week}", json={"expected_revision": 1}
    )

    assert _error(blank) == (422, "VALIDATION_FAILED", ["candidate_item_id"])
    assert _error(missing) == (422, "VALIDATION_FAILED", ["candidate_item_id"])
    assert no_key.status_code == 422
    assert _get(plan["id"])["revision"] == plan["revision"]


def test_후보가_없는_기존_계획에_배치하면_422_다(seed):
    plan = _monthly(seed)
    week = _active_weeks(plan)[0]

    response = _place(plan["id"], week, None, plan["revision"])

    assert _error(response) == (422, "VALIDATION_FAILED", [])
    assert response.json()["error"]["message"] == "이 월간계획안에는 안전교육 후보가 없습니다."


def test_후보_모드의_주별_안전_칸을_고치면_422_이고_저장되지_않는다(seed, candidate_mode):
    plan = _monthly(seed)
    section = next(s for s in plan["sections"] if s["section_key"] == "safety_education")
    cell = next(c for c in section["cells"] if c["week_id"] is not None)

    response = _edit(plan["id"], cell["item_id"], "교사가 쓴 안전교육", plan["revision"])

    assert _error(response) == (422, "VALIDATION_FAILED", ["item_id"])
    assert response.json()["error"]["message"] == "이 칸은 고칠 수 없습니다."
    assert _get(plan["id"]) == plan


def test_후보_문장은_고칠_수_있고_다시_만들_수는_없다(seed, candidate_mode):
    plan = _monthly(seed)
    candidate_id = plan["safety_candidates"][0]["cell"]["item_id"]

    edited = _edit(plan["id"], candidate_id, "교사가 고친 후보", plan["revision"])
    assert edited.status_code == 200, edited.json()
    assert edited.json()["safety_candidates"][0]["cell"]["value"] == "교사가 고친 후보"

    regenerated = _regenerate(plan["id"], candidate_id, edited.json()["revision"])
    assert _error(regenerated) == (422, "VALIDATION_FAILED", ["item_id"])
    assert regenerated.json()["error"]["message"] == "이 칸은 다시 만들 수 없습니다."


def test_배치는_이력에_ARRANGEMENT_CHANGED_로_남고_후보_칸_이력도_온다(seed, candidate_mode):
    plan = _monthly(seed)
    week = _active_weeks(plan)[0]
    candidate_id = plan["safety_candidates"][0]["cell"]["item_id"]
    placed = _place(plan["id"], week, candidate_id, 1).json()
    assert (
        _edit(plan["id"], candidate_id, "교사가 고친 후보", placed["revision"]).status_code == 200
    )

    items = _audit(plan["id"])

    (arranged,) = [i for i in items if i["type"] == "ARRANGEMENT_CHANGED"]
    assert arranged["scope"] == "PLAN"
    assert arranged["arrangement_change"] == {"scope": week, "before": [], "after": [candidate_id]}
    created = next(i for i in items if i["item_id"] == candidate_id and i["type"] == "CREATED")
    assert (created["scope"], created["section_key"], created["week_id"]) == (
        "CELL",
        "safety_education",
        None,
    )
    assert any(i["item_id"] == candidate_id and i["type"] == "TEACHER_EDITED" for i in items)
    assert all(i["arrangement_change"] is None for i in items if i is not arranged)

    only = _audit(plan["id"], candidate_id)
    assert {i["type"] for i in only} == {"CREATED", "TEACHER_EDITED"}
    assert all(i["item_id"] == candidate_id for i in only)
