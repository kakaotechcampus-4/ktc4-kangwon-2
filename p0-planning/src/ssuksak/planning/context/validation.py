"""Monthly Context Packet Validator (L3).

**LLM 출력 검증이 아니다.** 이것은 "우리가 조립한 Context가 스스로 모순되지
않는가"를 본다. LLM Proposal 검증은 L5의 일이고 대상도 시점도 다르다.

조용히 통과시키지 않는다(CLAUDE.md §14). 실패는 예외다.
"""

from __future__ import annotations

from ...ingestion.models import ExtractionQuality, MachineReadability, ReusePolicy
from ..domain.activity_reference import ActivityCatalog
from .models import ActivityOrigin, MonthlyContextPacket

__all__ = ["ContextPacketError", "validate_packet"]


class ContextPacketError(Exception):
    """Packet이 스스로 모순된다."""


def validate_packet(
    packet: MonthlyContextPacket,
    *,
    catalog: ActivityCatalog | None = None,
    expected_store_sha256: str | None = None,
) -> None:
    _required(packet)
    _weeks(packet)
    _evidence(packet)
    _license(packet)
    _reference(packet, catalog)
    _lineage(packet, expected_store_sha256)


def _fail(message: str) -> None:
    raise ContextPacketError(message)


def _required(packet: MonthlyContextPacket) -> None:
    if not packet.parent_theme.theme_id.strip():
        _fail("parent_theme.theme_id가 비어 있다")
    if not packet.parent_theme.theme_value.strip():
        _fail("parent_theme.theme_value가 비어 있다")
    if not packet.week_slots:
        _fail("week_slots가 비어 있다")
    if not packet.constraints.expected_week_ids:
        _fail("constraints.expected_week_ids가 비어 있다")
    if not packet.age_context.per_age:
        _fail("age_context.per_age가 비어 있다")
    if tuple(packet.age_context.requested_ages) != tuple(
        sorted(set(packet.planning_request.classroom_ages))
    ):
        _fail("age_context.requested_ages가 planning_request와 다르다")


def _weeks(packet: MonthlyContextPacket) -> None:
    ids = [w.week_id for w in packet.week_slots]
    if len(set(ids)) != len(ids):
        _fail(f"week_id가 중복된다: {ids}")
    if tuple(ids) != tuple(packet.constraints.expected_week_ids):
        _fail("constraints.expected_week_ids가 week_slots와 다르다")
    if packet.constraints.expected_week_count != len(packet.week_slots):
        _fail(
            "expected_week_count가 week_slots 개수와 다르다: "
            f"{packet.constraints.expected_week_count} vs {len(packet.week_slots)}"
        )
    for w in packet.week_slots:
        if w.end_date < w.start_date:
            _fail(f"{w.week_id}: end_date가 start_date보다 앞선다")


def _evidence(packet: MonthlyContextPacket) -> None:
    ids = packet.all_evidence_ids
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        _fail(f"Evidence record가 두 Block에 중복으로 들어갔다: {dupes}")

    for item in _all_items(packet):
        audit = item.audit
        if audit.extraction_quality != ExtractionQuality.VALID.value:
            _fail(f"{item.evidence_id}: VALID가 아닌 Evidence가 Context에 있다")
        if audit.machine_readability != MachineReadability.TEXT_LAYER.value:
            _fail(f"{item.evidence_id}: TEXT_LAYER가 아닌 Evidence가 Context에 있다")
        if not item.text.strip():
            _fail(f"{item.evidence_id}: 빈 text가 Context에 있다")

    for group in packet.age_contrast_evidence:
        ages = group.ages
        if len(ages) < 2:
            _fail(f"{group.group_id}: 연령 대조가 2개 미만이다")
        if len(set(ages)) != len(ages):
            _fail(f"{group.group_id}: 같은 연령이 두 번 들어갔다")
        for obs in group.observations:
            if not obs.items:
                _fail(f"{group.group_id}: 만{obs.age}세 관찰이 비어 있다")
            for item in obs.items:
                if item.audit.source_sha256 != group.source_sha256:
                    _fail(
                        f"{group.group_id}: 다른 문서의 record가 대조에 섞였다 "
                        f"({item.evidence_id})"
                    )


def _license(packet: MonthlyContextPacket) -> None:
    """`CONTEXT_ONLY` 상태가 Packet 안에서 사라지지 않았는가."""
    c = packet.constraints
    if c.source_text_copy_allowed:
        _fail("source_text_copy_allowed가 True다. 원문 복사를 허용할 수 없다")
    if c.safety_generation_allowed or packet.safety_context.safety_generation_allowed:
        _fail("safety_generation_allowed가 True다. 안전교육은 LLM이 배치하지 않는다")
    if not c.theme_locked:
        _fail("theme_locked가 False다. Theme은 immutable planning input이다")

    context_only = any(
        i.reuse_policy is ReusePolicy.CONTEXT_ONLY for i in _all_items(packet)
    )
    if context_only and c.corpus_direct_output_enabled:
        _fail("CONTEXT_ONLY Evidence가 있는데 corpus_direct_output_enabled가 True다")
    if (
        not c.corpus_direct_output_enabled
        and ActivityOrigin.CORPUS_EVIDENCE in c.allowed_activity_origins
    ):
        _fail(
            "corpus_direct_output_enabled가 False인데 CORPUS_EVIDENCE가 "
            "allowed_activity_origins에 있다"
        )
    if ActivityOrigin.REFERENCE not in c.allowed_activity_origins:
        _fail("REFERENCE가 allowed_activity_origins에 없다")


def _reference(packet: MonthlyContextPacket, catalog: ActivityCatalog | None) -> None:
    lineage = packet.source_lineage
    if bool(lineage.activity_catalog_id) != bool(lineage.activity_catalog_version):
        _fail("activity_catalog_id와 version 중 하나만 채워져 있다")
    if not lineage.activity_catalog_id and packet.reference_activities:
        _fail("Catalog 없이 reference_activities가 채워져 있다")

    ids = [a.activity_id for a in packet.reference_activities]
    if len(set(ids)) != len(ids):
        _fail("reference_activities에 중복 activity_id가 있다")
    if catalog is not None:
        for activity_id in ids:
            if catalog.get(activity_id) is None:
                _fail(f"Catalog에 없는 activity_id다: {activity_id}")


def _lineage(packet: MonthlyContextPacket, expected_sha256: str | None) -> None:
    lineage = packet.source_lineage
    if lineage.packet_version != packet.packet_version:
        _fail("source_lineage.packet_version이 packet_version과 다르다")
    if expected_sha256 and lineage.evidence_store_content_sha256 != expected_sha256:
        _fail(
            "Evidence Store SHA가 기대 pin과 다르다: "
            f"{lineage.evidence_store_content_sha256} vs {expected_sha256}"
        )


def _all_items(packet: MonthlyContextPacket):
    yield from packet.institution_evidence
    yield from packet.other_outdoor_evidence
    yield from packet.week_experience_candidates
    for group in packet.age_contrast_evidence:
        for obs in group.observations:
            yield from obs.items
