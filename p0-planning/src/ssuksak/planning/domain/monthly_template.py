"""Immutable Monthly Template values interpreted by deterministic rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError


class DisplayMode(str, Enum):
    WEEKLY_CELLS = "WEEKLY_CELLS"
    MONTHLY_MERGED_SUMMARY = "MONTHLY_MERGED_SUMMARY"


class EmptyValuePolicy(str, Enum):
    RENDER_EMPTY_CELL = "RENDER_EMPTY_CELL"


class SectionRole(str, Enum):
    CONTENT = "CONTENT"
    AXIS = "AXIS"


class SectionCategory(str, Enum):
    DEFAULT = "DEFAULT"
    OPTIONAL = "OPTIONAL"
    TEMPLATE_SPECIFIC = "TEMPLATE_SPECIFIC"


class SemanticVariant(str, Enum):
    SUBTHEME = "SUBTHEME"
    EXPECTED_PLAY = "EXPECTED_PLAY"
    WEEKLY_THEME = "WEEKLY_THEME"
    NEUTRAL = "NEUTRAL"


MAX_HIERARCHY_DEPTH = 2


@dataclass(frozen=True, slots=True)
class TemplateRef:
    template_id: str
    template_version: str

    def __post_init__(self) -> None:
        for name in ("template_id", "template_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidDomainValueError(
                    f"TemplateRef.{name} must be a non-blank string"
                )

    def __str__(self) -> str:
        return f"{self.template_id}/{self.template_version}"


@dataclass(frozen=True, slots=True)
class TemplateSection:
    section_key: str
    role: SectionRole
    activated: bool
    display_mode: DisplayMode | None = None
    empty_value_policy: EmptyValuePolicy | None = None
    parent_section_key: str | None = None
    source_label: str | None = None
    depth: int = 1
    display_label: str | None = None
    order: int = 0
    semantic_variant: SemanticVariant | None = None
    category: SectionCategory = SectionCategory.TEMPLATE_SPECIFIC
    required_for_generation: bool = False
    visible: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.section_key, str) or not self.section_key.strip():
            raise InvalidDomainValueError(
                "TemplateSection.section_key must be non-blank"
            )
        if not isinstance(self.role, SectionRole):
            raise InvalidDomainValueError("TemplateSection.role is invalid")
        if type(self.activated) is not bool:
            raise InvalidDomainValueError(
                "TemplateSection.activated must be a boolean"
            )
        if self.display_mode is not None and not isinstance(
            self.display_mode, DisplayMode
        ):
            raise InvalidDomainValueError("TemplateSection.display_mode is invalid")
        if self.empty_value_policy is not None and not isinstance(
            self.empty_value_policy, EmptyValuePolicy
        ):
            raise InvalidDomainValueError(
                "TemplateSection.empty_value_policy is invalid"
            )
        if type(self.depth) is not int or not 1 <= self.depth <= MAX_HIERARCHY_DEPTH:
            raise InvalidDomainValueError(
                f"TemplateSection.depth must be 1 through {MAX_HIERARCHY_DEPTH}"
            )
        if self.depth == 1 and self.parent_section_key is not None:
            raise InvalidDomainValueError(
                "A depth-one TemplateSection cannot have a parent"
            )
        if self.depth > 1 and (
            not isinstance(self.parent_section_key, str)
            or not self.parent_section_key.strip()
        ):
            raise InvalidDomainValueError(
                "A nested TemplateSection requires parent_section_key"
            )
        if self.role is SectionRole.AXIS and self.display_mode is not None:
            raise InvalidDomainValueError(
                "An AXIS TemplateSection cannot declare display_mode"
            )
        if self.source_label is not None and (
            not isinstance(self.source_label, str) or not self.source_label.strip()
        ):
            raise InvalidDomainValueError(
                "TemplateSection.source_label must be non-blank when set"
            )
        if self.display_label is not None and (
            not isinstance(self.display_label, str) or not self.display_label.strip()
        ):
            raise InvalidDomainValueError(
                "TemplateSection.display_label must be non-blank when set"
            )
        if type(self.order) is not int or self.order < 0:
            raise InvalidDomainValueError(
                "TemplateSection.order must be a non-negative integer"
            )
        if self.semantic_variant is not None and not isinstance(
            self.semantic_variant, SemanticVariant
        ):
            raise InvalidDomainValueError(
                "TemplateSection.semantic_variant is invalid"
            )
        if self.section_key == "focus" and self.semantic_variant is None:
            raise InvalidDomainValueError(
                "The focus TemplateSection requires semantic_variant"
            )
        if self.section_key != "focus" and self.semantic_variant is not None:
            raise InvalidDomainValueError(
                "semantic_variant is supported only by the focus TemplateSection"
            )
        if not isinstance(self.category, SectionCategory):
            raise InvalidDomainValueError("TemplateSection.category is invalid")
        if type(self.required_for_generation) is not bool:
            raise InvalidDomainValueError(
                "TemplateSection.required_for_generation must be a boolean"
            )
        if type(self.visible) is not bool:
            raise InvalidDomainValueError(
                "TemplateSection.visible must be a boolean"
            )
        if self.visible and self.display_label is None:
            raise InvalidDomainValueError(
                "A visible TemplateSection requires display_label"
            )
        if self.required_for_generation and not self.activated:
            raise InvalidDomainValueError(
                "A required TemplateSection must be activated"
            )


@dataclass(frozen=True, slots=True)
class MonthlyTemplate:
    template_ref: TemplateRef
    normative_status: str
    sections: tuple[TemplateSection, ...]
    hierarchy_max_depth: int = MAX_HIERARCHY_DEPTH
    default_empty_value_policy: EmptyValuePolicy = (
        EmptyValuePolicy.RENDER_EMPTY_CELL
    )
    runtime_active: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.template_ref, TemplateRef):
            raise InvalidDomainValueError(
                "MonthlyTemplate.template_ref must be TemplateRef"
            )
        if not isinstance(self.normative_status, str) or not self.normative_status.strip():
            raise InvalidDomainValueError(
                "MonthlyTemplate.normative_status must be non-blank"
            )
        if not isinstance(self.sections, tuple) or not self.sections:
            raise InvalidDomainValueError(
                "MonthlyTemplate.sections must be a non-empty tuple"
            )
        if not all(isinstance(section, TemplateSection) for section in self.sections):
            raise InvalidDomainValueError(
                "MonthlyTemplate.sections must contain TemplateSection values"
            )
        if (
            type(self.hierarchy_max_depth) is not int
            or not 1 <= self.hierarchy_max_depth <= MAX_HIERARCHY_DEPTH
        ):
            raise InvalidDomainValueError(
                f"MonthlyTemplate.hierarchy_max_depth must be 1 through "
                f"{MAX_HIERARCHY_DEPTH}"
            )
        if not isinstance(self.default_empty_value_policy, EmptyValuePolicy):
            raise InvalidDomainValueError(
                "MonthlyTemplate.default_empty_value_policy is invalid"
            )
        if type(self.runtime_active) is not bool:
            raise InvalidDomainValueError(
                "MonthlyTemplate.runtime_active must be a boolean"
            )

        keys = tuple(section.section_key for section in self.sections)
        if len(set(keys)) != len(keys):
            raise InvalidDomainValueError(
                "MonthlyTemplate contains duplicate section_key values"
            )
        key_set = set(keys)
        orders = tuple(section.order for section in self.sections)
        if len(set(orders)) != len(orders):
            raise InvalidDomainValueError(
                "MonthlyTemplate contains duplicate TemplateSection order values"
            )
        for section in self.sections:
            if (
                section.parent_section_key is not None
                and section.parent_section_key not in key_set
            ):
                raise InvalidDomainValueError(
                    "TemplateSection parent_section_key must resolve in its Template"
                )

    def section(self, section_key: str) -> TemplateSection | None:
        return next(
            (section for section in self.sections if section.section_key == section_key),
            None,
        )

    @property
    def activated_sections(self) -> tuple[TemplateSection, ...]:
        return tuple(
            sorted(
                (section for section in self.sections if section.activated),
                key=lambda section: section.order,
            )
        )

    @property
    def inactive_sections(self) -> tuple[TemplateSection, ...]:
        return tuple(
            sorted(
                (section for section in self.sections if not section.activated),
                key=lambda section: section.order,
            )
        )

    @property
    def is_active(self) -> bool:
        return self.runtime_active
