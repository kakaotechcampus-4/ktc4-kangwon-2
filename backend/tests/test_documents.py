"""documents 스키마·GET /api/documents 통합 테스트. 실제 DB 를 쓴다."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.features.observations.models import Observation
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _logged_in(db_session, teacher):
    """로그인한 교사를 세션에 매달아 둔다.

    문서 조회가 교사의 원으로 걸린다(§11). 원을 안 붙이면 아무것도 안 보인다.
    원은 각 테스트가 아래 헬퍼로 만드는데, 그 안에서 교사에게 붙이려면 교사를
    가져올 길이 필요하다. 호출부 열다섯 곳에 인자를 더하는 대신 여기 매단다.
    """
    db_session.info["teacher"] = teacher


def _make_center_class_child(session):
    center = Center(
        name="테스트어린이집",
        director_name="김원장",
        region_sido="충청북도",
        region_sigungu="충주시",
    )
    session.add(center)
    session.flush()
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
    )
    session.add(klass)
    session.flush()
    child = Child(class_id=klass.id, name="이가명", code="도담")
    session.add(child)
    session.flush()
    teacher = session.info.get("teacher")
    if teacher is not None:
        teacher.center_id = center.id
    return center, klass, child


def _make_sources(session, doc, klass, child, count=2):
    sources = []
    for i in range(count):
        source = DocumentSource(
            document_id=doc.id,
            source_kind="observation",
            source_id=100 + i,
            class_id=klass.id,
            child_id=child.id if child else None,
            date=date(2026, 9, 5 + i),
            text=f"관찰 기록 {i}.",
        )
        session.add(source)
        sources.append(source)
    session.flush()
    return sources


_LONG_ENOUGH = "스무 글자가 넘도록 채운 문장입니다 정말로요"


def _make_sections(session, doc, sources, interpretation=_LONG_ENOUGH, support=_LONG_ENOUGH):
    fact = "\n\n".join(s.text for s in sources)
    source_ids = [s.source_id for s in sources]
    for heading, body in [("사실", fact), ("해석", interpretation), ("지원", support)]:
        session.add(
            DocumentSection(document_id=doc.id, heading=heading, body=body, source_ids=source_ids)
        )
    session.flush()


def _make_document(session, klass, child=None, **overrides):
    kwargs = {
        "kind": "observation",
        "title": "테스트 문서",
        "class_id": klass.id,
        "child_id": child.id if child else None,
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 30),
        "status": "DRAFT",
        "origin": "AI",
        "stale": False,
        "review_note": "",
    }
    kwargs.update(overrides)
    doc = Document(**kwargs)
    session.add(doc)
    session.flush()
    return doc


# ── CHECK 제약 6개 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "bogus"},
        {"status": "bogus"},
        {"origin": "bogus"},
        {"start_date": date(2026, 9, 30), "end_date": date(2026, 9, 1)},
        {"kind": "dailyLog", "child_id": None, "end_date": date(2026, 9, 2)},
        {"kind": "observation", "child_id": None},
    ],
    ids=[
        "kind",
        "status",
        "origin",
        "date_range",
        "daily_log_single_day",
        "child_scoped_kind_requires_child",
    ],
)
def test_document_check_constraints_reject_invalid_rows(db_session, overrides):
    _, klass, child = _make_center_class_child(db_session)

    with pytest.raises(IntegrityError):
        _make_document(db_session, klass, child=child, **overrides)


def test_document_check_constraints_allow_the_valid_boundary(db_session):
    # 위 6개가 전부 "이 값은 막는다"만 확인하면, 정상 값까지 우연히 막고 있어도
    # 못 잡는다. 경계값(dailyLog 하루짜리, start==end)이 통과하는지도 같이 본다.
    _, klass, child = _make_center_class_child(db_session)

    doc = _make_document(
        db_session,
        klass,
        child=None,
        kind="dailyLog",
        start_date=date(2026, 9, 22),
        end_date=date(2026, 9, 22),
    )

    assert doc.id is not None


# ── UNIQUE(document_id, heading) ───────────────────────────────────────────
def test_document_section_heading_is_unique_per_document(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)

    db_session.add(DocumentSection(document_id=doc.id, heading="사실", body="A", source_ids=[]))
    db_session.flush()

    db_session.add(DocumentSection(document_id=doc.id, heading="사실", body="B", source_ids=[]))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ── sources_count 부속질의 ──────────────────────────────────────────────────
def test_list_documents_reports_sources_count(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc_with_sources = _make_document(db_session, klass, child=child)
    doc_without_sources = _make_document(db_session, klass, child=child, title="근거 없는 문서")

    db_session.add_all(
        [
            DocumentSource(
                document_id=doc_with_sources.id,
                source_kind="observation",
                source_id=101,
                class_id=klass.id,
                child_id=child.id,
                date=date(2026, 9, 5),
                text="개미를 관찰했다.",
            ),
            DocumentSource(
                document_id=doc_with_sources.id,
                source_kind="observation",
                source_id=102,
                class_id=klass.id,
                child_id=child.id,
                date=date(2026, 9, 6),
                text="무당벌레를 관찰했다.",
            ),
        ]
    )
    db_session.flush()

    response = client.get("/api/documents")
    assert response.status_code == 200
    counts = {item["id"]: item["sources_count"] for item in response.json()["items"]}
    assert counts[doc_with_sources.id] == 2
    assert counts[doc_without_sources.id] == 0


# ── 필터 5개 ────────────────────────────────────────────────────────────────
def test_list_documents_filters(db_session):
    center, klass1, child1 = _make_center_class_child(db_session)
    klass2 = Class(
        center_id=center.id,
        name="새싹반",
        school_year=2026,
        age_min=3,
        age_max=3,
        teacher_name="박선생",
    )
    db_session.add(klass2)
    db_session.flush()

    observation = _make_document(db_session, klass1, child=child1, kind="observation", stale=False)
    daily_log = _make_document(
        db_session,
        klass2,
        child=None,
        kind="dailyLog",
        start_date=date(2026, 9, 22),
        end_date=date(2026, 9, 22),
        status="CONFIRMED",
        stale=True,
    )

    def ids(**params):
        response = client.get("/api/documents", params=params)
        assert response.status_code == 200
        return {item["id"] for item in response.json()["items"]}

    all_ids = {observation.id, daily_log.id}
    assert ids() == all_ids
    assert ids(kind="observation") == {observation.id}
    assert ids(class_id=klass2.id) == {daily_log.id}
    assert ids(child_id=child1.id) == {observation.id}
    assert ids(status="CONFIRMED") == {daily_log.id}
    assert ids(stale=True) == {daily_log.id}


# ── 정렬 ────────────────────────────────────────────────────────────────────
def test_list_documents_orders_newest_first(db_session):
    _, klass, child = _make_center_class_child(db_session)
    older = _make_document(
        db_session, klass, child=child, created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    newer = _make_document(
        db_session, klass, child=child, created_at=datetime(2026, 9, 1, tzinfo=UTC)
    )

    response = client.get("/api/documents")
    ordered_ids = [item["id"] for item in response.json()["items"]]

    assert ordered_ids.index(newer.id) < ordered_ids.index(older.id)


def test_list_documents_breaks_same_timestamp_ties_by_id_desc(db_session):
    _, klass, child = _make_center_class_child(db_session)
    same_instant = datetime(2026, 9, 1, tzinfo=UTC)
    first = _make_document(db_session, klass, child=child, created_at=same_instant)
    second = _make_document(db_session, klass, child=child, created_at=same_instant)

    response = client.get("/api/documents")
    ordered_ids = [item["id"] for item in response.json()["items"]]

    assert ordered_ids.index(second.id) < ordered_ids.index(first.id)


# ── GET /api/documents/{id} ─────────────────────────────────────────────────
def test_get_document_returns_sections_and_sources(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)

    response = client.get(f"/api/documents/{doc.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == doc.id
    assert len(payload["sections"]) == 3
    assert len(payload["sources"]) == len(sources)


def test_get_document_missing_returns_not_found(db_session):
    response = client.get("/api/documents/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# ── PUT /api/documents/{id} ─────────────────────────────────────────────────


def _put_body(doc, **overrides):
    body = {
        "sections": [
            {"heading": "사실", "body": "고정", "source_ids": []},
            {"heading": "해석", "body": _LONG_ENOUGH, "source_ids": []},
            {"heading": "지원", "body": _LONG_ENOUGH, "source_ids": []},
        ],
        "review_note": "",
        "updated_at": doc.updated_at.isoformat(),
    }
    body.update(overrides)
    return body


def test_put_updates_review_note_and_title_and_bumps_updated_at(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)
    fact = "\n\n".join(s.text for s in sources)
    original_updated_at = doc.updated_at

    response = client.put(
        f"/api/documents/{doc.id}",
        json=_put_body(
            doc,
            title="바뀐 제목",
            sections=[
                {"heading": "사실", "body": fact, "source_ids": [s.source_id for s in sources]},
                {"heading": "해석", "body": "새로 쓴 " + _LONG_ENOUGH, "source_ids": []},
                {"heading": "지원", "body": "새로 쓴 " + _LONG_ENOUGH, "source_ids": []},
            ],
            review_note="확인 부탁드려요",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "바뀐 제목"
    assert payload["review_note"] == "확인 부탁드려요"
    assert payload["sections"][0]["body"] == fact
    assert datetime.fromisoformat(payload["updated_at"]) > original_updated_at


def test_put_missing_document_returns_not_found(db_session):
    response = client.put(
        "/api/documents/999999",
        json={
            "sections": [
                {"heading": "사실", "body": "", "source_ids": []},
                {"heading": "해석", "body": _LONG_ENOUGH, "source_ids": []},
                {"heading": "지원", "body": _LONG_ENOUGH, "source_ids": []},
            ],
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_put_confirmed_document_is_rejected(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child, status="CONFIRMED")
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)

    response = client.put(f"/api/documents/{doc.id}", json=_put_body(doc))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_CONFIRMED"


def test_put_with_stale_updated_at_is_rejected(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)

    response = client.put(
        f"/api/documents/{doc.id}",
        json=_put_body(doc, updated_at=datetime(2000, 1, 1, tzinfo=UTC).isoformat()),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_WRITE"


def test_put_rejects_wrong_section_headings(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)

    response = client.put(
        f"/api/documents/{doc.id}",
        json=_put_body(
            doc,
            sections=[
                {"heading": "사실", "body": "x", "source_ids": []},
                {"heading": "해석", "body": _LONG_ENOUGH, "source_ids": []},
            ],
        ),
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["sections"]


def test_put_rejects_changed_fact_section(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)

    response = client.put(
        f"/api/documents/{doc.id}",
        json=_put_body(
            doc,
            sections=[
                {"heading": "사실", "body": "원본에 없는 내용", "source_ids": []},
                {"heading": "해석", "body": _LONG_ENOUGH, "source_ids": []},
                {"heading": "지원", "body": _LONG_ENOUGH, "source_ids": []},
            ],
        ),
    )

    assert response.status_code == 422
    assert "sections.사실" in response.json()["error"]["fields"]


@pytest.mark.parametrize(
    "body_text,expected_field",
    [("", "sections.해석"), ("너무짧음", "sections.해석")],
)
def test_put_rejects_short_or_empty_interpretation_and_support(
    db_session, body_text, expected_field
):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)
    fact = "\n\n".join(s.text for s in sources)

    response = client.put(
        f"/api/documents/{doc.id}",
        json=_put_body(
            doc,
            sections=[
                {"heading": "사실", "body": fact, "source_ids": []},
                {"heading": "해석", "body": body_text, "source_ids": []},
                {"heading": "지원", "body": _LONG_ENOUGH, "source_ids": []},
            ],
        ),
    )

    assert response.status_code == 422
    assert expected_field in response.json()["error"]["fields"]


def test_put_rejects_source_ids_not_belonging_to_this_document(db_session):
    _, klass, child = _make_center_class_child(db_session)
    doc = _make_document(db_session, klass, child=child)
    sources = _make_sources(db_session, doc, klass, child)
    _make_sections(db_session, doc, sources)
    fact = "\n\n".join(s.text for s in sources)

    response = client.put(
        f"/api/documents/{doc.id}",
        json=_put_body(
            doc,
            sections=[
                {"heading": "사실", "body": fact, "source_ids": []},
                {"heading": "해석", "body": _LONG_ENOUGH, "source_ids": [999999]},
                {"heading": "지원", "body": _LONG_ENOUGH, "source_ids": []},
            ],
        ),
    )

    assert response.status_code == 422
    assert "sections.해석.source_ids" in response.json()["error"]["fields"]


# ── 겹치는 문서 대조 · 원 격리 ────────────────────────────────────────────────


def test_related_는_기간이_겹치는_확정_문서만_준다(db_session):
    _, klass, child = _make_center_class_child(db_session)
    target = _make_document(db_session, klass, child, kind="observation")
    겹치고_확정 = _make_document(
        db_session,
        klass,
        child,
        kind="dailyLog",
        status="CONFIRMED",
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 10),
    )
    _make_document(  # 겹치지만 아직 쓰는 중이다
        db_session,
        klass,
        child,
        kind="dailyLog",
        status="DRAFT",
        start_date=date(2026, 9, 11),
        end_date=date(2026, 9, 11),
    )
    _make_document(  # 확정이지만 기간이 안 겹친다
        db_session,
        klass,
        child,
        kind="dailyLog",
        status="CONFIRMED",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 1),
    )

    body = client.get(f"/api/documents/{target.id}/related").json()

    assert [item["id"] for item in body["items"]] == [겹치고_확정.id]


def test_related_는_종류마다_기대하는_짝을_알려준다(db_session):
    _, klass, child = _make_center_class_child(db_session)
    weekly = _make_document(db_session, klass, kind="weeklyLog")
    assessment = _make_document(db_session, klass, child, kind="assessment")

    assert client.get(f"/api/documents/{weekly.id}/related").json()["expected_kinds"] == [
        "dailyLog"
    ]
    assert client.get(f"/api/documents/{assessment.id}/related").json()["expected_kinds"] == [
        "observation",
        "dailyLog",
    ]


def test_related_는_없어도_막지_않는다(db_session):
    """ "아직 없음" 으로 표시만 한다 (docs/api-spec.md §11)."""
    _, klass, child = _make_center_class_child(db_session)
    lonely = _make_document(db_session, klass, child)

    response = client.get(f"/api/documents/{lonely.id}/related")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_related_는_다른_아이의_기록을_섞지_않는다(db_session):
    _, klass, child = _make_center_class_child(db_session)
    other_child = Child(class_id=klass.id, name="박가명", code="하늘")
    db_session.add(other_child)
    db_session.flush()
    target = _make_document(db_session, klass, child)
    남의_아이 = _make_document(db_session, klass, other_child, status="CONFIRMED")
    # 일일 보육일지는 하루짜리다 (CHECK 제약).
    반_전체 = _make_document(
        db_session,
        klass,
        None,
        kind="dailyLog",
        status="CONFIRMED",
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 10),
    )

    ids = [item["id"] for item in client.get(f"/api/documents/{target.id}/related").json()["items"]]

    assert 반_전체.id in ids  # 반 단위 문서는 그 반 아이 모두의 짝이다
    assert 남의_아이.id not in ids


def test_남의_원_문서는_목록에도_related_에도_안_나온다(db_session, teacher):
    _, klass, child = _make_center_class_child(db_session)
    남의것 = _make_document(db_session, klass, child)
    other = Center(
        name="남의어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    db_session.add(other)
    db_session.flush()
    teacher.center_id = other.id

    assert client.get("/api/documents").json()["items"] == []
    assert client.get(f"/api/documents/{남의것.id}/related").status_code == 404


# ── 원 격리 (단건 · 수정 · 삭제 · 확정) ────────────────────────────────────────
def test_남의_원_문서는_단건_수정_삭제_확정_모두_404_다(db_session, teacher):
    _, klass, child = _make_center_class_child(db_session)
    남의것 = _make_document(db_session, klass, child)
    other = Center(
        name="남의어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="원주시",
    )
    db_session.add(other)
    db_session.flush()
    teacher.center_id = other.id

    url = f"/api/documents/{남의것.id}"
    assert client.get(url).status_code == 404
    assert client.put(url, json=_put_body(남의것)).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.post(f"{url}/confirm", json={"checks": _ALL_CHECKED}).status_code == 404


# ── POST /api/documents ─────────────────────────────────────────────────────
def _observation(session, klass, child, day, fact):
    observation = Observation(
        class_id=klass.id,
        child_id=child.id,
        date=date(2026, 9, day),
        domain="자연탐구",
        context="바깥놀이",
        fact=fact,
    )
    session.add(observation)
    session.flush()
    return observation


def _create_body(klass, child, sources, **overrides):
    body = {
        "kind": "observation",
        "class_id": klass.id,
        "child_id": child.id if child else None,
        "start": "2026-09-01",
        "end": "2026-09-30",
        "source_ids": [s.id for s in sources],
    }
    body.update(overrides)
    return body


def test_create_document_copies_sources_and_builds_fact(db_session):
    _, klass, child = _make_center_class_child(db_session)
    first = _observation(db_session, klass, child, 5, "개미를 3분 동안 바라보았다.")
    second = _observation(db_session, klass, child, 6, "무당벌레를 손바닥에 올렸다.")

    response = client.post("/api/documents", json=_create_body(klass, child, [first, second]))

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "DRAFT"
    assert payload["origin"] == "AI"
    assert payload["title"] == "이가명 관찰일지 (9월)"
    by_heading = {s["heading"]: s for s in payload["sections"]}
    # 사실은 서버가 원문을 고른 순서대로 붙인다. LLM 이 만지지 않는다.
    assert by_heading["사실"]["body"] == f"{first.fact}\n\n{second.fact}"
    assert [s["id"] for s in payload["sources"]] == [first.id, second.id]

    # 원본을 나중에 고쳐도 문서 쪽 사본은 안 바뀐다 — 무효 판정이 비교할 원문이다.
    first.fact = "고친 사실"
    db_session.flush()
    detail = client.get(f"/api/documents/{payload['id']}").json()
    assert detail["sources"][0]["text"] == "개미를 3분 동안 바라보았다."


def test_create_document_masks_child_names_before_generation(db_session, monkeypatch):
    # 실명이 LLM 쪽(생성기)으로 넘어가면 안 된다. 가명으로 바뀐 글만 받아야 한다.
    _, klass, child = _make_center_class_child(db_session)
    record = _observation(db_session, klass, child, 5, "이가명이 가명이와 블록을 쌓았다.")
    seen = {}

    def fake_generate(kind, masked_facts):
        seen["facts"] = masked_facts
        return (
            "도담 해석입니다. 기록에 드러난 사실만 근거로 씁니다.",
            "도담 지원입니다. 다음 활동에서 교사가 할 방법을 적습니다.",
        )

    monkeypatch.setattr("app.features.documents.draft._generate", fake_generate)
    response = client.post("/api/documents", json=_create_body(klass, child, [record]))

    assert response.status_code == 201
    assert "이가명" not in seen["facts"][0] and "가명" not in seen["facts"][0]
    assert "도담" in seen["facts"][0]
    # 돌아온 글은 교사에게 주기 전에 실명으로 되돌린다.
    by_heading = {s["heading"]: s["body"] for s in response.json()["sections"]}
    assert by_heading["해석"].startswith("이가명 해석")


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"child_id": None}, "child_id"),
        ({"kind": "dailyLog", "child_id": None}, "end"),
        ({"source_ids": []}, "source_ids"),
    ],
    ids=["child_required", "daily_log_single_day", "empty_sources"],
)
def test_create_document_rejects_invalid_requests(db_session, overrides, field):
    _, klass, child = _make_center_class_child(db_session)
    record = _observation(db_session, klass, child, 5, "개미를 바라보았다.")

    response = client.post("/api/documents", json=_create_body(klass, child, [record], **overrides))

    assert response.status_code == 422
    assert field in response.json()["error"]["fields"]


def test_create_document_rejects_duplicate_source_ids(db_session):
    _, klass, child = _make_center_class_child(db_session)
    record = _observation(db_session, klass, child, 5, "개미를 바라보았다.")

    response = client.post(
        "/api/documents", json=_create_body(klass, child, [record], source_ids=[record.id] * 2)
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["source_ids"]


def test_create_document_rejects_sources_outside_the_document(db_session):
    # 기간 밖 · 다른 아이 기록은 근거로 못 쓴다. 틀린 근거를 전부 모아서 알려준다.
    _, klass, child = _make_center_class_child(db_session)
    other = Child(class_id=klass.id, name="박친구", code="하람")
    db_session.add(other)
    db_session.flush()
    out_of_range = _observation(db_session, klass, child, 5, "개미를 바라보았다.")
    other_child = _observation(db_session, klass, other, 6, "모래를 팠다.")

    response = client.post(
        "/api/documents",
        json=_create_body(
            klass, child, [out_of_range, other_child], start="2026-09-10", end="2026-09-30"
        ),
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == [
        f"sources.{out_of_range.id}",
        f"sources.{other_child.id}",
    ]


def test_create_weekly_log_requires_confirmed_daily_logs(db_session):
    _, klass, child = _make_center_class_child(db_session)
    daily = _make_document(
        db_session,
        klass,
        child=None,
        kind="dailyLog",
        start_date=date(2026, 9, 22),
        end_date=date(2026, 9, 22),
    )
    body = _create_body(
        klass, None, [daily], kind="weeklyLog", start="2026-09-21", end="2026-09-27"
    )

    blocked = client.post("/api/documents", json=body)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "GATE_BLOCKED"

    # 확정된 일일 보육일지는 그 문서의 `사실` 항목이 근거 원문이 된다.
    sources = _make_sources(db_session, daily, klass, None, count=1)
    _make_sections(db_session, daily, sources)
    daily.status = "CONFIRMED"
    db_session.flush()

    created = client.post("/api/documents", json=body)
    assert created.status_code == 201
    payload = created.json()
    assert payload["sources"][0]["text"] == "관찰 기록 0."
    source_row = db_session.query(DocumentSource).filter_by(document_id=payload["id"]).one()
    assert source_row.source_kind == "document"
    assert source_row.source_status == "CONFIRMED"


def test_create_document_saves_nothing_when_generation_fails(db_session, monkeypatch):
    """AI 를 못 부르면 **부분 결과를 남기지 않는다.**

    `real` 인데 엘리스 설정이 없는 상태를 만든다 — 운영에서 키를 안 넣고 배포한 경우다.
    """
    from app.config import settings

    _, klass, child = _make_center_class_child(db_session)
    record = _observation(db_session, klass, child, 5, "개미를 바라보았다.")
    monkeypatch.setattr(settings, "llm_mode", "real")
    monkeypatch.setattr(settings, "elice_mlapi_base_url", None)
    monkeypatch.setattr(settings, "elice_mlapi_api_key", None)

    response = client.post("/api/documents", json=_create_body(klass, child, [record]))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "GENERATION_FAILED"
    assert db_session.query(Document).count() == 0


# ── POST /api/documents/{id}/confirm ────────────────────────────────────────
_ALL_CHECKED = {"fact": True, "interpretation": True, "support": True}


def _ready_document(session):
    _, klass, child = _make_center_class_child(session)
    doc = _make_document(session, klass, child=child)
    _make_sections(session, doc, _make_sources(session, doc, klass, child))
    return doc


def test_confirm_marks_the_document_confirmed_and_is_idempotent(db_session):
    doc = _ready_document(db_session)

    first = client.post(f"/api/documents/{doc.id}/confirm", json={"checks": _ALL_CHECKED})
    again = client.post(f"/api/documents/{doc.id}/confirm", json={"checks": _ALL_CHECKED})

    assert first.status_code == 200
    assert first.json()["status"] == "CONFIRMED"
    # 더블클릭 · 재시도로 두 번 와도 실패가 아니다.
    assert again.status_code == 200
    assert client.put(f"/api/documents/{doc.id}", json=_put_body(doc)).status_code == 409


def test_confirm_requires_all_three_checks(db_session):
    doc = _ready_document(db_session)

    response = client.post(
        f"/api/documents/{doc.id}/confirm",
        json={"checks": {**_ALL_CHECKED, "support": False}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == ["checks.support"]


def test_confirm_is_blocked_while_stale(db_session):
    doc = _ready_document(db_session)
    doc.stale = True
    db_session.flush()

    response = client.post(f"/api/documents/{doc.id}/confirm", json={"checks": _ALL_CHECKED})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GATE_BLOCKED"


def test_confirm_reruns_the_section_gate(db_session):
    # 저장된 사실이 원문과 어긋나 있으면 교사가 체크해도 확정되지 않는다.
    doc = _ready_document(db_session)
    fact = db_session.query(DocumentSection).filter_by(document_id=doc.id, heading="사실").one()
    fact.body = "원문에 없는 사실"
    db_session.flush()

    response = client.post(f"/api/documents/{doc.id}/confirm", json={"checks": _ALL_CHECKED})

    assert response.status_code == 422
    assert "sections.사실" in response.json()["error"]["fields"]


# ── DELETE /api/documents/{id} ──────────────────────────────────────────────
def test_delete_removes_the_document_and_marks_dependents_stale(db_session):
    _, klass, child = _make_center_class_child(db_session)
    daily = _make_document(
        db_session,
        klass,
        child=None,
        kind="dailyLog",
        start_date=date(2026, 9, 22),
        end_date=date(2026, 9, 22),
    )
    _make_sections(db_session, daily, _make_sources(db_session, daily, klass, None, count=1))
    weekly = _make_document(
        db_session,
        klass,
        child=None,
        kind="weeklyLog",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 27),
    )
    db_session.add(
        DocumentSource(
            document_id=weekly.id,
            source_kind="document",
            source_id=daily.id,
            class_id=klass.id,
            date=date(2026, 9, 22),
            source_status="CONFIRMED",
            text="관찰 기록 0.",
        )
    )
    db_session.flush()

    response = client.delete(f"/api/documents/{daily.id}")

    assert response.status_code == 204
    assert client.get(f"/api/documents/{daily.id}").status_code == 404
    assert db_session.query(DocumentSection).filter_by(document_id=daily.id).count() == 0
    # 근거가 사라진 주간 보육일지는 지우지 않고 다시 보라고 표시한다.
    db_session.refresh(weekly)
    assert weekly.stale is True
