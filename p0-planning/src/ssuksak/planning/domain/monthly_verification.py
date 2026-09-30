"""Immutable findings returned by deterministic Monthly Plan verification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import InvalidDomainValueError
from .identifiers import PlanId
from .week_period import WeekId


def _require_non_blank(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDomainValueError(f"{path} must be non-blank")


def _require_unique(values: tuple[object, ...], path: str) -> None:
    if len(set(values)) != len(values):
        raise InvalidDomainValueError(f"{path} must not contain duplicates")


class FindingKind(str, Enum):
    VIOLATION = "VIOLATION"
    NOT_VERIFIED = "NOT_VERIFIED"


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class VerificationRuleRef:
    rule_id: str
    rule_version: str

    def __post_init__(self) -> None:
        _require_non_blank(self.rule_id, "VerificationRuleRef.rule_id")
        _require_non_blank(
            self.rule_version, "VerificationRuleRef.rule_version"
        )


@dataclass(frozen=True, slots=True)
class VerificationSourceRef:
    """Versioned trusted data used by a verification rule."""

    source_id: str
    source_version: str

    def __post_init__(self) -> None:
        _require_non_blank(self.source_id, "VerificationSourceRef.source_id")
        _require_non_blank(
            self.source_version, "VerificationSourceRef.source_version"
        )


@dataclass(frozen=True, slots=True)
class ViolationEvidence:
    """Observed Plan value and any trusted data references used to assess it."""

    observed_value: str
    source_refs: tuple[VerificationSourceRef, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank(
            self.observed_value, "ViolationEvidence.observed_value"
        )
        if not isinstance(self.source_refs, tuple) or not all(
            isinstance(source, VerificationSourceRef)
            for source in self.source_refs
        ):
            raise InvalidDomainValueError(
                "ViolationEvidence.source_refs must contain "
                "VerificationSourceRef values"
            )
        _require_unique(
            self.source_refs, "ViolationEvidence.source_refs"
        )


@dataclass(frozen=True, slots=True)
class ViolationLocation:
    section_key: str | None = None
    week_id: WeekId | None = None

    def __post_init__(self) -> None:
        if self.section_key is not None:
            _require_non_blank(
                self.section_key, "ViolationLocation.section_key"
            )
        if self.week_id is not None and not isinstance(self.week_id, WeekId):
            raise InvalidDomainValueError(
                "ViolationLocation.week_id must be WeekId when set"
            )


@dataclass(frozen=True, slots=True)
class Violation:
    """A verification finding record, including outcomes not verified."""

    rule_id: str
    rule_version: str
    code: str
    finding_kind: FindingKind
    severity: Severity
    location: ViolationLocation
    message: str
    evidence: tuple[ViolationEvidence, ...]

    def __post_init__(self) -> None:
        for name in ("rule_id", "rule_version", "code", "message"):
            _require_non_blank(getattr(self, name), f"Violation.{name}")
        if not isinstance(self.finding_kind, FindingKind):
            raise InvalidDomainValueError(
                "Violation.finding_kind is invalid"
            )
        if not isinstance(self.severity, Severity):
            raise InvalidDomainValueError("Violation.severity is invalid")
        if not isinstance(self.location, ViolationLocation):
            raise InvalidDomainValueError("Violation.location is invalid")
        if not isinstance(self.evidence, tuple) or not self.evidence or not all(
            isinstance(item, ViolationEvidence) for item in self.evidence
        ):
            raise InvalidDomainValueError(
                "Violation.evidence must contain ViolationEvidence values"
            )

    @property
    def rule_ref(self) -> VerificationRuleRef:
        return VerificationRuleRef(self.rule_id, self.rule_version)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Rule Engine output without Application save or confirm policy."""

    target_plan_id: PlanId
    executed_rules: tuple[VerificationRuleRef, ...]
    source_refs: tuple[VerificationSourceRef, ...]
    findings: tuple[Violation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_plan_id, PlanId):
            raise InvalidDomainValueError(
                "VerificationReport.target_plan_id must be PlanId"
            )
        self._validate_tuple(
            "executed_rules", self.executed_rules, VerificationRuleRef
        )
        self._validate_tuple(
            "source_refs", self.source_refs, VerificationSourceRef
        )
        self._validate_tuple("findings", self.findings, Violation)
        _require_unique(
            self.executed_rules, "VerificationReport.executed_rules"
        )
        _require_unique(self.source_refs, "VerificationReport.source_refs")

        executed = set(self.executed_rules)
        if any(finding.rule_ref not in executed for finding in self.findings):
            raise InvalidDomainValueError(
                "VerificationReport findings must belong to executed rules"
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
                "VerificationReport findings contain undeclared source refs"
            )

    @staticmethod
    def _validate_tuple(name: str, values: object, item_type: type) -> None:
        if not isinstance(values, tuple) or not all(
            isinstance(value, item_type) for value in values
        ):
            raise InvalidDomainValueError(
                f"VerificationReport.{name} contains invalid values"
            )

    @property
    def has_executed_rules(self) -> bool:
        return bool(self.executed_rules)

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)
