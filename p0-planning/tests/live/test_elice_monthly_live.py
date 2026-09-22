from __future__ import annotations

import os

import pytest

from ssuksak.adapters.elice_openai_monthly import (
    EliceOpenAiMonthlyAdapter,
    MonthlyLlmConfig,
)
from ssuksak.planning.planner.contracts import MonthlyPlanningRequest
from ssuksak.planning.domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    SectionCategory,
    SectionRole,
    TemplateRef,
    TemplateSection,
)
from ssuksak.planning.domain.monthly_template_profile import TemplateProfileRef
from ssuksak.planning.domain.monthly_template_snapshot import TemplateSnapshot
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.year_month import YearMonth


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
            target_month=YearMonth(2026, 9),
            expected_theme_id="live-smoke",
            expected_theme_value="Live smoke",
            expected_week_ids=(WeekId("2026-09-W1"),),
            template_snapshot=TemplateSnapshot(
                profile_ref=TemplateProfileRef("live-profile", "v1"),
                base_template_ref=TemplateRef("live-template", "v1"),
                institution_ref="live-institution",
                sections=(
                    TemplateSection(
                        section_key="theme",
                        role=SectionRole.CONTENT,
                        activated=True,
                        display_mode=DisplayMode.MONTHLY_MERGED_SUMMARY,
                        empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
                        display_label="Theme",
                        category=SectionCategory.DEFAULT,
                        required_for_generation=True,
                        visible=True,
                    ),
                ),
            ),
            packet_fingerprint="0" * 64,
        )
    )
    assert response.content.strip().startswith("{")
