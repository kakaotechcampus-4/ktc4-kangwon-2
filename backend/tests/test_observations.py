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
from app.features.observations.models import (
    AXES,
    DAILY_PLAY_DOMAINS,
    DEFAULT_AXIS,
    DOMAINS,
    NURI_DOMAINS,
    Observation,
)

# CHECK 를 **마지막으로 바꾼** 리비전이다. 처음 만든 리비전을 보면 그 뒤에 넓힌 것을 놓친다.
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/20261021_1600_b8d4f1a92c37_observation_axis.py"
)


def test_축은_둘이고_누리과정_5영역은_그중_하나다():
    assert NURI_DOMAINS == (
        "신체운동·건강",
        "의사소통",
        "사회관계",
        "예술경험",
        "자연탐구",
    )
    assert DAILY_PLAY_DOMAINS == ("일상생활", "놀이활동")
    assert AXES == {"NURI_5": NURI_DOMAINS, "DAILY_PLAY_2": DAILY_PLAY_DOMAINS}
    assert DEFAULT_AXIS == "NURI_5"


def test_DOMAINS_는_두_축을_합친_허용값_전체다():
    """DB 는 두 축을 다 받는다. 「이 원이 쓸 수 있는 값인가」는 라우터가 본다 —
    원이 축을 바꿔도 전에 쌓은 기록이 CHECK 에 걸려 못 읽히면 안 된다."""
    assert DOMAINS == NURI_DOMAINS + DAILY_PLAY_DOMAINS
    assert len(DOMAINS) == 7


def test_model_check_constraint_lists_every_domain():
    ddl = str(CreateTable(Observation.__table__).compile(dialect=postgresql.dialect()))

    assert "ck_observations_domain" in ddl
    for domain in DOMAINS:
        assert f"'{domain}'" in ddl


def test_migration_check_constraint_matches_the_model():
    # 리비전 본문에서 CHECK 한 줄만 꺼내 비교한다. 파일 전체를 보면 comment 에 섞인
    # 영역 이름까지 잡혀서 드리프트를 놓친다.
    # 리비전은 영역 이름을 NURI · DAILY_PLAY 두 상수에 담는다. 그 두 줄만 꺼내 본다 —
    # 파일 전체를 보면 docstring 에 적힌 영역 이름까지 잡혀서 드리프트를 놓친다.
    lines = MIGRATION.read_text(encoding="utf-8").splitlines()
    check = " ".join(line for line in lines if line.startswith(("NURI = ", "DAILY_PLAY = ")))

    for domain in DOMAINS:
        assert f"'{domain}'" in check
    # 모델에 없는 8번째 값이 리비전에만 남는 방향도 막는다.
    assert check.count("'") == 2 * len(DOMAINS)
    # 넓힌 CHECK 가 두 상수를 모두 쓰는지. 한쪽만 쓰면 2축이 DB 에서 막힌다.
    widened = next(
        line for line in lines if "create_check_constraint" in line and "DAILY_PLAY" in line
    )
    assert "{NURI}" in widened
