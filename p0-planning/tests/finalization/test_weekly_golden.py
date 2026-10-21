from __future__ import annotations

import json
from pathlib import Path

from .weekly_harness import WeeklyHarness, weekly_snapshot

GOLDEN = Path(__file__).with_name("golden")


def test_weekly_rule_only_product_contract_matches_golden():
    harness = WeeklyHarness()
    result = harness.generate_weekly(harness.monthly_parent())

    expected = json.loads((GOLDEN / "weekly_rule.json").read_text(encoding="utf-8"))
    assert weekly_snapshot(result) == expected
