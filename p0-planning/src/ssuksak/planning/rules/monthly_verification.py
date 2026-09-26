"""Deterministic aggregation of explicitly composed Monthly verifiers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..domain.activity_reference import ActivityCandidate, ActivityCatalog
from ..domain.errors import InvalidDomainValueError
from ..domain.activity_reference import OUTDOOR_PLAY_SLOT
from ..domain.monthly_plan import MonthlyCell, MonthlyPlan
from ..domain.monthly_template import DisplayMode
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
from ..domain.provenance import EvidenceSource, EvidenceSourceType, GenerationMethod
from .errors import MonthlyRuleError

AGE_RULE_ID = "monthly.activity.supported_ages"
AGE_RULE_VERSION = "v2"
AGE_RULE_REF = VerificationRuleRef(AGE_RULE_ID, AGE_RULE_VERSION)
AGE_UNSUPPORTED_CODE = "ACTIVITY_AGE_UNSUPPORTED"
AGE_REFERENCE_NOT_VERIFIED_CODE = "ACTIVITY_REFERENCE_NOT_VERIFIED"
# v2: a filled outdoor Cell without an Activity Reference is free text. Its grounding
# is age-validated before save, but the sentence itself is not age-verified.
AGE_FREE_TEXT_NOT_VERIFIED_CODE = "ACTIVITY_FREE_TEXT_AGE_NOT_VERIFIED"


@dataclass(frozen=True, slots=True)
class RuleVerificationResult:
    executed_rule: VerificationRuleRef
    source_refs: tuple[VerificationSourceRef, ...] = ()
    findings: tuple[Violation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.executed_rule, VerificationRuleRef):
            raise InvalidDomainValueError(
                "RuleVerificationResult.executed_rule is invalid"
            )
        if not isinstance(self.source_refs, tuple) or not all(
            isinstance(source, VerificationSourceRef)
            for source in self.source_refs
        ):
            raise InvalidDomainValueError(
                "RuleVerificationResult.source_refs are invalid"
            )
        if len(set(self.source_refs)) != len(self.source_refs):
            raise InvalidDomainValueError(
                "RuleVerificationResult.source_refs must not contain duplicates"
            )
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, Violation) for finding in self.findings
        ):
            raise InvalidDomainValueError(
                "RuleVerificationResult.findings are invalid"
            )
        if any(
            finding.rule_ref != self.executed_rule
            for finding in self.findings
        ):
            raise InvalidDomainValueError(
                "RuleVerificationResult findings must match its executed rule"
            )
        declared_sources = set(self.source_refs)
        finding_sources = {
            source
            for finding in self.findings
            for item in finding.evidence
            for source in item.source_refs
        }
        if not finding_sources.issubset(declared_sources):
            raise InvalidDomainValueError(
                "RuleVerificationResult findings contain undeclared source refs"
            )


MonthlyVerifier = Callable[[MonthlyPlan], RuleVerificationResult]


def verify_monthly_activity_ages(
    plan: MonthlyPlan,
    *,
    catalog: ActivityCatalog,
) -> RuleVerificationResult:
    """Compare reference-linked Cells with approved catalog age conditions; mark free-text
    outdoor Cells NOT_VERIFIED so no active outdoor Cell has silent age coverage."""

    source_ref = _require_age_catalog(plan, catalog)
    findings: list[Violation] = []
    for cell in plan.cells:
        references = tuple(
            source
            for source in cell.evidence
            if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
        )
        if not references:
            if cell.section_key == OUTDOOR_PLAY_SLOT and cell.value.strip():
                findings.append(
                    _age_finding(
                        cell,
                        plan,
                        source_ref,
                        code=AGE_FREE_TEXT_NOT_VERIFIED_CODE,
                        finding_kind=FindingKind.NOT_VERIFIED,
                        severity=Severity.WARNING,
                        message=(
                            "Free-text outdoor play has no Activity Reference; its own "
                            "age suitability is not deterministically verified"
                        ),
                        reference_ids=(),
                    )
                )
            continue
        candidate = _trusted_activity_candidate(cell, references, catalog)
        if candidate is None:
            findings.append(
                _age_finding(
                    cell,
                    plan,
                    source_ref,
                    code=AGE_REFERENCE_NOT_VERIFIED_CODE,
                    finding_kind=FindingKind.NOT_VERIFIED,
                    severity=Severity.WARNING,
                    message=(
                        "The current Cell value is not reliably linked to its "
                        "Activity Reference"
                    ),
                    reference_ids=tuple(source.source_id for source in references),
                )
            )
        elif not candidate.supports_age_set(plan.target_ages):
            findings.append(
                _age_finding(
                    cell,
                    plan,
                    source_ref,
                    code=AGE_UNSUPPORTED_CODE,
                    finding_kind=FindingKind.VIOLATION,
                    severity=Severity.ERROR,
                    message=(
                        f"Activity {candidate.activity_id} does not support "
                        f"target ages {sorted(plan.target_ages)}"
                    ),
                    reference_ids=(candidate.activity_id,),
                )
            )
    return RuleVerificationResult(AGE_RULE_REF, (source_ref,), tuple(findings))


def _require_age_catalog(
    plan: MonthlyPlan, catalog: ActivityCatalog
) -> VerificationSourceRef:
    if not isinstance(catalog, ActivityCatalog) or not catalog.is_active:
        raise MonthlyRuleError(
            AGE_RULE_ID, "Age verification requires a Human-approved Activity Catalog"
        )
    expected = plan.activity_catalog_ref
    if expected is None or (
        expected.catalog_id,
        expected.catalog_version,
    ) != (catalog.catalog_id, catalog.catalog_version):
        raise MonthlyRuleError(
            AGE_RULE_ID,
            "Age verification requires the exact Activity Catalog pinned by the Plan",
        )
    return VerificationSourceRef(catalog.catalog_id, catalog.catalog_version)


def _trusted_activity_candidate(
    cell: MonthlyCell,
    references: tuple[EvidenceSource, ...],
    catalog: ActivityCatalog,
) -> ActivityCandidate | None:
    if len(references) != 1:
        raise MonthlyRuleError(
            AGE_RULE_ID,
            "An Activity-linked Cell must have exactly one Activity Reference",
        )
    reference = references[0]
    if reference.source_version != catalog.catalog_version:
        raise MonthlyRuleError(
            AGE_RULE_ID,
            "Activity Reference version must match the Plan Activity Catalog",
        )
    candidate = catalog.get(reference.source_id)
    if candidate is None:
        raise MonthlyRuleError(
            AGE_RULE_ID,
            "Activity Reference must resolve in the Plan Activity Catalog",
        )
    # A teacher-edited value no longer claims to be the Reference label: NOT_VERIFIED.
    if (
        cell.audit.current_value_teacher_edited()
        or cell.generation is None
        or cell.generation.method
        not in {GenerationMethod.RULE_ONLY, GenerationMethod.RULE_LLM}
    ):
        return None
    if reference.display_name != cell.value:
        raise MonthlyRuleError(
            AGE_RULE_ID,
            "Canonical Activity Reference display value must match its Cell",
        )
    return candidate


def _age_finding(
    cell: MonthlyCell,
    plan: MonthlyPlan,
    source_ref: VerificationSourceRef,
    *,
    code: str,
    finding_kind: FindingKind,
    severity: Severity,
    message: str,
    reference_ids: tuple[str, ...],
) -> Violation:
    observed = (
        f"target_ages={','.join(str(age) for age in sorted(plan.target_ages))};"
        f"current_value={cell.value};"
        f"activity_refs={','.join(reference_ids)}"
    )
    return Violation(
        rule_id=AGE_RULE_ID,
        rule_version=AGE_RULE_VERSION,
        code=code,
        finding_kind=finding_kind,
        severity=severity,
        location=ViolationLocation(cell.section_key, cell.week_id),
        message=message,
        evidence=(ViolationEvidence(observed, (source_ref,)),),
    )


def verify_monthly_plan(
    plan: MonthlyPlan,
    verifiers: tuple[MonthlyVerifier, ...] = (),
) -> VerificationReport:
    """Run every composed verifier and aggregate a deterministic report.

    Verifier exceptions deliberately propagate. They are execution failures,
    not NOT_VERIFIED findings.
    """

    if not isinstance(plan, MonthlyPlan):
        raise InvalidDomainValueError(
            "verify_monthly_plan requires MonthlyPlan"
        )
    if not isinstance(verifiers, tuple) or not all(
        callable(verifier) for verifier in verifiers
    ):
        raise InvalidDomainValueError("verifiers must be a tuple of callables")

    results: list[RuleVerificationResult] = []
    for verifier in verifiers:
        result = verifier(plan)
        if not isinstance(result, RuleVerificationResult):
            raise InvalidDomainValueError(
                "A Monthly verifier must return RuleVerificationResult"
            )
        for finding in result.findings:
            _validate_location(plan, finding)
        results.append(result)

    executed_rules = tuple(result.executed_rule for result in results)
    source_refs = tuple(
        sorted(
            {
                source
                for result in results
                for source in result.source_refs
            },
            key=lambda source: (source.source_id, source.source_version),
        )
    )
    findings = tuple(
        finding
        for result in results
        for finding in sorted(result.findings, key=_finding_sort_key)
    )
    return VerificationReport(
        target_plan_id=plan.plan_id,
        executed_rules=executed_rules,
        source_refs=source_refs,
        findings=findings,
    )


def _validate_location(plan: MonthlyPlan, finding: Violation) -> None:
    location = finding.location
    section = (
        plan.section(location.section_key)
        if location.section_key is not None
        else None
    )
    if location.section_key is not None and section is None:
        raise InvalidDomainValueError(
            "ViolationLocation.section_key must exist in the Monthly Plan"
        )
    if location.week_id is not None and location.week_id not in {
        period.week_id for period in plan.active_week_periods
    }:
        raise InvalidDomainValueError(
            "ViolationLocation.week_id must reference an active Monthly week"
        )
    if (
        section is not None
        and section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY
        and location.week_id is not None
    ):
        raise InvalidDomainValueError(
            "A month-level Section violation cannot reference a week"
        )


def _finding_sort_key(finding: Violation) -> tuple[object, ...]:
    location = finding.location
    evidence = tuple(
        (
            item.observed_value,
            tuple(
                (source.source_id, source.source_version)
                for source in item.source_refs
            ),
        )
        for item in finding.evidence
    )
    return (
        location.week_id.value if location.week_id is not None else "",
        location.section_key or "",
        finding.code,
        finding.finding_kind.value,
        finding.severity.value,
        finding.message,
        evidence,
    )
