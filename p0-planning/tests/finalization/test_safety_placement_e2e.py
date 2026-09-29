from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ssuksak.planning.application import monthly_support
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.domain.monthly_constraint import CellState, ConstraintVerification
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.monthly_verification import FindingKind
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType, EvidenceSourceType, GenerationMethod
from ssuksak.planning.domain.safety_placement import SafetyKind
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.planner.contracts import MONTHLY_PROMPT_VERSION, MONTHLY_SAFETY_PROMPT_VERSION
from ssuksak.planning.rules.monthly_verification import RuleVerificationResult
from ssuksak.planning.rules.safety_placement import (
    ANNUAL_HOURS_NOT_VERIFIED,
    OFFICIAL_GROUNDING_MISSING,
    PLACEMENT_RULE_REF,
    is_official_ref,
    verify_monthly_safety_placement,
)

from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.monthly_reference_repositories import JsonSafetyPlacementPolicyRepository
from ssuksak.adapters.safety_evidence_classification_repository import (
    JsonSafetyEvidenceClassificationRepository,
)

from .harness import EXTENDED_PROFILE, SAFETY_PLACEMENT, TEACHER, PlanningHarness

STORE = JsonInstitutionEvidenceRepository().get_store()
CLASSIFICATION = JsonSafetyEvidenceClassificationRepository().get_classification()
_PENDING = replace(CLASSIFICATION, runtime_active=False)


from ssuksak.adapters.safety_reference_quality_repository import JsonSafetyReferenceQualityRepository

_POLICY_V2 = JsonSafetyPlacementPolicyRepository().get_policy("ssuksak-safety-placement-v2")
_QUALITY = JsonSafetyReferenceQualityRepository().get_quality()


@pytest.fixture(autouse=True)
def approved_v2_artifacts(monkeypatch):
    """The v2 policy and quality review are PENDING files; these tests run them as if approved."""
    policies = JsonSafetyPlacementPolicyRepository.get_policy
    monkeypatch.setattr(
        JsonSafetyPlacementPolicyRepository,
        "get_policy",
        lambda self, version: replace(_POLICY_V2, runtime_active=True)
        if version == _POLICY_V2.policy_version
        else policies(self, version),
    )
    monkeypatch.setattr(JsonSafetyReferenceQualityRepository, "get_quality", lambda self: replace(_QUALITY, runtime_active=True))


@pytest.fixture
def approved_classification(monkeypatch):
    monkeypatch.setattr(
        "ssuksak.adapters.safety_evidence_classification_repository."
        "JsonSafetyEvidenceClassificationRepository.get_classification",
        lambda self: CLASSIFICATION,
    )


def harness_policy():
    return JsonSafetyPlacementPolicyRepository().get_policy(SAFETY_PLACEMENT.policy_version)

LEGAL = "child-welfare-act-decree-annex6-2022-06-21"
# Mixed 3+4: the data has enough distinct approved supplemental topics for these months.
AGES = frozenset({3, 4})


def _generate(month, *, placement=SAFETY_PLACEMENT, mode=MonthlyGenerationMode.LLM_PLANNER):
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly(AGES).plan)
    result = harness.generate_monthly(
        parent, mode, target_month=month, profile=EXTENDED_PROFILE, safety_placement=placement
    )
    return harness, result.plan


