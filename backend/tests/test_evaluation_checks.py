"""자기 점검 체크 저장 통합 테스트. 실제 DB 를 쓰고 시각은 직접 넘긴다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from queue import Queue
from threading import Event
from time import monotonic, sleep

import pytest
from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.db import engine
from app.features.centers.models import Center
from app.features.evaluation.models import EvaluationCheck
from app.features.evaluation.service import InvalidChecks, read_checks, save_checks
from app.shared.school_year import KST

ALLOWED = frozenset({"6-3-1", "6-3-2", "6-3-3"})
T0 = datetime(2026, 10, 4, 0, 0, tzinfo=UTC)


@pytest.fixture
def center(db_session):
    row = Center(
        name="테스트어린이집",
        director_name="김원장",
        region_sido="충청북도",
        region_sigungu="충주시",
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_first_check_and_repeated_check_keep_the_first_time(db_session, center):
    save_checks(db_session, center.id, T0, [("6-3-1", True)], ALLOWED)
    assert read_checks(db_session, center.id, 2026) == {"6-3-1": T0}

    save_checks(db_session, center.id, T0 + timedelta(hours=1), [("6-3-1", True)], ALLOWED)

    assert read_checks(db_session, center.id, 2026) == {"6-3-1": T0}
    assert db_session.query(EvaluationCheck).count() == 1


def test_uncheck_removes_the_check_and_deletes_the_row(db_session, center):
    save_checks(db_session, center.id, T0, [("6-3-1", True)], ALLOWED)
    now = T0 + timedelta(minutes=1)

    save_checks(db_session, center.id, now, [("6-3-1", False)], ALLOWED)

    assert read_checks(db_session, center.id, 2026) == {}
    assert db_session.query(EvaluationCheck).count() == 0


def test_recheck_immediately_creates_a_new_time(db_session, center):
    save_checks(db_session, center.id, T0, [("6-3-1", True)], ALLOWED)
    now = T0 + timedelta(minutes=1)
    save_checks(db_session, center.id, now, [("6-3-1", False)], ALLOWED)

    save_checks(db_session, center.id, now, [("6-3-1", True)], ALLOWED)

    assert read_checks(db_session, center.id, 2026) == {"6-3-1": now}
    assert db_session.query(EvaluationCheck).one().checked_at == now


def test_uncheck_without_an_existing_check_creates_no_row(db_session, center):
    save_checks(db_session, center.id, T0, [("6-3-1", False)], ALLOWED)

    assert read_checks(db_session, center.id, 2026) == {}
    assert db_session.query(EvaluationCheck).count() == 0


def test_bulk_check_preserves_existing_check_time(db_session, center):
    save_checks(db_session, center.id, T0, [("6-3-1", True)], ALLOWED)
    now = T0 + timedelta(hours=1)

    save_checks(
        db_session,
        center.id,
        now,
        [("6-3-1", True), ("6-3-2", True), ("6-3-3", True)],
        ALLOWED,
    )

    assert read_checks(db_session, center.id, 2026) == {
        "6-3-1": T0,
        "6-3-2": now,
        "6-3-3": now,
    }


def test_invalid_checks_report_all_keys_in_request_order_and_save_nothing(db_session, center):
    save_checks(db_session, center.id, T0, [("6-3-1", True)], ALLOWED)
    # 중복을 나중에 발견해도 첫 등장 순서다. 같은 오류 키는 한 번만 낸다.
    checks = [
        ("6-3-1", False),
        ("6-3-9", True),
        ("4-1-1", True),
        ("6-3-2", True),
        ("6-3-1", True),
        ("6-3-9", False),
    ]

    with pytest.raises(InvalidChecks) as error:
        save_checks(db_session, center.id, T0 + timedelta(hours=1), checks, ALLOWED)

    assert error.value.elements == ["6-3-1", "6-3-9", "4-1-1"]
    assert read_checks(db_session, center.id, 2026) == {"6-3-1": T0}
    row = db_session.query(EvaluationCheck).one()
    assert row.checked_at == T0


def test_school_year_uses_kst_boundary_and_retains_previous_year(db_session, center):
    # UTC 로는 아직 2월이어도 KST 3월 1일부터 새 학년도다.
    march = datetime(2027, 3, 1, tzinfo=KST).astimezone(UTC)
    february = datetime(2027, 2, 28, tzinfo=KST).astimezone(UTC)
    save_checks(db_session, center.id, march, [("6-3-1", True)], ALLOWED)
    assert read_checks(db_session, center.id, 2027) == {"6-3-1": march}
    assert read_checks(db_session, center.id, 2026) == {}

    save_checks(db_session, center.id, february, [("6-3-1", True)], ALLOWED)
    save_checks(db_session, center.id, march, [("6-3-1", True)], ALLOWED)

    assert read_checks(db_session, center.id, 2026) == {"6-3-1": february}
    assert read_checks(db_session, center.id, 2027) == {"6-3-1": march}
    assert db_session.query(EvaluationCheck).count() == 2


def test_checks_are_isolated_by_center(db_session, center):
    other = Center(
        name="다른어린이집",
        director_name="박원장",
        region_sido="충청북도",
        region_sigungu="충주시",
    )
    db_session.add(other)
    db_session.flush()
    save_checks(db_session, center.id, T0, [("6-3-1", True)], ALLOWED)
    assert read_checks(db_session, other.id, 2026) == {}
    now = T0 + timedelta(minutes=1)
    save_checks(db_session, other.id, now, [("6-3-1", True), ("6-3-2", True)], ALLOWED)

    assert read_checks(db_session, center.id, 2026) == {"6-3-1": T0}
    assert read_checks(db_session, other.id, 2026) == {"6-3-1": now, "6-3-2": now}


def test_naive_now_raises_value_error(db_session, center):
    with pytest.raises(ValueError):
        save_checks(db_session, center.id, T0.replace(tzinfo=None), [("6-3-1", True)], ALLOWED)

    assert db_session.query(EvaluationCheck).count() == 0


def test_concurrent_bulk_checks_match_serial_execution(_schema):
    """엇갈린 두 「전체 체크」가 차례로 한 결과와 같다 — 기다리는 동안 생긴 줄을 놓치지 않는다."""
    with Session(engine) as session:
        center = Center(
            name="동시 체크", director_name="교사", region_sido="서울", region_sigungu="종로"
        )
        session.add(center)
        session.flush()
        center_id = center.id
        save_checks(session, center_id, T0, [("6-3-2", True)], ALLOWED)
        session.commit()
    first_done, release_first = Event(), Event()
    second_pid = Queue()
    lock_wait = text("SELECT EXISTS (SELECT FROM pg_locks WHERE NOT granted AND pid = :pid)")

    def save(first):
        with Session(engine) as session:
            session.execute(text("SET LOCAL statement_timeout = '15s'"))  # SQL 대기 제한
            if not first:
                second_pid.put(session.scalar(text("SELECT pg_backend_pid()")))
            now = T0 + timedelta(seconds=60 if first else 65)
            save_checks(session, center_id, now, [("6-3-1", first), ("6-3-2", not first)], ALLOWED)
            if first:
                first_done.set()
                assert release_first.wait(timeout=30)
            session.commit()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(save, True)
            try:
                assert first_done.wait(timeout=5)
                deadline = monotonic() + 10
                second = executor.submit(save, False)
                pid = second_pid.get(timeout=max(0, deadline - monotonic()))
                while monotonic() < deadline:
                    # B 의 DB 연결만 확인한다. 매번 새 트랜잭션으로 잠금 대기를 읽는다.
                    with engine.connect() as connection:
                        waiting = connection.scalar(lock_wait, {"pid": pid})
                    if waiting:
                        break
                    sleep(0.01)
                else:
                    pytest.fail("B 가 잠금을 기다리지 않았다")
            finally:
                release_first.set()
            first.result(timeout=10)
            second.result(timeout=10)
        with Session(engine) as session:
            assert read_checks(session, center_id, 2026) == {"6-3-2": T0 + timedelta(seconds=65)}
    finally:
        with Session(engine) as session:
            session.execute(delete(EvaluationCheck).where(EvaluationCheck.center_id == center_id))
            session.execute(delete(Center).where(Center.id == center_id))
            session.commit()
