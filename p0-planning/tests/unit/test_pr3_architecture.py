from __future__ import annotations

import ast
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
DOMAIN_ROOT = SRC_ROOT / "ssuksak" / "planning" / "domain"
RULES_ROOT = SRC_ROOT / "ssuksak" / "planning" / "rules"

PR3_DOMAIN = (
    "activity_reference.py",
    "monthly_constraint.py",
    "monthly_plan.py",
    "monthly_template.py",
    "safety_rule.py",
    "week_period.py",
)
PR3_RULES = (
    "monthly_activity_selection.py",
    "monthly_cell_state.py",
    "monthly_safety.py",
    "monthly_template_resolver.py",
    "monthly_theme_derivation.py",
    "monthly_week_periods.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_monthly_rules_do_not_import_application_or_adapters():
    for filename in PR3_RULES:
        imports = _imports(RULES_ROOT / filename)
        assert not any("application" in name or "adapters" in name for name in imports), filename


def test_monthly_domain_does_not_import_rules_application_or_adapters():
    for filename in PR3_DOMAIN:
        imports = _imports(DOMAIN_ROOT / filename)
        assert not any(
            boundary in name
            for name in imports
            for boundary in ("rules", "application", "adapters")
        ), filename


def test_pr3_has_no_evidence_llm_or_monthly_application_integration_dependency():
    paths = [*(DOMAIN_ROOT / name for name in PR3_DOMAIN), *(RULES_ROOT / name for name in PR3_RULES)]
    forbidden = ("ingestion", "retrieval", "context_packet", "llm", "planner", "generate_monthly_plan", "regenerate_monthly_plan")
    for path in paths:
        imports = _imports(path)
        assert not any(token in name for token in forbidden for name in imports), path


def test_activity_selection_trace_belongs_to_rule_layer():
    path = RULES_ROOT / "monthly_activity_selection.py"
    classes = {node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.ClassDef)}
    assert "ActivitySelectionTrace" in classes


def test_historical_monthly_contracts_are_not_resurrected():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [*(DOMAIN_ROOT / name for name in PR3_DOMAIN), *(RULES_ROOT / name for name in PR3_RULES)]
    )
    for forbidden in ("ParentYearlyLineage", "AuditTrail", "PlanningError", "FailureCategory", "PeriodKey", "SemanticKey", "LLMPort"):
        assert forbidden not in source


def test_pr3_modules_import_without_external_sdk():
    modules = [
        *(f"ssuksak.planning.domain.{Path(name).stem}" for name in PR3_DOMAIN),
        *(f"ssuksak.planning.rules.{Path(name).stem}" for name in PR3_RULES),
        "ssuksak.adapters.activity_reference_schema",
        "ssuksak.adapters.json_activity_reference_repository",
        "ssuksak.adapters.monthly_template_schema",
        "ssuksak.adapters.safety_rule_schema",
        "ssuksak.adapters.monthly_reference_repositories",
    ]
    for module in modules:
        assert importlib.import_module(module)
