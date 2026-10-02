"""실제 PostgreSQL의 서로 다른 트랜잭션으로 반 잠금을 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import engine
from app.features.centers.models import Center, Child, Class
from app.features.children.router import create_child
from app.features.children.schemas import ChildCreate
from app.shared.childCode import NameTable


@pytest.mark.parametrize(
    "names",
    [
        ("박서준", "김하윤"),
        ("김하윤", "박민준"),
        ("박민준", "김민준"),
    ],
)
def test_concurrent_registration_preserves_the_whole_class(_schema, names):
    # 이 fixture는 별도 연결에 보여야 하므로 커밋하고, 생성한 행만 finally에서 지운다.
    with Session(engine) as session:
        center = Center(
            name="가명 동시성 테스트",
            director_name="테스트",
            region_sido="테스트",
            region_sigungu="테스트",
        )
        session.add(center)
        session.flush()
        classroom = Class(
            center_id=center.id,
            name="테스트반",
            school_year=2026,
            age_min=3,
            age_max=3,
            teacher_name="테스트",
        )
        session.add(classroom)
        session.flush()
        center_id, class_id = center.id, classroom.id
        session.commit()
    barrier = Barrier(2)

    class ConcurrentSession(Session):
        def get(self, entity, ident, **kwargs):
            if entity is Class and kwargs.get("with_for_update"):
                barrier.wait(timeout=10)
            return super().get(entity, ident, **kwargs)

    def register(name):
        with ConcurrentSession(engine) as session:
            try:
                create_child(
                    class_id, ChildCreate(name=name), session, SimpleNamespace(center_id=center_id)
                )
                return 201
            except HTTPException as exc:
                assert exc.status_code == 422
                assert exc.detail["code"] == "VALIDATION_FAILED"
                return 422

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(register, names))
        with Session(engine) as session:
            children = list(session.scalars(select(Child).where(Child.class_id == class_id)))
            assert len(children) == results.count(201)
            assert 201 in results
            assert len({c.name for c in children}) == len(children)
            NameTable({c.name: c.code for c in children})
    finally:
        with Session(engine) as session:
            session.execute(delete(Child).where(Child.class_id == class_id))
            session.execute(delete(Class).where(Class.id == class_id))
            session.execute(delete(Center).where(Center.id == center_id))
            session.commit()
