"""별도 PostgreSQL 연결의 실제 동시 재확정/원본 수정. 만든 행만 정리한다."""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, time
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_documents import _make_center_class_child, _make_document, _make_sections

from app.db import engine
from app.features.auth.models import User
from app.features.centers.models import Center, Child, Class
from app.features.documents.models import (
    Document,
    DocumentReconfirmation,
    DocumentSection,
    DocumentSource,
    DocumentSourceResolution,
)
from app.features.documents.review import locked_review, reconfirm
from app.features.documents.router import confirm_document, refresh_document
from app.features.documents.schemas import (
    DocumentConfirmRequest,
    DocumentReconfirmRequest,
    DocumentRefreshRequest,
)
from app.features.documents.stale import source_changed
from app.features.routines.models import RoutineRecord
from app.features.routines.router import _own, delete_routine, update_routine
from app.features.routines.schemas import RoutineUpdate


@pytest.mark.parametrize("racing", ["same_request", "different_request", "source_write"])
def test_simultaneous_reconfirm_is_serialized_and_source_change_is_never_lost(_schema, racing):
    with Session(engine, expire_on_commit=False) as session:
        center, klass, child = _make_center_class_child(session)
        routine = RoutineRecord(
            class_id=klass.id,
            date=date(2026, 10, 19),
            position=0,
            start_time=time(9),
            end_time=time(10),
            name="가명 놀이",
            plan="",
            execution="최신 원본 사실",
        )
        session.add(routine)
        session.flush()
        doc = _make_document(
            session,
            klass,
            kind="dailyLog",
            start_date=routine.date,
            end_date=routine.date,
            status="CONFIRMED",
            stale=True,
        )
        copy = DocumentSource(
            document_id=doc.id,
            source_kind="routine",
            source_id=routine.id,
            class_id=klass.id,
            date=routine.date,
            text="이전 원본 사실",
        )
        session.add(copy)
        session.flush()
        _make_sections(session, doc, [copy])
        session.commit()
        center_id, class_id, child_id, routine_id, doc_id = (
            center.id,
            klass.id,
            child.id,
            routine.id,
            doc.id,
        )
    user = SimpleNamespace(center_id=center_id)
    with Session(engine) as session:
        _, _, sections, _, viewed = locked_review(session, user, doc_id)
        data = {
            "review_token": viewed.review_token,
            "updated_at": viewed.updated_at,
            "checks": {"fact": True, "interpretation": True, "support": True},
            "sections": [
                {
                    "heading": s.heading,
                    "body": viewed.sources[0].after if s.heading == "사실" else s.body,
                    "source_ids": s.source_ids,
                }
                for s in sections
            ],
        }
        body = DocumentReconfirmRequest.model_validate(data)
    barrier = Barrier(2)

    def run(index):
        with Session(engine, expire_on_commit=False) as session:
            session.execute(select(func.set_config("lock_timeout", "8s", True)))
            barrier.wait(timeout=10)
            try:
                if index and racing == "source_write":
                    update_routine(
                        routine_id,
                        RoutineUpdate(
                            date=date(2026, 10, 19),
                            position=0,
                            start=time(9),
                            end=time(10),
                            name="가명 놀이",
                            plan="",
                            execution="동시 수정한 사실",
                        ),
                        session,
                        user,
                    )
                    return "source"
                request = body.model_copy(deep=True)
                if index and racing == "different_request":
                    request.sections[1].body = "다른 교사가 직접 변경해서 제출한 해석 문장입니다."
                result = reconfirm(session, user, doc_id, request)
                return ("ok", result.updated_at)
            except HTTPException as exc:
                session.rollback()
                assert exc.detail["code"] == "STALE_WRITE"
                return "conflict"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, [0, 1]))
        with Session(engine) as session:
            current = session.get(Document, doc_id)
            receipts = session.scalar(
                select(func.count())
                .select_from(DocumentReconfirmation)
                .where(DocumentReconfirmation.document_id == doc_id)
            )
            assert current.status == "CONFIRMED"
            if racing == "same_request":
                assert results[0] == results[1]
                assert receipts == 1 and not current.stale
            elif racing == "different_request":
                assert results.count("conflict") == 1
                assert receipts == 1 and not current.stale
            else:
                assert "source" in results and current.stale
                assert session.get(RoutineRecord, routine_id).execution == "동시 수정한 사실"
                assert receipts in (0, 1)
    finally:
        with Session(engine) as session:
            session.execute(
                delete(DocumentReconfirmation).where(DocumentReconfirmation.document_id == doc_id)
            )
            session.execute(delete(DocumentSection).where(DocumentSection.document_id == doc_id))
            session.execute(delete(DocumentSource).where(DocumentSource.document_id == doc_id))
            session.execute(delete(Document).where(Document.id == doc_id))
            session.execute(delete(RoutineRecord).where(RoutineRecord.id == routine_id))
            session.execute(delete(Child).where(Child.id == child_id))
            session.execute(delete(Class).where(Class.id == class_id))
            session.execute(delete(Center).where(Center.id == center_id))
            session.commit()


