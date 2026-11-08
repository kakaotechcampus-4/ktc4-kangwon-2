"""Immutable Template structure captured when a Monthly Plan is generated."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .errors import InvalidDomainValueError
from .monthly_template import EmptyValuePolicy, RepeatBy, SectionRole, TemplateRef, TemplateSection
from .monthly_template_profile import TemplateProfile, TemplateProfileRef


# Human Decision 2026-11-06 (ADR-066): each weekly activity Section of a v1 monthly Plan
# carries a hidden one-cell-per-week description. Derived by the Core at generation, never a
# Template row; a Snapshot without them (an older Plan) stays as stored.
ACTIVITY_DETAIL_SECTION_KEYS = {
    "outdoor_play": "outdoor_play_detail",
    "indoor_alternative": "indoor_alternative_detail",
}
_DETAIL_LABELS = {"outdoor_play": "바깥놀이 설명", "indoor_alternative": "실내 대체활동 설명"}


def _non_blank(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{path} must be a non-blank string")


@dataclass(frozen=True, slots=True)
class TemplateSnapshot:
    """Self-contained, reproducible Template structure for one generated Plan."""

    profile_ref: TemplateProfileRef
    base_template_ref: TemplateRef
    institution_ref: str
    sections: tuple[TemplateSection, ...]
    classroom_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.profile_ref, TemplateProfileRef):
            raise InvalidDomainValueError(
                "TemplateSnapshot.profile_ref must be TemplateProfileRef"
            )
        if not isinstance(self.base_template_ref, TemplateRef):
            raise InvalidDomainValueError(
                "TemplateSnapshot.base_template_ref must be TemplateRef"
            )
        _non_blank(self.institution_ref, "TemplateSnapshot.institution_ref")
        if self.classroom_ref is not None:
            _non_blank(self.classroom_ref, "TemplateSnapshot.classroom_ref")
        if not isinstance(self.sections, tuple) or not self.sections:
            raise InvalidDomainValueError(
                "TemplateSnapshot.sections must be a non-empty tuple"
            )
        if not all(isinstance(section, TemplateSection) for section in self.sections):
            raise InvalidDomainValueError(
                "TemplateSnapshot.sections must contain TemplateSection values"
            )

        keys = tuple(section.section_key for section in self.sections)
        if "habits" in keys:
            raise InvalidDomainValueError(
                "TemplateSnapshot cannot store the legacy habits alias"
            )
        if len(set(keys)) != len(keys):
            raise InvalidDomainValueError(
                "TemplateSnapshot contains duplicate section keys"
            )
        if any(not section.activated for section in self.sections):
            raise InvalidDomainValueError(
                "TemplateSnapshot may contain active resolved Sections only"
            )
        orders = tuple(section.order for section in self.sections)
        if len(set(orders)) != len(orders):
            raise InvalidDomainValueError(
                "TemplateSnapshot contains duplicate TemplateSection order values"
            )
        if orders != tuple(sorted(orders)):
            raise InvalidDomainValueError(
                "TemplateSnapshot.sections must be ordered by TemplateSection.order"
            )
        key_set = set(keys)
        for section in self.sections:
            if (
                section.parent_section_key is not None
                and section.parent_section_key not in key_set
            ):
                raise InvalidDomainValueError(
                    "TemplateSection parent_section_key must resolve in its Snapshot"
                )

    @classmethod
    def from_profile(cls, profile: TemplateProfile) -> TemplateSnapshot:
        if not isinstance(profile, TemplateProfile):
            raise InvalidDomainValueError(
                "TemplateSnapshot.from_profile requires TemplateProfile"
            )
        return cls(
            profile_ref=TemplateProfileRef(
                profile.profile_ref.profile_id,
                profile.profile_ref.profile_version,
            ),
            base_template_ref=TemplateRef(
                profile.base_template_ref.template_id,
                profile.base_template_ref.template_version,
            ),
            institution_ref=profile.institution_ref,
            classroom_ref=profile.classroom_ref,
            sections=tuple(replace(section) for section in profile.ordered_sections),
        )

    def section(self, section_key: str) -> TemplateSection | None:
        return next(
            (
                section
                for section in self.sections
                if section.section_key == section_key
            ),
            None,
        )

    def with_activity_details(self) -> TemplateSnapshot:
        """This Snapshot plus a hidden WEEK detail Section for each weekly activity Section it has.

        Appended after the last Section (orders stay unique and sorted); never printed."""
        keys = {section.section_key for section in self.sections}
        order = max(section.order for section in self.sections)
        extra = []
        for parent_key, key in ACTIVITY_DETAIL_SECTION_KEYS.items():
            parent = self.section(parent_key)
            if parent is None or parent.repeat_by is not RepeatBy.WEEK or key in keys:
                continue
            order += 1
            extra.append(
                TemplateSection(
                    section_key=key,
                    role=SectionRole.CONTENT,
                    activated=True,
                    repeat_by=RepeatBy.WEEK,
                    empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
                    display_label=_DETAIL_LABELS[parent_key],
                    order=order,
                    category=parent.category,
                    visible=False,
                )
            )
        return replace(self, sections=self.sections + tuple(extra)) if extra else self
