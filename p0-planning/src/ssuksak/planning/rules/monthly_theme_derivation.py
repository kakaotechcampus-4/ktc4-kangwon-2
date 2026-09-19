"""Derive a Monthly theme from one confirmed Yearly period without repositories."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.lineage import ParentLineage
from ..domain.plan import PlanStatus
from ..domain.provenance import (
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ..domain.year_month import YearMonth
from ..domain.yearly_plan import YearlyPlan
from .errors import MonthlyRuleError

RULE_ID = "monthly.theme.parent_anchor_derivation"
RULE_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class ThemeDerivation:
    value: str
    parent_lineage: ParentLineage
    evidence: tuple[EvidenceSource, ...]
    generation: GenerationMethodDetail


def derive_monthly_theme(parent: YearlyPlan, target: YearMonth) -> ThemeDerivation:
    if not isinstance(parent, YearlyPlan) or not isinstance(target, YearMonth):
        raise MonthlyRuleError(RULE_ID, "parent and target have invalid types")
    if parent.status is not PlanStatus.CONFIRMED:
        raise MonthlyRuleError(RULE_ID, "Yearly Plan must be CONFIRMED", period=target)
    period = next((item for item in parent.periods if item.period == target), None)
    if period is None:
        raise MonthlyRuleError(RULE_ID, "target month is absent from Yearly Plan", period=target)
    confirmation = next(
        (
            event
            for event in reversed(parent.audit.events)
            if event.event_type is AuditEventType.CONFIRMED
        ),
        None,
    )
    if confirmation is None or confirmation.actor_id is None:
        raise MonthlyRuleError(RULE_ID, "confirmed Yearly Plan lacks teacher confirmation audit")
    theme_reference = period.theme_references[0]
    lineage = ParentLineage(
        parent_plan_id=parent.plan_id,
        confirmed_at=confirmation.occurred_at,
        confirmed_by=confirmation.actor_id,
        parent_item_id=period.theme.item_id,
        snapshot_value=period.theme.value,
    )
    evidence = (
        EvidenceSource(
            EvidenceSourceType.PARENT_PLAN,
            source_id=parent.plan_id.value,
            source_version=target.value,
            display_name=period.theme.value,
        ),
        theme_reference,
    )
    return ThemeDerivation(
        value=period.theme.value,
        parent_lineage=lineage,
        evidence=evidence,
        generation=GenerationMethodDetail(
            GenerationMethod.RULE_ONLY,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
        ),
    )
