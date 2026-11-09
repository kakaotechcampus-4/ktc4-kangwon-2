"""일과 임시본 — 쓰는 대로 서버에 두고, 떠날 때 · 일지 만들 때 근거로 올린다.

ADR-082 · api-spec §10-1.
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.features.centers.models import Center, Class
from app.features.documents.models import Document, DocumentSource
from app.features.routines.drafts import prune_drafts
from app.features.routines.models import RoutineDraft, RoutineRecord
from app.main import app

client = TestClient(app)
DAY = "2026-11-10"


@pytest.fixture
def sun(db_session, teacher):
    center = Center(
        name="테스트어린이집", director_name="김원장", region_sido="강원", region_sigungu="춘천시"
    )
    db_session.add(center)
    db_session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김",
    )
    db_session.add(klass)
    db_session.flush()
    teacher.center_id = center.id
    return klass


def _row(**kw):
    return {
        "id": None,
        "start": "09:20",
        "end": "10:40",
        "name": "오전 실내놀이",
        "plan": "",
        "execution": "블록으로 길을 만들었다.",
        "touched": True,
        **kw,
    }


def _save(klass, rows, *, revision=0, removed=(), promote=False, day=DAY):
    return client.put(
        "/api/routines/draft",
        json={
            "class_id": klass.id,
            "date": day,
            "expected_revision": revision,
            "rows": rows,
            "removed": list(removed),
            "promote": promote,
        },
    )


def _day(klass, day=DAY):
    return client.get(f"/api/routines?class_id={klass.id}&from={day}&to={day}").json()


def test_임시본은_일과_기록에_쓰지_않고_하루치_조회에_붙는다(db_session, sun):
    res = _save(sun, [_row()])
    assert res.status_code == 200, res.text
    draft = res.json()["draft"]
    assert draft["revision"] == 1
    assert draft["promoted"] is False
    assert res.json()["items"] is None

    day = _day(sun)
    assert day["items"] == []
    assert day["draft"]["rows"][0]["execution"] == "블록으로 길을 만들었다."
    assert day["draft"]["revision"] == 1
    assert db_session.scalars(select(RoutineRecord)).all() == []


def test_여러_날이나_반_없는_조회에는_임시본이_없다(sun):
    _save(sun, [_row()])
    assert client.get(f"/api/routines?class_id={sun.id}").json()["draft"] is None
    assert client.get(f"/api/routines?from={DAY}&to={DAY}").json()["draft"] is None


def test_다른_기기가_먼저_고쳤으면_409_STALE_WRITE_로_덮지_않는다(sun):
    assert _save(sun, [_row()]).status_code == 200
    stale = _save(sun, [_row(execution="옛 탭에서 친 글")], revision=0)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_WRITE"
    assert _day(sun)["draft"]["rows"][0]["execution"] == "블록으로 길을 만들었다."

    ok = _save(sun, [_row(execution="새 글")], revision=1)
    assert ok.json()["draft"]["revision"] == 2


def test_근거로_올리면_손댄_줄만_일과_기록이_되고_번호가_임시본에_붙는다(db_session, sun):
    rows = [
        _row(),
        # 깔아 두기만 하고 손대지 않은 줄 — 올리지 않는다.
        _row(name="점심식사", start="12:20", end="13:20", execution="", touched=False),
        # 손댔지만 통째로 빈 줄 — 올리지 않는다.
        _row(name="", start=None, end=None, execution=""),
        _row(name="바깥놀이", start="11:00", end="12:20", execution="모래놀이"),
    ]
    res = _save(sun, rows, promote=True)
    assert res.status_code == 200, res.text
    body = res.json()
    assert [i["name"] for i in body["items"]] == ["오전 실내놀이", "바깥놀이"]
    assert [i["position"] for i in body["items"]] == [0, 1]
    assert body["draft"]["promoted"] is True
    ids = [r["id"] for r in body["draft"]["rows"]]
    assert ids[0] == body["items"][0]["id"] and ids[3] == body["items"][1]["id"]
    assert ids[1] is None and ids[2] is None
    assert body["review_impact"] == {"affected_document_ids": [], "newly_stale_document_ids": []}
    assert len(db_session.scalars(select(RoutineRecord)).all()) == 2


def test_다시_올리면_같은_줄을_두_번_만들지_않고_고친_줄만_바꾼다(db_session, sun):
    first = _save(sun, [_row()], promote=True).json()
    rows = first["draft"]["rows"]
    rows[0]["execution"] = "블록으로 다리를 만들었다."
    again = _save(sun, rows, revision=first["draft"]["revision"], promote=True)
    assert again.status_code == 200, again.text
    records = db_session.scalars(select(RoutineRecord)).all()
    assert len(records) == 1
    assert records[0].execution == "블록으로 다리를 만들었다."


def test_지운_줄은_올릴_때_지우고_그_일과를_쓴_확정_일지를_다시_검토_대상으로_센다(db_session, sun):
    first = _save(sun, [_row(), _row(name="바깥놀이", start="11:00", end="12:20")], promote=True)
    first = first.json()
    gone, kept = first["items"][1]["id"], first["draft"]["rows"][0]
    doc = Document(
        kind="dailyLog",
        title="햇살반 보육일지",
        class_id=sun.id,
        start_date=datetime.date(2026, 11, 10),
        end_date=datetime.date(2026, 11, 10),
        status="CONFIRMED",
        origin="AI",
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(
        DocumentSource(
            document_id=doc.id,
            source_kind="routine",
            source_id=gone,
            class_id=sun.id,
            date=datetime.date(2026, 11, 10),
            text="[바깥놀이 11:00~12:20] 블록으로 길을 만들었다.",
        )
    )
    db_session.flush()

    res = _save(sun, [kept], revision=first["draft"]["revision"], removed=[gone], promote=True)
    assert res.status_code == 200, res.text
    assert res.json()["review_impact"]["newly_stale_document_ids"] == [doc.id]
    assert res.json()["draft"]["removed"] == []
    assert db_session.get(RoutineRecord, gone) is None


def test_교사가_안_고친_초는_올려도_그대로다(db_session, sun):
    record = RoutineRecord(
        class_id=sun.id,
        date=datetime.date(2026, 11, 10),
        position=0,
        start_time=datetime.time(9, 16, 25),
        end_time=datetime.time(10, 40),
        name="오전 실내놀이",
        execution="블록",
    )
    db_session.add(record)
    db_session.flush()
    res = _save(sun, [_row(id=record.id, start="09:16", execution="블록 셋")], promote=True)
    assert res.status_code == 200, res.text
    db_session.refresh(record)
    assert record.start_time == datetime.time(9, 16, 25)
    assert record.execution == "블록 셋"


@pytest.mark.parametrize(
    ("row", "field"),
    [
        (_row(name="  "), "rows.0.name"),
        (_row(start="11:00", end="10:00"), "rows.0.end"),
    ],
)
def test_올릴_수_없는_줄이면_아무것도_바꾸지_않고_422(db_session, sun, row, field):
    res = _save(sun, [row], promote=True)
    assert res.status_code == 422
    assert res.json()["error"]["fields"] == [field]
    assert db_session.scalars(select(RoutineRecord)).all() == []
    assert db_session.scalars(select(RoutineDraft)).all() == []


def test_올리지_않는_임시본은_이름이_비어도_저장한다(sun):
    assert _save(sun, [_row(name="")]).status_code == 200


def test_남의_원_반은_404(db_session, sun, teacher):
    other = Center(name="남의원", director_name="박", region_sido="강원", region_sigungu="춘천시")
    db_session.add(other)
    db_session.flush()
    theirs = Class(
        center_id=other.id, name="남반", school_year=2026, age_min=4, age_max=4, teacher_name="박"
    )
    db_session.add(theirs)
    db_session.flush()
    assert _save(theirs, [_row()]).status_code == 404


def test_정리는_올라간_뒤_30일_지난_임시본만_지운다(db_session, sun):
    now = datetime.datetime(2026, 12, 20, tzinfo=datetime.UTC)
    old = now - datetime.timedelta(days=31)
    db_session.add_all(
        [
            # 올라간 지 31일 — 지운다.
            RoutineDraft(
                class_id=sun.id,
                date=datetime.date(2026, 11, 1),
                rows=[],
                promoted=True,
                promoted_at=old,
            ),
            # 올라간 지 29일 — 남긴다.
            RoutineDraft(
                class_id=sun.id,
                date=datetime.date(2026, 11, 2),
                rows=[],
                promoted=True,
                promoted_at=now - datetime.timedelta(days=29),
            ),
            # 올라가지 않았다 — 오래돼도 남긴다.
            RoutineDraft(
                class_id=sun.id,
                date=datetime.date(2026, 10, 1),
                rows=[],
                promoted=False,
                promoted_at=old,
            ),
        ]
    )
    db_session.flush()
    assert prune_drafts(db_session, now) == 1
    left = sorted(d.date.day for d in db_session.scalars(select(RoutineDraft)))
    assert left == [1, 2]


# ── 반 기본 일과표 · 새 날 깔기 ──────────────────────────────────────────────


def _template(klass, rows):
    return client.put("/api/routines/template", json={"class_id": klass.id, "rows": rows})


def _record(session, klass, day, name, start, end):
    session.add(
        RoutineRecord(
            class_id=klass.id,
            date=datetime.date.fromisoformat(day),
            position=0,
            start_time=datetime.time.fromisoformat(start),
            end_time=datetime.time.fromisoformat(end),
            name=name,
            execution="",
        )
    )
    session.flush()


def test_기본_일과표는_고정_줄과_그_요일에_더할_줄로_새_날을_깐다(sun):
    res = _template(
        sun,
        [
            {"name": "등원 및 통합보육", "start": "07:30", "end": "09:00"},
            {"name": "오전 실내놀이", "start": "09:20", "end": "10:40"},
            # 월요일(0)에만 더하는 특별활동. 시간 순서로 끼어 들어간다.
            {"name": "특별활동(체육)", "start": "09:00", "end": "09:20", "weekday": 0},
            {"name": "특별활동(음악)", "start": "09:00", "end": "09:20", "weekday": 2},
        ],
    )
    assert res.status_code == 200, res.text
    assert client.get(f"/api/routines/template?class_id={sun.id}").json()["rows"][2]["weekday"] == 0

    monday = _day(sun, "2026-11-09")["preset"]
    assert monday["source"] == "template"
    assert [r["name"] for r in monday["rows"]] == [
        "등원 및 통합보육",
        "특별활동(체육)",
        "오전 실내놀이",
    ]
    tuesday = _day(sun, "2026-11-10")["preset"]
    assert [r["name"] for r in tuesday["rows"]] == ["등원 및 통합보육", "오전 실내놀이"]


def test_기본_일과표가_없으면_지난주_같은_요일_그것도_없으면_가장_최근_기록일(db_session, sun):
    _record(db_session, sun, "2026-11-03", "지난주 화요일", "09:00", "10:00")
    _record(db_session, sun, "2026-11-06", "지난 금요일", "09:00", "10:00")
    tuesday = _day(sun, "2026-11-10")["preset"]
    assert tuesday["source"] == "last_week"
    assert tuesday["from_date"] == "2026-11-03"
    assert [r["name"] for r in tuesday["rows"]] == ["지난주 화요일"]

    wednesday = _day(sun, "2026-11-11")["preset"]
    assert wednesday["source"] == "recent"
    assert wednesday["from_date"] == "2026-11-06"


def test_그날_적은_줄이_있거나_아무것도_없으면_깔_것이_없다(db_session, sun):
    assert _day(sun)["preset"] is None
    _record(db_session, sun, DAY, "오늘", "09:00", "10:00")
    assert _day(sun)["preset"] is None


def test_기본_일과표는_이름이_비거나_시간이_거꾸로면_422(sun):
    assert _template(sun, [{"name": " ", "start": None, "end": None}]).status_code == 422
    assert _template(sun, [{"name": "a", "start": "10:00", "end": "09:00"}]).status_code == 422
    assert _template(sun, [{"name": "a", "weekday": 7}]).status_code == 422


def test_반영과_맞다고_한_활동은_올릴_때_일과_기록에_따라간다(db_session, sun):
    """둘 다 사실 칸이 아니다 — 종이에서만 쓰는 표시다 (ADR-086)."""
    row = _row(reflected=True, activities=["낙엽 모자이크"])
    items = _save(sun, [row], promote=True).json()["items"]
    assert items[0]["reflected"] is True
    assert items[0]["activities"] == ["낙엽 모자이크"]
    record = db_session.get(RoutineRecord, items[0]["id"])
    assert record.fact_text() == "[오전 실내놀이 09:20~10:40] 블록으로 길을 만들었다."
