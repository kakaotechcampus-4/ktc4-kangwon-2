"""Provenance 3축 분리 단위 테스트.

CLAUDE.md §13 / docs/screen-spec.md §6·§20:
- AI와 TEACHER_EDIT은 Evidence Source가 아니다.
- LLM 사용 여부는 Generation Method로 표현한다.
- 교사 수정·확정은 Audit History로 표현한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditTrail,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
    SYSTEM_ACTOR_MARKER,
)

NOW = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)


def test_ai_is_not_an_evidence_source_type():
    """`AI`가 Enum에 없으므로 값으로 만들 수 없다."""
    assert "AI" not in {e.value for e in EvidenceSourceType}
    with pytest.raises(ValueError):
        EvidenceSourceType("AI")


def test_teacher_edit_is_not_an_evidence_source_type():
    assert "TEACHER_EDIT" not in {e.value for e in EvidenceSourceType}
    with pytest.raises(ValueError):
        EvidenceSourceType("TEACHER_EDIT")


def test_evidence_source_types_match_screen_spec_list():
    expected = {
        "CURRICULUM",
        "THEME_REFERENCE",
        "PARENT_PLAN",
        "DAYCARE_PROFILE",
        "CLASSROOM_PROFILE",
        "EVENT",
        "SAFETY_RULE",
        "ACTIVITY_REFERENCE",
        "INSTITUTION_SAMPLE",
        "CALENDAR",
        "TREND",
        "EXTERNAL_CONTEXT",
    }
    assert {e.value for e in EvidenceSourceType} == expected


def test_llm_synthesized_is_not_an_evidence_source_type():
    """생성 방식을 Evidence Source로 표현하지 않는다 (OD-N13)."""
    assert "LLM_SYNTHESIZED" not in {e.value for e in EvidenceSourceType}
    assert "AI" not in {e.value for e in EvidenceSourceType}


def test_generation_methods_match_spec():
    assert {m.value for m in GenerationMethod} == {
        "RULE_ONLY",
        "RULE_LLM",
        "IMPORTED",
        "MANUAL",
    }


def test_audit_event_types_match_spec():
    assert {a.value for a in AuditEventType} == {
        "CREATED",
        "REGENERATED",
        "TEACHER_EDITED",
        "CONFIRMED",
    }


def test_evidence_source_requires_source_id():
    with pytest.raises(ValueError):
        EvidenceSource(source_type=EvidenceSourceType.THEME_REFERENCE, source_id="  ")


def test_rule_methods_require_rule_id_and_version():
    """적용된 Rule은 Generation Method 상세이며 Evidence가 아니다."""
    with pytest.raises(ValueError):
        GenerationMethodDetail(method=GenerationMethod.RULE_LLM)
    with pytest.raises(ValueError):
        GenerationMethodDetail(method=GenerationMethod.RULE_ONLY, rule_id="r")

    ok = GenerationMethodDetail(
        method=GenerationMethod.RULE_LLM, rule_id="r", rule_version="v1"
    )
    assert ok.rule_id == "r"


def test_manual_method_needs_no_rule_metadata():
    detail = GenerationMethodDetail(method=GenerationMethod.MANUAL)
    assert detail.rule_id is None


def test_audit_event_requires_actor_or_system_marker():
    with pytest.raises(ValueError):
        AuditEvent(
            event_type=AuditEventType.CREATED, occurred_at=NOW, plan_id="p1"
        )

    system = AuditEvent(
        event_type=AuditEventType.CREATED,
        occurred_at=NOW,
        plan_id="p1",
        system_actor=SYSTEM_ACTOR_MARKER,
    )
    assert system.actor_display == SYSTEM_ACTOR_MARKER

    human = AuditEvent(
        event_type=AuditEventType.CONFIRMED,
        occurred_at=NOW,
        plan_id="p1",
        actor_id=ActorId("user_1"),
    )
    assert human.actor_display == "user_1"


def test_audit_trail_preserves_order():
    trail = AuditTrail()
    order = [
        AuditEventType.CREATED,
        AuditEventType.REGENERATED,
        AuditEventType.TEACHER_EDITED,
        AuditEventType.CONFIRMED,
    ]
    for event_type in order:
        trail.append(
            AuditEvent(
                event_type=event_type,
                occurred_at=NOW,
                plan_id="p1",
                system_actor=SYSTEM_ACTOR_MARKER,
            )
        )

    assert trail.types() == order
    assert len(trail) == 4
    assert trail.contains(AuditEventType.TEACHER_EDITED)


def test_regenerated_event_preserves_previous_and_new_method():
    event = AuditEvent(
        event_type=AuditEventType.REGENERATED,
        occurred_at=NOW,
        plan_id="p1",
        item_id="i1",
        actor_id=ActorId("user_1"),
        previous_value="이전",
        new_value="새로운",
        previous_method=GenerationMethod.RULE_ONLY,
        new_method=GenerationMethod.RULE_LLM,
    )
    assert event.previous_method is GenerationMethod.RULE_ONLY
    assert event.new_method is GenerationMethod.RULE_LLM
    assert event.previous_value == "이전"
