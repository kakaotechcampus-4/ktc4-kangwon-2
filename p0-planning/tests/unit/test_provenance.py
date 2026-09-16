from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodChange,
    GenerationMethodDetail,
    ValueChange,
)

NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)


def _created(at: datetime = NOW) -> AuditEvent:
    return AuditEvent(
        event_type=AuditEventType.CREATED,
        occurred_at=at,
        plan_id=PlanId("plan_001"),
        system_actor="PLANNING_CORE",
    )


def test_evidence_source_types_follow_p0_contract():
    names = {source_type.value for source_type in EvidenceSourceType}

    assert "INSTITUTION_SAMPLE" in names
    assert "PARENT_PLAN" in names
    assert "AI" not in names
    assert "TEACHER_EDIT" not in names


def test_evidence_source_carries_identity_and_optional_metadata():
    source = EvidenceSource(
        source_type=EvidenceSourceType.CURRICULUM,
        source_id="curriculum_2019",
        source_version="notice-2019-189",
        effective_date=date(2020, 3, 1),
        display_name="2019 개정 누리과정",
    )

    assert source.source_id == "curriculum_2019"
    assert source.source_version == "notice-2019-189"


@pytest.mark.parametrize("source_id", ["", "   ", None])
def test_evidence_source_rejects_invalid_identity(source_id):
    with pytest.raises(InvalidDomainValueError):
        EvidenceSource(EvidenceSourceType.CALENDAR, source_id)


def test_generation_method_is_independent_from_evidence():
    detail = GenerationMethodDetail(
        method=GenerationMethod.RULE_LLM,
        rule_id="theme-wording",
        rule_version="v1",
    )

    assert detail.method is GenerationMethod.RULE_LLM
    assert not hasattr(detail, "source_type")


def test_teacher_edit_is_a_generation_method_not_evidence():
    assert GenerationMethod.TEACHER_EDIT.value == "TEACHER_EDIT"
    assert "TEACHER_EDIT" not in {source.value for source in EvidenceSourceType}


@pytest.mark.parametrize(
    "method", [GenerationMethod.RULE_ONLY, GenerationMethod.RULE_LLM]
)
def test_rule_generation_requires_rule_identity(method):
    with pytest.raises(InvalidDomainValueError):
        GenerationMethodDetail(method=method)


def test_manual_generation_does_not_require_rule_identity():
    assert GenerationMethodDetail(GenerationMethod.MANUAL).rule_id is None


def test_audit_event_requires_exactly_one_actor_kind():
    common = {
        "event_type": AuditEventType.CREATED,
        "occurred_at": NOW,
        "plan_id": PlanId("plan_001"),
    }
    with pytest.raises(InvalidDomainValueError):
        AuditEvent(**common)
    with pytest.raises(InvalidDomainValueError):
        AuditEvent(**common, actor_id=ActorId("teacher_001"), system_actor="SYSTEM")


def test_teacher_edit_audit_requires_item_change_and_human_actor():
    with pytest.raises(InvalidDomainValueError):
        AuditEvent(
            event_type=AuditEventType.TEACHER_EDITED,
            occurred_at=NOW,
            plan_id=PlanId("plan_001"),
            system_actor="SYSTEM",
        )

    event = AuditEvent(
        event_type=AuditEventType.TEACHER_EDITED,
        occurred_at=NOW,
        plan_id=PlanId("plan_001"),
        item_id=ItemId("item_001"),
        actor_id=ActorId("teacher_001"),
        value_change=ValueChange("before", "after"),
        generation_change=GenerationMethodChange(
            GenerationMethodDetail(
                GenerationMethod.RULE_LLM,
                rule_id="theme-wording",
                rule_version="v1",
            ),
            GenerationMethodDetail(GenerationMethod.TEACHER_EDIT),
        ),
    )
    assert event.actor_id == ActorId("teacher_001")


def test_audit_history_append_is_immutable_and_chronological():
    history = AuditHistory().append(_created())
    later = _created(NOW + timedelta(seconds=1))

    appended = history.append(later)

    assert len(history) == 1
    assert len(appended) == 2
    with pytest.raises(InvalidDomainValueError):
        appended.append(_created(NOW - timedelta(seconds=1)))


def test_audit_history_rejects_mutable_event_collection():
    with pytest.raises(InvalidDomainValueError):
        AuditHistory([_created()])


def test_audit_event_rejects_untyped_value_change():
    with pytest.raises(InvalidDomainValueError):
        AuditEvent(
            event_type=AuditEventType.CREATED,
            occurred_at=NOW,
            plan_id=PlanId("plan_001"),
            system_actor="PLANNING_CORE",
            value_change={"before": "a", "after": "b"},
        )


def test_audit_timestamp_must_be_timezone_aware():
    with pytest.raises(InvalidDomainValueError):
        _created(datetime(2026, 9, 16, 9, 0))  # noqa: DTZ001 - intentionally naive
