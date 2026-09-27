from __future__ import annotations

import ast
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "ssuksak"

PR4_ROOTS = (
    SRC_ROOT / "planning" / "evidence",
    SRC_ROOT / "ingestion",
    SRC_ROOT / "planning" / "retrieval",
    SRC_ROOT / "planning" / "context",
)


def _python_files():
    return tuple(path for root in PR4_ROOTS for path in root.glob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_pr4_core_has_no_application_adapter_or_provider_dependency():
    forbidden = ("application", "adapters", "openai", "pydantic", "fastapi", "sqlalchemy")
    for path in _python_files():
        imports = _imports(path)
        assert not any(token in name for token in forbidden for name in imports), path


def test_context_does_not_import_pr5_or_pr6_modules():
    forbidden = (
        "prompt", "planner", "llm", "provider", "generate_monthly_plan",
        "regenerate_monthly", "monthly_application",
    )
    context_root = SRC_ROOT / "planning" / "context"
    for path in context_root.glob("*.py"):
        imports = _imports(path)
        assert not any(token in name.lower() for token in forbidden for name in imports), path


def test_context_builder_has_no_generate_monthly_reverse_reference():
    source = (SRC_ROOT / "planning" / "context" / "builder.py").read_text(encoding="utf-8")
    assert "GenerateMonthlyPlan" not in source
    assert "application" not in source


def test_evidence_uses_pr0_source_type_instead_of_duplicate_enum():
    source = (SRC_ROOT / "planning" / "evidence" / "models.py").read_text(encoding="utf-8")
    assert "from ..domain.provenance import EvidenceSourceType" in source
    assert "class EvidenceSourceType" not in source


def test_activity_selection_trace_remains_rule_local():
    rule = SRC_ROOT / "planning" / "rules" / "monthly_activity_selection.py"
    classes = {
        node.name
        for node in ast.walk(ast.parse(rule.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef)
    }
    assert "ActivitySelectionTrace" in classes


def test_pr4_modules_import_without_external_sdk():
    modules = (
        "ssuksak.planning.evidence.models",
        "ssuksak.planning.evidence.store",
        "ssuksak.planning.evidence.ports",
        "ssuksak.ingestion.ports",
        "ssuksak.ingestion.pipeline",
        "ssuksak.planning.retrieval.models",
        "ssuksak.planning.retrieval.ranking",
        "ssuksak.planning.retrieval.retriever",
        "ssuksak.planning.context.models",
        "ssuksak.planning.context.builder",
        "ssuksak.planning.context.serialization",
        "ssuksak.adapters.institution_evidence_repository",
        "ssuksak.dev.verify_evidence_store",
    )
    for module in modules:
        assert importlib.import_module(module)
