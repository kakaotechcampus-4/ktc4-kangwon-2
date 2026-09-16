from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ssuksak.planning.domain.constraint import Constraint
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.plan import PlanItem, PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)


def _item() -> PlanItem:
    return PlanItem(
        item_id=ItemId("item_001"),
        value="봄과 우리 반",
        evidence=(
            EvidenceSource(
                source_type=EvidenceSourceType.INSTITUTION_SAMPLE,
                source_id="sample_001",
                source_version="v1",
            ),
        ),
        generation=GenerationMethodDetail(
            method=GenerationMethod.RULE_LLM,
            rule_id="theme-wording",
            rule_version="v1",
        ),
    )


def test_plan_status_has_only_draft_and_confirmed():
    assert {status.value for status in PlanStatus} == {"DRAFT", "CONFIRMED"}
    assert PlanStatus.DRAFT.is_mutable
    assert not PlanStatus.CONFIRMED.is_mutable


@pytest.mark.parametrize(
    ("code", "description"),
    [("", "required"), ("required", ""), ("   ", "required")],
)
def test_constraint_rejects_blank_fields(code, description):
    with pytest.raises(InvalidDomainValueError):
        Constraint(code=code, description=description)


def test_constraint_is_representation_only_and_immutable():
    constraint = Constraint(
        code="parent-confirmed", description="Parent must be confirmed"
    )

    assert constraint.code == "parent-confirmed"
    assert not hasattr(constraint, "evaluate")
    with pytest.raises(AttributeError):
        constraint.description = "changed"


def test_teacher_edit_preserves_evidence_and_records_generation_change():
    item = _item()

    edited = item.edit_by_teacher(
        plan_id=PlanId("plan_001"),
        new_value="따뜻한 봄과 즐거운 우리 반",
        actor_id=ActorId("teacher_001"),
        occurred_at=datetime(2026, 9, 16, 9, 0, tzinfo=UTC),
    )

    assert edited is not item
    assert edited.value == "따뜻한 봄과 즐거운 우리 반"
    assert edited.evidence == item.evidence
    assert item.generation.method is GenerationMethod.RULE_LLM
    assert edited.generation.method is GenerationMethod.TEACHER_EDIT
    assert len(item.audit) == 0
    assert len(edited.audit) == 1
    event = next(iter(edited.audit))
    assert event.event_type is AuditEventType.TEACHER_EDITED
    assert event.value_change.before == "봄과 우리 반"
    assert event.value_change.after == "따뜻한 봄과 즐거운 우리 반"
    assert event.generation_change.before.method is GenerationMethod.RULE_LLM
    assert event.generation_change.before.rule_id == "theme-wording"
    assert event.generation_change.before.rule_version == "v1"
    assert event.generation_change.after.method is GenerationMethod.TEACHER_EDIT
    assert event.generation_change.after == edited.generation


def test_plan_item_rejects_invalid_value_and_evidence_container():
    valid = _item()
    with pytest.raises(InvalidDomainValueError):
        PlanItem(
            item_id=valid.item_id,
            value=" ",
            evidence=valid.evidence,
            generation=valid.generation,
        )
    with pytest.raises(InvalidDomainValueError):
        PlanItem(
            item_id=valid.item_id,
            value=valid.value,
            evidence=list(valid.evidence),
            generation=valid.generation,
        )


def test_teacher_edit_rejects_blank_value():
    with pytest.raises(InvalidDomainValueError):
        _item().edit_by_teacher(
            plan_id=PlanId("plan_001"),
            new_value=" ",
            actor_id=ActorId("teacher_001"),
            occurred_at=datetime(2026, 9, 16, tzinfo=UTC),
        )
