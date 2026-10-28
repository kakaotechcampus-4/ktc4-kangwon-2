"""놀이 프로젝트형 선택 저장 · 칸 편집 API (api-spec §6-1, ADR-048 §1~§3)."""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from ssuksak.planning import PlanId
from test_plans_play_project import (  # noqa: F401
    _approved,
    _klass,
    _logged_in,
    _plan,
    saved,
    world,
)

from app.db import engine
from app.features.centers.models import Center, Class
from app.features.plans import router as plans_router
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.main import app

from ssuksak.planning.domain.play_project_plan import PlayProjectYearlyPlan  # isort: skip
from ssuksak.planning.domain.provenance import EvidenceSource, EvidenceSourceType  # isort: skip

client = TestClient(app)
KEYS = ("m03_m05", "m06_m08", "m09_m11", "m12_m02")
EMPTY = {key: [] for key in KEYS}


def _put_selection(row, selections, revision=1):
    return client.put(
        f"/api/plans/annual/{row.id}/selection",
        json={"selections": selections, "expected_revision": revision},
    )


def _put_cell(row, item_id, value, revision=1):
    return client.put(
        f"/api/plans/annual/{row.id}/cells/{item_id}",
        json={"value": value, "expected_revision": revision},
    )


def _stored(world, row) -> PlayProjectYearlyPlan:
    session = world["session"]
    session.refresh(row)
    return PostgresPlanRepository(
        session, center_id=world["center_id"], kind="annual", plan_type=PlayProjectYearlyPlan
    ).get(PlanId(row.plan_ref))


def _item_id(plan, period=0, n=1, field="play_name"):
    return getattr(plan.periods[period].candidates[n - 1], field).item_id.value


def _events(plan, kind):
    return [e for e in plan.audit.events if e.event_type.value == kind]


def _error(response, status, code, fields):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert (error["code"], error["fields"]) == (code, fields), error
    return error


def _unchanged(world, row, plan, revision=1):
    """실패한 요청은 본문 · revision 을 바꾸지 않는다."""
    assert _stored(world, row) == plan
    assert row.revision == revision


def test_상세_응답이_revision_selected_item_id_를_준다(saved):
    _, row = saved
    detail = client.get(f"/api/plans/annual/{row.id}").json()
    assert detail["revision"] == 1
    assert [p["selected"] for p in detail["periods"]] == [[]] * 4
    cells = [
        c[f]["item_id"]
        for p in detail["periods"]
        for c in p["candidates"]
        for f in ("play_name", "materials", "support_direction", "learning")
    ]
    assert len(cells) == len(set(cells)) == 160 and all(cells)


def test_생성_응답도_revision_selected_item_id_를_준다(world, monkeypatch):
    _approved(monkeypatch)
    created = client.post(
        "/api/plans/annual", json={"class_id": world["play"].id, "format": "PLAY_PROJECT"}
    ).json()
    assert created["revision"] == 1
    assert [p["selected"] for p in created["periods"]] == [[]] * 4
    assert created["periods"][0]["candidates"][0]["play_name"]["item_id"].startswith("item_")


def test_선택_저장은_순서대로_저장하고_바뀐_구간마다_이벤트_하나(world, saved):
    plan, row = saved
    selections = {**EMPTY, "m03_m05": ["cand5", "cand1"], "m09_m11": ["cand2"]}

    response = _put_selection(row, selections)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 2
    assert [p["selected"] for p in body["periods"]] == [["cand5", "cand1"], [], ["cand2"], []]
    stored = _stored(world, row)
    assert [p.selected for p in stored.periods] == [("cand5", "cand1"), (), ("cand2",), ()]
    events = _events(stored, "CANDIDATES_SELECTED")
    assert [(e.selection_change.period_key, e.selection_change.after) for e in events] == [
        ("m03_m05", ("cand5", "cand1")),
        ("m09_m11", ("cand2",)),
    ]
    assert all(e.actor_id.value == "user_1" for e in events)
    assert row.revision == 2


