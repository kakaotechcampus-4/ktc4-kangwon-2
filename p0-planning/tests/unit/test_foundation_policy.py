from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def test_json_files_are_canonicalized_to_lf_in_p0_subtree():
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "*.json text eol=lf" in attributes.splitlines()


def test_foundation_has_no_runtime_dependency_on_external_sdks():
    config = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert config["project"]["dependencies"] == []
    assert config["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
