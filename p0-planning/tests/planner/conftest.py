from __future__ import annotations

from datetime import date

import pytest

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
        week_experience_candidates=(),
        reference_activities=(ReferenceActivityContext("act-1", "바람개비 놀이", 0),),
        other_outdoor_evidence=(second,),
        constraints=ContextConstraints(
            deterministic_constraint_codes=("STATUTORY_SAFETY_EDUCATION",)
        ),
        lineage=ContextLineage(
            "evidence-store-v1",
            "1" * 64,
            "monthly-evidence-retrieval-v0.1.0",
            "activities",
            "v1",
        ),
    )
