from __future__ import annotations

import os

import pytest

from ssuksak.adapters.elice_openai_monthly import (
    EliceOpenAiMonthlyAdapter,
    MonthlyLlmConfig,
)
from ssuksak.planning.planner.contracts import MonthlyPlanningRequest


@pytest.mark.live
def test_elice_openai_compatible_live_smoke_is_explicitly_opt_in():
    if os.getenv("P0_RUN_LIVE_MONTHLY_LLM") != "1":
        pytest.skip("set P0_RUN_LIVE_MONTHLY_LLM=1 to call Elice MLAPI")
    adapter = EliceOpenAiMonthlyAdapter(MonthlyLlmConfig.from_env())
    response = adapter.generate_monthly(
        MonthlyPlanningRequest(
            task="monthly_plan_proposal",
            prompt_version="live-smoke-v1",
            system_prompt="Return only a JSON object.",
            user_content='Return {"status":"ok"}.',
            target_month="2026-09",
            expected_theme_id="live-smoke",
            expected_week_ids=("W1",),
            packet_fingerprint="0" * 64,
        )
    )
    assert response.content.strip().startswith("{")
