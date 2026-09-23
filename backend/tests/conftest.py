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

    연결 하나를 열어 트랜잭션을 시작하고, 그 커넥션에 묶인 세션을 FastAPI 의
    `get_session` 대신 쓰게 한다 — 라우터가 실행하는 쿼리와 테스트 코드가 만드는
    픽스처 데이터가 같은(아직 커밋 안 된) 트랜잭션 안에 있어야 서로 보인다.
    라우터가 `commit()`을 부르지 않는(읽기 전용) 범위에서만 안전하다 — 쓰기
    엔드포인트를 테스트할 때는 SAVEPOINT 방식으로 바꿔야 한다.
    """
    connection = app_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_session, None)
        session.close()
        # IntegrityError 를 일부러 일으키는 테스트는 session.close() 시점에 이미
        # 트랜잭션이 끊겨 있다 — 그럴 때 또 rollback() 을 부르면 SAWarning 이 뜬다.
        if transaction.is_active:
            transaction.rollback()
        connection.close()
