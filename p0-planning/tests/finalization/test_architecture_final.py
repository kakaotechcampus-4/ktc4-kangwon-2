from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANNING = ROOT / "src" / "ssuksak" / "planning"


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            values.append(("." * node.level) + (node.module or ""))
    return tuple(values)


def _offenders(paths, forbidden):
    return {
        str(path.relative_to(PLANNING)): matches
        for path in paths
        if (
            matches := tuple(
                value
                for value in _imports(path)
                if any(term in value.casefold() for term in forbidden)
            )
        )
    }


def test_domain_has_no_outward_dependency():
    forbidden = (
        "application",
        "adapters",
        "rules",
        "context",
        "planner",
        "retrieval",
        "ingestion",
        "fastapi",
        "sqlalchemy",
    )
    assert _offenders((PLANNING / "domain").glob("*.py"), forbidden) == {}


def test_rules_do_not_import_application_or_adapters():
    assert _offenders(
        (PLANNING / "rules").glob("*.py"),
        ("application", "adapters", "context", "planner"),
    ) == {}


def test_context_does_not_import_planner_application_or_adapters():
    assert _offenders(
        (PLANNING / "context").glob("*.py"),
        ("planner", "application", "adapters"),
    ) == {}


def test_planner_does_not_import_monthly_application_or_adapters():
    assert _offenders(
        (PLANNING / "planner").glob("*.py"),
        ("application", "adapters", "generate_monthly", "regenerate_monthly"),
    ) == {}


def test_pr3_pr4_pr5_have_no_reverse_dependency_on_pr6():
    lower_layers = (
        tuple((PLANNING / "domain").glob("*.py"))
        + tuple((PLANNING / "rules").glob("*.py"))
        + tuple((PLANNING / "evidence").glob("*.py"))
        + tuple((PLANNING / "retrieval").glob("*.py"))
        + tuple((PLANNING / "context").glob("*.py"))
        + tuple((PLANNING / "planner").glob("*.py"))
    )
    pr6_modules = (
        "confirm_monthly_plan",
        "edit_monthly_plan_item",
        "generate_monthly_plan",
        "monthly_dto",
        "monthly_errors",
        "monthly_support",
        "regenerate_monthly_plan_item",
    )

    assert _offenders(lower_layers, pr6_modules) == {}
