from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.lineage import ParentLineage
from ssuksak.planning.domain.monthly_plan import MonthlyPlan, MonthlySection
from ssuksak.planning.domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    SemanticVariant,
    SectionRole,
    TemplateRef,
    TemplateSection,
)
from ssuksak.planning.domain.monthly_template_profile import TemplateProfileRef
from ssuksak.planning.domain.monthly_template_snapshot import TemplateSnapshot
from ssuksak.planning.domain.monthly_verification import (
    FindingKind,
    Severity,
    VerificationReport,
    VerificationRuleRef,
    VerificationSourceRef,
    Violation,
    ViolationEvidence,
    ViolationLocation,
)
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.monthly_verification import (
    RuleVerificationResult,
    verify_monthly_plan,
)
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods


def _plan(
    *,
    section_key: str = "focus",
    display_mode: DisplayMode = DisplayMode.WEEKLY_CELLS,
) -> MonthlyPlan:
    section = TemplateSection(
        section_key=section_key,
        role=SectionRole.CONTENT,
        activated=True,
        display_mode=display_mode,
        empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
        display_label=section_key.title(),
        semantic_variant=(
            SemanticVariant.SUBTHEME if section_key == "focus" else None
        ),
        required_for_generation=True,
        visible=True,
    )
    snapshot = TemplateSnapshot(
        profile_ref=TemplateProfileRef("profile-1", "v1"),
        base_template_ref=TemplateRef("template-1", "v1"),
        institution_ref="daycare-1",
        classroom_ref="class-1",
        sections=(section,),
    )
    return MonthlyPlan(
        plan_id=PlanId("monthly-1"),
        school_year=2026,
        target_month=YearMonth(2026, 9),
        daycare_ref="daycare-1",
        classroom_ref="class-1",
        target_ages=frozenset({3, 4}),
        status=PlanStatus.DRAFT,
        parent_lineage=ParentLineage(
            parent_plan_id=PlanId("yearly-1"),
            confirmed_at=datetime(2026, 9, 1, tzinfo=UTC),
            confirmed_by=ActorId("teacher-1"),
            parent_item_id=ItemId("yearly-theme-7"),
            snapshot_value="우리나라",
        ),
        template_snapshot=snapshot,
        week_periods=canonical_week_periods(YearMonth(2026, 9)),
        sections=(
            MonthlySection(
                section_key=section_key,
                role=SectionRole.CONTENT,
                display_mode=display_mode,
                empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
            ),
        ),
    )


SOURCE = VerificationSourceRef("activity-catalog", "v1")
AGE_RULE = VerificationRuleRef("age", "v1")
SAFETY_RULE = VerificationRuleRef("safety", "v1")


def _finding(
    *,
    rule: VerificationRuleRef = AGE_RULE,
    code: str = "AGE_OUT_OF_RANGE",
    location: ViolationLocation = ViolationLocation(),
    kind: FindingKind = FindingKind.VIOLATION,
    severity: Severity = Severity.ERROR,
) -> Violation:
    return Violation(
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        code=code,
        finding_kind=kind,
        severity=severity,
        location=location,
        message=f"finding {code}",
        evidence=(ViolationEvidence("observed activity", (SOURCE,)),),
    )


def test_finding_kind_and_severity_are_the_exact_initial_contract():
    assert {kind.value for kind in FindingKind} == {
        "VIOLATION",
        "NOT_VERIFIED",
    }
    assert {severity.value for severity in Severity} == {"ERROR", "WARNING"}


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (ViolationLocation(), (None, None)),
        (ViolationLocation(section_key="theme"), ("theme", None)),
        (
            ViolationLocation(week_id=WeekId("2026-09-W1")),
            (None, "2026-09-W1"),
        ),
        (
            ViolationLocation(
                section_key="focus", week_id=WeekId("2026-09-W2")
            ),
            ("focus", "2026-09-W2"),
        ),
    ],
)
def test_violation_location_supports_each_monthly_address(location, expected):
    week_id = location.week_id.value if location.week_id is not None else None
    assert (location.section_key, week_id) == expected


def test_violation_is_an_immutable_value_with_separate_verification_evidence():
    finding = _finding(
        kind=FindingKind.NOT_VERIFIED,
        severity=Severity.WARNING,
    )
    same = _finding(
        kind=FindingKind.NOT_VERIFIED,
        severity=Severity.WARNING,
    )

    assert finding == same
    assert finding.evidence[0].observed_value == "observed activity"
    assert finding.evidence[0].source_refs == (SOURCE,)
    with pytest.raises(FrozenInstanceError):
        finding.code = "changed"


def test_violation_does_not_contain_application_policy_fields():
    finding = _finding()

    for name in (
        "blocking",
        "save_allowed",
        "confirm_allowed",
        "retry_count",
        "auto_retry",
        "should_regenerate",
        "regenerable",
    ):
        assert not hasattr(finding, name)


def test_empty_report_means_no_rules_were_executed_not_global_success():
    report = VerificationReport(PlanId("monthly-1"), (), (), ())

    assert not report.has_executed_rules
    assert not report.has_findings
    assert report.executed_rules == ()
    assert not hasattr(report, "is_valid")


