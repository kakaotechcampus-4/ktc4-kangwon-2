"""Shared v1 writing context; curriculum scope is not a new cell grounding source."""

from dataclasses import asdict

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.errors import InvalidDomainValueError

V1_GUIDANCE = """
누리과정 참고 내용은 교육적 방향을 살피는 맥락이다. 매달 5영역을 모두 넣거나
연령별로 내용 ID를 허용·금지하지 않는다. 활동·도구의 연령 적합성과 안전 기준은 지킨다.
연간은 월 주제의 범위를 짧고 익숙한 말로 나누고, 월간은 그 범위의 예상 경험을,
주간은 부모 월간에 맞는 경험을 조금 더 구체적으로 쓴다.
유아의 선택과 놀이가 달라질 여지를 두고, 행동 순서·완성품·발달 효과를 강제하지 않는다.
확인하지 않은 보유 재료·시설·유아 반응을 사실로 쓰지 않는다.
같은 '알아보기/놀이하기'를 덧붙이기보다 대상과 경험의 차이가 드러나게 쓴다.
curriculum_context는 grounding_refs나 reference_id의 새 허용 목록이 아니다.
출력에는 내부 ID·출처 표기를 넣지 않고, 기존 칸별 근거 규칙을 그대로 따른다.
"""


def curriculum_context(catalog: CurriculumCatalog) -> dict[str, object]:
    if not isinstance(catalog, CurriculumCatalog) or not catalog.is_active:
        raise InvalidDomainValueError(
            "v1 curriculum context requires an approved Catalog"
        )
    return {
        "catalog_id": catalog.catalog_id,
        "catalog_version": catalog.catalog_version,
        "purpose": "EDUCATIONAL_CONTEXT_ONLY",
        "contents": [asdict(content) for content in catalog.contents],
    }


def curriculum_source_refs(catalog: CurriculumCatalog | None) -> frozenset[str]:
    if catalog is None:
        return frozenset()
    return frozenset(
        (
            catalog.catalog_id,
            catalog.catalog_version,
            *(c.content_id for c in catalog.contents),
        )
    )