# --- F2: 초안 refresh 와 원본 수정이 겹칠 때 원본·사본이 어긋나는가 -------------------

FACT = "[가명 놀이 09:00~10:00] {}"
CHECKS = {"fact": True, "interpretation": True, "support": True}


@pytest.fixture
def racing_draft():
    """초안 + stale. 사본은 A 인데 살아 있는 원본은 B 다 — A→B 가 이미 끝난 자리."""
    with Session(engine, expire_on_commit=False) as session:
        center, klass, child = _make_center_class_child(session)
        # 감사 기록(document_source_resolutions.actor_user_id)이 가리킬 진짜 계정.
        teacher = User(
            email=f"racing{uuid4().hex}@example.com",
            name="김선생",
            password_hash=b"x" * 64,
            password_salt=b"y" * 16,
            center_id=center.id,
        )
        session.add(teacher)
        session.flush()
        day = date(2026, 10, 19)
        routine = RoutineRecord(
            class_id=klass.id,
            date=day,
            position=0,
            start_time=time(9),
            end_time=time(10),
            name="가명 놀이",
            plan="",
            execution="B원본",
        )
        spare = RoutineRecord(
            class_id=klass.id,
            date=day,
            position=1,
            start_time=time(11),
            end_time=time(12),
            name="대체용 놀이",
            plan="",
            execution="대체용 사실",
        )
        session.add_all([routine, spare])
        session.flush()
        doc = _make_document(
            session,
            klass,
            kind="dailyLog",
            start_date=day,
            end_date=day,
            status="DRAFT",
            stale=True,
            review_note="교사가 남긴 메모",
        )
        copy = DocumentSource(
            document_id=doc.id,
            source_kind="routine",
            source_id=routine.id,
            class_id=klass.id,
            date=day,
            text=FACT.format("A원본"),
        )
        session.add(copy)
        session.flush()
        _make_sections(session, doc, [copy])
        session.commit()
        ids = SimpleNamespace(
            center=center.id,
            user=teacher.id,
            klass=klass.id,
            child=child.id,
            routine=routine.id,
            spare=spare.id,
            doc=doc.id,
            day=day,
        )
    try:
        yield ids
    finally:
        with Session(engine) as session:
            session.execute(
                delete(DocumentReconfirmation).where(DocumentReconfirmation.document_id == ids.doc)
            )
            session.execute(
                delete(DocumentSourceResolution).where(
                    DocumentSourceResolution.document_id == ids.doc
                )
            )
            session.execute(delete(DocumentSection).where(DocumentSection.document_id == ids.doc))
            session.execute(delete(DocumentSource).where(DocumentSource.document_id == ids.doc))
            session.execute(delete(Document).where(Document.id == ids.doc))
            session.execute(
                delete(RoutineRecord).where(RoutineRecord.id.in_([ids.routine, ids.spare]))
            )
            session.execute(delete(Child).where(Child.id == ids.child))
            session.execute(delete(User).where(User.id == ids.user))
            session.execute(delete(Class).where(Class.id == ids.klass))
            session.execute(delete(Center).where(Center.id == ids.center))
            session.commit()


def _writer(ids, execution, *, started, release, timeout=10):
    """원본을 되돌리는 트랜잭션. **커밋 직전에 멈춘다** — 그래야 경쟁 창이 결정적이다.

    `update_routine` 이 하는 일을 그대로(같은 잠금·같은 `source_changed`) 하고 커밋만 늦춘다.
    """

    def run():
        user = SimpleNamespace(center_id=ids.center, id=ids.user)
        with Session(engine, expire_on_commit=False) as session:
            session.execute(select(func.set_config("lock_timeout", "8s", True)))
            record = _own(session, user, ids.routine, lock=True)[0]
            record.execution = execution
            source_changed(
                session,
                "routine",
                ids.routine,
                record.fact_text(),
                record.date,
                center_id=ids.center,
            )
            started.set()
            assert release.wait(timeout), "release 신호가 오지 않았다"
            session.commit()
        return "writer"

    return run


