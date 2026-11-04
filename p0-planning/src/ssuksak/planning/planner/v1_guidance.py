"""Shared v1 writing context; curriculum scope is not a new cell grounding source."""

from dataclasses import asdict

from ..domain.curriculum_reference import CurriculumCatalog
from ..domain.errors import InvalidDomainValueError

# Shared play expression criteria; callers version their prompts when this changes.
NATURAL_PLAY_GUIDANCE = (
    "놀이마다 중요한 대상과 탐색을 중심으로 자연스럽게 쓴다 — 모든 설명을 재료 준비로 시작하거나 같은 문장 구조 · 맺는말로 되풀이하지 않는다. "
    "준비 제안이라는 뜻을 매번 「제안합니다」로 나타낼 필요는 없다. "
    "놀이 이름은 입력 자료의 익숙하고 자연스러운 표현을 우선하며, 명사를 압축해 대상이 모호한 이름을 만들지 않는다. "
    "설명은 유아가 살펴보거나 표현할 대상과 놀이 행동이 읽히게 쓰고, 추상적인 관심이나 경험의 나열로 끝내지 않는다. "
)

SAFETY_TEXT_GUIDANCE = (
    "안전교육은 유아가 알아듣는 말로, 주의할 대상·상황이나 배울 내용이 식별되는 짧은 한 문장으로 쓴다. "
    "허용 근거 중 그 내용을 분명하게 말할 수 있는 항목을 우선하고, 인용한 근거에 행동이 있을 때는 그 행동을 드러낸다. "
    "뜻을 더하지 않는 계절 수식·서론·부연과 여러 내용의 나열은 줄이되, 「조심해요」처럼 무엇을 배우는지 모호해지도록 줄이지 않는다. "
    "뜻을 가르는 조건·부정 표현은 남기며, 더 구체적으로 보이려고 근거에 없는 대상·행동·재료·절차를 보태지 않는다. "
    "약물 오남용을 다룰 때 「많이 먹지 않아요」처럼 양만 제한해 적게 먹는 것은 괜찮다고 읽힐 문장을 피하고, 근거가 다루는 잘못된 사용의 위험을 분명히 쓴다. "
    "「바르게/안전하게 하는 방법」만으로 끝내지 말고, 근거에 있는 주의 대상이나 상황을 남긴다. 근거가 넓으면 새 행동을 지어내지 말고 무엇을 알아볼지 쓴다. "
)

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
