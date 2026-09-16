from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.lineage import ParentLineage
from ssuksak.planning.domain.provenance import EvidenceSource, EvidenceSourceType

NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)


def test_plan_level_parent_lineage_is_an_immutable_snapshot():
    lineage = ParentLineage(
        parent_plan_id=PlanId("yearly_001"),
        confirmed_at=NOW,
        confirmed_by=ActorId("teacher_001"),
    )

    assert lineage.parent_item_id is None
    with pytest.raises(FrozenInstanceError):
        lineage.parent_plan_id = PlanId("yearly_002")


def test_item_level_lineage_requires_item_and_value_together():
    with pytest.raises(InvalidDomainValueError):
        ParentLineage(
            parent_plan_id=PlanId("yearly_001"),
            confirmed_at=NOW,
            confirmed_by=ActorId("teacher_001"),
            parent_item_id=ItemId("theme_001"),
        )

    lineage = ParentLineage(
        parent_plan_id=PlanId("yearly_001"),
        confirmed_at=NOW,
        confirmed_by=ActorId("teacher_001"),
        parent_item_id=ItemId("theme_001"),
        snapshot_value="봄과 우리 반",
    )
    assert lineage.snapshot_value == "봄과 우리 반"


def test_parent_lineage_and_parent_evidence_remain_separate_objects():
    lineage = ParentLineage(
        parent_plan_id=PlanId("yearly_001"),
        confirmed_at=NOW,
        confirmed_by=ActorId("teacher_001"),
    )
    evidence = EvidenceSource(
        source_type=EvidenceSourceType.PARENT_PLAN,
        source_id=str(lineage.parent_plan_id),
    )

    assert evidence.source_type is EvidenceSourceType.PARENT_PLAN
    assert not hasattr(lineage, "generation")
    assert not hasattr(lineage, "audit")


def test_parent_lineage_requires_timezone_aware_confirmation_time():
    with pytest.raises(InvalidDomainValueError):
        ParentLineage(
            parent_plan_id=PlanId("yearly_001"),
            confirmed_at=datetime(2026, 9, 16, 9, 0),  # noqa: DTZ001 - intentionally naive
            confirmed_by=ActorId("teacher_001"),
        )
