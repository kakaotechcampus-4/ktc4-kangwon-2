"""관찰 기록 API 를 진짜 Postgres 로 확인한다 (docs/api-spec.md §10).

`db_session` 을 받는 테스트는 끝나면 전부 롤백된다(`conftest.py`).
아동 이름은 가명이다 — 개발 DB 에 실제 아동 실명을 넣지 않는다 (CLAUDE.md 개인정보).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document, DocumentSource
from app.features.observations import assist
from app.features.observations.models import Observation
from app.main import app
from app.shared.llm import LlmFailed

client = TestClient(app)


def _center(session, name: str) -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _class(session, center: Center, name: str) -> Class:
    classroom = Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    session.add(classroom)
    session.flush()
    return classroom


def _child(session, classroom: Class, name: str, code: str) -> Child:
    child = Child(class_id=classroom.id, name=name, code=code)
    session.add(child)
    session.flush()
    return child


@pytest.fixture
def mine(db_session, teacher):
    """로그인한 교사의 원 · 반 둘 · 아이 둘."""
    center = _center(db_session, "쓱싹 어린이집")
    teacher.center_id = center.id
    sun = _class(db_session, center, "햇살반")
    moon = _class(db_session, center, "달님반")
    return {
        "sun": sun,
        "moon": moon,
        "seojun": _child(db_session, sun, "가서준", "민준"),
        "haeun": _child(db_session, moon, "나하은", "지안"),
    }


def _post(classroom, child, **overrides):
    body = {
        "class_id": classroom.id,
        "child_id": child.id,
        "date": "2026-09-22",
        "domain": "자연탐구",
        "context": "바깥놀이",
        "fact": "화단 앞에 앉아 개미가 줄지어 가는 것을 3분 동안 바라보았다.",
        **overrides,
    }
    return client.post("/api/observations", json=body)


def test_기록을_넣으면_행이_남고_반_아이_이름과_코드가_같이_온다(db_session, mine):
    response = _post(mine["sun"], mine["seojun"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["class_name"], body["child_name"], body["child_code"]) == (
        "햇살반",
        "가서준",
        "민준",
    )
    row = db_session.get(Observation, body["id"])
    assert row.fact == body["fact"]
    assert row.domain == "자연탐구"


def test_상황을_안_적으면_null_이_아니라_빈_문자열이다(db_session, mine):
    """PR #42 리뷰에서 물은 것. `expire_on_commit=False` 여도 None 이 나가지 않는다 —
    SQLAlchemy 2.0 이 Postgres 에서 INSERT … RETURNING 으로 server_default 를 받아온다.
    그 동작에 기대는 것을 여기서 고정한다."""
    body = {"class_id": mine["sun"].id, "child_id": mine["seojun"].id, "date": "2026-09-22"}
    body |= {"domain": "의사소통", "fact": "친구에게 그림책 내용을 이야기했다."}

    response = client.post("/api/observations", json=body)

    assert response.status_code == 201, response.text
    assert response.json()["context"] == ""


def test_반_아이_날짜로_다시_꺼낸다_최신순(db_session, mine):
    _post(mine["sun"], mine["seojun"], date="2026-09-01")
    _post(mine["sun"], mine["seojun"], date="2026-09-20")
    _post(mine["sun"], mine["seojun"], date="2026-10-02")
    _post(mine["moon"], mine["haeun"], date="2026-09-10")

    def dates(**params):
        response = client.get("/api/observations", params=params)
        assert response.status_code == 200, response.text
        return [item["date"] for item in response.json()["items"]]

    assert dates() == ["2026-10-02", "2026-09-20", "2026-09-10", "2026-09-01"]
    assert dates(class_id=mine["moon"].id) == ["2026-09-10"]
    assert dates(child_id=mine["seojun"].id) == ["2026-10-02", "2026-09-20", "2026-09-01"]
    assert dates(**{"from": "2026-09-01", "to": "2026-09-30"}) == [
        "2026-09-20",
        "2026-09-10",
        "2026-09-01",
    ]


def test_다른_원의_기록은_안_보이고_고치지도_지우지도_못한다(db_session, mine):
    other = _center(db_session, "다른 어린이집")
    their_class = _class(db_session, other, "별님반")
    their_child = _child(db_session, their_class, "다도윤", "서윤")
    theirs = Observation(
        class_id=their_class.id,
        child_id=their_child.id,
        date="2026-09-22",
        domain="사회관계",
        fact="x",
    )
    db_session.add(theirs)
    db_session.flush()

    assert client.get("/api/observations").json() == {"items": []}
    update = {"date": "2026-09-22", "domain": "사회관계", "fact": "y"}
    assert client.put(f"/api/observations/{theirs.id}", json=update).status_code == 404
    assert client.delete(f"/api/observations/{theirs.id}").status_code == 404
    # 남의 반에 쓰는 것도 막는다.
    assert _post(their_class, their_child).status_code == 404


def test_그_반의_아이가_아니면_422(db_session, mine):
    response = _post(mine["sun"], mine["haeun"])

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["child_id"]


def test_사실이_공백뿐이거나_5영역_밖이면_422_를_한꺼번에(db_session, mine):
    response = _post(mine["sun"], mine["seojun"], fact="   ", domain="수학")

    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"fact", "domain"}


def test_사실은_5000자까지만_받는다(db_session, mine):
    # 화면 입력칸과 같은 상한이다. 이 글이 그대로 일지 초안 LLM 으로 간다.
    assert _post(mine["sun"], mine["seojun"], fact="가" * 5000).status_code == 201
    too_long = _post(mine["sun"], mine["seojun"], fact="가" * 5001)
    assert too_long.status_code == 422
    assert too_long.json()["error"]["fields"] == ["fact"]

    created = _post(mine["sun"], mine["seojun"]).json()
    update = {"date": "2026-09-23", "domain": "자연탐구", "context": "", "fact": "가" * 5001}
    response = client.put(f"/api/observations/{created['id']}", json=update)
    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["fact"]


def test_고치면_네_칸만_바뀌고_대상은_못_바꾼다(db_session, mine):
    created = _post(mine["sun"], mine["seojun"]).json()
    update = {
        "date": "2026-09-23",
        "domain": "예술경험",
        "context": "",
        "fact": "블록으로 탑을 쌓았다.",
    }

    response = client.put(f"/api/observations/{created['id']}", json=update)

    assert response.status_code == 200, response.text
    assert {k: response.json()[k] for k in update} == update
    moved = client.put(f"/api/observations/{created['id']}", json={**update, "child_id": 1})
    assert moved.status_code == 422


def test_지우면_204_이고_목록에서_사라진다(db_session, mine):
    created = _post(mine["sun"], mine["seojun"]).json()

    assert client.delete(f"/api/observations/{created['id']}").status_code == 204
    assert client.get("/api/observations").json() == {"items": []}
    assert client.delete(f"/api/observations/{created['id']}").status_code == 404


def test_DB_가_5영역_밖의_값을_직접_막는다(db_session, mine):
    """라우터를 안 지나는 INSERT(스크립트·수동)도 CHECK 가 막는다."""
    db_session.add(
        Observation(
            class_id=mine["sun"].id,
            child_id=mine["seojun"].id,
            date="2026-09-22",
            domain="수학",
            fact="x",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


# ── stale 전파 (docs/api-spec.md §11 「stale — 원본이 바뀌었다는 표시」) ──────────────


def _document(session, classroom, kind, sources, child=None):
    """근거 사본을 가진 문서를 DB 에 직접 넣는다. 생성 API(§11 POST)와 무관하게 전파만 본다.

    `sources` 는 (source_kind, source_id, text, date) 목록이다.
    """
    day = sources[0][3]
    doc = Document(
        kind=kind,
        title="t",
        class_id=classroom.id,
        child_id=child.id if child else None,
        start_date=day,
        end_date=day,
        origin="AI",
    )
    session.add(doc)
    session.flush()
    for source_kind, source_id, text, date in sources:
        session.add(
            DocumentSource(
                document_id=doc.id,
                source_kind=source_kind,
                source_id=source_id,
                class_id=classroom.id,
                child_id=child.id if child else None,
                date=date,
                text=text,
            )
        )
    session.flush()
    return doc


@pytest.fixture
def chain(db_session, mine):
    """기록 → 일일 보육일지 → 주간 보육일지. 그리고 이 기록을 안 쓴 일지 하나."""
    record = _post(mine["sun"], mine["seojun"]).json()
    other = _post(mine["sun"], mine["seojun"], fact="블록 세 개를 쌓았다.").json()
    day = record["date"]
    daily = _document(
        db_session, mine["sun"], "dailyLog", [("observation", record["id"], record["fact"], day)]
    )
    weekly = _document(
        db_session, mine["sun"], "weeklyLog", [("document", daily.id, record["fact"], day)]
    )
    unrelated = _document(
        db_session, mine["sun"], "dailyLog", [("observation", other["id"], other["fact"], day)]
    )
    return {"record": record, "docs": (daily, weekly, unrelated)}


def _stale(db_session, docs):
    for doc in docs:
        db_session.refresh(doc)
    return [doc.stale for doc in docs]


def test_사실을_고치면_그_기록을_쓴_일지와_그_일지를_쓴_주간_일지가_stale(db_session, chain):
    record = chain["record"]
    update = {
        "date": record["date"],
        "domain": record["domain"],
        "context": "",
        "fact": "5분 동안 바라보았다.",
    }

    assert client.put(f"/api/observations/{record['id']}", json=update).status_code == 200

    assert _stale(db_session, chain["docs"]) == [True, True, False]


def test_날짜만_고쳐도_stale(db_session, chain):
    record = chain["record"]
    update = {"date": "2026-09-23", "domain": record["domain"], "fact": record["fact"]}

    client.put(f"/api/observations/{record['id']}", json=update)

    assert _stale(db_session, chain["docs"]) == [True, True, False]


def _snapshot(db_session, doc, record):
    """만들 때 영역 · 상황을 찍은 사본으로 만든다 — 지금 생성 API 가 남기는 모양 (ADR-088)."""
    for copy in db_session.query(DocumentSource).filter_by(document_id=doc.id):
        copy.domain, copy.context = record["domain"], record["context"]
    db_session.flush()


def _keep(record, **changes):
    return {k: record[k] for k in ("date", "domain", "context", "fact")} | changes


# ADR-088 전에는 「영역 · 상황만 고치면 사실이 그대로라 stale 이 아니다」였다. 그런데 종이의 영역
# 행이 원본을 따라 바뀌어, 옛 영역의 누리과정으로 쓴 배움 칸이 다른 행 아래로 나갔다.
@pytest.mark.parametrize(
    "changes", [{"domain": "의사소통"}, {"context": "실내"}], ids=["domain", "context"]
)
def test_영역이나_상황만_고쳐도_stale(db_session, chain, changes):
    record = chain["record"]
    _snapshot(db_session, chain["docs"][0], record)

    assert client.put(f"/api/observations/{record['id']}", json=_keep(record, **changes)).is_success

    assert _stale(db_session, chain["docs"]) == [True, True, False]


def test_사본_그대로_다시_저장하면_stale_이_아니다(db_session, chain):
    record = chain["record"]
    _snapshot(db_session, chain["docs"][0], record)

    assert client.put(f"/api/observations/{record['id']}", json=_keep(record)).is_success

    assert _stale(db_session, chain["docs"]) == [False, False, False]


def test_영역_사본이_없는_옛_문서는_원본_영역이_바뀔_때만_stale(db_session, chain):
    """채우기 규칙이 못 채운 사본(「다시 확인」)은 종이가 지금 원본 영역을 따른다.

    상황은 옛 종이에 쓰이지 않았다.
    그대로 다시 저장해도 stale 이 되면 교사가 손대지 않은 문서가 걸린다.
    """
    record = chain["record"]
    url = f"/api/observations/{record['id']}"

    assert client.put(url, json=_keep(record, context="실내")).is_success
    assert _stale(db_session, chain["docs"]) == [False, False, False]

    assert client.put(url, json=_keep(record, domain="의사소통")).is_success
    assert _stale(db_session, chain["docs"]) == [True, True, False]


def test_지우면_원본_없음이라_stale(db_session, chain):
    assert client.delete(f"/api/observations/{chain['record']['id']}").status_code == 204

    assert _stale(db_session, chain["docs"]) == [True, True, False]


# ── 고치거나 지운 뒤 「N건 다시 검토」 안내 (api-spec §10 「저장 뒤 재검토 안내」) ─────────


@pytest.fixture
def journals(db_session, mine):
    """한 기록을 쓴 관찰일지 셋 — 확정 · 이미 stale 인 확정 · 초안. 그리고 확정본을 쓴 문서 하나."""
    record = _post(mine["sun"], mine["seojun"]).json()
    rows = [("observation", record["id"], record["fact"], record["date"])]
    fresh = _document(db_session, mine["sun"], "observation", rows, mine["seojun"])
    old = _document(db_session, mine["sun"], "observation", rows, mine["seojun"])
    draft = _document(db_session, mine["sun"], "observation", rows, mine["seojun"])
    fresh.status = old.status = "CONFIRMED"
    old.stale = True
    chained = _document(
        db_session,
        mine["sun"],
        "assessment",
        [("document", fresh.id, record["fact"], record["date"])],
        mine["seojun"],
    )
    db_session.flush()
    return {"record": record, "fresh": fresh, "old": old, "draft": draft, "chained": chained}


def test_고치면_직접_쓴_확정_일지만_영향으로_센다(db_session, journals):
    record = journals["record"]
    url = f"/api/observations/{record['id']}?include_impact=true"

    response = client.put(url, json=_keep(record, fact="5분 동안 바라보았다."))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fact"] == "5분 동안 바라보았다."
    assert body["review_impact"] == {
        "affected_document_ids": sorted([journals["fresh"].id, journals["old"].id]),
        "newly_stale_document_ids": [journals["fresh"].id],
    }
    # 초안과 연쇄로 따라간 문서도 stale 이 되지만 안내 건수에는 없다(일과 기록과 같은 규칙).
    assert _stale(db_session, [journals["draft"], journals["chained"]]) == [True, True]


def test_사본과_같으면_영향이_비고_옵션이_없으면_예전_응답이다(db_session, journals):
    record = journals["record"]
    url = f"/api/observations/{record['id']}"

    same = client.put(url + "?include_impact=true", json=_keep(record))
    plain = client.put(url, json=_keep(record, fact="바뀐 글"))

    assert same.json()["review_impact"] == {
        "affected_document_ids": [],
        "newly_stale_document_ids": [],
    }
    assert "review_impact" not in plain.json()


def test_지우면_영향만_담은_200_이고_옵션이_없으면_204(db_session, journals, mine):
    record = journals["record"]
    other = _post(mine["sun"], mine["seojun"]).json()

    response = client.delete(f"/api/observations/{record['id']}?include_impact=true")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "review_impact": {
            "affected_document_ids": sorted([journals["fresh"].id, journals["old"].id]),
            "newly_stale_document_ids": [journals["fresh"].id],
        }
    }
    assert client.delete(f"/api/observations/{other['id']}").status_code == 204


# ── jev 도움 — 영역 추천 · 빠진 것 쪽지 (ADR-082) ───────────────────────────────────
# 실제 호출은 하지 않는다. CI 는 mock 이고, real 은 가짜 decide 로 흉내 낸다.

SUGGEST = "/api/observations/domain-suggest"


@pytest.fixture
def jev(monkeypatch):
    """real 모드 흉내. `answer` 에 돌려줄 답을 넣고, 보낸 state · questions 를 `sent` 에 모은다."""
    box = {"sent": [], "answer": {}}

    def fake(state, questions):
        box["sent"].append((state, questions))
        if isinstance(box["answer"], Exception):
            raise box["answer"]
        return box["answer"]

    monkeypatch.setattr(assist, "is_mock", lambda: False)
    monkeypatch.setattr(assist, "decide", fake)
    return box


def _domain_answer(choice, p):
    rest = (1 - p) / 4
    probs = {d: (p if d == choice else rest) for d in assist.NURI_DOMAINS}
    return {"영역": {"choice": choice, "probabilities": probs}}


def _suggest(mine, fact="블록 세 개를 쌓고 친구에게 같이 만들자고 말했다.", context=""):
    return client.post(SUGGEST, json={"class_id": mine["sun"].id, "fact": fact, "context": context})


def test_추천은_mock_이면_부르지_않고_비어_있다(db_session, mine):
    response = _suggest(mine)

    assert response.status_code == 200, response.text
    assert response.json() == {"domain": None, "confidence": None}


def test_추천은_확신이_0_8_이상일_때만_영역을_준다(db_session, mine, jev):
    jev["answer"] = _domain_answer("사회관계", 0.86)
    assert _suggest(mine).json() == {"domain": "사회관계", "confidence": 0.86}

    jev["answer"] = _domain_answer("의사소통", 0.79)
    assert _suggest(mine).json() == {"domain": None, "confidence": 0.79}


def test_추천은_아이_이름을_가명으로_바꿔_보낸다(db_session, mine, jev):
    jev["answer"] = _domain_answer("사회관계", 0.9)

    _suggest(mine, fact="가서준이 나하은에게 블록을 건넸다.", context="서준이 자리")

    sent = repr(jev["sent"])
    for real in ("가서준", "서준", "나하은", "하은"):
        assert real not in sent


def test_추천은_2축_원이면_부르지_않는다(db_session, mine, jev, teacher):
    db_session.get(Center, teacher.center_id).observation_axis = "DAILY_PLAY_2"
    db_session.flush()

    assert _suggest(mine).json() == {"domain": None, "confidence": None}
    assert jev["sent"] == []


def test_추천이_실패해도_기록은_막지_않는다(db_session, mine, jev):
    jev["answer"] = LlmFailed("x")
    assert _suggest(mine).json() == {"domain": None, "confidence": None}

    jev["answer"] = {"영역": {"choice": "수학", "probabilities": {}}}
    assert _suggest(mine).json() == {"domain": None, "confidence": None}


def test_추천은_남의_반이면_404_빈_사실이면_422(db_session, mine):
    other = _class(db_session, _center(db_session, "다른 어린이집"), "별님반")

    assert client.post(SUGGEST, json={"class_id": other.id, "fact": "x"}).status_code == 404
    assert _suggest(mine, fact="   ").status_code == 422


def _missing(record_id):
    return client.post(f"/api/observations/{record_id}/missing")


def test_빠진_것은_mock_이면_묻지_않는다(db_session, mine):
    record = _post(mine["sun"], mine["seojun"]).json()

    response = _missing(record["id"])

    assert response.status_code == 200, response.text
    assert response.json() == {"missing": []}


def test_빠진_것은_상황_행동_반응_순서로_알린다(db_session, mine, jev):
    record = _post(mine["sun"], mine["seojun"], context="", fact="가서준이 블록 세 개를 쌓았다.")
    jev["answer"] = {"상황": {"noul": 0.2}, "행동": {"noul": 0.95}, "반응": {"noul": 0.1}}

    assert _missing(record.json()["id"]).json() == {"missing": ["상황", "반응"]}
    assert "가서준" not in repr(jev["sent"])


def test_상황_칸을_적었으면_상황은_묻지_않는다(db_session, mine, jev):
    record = _post(mine["sun"], mine["seojun"], context="실내놀이, 쌓기").json()
    jev["answer"] = {"행동": {"noul": 0.9}, "반응": {"noul": 0.9}}

    assert _missing(record["id"]).json() == {"missing": []}
    assert set(jev["sent"][0][1]) == {"행동", "반응"}


def test_빠진_것을_못_물으면_조용히_비운다(db_session, mine, jev):
    record = _post(mine["sun"], mine["seojun"]).json()
    jev["answer"] = {"행동": {"noul": "?"}}

    assert _missing(record["id"]).json() == {"missing": []}
    assert _missing(999999).status_code == 404
