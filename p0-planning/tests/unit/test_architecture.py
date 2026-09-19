from __future__ import annotations

import ast
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
DOMAIN_ROOT = SRC_ROOT / "ssuksak" / "planning" / "domain"
APPLICATION_ROOT = SRC_ROOT / "ssuksak" / "planning" / "application"

EXTERNAL_SDKS = {"fastapi", "httpx", "openai", "pydantic", "requests", "sqlalchemy"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_domain_does_not_depend_on_application_adapters_or_external_sdks():
    for path in DOMAIN_ROOT.glob("*.py"):
        imports = _imports(path)
        top_levels = {name.split(".")[0] for name in imports}
        assert not (top_levels & EXTERNAL_SDKS), path
        assert not any(
            "application" in name or "adapters" in name for name in imports
        ), path


def test_application_does_not_depend_on_adapters_or_external_sdks():
    for path in APPLICATION_ROOT.glob("*.py"):
        imports = _imports(path)
        top_levels = {name.split(".")[0] for name in imports}
        assert not (top_levels & EXTERNAL_SDKS), path
        assert not any("adapters" in name for name in imports), path


def test_foundation_modules_import_without_external_sdks():
    modules = [
        "ssuksak.planning.domain.identifiers",
        "ssuksak.planning.domain.constraint",
        "ssuksak.planning.domain.provenance",
        "ssuksak.planning.domain.plan",
        "ssuksak.planning.domain.lineage",
        "ssuksak.planning.application.ports",
        "ssuksak.adapters.in_memory_plan_repository",
        "ssuksak.adapters.deterministic",
        "ssuksak.adapters.stub_optional_context_provider",
    ]

    for module in modules:
        assert importlib.import_module(module)
