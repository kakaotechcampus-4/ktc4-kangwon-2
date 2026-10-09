"""문서 읽기 창구의 기간·원 경계를 실제 Postgres 로 확인한다."""

from dataclasses import FrozenInstanceError, fields
from datetime import date, timedelta

import pytest

from app.features.centers.models import Center, Child, Class
from app.features.documents import service
from app.features.documents.models import Document

START, END = date(2026, 9, 1), date(2026, 10, 7)
READERS = [
    (service.list_confirmed_by_class, "dailyLog", "class_ids"),
    (service.list_confirmed_by_child, "assessment", "child_ids"),
]


@pytest.fixture
def scopes(db_session):
    result = []
    for name in ("우리 원", "다른 원"):
        center = Center(name=name, director_name="가명", region_sido="강원", region_sigungu="춘천")
        db_session.add(center)
        db_session.flush()
        klass = Class(
            center_id=center.id,
            name="해님반",
            school_year=2026,
            age_min=4,
            age_max=4,
            teacher_name="가명",
        )
        db_session.add(klass)
        db_session.flush()
        child = Child(class_id=klass.id, name="김하늘(가명)", code="하늘")
        db_session.add(child)
        db_session.flush()
        result.append((center, klass, child))
    return result


def _document(session, klass, child, day, kind, status="CONFIRMED"):
    document = Document(
        class_id=klass.id,
        child_id=child.id if kind in ("assessment", "observation") else None,
        kind=kind,
        title="테스트 문서",
        status=status,
        origin="TEACHER",
        start_date=day if kind == "dailyLog" else date(2025, 1, 1),
        end_date=day,
    )
    session.add(document)
    session.flush()
    return document.id


@pytest.mark.parametrize("reader,kind,ids_key", READERS)
def test_확정_종류_끝날경계와_정렬을_지킨다(db_session, scopes, reader, kind, ids_key):
    center, klass, child = scopes[0]
    last = _document(db_session, klass, child, END, kind)
    first = _document(db_session, klass, child, START, kind)
    tied = _document(db_session, klass, child, START, kind)
    for day in (START - timedelta(days=1), END + timedelta(days=1)):
        _document(db_session, klass, child, day, kind)
    _document(db_session, klass, child, START, kind, "DRAFT")
    _document(
        db_session, klass, child, START, "observation" if kind == "assessment" else "weeklyLog"
    )
    ids = [klass.id if ids_key == "class_ids" else child.id]
    result = reader(db_session, center.id, kind=kind, start=START, end=END, **{ids_key: ids})
    assert [row.id for row in result] == [first, tied, last]


@pytest.mark.parametrize("reader,kind,ids_key", READERS)
def test_남의_원_반과_아동은_빠진다(db_session, scopes, reader, kind, ids_key):
    center, klass, child = scopes[0]
    _, other_class, other_child = scopes[1]
    own = _document(db_session, klass, child, START, kind)
    _document(db_session, other_class, other_child, START, kind)
    _document(db_session, other_class, child, START, kind)
    ids = [klass.id, other_class.id] if ids_key == "class_ids" else [child.id, other_child.id]
    result = reader(db_session, center.id, kind=kind, start=START, end=END, **{ids_key: ids})
    assert [row.id for row in result] == [own]


@pytest.mark.parametrize("reader,kind,ids_key", READERS)
def test_빈_목록이면_쿼리하지_않고_빈_결과다(db_session, monkeypatch, reader, kind, ids_key):
    monkeypatch.setattr(
        db_session, "execute", lambda *args, **kwargs: pytest.fail("쿼리하면 안 된다")
    )
    assert reader(db_session, 1, kind=kind, start=START, end=END, **{ids_key: []}) == []


@pytest.mark.parametrize("reader,kind,ids_key", READERS)
def test_네칸만_읽고_저장하지_않는다(db_session, scopes, monkeypatch, reader, kind, ids_key):
    center, klass, child = scopes[0]
    document_id = _document(db_session, klass, child, START, kind)
    monkeypatch.setattr(db_session, "commit", lambda *args: pytest.fail("읽기 중 저장 금지"))
    execute = db_session.execute

    def record(statement):
        assert list(statement.selected_columns.keys()) == ["id", "class_id", "child_id", "end_date"]
        return execute(statement)

    monkeypatch.setattr(db_session, "execute", record)
    ids = [klass.id if ids_key == "class_ids" else child.id]
    result = reader(db_session, center.id, kind=kind, start=START, end=END, **{ids_key: ids})
    child_id = child.id if kind == "assessment" else None
    assert result == [service.ConfirmedDocument(document_id, klass.id, child_id, START)]
    assert [field.name for field in fields(result[0])] == ["id", "class_id", "child_id", "end_date"]
    with pytest.raises(FrozenInstanceError):
        result[0].id = 0
