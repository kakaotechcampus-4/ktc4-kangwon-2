"""The ``ssuksak.planning`` root is the caller contract, not a copy of it."""

import importlib
import os
import subprocess
import sys

import pytest

import ssuksak.planning as planning

# Public name -> the module that defines it. The root re-exports these objects.
PUBLIC = {
    "GenerateYearlyPlan": "application.generate_yearly_plan",
    "EditYearlyPlanItem": "application.edit_yearly_plan_item",
    "RegenerateYearlyPlanItem": "application.regenerate_yearly_plan_item",
    "ConfirmYearlyPlan": "application.confirm_yearly_plan",
    "GenerateYearlyPlanCommand": "application.yearly_dto",
    "EditYearlyPlanItemCommand": "application.yearly_dto",
    "RegenerateYearlyPlanItemCommand": "application.yearly_dto",
    "ConfirmYearlyPlanCommand": "application.yearly_dto",
    "GenerateYearlyPlanResult": "application.yearly_dto",
    "RegenerateYearlyPlanItemResult": "application.yearly_dto",
    "CatalogSelector": "application.yearly_dto",
    "GenerateMonthlyPlan": "application.generate_monthly_plan",
    "EditMonthlyPlanItem": "application.edit_monthly_plan_item",
    "RegenerateMonthlyPlanItem": "application.regenerate_monthly_plan_item",
    "ConfirmMonthlyPlan": "application.confirm_monthly_plan",
    "GenerateMonthlyPlanCommand": "application.monthly_dto",
    "EditMonthlyPlanItemCommand": "application.monthly_dto",
    "RegenerateMonthlyPlanItemCommand": "application.monthly_dto",
    "ConfirmMonthlyPlanCommand": "application.monthly_dto",
    "GenerateMonthlyPlanResult": "application.monthly_dto",
    "RegenerateMonthlyPlanItemResult": "application.monthly_dto",
    "SafetyRuleSelector": "application.monthly_dto",
    "SafetyPlacementSelector": "application.monthly_dto",
    "ActivityCatalogSelector": "application.monthly_dto",
    "TemplateProfileRef": "domain.monthly_template_profile",
    "MonthlyGenerationMode": "domain.monthly_plan",
    "YearMonth": "domain.year_month",
    "PlanId": "domain.identifiers",
    "ItemId": "domain.identifiers",
    "ActorId": "domain.identifiers",
    "YearlyPlan": "domain.yearly_plan",
    "MonthlyPlan": "domain.monthly_plan",
    "YearlyApplicationError": "application.yearly_errors",
    "MonthlyApplicationError": "application.monthly_errors",
    "InvalidStateTransitionError": "domain.errors",
    "InvalidDomainValueError": "domain.errors",
}


def test_all_is_exactly_the_intended_contract():
    assert len(planning.__all__) == len(set(planning.__all__))
    assert set(planning.__all__) == set(PUBLIC)


@pytest.mark.parametrize("name", sorted(PUBLIC))
def test_public_name_is_the_internal_object_and_deep_import_still_works(name):
    internal = importlib.import_module(f"ssuksak.planning.{PUBLIC[name]}")
    assert getattr(planning, name) is getattr(internal, name)


def test_ports_are_not_part_of_the_root_surface():
    for name in ("PlanRepository", "Clock", "IdGenerator", "MonthlyPlanningProvider"):
        assert name not in planning.__all__
        assert not hasattr(planning, name)


@pytest.mark.parametrize(
    "first_import",
    [
        "import ssuksak.planning",
        # A deep import runs the root __init__ first; it must not cycle.
        "import ssuksak.planning.domain.monthly_plan",
        "import ssuksak.adapters.elice_openai_monthly",
    ],
)
def test_fresh_interpreter_imports_without_a_cycle(first_import):
    code = f"{first_import}\nfrom ssuksak.planning import *\n"
    # Hand the child this interpreter's sys.path so it works without an install.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, env=env
    )
    assert result.returncode == 0, result.stderr
