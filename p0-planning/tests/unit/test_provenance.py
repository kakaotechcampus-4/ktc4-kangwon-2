from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.provenance import (
    ArrangementChange,
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodChange,
    GenerationMethodDetail,
    LinkChange,
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


def test_value_change_can_record_a_monthly_empty_to_filled_transition():
    change = ValueChange("", "Teacher-authored value")

    assert change.before == ""
    assert change.after == "Teacher-authored value"
    with pytest.raises(InvalidDomainValueError):
        ValueChange(" ", "")


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


def test_a_teacher_edit_needs_no_generation_change_but_still_a_value_change():
    common = dict(
        event_type=AuditEventType.TEACHER_EDITED, occurred_at=NOW, plan_id=PlanId("plan_001"),
        item_id=ItemId("item_001"), actor_id=ActorId("teacher_001"),
    )

    assert AuditEvent(**common, value_change=ValueChange("before", "after")).generation_change is None
    with pytest.raises(InvalidDomainValueError, match="value_change"):
        AuditEvent(**common)


def _event(event_type, minute):
    return AuditEvent(
        event_type=event_type, occurred_at=NOW.replace(minute=minute), plan_id=PlanId("plan_001"),
        item_id=ItemId("item_001"), actor_id=ActorId("teacher_001"), value_change=ValueChange("a", "b"),
    )


@pytest.mark.parametrize(
    ("events", "edited"),
    [
        ((), False),
        ((AuditEventType.CREATED,), False),
        ((AuditEventType.CREATED, AuditEventType.TEACHER_EDITED), True),
        ((AuditEventType.CREATED, AuditEventType.TEACHER_EDITED, AuditEventType.CONFIRMED), True),
        ((AuditEventType.CREATED, AuditEventType.TEACHER_EDITED, AuditEventType.REGENERATED), False),
        ((AuditEventType.CREATED, AuditEventType.REGENERATED, AuditEventType.TEACHER_EDITED), True),
    ],
    ids=["empty", "created", "edited", "edited-then-confirmed", "edited-then-regenerated", "regenerated-then-edited"],
)
def test_the_current_value_is_teacher_edited_only_until_a_later_regeneration(events, edited):
    history = AuditHistory(tuple(_event(kind, minute) for minute, kind in enumerate(events)))

    assert history.current_value_teacher_edited() is edited


def _links_only(minute):
    return AuditEvent(
        event_type=AuditEventType.TEACHER_EDITED, occurred_at=NOW.replace(minute=minute), plan_id=PlanId("plan_001"),
        item_id=ItemId("item_001"), actor_id=ActorId("teacher_001"), link_change=LinkChange(("a",), ("b", "c"), "v1"),
    )


@pytest.mark.parametrize(
    ("events", "edited"),
    [
        ((AuditEventType.CREATED,), False),
        ((AuditEventType.CREATED, AuditEventType.TEACHER_EDITED), True),
        ((AuditEventType.CREATED, AuditEventType.REGENERATED), False),
    ],
    ids=["generated", "text-edited", "regenerated"],
)
def test_a_links_only_edit_never_changes_whether_the_text_is_teacher_edited(events, edited):
    history = AuditHistory(tuple(_event(kind, minute) for minute, kind in enumerate(events)))

    assert history.append(_links_only(len(events))).current_value_teacher_edited() is edited


def test_a_teacher_edit_may_carry_links_only_and_only_a_teacher_edit_carries_links():
    assert _links_only(0).value_change is None
    with pytest.raises(InvalidDomainValueError, match="Only TEACHER_EDITED"):
        AuditEvent(
            event_type=AuditEventType.REGENERATED, occurred_at=NOW, plan_id=PlanId("plan_001"),
            item_id=ItemId("item_001"), actor_id=ActorId("teacher_001"), link_change=LinkChange((), ("a",), "v1"),
        )


@pytest.mark.parametrize(
    "args",
    [(("a", "a"), ("b",), "v1"), (("a",), ("a",), "v1"), (("a",), ("b",), " "), ((" ",), ("b",), "v1")],
    ids=["duplicate", "unchanged", "blank-version", "blank-id"],
)
def test_a_link_change_needs_unique_ids_a_real_change_and_a_version(args):
    with pytest.raises(InvalidDomainValueError):
        LinkChange(*args)


def test_a_link_change_may_start_from_no_links():
    assert LinkChange((), ("a",), "v1").before == ()


def _arranged(**fields):
    return AuditEvent(
        event_type=AuditEventType.ARRANGEMENT_CHANGED, occurred_at=NOW, plan_id=PlanId("plan_001"), **fields
    )


def test_an_arrangement_change_is_a_plan_level_teacher_event():
    change = ArrangementChange("together", ("a", "b"), ("a",))

    assert _arranged(actor_id=ActorId("teacher_001"), arrangement_change=change).item_id is None
    for fields in (
        {"system_actor": "system"},
        {"actor_id": ActorId("teacher_001"), "item_id": ItemId("item_001")},
        {"actor_id": ActorId("teacher_001"), "value_change": ValueChange("", "x")},
    ):
        with pytest.raises(InvalidDomainValueError, match="ARRANGEMENT_CHANGED"):
            _arranged(**{"arrangement_change": change, **fields})
    with pytest.raises(InvalidDomainValueError, match="ARRANGEMENT_CHANGED"):
        _arranged(actor_id=ActorId("teacher_001"))
    with pytest.raises(InvalidDomainValueError, match="Only ARRANGEMENT_CHANGED"):
        AuditEvent(
            event_type=AuditEventType.CONFIRMED, occurred_at=NOW, plan_id=PlanId("plan_001"),
            actor_id=ActorId("teacher_001"), arrangement_change=change,
        )


@pytest.mark.parametrize(
    "args",
    [(" ", (), ("a",)), ("w", ("a", "a"), ()), ("w", ("a",), ("a",)), ("w", (" ",), ())],
    ids=["blank-scope", "duplicate", "unchanged", "blank-id"],
)
def test_an_arrangement_change_needs_a_scope_unique_ids_and_a_real_change(args):
    with pytest.raises(InvalidDomainValueError):
        ArrangementChange(*args)


def _copied(**fields):
    return AuditEvent(
        event_type=AuditEventType.CANDIDATE_COPIED, occurred_at=NOW, plan_id=PlanId("plan_001"),
        **{"actor_id": ActorId("teacher_001"), "item_id": ItemId("item_001"), **fields},
    )


def test_a_candidate_copy_names_its_source_and_only_a_copy_does():
    event = _copied(value_change=ValueChange("", "x"), copied_from=ItemId("item_002"))

    assert AuditHistory((event,)).current_value_teacher_edited() is False
    for fields in (
        {"value_change": ValueChange("", "x")},
        {"copied_from": ItemId("item_002")},
        {"value_change": ValueChange("", "x"), "copied_from": "item_002"},
        {"value_change": ValueChange("", "x"), "copied_from": ItemId("item_002"), "item_id": None},
    ):
        with pytest.raises(InvalidDomainValueError, match="CANDIDATE_COPIED"):
            _copied(**fields)
    with pytest.raises(InvalidDomainValueError, match="Only CANDIDATE_COPIED"):
        AuditEvent(
            event_type=AuditEventType.TEACHER_EDITED, occurred_at=NOW, plan_id=PlanId("plan_001"),
            item_id=ItemId("item_001"), actor_id=ActorId("teacher_001"),
            value_change=ValueChange("", "x"), copied_from=ItemId("item_002"),
        )
