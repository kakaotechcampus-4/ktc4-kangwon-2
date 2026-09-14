"""Monthly Template → 활성 Section 구조 Resolver.

docs/open-decisions.md OD-M01 (`RESOLVED_FOR_P0`):
Section의 활성화·표시 방식·계층·빈 값 정책의 결정 주체는 Template instance
data다. **코드에 전역 기본값을 두지 않는다.**

    global display_mode default = 없음

따라서 활성 CONTENT Section이 `display_mode`를 갖지 않으면 조용히 추정하지 않고
Gate 실패를 낸다. 이 모듈에 기본값 상수가 존재하지 않는 것이 계약이다.

이 계층은 파일을 읽지 않는다. JSON Adapter는 후속 Slice에서 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import FailureCategory, blocked
from ..domain.identifiers import SemanticKey
from ..domain.monthly_plan import MonthlySection
from ..domain.monthly_template import (
    DisplayMode,
    MonthlyTemplate,
    SectionRole,
    TemplateSection,
)

RULE_ID = "monthly.template.section_resolution"
RULE_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class ResolvedSection:
    """Generate가 Cell을 만들 때 필요한 최소 정보.

    `cell_count_for(active_week_count)`가 Section 하나가 만들 Cell 개수를 준다.
    """

    template_section: TemplateSection
    semantic_key: SemanticKey

    @property
    def section_key(self) -> str:
        return self.template_section.section_key

    @property
    def role(self) -> SectionRole:
        return self.template_section.role

    @property
    def display_mode(self) -> DisplayMode | None:
        return self.template_section.display_mode

    def cell_count_for(self, active_week_count: int) -> int:
        """이 Section이 생성할 Cell 개수.

        AXIS                     0   구조 축이며 Item을 만들지 않는다
        MONTHLY_MERGED_SUMMARY   1   week_id=None인 Cell 하나
        WEEKLY_CELLS             n   활성 WeekPeriod 수만큼
        """
        if self.role is SectionRole.AXIS:
            return 0
        if self.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY:
            return 1
        if self.display_mode is DisplayMode.WEEKLY_CELLS:
            return active_week_count
        # require_resolvable_display_modes를 통과했다면 도달할 수 없다.
        raise AssertionError(
            f"display_mode가 없는 Section의 Cell 수를 계산할 수 없다: {self.section_key}"
        )


def require_active_template(template: MonthlyTemplate) -> MonthlyTemplate:
    """사람이 승인해 활성화된 Template만 사용한다.

    승인 상태는 Repository가 반환한 Template의 신뢰 가능한 metadata에서만 읽는다.
    외부 요청자가 활성화 여부를 지정할 수 없다.
    """
    if not template.is_active:
        raise blocked(
            "only_human_approved_template_instance_is_eligible",
            FailureCategory.PREREQUISITE_GATE,
            f"Template {template.template_ref}가 활성 상태가 아니다",
        )
    return template


def require_resolvable_display_modes(template: MonthlyTemplate) -> None:
    """활성 CONTENT Section이 모두 display_mode를 갖는지 확인한다.

    전역 기본값으로 조용히 채우지 않는다. 값이 없으면 Gate 실패다(OD-M01).
    """
    missing = [
        s.section_key
        for s in template.activated_sections
        if s.role is SectionRole.CONTENT and not s.has_display_mode
    ]
    if missing:
        raise blocked(
            "active_section_requires_explicit_display_mode",
            FailureCategory.PREREQUISITE_GATE,
            "활성 Section에 display_mode가 없다. 전역 기본값으로 추정하지 않는다: "
            f"{sorted(missing)}",
        )


def resolve_sections(template: MonthlyTemplate) -> tuple[ResolvedSection, ...]:
    """Template 정의에서 **활성 Section만** 골라 해석한다.

    비활성 Section은 생성 대상에서 제외한다. Template 선언 순서를 유지한다.
    """
    require_active_template(template)
    require_resolvable_display_modes(template)
    return tuple(
        ResolvedSection(
            template_section=section,
            semantic_key=SemanticKey.monthly_section(section.section_key),
        )
        for section in template.activated_sections
    )


def build_section_skeleton(
    template: MonthlyTemplate, resolved: tuple[ResolvedSection, ...]
) -> list[MonthlySection]:
    """Item이 비어 있는 MonthlySection 골격을 만든다.

    Cell 채우기는 Generate Use Case의 몫이다. 이 함수는 구조만 만든다.
    """
    return [
        MonthlySection(
            semantic_key=r.semantic_key,
            section_key=r.section_key,
            role=r.role,
            display_mode=r.display_mode,
            empty_value_policy=(
                r.template_section.empty_value_policy
                or template.default_empty_value_policy
            ),
            activated=True,
            parent_section_key=r.template_section.parent_section_key,
            source_label=r.template_section.source_label,
        )
        for r in resolved
    ]


def expected_cell_count(
    resolved: tuple[ResolvedSection, ...], active_week_count: int
) -> int:
    return sum(r.cell_count_for(active_week_count) for r in resolved)
