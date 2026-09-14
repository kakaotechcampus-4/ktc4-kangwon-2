"""Monthly theme Cell의 parent anchor 파생 Rule.

docs/demo-source-of-truth.md §21.1:

    parent_yearly_theme_id는 immutable parent anchor다. 하지만 Yearly value/theme을
    Monthly Cell에 문자 그대로 1:1 복사해야 한다는 Contract는 아니다.

이 모듈은 **M1의 Rule 기본 출력**을 만든다. 상위 확정 값에서 파생하며 창작하지
않는다. 교사 Edit과 Regenerate가 이 값을 바꿀 수 있고(분화 허용), 바뀌어도
`parent_yearly_theme_id`는 변하지 않는다.

Generate와 Regenerate가 같은 Rule을 쓰도록 한곳에 둔다. 두 경로가 서로 다른
값을 만들면 Regenerate가 anchor에서 벗어날 수 있기 때문이다.
"""

from __future__ import annotations

from ..domain.parent_lineage import ParentYearlyLineage
from ..domain.provenance import (
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)

RULE_ID = "monthly.theme.parent_anchor_derivation"
RULE_VERSION = "v1"


def derive_theme_value(lineage: ParentYearlyLineage) -> str:
    """M1의 theme 기본값.

    상위 확정 Yearly value를 그대로 쓴다. 이것은 **M1 시점의 Rule 출력**이며
    "Monthly는 항상 Yearly value를 복사해야 한다"는 장기 Contract가 아니다.
    """
    return lineage.parent_yearly_value


def build_theme_evidence(lineage: ParentYearlyLineage) -> list[EvidenceSource]:
    """theme Cell의 Evidence를 lineage에서만 구성한다.

    LLM 응답이나 요청자 입력에서 읽는 경로가 없다. Yearly `_build_evidence`가
    Rule 결과에서만 Evidence를 세팅하는 것과 같은 방어다.
    """
    return [
        EvidenceSource(
            source_type=EvidenceSourceType.PARENT_PLAN,
            source_id=lineage.parent_yearly_plan_id,
            source_version=lineage.reference_version,
            display_name=lineage.parent_yearly_value,
        ),
        EvidenceSource(
            source_type=EvidenceSourceType.THEME_REFERENCE,
            source_id=lineage.parent_yearly_theme_id,
            source_version=lineage.reference_version,
        ),
    ]


def theme_generation_method() -> GenerationMethodDetail:
    """M1에서 theme은 LLM 없이 Rule로만 파생된다."""
    return GenerationMethodDetail(
        method=GenerationMethod.RULE_ONLY,
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
    )