@pytest.mark.parametrize(
    ("month", "statutory"),
    [
        (YearMonth(2026, 9), [None, "traffic_safety", None, "sexual_violence_prevention", None]),
        (YearMonth(2026, 8), [None, "infectious_disease_and_drug_misuse_prevention", None, "disaster_preparedness_safety"]),
    ],
    ids=["5-week", "4-week"],
)
def test_placement_fills_statutory_and_supplemental_safety_weeks(month, statutory, approved_classification):
    harness, plan = _generate(month)
    safety = plan.section("safety_education").cells
    request = harness.provider.monthly_requests[-1]

    assert request.prompt_version == MONTHLY_SAFETY_PROMPT_VERSION
    assert [cell.safety.category_id for cell in safety] == statutory
    for cell, category in zip(safety, statutory):
        official = [s for s in cell.evidence if s.source_type is EvidenceSourceType.SAFETY_RULE and is_official_ref(s.source_id)]
        samples = [s for s in cell.evidence if s.source_type is EvidenceSourceType.INSTITUTION_SAMPLE]
        assert cell.cell_state is CellState.FILLED
        assert cell.generation.method is GenerationMethod.RULE_LLM
        assert cell.safety.policy_version == "ssuksak-safety-placement-v2" and cell.safety.legal_rule_version == LEGAL
        if category:
            assert cell.safety.kind is SafetyKind.STATUTORY
            assert official and all(is_official_ref(s.source_id, category) and s.source_version == LEGAL for s in official)
        else:
            assert cell.safety.kind is SafetyKind.SUPPLEMENTAL
            assert samples and not official
    # Other Sections are unchanged by safety placement.
    for key in ("goals", "basic_habit", "focus", "outdoor_play"):
        assert all(cell.cell_state is CellState.FILLED for cell in plan.section(key).cells)
    report = plan.verification_report
    assert PLACEMENT_RULE_REF in report.executed_rules
    assert [(f.code, f.finding_kind) for f in report.findings] == [(ANNUAL_HOURS_NOT_VERIFIED, FindingKind.NOT_VERIFIED)]
    # Placement never claims the legal hours: the statutory constraint stays unverified.
    assert plan.constraint("STATUTORY_SAFETY_EDUCATION").verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    assert plan.status is PlanStatus.DRAFT and harness.monthly_plans.get(plan.plan_id) is plan


def test_packet_carries_official_content_and_only_safety_sample_evidence(approved_classification):
    harness, _ = _generate(YearMonth(2026, 9))
    body = json.loads(harness.provider.monthly_requests[-1].user_content)
    weeks = body["safety_plan"]["weeks"]
    traffic = weeks[1]["official_content"]

    # One official content focus per statutory week: traffic in September is item 4.
    assert traffic == [{"grounding_ref": "annex6:traffic_safety:4", "text": "바퀴 달린 탈것의 안전한 이용법"}]
    assert any(item["source_section"] == "safety_education" for item in body["evidence"])


def test_without_a_placement_selector_safety_stays_source_required():
    harness, plan = _generate(YearMonth(2026, 9), placement=None)

    assert harness.provider.monthly_requests[-1].prompt_version == MONTHLY_PROMPT_VERSION
    assert all(
        cell.cell_state is CellState.EMPTY_UNRESOLVED and cell.safety is None
        for cell in plan.section("safety_education").cells
    )
    assert PLACEMENT_RULE_REF not in plan.verification_report.executed_rules


def test_rule_only_generation_refuses_safety_placement():
    with pytest.raises(MonthlyApplicationError) as exc:
        _generate(YearMonth(2026, 9), mode=MonthlyGenerationMode.RULE_ONLY)

    assert exc.value.code == "monthly_safety_placement_requires_llm_planner"


def test_teacher_edit_keeps_placement_and_grounding_then_confirms():
    harness, plan = _generate(YearMonth(2026, 9))
    statutory = plan.section("safety_education").cells[1]

    edited = harness.edit_monthly(plan, item_id=statutory.item_id, value="교사가 고친 교통안전 문장")
    cell = edited.find_cell(statutory.item_id)[3]
    confirmed = harness.confirm_monthly(edited)

    assert cell.safety == statutory.safety and cell.evidence == statutory.evidence
    assert cell.generation == statutory.generation
    assert cell.audit.events[-1].event_type is AuditEventType.TEACHER_EDITED
    assert PLACEMENT_RULE_REF in edited.verification_report.executed_rules
    assert confirmed.status is PlanStatus.CONFIRMED