def _refresh(ids, body=None, *, wait=None, timeout=10):
    def run():
        user = SimpleNamespace(center_id=ids.center, id=ids.user)
        if wait is not None:
            assert wait.wait(timeout), "start 신호가 오지 않았다"
        with Session(engine, expire_on_commit=False) as session:
            session.execute(select(func.set_config("lock_timeout", "8s", True)))
            try:
                refresh_document(ids.doc, session, user, body)
                return "refreshed"
            except HTTPException as exc:
                session.rollback()
                return ("conflict", exc.detail["code"])

    return run


def _state(doc_id):
    with Session(engine) as session:
        doc = session.get(Document, doc_id)
        copies = session.scalars(
            select(DocumentSource).where(DocumentSource.document_id == doc_id)
        ).all()
        fact = session.scalar(
            select(DocumentSection.body).where(
                DocumentSection.document_id == doc_id, DocumentSection.heading == "사실"
            )
        )
        return SimpleNamespace(
            status=doc.status,
            stale=doc.stale,
            note=doc.review_note,
            copies={c.source_id: c.text for c in copies},
            fact=fact,
        )


def _live(routine_id):
    with Session(engine) as session:
        record = session.get(RoutineRecord, routine_id)
        return None if record is None else record.fact_text()


def _assert_consistent(ids, label=""):
    """불변식: 확정 가능한 문서(= stale 아님)의 사본은 살아 있는 원본과 같아야 한다."""
    state = _state(ids.doc)
    if state.stale:
        return state
    for source_id, text in state.copies.items():
        assert _live(source_id) == text, f"{label}: 원본과 사본이 다른데 stale 이 아니다"
    return state


def _race_refresh_with_revert(ids, execution, body=None, settle=3):
    """되돌리기를 **커밋 직전까지** 세워 두고 그 창에서 refresh 를 돌린다.

    수정 전에는 refresh 가 막히지 않고 끝나 옛 값을 fresh 로 저장했다.
    수정 뒤에는 원본 잠금에서 기다리므로 `settle` 안에 끝나지 않는다 — 그때 되돌리기를 커밋한다.
    무작위 sleep 이 아니라 **잠금 대기**를 기다리는 것이고, 상한을 둬서 교착이면 테스트가 끝난다.
    """
    started, release = Event(), Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(_writer(ids, execution, started=started, release=release))
        assert started.wait(10), "writer 가 source_changed 까지 가지 못했다"
        refreshing = pool.submit(_refresh(ids, body))
        try:
            outcome = refreshing.result(timeout=settle)
        except FutureTimeout:
            outcome = None
        release.set()
        assert writing.result(timeout=20) == "writer"
        if outcome is None:
            outcome = refreshing.result(timeout=20)
    return outcome


def test_f2_refresh_racing_a_b_a_never_leaves_a_fresh_mismatch(_schema, racing_draft):
    """A→B 뒤 refresh 와 B→A 되돌리기가 겹쳐도 원본과 사본이 어긋난 채 확정되지 않는다."""
    ids = racing_draft
    outcome = _race_refresh_with_revert(ids, "A원본")
    assert outcome in ("refreshed", ("conflict", "GATE_BLOCKED"), ("conflict", "STALE_WRITE"))
    assert _live(ids.routine) == FACT.format("A원본")
    state = _assert_consistent(ids, "A→B→A")
    assert state.status == "DRAFT"
    assert state.note == "교사가 남긴 메모"


def test_f2_source_put_committed_first_is_reflected_by_the_later_refresh(_schema, racing_draft):
    """원본 PUT 이 먼저 끝나면 refresh 는 그 최신 값을 반영한다."""
    ids = racing_draft
    user = SimpleNamespace(center_id=ids.center, id=ids.user)
    with Session(engine) as session:
        update_routine(
            ids.routine,
            RoutineUpdate(
                date=ids.day,
                position=0,
                start=time(9),
                end=time(10),
                name="가명 놀이",
                plan="",
                execution="C원본",
            ),
            session,
            user,
        )
    assert _refresh(ids)() == "refreshed"
    state = _assert_consistent(ids, "PUT 선행")
    assert state.copies[ids.routine] == FACT.format("C원본")
    assert state.fact == FACT.format("C원본")
    assert not state.stale


