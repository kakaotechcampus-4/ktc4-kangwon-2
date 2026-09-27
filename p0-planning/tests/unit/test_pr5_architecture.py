from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ssuksak"
PLANNER = SRC / "planning" / "planner"


def imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(("." * node.level) + (node.module or ""))
    return tuple(names)


def test_pr5_planner_does_not_import_application_or_adapters():
    imported = {
        path.name: imports(path) for path in PLANNER.glob("*.py")
    }
    offenders = {
        name: values
        for name, values in imported.items()
        if any("application" in value or "adapters" in value for value in values)
    }
    assert offenders == {}


def test_pr5_has_no_pr6_demo_db_or_fastapi_dependency():
    forbidden = (
        "generate_monthly_plan",
        "regenerate_monthly_plan_item",
        "demo",
        "fastapi",
        "sqlalchemy",
    )
    files = tuple(PLANNER.glob("*.py")) + (
        SRC / "adapters" / "deterministic_monthly_llm.py",
        SRC / "adapters" / "elice_openai_monthly.py",
    )
    offenders = []
    for path in files:
        for value in imports(path):
            if any(term in value.casefold() for term in forbidden):
                offenders.append((path.name, value))
    assert offenders == []


def test_context_packet_remains_provider_neutral():
    context_files = (SRC / "planning" / "context").glob("*.py")
    assert all(
        not any("planner" in value or "adapters" in value for value in imports(path))
        for path in context_files
    )
