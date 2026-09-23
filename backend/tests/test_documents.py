"""documents 스키마·GET /api/documents 통합 테스트. 실제 DB 를 쓴다."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document, DocumentSection, DocumentSource
from app.main import app

client = TestClient(app)


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
