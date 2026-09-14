"""JSON 파일 기반 ActivityReferenceRepository.

CLAUDE.md §17: 개발/테스트 단계의 가역 Adapter이며 최종 PostgreSQL 구현과
동일시하지 않는다.

**활성화 판정**
`activation_status`는 파일의 `review.domain_owner_approval`에서만 읽는다.
외부 요청자가 지정할 수 없다. 현재 저장소의 catalog는 `PENDING_HUMAN_REVIEW`
이므로 이 Adapter로 로드하면 `is_active`가 False이고 후보 조회가 빈 결과를
반환한다. 이는 의도된 동작이다(CLAUDE.md §8 / OD-N03 D1 결정).

**승인 우회 입력이 없다.** `activation_override` / `approval_override` /
`force_active` 같은 파라미터를 두지 않는다. 승인 상태가 필요한 테스트는
HUMAN_APPROVED인 JSON fixture를 tmp_path에 만들어 이 Adapter로 로드하거나
`ActivityCatalog` Domain 객체를 직접 구성한다. 실제
`data/activities/activity_reference_v0.json`은 수정하지 않는다.

원시 JSON 검증은 activity_reference_schema.py가 담당한다. 필수 필드가 없으면
기본값으로 보정하지 않고 즉시 실패한다. `latest` version 자동 탐색도 없다 —
`get_catalog`은 정확히 일치하는 id/version만 반환한다.

**Runtime Projection (HD-I)**
승인 Catalog는 Human Review / 품질 metadata를 함께 담는 Source of Truth다.
Domain Model을 확장하지 않고 `activity_reference_projection.py`의 allowlist로
review-only 필드만 제거한 뒤 strict schema에 넘긴다. allowlist에 없는 필드는
제거하지 않으므로 기존 strict 검증이 그대로 작동한다.

이 Adapter는 selection logic을 갖지 않는다. 읽기·strict parse·exact 조회·
approval 기반 activation까지만 담당하고 후보 필터는 Domain, 순위는 Rule이
담당한다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from ..planning.domain.activity_reference import ActivityCatalog
from .activity_reference_projection import project_runtime_payload
from .activity_reference_schema import (
    ActivityReferenceSchemaError,
    parse_activity_reference_payload,
)

__all__ = [
    "ActivityReferenceSchemaError",
    "DEFAULT_ACTIVITY_CATALOG_PATH",
    "LEGACY_ACTIVITY_CATALOG_PATH",
    "SUPERSEDED_ACTIVITY_CATALOG_PATHS",
    "InMemoryActivityReferenceRepository",
    "JsonActivityReferenceRepository",
    "load_activity_catalog_from_dict",
    "production_activity_reference_repository",
]

_DATA = Path(__file__).resolve().parents[3] / "data" / "activities"

DEFAULT_ACTIVITY_CATALOG_PATH = _DATA / "activity_reference_v0_2_1.json"
"""Production Activity Catalog. 2026-09-13 승인된 v0.2.1로 전환했다.

**새로 생성되는 Monthly Plan만** 이 default를 pin한다. 이미 다른 version을 pin한
Plan은 자기 lineage를 그대로 쓴다(`SUPERSEDED_ACTIVITY_CATALOG_PATHS`).
"""

SUPERSEDED_ACTIVITY_CATALOG_PATHS: tuple[Path, ...] = (
    _DATA / "activity_reference_v0_2.json",
)
"""default에서 밀려났지만 **아직 해소되어야 하는** 과거 승인 Catalog.

Plan은 생성 시점의 catalog_version을 pin한다(`MonthlyPlan.activity_catalog`).
default가 v0.2.1로 바뀌어도 v0.2.0으로 생성된 Plan의 Regenerate는 v0.2.0을
정확히 다시 찾아야 한다. 그 해소 경로가 여기다.

이것은 fallback이 **아니다.** 요청된 version과 정확히 일치할 때만 반환하며,
못 찾으면 default로 대체하지 않고 실패한다.
"""

LEGACY_ACTIVITY_CATALOG_PATH = _DATA / "activity_reference_v0.json"
"""v0.1.0. 역사적 artifact로 보존한다. Production 기본 경로가 아니다."""


def load_activity_catalog_from_dict(payload: object) -> ActivityCatalog:
    """Runtime projection을 거쳐 검증하고 domain ActivityCatalog로 변환한다.

    승인 artifact는 Human Review / 품질 metadata를 함께 담는다(HD-I 선택지 B).
    Domain Model을 확장하지 않고 adapter에서 **allowlist에 선언된 review
    metadata만** 제거한 뒤 기존 strict schema로 파싱한다.

    알 수 없는 extra field는 제거하지 않으므로 strict schema가 기존대로 거부한다.
    승인 상태는 여전히 `review.domain_owner_approval`에서만 파생된다.
    """
    return parse_activity_reference_payload(project_runtime_payload(payload))


class JsonActivityReferenceRepository:
    """JSON Catalog 파일을 읽는 Repository.

    기본은 파일 하나다. `superseded_paths`를 주면 과거 승인 Catalog도 **정확히
    그 version을 요청받았을 때만** 해소한다. 요청 version이 어디에도 없으면
    None이며 default로 대체하지 않는다 — fallback 경로를 만들지 않는다.
    """

    def __init__(
        self,
        path: Path | str = DEFAULT_ACTIVITY_CATALOG_PATH,
        *,
        superseded_paths: Sequence[Path | str] = (),
    ) -> None:
        self._path = Path(path)
        self._superseded = tuple(Path(p) for p in superseded_paths)
        self._cache: dict[Path, ActivityCatalog] = {}

    def _load(self, path: Path) -> ActivityCatalog:
        cached = self._cache.get(path)
        if cached is None:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached = load_activity_catalog_from_dict(payload)
            self._cache[path] = cached
        return cached

    def get_catalog(
        self, catalog_id: str, catalog_version: str
    ) -> ActivityCatalog | None:
        """정확히 일치하는 catalog_id + catalog_version만 반환한다."""
        for path in (self._path, *self._superseded):
            catalog = self._load(path)
            if catalog.catalog_id != catalog_id:
                continue
            if catalog.catalog_version != catalog_version:
                continue
            return catalog
        return None


def production_activity_reference_repository() -> JsonActivityReferenceRepository:
    """Production / Demo 공용 Activity Reference Repository.

    default는 승인된 v0.2.1이고, v0.2.0으로 생성된 기존 Plan의 pin도 해소한다.
    Demo도 이 함수를 써서 Production과 **같은 승인 Artifact**를 읽는다.
    """
    return JsonActivityReferenceRepository(
        DEFAULT_ACTIVITY_CATALOG_PATH,
        superseded_paths=SUPERSEDED_ACTIVITY_CATALOG_PATHS,
    )


class InMemoryActivityReferenceRepository:
    """테스트에서 Catalog를 직접 구성하기 위한 Repository."""

    def __init__(self, catalogs: list[ActivityCatalog] | None = None) -> None:
        self._catalogs = list(catalogs or [])

    def add(self, catalog: ActivityCatalog) -> None:
        self._catalogs.append(catalog)

    def get_catalog(
        self, catalog_id: str, catalog_version: str
    ) -> ActivityCatalog | None:
        for c in self._catalogs:
            if c.catalog_id == catalog_id and c.catalog_version == catalog_version:
                return c
        return None
