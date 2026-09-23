import os

import pytest

# /health/ready 200 을 실제 DB 로 검증하므로 DATABASE_URL 이 반드시 있어야 한다.
# CI 는 job 의 env 로 준다. 없으면 pydantic 이 "database_url Field required" 로
# 죽는데 원인이 안 보여서, 여기서 먼저 잡고 방법을 알려준다.
if not os.environ.get("DATABASE_URL"):
    raise RuntimeError(
        "DATABASE_URL 이 없다. 로컬에서는:\n"
        "  cp .env.example .env\n"
        "  docker compose up -d db\n"
        "  DATABASE_URL='postgresql+psycopg://ssuksak:<.env 의 비밀번호>"
        "@localhost:5432/ssuksak' pytest"
    )

# app.* 는 위 검사 뒤에서 import 한다. 위로 올리면 Settings 가 먼저 평가돼
# 우리 메시지 대신 pydantic 의 ValidationError 가 나온다.
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import engine as app_engine  # noqa: E402
from app.db import get_session  # noqa: E402
from app.features.forms import mapping  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def clean_alias_cache():
    mapping._alias_table.cache_clear()
    yield
    mapping._alias_table.cache_clear()


@pytest.fixture
def db_session():
    """실제 DB 에 연결하되 테스트가 끝나면 통째로 롤백한다.

    바깥 트랜잭션 하나(`outer`)를 열고 그 안에 SAVEPOINT(`nested`)를 하나 판다.
    라우터가 `session.commit()`을 불러도 SAVEPOINT 까지만 끝나고 바깥 트랜잭션은
    안 끝난다 — `after_transaction_end` 훅이 SAVEPOINT 를 바로 다시 파서 다음
    쿼리도 여전히 롤백 대상 안에 있게 한다. `PUT` 처럼 실제로 커밋하는
    엔드포인트를 테스트하려면 이 방식이 필요하다(단순 트랜잭션 하나로는 커밋이
    바깥 트랜잭션까지 끝내버려서 다음 줄의 `rollback()`이 아무것도 못 되돌린다).
    """
    connection = app_engine.connect()
    outer = connection.begin()
    session = sessionmaker(bind=connection)()
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: object, trans: object) -> None:
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_session, None)
        event.remove(session, "after_transaction_end", _restart_savepoint)
        session.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