def test_선택이_같으면_200_이고_revision_과_이벤트가_그대로(world, saved):
    plan, row = saved
    selections = {**EMPTY, "m03_m05": ["cand2", "cand1"]}
    assert _put_selection(row, selections).status_code == 200

    again = _put_selection(row, selections, revision=2)

    assert again.status_code == 200
    assert again.json()["revision"] == 2
    assert len(_events(_stored(world, row), "CANDIDATES_SELECTED")) == 1
    assert row.revision == 2


def test_선택이_같아도_revision_이_다르면_409(world, saved):
    _, row = saved
    _put_selection(row, EMPTY)  # 무변경 — revision 1 그대로
    _error(_put_selection(row, EMPTY, revision=7), 409, "STALE_WRITE", ["expected_revision"])


@pytest.mark.parametrize(
    "selections, fields",
    [
        ({k: [] for k in KEYS[:3]}, ["selections.m12_m02"]),
        ({**EMPTY, "m99": []}, ["selections.m99"]),
        ({**EMPTY, "m06_m08": [f"cand{n}" for n in range(1, 7)]}, ["selections.m06_m08"]),
        ({**EMPTY, "m06_m08": ["cand1", "cand1"]}, ["selections.m06_m08"]),
        ({**EMPTY, "m09_m11": ["cand99"]}, ["selections.m09_m11"]),
    ],
)
def test_선택_저장_422_는_구간_키를_가리키고_아무것도_저장하지_않는다(
    world, saved, selections, fields
):
    plan, row = saved
    # 유효한 변경(m03_m05)이 있어도 다른 구간이 틀리면 전부 막는다
    selections = {**selections, "m03_m05": ["cand1"]}

    _error(_put_selection(row, selections), 422, "VALIDATION_FAILED", fields)

    _unchanged(world, row, plan)


@pytest.mark.parametrize("revision", ["3", True, 0])
def test_expected_revision_타입이_틀리면_422(saved, revision):
    _, row = saved
    _error(_put_selection(row, EMPTY, revision), 422, "VALIDATION_FAILED", ["expected_revision"])
    _error(
        _put_cell(row, "item_x", "값", revision), 422, "VALIDATION_FAILED", ["expected_revision"]
    )


def test_옛_revision_이면_409_이고_같은_revision_으로_두_번째는_저장되지_않는다(world, saved):
    plan, row = saved
    first = _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    assert first.status_code == 200

    second = _put_selection(row, {**EMPTY, "m03_m05": ["cand2"]}, revision=1)

    _error(second, 409, "STALE_WRITE", ["expected_revision"])
    assert _stored(world, row).periods[0].selected == ("cand1",)
    assert row.revision == 2


def test_칸_편집은_값만_바꾸고_근거_생성방식은_그대로_TEACHER_EDITED_를_남긴다(world, saved):
    plan, row = saved
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    item_id = _item_id(plan, 0, 1, "support_direction")
    before = plan.periods[0].candidates[0].support_direction

    response = _put_cell(row, item_id, "  새 지원 방향  ", revision=2)

    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 3
    cell = response.json()["periods"][0]["candidates"][0]["support_direction"]
    assert (cell["item_id"], cell["value"]) == (item_id, "새 지원 방향")
    after = _stored(world, row).periods[0].candidates[0].support_direction
    assert after.value == "새 지원 방향"
    assert (after.evidence, after.generation, after.item_id) == (
        before.evidence,
        before.generation,
        before.item_id,
    )
    assert after.generation.rule_id == "play_project.generate"
    edited = _events(after, "TEACHER_EDITED")
    assert len(edited) == 1
    assert (edited[0].value_change.before, edited[0].value_change.after) == (
        "지켜본다",
        "새 지원 방향",
    )
    assert edited[0].actor_id.value == "user_1"
    assert row.revision == 3


@pytest.mark.parametrize("value", ["지켜본다", "  지켜본다 ", "", "   ", "가" * 601])
def test_칸_편집_422_값(world, saved, value):
    plan, row = saved
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    plan = _stored(world, row)

    _error(
        _put_cell(row, _item_id(plan, 0, 1, "support_direction"), value, revision=2),
        422,
        "VALIDATION_FAILED",
        ["value"],
    )

    _unchanged(world, row, plan, revision=2)


