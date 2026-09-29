from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
)
from ssuksak.planning.context.models import (
    CONTEXT_PACKET_VERSION,
    ContextConstraints,
    ContextLineage,
    GroundingContextItem,
    MonthlyContextPacket,
    ReferenceActivityContext,
    WeekContext,
)
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.domain.monthly_template import SemanticVariant
from ssuksak.planning.domain.monthly_template_profile import (
    TemplateProfile,
    TemplateProfileRef,
)
from ssuksak.planning.domain.monthly_template_snapshot import TemplateSnapshot
from ssuksak.planning.evidence.classification import SemanticClass
from ssuksak.planning.evidence.models import ReusePolicy, SourceSection
from ssuksak.planning.retrieval.models import AgeMatchKind


@pytest.fixture
def packet() -> MonthlyContextPacket:
    first = GroundingContextItem(
        evidence_ref="ev-1",
        text="나뭇잎 색을 관찰한다.",
        source_section=SourceSection.WEEK_EXPERIENCE,
        source_label="주간 경험",
        age_scope=(3, 4),
        age_match=AgeMatchKind.MIXED_AGE_COVERING,
        institution_alias="S1",
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
    )
    second = GroundingContextItem(
        evidence_ref="ev-2",
        text="바람의 움직임을 느껴 본다.",
        source_section=SourceSection.OUTDOOR_PLAY,
        source_label="바깥놀이",
        age_scope=(3, 4),
        age_match=AgeMatchKind.MIXED_AGE_COVERING,
        institution_alias="S2",
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
    )
    subtheme = GroundingContextItem(
        evidence_ref="ev-3",
        text="가을 열매와 나뭇잎",
        source_section=SourceSection.WEEK_EXPERIENCE,
        source_label="소주제",
        age_scope=(3, 4),
        age_match=AgeMatchKind.MIXED_AGE_COVERING,
        institution_alias="S1",
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        grounding_class=SemanticClass.SUBTHEME,
    )
    return MonthlyContextPacket(
        packet_version=CONTEXT_PACKET_VERSION,
        target_month=YearMonth(2026, 9),
        ages=(3, 4),
        parent_theme_id="theme-autumn",
        parent_theme_value="가을과 자연",
        weeks=(
            WeekContext("2026-09-W1", date(2026, 8, 31), date(2026, 9, 4), "1주"),
            WeekContext("2026-09-W2", date(2026, 9, 7), date(2026, 9, 11), "2주"),
        ),
        institution_evidence=(first,),
        age_contrast_evidence=(),
        section_evidence=(subtheme,),
        reference_activities=(ReferenceActivityContext("act-1", "바람개비 놀이", 0),),
        other_outdoor_evidence=(second,),
        constraints=ContextConstraints(
            deterministic_constraint_codes=("STATUTORY_SAFETY_EDUCATION",)
        ),
        lineage=ContextLineage(
            "evidence-store-v1",
            "1" * 64,
            "monthly-evidence-retrieval-v0.2.0",
            "activities",
            "v1",
            "monthly-evidence-semantic-classification-v0.1.0",
        ),
    )


@pytest.fixture
def snapshot() -> TemplateSnapshot:
    template = JsonMonthlyTemplateRepository().get_template(
        "ssuksak.monthly-template-a", "monthly-template-a-v0.2.0"
    )
    assert template is not None
    labels = {
        "theme": "Theme",
        "week_axis": "Week",
        "outdoor_play": "Outdoor play",
        "safety_education": "Safety education",
        "focus": "Subtheme",
    }
    profile = TemplateProfile(
        profile_ref=TemplateProfileRef("planner-profile", "v1"),
        institution_ref="institution-1",
        classroom_ref="class-1",
        base_template_ref=template.template_ref,
        selected_optional_keys=("focus",),
        sections=tuple(
            replace(
                section,
                display_label=labels[section.section_key],
                semantic_variant=(
                    SemanticVariant.SUBTHEME
                    if section.section_key == "focus"
                    else None
                ),
            )
            for section in template.activated_sections
        ),
    )
    return TemplateSnapshot.from_profile(profile)
