from __future__ import annotations

import ast
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
RULES_ROOT = SRC_ROOT / "ssuksak" / "planning" / "rules"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_rules_do_not_depend_on_application_adapters_or_external_sdks():
    for path in RULES_ROOT.glob("*.py"):
        imports = _imports(path)
        assert not any("application" in name for name in imports), path
        assert not any("adapters" in name for name in imports), path
        assert not ({name.split(".")[0] for name in imports} & {"pydantic", "openai"}), path


def test_pr1_modules_import_without_pr2_or_monthly_modules():
    modules = [
        "ssuksak.planning.domain.year_month",
        "ssuksak.planning.domain.theme_reference",
        "ssuksak.planning.rules.errors",
        "ssuksak.planning.rules.academic_periods",
        "ssuksak.planning.rules.yearly_reference_rules",
        "ssuksak.planning.rules.yearly_theme_selection",
        "ssuksak.planning.application.ports",
        "ssuksak.adapters.theme_reference_schema",
        "ssuksak.adapters.json_theme_reference_repository",
    ]

    for module in modules:
        assert importlib.import_module(module)


def test_historical_contract_types_are_not_resurrected_in_pr1_source():
    forbidden = {
        "PeriodKey",
        "PlanningError",
        "FailureCategory",
        "Outcome",
        "AuditTrail",
        "ParentYearlyLineage",
    }
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (
            SRC_ROOT / "ssuksak" / "planning" / "rules",
            SRC_ROOT / "ssuksak" / "planning" / "domain",
            SRC_ROOT / "ssuksak" / "adapters",
        )
        for path in root.glob("*.py")
    )

    for name in forbidden:
        assert name not in source
