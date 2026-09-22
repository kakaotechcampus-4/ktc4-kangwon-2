from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "ssuksak" / "planning"
APPLICATION = SRC / "application"
PR6_FILES = (
    "confirm_monthly_plan.py",
    "edit_monthly_plan_item.py",
    "generate_monthly_plan.py",
    "monthly_dto.py",
    "monthly_errors.py",
    "monthly_support.py",
    "regenerate_monthly_plan_item.py",
)


def imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(("." * node.level) + (node.module or ""))
    return tuple(names)


def test_pr3_pr4_and_pr5_have_no_reverse_dependency_on_pr6():
    lower_layers = (
        tuple((SRC / "domain").glob("*.py"))
        + tuple((SRC / "rules").glob("*.py"))
        + tuple((SRC / "evidence").glob("*.py"))
        + tuple((SRC / "retrieval").glob("*.py"))
        + tuple((SRC / "context").glob("*.py"))
        + tuple((SRC / "planner").glob("*.py"))
    )
    pr6_modules = tuple(name.removesuffix(".py") for name in PR6_FILES)
    offenders = {
        str(path.relative_to(SRC)): values
        for path in lower_layers
        if (
            values := tuple(
                value
                for value in imports(path)
                if any(module in value for module in pr6_modules)
            )
        )
    }
    assert offenders == {}


def test_pr6_application_has_no_adapter_demo_db_api_or_provider_dependency():
    forbidden = (
        "adapters",
        "demo",
        "fastapi",
        "sqlalchemy",
        "backend",
        "frontend",
        "elice",
        "openai",
    )
    offenders = {
        name: values
        for name in PR6_FILES
        if (
            values := tuple(
                value
                for value in imports(APPLICATION / name)
                if any(term in value.casefold() for term in forbidden)
            )
        )
    }
    assert offenders == {}


def test_generate_orchestration_reuses_layers_instead_of_provider_internals():
    source = (APPLICATION / "generate_monthly_plan.py").read_text(
        encoding="utf-8"
    )
    assert "MonthlyContextPipeline" in source
    assert "MonthlyPlanner" in source
    assert "MonthlyEvidenceRetriever" not in source
    assert "build_monthly_planning_request" not in source
    assert "parse_monthly_proposal" not in source
    assert "validate_monthly_proposal" not in source
