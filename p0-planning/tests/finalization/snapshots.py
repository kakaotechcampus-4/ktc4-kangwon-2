from __future__ import annotations

from typing import Any

from ssuksak.planning.application.monthly_dto import (
    GenerateMonthlyPlanResult,
    RegenerateMonthlyPlanItemResult,
)
from ssuksak.planning.domain.identifiers import ItemId
from ssuksak.planning.domain.monthly_plan import MonthlyCell, MonthlyPlan
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditHistory,
    EvidenceSource,
    GenerationMethodDetail,
)
from ssuksak.planning.domain.yearly_plan import YearlyPlan


def _generation(value: GenerationMethodDetail | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "method": value.method.value,
        "rule_id": value.rule_id,
        "rule_version": value.rule_version,
    }


def _evidence(value: EvidenceSource) -> dict[str, Any]:
    return {
        "type": value.source_type.value,
        "source_id": value.source_id,
        "source_version": value.source_version,
    }


def _event(value: AuditEvent) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": value.event_type.value,
        "actor": value.actor_id.value if value.actor_id is not None else None,
        "system_actor": value.system_actor,
    }
    if value.value_change is not None:
        result["value_change"] = {
            "before": value.value_change.before,
            "after": value.value_change.after,
        }
    if value.generation_change is not None:
        result["generation_change"] = {
            "before": _generation(value.generation_change.before),
            "after": _generation(value.generation_change.after),
        }
    return result


def _audit(value: AuditHistory) -> list[dict[str, Any]]:
    return [_event(event) for event in value.events]


def yearly_snapshot(plan: YearlyPlan) -> dict[str, Any]:
    return {
        "schema": "yearly-golden-v1",
        "school_year": plan.school_year,
        "status": plan.status.value,
        "target_ages": sorted(plan.target_ages),
        "audit": _audit(plan.audit),
        "periods": [
            {
                "period": period.period.value,
                "theme_id": period.theme_id,
                "value": period.theme.value,
                "generation": _generation(period.theme.generation),
                "evidence": [_evidence(item) for item in period.theme.evidence],
                "audit": _audit(period.theme.audit),
            }
            for period in plan.periods
        ],
    }


def _verification(plan: MonthlyPlan) -> dict[str, Any] | None:
    """Deterministic VerificationReport contract; messages and observed values are excluded."""
    report = plan.verification_report
    if report is None:
        return None
    return {
        "targets_plan": report.target_plan_id == plan.plan_id,
        "executed_rules": [
            {"rule_id": rule.rule_id, "rule_version": rule.rule_version}
            for rule in report.executed_rules
        ],
        "source_refs": [
            {"source_id": source.source_id, "source_version": source.source_version}
            for source in report.source_refs
        ],
        "findings": [
            {
                "rule_id": finding.rule_id,
                "rule_version": finding.rule_version,
                "code": finding.code,
                "finding_kind": finding.finding_kind.value,
                "severity": finding.severity.value,
                "section_key": finding.location.section_key,
                "week_id": (
                    finding.location.week_id.value
                    if finding.location.week_id is not None
                    else None
                ),
            }
            for finding in report.findings
        ],
    }


def _cell(value: MonthlyCell) -> dict[str, Any]:
    return {
        "week_id": value.week_id.value if value.week_id is not None else None,
        "value": value.value,
        "state": value.cell_state.value,
        "generation": _generation(value.generation),
        "evidence": [_evidence(item) for item in value.evidence],
        "audit": _audit(value.audit),
    }


def monthly_snapshot(result: GenerateMonthlyPlanResult) -> dict[str, Any]:
    plan = result.plan
    return {
        "schema": "monthly-golden-v2",
        "target_month": plan.target_month.value,
        "status": plan.status.value,
        "target_ages": sorted(plan.target_ages),
        "generation_mode": plan.generation_mode.value,
        "template": str(plan.template_ref),
        "activity_catalog": (
            None
            if plan.activity_catalog_ref is None
            else {
                "id": plan.activity_catalog_ref.catalog_id,
                "version": plan.activity_catalog_ref.catalog_version,
            }
        ),
        "parent_lineage": {
            "has_parent_plan_id": bool(plan.parent_lineage.parent_plan_id.value),
            "has_parent_item_id": plan.parent_lineage.parent_item_id is not None,
            "snapshot_value": plan.parent_lineage.snapshot_value,
            "confirmed_by": plan.parent_lineage.confirmed_by.value,
        },
        "weeks": [
            {
                "week_id": period.week_id.value,
                "start": period.start_date.isoformat(),
                "end": period.end_date.isoformat(),
                "active": period.active,
            }
            for period in plan.week_periods
        ],
        "sections": [
            {
                "key": section.section_key,
                "role": section.role.value,
                "display_mode": (
                    section.display_mode.value
                    if section.display_mode is not None
                    else None
                ),
                "cells": [_cell(cell) for cell in section.cells],
            }
            for section in plan.sections
        ],
        "constraints": [
            {
                "code": item.constraint.code,
                "verification": item.verification.value,
                "rule_version": item.rule_version,
                "affected_sections": list(item.affected_section_keys),
            }
            for item in plan.constraint_assessments
        ],
        "activity_selections": [
            {
                "week_id": item.week_id,
                "selected_activity_id": item.trace.selected_activity_id,
                "reason_codes": list(item.trace.reason_codes),
            }
            for item in result.activity_selections
        ],
        "context_packet_fingerprint": result.context_packet_fingerprint,
        "audit": _audit(plan.audit),
        "verification": _verification(plan),
    }


def cell_regeneration_snapshot(
    before: MonthlyPlan,
    result: RegenerateMonthlyPlanItemResult,
    target_item_id: ItemId,
) -> dict[str, Any]:
    after = result.plan
    before_target = before.find_cell(target_item_id)
    after_target = after.find_cell(target_item_id)
    assert before_target is not None and after_target is not None
    siblings_before = {
        cell.item_id: cell for cell in before.cells if cell.item_id != target_item_id
    }
    siblings_after = {
        cell.item_id: cell for cell in after.cells if cell.item_id != target_item_id
    }
    outcome = result.planner_outcome
    return {
        "schema": "monthly-cell-regeneration-golden-v2",
        "generation_mode": after.generation_mode.value,
        "section": after_target[3].section_key,
        "week_id": (
            after_target[3].week_id.value
            if after_target[3].week_id is not None
            else None
        ),
        "before": _cell(before_target[3]),
        "after": _cell(after_target[3]),
        "siblings": {
            "count": len(siblings_before),
            "identities_preserved": siblings_before.keys() == siblings_after.keys()
            and all(
                siblings_before[item_id] is siblings_after[item_id]
                for item_id in siblings_before
            ),
        },
        "planner": (
            None
            if outcome is None
            else {
                "model": outcome.model,
                "prompt_version": outcome.prompt_version,
                "packet_fingerprint": outcome.packet_fingerprint,
                "plan_snapshot_fingerprint": outcome.plan_snapshot_fingerprint,
            }
        ),
        "report_refreshed": after.verification_report is not before.verification_report,
        "verification": _verification(after),
    }