def test_verifier_flags_statutory_cells_without_official_grounding():
    _, plan = _generate(YearMonth(2026, 9))
    section = plan.section("safety_education")
    first = section.cells[1]
    stripped = replace(first, evidence=tuple(s for s in first.evidence if not is_official_ref(s.source_id)))
    plan = replace(
        plan,
        sections=tuple(
            replace(s, cells=(s.cells[0], stripped, *s.cells[2:])) if s.section_key == "safety_education" else s
            for s in plan.sections
        ),
    )

    assert OFFICIAL_GROUNDING_MISSING in [f.code for f in verify_monthly_safety_placement(plan).findings]


def test_safety_verification_violation_blocks_saving(monkeypatch):
    def failing(plan):
        result = verify_monthly_safety_placement(plan)
        cell = plan.section("safety_education").cells[0]
        violation = result.findings[0].__class__(
            rule_id=PLACEMENT_RULE_REF.rule_id,
            rule_version=PLACEMENT_RULE_REF.rule_version,
            code=OFFICIAL_GROUNDING_MISSING,
            finding_kind=FindingKind.VIOLATION,
            severity=result.findings[0].severity.__class__.ERROR,
            location=result.findings[0].location.__class__(cell.section_key, cell.week_id),
            message="forced",
            evidence=result.findings[0].evidence,
        )
        return RuleVerificationResult(result.executed_rule, result.source_refs, (violation,))

    monkeypatch.setattr(monthly_support, "verify_monthly_safety_placement", failing)
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly(AGES).plan)

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate_monthly(
            parent, MonthlyGenerationMode.LLM_PLANNER, profile=EXTENDED_PROFILE, safety_placement=SAFETY_PLACEMENT
        )
    assert exc.value.code == "monthly_safety_verification_failed"
    assert harness.monthly_plans.save_count == 0


def _classified(ref):
    record = next(r for r in STORE.records if r.record_id == ref)
    return CLASSIFICATION.classify(record)


@pytest.mark.parametrize("month", [YearMonth(2026, 9), YearMonth(2026, 8)], ids=["5-week", "4-week"])
def test_supplemental_weeks_use_only_approved_supplemental_references(month, approved_classification):
    _, plan = _generate(month)
    cells = plan.section("safety_education").cells
    supplemental = [cell for cell in cells if cell.safety.kind is SafetyKind.SUPPLEMENTAL]

    assert supplemental and all(cell.cell_state is CellState.FILLED for cell in supplemental)
    for cell in supplemental:
        samples = [s.source_id for s in cell.evidence if s.source_type is EvidenceSourceType.INSTITUTION_SAMPLE]
        assert samples and all(
            _classified(ref).kind.value == "SUPPLEMENTAL_REFERENCE" for ref in samples
        )
        assert cell.safety.category_id is None
    # Supplemental Cells never become statutory sessions.
    statutory = [cell for cell in cells if cell.safety.kind is SafetyKind.STATUTORY]
    assert len(statutory) == len(harness_policy().for_month(month.calendar_month))


@pytest.mark.parametrize("pending", ["classification", "quality"])
def test_without_approved_supplemental_grounding_generation_fails_before_the_llm(monkeypatch, pending):
    if pending == "classification":
        monkeypatch.setattr(
            "ssuksak.adapters.safety_evidence_classification_repository."
            "JsonSafetyEvidenceClassificationRepository.get_classification",
            lambda self: _PENDING,
        )
    else:
        monkeypatch.setattr(
            JsonSafetyReferenceQualityRepository, "get_quality", lambda self: replace(_QUALITY, runtime_active=False)
        )
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly(AGES).plan)

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate_monthly(
            parent, MonthlyGenerationMode.LLM_PLANNER, profile=EXTENDED_PROFILE, safety_placement=SAFETY_PLACEMENT
        )
    assert exc.value.code == "monthly_safety_grounding_insufficient"
    assert harness.provider.monthly_requests == [] and harness.monthly_plans.save_count == 0


