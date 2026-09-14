"""JSON 파일 기반 ThemeReferenceRepository.

CLAUDE.md §17: 개발/테스트 단계의 가역 Adapter이며 최종 PostgreSQL 구현과
동일시하지 않는다.

**활성화 판정**
`activation_status`는 파일의 `review.domain_owner_approval`에서만 읽는다.
외부 요청자가 지정할 수 없다. 현재 저장소의 catalog는
`PENDING_HUMAN_REVIEW`이므로 이 Adapter로 로드하면 운영 성공 경로가 차단된다.
이는 의도된 동작이다(CLAUDE.md §8).

테스트는 `activation_override`로 승인 상태를 주입한다. 파일을 수정하지 않는다.

원시 JSON 검증은 theme_reference_schema.py가 담당한다. 필수 필드가 없으면
기본값으로 보정하지 않고 즉시 실패한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..planning.domain.theme_reference import ActivationStatus, ThemeCatalog
from .theme_reference_schema import (
    ThemeReferenceSchemaError,
    parse_theme_reference_payload,
)

__all__ = [
    "DEFAULT_CATALOG_PATH",
    "InMemoryThemeReferenceRepository",
    "JsonThemeReferenceRepository",
    "ThemeReferenceSchemaError",
    "load_catalog_from_dict",
]

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "themes" / "theme_reference_v0.json"
)


def load_catalog_from_dict(
    payload: object, *, activation_override: ActivationStatus | None = None
) -> ThemeCatalog:
    """검증을 거쳐 domain ThemeCatalog로 변환한다."""
    return parse_theme_reference_payload(
        payload, activation_override=activation_override
    )


class JsonThemeReferenceRepository:
    """단일 JSON Catalog 파일을 읽는 Repository."""

    def __init__(
        self,
        path: Path | str = DEFAULT_CATALOG_PATH,
        *,
        activation_override: ActivationStatus | None = None,
    ) -> None:
        self._path = Path(path)
        self._activation_override = activation_override
        self._catalog: ThemeCatalog | None = None

    def _load(self) -> ThemeCatalog:
        if self._catalog is None:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            self._catalog = load_catalog_from_dict(
                payload, activation_override=self._activation_override
            )
        return self._catalog

    def get_catalog(self, catalog_id: str, catalog_version: str) -> ThemeCatalog | None:
        catalog = self._load()
        if catalog.catalog_id != catalog_id:
            return None
        if catalog.catalog_version != catalog_version:
            return None
        return catalog


class InMemoryThemeReferenceRepository:
    """테스트에서 Catalog를 직접 구성·변조하기 위한 Repository.

    tests/golden/yearly_cases.json case 9의 `catalog_mutation`이 필요로 한다.
    """

    def __init__(self, catalogs: list[ThemeCatalog] | None = None) -> None:
        self._catalogs = list(catalogs or [])

    def add(self, catalog: ThemeCatalog) -> None:
        self._catalogs.append(catalog)

    def get_catalog(self, catalog_id: str, catalog_version: str) -> ThemeCatalog | None:
        for c in self._catalogs:
            if c.catalog_id == catalog_id and c.catalog_version == catalog_version:
                return c
        return None
