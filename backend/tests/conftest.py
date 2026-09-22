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
from app.features.forms import mapping  # noqa: E402


@pytest.fixture
def clean_alias_cache():
    mapping._alias_table.cache_clear()
    yield
    mapping._alias_table.cache_clear()


# ── DB 통합 테스트용 ────────────────────────────────────────────────────
# 여기부터는 실제 PostgreSQL 을 탄다. 검증 로직만 보는 테스트와 달리
# 행이 정말 남는지를 확인하려면 연결이 필요하다.
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db_session():
    """function 스코프 트랜잭션 롤백.

    바깥 트랜잭션을 열어 두고 세션을 그 연결에 묶는다. `join_transaction_mode` 가
    "create_savepoint" 라 라우터의 `session.commit()` 은 savepoint 만 풀고 바깥
    트랜잭션은 살아 있다 — 테스트가 끝나면 통째로 rollback 되어 테스트 데이터가
    DB 에 남지 않는다. 테스트 사이 순서 의존도 생기지 않는다.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def db_client(db_session):
    """`db_session` 을 그대로 쓰는 TestClient.

    요청이 만든 행을 테스트가 같은 트랜잭션에서 다시 읽을 수 있어야 한다.
    오버라이드를 안 하면 라우터가 별도 세션·별도 트랜잭션을 잡아 롤백이 안 걸린다.
    """
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