def test_f2_source_change_between_refresh_and_confirm_blocks_the_confirm(_schema, racing_draft):
    """refresh 뒤 원본이 바뀌면 확정이 거절된다 — 옛 근거가 확정되지 않는다."""
    ids = racing_draft
    user = SimpleNamespace(center_id=ids.center, id=ids.user)
    assert _refresh(ids)() == "refreshed"
    assert not _state(ids.doc).stale
    with Session(engine) as session:
        update_routine(
            ids.routine,
            RoutineUpdate(
                date=ids.day,
                position=0,
                start=time(9),
                end=time(10),
                name="가명 놀이",
                plan="",
                execution="확정 직전에 바뀐 사실",
            ),
            session,
            user,
        )
    assert _state(ids.doc).stale, "원본이 바뀌었으면 다시 stale 이다"
    with Session(engine) as session:
        with pytest.raises(HTTPException) as refused:
            confirm_document(
                ids.doc, DocumentConfirmRequest.model_validate({"checks": CHECKS}), session, user
            )
        session.rollback()
    assert refused.value.status_code == 409
    assert refused.value.detail["code"] == "GATE_BLOCKED"
    assert _state(ids.doc).status == "DRAFT"


def _delete_routine(ids, record_id):
    with Session(engine) as session:
        delete_routine(record_id, session, SimpleNamespace(center_id=ids.center, id=ids.user))


def _drop(source_id):
    return DocumentRefreshRequest.model_validate(
        {"resolutions": [{"source_id": source_id, "action": "drop"}]}
    )


def _replace(source_id, replacement_id):
    return DocumentRefreshRequest.model_validate(
        {
            "resolutions": [
                {"source_id": source_id, "action": "replace", "replacement_id": replacement_id}
            ]
        }
    )


@pytest.fixture
def deleted_and_live(racing_draft):
    """사라진 근거 1건 + 살아 있는 근거 1건. 초안이고 stale 이다."""
    ids = racing_draft
    with Session(engine, expire_on_commit=False) as session:
        copy = DocumentSource(
            document_id=ids.doc,
            source_kind="routine",
            source_id=ids.spare,
            class_id=ids.klass,
            date=ids.day,
            text=FACT.format("A원본"),
        )
        session.add(copy)
        session.flush()
        for section in session.scalars(
            select(DocumentSection).where(DocumentSection.document_id == ids.doc)
        ):
            section.source_ids = [*section.source_ids, ids.spare]
        session.commit()
    _delete_routine(ids, ids.routine)
    return ids


def test_f2_dropping_a_deleted_source_while_the_live_one_changes_stays_consistent(
    _schema, deleted_and_live
):
    """사라진 근거를 빼는 동안 살아 있는 근거가 바뀌어도 fresh 로 어긋나지 않는다."""
    ids = deleted_and_live
    started, release = Event(), Event()
    with ThreadPoolExecutor(max_workers=2) as pool:

        def writer():
            user = SimpleNamespace(center_id=ids.center, id=ids.user)
            with Session(engine, expire_on_commit=False) as session:
                session.execute(select(func.set_config("lock_timeout", "8s", True)))
                record = _own(session, user, ids.spare, lock=True)[0]
                record.execution = "동시에 바뀐 살아 있는 사실"
                source_changed(
                    session,
                    "routine",
                    ids.spare,
                    record.fact_text(),
                    record.date,
                    center_id=ids.center,
                )
                started.set()
                assert release.wait(10)
                session.commit()
            return "writer"

        writing = pool.submit(writer)
        assert started.wait(10)
        refreshing = pool.submit(_refresh(ids, _drop(ids.routine)))
        try:
            outcome = refreshing.result(timeout=3)
        except FutureTimeout:
            outcome = None
        release.set()
        assert writing.result(timeout=20) == "writer"
        if outcome is None:
            outcome = refreshing.result(timeout=20)
    assert outcome in ("refreshed", ("conflict", "GATE_BLOCKED"))
    state = _assert_consistent(ids, "제외 + 동시 수정")
    assert ids.routine not in state.copies, "사라진 근거는 빠졌다"


