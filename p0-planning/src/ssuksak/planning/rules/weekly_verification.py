"""Pre-save checks of a generated Weekly Plan (docs/weekly-plan-contract.md §8 · §11-1).

Two rules, same report type as monthly (ADR-037). Verifier exceptions propagate:
they are execution failures, never NOT_VERIFIED findings.
"""

from __future__ import annotations

from ..domain.activity_reference import OUTDOOR_PLAY_SLOT, ActivityCatalog
from ..domain.monthly_verification import (
    FindingKind,
    Severity,
    VerificationReport,
    VerificationRuleRef,
    VerificationSourceRef,
    Violation,
    ViolationEvidence,
    ViolationLocation,
)
from ..domain.provenance import EvidenceSourceType
from ..domain.safety_placement import SafetyKind
from ..domain.weekly_plan import WeeklyCell, WeeklyPlan
from .errors import MonthlyRuleError
from .monthly_verification import (
    AGE_FREE_TEXT_NOT_VERIFIED_CODE,
    AGE_REFERENCE_NOT_VERIFIED_CODE,
    AGE_RULE_ID,
    AGE_RULE_REF,
    AGE_RULE_VERSION,
    AGE_UNSUPPORTED_CODE,
    RuleVerificationResult,
    _require_age_catalog,
    _trusted_activity_candidate,
)
from .safety_placement import OFFICIAL_GROUNDING_MISSING, is_official_ref

SAFETY_SECTION_KEY = "safety_education"
SAFETY_GROUNDING_RULE_ID = "weekly.safety.grounding"
SAFETY_GROUNDING_RULE_VERSION = "v1"
SAFETY_GROUNDING_RULE_REF = VerificationRuleRef(
    SAFETY_GROUNDING_RULE_ID, SAFETY_GROUNDING_RULE_VERSION
)
# §8: a safety sentence without an untouched statutory placement is grounded only by
# the parent monthly safety Cell it cites — never by a legal category it might imply.
PARENT_CITATION_INVALID = "WEEKLY_SAFETY_PARENT_CITATION_INVALID"


def verify_weekly_plan(
    plan: WeeklyPlan, catalog: ActivityCatalog | None
) -> VerificationReport:
    results = (_verify_ages(plan, catalog), _verify_safety_grounding(plan))
    return VerificationReport(
        target_plan_id=plan.plan_id,
        executed_rules=tuple(result.executed_rule for result in results),
        source_refs=tuple(
            sorted(
                {source for result in results for source in result.source_refs},
                key=lambda source: (source.source_id, source.source_version),
            )
        ),
        findings=tuple(finding for result in results for finding in result.findings),
    )


def _verify_ages(plan: WeeklyPlan, catalog: ActivityCatalog | None) -> RuleVerificationResult:
    """Monthly age rule on the one weekly outdoor Cell (same codes, no week axis)."""
    sources = (_require_age_catalog(plan, catalog),) if catalog is not None else ()
    if catalog is None and plan.activity_catalog_ref is not None:
        raise MonthlyRuleError(AGE_RULE_ID, "The Activity Catalog pinned by the Plan is missing")
    findings = []
    for cell in plan.cells:
        references = tuple(
            source for source in cell.evidence
            if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
        )
        if not references:
            if cell.section_key == OUTDOOR_PLAY_SLOT and cell.value.strip():
                findings.append(_finding(
                    AGE_RULE_ID, AGE_RULE_VERSION, AGE_FREE_TEXT_NOT_VERIFIED_CODE,
                    FindingKind.NOT_VERIFIED, Severity.WARNING, cell,
                    "Free-text outdoor play has no Activity Reference; its own "
                    "age suitability is not deterministically verified",
                    _age_observed(plan, cell, ()), sources,
                ))
            continue
        if catalog is None:
            raise MonthlyRuleError(AGE_RULE_ID, "Activity-linked Cells require the Plan Activity Catalog")
        candidate = _trusted_activity_candidate(cell, references, catalog)
        if candidate is None:
            findings.append(_finding(
                AGE_RULE_ID, AGE_RULE_VERSION, AGE_REFERENCE_NOT_VERIFIED_CODE,
                FindingKind.NOT_VERIFIED, Severity.WARNING, cell,
                "The current Cell value is not reliably linked to its Activity Reference",
                _age_observed(plan, cell, tuple(s.source_id for s in references)), sources,
            ))
        elif not candidate.supports_age_set(plan.target_ages):
            findings.append(_finding(
                AGE_RULE_ID, AGE_RULE_VERSION, AGE_UNSUPPORTED_CODE,
                FindingKind.VIOLATION, Severity.ERROR, cell,
                f"Activity {candidate.activity_id} does not support target ages {sorted(plan.target_ages)}",
                _age_observed(plan, cell, (candidate.activity_id,)), sources,
            ))
    return RuleVerificationResult(AGE_RULE_REF, sources, tuple(findings))