def test_칸_편집_600자는_저장된다(world, saved):
    plan, row = saved
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    assert _put_cell(row, _item_id(plan, 0, 1), "가" * 600, revision=2).status_code == 200


def test_칸_편집_422_item_id(world, saved):
    plan, row = saved
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    plan = _stored(world, row)
    for item_id in (
        _item_id(plan, 0, 1, "learning"),  # 배움은 읽기 전용
        _item_id(plan, 0, 2),  # 안 고른 후보
        "item_없는칸",
        " ",
    ):
        _error(_put_cell(row, item_id, "새 값", revision=2), 422, "VALIDATION_FAILED", ["item_id"])
        _unchanged(world, row, plan, revision=2)


def test_남의_원_계획안은_404(world, saved):
    session = world["session"]
    other = Center(
        name="다른어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    session.add(other)
    session.flush()
    plan = _plan(str(_klass(session, other, "남의반").id))
    PostgresPlanRepository(
        session, center_id=other.id, kind="annual", plan_type=PlayProjectYearlyPlan
    ).save(plan.plan_id, plan)
    session.commit()
    row = session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))

    _error(_put_selection(row, EMPTY), 404, "NOT_FOUND", ["id"])
    _error(_put_cell(row, _item_id(plan), "값"), 404, "NOT_FOUND", ["id"])
    assert _put_selection(type("R", (), {"id": 999999})(), EMPTY).status_code == 404


def test_월별_주제형에_두_API_는_409(world):
    created = client.post(
        "/api/plans/annual",
        json={"format": "MONTHLY_THEME", "class_id": world["theme"].id, "form_id": None},
    )
    row = type("R", (), {"id": created.json()["id"]})()
    for response in (_put_selection(row, EMPTY), _put_cell(row, "item_x", "값")):
        error = _error(response, 409, "GATE_BLOCKED", [])
        assert error["message"] == "월별 주제형은 월별 칸 수정으로 고칩니다."


def test_놀이형에_월별_칸_수정은_새_문구의_409(world, saved):
    _, row = saved
    response = client.put(
        f"/api/plans/annual/{row.id}/months/3", json={"theme": "새 주제", "sub_themes": []}
    )
    error = _error(response, 409, "GATE_BLOCKED", [])
    assert error["message"] == "놀이 프로젝트형은 칸 편집으로 고칩니다."


def test_확정된_놀이형은_선택도_편집도_409(world, saved):
    plan, row = saved
    item_id = _item_id(plan, 0, 1)
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    row.status = "CONFIRMED"
    world["session"].flush()

    _error(_put_selection(row, EMPTY, revision=2), 409, "ALREADY_CONFIRMED", [])
    _error(_put_cell(row, item_id, "새 값", revision=2), 409, "ALREADY_CONFIRMED", [])


@pytest.fixture
def live(_schema, teacher):
    """커밋된 원 · 반 · 놀이형 DRAFT. 끼어드는 요청은 다른 연결에서 커밋한다."""
    with Session(engine) as session:
        center = Center(
            name="놀이 저장 잠금 테스트원",
            director_name="김원장",
            region_sido="강원특별자치도",
            region_sigungu="춘천시",
        )
        session.add(center)
        session.flush()
        klass = _klass(session, center, "놀이반")
        plan = _plan(str(klass.id))
        PostgresPlanRepository(
            session, center_id=center.id, kind="annual", plan_type=PlayProjectYearlyPlan
        ).save(plan.plan_id, plan)
        session.commit()
        row_id = session.scalar(select(Plan.id).where(Plan.plan_ref == plan.plan_id.value))
        ids = {"center": center.id, "class": klass.id, "plan": plan, "row": row_id}
    teacher.center_id = ids["center"]
    try:
        yield ids
    finally:
        with Session(engine) as session:
            session.execute(delete(Plan).where(Plan.center_id == ids["center"]))
            session.execute(delete(Class).where(Class.id == ids["class"]))
            session.execute(delete(Center).where(Center.id == ids["center"]))
            session.commit()


def _interleave(monkeypatch, row_id, statement):
    """요청이 읽은 뒤 · 쓰기 전에, 다른 연결이 statement 를 커밋한다."""
    read = plans_router._play_read

    def read_then_interleave(*args):
        result = read(*args)
        with Session(engine) as other:
            other.execute(statement(row_id))
            other.commit()
        return result

    monkeypatch.setattr(plans_router, "_play_read", read_then_interleave)


