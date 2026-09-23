from dataclasses import replace

import pytest

from ssuksak.adapters.json_activity_reference_repository import JsonActivityReferenceRepository
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.adapters.monthly_template_schema import MonthlyTemplateSchemaError, parse_monthly_template_payload
from ssuksak.planning.application.ports import (
    ActivityReferenceRepository,
    MonthlyTemplateRepository,
    SafetyLegalRuleRepository,
)
from ssuksak.planning.domain.monthly_template import DisplayMode
from ssuksak.planning.rules.monthly_template_resolver import expected_cell_count, resolve_sections


def test_reference_adapters_implement_ports():
    assert isinstance(JsonActivityReferenceRepository(), ActivityReferenceRepository)
    assert isinstance(JsonMonthlyTemplateRepository(), MonthlyTemplateRepository)
    assert isinstance(JsonSafetyLegalRuleRepository(), SafetyLegalRuleRepository)


def test_activity_repository_resolves_exact_versions_only():
    repository = JsonActivityReferenceRepository()

    current = repository.get_catalog("ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1")
    previous = repository.get_catalog("ssuksak.outdoor-activity-reference", "activity-reference-v0.2.0")
    baseline = repository.get_catalog("ssuksak.outdoor-activity-reference", "activity-reference-v0.1.0")

    assert current is not None and current.is_active and len(current.activities) == 196
    assert previous is not None and previous.is_active and len(previous.activities) == 198
    assert baseline is not None and not baseline.is_active and len(baseline.activities) == 49
    assert repository.get_catalog("ssuksak.outdoor-activity-reference", "latest") is None
    assert repository.get_catalog("ssuksak.outdoor-activity-reference", "activity-reference-v0.2.0-draft") is None


def test_template_versions_have_expected_active_sections():
    repository = JsonMonthlyTemplateRepository()
    v1 = repository.get_template("ssuksak.monthly-template-a", "monthly-template-a-v0.1.0")
    v2 = repository.get_template("ssuksak.monthly-template-a", "monthly-template-a-v0.2.0")

    assert v1 is not None and v2 is not None
    assert tuple(item.section_key for item in v1.activated_sections) == (
        "theme", "week_axis", "outdoor_play", "safety_education"
    )
    assert tuple(item.section_key for item in v2.activated_sections) == (
        "theme", "week_axis", "outdoor_play", "safety_education", "focus"
    )
    assert v1.section("focus").activated is False
    assert v2.section("focus").display_mode is DisplayMode.WEEKLY_CELLS
    assert repository.get_template("ssuksak.monthly-template-a", "latest") is None


def test_template_resolver_counts_structure_without_application_dto():
    template = JsonMonthlyTemplateRepository().get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.1.0"
    )
    resolved = resolve_sections(template)

    assert expected_cell_count(resolved, 5) == 11


def test_template_resolver_rejects_unapproved_template():
    template = JsonMonthlyTemplateRepository().get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.1.0"
    )
    with pytest.raises(Exception, match="HUMAN_APPROVED"):
        resolve_sections(replace(template, runtime_active=False))


def test_template_schema_does_not_accept_manual_runtime_activation():
    with pytest.raises(MonthlyTemplateSchemaError, match="object"):
        parse_monthly_template_payload([])


def test_safety_reference_is_six_category_and_has_no_placement_policy():
    repository = JsonSafetyLegalRuleRepository()
    rule = repository.get_legal_rule("child-welfare-act-decree-annex6-2022-06-21")

    assert rule is not None and rule.is_active
    assert len(rule.categories) == 6
    assert rule.annual_hours_min_total == 44
    assert not rule.has_placement_policy
    assert repository.get_legal_rule("latest") is None
