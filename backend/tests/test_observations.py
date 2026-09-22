"""관찰 기록 테이블. 계약은 docs/api-spec.md §10 이다.

DB 를 타지 않는 범위만 다룬다 — 저장·조회는 `POST · GET /api/observations` PR 에서 붙인다.

여기서 지키는 것은 **5영역 목록이 두 군데 있다는 사실** 하나다. 모델은 DOMAINS 를 보고
마이그레이션은 문자열을 박았다(리비전은 스냅샷이라 app 코드를 import 하면 안 된다).
한쪽만 고치면 교사가 고른 정상 영역을 DB 가 거부하고, 파일럿 중에 500 이 난다.
"""

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.features.centers import models as _centers  # noqa: F401  FK 대상 먼저 등록
from app.features.observations.models import DOMAINS, Observation

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/20260922_1546_3e5298ab9396_add_observations_table.py"
)


def test_domains_are_the_five_nuri_areas():
    assert DOMAINS == (
        "신체운동·건강",
        "의사소통",
        "사회관계",
        "예술경험",
        "자연탐구",
    )


def test_model_check_constraint_lists_every_domain():
    ddl = str(CreateTable(Observation.__table__).compile(dialect=postgresql.dialect()))

    assert "ck_observations_domain" in ddl
    for domain in DOMAINS:
        assert f"'{domain}'" in ddl


def test_migration_check_constraint_matches_the_model():
    # 리비전 본문에서 CHECK 한 줄만 꺼내 비교한다. 파일 전체를 보면 comment 에 섞인
    # 영역 이름까지 잡혀서 드리프트를 놓친다.
    check = next(
        line
        for line in MIGRATION.read_text(encoding="utf-8").splitlines()
        if "CheckConstraint" in line
    )

    for domain in DOMAINS:
        assert f"'{domain}'" in check
    # 모델에 없는 6번째 값이 리비전에만 남는 방향도 막는다.
    assert check.count("'") == 2 * len(DOMAINS) + 2  # 영역 5개 + name=op.f('...')
