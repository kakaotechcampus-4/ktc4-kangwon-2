from __future__ import annotations

import ast
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
APPLICATION_ROOT = SRC_ROOT / "ssuksak" / "planning" / "application"
DOMAIN_ROOT = SRC_ROOT / "ssuksak" / "planning" / "domain"

PR2_APPLICATION_MODULES = (
    "confirm_yearly_plan.py",
    "edit_yearly_plan_item.py",
    "generate_yearly_plan.py",
    "regenerate_yearly_plan_item.py",
    "yearly_dto.py",
    "yearly_errors.py",
    "yearly_ports.py",
    "yearly_support.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_pr2_application_does_not_depend_on_adapters_monthly_or_external_sdks():
    for filename in PR2_APPLICATION_MODULES:
        path = APPLICATION_ROOT / filename
        imports = _imports(path)
        assert not any("adapters" in name for name in imports), path
        assert not any("monthly" in name for name in imports), path
        assert not (
            {name.split(".")[0] for name in imports}
            & {"fastapi", "openai", "pydantic", "sqlalchemy"}
        ), path


def test_yearly_domain_does_not_depend_on_rules_application_or_adapters():
    imports = _imports(DOMAIN_ROOT / "yearly_plan.py")

    assert not any(
        boundary in name
        for name in imports
        for boundary in ("rules", "application", "adapters")
    )


def test_historical_yearly_contracts_are_not_resurrected():
    source = "\n".join(
        (APPLICATION_ROOT / filename).read_text(encoding="utf-8")
        for filename in PR2_APPLICATION_MODULES
    )
    source += (
        DOMAIN_ROOT / "yearly_plan.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "PlanningError",
        "FailureCategory",
        "Outcome",
        "AuditTrail",
        "ParentYearlyLineage",
        "PeriodKey",
        "LLMPort",
        "FakeLLM",
    ):
        assert forbidden not in source


def test_pr2_modules_import_without_provider_monthly_or_demo_modules():
    modules = [
        "ssuksak.planning.domain.yearly_plan",
        "ssuksak.planning.application.yearly_errors",
        "ssuksak.planning.application.yearly_dto",
        "ssuksak.planning.application.yearly_ports",
        "ssuksak.planning.application.yearly_support",
        "ssuksak.planning.application.generate_yearly_plan",
        "ssuksak.planning.application.edit_yearly_plan_item",
        "ssuksak.planning.application.regenerate_yearly_plan_item",
        "ssuksak.planning.application.confirm_yearly_plan",
        "ssuksak.adapters.deterministic_theme_text_generator",
    ]

    for module in modules:
        assert importlib.import_module(module)
