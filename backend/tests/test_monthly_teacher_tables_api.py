"""v1 월간 교사 표(행사 일정 · 특성화 · 특별활동) 편집 · 나누기 API (Human Decision 2026-11-05).

경로 · 본문은 놀이 월간 시간표(ADR-047)와 같은 모양이다. 칸 글은 기존 칸 편집으로 쓴다.
"""

# ruff: noqa: F811 — 다른 테스트 파일의 픽스처를 가져와 쓰면 인자 이름이 import 와 겹친다

from ssuksak.planning import ItemId
from test_monthly_lifecycle_api import (  # noqa: F401
    _approved,
    _confirm,
    _edit,
    _error,
    _get,
    _stored,
    client,
    world,
)
from test_monthly_plans_api import _exported_table

URL = "/api/plans/monthly"


def _table(plan: dict, key: str) -> dict:
    return next(t for t in plan["teacher_tables"] if t["table_key"] == key)


def _split(plan_id, item_id, axis, revision):
    return client.post(
        f"{URL}/{plan_id}/cells/{item_id}/split",
        json={"axis": axis, "expected_revision": revision},
    )


def test_빈_표_셋이_보이고_행사_칸은_교사가_쓰면_MANUAL_이다(world):
    plan = world["plan"]
    assert [t["table_key"] for t in plan["teacher_tables"]] == [
        "event_schedule",
        "specialized_timetable",
        "special_activity_timetable",
    ]
    event = _table(plan, "event_schedule")
    assert (event["label"], event["column_widths"], event["titles"]) == ("행사 일정", [100], [])
    cell = event["columns"][0]["cell"]
    assert (cell["value"], cell["generation"]) == ("", None)
    assert _get(plan["id"])["teacher_tables"] == plan["teacher_tables"]  # 같은 id 를 다시 준다

    edited = _edit(plan["id"], cell["item_id"], "9/12 추석 행사", plan["revision"])
    assert edited.status_code == 200, edited.json()
    body = edited.json()
    after = _table(body, "event_schedule")["columns"][0]["cell"]
    assert (after["item_id"], after["value"]) == (cell["item_id"], "9/12 추석 행사")
    assert after["generation"]["method"] == "MANUAL"
    assert body["revision"] == plan["revision"] + 1
    _, core = _stored(world["session"], world["mine"]["center"], plan["id"])
    _, stored = core.table_cell(ItemId(cell["item_id"]))
    events = [e.event_type.value for e in stored.audit.events]
    assert events == ["TEACHER_EDITED"]

    title = _table(body, "specialized_timetable")["titles"][0]
    titled = _edit(plan["id"], title["item_id"], "영어", body["revision"])
    assert titled.status_code == 200, titled.json()
    assert _table(titled.json(), "specialized_timetable")["titles"][0]["value"] == "영어"
    split_title = _split(plan["id"], title["item_id"], "VERTICAL", titled.json()["revision"])
    assert split_title.status_code == 404