@pytest.mark.parametrize(
    "statement, status, code, fields",
    [
        (
            lambda i: update(Plan).where(Plan.id == i).values(revision=Plan.revision + 1),
            409,
            "STALE_WRITE",
            ["expected_revision"],
        ),
        (
            lambda i: update(Plan).where(Plan.id == i).values(status="CONFIRMED"),
            409,
            "ALREADY_CONFIRMED",
            [],
        ),
        (lambda i: delete(Plan).where(Plan.id == i), 404, "NOT_FOUND", ["id"]),
    ],
    ids=["revision만_올림", "확정", "삭제"],
)
def test_읽은_뒤_쓰기_전에_다른_연결이_커밋하면_조건부_UPDATE_가_막는다(
    live, monkeypatch, statement, status, code, fields
):
    row = type("R", (), {"id": live["row"]})()
    _interleave(monkeypatch, live["row"], statement)

    _error(_put_selection(row, {**EMPTY, "m03_m05": ["cand1"]}), status, code, fields)

    with Session(engine) as session:
        stored = session.scalar(select(Plan).where(Plan.id == live["row"]))
        if status != 404:
            assert stored.body["periods"][0]["selected"] == []


def test_빼고_다시_골라도_고친_값과_TEACHER_EDITED_가_남는다(world, saved):
    plan, row = saved
    item_id = _item_id(plan, 0, 1)
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]})
    _put_cell(row, item_id, "고친 놀이", revision=2)
    _put_selection(row, EMPTY, revision=3)

    assert _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]}, revision=4).status_code == 200

    stored = _stored(world, row)
    item = stored.periods[0].candidates[0].play_name
    assert item.value == "고친 놀이"
    assert len(_events(item, "TEACHER_EDITED")) == 1
    assert stored.periods[0].selected == ("cand1",)


def test_두_구간이_함께_틀리면_fields_에_정렬된_두_키가_온다(world, saved):
    plan, row = saved
    selections = {**EMPTY, "m09_m11": ["cand99"], "m06_m08": ["cand98"]}

    _error(
        _put_selection(row, selections),
        422,
        "VALIDATION_FAILED",
        ["selections.m06_m08", "selections.m09_m11"],
    )

    _unchanged(world, row, plan)


def test_비어_있지_않은_근거도_칸_편집_뒤_그대로다(world, saved):
    plan, row = saved
    item_id = _item_id(plan, 0, 1, "materials")
    old = plan.periods[0].candidates[0].materials
    cited = replace(
        old,
        evidence=(
            EvidenceSource(
                EvidenceSourceType.THEME_REFERENCE,
                "theme.1",
                source_version="v1",
                display_name="주제",
            ),
        ),
    )
    repo = PostgresPlanRepository(
        world["session"],
        center_id=world["center_id"],
        kind="annual",
        plan_type=PlayProjectYearlyPlan,
    )
    repo.save(plan.plan_id, plan.replace_item(old.item_id, cited))
    world["session"].commit()
    world["session"].refresh(row)
    revision = row.revision
    _put_selection(row, {**EMPTY, "m03_m05": ["cand1"]}, revision=revision)

    response = _put_cell(row, item_id, "새 재료", revision=revision + 1)

    assert response.status_code == 200, response.text
    after = _stored(world, row).periods[0].candidates[0].materials
    assert after.value == "새 재료"
    assert after.evidence == cited.evidence != ()
    cell = response.json()["periods"][0]["candidates"][0]["materials"]
    assert [e["source_id"] for e in cell["evidence"]] == ["theme.1"]


def test_행을_읽은_뒤_본문을_읽기_전에_지워지면_404(world, saved, monkeypatch):
    _, row = saved
    monkeypatch.setattr(PostgresPlanRepository, "get", lambda self, plan_id: None)

    _error(_put_selection(row, EMPTY), 404, "NOT_FOUND", ["id"])
    _error(_put_cell(row, "item_x", "값"), 404, "NOT_FOUND", ["id"])
