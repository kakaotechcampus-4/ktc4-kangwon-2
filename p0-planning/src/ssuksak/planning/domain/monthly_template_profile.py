"""Institution/class Monthly Template Profile values.

A Profile resolves one approved base Template into the active, ordered Sections
used for generation. It is not a Plan snapshot; that belongs to V1-3.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .errors import InvalidDomainValueError
from .monthly_template import (
    SectionCategory,
    SemanticVariant,
    TemplateRef,
    TemplateSection,
)


DEFAULT_PROFILE_SECTION_KEYS = frozenset(
    {"theme", "week_axis", "outdoor_play", "safety_education"}
)
OPTIONAL_PROFILE_SECTION_KEYS = frozenset(
    {"focus", "goals", "basic_habit", "event_schedule", "drill"}
)
# Full Monthly v1 section 5: explicit institution input, never invented by the
# LLM. No institution-input contract exists yet, so generation refuses them.
INSTITUTION_INPUT_SECTION_KEYS = frozenset({"event_schedule", "drill"})
TEMPLATE_SPECIFIC_PROFILE_SECTION_KEYS = frozenset(
    {
        "indoor_alternative",
        "special_program",
        "emergency_response",
        "daily_routine",
        "community_link",
        "family_link",
    }
)

_LEGACY_SECTION_ALIASES = {"habits": "basic_habit"}


def _non_blank(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{path} must be a non-blank string")


def _canonical_profile_key(section_key: str) -> str:
    return _LEGACY_SECTION_ALIASES.get(section_key, section_key)


@dataclass(frozen=True, slots=True)
class TemplateProfileRef:
    profile_id: str
    profile_version: str

    def __post_init__(self) -> None:
        _non_blank(self.profile_id, "TemplateProfileRef.profile_id")
        _non_blank(self.profile_version, "TemplateProfileRef.profile_version")

    def __str__(self) -> str:
        return f"{self.profile_id}/{self.profile_version}"


@dataclass(frozen=True, slots=True)
class TemplateProfile:
    """Resolved pre-generation Template configuration for one institution/class.

    ``habits`` is accepted only as a legacy input alias. The immutable value
    stores ``basic_habit`` and never stores both spellings.
    """

    profile_ref: TemplateProfileRef
    institution_ref: str
    base_template_ref: TemplateRef
    selected_optional_keys: tuple[str, ...]
    sections: tuple[TemplateSection, ...]
    classroom_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.profile_ref, TemplateProfileRef):
            raise InvalidDomainValueError(
                "TemplateProfile.profile_ref must be TemplateProfileRef"
            )
        _non_blank(self.institution_ref, "TemplateProfile.institution_ref")
        if self.classroom_ref is not None:
            _non_blank(self.classroom_ref, "TemplateProfile.classroom_ref")
        if not isinstance(self.base_template_ref, TemplateRef):
            raise InvalidDomainValueError(
                "TemplateProfile.base_template_ref must be TemplateRef"
            )
        if not isinstance(self.selected_optional_keys, tuple):
            raise InvalidDomainValueError(
                "TemplateProfile.selected_optional_keys must be a tuple"
            )
        if not isinstance(self.sections, tuple) or not self.sections:
            raise InvalidDomainValueError(
                "TemplateProfile.sections must be a non-empty tuple"
            )
        if not all(isinstance(section, TemplateSection) for section in self.sections):
            raise InvalidDomainValueError(
                "TemplateProfile.sections must contain TemplateSection values"
            )

        optional_keys = self._normalize_optional_keys()
        sections = self._normalize_sections()
        object.__setattr__(self, "selected_optional_keys", optional_keys)
        object.__setattr__(self, "sections", sections)

        self._validate_sections()

    def _normalize_optional_keys(self) -> tuple[str, ...]:
        normalized: list[str] = []
        for key in self.selected_optional_keys:
            _non_blank(key, "TemplateProfile.selected_optional_keys item")
            normalized.append(_canonical_profile_key(key))
        if len(set(normalized)) != len(normalized):
            raise InvalidDomainValueError(
                "TemplateProfile.selected_optional_keys contains duplicates"
            )
        invalid = set(normalized) - OPTIONAL_PROFILE_SECTION_KEYS
        if invalid:
            raise InvalidDomainValueError(
                "TemplateProfile.selected_optional_keys contains unsupported keys: "
                + ", ".join(sorted(invalid))
            )
        return tuple(normalized)

    def _normalize_sections(self) -> tuple[TemplateSection, ...]:
        normalized: list[TemplateSection] = []
        for section in self.sections:
            original_key = section.section_key
            canonical_key = _canonical_profile_key(original_key)
            canonical_parent = (
                None
                if section.parent_section_key is None
                else _canonical_profile_key(section.parent_section_key)
            )
            if section.visible and section.display_label in {
                original_key,
                canonical_key,
            }:
                raise InvalidDomainValueError(
                    "A visible Profile TemplateSection requires an explicit "
                    "display_label, not a legacy section-key fallback"
                )
            normalized.append(
                replace(
                    section,
                    section_key=canonical_key,
                    parent_section_key=canonical_parent,
                )
            )
        return tuple(normalized)

    def _validate_sections(self) -> None:
        keys = tuple(section.section_key for section in self.sections)
        if len(set(keys)) != len(keys):
            raise InvalidDomainValueError(
                "TemplateProfile contains duplicate canonical section keys"
            )
        orders = tuple(section.order for section in self.sections)
        if len(set(orders)) != len(orders):
            raise InvalidDomainValueError(
                "TemplateProfile contains duplicate TemplateSection order values"
            )

        key_set = set(keys)
        missing_defaults = DEFAULT_PROFILE_SECTION_KEYS - key_set
        if missing_defaults:
            raise InvalidDomainValueError(
                "TemplateProfile is missing default Sections: "
                + ", ".join(sorted(missing_defaults))
            )

        selected_optional = set(self.selected_optional_keys)
        included_optional: set[str] = set()
        supported_keys = (
            DEFAULT_PROFILE_SECTION_KEYS
            | OPTIONAL_PROFILE_SECTION_KEYS
            | TEMPLATE_SPECIFIC_PROFILE_SECTION_KEYS
        )
        for section in self.sections:
            key = section.section_key
            if key not in supported_keys:
                raise InvalidDomainValueError(
                    f"TemplateProfile contains unsupported Section: {key}"
                )
            if not section.activated:
                raise InvalidDomainValueError(
                    "TemplateProfile.sections may contain active Sections only"
                )
            if section.parent_section_key is not None and (
                section.parent_section_key not in key_set
            ):
                raise InvalidDomainValueError(
                    "TemplateSection parent_section_key must resolve in its Profile"
                )

            if key in DEFAULT_PROFILE_SECTION_KEYS:
                if section.category is not SectionCategory.DEFAULT:
                    raise InvalidDomainValueError(
                        f"Default Profile Section {key} must use DEFAULT category"
                    )
                if not section.required_for_generation:
                    raise InvalidDomainValueError(
                        f"Default Profile Section {key} must be required for generation"
                    )
            elif key in OPTIONAL_PROFILE_SECTION_KEYS:
                if section.category is not SectionCategory.OPTIONAL:
                    raise InvalidDomainValueError(
                        f"Optional Profile Section {key} must use OPTIONAL category"
                    )
                included_optional.add(key)
            else:
                if section.category is not SectionCategory.TEMPLATE_SPECIFIC:
                    raise InvalidDomainValueError(
                        f"Template-specific Section {key} must use "
                        "TEMPLATE_SPECIFIC category"
                    )

            if (
                key == "focus"
                and section.semantic_variant is SemanticVariant.NEUTRAL
            ):
                raise InvalidDomainValueError(
                    "An active focus Profile Section cannot use NEUTRAL "
                    "semantic_variant"
                )

        if included_optional != selected_optional:
            raise InvalidDomainValueError(
                "TemplateProfile selected_optional_keys must exactly match its "
                "active Optional Sections"
            )

    @property
    def ordered_sections(self) -> tuple[TemplateSection, ...]:
        return tuple(sorted(self.sections, key=lambda section: section.order))

    def section(self, section_key: str) -> TemplateSection | None:
        canonical_key = _canonical_profile_key(section_key)
        return next(
            (
                section
                for section in self.sections
                if section.section_key == canonical_key
            ),
            None,
        )
