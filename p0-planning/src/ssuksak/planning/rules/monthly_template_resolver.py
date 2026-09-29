"""Resolve an approved Monthly Template into deterministic section structure."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.monthly_template import DisplayMode, MonthlyTemplate, SectionRole, TemplateSection
from ..domain.monthly_template_profile import TemplateProfile
from ..domain.monthly_template_snapshot import TemplateSnapshot
from .errors import MonthlyRuleError

RULE_ID = "monthly.template.section_resolution"
RULE_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class ResolvedSection:
    template_section: TemplateSection

    @property
    def section_key(self) -> str:
        return self.template_section.section_key

    def cell_count_for(self, active_week_count: int) -> int:
        if type(active_week_count) is not int or active_week_count < 0:
            raise MonthlyRuleError(RULE_ID, "active_week_count must be non-negative")
        if self.template_section.role is SectionRole.AXIS:
            return 0
        if self.template_section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY:
            return 1
        if self.template_section.display_mode is DisplayMode.WEEKLY_CELLS:
            return active_week_count
        raise MonthlyRuleError(
            RULE_ID, f"active content section lacks display mode: {self.section_key}"
        )


def resolve_sections(template: MonthlyTemplate) -> tuple[ResolvedSection, ...]:
    if not isinstance(template, MonthlyTemplate):
        raise MonthlyRuleError(RULE_ID, "template must be MonthlyTemplate")
    if not template.is_active:
        raise MonthlyRuleError(RULE_ID, f"template is not HUMAN_APPROVED: {template.template_ref}")
    missing = tuple(
        section.section_key
        for section in template.activated_sections
        if section.role is SectionRole.CONTENT and section.display_mode is None
    )
    if missing:
        raise MonthlyRuleError(
            RULE_ID, f"active content sections require display_mode: {missing}"
        )
    return tuple(ResolvedSection(section) for section in template.activated_sections)


def resolve_profile_sections(
    profile: TemplateProfile,
) -> tuple[ResolvedSection, ...]:
    """Resolve an exact Profile without re-reading its base Template artifact."""

    if not isinstance(profile, TemplateProfile):
        raise MonthlyRuleError(RULE_ID, "profile must be TemplateProfile")
    missing = tuple(
        section.section_key
        for section in profile.ordered_sections
        if section.role is SectionRole.CONTENT and section.display_mode is None
    )
    if missing:
        raise MonthlyRuleError(
            RULE_ID, f"active content sections require display_mode: {missing}"
        )
    return tuple(
        ResolvedSection(section) for section in profile.ordered_sections
    )


def resolve_snapshot_sections(
    snapshot: TemplateSnapshot,
) -> tuple[ResolvedSection, ...]:
    """Resolve the immutable structure captured for one generated Plan."""

    if not isinstance(snapshot, TemplateSnapshot):
        raise MonthlyRuleError(RULE_ID, "snapshot must be TemplateSnapshot")
    missing = tuple(
        section.section_key
        for section in snapshot.sections
        if section.role is SectionRole.CONTENT and section.display_mode is None
    )
    if missing:
        raise MonthlyRuleError(
            RULE_ID, f"active content sections require display_mode: {missing}"
        )
    return tuple(ResolvedSection(section) for section in snapshot.sections)


def expected_cell_count(
    sections: tuple[ResolvedSection, ...], active_week_count: int
) -> int:
    return sum(section.cell_count_for(active_week_count) for section in sections)
