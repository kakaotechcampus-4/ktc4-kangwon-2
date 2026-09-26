"""Assemble retrieval results into a provider-neutral Context Packet."""

from __future__ import annotations

from dataclasses import replace

from ..domain.week_period import WeekPeriod
from ..evidence.classification import SemanticClass
from ..retrieval.models import (
    CLASS_BLOCKS,
    BlockName,
    MonthlyEvidenceRetrievalResult,
    RetrievedEvidence,
)
from .models import (
    CONTEXT_PACKET_VERSION,
    ContextConstraints,
    ContextLineage,
    GroundingContextItem,
    MonthlyContextPacket,
    ReferenceActivityContext,
    SafetyContext,
    SafetyReferenceContext,
    WeekContext,
)
from ..evidence.safety_classification import SafetyEvidenceClassification
from ..evidence.safety_quality import SafetyReferenceQuality


class ContextPacketBuilder:
    def build(
        self,
        retrieval: MonthlyEvidenceRetrievalResult,
        *,
        week_periods: tuple[WeekPeriod, ...],
        deterministic_constraint_codes: tuple[str, ...] = (),
        safety: SafetyContext | None = None,
        safety_classification: SafetyEvidenceClassification | None = None,
        safety_quality: SafetyReferenceQuality | None = None,
    ) -> MonthlyContextPacket:
        active_weeks = tuple(period for period in week_periods if period.active)
        if len(active_weeks) != retrieval.request.week_count:
            raise ValueError("active week structure does not match retrieval request")

        all_items = [
            item
            for name in (
                BlockName.AGE_CONTRAST_EVIDENCE,
                BlockName.INSTITUTION_MONTHLY_EVIDENCE,
                *CLASS_BLOCKS.values(),
                BlockName.OTHER_OUTDOOR_EVIDENCE,
                *(
                    (
                        BlockName.SAFETY_EDUCATION_EVIDENCE,
                        BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE,
                        BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE,
                    )
                    if safety is not None
                    else ()
                ),
            )
            for item in retrieval.block(name).items
        ]
        institutions = sorted(
            {item.record.institution_id or "UNKNOWN_INSTITUTION" for item in all_items}
        )
        aliases = {institution: f"S{index}" for index, institution in enumerate(institutions, start=1)}
        used: set[str] = set()

        def convert(
            items: tuple[RetrievedEvidence, ...],
            grounding_class: SemanticClass | None = None,
        ) -> tuple[GroundingContextItem, ...]:
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
                        grounding_class=grounding_class,
                    )
                )
            return tuple(converted)

        contrast = convert(retrieval.block(BlockName.AGE_CONTRAST_EVIDENCE).items)
        institution = convert(retrieval.block(BlockName.INSTITUTION_MONTHLY_EVIDENCE).items)
        section = tuple(
            item
            for grounding_class, block in CLASS_BLOCKS.items()
            for item in convert(retrieval.block(block).items, grounding_class)
        )
        other = convert(retrieval.block(BlockName.OTHER_OUTDOOR_EVIDENCE).items)
        if safety is not None:
            retrieved = {
                item.record_id: item.record
                for name in (
                    BlockName.SAFETY_EDUCATION_EVIDENCE,
                    BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE,
                    BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE,
                )
                for item in retrieval.block(name).items
            }
            cross_month = {item.record_id for item in retrieval.block(BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE).items}
            # Order matters: target-month References rank before cross-month ones.
            evidence = (
                convert(retrieval.block(BlockName.SAFETY_EDUCATION_EVIDENCE).items)
                + convert(retrieval.block(BlockName.SUPPLEMENTAL_SAFETY_EVIDENCE).items)
                + convert(retrieval.block(BlockName.CROSS_MONTH_SUPPLEMENTAL_SAFETY_EVIDENCE).items)
            )
            references = []
            for item in evidence:
                record = retrieved[item.evidence_ref]
                reference = safety_classification.runtime_reference(record)
                references.append(
                    SafetyReferenceContext(
                        item.evidence_ref, reference.kind, reference.legal_category_id, reference.supplemental_label,
                        safety_quality.usable_topic_group(record) if reference.supplemental_label else None,
                        item.evidence_ref in cross_month,
                    )
                )
            safety = replace(safety, evidence=evidence, references=tuple(references))
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
            section_evidence=section,
            reference_activities=references,
            other_outdoor_evidence=other,
            safety=safety,
            constraints=ContextConstraints(
                deterministic_constraint_codes=deterministic_constraint_codes
            ),
            lineage=ContextLineage(
                retrieval.evidence_store_version,
                retrieval.evidence_store_sha256,
                retrieval.retrieval_version,
                retrieval.activity_catalog_id,
                retrieval.activity_catalog_version,
                retrieval.evidence_classification_version,
            ),
        )