def _verify_safety_grounding(plan: WeeklyPlan) -> RuleVerificationResult:
    cell = next((c for c in plan.cells if c.section_key == SAFETY_SECTION_KEY), None)
    if cell is None or not cell.value.strip():
        return RuleVerificationResult(SAFETY_GROUNDING_RULE_REF)
    official = [
        s for s in cell.evidence
        if s.source_type is EvidenceSourceType.SAFETY_RULE and is_official_ref(s.source_id)
    ]
    placement = cell.safety
    if placement is not None and placement.kind is SafetyKind.STATUTORY:
        focus = placement.official_content_focus_ref
        ids = {s.source_id for s in official}
        grounded = ids == {focus} if focus is not None else bool(ids) and all(
            is_official_ref(ref, placement.category_id) for ref in ids
        )
        code = OFFICIAL_GROUNDING_MISSING
        message = f"STATUTORY {placement.category_id} requires its own official content grounding only"
    else:
        cites_parent = any(
            s.source_type is EvidenceSourceType.PARENT_PLAN for s in cell.evidence
        )
        grounded = cites_parent and bool(cell.parent_snapshots) and not any(
            s.source_type is EvidenceSourceType.SAFETY_RULE for s in cell.evidence
        )
        code = PARENT_CITATION_INVALID
        message = "Weekly safety text must cite its parent monthly safety Cell and claim no legal category"
    if grounded:
        return RuleVerificationResult(SAFETY_GROUNDING_RULE_REF)
    observed = "kind={};parent_snapshots={};evidence={}".format(
        placement.kind.value if placement is not None else "NONE",
        len(cell.parent_snapshots),
        ",".join(f"{s.source_type.value}:{s.source_id}" for s in cell.evidence) or "-",
    )
    return RuleVerificationResult(
        SAFETY_GROUNDING_RULE_REF,
        findings=(_finding(
            SAFETY_GROUNDING_RULE_ID, SAFETY_GROUNDING_RULE_VERSION, code,
            FindingKind.VIOLATION, Severity.ERROR, cell, message, observed, (),
        ),),
    )


def _age_observed(plan: WeeklyPlan, cell: WeeklyCell, reference_ids: tuple[str, ...]) -> str:
    return (
        f"target_ages={','.join(str(age) for age in sorted(plan.target_ages))};"
        f"current_value={cell.value};activity_refs={','.join(reference_ids)}"
    )


def _finding(
    rule_id: str,
    rule_version: str,
    code: str,
    kind: FindingKind,
    severity: Severity,
    cell: WeeklyCell,
    message: str,
    observed: str,
    sources: tuple[VerificationSourceRef, ...],
) -> Violation:
    return Violation(
        rule_id=rule_id,
        rule_version=rule_version,
        code=code,
        finding_kind=kind,
        severity=severity,
        location=ViolationLocation(cell.section_key),
        message=message,
        evidence=(ViolationEvidence(observed, sources),),
    )
