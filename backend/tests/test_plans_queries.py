"""확정 월간계획안 조회 (§12 지표 4-1 이 쓴다)."""

import pytest

from app.features.centers.models import Center
from app.features.plans.models import Plan
from app.features.plans.queries import confirmed_monthly_plans


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


@pytest.fixture
def other_center(db_session):
    row = Center(
        name="남의어린이집",
        director_name="박원장",
        region_sido="강원특별자치도",
        region_sigungu="춘천시",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _month(year, month):
    return {"target_month": {"calendar_year": year, "calendar_month": month}}


def _plan(center_id, plan_ref, *, kind="monthly", status="CONFIRMED", classroom="1", body=None):
    return Plan(
        plan_ref=plan_ref,
        center_id=center_id,
        kind=kind,
        school_year=2026,
        classroom_ref=classroom,
        status=status,
        body=_month(2026, 10) if body is None else body,
    )


def test_확정된_월간만_준다(db_session, center):
    db_session.add_all(
        [
            _plan(center.id, "m-1"),
            _plan(center.id, "m-2", status="DRAFT", body=_month(2026, 11)),
            _plan(center.id, "a-1", kind="annual", body={}),
        ]
    )
    db_session.flush()
    plans = confirmed_monthly_plans(db_session, center.id)
    assert [(p.class_id, p.year, p.month) for p in plans] == [(1, 2026, 10)]


def test_남의_원은_안_준다(db_session, center, other_center):
    db_session.add_all([_plan(center.id, "m-1"), _plan(other_center.id, "m-2", classroom="9")])
    db_session.flush()
    plans = confirmed_monthly_plans(db_session, center.id)
    assert [p.class_id for p in plans] == [1]


def test_대상_월을_못_읽는_행은_건너뛴다(db_session, center):
    """조용히 틀린 숫자를 내는 것보다 안 세는 쪽이 낫다 — 「부족」은 교사가 보고 고친다."""
    db_session.add_all(
        [
            _plan(center.id, "m-1", body={}),
            _plan(center.id, "m-2", body={"target_month": {}}),
            _plan(center.id, "m-3", classroom="반이름"),
            _plan(center.id, "m-4", classroom="2"),
        ]
    )
    db_session.flush()
    plans = confirmed_monthly_plans(db_session, center.id)
    assert [(p.class_id, p.year, p.month) for p in plans] == [(2, 2026, 10)]