@pytest.mark.parametrize("racing", ["edited", "emptied", "deleted"])
def test_f2_a_replacement_changed_underneath_is_never_stored(_schema, deleted_and_live, racing):
    """대체 후보가 그 사이 바뀌거나 사라지면, 본 적 없는 값이나 못 쓰는 근거를 저장하지 않는다."""
    ids = deleted_and_live
    # 대체 후보를 하나 더 만든다 — 지워진 근거를 이걸로 바꾸려는 참이다.
    with Session(engine, expire_on_commit=False) as session:
        pick = RoutineRecord(
            class_id=ids.klass,
            date=ids.day,
            position=2,
            start_time=time(13),
            end_time=time(14),
            name="새 놀이",
            plan="",
            execution="대체할 사실",
        )
        session.add(pick)
        session.commit()
        pick_id, pick_text = pick.id, pick.fact_text()
    try:
        before = _state(ids.doc)
        started, release = Event(), Event()
        with ThreadPoolExecutor(max_workers=2) as pool:

            def writer():
                user = SimpleNamespace(center_id=ids.center, id=ids.user)
                with Session(engine, expire_on_commit=False) as session:
                    session.execute(select(func.set_config("lock_timeout", "8s", True)))
                    record = _own(session, user, pick_id, lock=True)[0]
                    if racing == "deleted":
                        source_changed(
                            session, "routine", pick_id, None, None, center_id=ids.center
                        )
                        session.delete(record)
                    else:
                        record.execution = "" if racing == "emptied" else "그 사이 고쳐진 사실"
                        source_changed(
                            session,
                            "routine",
                            pick_id,
                            record.fact_text(),
                            record.date,
                            center_id=ids.center,
                        )
                    started.set()
                    assert release.wait(10)
                    session.commit()
                return "writer"

            writing = pool.submit(writer)
            assert started.wait(10)
            refreshing = pool.submit(_refresh(ids, _replace(ids.routine, pick_id)))
            try:
                outcome = refreshing.result(timeout=3)
            except FutureTimeout:
                outcome = None
            release.set()
            assert writing.result(timeout=20) == "writer"
            if outcome is None:
                outcome = refreshing.result(timeout=20)
        state = _assert_consistent(ids, f"대체 후보 {racing}")
        if racing == "edited":
            # 바뀐 값이 저장됐다면 **지금 원본과 같은 값**이어야 한다. 본 적 없는 옛 값은 안 된다.
            assert outcome == "refreshed"
            assert state.copies.get(pick_id) in (None, _live(pick_id))
            assert pick_text not in state.copies.values()
        else:
            assert outcome == ("conflict", "GATE_BLOCKED")
            assert _state(ids.doc).__dict__ == before.__dict__, "거절은 문서를 건드리지 않는다"
    finally:
        with Session(engine) as session:
            session.execute(delete(DocumentSource).where(DocumentSource.source_id == pick_id))
            session.execute(delete(RoutineRecord).where(RoutineRecord.id == pick_id))
            session.commit()


def test_f2_refused_refresh_changes_nothing_and_parallel_refresh_does_not_deadlock(
    _schema, deleted_and_live
):
    """거절은 문서를 반쯤 바꾸지 않고, 같은 근거를 동시에 처리해도 교착이 나지 않는다."""
    ids = deleted_and_live
    before = _state(ids.doc)
    # 사라진 근거를 고르지 않으면 거절이다 — 그래도 문서는 그대로다.
    assert _refresh(ids)() == ("conflict", "GATE_BLOCKED")
    assert _state(ids.doc).__dict__ == before.__dict__

    start = Barrier(3)

    def racer(_):
        start.wait(timeout=10)
        return _refresh(ids, _drop(ids.routine))()

    def mutate(_):
        start.wait(timeout=10)
        user = SimpleNamespace(center_id=ids.center, id=ids.user)
        with Session(engine) as session:
            session.execute(select(func.set_config("lock_timeout", "8s", True)))
            update_routine(
                ids.spare,
                RoutineUpdate(
                    date=ids.day,
                    position=1,
                    start=time(11),
                    end=time(12),
                    name="대체용 놀이",
                    plan="",
                    execution="경합 중 수정",
                ),
                session,
                user,
            )
        return "writer"

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = [
            f.result(timeout=30)
            for f in [pool.submit(racer, 0), pool.submit(racer, 1), pool.submit(mutate, 0)]
        ]
    assert "writer" in results
    assert all(r in ("refreshed", ("conflict", "GATE_BLOCKED"), "writer") for r in results), results
    _assert_consistent(ids, "동시 refresh")