def test_report_preserves_single_and_multiple_findings_for_one_rule():
    first = _finding(location=ViolationLocation(section_key="focus"))
    second = _finding(
        code="AGE_NOT_VERIFIED",
        location=ViolationLocation(
            section_key="focus", week_id=WeekId("2026-09-W1")
        ),
        kind=FindingKind.NOT_VERIFIED,
        severity=Severity.WARNING,
    )

    single = VerificationReport(
        PlanId("monthly-1"), (AGE_RULE,), (SOURCE,), (first,)
    )
    multiple = VerificationReport(
        PlanId("monthly-1"), (AGE_RULE,), (SOURCE,), (first, second)
    )

    assert single.findings == (first,)
    assert multiple.findings == (first, second)


def test_report_rejects_findings_from_unexecuted_rules():
    with pytest.raises(InvalidDomainValueError, match="executed rules"):
        VerificationReport(
            PlanId("monthly-1"), (), (SOURCE,), (_finding(),)
        )


def test_empty_runner_has_empty_coverage_and_findings():
    report = verify_monthly_plan(_plan())

    assert report.target_plan_id == PlanId("monthly-1")
    assert report.executed_rules == ()
    assert report.source_refs == ()
    assert report.findings == ()


def test_runner_executes_all_rules_and_uses_explicit_composition_order():
    calls: list[str] = []
    week_one = ViolationLocation(
        section_key="focus", week_id=WeekId("2026-09-W1")
    )
    week_two = ViolationLocation(
        section_key="focus", week_id=WeekId("2026-09-W2")
    )

    def age(plan: MonthlyPlan) -> RuleVerificationResult:
        calls.append(f"age:{plan.plan_id}")
        return RuleVerificationResult(
            AGE_RULE,
            (SOURCE,),
            (
                _finding(code="AGE_W2", location=week_two),
                _finding(code="AGE_W1", location=week_one),
            ),
        )

    def safety(plan: MonthlyPlan) -> RuleVerificationResult:
        calls.append(f"safety:{plan.plan_id}")
        return RuleVerificationResult(SAFETY_RULE)

    report = verify_monthly_plan(_plan(), (age, safety))

    assert calls == ["age:monthly-1", "safety:monthly-1"]
    assert report.executed_rules == (AGE_RULE, SAFETY_RULE)
    assert tuple(item.code for item in report.findings) == (
        "AGE_W1",
        "AGE_W2",
    )
    assert report.source_refs == (SOURCE,)


def test_runner_order_is_deterministic_for_the_same_findings():
    locations = (
        ViolationLocation(week_id=WeekId("2026-09-W2")),
        ViolationLocation(section_key="focus"),
        ViolationLocation(),
    )

    def result(findings):
        return lambda plan: RuleVerificationResult(
            AGE_RULE, (SOURCE,), tuple(findings)
        )

    forward = tuple(_finding(location=location) for location in locations)
    backward = tuple(reversed(forward))

    first = verify_monthly_plan(_plan(), (result(forward),))
    second = verify_monthly_plan(_plan(), (result(backward),))

    assert first == second


def test_runner_does_not_convert_verifier_exceptions_to_not_verified():
    calls: list[str] = []

    def age(plan: MonthlyPlan) -> RuleVerificationResult:
        calls.append("age")
        return RuleVerificationResult(AGE_RULE)

    def broken(plan: MonthlyPlan) -> RuleVerificationResult:
        calls.append("broken")
        raise RuntimeError("verifier failed")

    with pytest.raises(RuntimeError, match="verifier failed"):
        verify_monthly_plan(_plan(), (age, broken))

    assert calls == ["age", "broken"]


def test_runner_records_only_rules_that_are_actually_composed():
    report = verify_monthly_plan(
        _plan(), (lambda plan: RuleVerificationResult(AGE_RULE),)
    )

    assert report.executed_rules == (AGE_RULE,)
    assert SAFETY_RULE not in report.executed_rules


@pytest.mark.parametrize(
    ("plan", "location", "message"),
    [
        (
            _plan(),
            ViolationLocation(section_key="unknown"),
            "section_key",
        ),
        (
            _plan(),
            ViolationLocation(week_id=WeekId("2026-09-W9")),
            "active Monthly week",
        ),
        (
            _plan(
                section_key="theme",
                display_mode=DisplayMode.MONTHLY_MERGED_SUMMARY,
            ),
            ViolationLocation(
                section_key="theme", week_id=WeekId("2026-09-W1")
            ),
            "month-level Section",
        ),
    ],
)
def test_runner_rejects_locations_outside_the_monthly_plan(
    plan, location, message
):
    finding = _finding(location=location)

    with pytest.raises(InvalidDomainValueError, match=message):
        verify_monthly_plan(
            plan,
            (
                lambda current: RuleVerificationResult(
                    AGE_RULE, (SOURCE,), (finding,)
                ),
            ),
        )


def test_rule_and_source_versions_are_preserved():
    report = verify_monthly_plan(
        _plan(),
        (
            lambda plan: RuleVerificationResult(
                AGE_RULE, (SOURCE,), (_finding(),)
            ),
        ),
    )

    assert report.executed_rules[0].rule_version == "v1"
    assert report.source_refs[0].source_version == "v1"
