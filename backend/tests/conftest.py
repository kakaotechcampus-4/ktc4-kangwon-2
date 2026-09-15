import os

import pytest

# app.config.Settings 가 import 시점에 DATABASE_URL 을 요구한다 (기본값 없음).
# 여기 넣는 값은 일부러 못 붙는 주소다 — create_engine 은 연결을 열지 않아서
# import 는 통과하고, /health/ready 가 SessionLocal() 시점에 터져 503 을 낸다.
# 로직이 있는 except 분기를 모의 없이 검증하는 게 목적이다.
#
# setdefault 가 아니라 대입이다 — 로컬에 DATABASE_URL 이 export 돼 있으면
# 503 테스트가 사람마다 다르게 돈다. 대입이라 CI job 의 env 도 덮어쓴다:
# 이 job 에 services: db 를 붙여도 그 DB 는 쓰이지 않는다. ADR-011 참조.
os.environ["DATABASE_URL"] = "postgresql+psycopg://t:t@127.0.0.1:1/t"

# app.* 는 반드시 위 대입 뒤에서 import 한다. 위로 올리면 Settings 가 먼저
# 평가돼 ValidationError 로 죽는다 — 지금 통과하는 건 mapping 이 app.config 를
# 안 건드려서일 뿐이다. 여기에 app.main 이나 app.db 를 추가해도 안전하게 둔다.
from app.features.forms import mapping  # noqa: E402


@pytest.fixture
def clean_alias_cache():
    mapping._alias_table.cache_clear()
    yield
    mapping._alias_table.cache_clear()
