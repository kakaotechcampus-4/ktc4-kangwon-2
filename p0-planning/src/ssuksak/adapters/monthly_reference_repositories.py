"""Exact-version JSON adapters for Monthly Template and Safety References."""

from __future__ import annotations

import json
from pathlib import Path

from ..planning.domain.monthly_template import MonthlyTemplate
from ..planning.domain.safety_rule import SafetyLegalRule
from .monthly_template_schema import parse_monthly_template_payload
from .safety_rule_schema import parse_safety_rule_payload

_DATA = Path(__file__).resolve().parents[3] / "data"
DEFAULT_TEMPLATE_PATH = _DATA / "templates" / "monthly_template_a.json"
FOCUS_TEMPLATE_PATH = _DATA / "templates" / "monthly_template_a_v0_2_0.json"
DEFAULT_SAFETY_RULE_PATH = _DATA / "rules" / "safety_education_legal_v1.json"


class JsonMonthlyTemplateRepository:
    def __init__(self, paths: tuple[Path, ...] = (DEFAULT_TEMPLATE_PATH, FOCUS_TEMPLATE_PATH)) -> None:
        self._paths = tuple(Path(path) for path in paths)
        self._cache: dict[Path, MonthlyTemplate] = {}

    def _load(self, path: Path) -> MonthlyTemplate:
        if path not in self._cache:
            self._cache[path] = parse_monthly_template_payload(
                json.loads(path.read_text(encoding="utf-8"))
            )
        return self._cache[path]

    def get_template(self, template_id: str, template_version: str) -> MonthlyTemplate | None:
        for path in self._paths:
            template = self._load(path)
            ref = template.template_ref
            if (ref.template_id, ref.template_version) == (template_id, template_version):
                return template
        return None


class JsonSafetyLegalRuleRepository:
    def __init__(self, path: Path = DEFAULT_SAFETY_RULE_PATH) -> None:
        self._path = Path(path)
        self._cached: SafetyLegalRule | None = None

    def _load(self) -> SafetyLegalRule:
        if self._cached is None:
            self._cached = parse_safety_rule_payload(
                json.loads(self._path.read_text(encoding="utf-8"))
            )
        return self._cached

    def get_legal_rule(self, legal_rule_version: str) -> SafetyLegalRule | None:
        rule = self._load()
        return rule if rule.legal_rule_version == legal_rule_version else None
