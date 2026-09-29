from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from ssuksak.adapters.evidence_classification_repository import (
    JsonEvidenceClassificationRepository,
)
from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.json_activity_reference_repository import JsonActivityReferenceRepository
from ssuksak.planning.context.builder import ContextPacketBuilder
from ssuksak.planning.context.models import ContextConstraints
from ssuksak.planning.context.serialization import canonical_context_json, packet_fingerprint
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.classification import SemanticClass
from ssuksak.planning.evidence.models import ReusePolicy
from ssuksak.planning.retrieval.models import RetrievalRequest
from ssuksak.planning.retrieval.retriever import MonthlyEvidenceRetriever
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods


@pytest.fixture(scope="module")
def retrieval():
    store = JsonInstitutionEvidenceRepository().get_store()
    catalog = JsonActivityReferenceRepository().get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
    )
    request = RetrievalRequest(
        YearMonth(2026, 9),
        frozenset({3, 4}),
        "yr_theme_korea_and_world_cultures",
        "우리나라와 세계 여러 나라",
        5,
        ("가을", "전통"),
        frozenset({SemanticClass.GOALS, SemanticClass.SUBTHEME}),
    )
    return MonthlyEvidenceRetriever(
        store,
        activity_catalog=catalog,
        classification=JsonEvidenceClassificationRepository().get_classification(),
    ).retrieve(request)


@pytest.fixture(scope="module")
def packet(retrieval):
    return ContextPacketBuilder().build(
        retrieval,
        week_periods=canonical_week_periods(YearMonth(2026, 9)),
        deterministic_constraint_codes=("STATUTORY_SAFETY_EDUCATION",),
    )


def test_packet_is_provider_neutral_and_complete(packet):
    assert packet.target_month == YearMonth(2026, 9)
    assert len(packet.weeks) == 5
    assert packet.reference_activities
    assert packet.constraints.deterministic_constraint_codes == ("STATUTORY_SAFETY_EDUCATION",)
    assert packet.lineage.evidence_store_sha256


def test_evidence_is_deduplicated_across_context_blocks(packet):
    ids = [item.evidence_ref for item in packet.grounding_items]
    assert len(ids) == len(set(ids))


def test_context_preserves_reuse_policy_and_anonymizes_institutions(packet):
    items = packet.institution_evidence + packet.age_contrast_evidence
    assert all(item.reuse_policy is ReusePolicy.CONTEXT_ONLY for item in items)
    assert all(item.institution_alias.startswith("S") for item in items)
    payload = canonical_context_json(packet)
    assert "어린이집" not in payload
    assert "references/samples" not in payload


def test_context_disallows_direct_corpus_output():
    with pytest.raises(InvalidDomainValueError, match="direct output"):
        ContextConstraints(source_text_copy_allowed=True)


def test_packet_fingerprint_is_deterministic_and_lineage_sensitive(packet):
    assert packet_fingerprint(packet) == packet_fingerprint(packet)
    changed = replace(
        packet,
        lineage=replace(packet.lineage, evidence_store_sha256="0" * 64),
    )
    assert packet_fingerprint(packet) != packet_fingerprint(changed)


def test_packet_is_immutable(packet):
    with pytest.raises(FrozenInstanceError):
        packet.parent_theme_value = "changed"


def test_week_count_mismatch_is_rejected(retrieval):
    with pytest.raises(ValueError, match="week structure"):
        ContextPacketBuilder().build(
            retrieval,
            week_periods=canonical_week_periods(YearMonth(2026, 8)),
        )


def test_packet_v020_carries_only_requested_section_classes(packet):
    outdoor_blocks = packet.institution_evidence + packet.age_contrast_evidence + packet.other_outdoor_evidence

    assert packet.packet_version == "monthly-context-packet-v0.2.0"
    assert packet.lineage.retrieval_version == "monthly-evidence-retrieval-v0.3.0"
    assert packet.lineage.evidence_classification_version == (
        "monthly-evidence-semantic-classification-v0.1.0"
    )
    assert {item.grounding_class for item in packet.section_evidence} == {
        SemanticClass.GOALS,
        SemanticClass.SUBTHEME,
    }
    assert all(item.grounding_class is None for item in outdoor_blocks)


def test_packet_fingerprint_binds_the_classification_version(packet):
    changed = replace(
        packet,
        lineage=replace(packet.lineage, evidence_classification_version="other-classification"),
    )

    assert packet_fingerprint(packet) != packet_fingerprint(changed)


def test_packet_rejects_misplaced_or_unversioned_grounding_classes(packet):
    section_item = packet.section_evidence[0]
    outdoor_item = packet.institution_evidence[0]

    with pytest.raises(InvalidDomainValueError, match="approved grounding_class"):
        replace(packet, section_evidence=(replace(section_item, grounding_class=None),))
    with pytest.raises(InvalidDomainValueError, match="Only section evidence"):
        replace(
            packet,
            institution_evidence=(replace(outdoor_item, grounding_class=SemanticClass.GOALS),)
            + packet.institution_evidence[1:],
        )
    with pytest.raises(InvalidDomainValueError, match="classification version"):
        replace(packet, lineage=replace(packet.lineage, evidence_classification_version=""))
