"""Monthly Template 정의 Value Object.

docs/open-decisions.md OD-M01 (`RESOLVED_FOR_P0`):
Section의 활성화·표시 방식·계층·빈 값 정책의 **결정 주체는 Template instance
data**다. 코드에 전역 기본값을 두지 않는다.

    global display_mode default = 없음

이 모듈에 `DEFAULT_DISPLAY_MODE` 같은 상수를 만들면 그 결정을 위반한다.
활성 CONTENT Section이 `display_mode`를 갖지 않으면 조용히 추정하지 않고
Resolver가 Gate 실패를 낸다.

Template A는 국가 표준이 아니라 `SAMPLE_DERIVED_NON_NORMATIVE` product adapter다.

이 계층은 파일을 읽지 않는다. JSON Adapter는 후속 Slice에서 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DisplayMode(str, Enum):
    """Section의 표시 방식.

    **이 값 집합이 영구적으로 전부라고 가정하지 않는다.**
    `monthly_template_a.json`의 `supported_display_modes_extensible = true`이며,
    공립아이사랑어린이집에서 관찰된 inline/tagged 유형은 아직 두 값 중 어느 쪽도
    아니다. 값 추가는 additive 변경으로 허용된다.
    """

    WEEKLY_CELLS = "WEEKLY_CELLS"
    MONTHLY_MERGED_SUMMARY = "MONTHLY_MERGED_SUMMARY"


class EmptyValuePolicy(str, Enum):
    """활성 Section에 값이 없을 때의 정책.

    `RENDER_EMPTY_CELL`은 **표시·구조 정책**이며 모든 semantic content가
    선택사항이라는 뜻이 아니다(2026-09-11 결정). Section별 non-blank 요구는
    Validation이 의미에 따라 별도로 정한다.
    """

    RENDER_EMPTY_CELL = "RENDER_EMPTY_CELL"


class SectionRole(str, Enum):
    """Section의 역할.

    AXIS는 값을 담는 Section이 아니라 축이다. `display_mode`가 적용되지 않고
    Item을 생성하지 않는다.
    """

    CONTENT = "CONTENT"
    AXIS = "AXIS"


MAX_HIERARCHY_DEPTH = 2
"""2단 계층은 판독 10기관 중 4기관에서 관찰되고 3단은 0/10이다.
docs/template-a-validation.md §4.6."""


@dataclass(frozen=True, slots=True)
class TemplateRef:
    template_id: str
    template_version: str

    def __post_init__(self) -> None:
        for name, value in (
            ("template_id", self.template_id),
            ("template_version", self.template_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"TemplateRef.{name}는 비어 있을 수 없다")

    def __str__(self) -> str:
        return f"{self.template_id}/{self.template_version}"


@dataclass(frozen=True, slots=True)
class TemplateSection:
    """Template이 정의하는 Section 하나.

    `display_mode`가 `None`일 수 있다. AXIS Section은 해당 없음이고,
    CONTENT Section은 Template이 아직 값을 정하지 않은 PENDING 상태다.
    둘의 구분은 `role`이 한다.
    """

    section_key: str
    role: SectionRole
    activated: bool
    display_mode: DisplayMode | None = None
    empty_value_policy: EmptyValuePolicy | None = None
    parent_section_key: str | None = None
    source_label: str | None = None
    depth: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.section_key, str) or not self.section_key.strip():
            raise ValueError("TemplateSection.section_key는 비어 있을 수 없다")
        if not 1 <= self.depth <= MAX_HIERARCHY_DEPTH:
            raise ValueError(
                f"Section depth는 1..{MAX_HIERARCHY_DEPTH} 범위여야 한다: "
                f"{self.section_key} depth={self.depth}"
            )
        if self.depth == 1 and self.parent_section_key is not None:
            raise ValueError(
                f"depth 1 Section은 parent를 가질 수 없다: {self.section_key}"
            )
        if self.depth > 1 and self.parent_section_key is None:
            raise ValueError(
                f"depth {self.depth} Section은 parent_section_key가 필요하다: "
                f"{self.section_key}"
            )
        if self.role is SectionRole.AXIS and self.display_mode is not None:
            raise ValueError(
                f"AXIS Section에는 display_mode가 적용되지 않는다: {self.section_key}"
            )

    @property
    def has_display_mode(self) -> bool:
        return self.display_mode is not None


@dataclass(frozen=True, slots=True)
class MonthlyTemplate:
    """Template instance 하나.

    전역 기본값을 두지 않으므로 Section 해석에 필요한 모든 정책이 이 객체 안에 있다.
    """

    template_ref: TemplateRef
    normative_status: str
    sections: tuple[TemplateSection, ...]
    hierarchy_max_depth: int = MAX_HIERARCHY_DEPTH
    default_empty_value_policy: EmptyValuePolicy = EmptyValuePolicy.RENDER_EMPTY_CELL
    runtime_active: bool = False
    _by_key: dict[str, TemplateSection] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValueError("MonthlyTemplate은 Section을 하나 이상 가져야 한다")
        if self.hierarchy_max_depth > MAX_HIERARCHY_DEPTH:
            raise ValueError(
                f"P0는 {MAX_HIERARCHY_DEPTH}단 계층까지만 기본 지원한다: "
                f"{self.hierarchy_max_depth}"
            )
        index: dict[str, TemplateSection] = {}
        for section in self.sections:
            if section.section_key in index:
                raise ValueError(f"Section key가 중복된다: {section.section_key}")
            index[section.section_key] = section
        for section in self.sections:
            parent = section.parent_section_key
            if parent is not None and parent not in index:
                raise ValueError(
                    f"parent_section_key가 Template에 없다: "
                    f"{section.section_key} -> {parent}"
                )
        object.__setattr__(self, "_by_key", index)

    def section(self, section_key: str) -> TemplateSection | None:
        return self._by_key.get(section_key)

    @property
    def activated_sections(self) -> tuple[TemplateSection, ...]:
        return tuple(s for s in self.sections if s.activated)

    @property
    def inactive_sections(self) -> tuple[TemplateSection, ...]:
        return tuple(s for s in self.sections if not s.activated)

    @property
    def is_active(self) -> bool:
        """사람이 승인한 Template만 활성으로 취급한다.

        `runtime_active`는 독립 스위치가 아니라 approval에서 파생된 값이다.
        data/themes/theme_reference_v0.json의 activation 파생 원칙과 동일하다.
        """
        return self.runtime_active
