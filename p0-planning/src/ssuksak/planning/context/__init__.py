"""Monthly Context Packet (L3).

L2 Retrieval 결과를 GPT-4.1 mini가 이후 사용할 **구조화된 Planning Context**로
조립한다. Prompt 문자열은 만들지 않는다 — Rendering은 L4다.
"""

from __future__ import annotations

from .budget import (
    DEFAULT_CHAR_BUDGET,
    MIN_ITEMS,
    TRIM_ORDER,
    PacketMeasurement,
    measure,
    packet_fingerprint,
    planner_visible_payload,
    trim_to_budget,
)
from .builder import (
    AGE_CRITERIA_ID,
    BLOCK_DEDUP_PRIORITY,
    SAFETY_REQUIRED_SOURCE_KINDS,
    MonthlyContextPacketBuilder,
    MonthlyContextRequest,
    age_evidence_summary,
)
from .debug import render_debug_packet
from .models import (
    PACKET_VERSION,
    RETRIEVAL_CONTRACT_VERSION,
    ActivityOrigin,
    AgeContext,
    AgeContrastGroup,
    AgeContrastObservation,
    AgeEvidenceStrength,
    AgeEvidenceSummary,
    EvidenceAudit,
    EvidenceItem,
    MonthlyContextPacket,
    OfficialCaseContext,
    PackedBlock,
    ParentThemeContext,
    PlannerConstraints,
    PlanningRequestContext,
    ReferenceActivityCandidate,
    SafetyContext,
    SourceLineage,
    WeekExperienceCandidate,
    WeekSlot,
)
from .validation import ContextPacketError, validate_packet

__all__ = [
    "AGE_CRITERIA_ID",
    "BLOCK_DEDUP_PRIORITY",
    "DEFAULT_CHAR_BUDGET",
    "MIN_ITEMS",
    "PACKET_VERSION",
    "RETRIEVAL_CONTRACT_VERSION",
    "SAFETY_REQUIRED_SOURCE_KINDS",
    "TRIM_ORDER",
    "ActivityOrigin",
    "AgeContext",
    "AgeContrastGroup",
    "AgeContrastObservation",
    "AgeEvidenceStrength",
    "AgeEvidenceSummary",
    "ContextPacketError",
    "EvidenceAudit",
    "EvidenceItem",
    "MonthlyContextPacket",
    "MonthlyContextPacketBuilder",
    "MonthlyContextRequest",
    "OfficialCaseContext",
    "PackedBlock",
    "PacketMeasurement",
    "ParentThemeContext",
    "PlannerConstraints",
    "PlanningRequestContext",
    "ReferenceActivityCandidate",
    "SafetyContext",
    "SourceLineage",
    "WeekExperienceCandidate",
    "WeekSlot",
    "age_evidence_summary",
    "measure",
    "packet_fingerprint",
    "planner_visible_payload",
    "render_debug_packet",
    "trim_to_budget",
    "validate_packet",
]