def test_runtime_loads_the_approved_v0_2_0_classification():
    loaded = JsonSafetyEvidenceClassificationRepository().get_classification()

    assert loaded.runtime_active and loaded.multi_tag_needs_review
    assert loaded.classification_version == "safety-evidence-classification-v0.2.0"


def test_supplemental_weeks_get_distinct_primary_topics_and_statutory_weeks_one_focus():
    harness, plan = _generate(YearMonth(2026, 9))
    body = json.loads(harness.provider.monthly_requests[-1].user_content)
    weeks = body["safety_plan"]["weeks"]
    supplemental = [week for week in weeks if week["kind"] == "SUPPLEMENTAL"]
    statutory = [week for week in weeks if week["kind"] == "STATUTORY"]
    primaries = [_classified(week["primary_ref"]) for week in supplemental]

    assert len({week["primary_ref"] for week in supplemental}) == 3
    assert all(p.kind.value == "SUPPLEMENTAL_REFERENCE" for p in primaries)
    assert all(len(week["official_content"]) == 1 for week in statutory)
    assert [week["official_content"][0]["grounding_ref"] for week in statutory] == [
        "annex6:traffic_safety:4", "annex6:sexual_violence_prevention:2"
    ]
    focus = [cell.safety.official_content_focus_ref for cell in plan.section("safety_education").cells]
    assert focus == [None, "annex6:traffic_safety:4", None, "annex6:sexual_violence_prevention:2", None]


def test_single_age_three_september_uses_the_month_independent_fallback_for_distinct_topics():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly(frozenset({3})).plan)
    plan = harness.generate_monthly(
        parent, MonthlyGenerationMode.LLM_PLANNER, profile=EXTENDED_PROFILE, safety_placement=SAFETY_PLACEMENT
    ).plan
    body = json.loads(harness.provider.monthly_requests[-1].user_content)
    supplemental = [w for w in body["safety_plan"]["weeks"] if w["kind"] == "SUPPLEMENTAL"]
    records = {r.record_id: r for r in STORE.records}
    topics = [_QUALITY.usable_topic_group(records[w["primary_ref"]]) for w in supplemental]
    months = [records[w["primary_ref"]].month for w in supplemental]

    assert len(set(topics)) == 3 and len({w["primary_ref"] for w in supplemental}) == 3
    # Target-month topics first (crowd, internet), then one MONTH_INDEPENDENT cross-month topic.
    assert months[:2].count(9) + months[2:].count(9) >= 2 and any(m != 9 for m in months)
    for week in supplemental:
        record = records[week["primary_ref"]]
        if record.month != 9:
            assert _QUALITY.month_independent_topic_group(record)
    assert all(cell.cell_state is CellState.FILLED for cell in plan.section("safety_education").cells)
    assert plan.status is PlanStatus.DRAFT


def test_an_unresolved_active_safety_week_is_never_saved(monkeypatch):
    from ssuksak.planning.planner import service
    from ssuksak.planning.planner.validation import MonthlyProposalValidationResult

    monkeypatch.setattr(service, "validate_monthly_proposal", lambda *args: MonthlyProposalValidationResult(()))
    harness = PlanningHarness()
    original = harness.provider.generate_monthly

    def leave_week_one_empty(request):
        response = original(request)
        payload = json.loads(response.content)
        for section in payload["weeks"][0]["sections"]:
            if section["section_key"] == "safety_education":
                section.update(value="", unresolved=True, grounding_refs=[])
        return response.__class__(json.dumps(payload, ensure_ascii=False), response.model, response.request_id)

    harness.provider.generate_monthly = leave_week_one_empty
    parent = harness.confirm_yearly(harness.generate_yearly(AGES).plan)

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate_monthly(
            parent, MonthlyGenerationMode.LLM_PLANNER, profile=EXTENDED_PROFILE, safety_placement=SAFETY_PLACEMENT
        )
    assert exc.value.code == "monthly_safety_cell_unresolved"
    assert harness.monthly_plans.save_count == 0
