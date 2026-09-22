"""Deterministic aggregation of explicitly composed Monthly verifiers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..domain.errors import InvalidDomainValueError
from ..domain.monthly_plan import MonthlyPlan
from ..domain.monthly_template import DisplayMode
from ..domain.monthly_verification import (
    VerificationReport,
    VerificationRuleRef,
    VerificationSourceRef,
    Violation,
)


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
