"""일과 기록(§10-1)과, 그것을 근거로 쓰는 일일 보육일지(§11) 통합 테스트. 실제 DB 를 쓴다."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document, DocumentSource
from app.features.observations.models import Observation
from app.features.routines.models import RoutineRecord
from app.main import app

client = TestClient(app)
LONG = "스무 글자가 넘도록 채운 문장입니다 정말로요"
CHECKS = {"fact": True, "interpretation": True, "support": True}
DAY = "2026-09-22"


@pytest.fixture
def mine(db_session, teacher):
    center = Center(
        name="테스트어린이집", director_name="김원장", region_sido="강원", region_sigungu="춘천시"
    )
    db_session.add(center)
    db_session.flush()
    sun = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김",
    )
    moon = Class(
        center_id=center.id,
        name="달님반",
        school_year=2026,
        age_min=5,
        age_max=5,
        teacher_name="이",
    )
    db_session.add_all([sun, moon])
    db_session.flush()
    teacher.center_id = center.id
    return {"center": center, "sun": sun, "moon": moon}


def _routine(klass, **kw):
    body = {
        "class_id": klass.id,
        "date": DAY,
        "position": 2,
        "start": "09:20",
        "end": "10:40",
        "name": "오전 실내놀이",
        "plan": "자동차 굴리기",
        "execution": "블록 3개로 길을 만들었다.",
        **kw,
    }
    return client.post("/api/routines", json=body)


def _update_body(record, **kw):
    keys = ("date", "position", "start", "end", "name", "plan", "execution")
    return {**{k: record[k] for k in keys}, **kw}


def _daily(klass, routines, **kw):
    body = {
        "kind": "dailyLog",
        "class_id": klass.id,
        "start": DAY,
        "end": DAY,
        "source_ids": [r["id"] for r in routines],
        **kw,
    }
    return client.post("/api/documents", json=body)


def _facts(doc):
    return {s["heading"]: s["body"] for s in doc["sections"]}["사실"]


# ── 일과 기록 저장 · 조회 ──────────────────────────────────────────────────
def test_저장하고_반_이름까지_같이_돌려준다(mine):
    response = _routine(mine["sun"])

    assert response.status_code == 201
    record = response.json()
    assert record["class_name"] == "햇살반"
    assert (record["start"], record["end"]) == ("09:20:00", "10:40:00")
    assert (record["name"], record["plan"]) == ("오전 실내놀이", "자동차 굴리기")


def test_행_수는_자유이고_종이의_행_순서로_나온다(mine):
    # 같은 날 행을 몇 개든 넣을 수 있다. position · 시작 시간 · id 순이다.
    _routine(mine["sun"], position=5, start=None, end=None, name="특별활동(체육)")
    _routine(mine["sun"], position=1, start="08:00", end="09:00", name="등원 및 통합보육")
    _routine(mine["sun"], position=1, start="07:30", end="08:00", name="조기 등원")
    _routine(mine["sun"], date="2026-09-21", position=9, name="전날 일과")

    items = client.get(f"/api/routines?class_id={mine['sun'].id}").json()["items"]

    assert [i["name"] for i in items] == [
        "전날 일과",
        "조기 등원",
        "등원 및 통합보육",
        "특별활동(체육)",
    ]


def test_반과_기간으로_거른다(mine):
    _routine(mine["sun"])
    _routine(mine["moon"])
    _routine(mine["sun"], date="2026-09-30")

    items = client.get(f"/api/routines?class_id={mine['sun'].id}&from={DAY}&to={DAY}").json()[
        "items"
    ]

    assert len(items) == 1 and items[0]["class_id"] == mine["sun"].id


@pytest.mark.parametrize(
    "kw",
    [
        {"name": "   "},
        {"name": "x" * 51},
        {"start": "10:40", "end": "09:20"},
        {"position": -1},
        {"execution": "x" * 5001},
        {"child_id": 1},
    ],
    ids=["blank_name", "long_name", "time_range", "negative_position", "too_long", "extra"],
)
def test_틀린_입력은_422(mine, kw):
    assert _routine(mine["sun"], **kw).status_code == 422


def test_남의_원_반에는_못_쓰고_남의_원_기록은_안_보인다(db_session, mine, teacher):
    record = _routine(mine["sun"]).json()
    other = Center(name="남의원", director_name="박", region_sido="강원", region_sigungu="원주시")
    db_session.add(other)
    db_session.flush()
    teacher.center_id = other.id

    assert _routine(mine["sun"]).status_code == 404
    assert client.get("/api/routines").json()["items"] == []
    body = _update_body(record)
    assert client.put(f"/api/routines/{record['id']}", json=body).status_code == 404
    assert client.delete(f"/api/routines/{record['id']}").status_code == 404


def test_수정은_반을_못_바꾼다(mine):
    record = _routine(mine["sun"]).json()
    body = _update_body(record, class_id=mine["moon"].id)

    assert client.put(f"/api/routines/{record['id']}", json=body).status_code == 422


# ── 일일 보육일지는 일과 기록을 근거로 쓴다 ───────────────────────────────────
def test_일일_보육일지의_사실은_일과_기록을_고른_순서로_잇는다(mine):
    indoor = _routine(mine["sun"]).json()
    lunch = _routine(
        mine["sun"],
        position=5,
        start="12:20",
        end="13:20",
        name="점심식사",
        execution="골고루 먹음",
    ).json()

    response = _daily(mine["sun"], [indoor, lunch])

    assert response.status_code == 201
    doc = response.json()
    assert _facts(doc) == (
        "[오전 실내놀이 09:20~10:40] 블록 3개로 길을 만들었다."
        "\n\n[점심식사 12:20~13:20] 골고루 먹음"
    )
    assert [s["id"] for s in doc["sources"]] == [indoor["id"], lunch["id"]]
    assert doc["child_id"] is None


def test_시간이_없는_일과도_사실이_된다(mine):
    record = _routine(mine["sun"], start=None, end=None, name="특별활동").json()

    doc = _daily(mine["sun"], [record]).json()

    assert _facts(doc) == "[특별활동] 블록 3개로 길을 만들었다."


@pytest.mark.parametrize(
    "case",
    ["other_day", "other_class", "empty_execution", "observation_id", "missing"],
)
def test_근거로_못_쓰는_일과는_어느_것인지_알려준다(db_session, mine, case):
    good = _routine(mine["sun"]).json()
    if case == "other_day":
        bad = _routine(mine["sun"], date="2026-09-23").json()["id"]
    elif case == "other_class":
        bad = _routine(mine["moon"]).json()["id"]
    elif case == "empty_execution":
        bad = _routine(mine["sun"], execution="   ").json()["id"]
    elif case == "observation_id":
        # 관찰 기록은 더 이상 일일 보육일지의 근거가 아니다 (§11 · ADR-024).
        child = Child(class_id=mine["sun"].id, name="이가명", code="도담")
        db_session.add(child)
        db_session.flush()
        obs = Observation(
            class_id=mine["sun"].id,
            child_id=child.id,
            date=good["date"],
            domain="자연탐구",
            fact="개미를 보았다.",
        )
        db_session.add(obs)
        db_session.flush()
        # 관찰 기록 id 가 우연히 일과 기록 id 와 겹치지 않게 큰 수를 쓴다.
        bad = obs.id + 10_000
    else:
        bad = 999_999

    response = _daily(mine["sun"], [good, {"id": bad}])

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [f"sources.{bad}"]


def test_일일_보육일지는_아이를_받지_않는다(db_session, mine):
    child = Child(class_id=mine["sun"].id, name="이가명", code="도담")
    db_session.add(child)
    db_session.flush()
    record = _routine(mine["sun"]).json()

    response = _daily(mine["sun"], [record], child_id=child.id)

    assert response.status_code == 422
    assert "child_id" in response.json()["error"]["fields"]


def test_확정까지_가고_주간_보육일지의_근거가_된다(mine):
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()

    confirmed = client.post(f"/api/documents/{doc['id']}/confirm", json={"checks": CHECKS})
    weekly = client.post(
        "/api/documents",
        json={
            "kind": "weeklyLog",
            "class_id": mine["sun"].id,
            "start": "2026-09-21",
            "end": "2026-09-27",
            "source_ids": [doc["id"]],
        },
    )

    assert confirmed.status_code == 200
    assert weekly.status_code == 201
    assert weekly.json()["sources"][0]["text"] == _facts(doc)


# ── 일과 기록을 고치면 그걸 쓴 일지가 stale ──────────────────────────────────
def _stale(db_session, doc_id):
    db_session.expire_all()
    return db_session.get(Document, doc_id).stale


@pytest.mark.parametrize(
    "edit",
    [
        {"execution": "블록 5개로 길을 만들었다."},
        {"name": "실내 자유놀이"},
        {"start": "09:00"},
        {"date": "2026-09-23"},
    ],
    ids=["execution", "name", "time", "date"],
)
def test_사실에_들어가는_칸을_고치면_stale(db_session, mine, edit):
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()

    response = client.put(f"/api/routines/{record['id']}", json=_update_body(record, **edit))

    assert response.status_code == 200
    assert _stale(db_session, doc["id"]) is True


def test_활동계획이나_순서만_고치면_사실이_그대로라_stale_이_아니다(db_session, mine):
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()
    body = _update_body(record, plan="다른 계획", position=7)

    client.put(f"/api/routines/{record['id']}", json=body)

    assert _stale(db_session, doc["id"]) is False


def test_id_가_같은_관찰_기록을_쓴_문서는_건드리지_않는다(db_session, mine):
    # 근거 id 는 테이블마다 1 부터 센다. 종류를 안 보면 일과 기록 N 을 고쳤는데
    # 관찰 기록 N 을 쓴 관찰일지까지 stale 이 된다.
    import datetime

    record = _routine(mine["sun"]).json()
    child = Child(class_id=mine["sun"].id, name="이가명", code="도담")
    db_session.add(child)
    db_session.flush()
    day = datetime.date(2026, 9, 22)
    obs_doc = Document(
        kind="observation",
        title="t",
        class_id=mine["sun"].id,
        child_id=child.id,
        start_date=day,
        end_date=day,
        status="DRAFT",
        origin="AI",
        stale=False,
        review_note="",
    )
    db_session.add(obs_doc)
    db_session.flush()
    db_session.add(
        DocumentSource(
            document_id=obs_doc.id,
            source_kind="observation",
            source_id=record["id"],
            class_id=mine["sun"].id,
            child_id=child.id,
            date=day,
            text="다른 사실",
        )
    )
    db_session.flush()

    body = _update_body(record, execution="블록 5개로 길을 만들었다.")
    client.put(f"/api/routines/{record['id']}", json=body)

    assert _stale(db_session, obs_doc.id) is False


def test_지우면_원본_없음이라_stale(db_session, mine):
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()

    assert client.delete(f"/api/routines/{record['id']}").status_code == 204

    assert _stale(db_session, doc["id"]) is True


def test_refresh_는_고친_일과로_사실을_다시_잇고_stale_을_푼다(db_session, mine):
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()
    body = _update_body(record, execution="블록 5개로 길을 만들었다.")
    client.put(f"/api/routines/{record['id']}", json=body)

    refreshed = client.post(f"/api/documents/{doc['id']}/refresh")

    assert refreshed.status_code == 200
    assert refreshed.json()["stale"] is False
    assert _facts(refreshed.json()) == "[오전 실내놀이 09:20~10:40] 블록 5개로 길을 만들었다."


def test_다른_날로_옮긴_일과는_refresh_가_거절한다(db_session, mine):
    # 만들 때 다른 날 일과를 막는 것과 같은 규칙이다. 안 막으면 9/22 일지에 9/23 사실이 들어간다.
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()
    client.put(f"/api/routines/{record['id']}", json=_update_body(record, date="2026-09-23"))

    response = client.post(f"/api/documents/{doc['id']}/refresh")

    assert response.status_code == 409
    assert response.json()["error"]["fields"] == [f"sources.{record['id']}"]


def test_끝_시간만_있어도_사실에_시간이_들어가고_고치면_stale(db_session, mine):
    record = _routine(mine["sun"], start=None, end="10:40").json()
    doc = _daily(mine["sun"], [record]).json()
    assert _facts(doc) == "[오전 실내놀이 ~10:40] 블록 3개로 길을 만들었다."

    client.put(f"/api/routines/{record['id']}", json=_update_body(record, end="11:00"))

    assert _stale(db_session, doc["id"]) is True


def test_활동실행을_비웠으면_refresh_가_거절한다(db_session, mine):
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()
    client.put(f"/api/routines/{record['id']}", json=_update_body(record, execution=""))

    response = client.post(f"/api/documents/{doc['id']}/refresh")

    assert response.status_code == 409
    assert response.json()["error"]["fields"] == [f"sources.{record['id']}"]


# ── DB 가 직접 막는 것 ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "kw",
    [{"name": "  "}, {"position": -1}],
    ids=["name_not_blank", "position_not_negative"],
)
def test_DB_가_잘못된_일과를_직접_막는다(db_session, mine, kw):
    import datetime

    db_session.add(
        RoutineRecord(
            class_id=mine["sun"].id,
            date=datetime.date(2026, 9, 22),
            **{"name": "오전 실내놀이", "position": 0, **kw},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_DB_가_모르는_근거_종류를_막는다(db_session, mine):
    record = _routine(mine["sun"]).json()
    doc = _daily(mine["sun"], [record]).json()
    db_session.add(
        DocumentSource(
            document_id=doc["id"],
            source_kind="photo",
            source_id=1,
            class_id=mine["sun"].id,
            text="x",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
