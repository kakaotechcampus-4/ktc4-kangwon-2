"""자동 판정 입력을 실제 Postgres 에서 모은다. 아동 이름은 모두 테스트용 가명이다."""

from datetime import date, datetime

import pytest

from app.features.centers.models import Center, Child, Class
from app.features.documents.models import Document
from app.features.evaluation import auto
from app.features.evaluation.judge import INSUFFICIENT, NONE, Ratio, Window
from app.shared.school_year import KST

NOW = datetime(2026, 10, 8, 10, tzinfo=KST)


@pytest.fixture
def roster(db_session):
    centers = [
        Center(name=name, director_name="가명원장", region_sido="강원", region_sigungu="춘천")
        for name in ("테스트 원", "다른 원")
    ]
    db_session.add_all(centers)
    db_session.flush()
    classes = [
        Class(
            center_id=center.id,
            name=name,
            school_year=year,
            age_min=3,
            age_max=5,
            teacher_name="가명교사",
        )
        for center, name, year in (
            (centers[0], "해님반", 2026),
            (centers[0], "달님반", 2026),
            (centers[0], "해님반", 2025),
            (centers[1], "다른 반", 2026),
        )
    ]
    db_session.add_all(classes)
    db_session.flush()
    children = [
        Child(class_id=classes[index].id, name=name, code=name)
        for index, name in zip(
            (0, 0, 1, 2, 3), "김하늘 이바다 박구름 최새벽 강이슬".split(), strict=True
        )
    ]
    db_session.add_all(children)
    db_session.flush()
    return centers[0], classes, children


def _document(session, classroom, day, child=None, kind="dailyLog", status="CONFIRMED"):
    document = Document(
        class_id=classroom.id,
        child_id=child.id if child else None,
        kind=kind,
        title="테스트 문서",
        start_date=date.fromisoformat(day),
        end_date=date.fromisoformat(day),
        status=status,
        origin="IMPORT",
        stale=True,
    )
    session.add(document)
    session.flush()
    return document.id


def test_확정_IMPORT_stale도_세고_타원과_작년반을_뺀_최종판정이다(db_session, roster, monkeypatch):
    center, classes, children = roster
    sun, moon, previous, other = classes
    sky, sea, _, last_child, other_child = children
    log = _document(db_session, sun, "2026-10-06")
    _document(db_session, sun, "2026-10-06", status="DRAFT")
    _document(db_session, sun, "2026-08-31")
    _document(db_session, previous, "2026-10-06")
    _document(db_session, other, "2026-10-06")
    assessments = (
        _document(db_session, sun, "2026-03-31", sky, "assessment"),
        _document(db_session, moon, "2026-04-30", sky, "assessment"),
    )
    _document(db_session, sun, "2026-04-30", sea, "assessment", "DRAFT")
    _document(db_session, previous, "2026-04-30", last_child, "assessment")
    _document(db_session, other, "2026-04-30", other_child, "assessment")

    result = auto.judge_auto(db_session, center.id, NOW)

    assert set(result) == {"4-1", "4-2"}
    assert result["4-1"].verdict == result["4-2"].verdict == INSUFFICIENT
    assert result["4-1"].classes == Ratio(0, 2)
    assert result["4-1"].document_ids == (log,)
    assert result["4-1"].plan_ids == ()
    assert result["4-1"].count == 1
    assert result["4-1"].period == Window(date(2026, 9, 1), date(2026, 10, 7))
    assert result["4-2"].children == Ratio(1, 3)
    assert result["4-2"].document_ids == assessments
    assert result["4-2"].count == result["4-2"].required == 2
    assert result["4-2"].period == Window(date(2025, 10, 1), date(2026, 10, 7))
    monkeypatch.setattr(db_session, "commit", lambda: pytest.fail("판정은 저장하지 않는다"))
    assert auto.judge_auto(db_session, center.id, NOW) == result


def test_반을_옮긴_아이의_옛반_평가도_센다(db_session, roster):
    center, classes, children = roster
    child = children[0]
    child.class_id = classes[2].id
    db_session.flush()
    assessment = _document(db_session, classes[2], "2026-02-28", child, "assessment")
    child.class_id = classes[0].id
    db_session.flush()

    assert auto.judge_auto(db_session, center.id, NOW)["4-2"].document_ids == (assessment,)


def test_문서가_없으면_둘_다_NONE이다(db_session, roster):
    result = auto.judge_auto(db_session, roster[0].id, NOW)
    assert result["4-1"].verdict == result["4-2"].verdict == NONE
    assert result["4-1"].classes == Ratio(0, 2)
    assert result["4-2"].children == Ratio(0, 3)
