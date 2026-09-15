import os

import pytest

from app.features.forms import mapping

# app.config.Settings 가 import 시점에 DATABASE_URL 을 요구한다 (기본값 없음).
# 여기 넣는 값은 일부러 못 붙는 주소다 — create_engine 은 연결을 열지 않아서
# import 는 통과하고, /health/ready 가 SessionLocal() 시점에 터져 503 을 낸다.
# 로직이 있는 except 분기를 모의 없이 검증하는 게 목적이다.
#
# 여기에 진짜 postgres 를 붙이면 그 테스트가 조용히 무의미해진다. ADR-011 참조.
# setdefault 가 아니라 대입이다 — 로컬에 DATABASE_URL 이 export 돼 있으면
# 503 테스트가 사람마다 다르게 돈다.
os.environ["DATABASE_URL"] = "postgresql+psycopg://t:t@127.0.0.1:1/t"


@pytest.fixture
def clean_alias_cache():
    mapping._alias_table.cache_clear()
    yield
    mapping._alias_table.cache_clear()
