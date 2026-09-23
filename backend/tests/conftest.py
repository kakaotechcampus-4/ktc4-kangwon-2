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
from pathlib import Path  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import engine, get_session  # noqa: E402
from app.features.forms import mapping  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_alias_cache():
    mapping._alias_table.cache_clear()
    yield
    mapping._alias_table.cache_clear()


@pytest.fixture(scope="session")
def _schema():
    """테스트 DB 에 스키마를 올린다. 이 세션에서 한 번만 돈다.

    **`create_all` 이 아니라 마이그레이션을 돌린다.** `create_all` 은 `models.py` 만
    보므로 마이그레이션이 깨져 있어도 테스트가 통과한다. 배포는 마이그레이션으로
    올라가니 테스트도 같은 것을 써야 한다.

    끝나고 내리지 않는다. CI 는 job 이 끝나면 컨테이너째 사라지고, 로컬은 다시 돌려도
    `upgrade head` 가 멱등이다. 내리다 실패하면 원인 못 찾는 실패가 하나 는다.
    """
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture
def db_session(_schema):
    """진짜 Postgres 를 쓰되 테스트가 끝나면 전부 되돌린다.

    바깥 트랜잭션을 열어두고 그 안에서 돌린 뒤 통째로 롤백한다. 라우터가 부르는
    `session.commit()` 은 `join_transaction_mode="create_savepoint"` 덕에 세이브포인트
    해제로 바뀌어서, 커밋해도 바깥 트랜잭션은 그대로 살아 있다.

    **왜 지우지 않고 롤백인가** — `DELETE FROM` 으로 치우면 지우는 순서를 외래키에 맞춰
    관리해야 하고, 테이블이 늘 때마다 그 목록을 고쳐야 한다. 롤백은 그게 없다.

    앞 테스트가 넣은 행이 남으면 테스트 순서만 바꿔도 결과가 달라진다.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    app.dependency_overrides[get_session] = lambda: session
    try:
        yield session
    finally:
        # 라우터가 끼워둔 가짜 세션까지 같이 걷어낸다. 남으면 다음 테스트가 그걸 쓴다.
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()
