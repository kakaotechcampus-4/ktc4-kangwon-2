"""Assemble retrieval results into a provider-neutral Context Packet."""

from __future__ import annotations

from ..domain.week_period import WeekPeriod
from ..retrieval.models import BlockName, MonthlyEvidenceRetrievalResult, RetrievedEvidence
from .models import (
    CONTEXT_PACKET_VERSION,
    ContextConstraints,
    ContextLineage,
    GroundingContextItem,
    MonthlyContextPacket,
    ReferenceActivityContext,
    WeekContext,
)


class ContextPacketBuilder:
    def build(
        self,
        retrieval: MonthlyEvidenceRetrievalResult,
        *,
        week_periods: tuple[WeekPeriod, ...],
        deterministic_constraint_codes: tuple[str, ...] = (),
    ) -> MonthlyContextPacket:
        active_weeks = tuple(period for period in week_periods if period.active)
        if len(active_weeks) != retrieval.request.week_count:
            raise ValueError("active week structure does not match retrieval request")

        all_items = [
            item
            for name in (
                BlockName.AGE_CONTRAST_EVIDENCE,
                BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                BlockName.WEEK_EXPERIENCE_CANDIDATES,
                BlockName.OTHER_OUTDOOR_EVIDENCE,
            )
            for item in retrieval.block(name).items
        ]
        institutions = sorted(
            {item.record.institution_id or "UNKNOWN_INSTITUTION" for item in all_items}
        )
        aliases = {institution: f"S{index}" for index, institution in enumerate(institutions, start=1)}
        used: set[str] = set()

        def convert(items: tuple[RetrievedEvidence, ...]) -> tuple[GroundingContextItem, ...]:
            converted = []
            for item in items:
                if item.record_id in used or item.record.text is None:
                    continue
                used.add(item.record_id)
                institution = item.record.institution_id or "UNKNOWN_INSTITUTION"
                converted.append(
                    GroundingContextItem(
                        evidence_ref=item.record_id,
                        text=item.record.text,
                        source_section=item.record.source_section,
                        source_label=item.record.source_label,
                        age_scope=item.record.age_scope,
                        age_match=item.trace.age_match,
                        institution_alias=aliases[institution],
                        reuse_policy=item.record.reuse_policy,
                    )
                )
            return tuple(converted)

        contrast = convert(retrieval.block(BlockName.AGE_CONTRAST_EVIDENCE).items)
        institution = convert(retrieval.block(BlockName.INSTITUTION_MONTHLY_EVIDENCE).items)
        week = convert(retrieval.block(BlockName.WEEK_EXPERIENCE_CANDIDATES).items)
        other = convert(retrieval.block(BlockName.OTHER_OUTDOOR_EVIDENCE).items)
        references = tuple(
            ReferenceActivityContext(item.activity_id, item.label, item.rank)
            for item in retrieval.block(BlockName.REFERENCE_ACTIVITIES).reference_items
        )
        return MonthlyContextPacket(
            packet_version=CONTEXT_PACKET_VERSION,
            target_month=retrieval.request.target_month,
            ages=tuple(sorted(retrieval.request.ages)),
            parent_theme_id=retrieval.request.confirmed_theme_id,
            parent_theme_value=retrieval.request.confirmed_theme_value,
            weeks=tuple(
                WeekContext(
                    str(period.week_id),
                    period.start_date,
                    period.end_date,
                    period.display_label,
                )
                for period in active_weeks
            ),
            institution_evidence=institution,
            age_contrast_evidence=contrast,
            week_experience_candidates=week,
            reference_activities=references,
            other_outdoor_evidence=other,
            constraints=ContextConstraints(
                deterministic_constraint_codes=deterministic_constraint_codes
            ),
            lineage=ContextLineage(
                retrieval.evidence_store_version,
                retrieval.evidence_store_sha256,
                retrieval.retrieval_version,
                retrieval.activity_catalog_id,
                retrieval.activity_catalog_version,
            ),
        )