def test_나누고_비율_크기를_바꾸고_빼면_한글_문서에도_그대로다(world):
    plan = world["plan"]
    first = _table(plan, "special_activity_timetable")["columns"][0]["cell"]["item_id"]

    split = _split(plan["id"], first, "VERTICAL", plan["revision"])
    assert split.status_code == 200, split.json()
    column = _table(split.json(), "special_activity_timetable")["columns"][0]
    assert (column["axis"], column["ratio"]) == ("VERTICAL", 50)
    top, bottom = (c["cell"] for c in column["children"])
    assert top["item_id"] == first
    revision = split.json()["revision"]

    for item_id, text in ((top["item_id"], "체육"), (bottom["item_id"], "미술")):
        edited = _edit(plan["id"], item_id, text, revision)
        assert edited.status_code == 200, edited.json()
        revision = edited.json()["revision"]

    ratio = client.put(
        f"{URL}/{plan['id']}/timetable/splits/{column['split_id']}",
        json={"ratio": 30, "expected_revision": revision},
    )
    assert ratio.status_code == 200, ratio.json()
    assert _table(ratio.json(), "special_activity_timetable")["columns"][0]["ratio"] == 30
    revision = ratio.json()["revision"]
    same = client.put(
        f"{URL}/{plan['id']}/timetable/splits/{column['split_id']}",
        json={"ratio": 30, "expected_revision": revision},
    )
    assert same.json()["revision"] == revision  # 같은 값이면 저장하지 않는다

    size = client.put(
        f"{URL}/{plan['id']}/timetable/size",
        json={
            "table_key": "special_activity_timetable",
            "column_widths": [30, 10, 20, 20, 20],
            "height_mm": 40,
            "expected_revision": revision,
        },
    )
    assert size.status_code == 200, size.json()
    table = _table(size.json(), "special_activity_timetable")
    assert (table["column_widths"], table["height_mm"]) == ([30, 10, 20, 20, 20], 40)
    revision = size.json()["revision"]

    event = _table(plan, "event_schedule")["columns"][0]["cell"]["item_id"]
    beside = _split(plan["id"], event, "HORIZONTAL", revision)
    assert beside.status_code == 200, beside.json()
    revision = beside.json()["revision"]
    second = _table(beside.json(), "event_schedule")["columns"][0]["children"][1]["cell"]
    edited = _edit(plan["id"], second["item_id"], "운동회", revision)
    assert edited.status_code == 200, edited.json()
    revision = edited.json()["revision"]

    confirmed = _confirm(plan["id"], revision)
    assert confirmed.status_code == 200, confirmed.json()
    response = client.get(f"{URL}/{plan['id']}/export/hwp")
    assert response.status_code == 200, response.text
    table, texts = _exported_table(response.content)
    assert {"체육", "미술", "운동회", "행사 일정", "[ 특별활동 시간표 ]"} <= set(texts)
    assert int(table.get("rowCnt")) == 26  # 특별활동 위아래 나눔이 한 줄을 더한다


def test_마지막_칸은_뺄_수_없고_나눈_칸은_빼면_형제가_자리를_채운다(world):
    plan = world["plan"]
    only = _table(plan, "specialized_timetable")["columns"][2]["cell"]["item_id"]
    last = client.delete(
        f"{URL}/{plan['id']}/cells/{only}/split", params={"expected_revision": plan["revision"]}
    )
    assert _error(last) == (422, "VALIDATION_FAILED", ["item_id"])

    split = _split(plan["id"], only, "HORIZONTAL", plan["revision"]).json()
    added = _table(split, "specialized_timetable")["columns"][2]["children"][1]["cell"]
    removed = client.delete(
        f"{URL}/{plan['id']}/cells/{added['item_id']}/split",
        params={"expected_revision": split["revision"]},
    )
    assert removed.status_code == 200, removed.json()
    assert _table(removed.json(), "specialized_timetable")["columns"][2]["cell"]["item_id"] == only


def test_확정된_계획안은_표를_고치지_못한다(world):
    plan = world["plan"]
    confirmed = _confirm(plan["id"], plan["revision"]).json()
    cell = _table(confirmed, "event_schedule")["columns"][0]["cell"]["item_id"]
    revision = confirmed["revision"]
    calls = (
        _split(plan["id"], cell, "VERTICAL", revision),
        client.delete(
            f"{URL}/{plan['id']}/cells/{cell}/split", params={"expected_revision": revision}
        ),
        client.put(
            f"{URL}/{plan['id']}/timetable/size",
            json={
                "table_key": "event_schedule",
                "column_widths": [100],
                "height_mm": 30,
                "expected_revision": revision,
            },
        ),
        _edit(plan["id"], cell, "행사", revision),
    )
    for response in calls:
        assert _error(response)[:2] == (409, "ALREADY_CONFIRMED"), response.json()
