from dataclasses import replace

import pytest

from ssuksak.adapters.in_memory_template_profile_repository import (
    InMemoryTemplateProfileRepository,
)
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
)
from ssuksak.planning.application.ports import TemplateProfileRepository
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.monthly_template import SemanticVariant
from ssuksak.planning.domain.monthly_template_profile import (
    TemplateProfile,
    TemplateProfileRef,
)


_LABELS = {
    "theme": "Theme",
    "week_axis": "Week",
    "outdoor_play": "Outdoor play",
    "safety_education": "Safety education",
    "focus": "Subtheme",
    "goals": "Goals",
    "habits": "Basic habit",
    "event_schedule": "Events",
    "drill": "Drill",
    "indoor_alternative": "Indoor alternative",
    "special_program": "Special program",
    "emergency_response": "Emergency response",
}


def _template():
    template = JsonMonthlyTemplateRepository().get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.2.0"
    )
    assert template is not None
    return template


def _profile(
    *,
    selected_optional_keys: tuple[str, ...] = ("focus", "basic_habit"),
    template_specific_keys: tuple[str, ...] = (),
    focus_variant: SemanticVariant = SemanticVariant.SUBTHEME,
    institution_ref: str = "institution-1",
    classroom_ref: str | None = "class-1",
) -> TemplateProfile:
    template = _template()
    selected = {
        "habits" if key == "basic_habit" else key
        for key in selected_optional_keys
    }
    included = {
        "theme",
        "week_axis",
        "outdoor_play",
        "safety_education",
        *selected,
        *template_specific_keys,
    }
    sections = []
    for section in template.sections:
        if section.section_key not in included:
            continue
        is_week_axis = section.section_key == "week_axis"
        sections.append(
            replace(
                section,
                activated=True,
                display_label=None if is_week_axis else _LABELS[section.section_key],
                visible=not is_week_axis,
                semantic_variant=(
                    focus_variant if section.section_key == "focus" else None
                ),
            )
        )
    return TemplateProfile(
        profile_ref=TemplateProfileRef("profile-1", "v1"),
        institution_ref=institution_ref,
        classroom_ref=classroom_ref,
        base_template_ref=template.template_ref,
        selected_optional_keys=selected_optional_keys,
        sections=tuple(sections),
    )


def test_repository_resolves_exact_profile_versions_only():
    profile_v1 = _profile()
    profile_v2 = replace(
        profile_v1,
        profile_ref=TemplateProfileRef("profile-1", "v2"),
    )
    repository = InMemoryTemplateProfileRepository((profile_v1, profile_v2))

    assert isinstance(repository, TemplateProfileRepository)
    assert repository.get_profile("profile-1", "v1") is profile_v1
    assert repository.get_profile("profile-1", "v2") is profile_v2
    assert repository.get_profile("profile-1", "latest") is None


def test_profile_rejects_missing_default_section():
    profile = _profile()

    with pytest.raises(InvalidDomainValueError, match="missing default.*theme"):
        replace(
            profile,
            sections=tuple(
                section
                for section in profile.sections
                if section.section_key != "theme"
            ),
        )


def test_profile_rejects_duplicate_and_unsupported_optional_keys():
    profile = _profile()

    with pytest.raises(InvalidDomainValueError, match="contains duplicates"):
        replace(
            profile,
            selected_optional_keys=("habits", "basic_habit", "focus"),
        )
    with pytest.raises(InvalidDomainValueError, match="unsupported keys.*unknown"):
        replace(profile, selected_optional_keys=("focus", "unknown"))


def test_profile_normalizes_legacy_habits_alias_without_storing_both_keys():
    profile = _profile(selected_optional_keys=("habits",))

    assert profile.selected_optional_keys == ("basic_habit",)
    assert profile.section("basic_habit") is not None
    assert profile.section("habits") is profile.section("basic_habit")
    assert "habits" not in {section.section_key for section in profile.sections}

    duplicate_legacy = replace(
        profile.section("basic_habit"),
        section_key="habits",
        order=max(section.order for section in profile.sections) + 1,
    )
    with pytest.raises(InvalidDomainValueError, match="duplicate canonical"):
        replace(profile, sections=(*profile.sections, duplicate_legacy))


def test_profile_rejects_optional_state_that_does_not_match_selection():
    profile = _profile()
    without_focus = tuple(
        section for section in profile.sections if section.section_key != "focus"
    )

    with pytest.raises(InvalidDomainValueError, match="exactly match"):
        replace(profile, sections=without_focus)

    goals = _profile(selected_optional_keys=("goals",)).section("goals")
    with pytest.raises(InvalidDomainValueError, match="exactly match"):
        replace(profile, sections=(*profile.sections, goals))


def test_profile_rejects_inactive_template_specific_section():
    profile = _profile(template_specific_keys=("special_program",))
    special_program = profile.section("special_program")

    assert special_program is not None
    with pytest.raises(InvalidDomainValueError, match="active Sections only"):
        replace(
            profile,
            sections=tuple(
                replace(section, activated=False)
                if section.section_key == "special_program"
                else section
                for section in profile.sections
            ),
        )


def test_profile_rejects_neutral_focus_but_accepts_explicit_variants():
    with pytest.raises(InvalidDomainValueError, match="cannot use NEUTRAL"):
        _profile(focus_variant=SemanticVariant.NEUTRAL)

    for variant in (
        SemanticVariant.SUBTHEME,
        SemanticVariant.EXPECTED_PLAY,
        SemanticVariant.WEEKLY_THEME,
    ):
        assert _profile(focus_variant=variant).section("focus").semantic_variant is variant


def test_profile_validates_explicit_display_labels_and_unique_order():
    profile = _profile()
    theme = profile.section("theme")
    outdoor = profile.section("outdoor_play")

    with pytest.raises(InvalidDomainValueError, match="legacy section-key fallback"):
        replace(
            profile,
            sections=tuple(
                replace(section, display_label="theme")
                if section.section_key == "theme"
                else section
                for section in profile.sections
            ),
        )
    with pytest.raises(InvalidDomainValueError, match="duplicate.*order"):
        replace(
            profile,
            sections=tuple(
                replace(section, order=theme.order)
                if section.section_key == outdoor.section_key
                else section
                for section in profile.sections
            ),
        )


def test_profile_validates_institution_and_optional_classroom_scope():
    assert _profile(classroom_ref=None).classroom_ref is None
    assert _profile(classroom_ref="class-1").classroom_ref == "class-1"

    with pytest.raises(InvalidDomainValueError, match="institution_ref"):
        _profile(institution_ref=" ")
    with pytest.raises(InvalidDomainValueError, match="classroom_ref"):
        _profile(classroom_ref=" ")


def test_legacy_template_versions_still_load_without_profile_fields():
    repository = JsonMonthlyTemplateRepository()

    assert repository.get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.1.0"
    ) is not None
    assert repository.get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.2.0"
    ) is not None
