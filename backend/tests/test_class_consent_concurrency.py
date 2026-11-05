"""동의 끄기와 아이 등록이 겹쳐도 「아이는 있는데 동의 없는 반」이 생기지 않는다 (ADR-062).

두 경로(`PATCH /api/classes/{id}` · `POST /api/classes/{id}/children`)는 같은 반 행을 잠근 뒤
검사한다. 잠금이 없으면 둘 다 상대가 커밋하기 전의 값을 읽고 둘 다 통과한다.
실제 PostgreSQL 의 서로 다른 트랜잭션으로 돌린다.
`test_child_allocation_concurrency.py` 와 같은 방식이다.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import engine
from app.features.centers import router as centers_router
from app.features.centers.models import Center, Child, Class
from app.features.centers.schemas import ClassUpdate
from app.features.children import router as children_router
from app.features.children.schemas import ChildCreate


def _blocked(exc: HTTPException) -> str:
    assert (exc.status_code, exc.detail["code"]) == (409, "GATE_BLOCKED")
    return "blocked"


@pytest.mark.parametrize("attempt", range(3))
def test_동의_끄기와_아이_등록이_겹쳐도_아이는_있는데_동의_없는_반이_생기지_않는다(
    _schema, monkeypatch, attempt
):
    # 별도 연결에 보여야 하므로 커밋하고, 만든 행만 finally 에서 지운다.
    with Session(engine) as session:
        center = Center(
            name="가명 경합 테스트",
            director_name="테스트",
            region_sido="테스트",
            region_sigungu="테스트",
        )
        session.add(center)
        session.flush()
        # 주인 없는 옛 반(OPEN)이라 가짜 계정으로도 쓰기 권한을 지난다.
        classroom = Class(
            center_id=center.id,
            name="경합반",
            school_year=2026,
            age_min=3,
            age_max=3,
            teacher_name="테스트",
            consent_confirmed_at=datetime.now(UTC),
        )
        session.add(classroom)
        session.flush()
        center_id, class_id = center.id, classroom.id
        session.commit()
    user = SimpleNamespace(center_id=center_id, id=None)

    # 출발선은 권한 확인 바로 뒤다. 잠그는 줄 앞에 두면, 잠금을 지우는 회귀가 생겼을 때
    # 출발선도 같이 사라져 엉뚱한 이유(대기 시간 초과)로 실패한다.
    barrier = Barrier(2)

    def gate(original):
        def checked(*args, **kwargs):
            result = original(*args, **kwargs)
            barrier.wait(timeout=10)
            return result

        return checked

    monkeypatch.setattr(centers_router, "require_own_class", gate(centers_router.require_own_class))
    monkeypatch.setattr(
        children_router, "require_own_class", gate(children_router.require_own_class)
    )

    def turn_off_consent():
        with Session(engine) as session:
            try:
                centers_router.patch_class(
                    class_id, ClassUpdate(consent_confirmed=False), session, user
                )
                return "consent_off"
            except HTTPException as exc:
                return _blocked(exc)

    def add_child():
        with Session(engine) as session:
            try:
                children_router.create_child(class_id, ChildCreate(name="박서준"), session, user)
                return "child_added"
            except HTTPException as exc:
                return _blocked(exc)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            off, add = executor.submit(turn_off_consent), executor.submit(add_child)
            results = {off.result(), add.result()}
        with Session(engine) as session:
            children = session.scalars(select(Child).where(Child.class_id == class_id)).all()
            consent = session.get(Class, class_id).consent_confirmed_at

        # 잠금이 순서를 세운다 — 먼저 잡은 쪽이 되고, 나중 쪽은 바뀐 값을 보고 막힌다.
        assert results in ({"consent_off", "blocked"}, {"child_added", "blocked"})
        assert not (children and consent is None)
    finally:
        with Session(engine) as session:
            session.execute(delete(Child).where(Child.class_id == class_id))
            session.execute(delete(Class).where(Class.id == class_id))
            session.execute(delete(Center).where(Center.id == center_id))
            session.commit()
