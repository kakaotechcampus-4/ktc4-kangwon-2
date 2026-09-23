from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json

import pytest

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.evidence_classification_repository import (
    InMemoryEvidenceClassificationRepository,
    JsonEvidenceClassificationRepository,
)
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.in_memory_template_profile_repository import (
    InMemoryTemplateProfileRepository,
)
from ssuksak.adapters.institution_evidence_repository import (
    JsonInstitutionEvidenceRepository,
)
from ssuksak.adapters.json_activity_reference_repository import (
    JsonActivityReferenceRepository,
)
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_dto import (
    ActivityCatalogSelector,
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    RegenerateMonthlyPlanItemCommand,
    SafetyRuleSelector,
)
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.application import monthly_support
from ssuksak.planning.application.monthly_support import MonthlyContextPipeline
from ssuksak.planning.application.ports import OptionalContextStatus
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.context.builder import ContextPacketBuilder
from ssuksak.planning.domain.errors import (
    InvalidDomainValueError,
    InvalidStateTransitionError,
)
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.monthly_constraint import CellState
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from ssuksak.planning.domain.monthly_template import (
    DisplayMode,
    SectionRole,
    SemanticVariant,
    TemplateRef,
)
from ssuksak.planning.domain.monthly_template_profile import (
    TemplateProfile,
    TemplateProfileRef,
)
from ssuksak.planning.domain.monthly_verification import (
    FindingKind,
    Severity,
    VerificationSourceRef,
    Violation,
    ViolationEvidence,
    ViolationLocation,
)
from ssuksak.planning.domain.plan import PlanItem, PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.classification import SemanticClass
from ssuksak.planning.domain.yearly_plan import YearlyPeriod, YearlyPlan
from ssuksak.planning.planner.cell_service import MonthlyCellPlanner
from ssuksak.planning.planner.contracts import (
    MONTHLY_CELL_PROMPT_VERSION,
    MONTHLY_MODEL,
    MonthlyCellPlanningRequest,
    MonthlyPlanningRequest,
    ProposalRejectedError,
    RawLlmResponse,
)
from ssuksak.planning.planner.service import MonthlyPlanner
from ssuksak.planning.rules.monthly_verification import (
    AGE_REFERENCE_NOT_VERIFIED_CODE,
    AGE_RULE_ID,
    AGE_RULE_REF,
    AGE_RULE_VERSION,
    AGE_UNSUPPORTED_CODE,
    RuleVerificationResult,
)

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
TEACHER = ActorId("teacher_001")
PARENT_PLAN_ID = PlanId("yearly_plan_001")
TARGET_MONTH = YearMonth(2026, 9)
TARGET_THEME_ID = "yr_theme_korea_and_world_cultures"
TEMPLATE = TemplateRef(
    "ssuksak.monthly-template-a", "monthly-template-a-v0.2.0"
)
RULE_TEMPLATE = TemplateRef(
    "ssuksak.monthly-template-a", "monthly-template-a-v0.1.0"
)
PROFILE = TemplateProfileRef("monthly-profile-classroom-001", "v2")
RULE_PROFILE = TemplateProfileRef("monthly-profile-classroom-001", "v1")
COMMON_PROFILE = TemplateProfileRef("monthly-profile-institution", "v1")
WRONG_CLASS_PROFILE = TemplateProfileRef("monthly-profile-wrong-class", "v1")
ACTIVITY_CATALOG = ActivityCatalogSelector(
    "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
)
SAFETY_RULE = SafetyRuleSelector(
    "child-welfare-act-decree-annex6-2022-06-21"
)

EVIDENCE_REPOSITORY = JsonInstitutionEvidenceRepository()
CLASSIFICATION_REPOSITORY = JsonEvidenceClassificationRepository()


def grounding_ref_for(request, section_key: str) -> str | None:
    """Pick the first supplied evidence ref allowed for this Section's grounding_class."""
    body = json.loads(request.user_content)
    expected = next(
        (
            section.get("grounding_class")
            for section in body["generation_schema"]["sections"]
            if section["section_key"] == section_key
        ),
        None,
    )
    refs = sorted(
        item["grounding_ref"]
        for item in body["evidence"]
        if item["grounding_class"] == expected
    )
    return refs[0] if refs else None


def _profile(
    template_repository: JsonMonthlyTemplateRepository,
    template_ref: TemplateRef,
    profile_ref: TemplateProfileRef,
    *,
    classroom_ref: str | None = "classroom_001",
) -> TemplateProfile:
    template = template_repository.get_template(
        template_ref.template_id, template_ref.template_version
    )
    assert template is not None
    labels = {
        "theme": "Theme",
        "week_axis": "Week",
        "outdoor_play": "Outdoor play",
        "safety_education": "Safety education",
        "focus": "Subtheme",
    }
    sections = tuple(
        replace(
            section,
            display_label=labels[section.section_key],
            semantic_variant=(
                SemanticVariant.SUBTHEME
                if section.section_key == "focus"
                else None
            ),
        )
        for section in template.activated_sections
    )
    return TemplateProfile(
        profile_ref=profile_ref,
        institution_ref="daycare_001",
        classroom_ref=classroom_ref,
        base_template_ref=template.template_ref,
        selected_optional_keys=("focus",) if template.section("focus").activated else (),
        sections=sections,
    )


def _yearly_plan(*, confirmed: bool = True) -> YearlyPlan:
    months = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2)
    periods = []
    for ordinal, month in enumerate(months, start=1):
        year = 2026 if month >= 3 else 2027
        period = YearMonth(year, month)
        item_id = ItemId(f"yearly_theme_{ordinal:02d}")
        theme_id = (
            TARGET_THEME_ID if period == TARGET_MONTH else f"theme-{period.value}"
        )
        item = PlanItem(
            item_id=item_id,
            value=(
                "Korea and world cultures"
                if period == TARGET_MONTH
                else f"Theme {period.value}"
            ),
            evidence=(
                EvidenceSource(
                    EvidenceSourceType.THEME_REFERENCE,
                    theme_id,
                    "theme-reference-v0.1.2",
                ),
            ),
            generation=GenerationMethodDetail(
                GenerationMethod.RULE_ONLY, "yearly.test.selection", "v1"
            ),
            audit=AuditHistory(
                (
                    AuditEvent(
                        AuditEventType.CREATED,
                        NOW,
                        PARENT_PLAN_ID,
                        item_id=item_id,
                        system_actor="yearly_application",
                    ),
                )
            ),
        )
        periods.append(YearlyPeriod(period, item))
    plan = YearlyPlan(
        plan_id=PARENT_PLAN_ID,
        school_year=2026,
        classroom_ref="classroom_001",
        target_ages=frozenset({3, 4}),
        status=PlanStatus.DRAFT,
        periods=tuple(periods),
        audit=AuditHistory(
            (
                AuditEvent(
                    AuditEventType.CREATED,
                    NOW,
                    PARENT_PLAN_ID,
                    system_actor="yearly_application",
                ),
            )
        ),
    )
    return plan.confirm(actor_id=TEACHER, occurred_at=NOW) if confirmed else plan


class RequestAwareMonthlyLlm:
    """Deterministic provider whose response follows each validated request."""

    def __init__(self) -> None:
        self.monthly_requests: list[MonthlyPlanningRequest] = []
        self.cell_requests: list[MonthlyCellPlanningRequest] = []

    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        self.monthly_requests.append(request)
        month_sections = []
        weekly_keys = []
        for section in request.template_snapshot.sections:
            if section.role is SectionRole.AXIS:
                continue
            if section.display_mode is DisplayMode.MONTHLY_MERGED_SUMMARY:
                if section.section_key == "theme":
                    month_sections.append(
                        {
                            "section_key": "theme",
                            "value": request.expected_theme_value,
                            "unresolved": False,
                            "reference_id": request.expected_theme_id,
                            "grounding_refs": [],
                        }
                    )
                elif section.required_for_generation:
                    month_sections.append(
                        {
                            "section_key": section.section_key,
                            "value": f"Context-based {section.section_key}",
                            "unresolved": False,
                            "reference_id": None,
                            "grounding_refs": [
                                grounding_ref_for(request, section.section_key)
                            ],
                        }
                    )
            elif section.display_mode is DisplayMode.WEEKLY_CELLS:
                weekly_keys.append(section.section_key)
        payload = {
            "target_month": request.target_month.value,
            "month_sections": month_sections,
            "weeks": [
                {
                    "week_id": week_id.value,
                    "sections": [
                        {
                            "section_key": key,
                            "value": (
                                ""
                                if key == "safety_education"
                                else f"Context-based {key} {index}"
                            ),
                            "unresolved": key == "safety_education",
                            "reference_id": None,
                            "grounding_refs": (
                                []
                                if key == "safety_education"
                                else [grounding_ref_for(request, key)]
                            ),
                        }
                        for key in weekly_keys
                        if key == "safety_education"
                        or grounding_ref_for(request, key) is not None
                    ],
                }
                for index, week_id in enumerate(
                    request.expected_week_ids, start=1
                )
            ],
        }
        return RawLlmResponse(
            json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "monthly-1"
        )

    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse:
        self.cell_requests.append(request)
        grounding_ref = grounding_ref_for(request, request.target_section_key)
        payload = {
            "target_month": request.target_month.value,
            "target_week_id": request.target_week_id.value,
            "section": {
                "section_key": request.target_section_key,
                "value": f"Regenerated {request.target_section_key} value",
                "unresolved": False,
                "reference_id": None,
                "grounding_refs": [grounding_ref],
            },
        }
        return RawLlmResponse(
            json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "cell-1"
        )


class ExplodingMonthlyLlm(RequestAwareMonthlyLlm):
    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        self.monthly_requests.append(request)
        raise RuntimeError("provider unavailable")


class ExplodingCellLlm(RequestAwareMonthlyLlm):
    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse:
        self.cell_requests.append(request)
        raise RuntimeError("provider unavailable")


class ReferenceAndGroundingCellLlm(RequestAwareMonthlyLlm):
    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse:
        self.cell_requests.append(request)
        reference_id, value = request.reference_labels[0]
        grounding_ref = grounding_ref_for(request, request.target_section_key)
        return RawLlmResponse(
            json.dumps(
                {
                    "target_month": request.target_month.value,
                    "target_week_id": request.target_week_id.value,
                    "section": {
                        "section_key": request.target_section_key,
                        "value": value,
                        "unresolved": False,
                        "reference_id": reference_id,
                        "grounding_refs": [grounding_ref],
                    },
                },
                ensure_ascii=False,
            ),
            MONTHLY_MODEL,
            "reference-and-grounding-cell",
        )


class LegacyShapeMonthlyLlm(RequestAwareMonthlyLlm):
    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        self.monthly_requests.append(request)
        return RawLlmResponse(
            json.dumps(
                {
                    "target_month": request.target_month.value,
                    "theme_id": request.expected_theme_id,
                    "month_flow_rationale": "legacy",
                    "weeks": [],
                }
            ),
            MONTHLY_MODEL,
            "legacy-monthly-1",
        )


class InstitutionInputMonthlyLlm(RequestAwareMonthlyLlm):
    """Returns an otherwise valid proposal plus an invented event_schedule."""

    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        payload = json.loads(super().generate_monthly(request).content)
        for week in payload["weeks"]:
            week["sections"].append(
                {
                    "section_key": "event_schedule",
                    "value": "Invented autumn sports day",
                    "unresolved": False,
                    "reference_id": None,
                    "grounding_refs": [sorted(request.valid_grounding_refs)[0]],
                }
            )
        return RawLlmResponse(
            json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "monthly-1"
        )


def _institution_input_profile(
    template_repository: JsonMonthlyTemplateRepository, section_key: str
) -> TemplateProfile:
    base = _profile(
        template_repository,
        TEMPLATE,
        TemplateProfileRef(f"monthly-profile-{section_key}", "v1"),
    )
    template = template_repository.get_template(
        TEMPLATE.template_id, TEMPLATE.template_version
    )
    assert template is not None
    section = replace(
        template.section(section_key),
        activated=True,
        display_label={"event_schedule": "Events", "drill": "Drill"}[section_key],
        display_mode=DisplayMode.WEEKLY_CELLS,
        visible=True,
    )
    return replace(
        base,
        selected_optional_keys=(*base.selected_optional_keys, section_key),
        sections=(*base.sections, section),
    )


class Harness:
    def __init__(self, *, parent_confirmed: bool = True) -> None:
        self.parents: InMemoryPlanRepository[YearlyPlan] = InMemoryPlanRepository()
        self.plans: InMemoryPlanRepository[MonthlyPlan] = InMemoryPlanRepository()
        self.parents.save(PARENT_PLAN_ID, _yearly_plan(confirmed=parent_confirmed))
        self.templates = JsonMonthlyTemplateRepository()
        self.profiles = InMemoryTemplateProfileRepository(
            (
                _profile(self.templates, TEMPLATE, PROFILE),
                _profile(self.templates, RULE_TEMPLATE, RULE_PROFILE),
                _profile(
                    self.templates,
                    TEMPLATE,
                    COMMON_PROFILE,
                    classroom_ref=None,
                ),
                _profile(
                    self.templates,
                    TEMPLATE,
                    WRONG_CLASS_PROFILE,
                    classroom_ref="classroom_other",
                ),
            )
        )
        self.safety = JsonSafetyLegalRuleRepository()
        self.activities = JsonActivityReferenceRepository()
        self.clock = FixedClock(NOW)
        self.ids = DeterministicIdGenerator("monthly")
        self.context = MonthlyContextPipeline(
            evidence_repository=EVIDENCE_REPOSITORY,
            classification_repository=CLASSIFICATION_REPOSITORY,
            context_builder=ContextPacketBuilder(),
        )

    def command(
        self, mode: MonthlyGenerationMode = MonthlyGenerationMode.RULE_ONLY
    ) -> GenerateMonthlyPlanCommand:
        return GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=PARENT_PLAN_ID,
            target_month=TARGET_MONTH,
            daycare_ref="daycare_001",
            profile_ref=PROFILE,
            safety_rule=SAFETY_RULE,
            generation_mode=mode,
            activity_catalog=ACTIVITY_CATALOG,
        )

    def generate(
        self,
        mode: MonthlyGenerationMode = MonthlyGenerationMode.RULE_ONLY,
        *,
        provider: RequestAwareMonthlyLlm | None = None,
        optional_context=None,
        command: GenerateMonthlyPlanCommand | None = None,
    ):
        planner = MonthlyPlanner(provider) if provider is not None else None
        use_case = GenerateMonthlyPlan(
            parent_plan_repository=self.parents,
            plan_repository=self.plans,
            profile_repository=self.profiles,
            safety_repository=self.safety,
            activity_repository=self.activities,
            clock=self.clock,
            id_generator=self.ids,
            context_pipeline=self.context,
            planner=planner,
            optional_context=optional_context,
        )
        return use_case.execute(command or self.command(mode))

    def regenerate(
        self, provider: RequestAwareMonthlyLlm | None = None
    ) -> RegenerateMonthlyPlanItem:
        return RegenerateMonthlyPlanItem(
            plan_repository=self.plans,
            clock=self.clock,
            activity_repository=self.activities,
            context_pipeline=self.context,
            cell_planner=(
                MonthlyCellPlanner(provider) if provider is not None else None
            ),
        )


def _cell(plan: MonthlyPlan, section: str, index: int = 0):
    monthly_section = plan.section(section)
    assert monthly_section is not None
    return monthly_section.cells[index]


def _age_result(plan, catalog, kind, severity, code):
    source = VerificationSourceRef(catalog.catalog_id, catalog.catalog_version)
    cell = _cell(plan, "outdoor_play")
    return RuleVerificationResult(
        AGE_RULE_REF,
        (source,),
        (
            Violation(
                AGE_RULE_ID,
                AGE_RULE_VERSION,
                code,
                kind,
                severity,
                ViolationLocation(cell.section_key, cell.week_id),
                "forced application integration finding",
                (ViolationEvidence("observed application state", (source,)),),
            ),
        ),
    )


def _fail_age_verification(plan, *, catalog):
    raise RuntimeError("verifier unavailable")


def _with_age_mismatch(harness: Harness, plan: MonthlyPlan) -> MonthlyPlan:
    ref = plan.activity_catalog_ref
    assert ref is not None
    catalog = harness.activities.get_catalog(ref.catalog_id, ref.catalog_version)
    assert catalog is not None
    candidate = next(
        item
        for item in catalog.activities
        if not item.supports_age_set(plan.target_ages)
    )
    cell = _cell(plan, "outdoor_play")
    evidence = tuple(
        source
        for source in cell.evidence
        if source.source_type is not EvidenceSourceType.ACTIVITY_REFERENCE
    ) + (
        EvidenceSource(
            EvidenceSourceType.ACTIVITY_REFERENCE,
            candidate.activity_id,
            catalog.catalog_version,
            display_name=candidate.label,
        ),
    )
    return plan.replace_cell(
        cell.item_id,
        replace(cell, value=candidate.label, evidence=evidence),
    )


def test_rule_only_generation_assembles_complete_draft_and_saves_once():
    harness = Harness()

    result = harness.generate()
    plan = result.plan

    assert plan.status is PlanStatus.DRAFT
    assert plan.generation_mode is MonthlyGenerationMode.RULE_ONLY
    assert plan.template_snapshot.profile_ref == PROFILE
    assert plan.template_ref == TEMPLATE
    assert plan.parent_lineage.parent_plan_id == PARENT_PLAN_ID
    assert plan.parent_lineage.parent_item_id == ItemId("yearly_theme_07")
    assert tuple(section.section_key for section in plan.sections) == (
        "theme",
        "week_axis",
        "outdoor_play",
        "safety_education",
        "focus",
    )
    assert len(plan.active_week_periods) == 5
    assert {
        source.source_type for source in _cell(plan, "outdoor_play").evidence
    } == {
        EvidenceSourceType.PARENT_PLAN,
        EvidenceSourceType.ACTIVITY_REFERENCE,
    }
    assert _cell(plan, "focus").cell_state is CellState.EMPTY_VALID
    assert all(
        cell.cell_state is CellState.EMPTY_UNRESOLVED
        for cell in plan.section("safety_education").cells
    )
    assert len(result.activity_selections) == len(plan.active_week_periods)
    assert harness.plans.save_count == 1
    assert harness.plans.get(plan.plan_id) is plan


def test_generation_stores_the_actual_age_rule_coverage():
    harness = Harness()

    plan = harness.generate().plan
    report = plan.verification_report

    assert report is not None
    assert report.target_plan_id == plan.plan_id
    assert report.executed_rules == (AGE_RULE_REF,)
    assert report.source_refs == (
        VerificationSourceRef(
            ACTIVITY_CATALOG.catalog_id, ACTIVITY_CATALOG.catalog_version
        ),
    )
    assert report.findings == ()


@pytest.mark.parametrize(
    ("kind", "severity", "code"),
    (
        (FindingKind.VIOLATION, Severity.ERROR, AGE_UNSUPPORTED_CODE),
        (
            FindingKind.NOT_VERIFIED,
            Severity.WARNING,
            AGE_REFERENCE_NOT_VERIFIED_CODE,
        ),
    ),
)
def test_generation_saves_a_draft_with_rule_findings(
    monkeypatch, kind, severity, code
):
    harness = Harness()

    monkeypatch.setattr(
        monthly_support,
        "verify_monthly_activity_ages",
        lambda plan, *, catalog: _age_result(
            plan, catalog, kind, severity, code
        ),
    )
    plan = harness.generate().plan

    assert plan.status is PlanStatus.DRAFT
    assert plan.verification_report is not None
    assert plan.verification_report.findings[0].finding_kind is kind
    assert harness.plans.get(plan.plan_id) is plan


def test_generation_verifier_failure_saves_nothing(monkeypatch):
    harness = Harness()

    monkeypatch.setattr(
        monthly_support, "verify_monthly_activity_ages", _fail_age_verification
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate()

    assert exc.value.code == "monthly_verification_failed"
    assert harness.plans.save_count == 0


def test_generation_resolves_an_exact_profile_version():
    harness = Harness()
    command = replace(
        harness.command(),
        profile_ref=TemplateProfileRef(PROFILE.profile_id, "missing"),
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(command=command)

    assert exc.value.code == "monthly_template_profile_not_found"
    assert harness.plans.save_count == 0


def test_generation_command_accepts_profile_ref_not_template_ref():
    harness = Harness()

    with pytest.raises(InvalidDomainValueError, match="profile_ref"):
        replace(harness.command(), profile_ref=TEMPLATE)


def test_generation_rejects_profile_scope_mismatches():
    harness = Harness()

    with pytest.raises(MonthlyApplicationError) as institution_error:
        harness.generate(
            command=replace(harness.command(), daycare_ref="daycare_other")
        )
    assert (
        institution_error.value.code
        == "monthly_template_profile_institution_mismatch"
    )

    with pytest.raises(MonthlyApplicationError) as classroom_error:
        harness.generate(
            command=replace(
                harness.command(), profile_ref=WRONG_CLASS_PROFILE
            )
        )
    assert (
        classroom_error.value.code
        == "monthly_template_profile_classroom_mismatch"
    )
    assert harness.plans.save_count == 0


def test_generation_accepts_an_institution_wide_profile():
    harness = Harness()

    result = harness.generate(
        command=replace(harness.command(), profile_ref=COMMON_PROFILE)
    )

    assert result.plan.template_snapshot.classroom_ref is None
    assert result.plan.classroom_ref == "classroom_001"


def test_generation_requires_an_explicitly_confirmed_yearly_parent():
    harness = Harness(parent_confirmed=False)

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate()

    assert exc.value.code == "parent_yearly_plan_must_be_confirmed"
    assert harness.plans.save_count == 0


def test_generation_mode_is_explicit_and_never_silently_falls_back():
    harness = Harness()

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(MonthlyGenerationMode.LLM_PLANNER)

    assert exc.value.code == "monthly_llm_dependencies_required"
    assert harness.plans.save_count == 0


def test_llm_mode_uses_the_profile_structure_without_requiring_focus():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    command = replace(
        harness.command(MonthlyGenerationMode.LLM_PLANNER),
        profile_ref=RULE_PROFILE,
    )

    result = harness.generate(provider=provider, command=command)

    assert result.plan.section("focus") is None
    assert tuple(section.section_key for section in result.plan.sections) == (
        "theme",
        "week_axis",
        "outdoor_play",
        "safety_education",
    )
    assert len(provider.monthly_requests) == 1
    assert harness.plans.save_count == 1


def test_rule_only_mode_does_not_call_a_configured_llm_planner():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()

    result = harness.generate(provider=provider)

    assert result.plan.generation_mode is MonthlyGenerationMode.RULE_ONLY
    assert provider.monthly_requests == []


def test_llm_mode_reuses_context_and_planner_then_persists_validated_draft():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()

    result = harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=provider)
    plan = result.plan

    assert plan.generation_mode is MonthlyGenerationMode.LLM_PLANNER
    assert result.context_packet_fingerprint
    assert len(provider.monthly_requests) == 1
    assert all(cell.value for cell in plan.section("focus").cells)
    assert all(cell.value for cell in plan.section("outdoor_play").cells)
    assert all(
        cell.generation.method is GenerationMethod.RULE_LLM
        for section_key in ("focus", "outdoor_play")
        for cell in plan.section(section_key).cells
    )
    assert all(
        {source.source_type for source in cell.evidence}
        == {
            EvidenceSourceType.PARENT_PLAN,
            EvidenceSourceType.INSTITUTION_SAMPLE,
        }
        for cell in plan.section("focus").cells
    )
    assert all(
        any(
            source.source_type is EvidenceSourceType.INSTITUTION_SAMPLE
            for source in cell.evidence
        )
        for cell in plan.section("outdoor_play").cells
    )
    assert all(
        cell.cell_state is CellState.EMPTY_UNRESOLVED
        for cell in plan.section("safety_education").cells
    )
    assert harness.plans.save_count == 1


def test_llm_focus_semantics_remain_snapshot_owned():
    harness = Harness()
    result = harness.generate(
        MonthlyGenerationMode.LLM_PLANNER, provider=RequestAwareMonthlyLlm()
    )
    focus = result.plan.section("focus")
    outdoor = result.plan.section("outdoor_play")
    snapshot_focus = result.plan.template_snapshot.section("focus")

    assert snapshot_focus is not None
    assert snapshot_focus.semantic_variant is SemanticVariant.SUBTHEME
    assert focus is not None and outdoor is not None
    assert all(
        cell.label_variant is None and cell.mapping_confidence is None
        for cell in (*focus.cells, *outdoor.cells)
    )


def test_llm_failure_never_saves_an_incomplete_monthly_plan():
    harness = Harness()
    provider = ExplodingMonthlyLlm()

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=provider)

    assert exc.value.code == "monthly_llm_planning_failed"
    assert len(provider.monthly_requests) == 1
    assert harness.plans.save_count == 0


def test_legacy_proposal_shape_is_rejected_without_running_verification(monkeypatch):
    harness = Harness()
    provider = LegacyShapeMonthlyLlm()
    calls = []

    monkeypatch.setattr(
        monthly_support,
        "verify_monthly_activity_ages",
        lambda plan, *, catalog: calls.append(plan),
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=provider)

    assert exc.value.code == "monthly_llm_planning_failed"
    assert len(provider.monthly_requests) == 1
    assert calls == []
    assert harness.plans.save_count == 0


@pytest.mark.parametrize("mode", tuple(MonthlyGenerationMode))
@pytest.mark.parametrize("section_key", ("event_schedule", "drill"))
def test_active_institution_input_section_fails_closed_before_generation(
    section_key, mode
):
    harness = Harness()
    profile = _institution_input_profile(harness.templates, section_key)
    harness.profiles = InMemoryTemplateProfileRepository((profile,))
    provider = RequestAwareMonthlyLlm()
    command = replace(harness.command(mode), profile_ref=profile.profile_ref)

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(provider=provider, command=command)

    assert exc.value.code == "monthly_institution_input_section_unsupported"
    assert section_key in exc.value.detail
    assert provider.monthly_requests == []
    assert harness.plans.save_count == 0


def test_provider_institution_input_section_is_rejected_without_saving():
    harness = Harness()
    provider = InstitutionInputMonthlyLlm()

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=provider)

    assert exc.value.code == "monthly_llm_planning_failed"
    assert isinstance(exc.value.__cause__, ProposalRejectedError)
    assert "UNKNOWN_SECTION" in exc.value.__cause__.validation_codes
    assert len(provider.monthly_requests) == 1
    assert harness.plans.save_count == 0


def test_optional_context_failure_is_reported_without_failing_core_generation():
    harness = Harness()

    class ExplodingOptionalContext:
        def fetch(self, name: str):
            raise RuntimeError(name)

    command = replace(
        harness.command(), optional_context_names=("weather",)
    )
    result = harness.generate(
        optional_context=ExplodingOptionalContext(), command=command
    )

    assert result.optional_context[0].status is OptionalContextStatus.ERROR
    assert result.plan.status is PlanStatus.DRAFT


def test_teacher_edit_is_immutable_and_preserves_existing_evidence():
    harness = Harness()
    original = harness.generate().plan
    target = _cell(original, "outdoor_play")
    other = _cell(original, "focus")
    saves_before = harness.plans.save_count

    updated = EditMonthlyPlanItem(
        plan_repository=harness.plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    ).execute(
        EditMonthlyPlanItemCommand(
            original.plan_id, target.item_id, "Teacher-authored outdoor play", TEACHER
        )
    )
    edited = updated.find_cell(target.item_id)[3]

    assert original.find_cell(target.item_id)[3].value == target.value
    assert edited.value == "Teacher-authored outdoor play"
    assert edited.evidence == target.evidence
    assert edited.generation.method is GenerationMethod.TEACHER_EDIT
    event = edited.audit.events[-1]
    assert event.event_type is AuditEventType.TEACHER_EDITED
    assert event.value_change.before == target.value
    assert event.value_change.after == "Teacher-authored outdoor play"
    assert updated.find_cell(other.item_id)[3] is other
    assert harness.plans.save_count == saves_before + 1


def test_teacher_can_fill_an_empty_cell_and_audit_records_blank_before_value():
    harness = Harness()
    original = harness.generate().plan
    target = _cell(original, "focus")

    updated = EditMonthlyPlanItem(
        plan_repository=harness.plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    ).execute(
        EditMonthlyPlanItemCommand(
            original.plan_id, target.item_id, "Teacher-authored focus", TEACHER
        )
    )
    event = updated.find_cell(target.item_id)[3].audit.events[-1]

    assert event.value_change.before == ""
    assert event.value_change.after == "Teacher-authored focus"


def test_teacher_edit_replaces_the_report_with_stale_reference_warning():
    harness = Harness()
    original = harness.generate().plan
    target = _cell(original, "outdoor_play")

    updated = EditMonthlyPlanItem(
        plan_repository=harness.plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    ).execute(
        EditMonthlyPlanItemCommand(
            original.plan_id, target.item_id, "Teacher-authored outdoor play", TEACHER
        )
    )
    report = updated.verification_report

    assert report is not None
    assert report is not original.verification_report
    assert report.executed_rules == (AGE_RULE_REF,)
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.code == AGE_REFERENCE_NOT_VERIFIED_CODE
    assert finding.finding_kind is FindingKind.NOT_VERIFIED
    assert finding.severity is Severity.WARNING
    assert finding.location == ViolationLocation(target.section_key, target.week_id)
    assert harness.plans.get(updated.plan_id) is updated


def test_teacher_edit_verifier_failure_preserves_the_saved_plan(monkeypatch):
    harness = Harness()
    original = harness.generate().plan
    target = _cell(original, "outdoor_play")
    saves_before = harness.plans.save_count

    monkeypatch.setattr(
        monthly_support, "verify_monthly_activity_ages", _fail_age_verification
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        EditMonthlyPlanItem(
            plan_repository=harness.plans,
            clock=harness.clock,
            activity_repository=harness.activities,
        ).execute(
            EditMonthlyPlanItemCommand(
                original.plan_id, target.item_id, "Unsaved edit", TEACHER
            )
        )

    assert exc.value.code == "monthly_verification_failed"
    assert harness.plans.save_count == saves_before
    assert harness.plans.get(original.plan_id) is original


def test_rule_only_regeneration_replaces_only_one_outdoor_cell():
    harness = Harness()
    original = harness.generate().plan
    target = _cell(original, "outdoor_play")
    sibling = _cell(original, "outdoor_play", 1)

    result = harness.regenerate().execute(
        RegenerateMonthlyPlanItemCommand(
            original.plan_id, target.item_id, TEACHER
        )
    )
    regenerated = result.plan.find_cell(target.item_id)[3]

    assert regenerated.item_id == target.item_id
    assert regenerated.audit.events[-1].event_type is AuditEventType.REGENERATED
    assert result.activity_selection is not None
    assert result.plan.find_cell(sibling.item_id)[3] is sibling
    assert result.plan.verification_report is not original.verification_report
    assert result.plan.verification_report is not None
    assert result.plan.verification_report.executed_rules == (AGE_RULE_REF,)


def test_regeneration_verifier_failure_preserves_the_saved_plan(monkeypatch):
    harness = Harness()
    original = harness.generate().plan
    target = _cell(original, "outdoor_play")
    saves_before = harness.plans.save_count

    monkeypatch.setattr(
        monthly_support, "verify_monthly_activity_ages", _fail_age_verification
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.regenerate().execute(
            RegenerateMonthlyPlanItemCommand(
                original.plan_id, target.item_id, TEACHER
            )
        )

    assert exc.value.code == "monthly_verification_failed"
    assert harness.plans.save_count == saves_before
    assert harness.plans.get(original.plan_id) is original


def test_llm_cell_regeneration_records_before_and_after_method_details():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    original = harness.generate(
        MonthlyGenerationMode.LLM_PLANNER, provider=provider
    ).plan
    target = _cell(original, "focus")
    sibling = _cell(original, "focus", 1)

    result = harness.regenerate(provider).execute(
        RegenerateMonthlyPlanItemCommand(
            original.plan_id, target.item_id, TEACHER
        )
    )
    regenerated = result.plan.find_cell(target.item_id)[3]
    change = regenerated.audit.events[-1].generation_change

    assert regenerated.value == "Regenerated focus value"
    assert change.before.rule_version != change.after.rule_version
    assert change.after.rule_version == MONTHLY_CELL_PROMPT_VERSION
    assert result.plan.find_cell(sibling.item_id)[3] is sibling
    assert len(provider.cell_requests) == 1


def test_llm_cell_regeneration_preserves_reference_and_grounding_provenance():
    harness = Harness()
    original = harness.generate(
        MonthlyGenerationMode.LLM_PLANNER, provider=RequestAwareMonthlyLlm()
    ).plan
    target = _cell(original, "outdoor_play")
    provider = ReferenceAndGroundingCellLlm()

    result = harness.regenerate(provider).execute(
        RegenerateMonthlyPlanItemCommand(original.plan_id, target.item_id, TEACHER)
    )
    outcome = result.planner_outcome
    regenerated = result.plan.find_cell(target.item_id)[3]

    assert outcome is not None
    assert outcome.proposal.section.reference_id is not None
    assert outcome.proposal.section.grounding_refs
    assert {source.source_type for source in regenerated.evidence} == {
        EvidenceSourceType.PARENT_PLAN,
        EvidenceSourceType.ACTIVITY_REFERENCE,
        EvidenceSourceType.INSTITUTION_SAMPLE,
    }
    assert {(source.source_type, source.source_id) for source in regenerated.evidence} >= {
        (
            EvidenceSourceType.ACTIVITY_REFERENCE,
            outcome.proposal.section.reference_id,
        ),
        (
            EvidenceSourceType.INSTITUTION_SAMPLE,
            outcome.proposal.section.grounding_refs[0],
        ),
    }
    assert result.plan.parent_lineage is original.parent_lineage
    assert regenerated.generation.method is GenerationMethod.RULE_LLM


def test_llm_cell_failure_does_not_persist_a_partial_regeneration():
    harness = Harness()
    generation_provider = RequestAwareMonthlyLlm()
    original = harness.generate(
        MonthlyGenerationMode.LLM_PLANNER, provider=generation_provider
    ).plan
    target = _cell(original, "focus")
    provider = ExplodingCellLlm()
    saves_before = harness.plans.save_count

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.regenerate(provider).execute(
            RegenerateMonthlyPlanItemCommand(
                original.plan_id, target.item_id, TEACHER
            )
        )

    assert exc.value.code == "monthly_llm_cell_planning_failed"
    assert harness.plans.save_count == saves_before
    assert harness.plans.get(original.plan_id) is original
    assert len(provider.cell_requests) == 1


def test_safety_cell_is_not_an_llm_regeneration_target():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    plan = harness.generate(
        MonthlyGenerationMode.LLM_PLANNER, provider=provider
    ).plan
    target = _cell(plan, "safety_education")
    saves_before = harness.plans.save_count

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.regenerate(provider).execute(
            RegenerateMonthlyPlanItemCommand(plan.plan_id, target.item_id, TEACHER)
        )

    assert exc.value.code == "monthly_cell_not_regeneratable"
    assert harness.plans.save_count == saves_before
    assert provider.cell_requests == []


def test_confirm_requires_teacher_and_locks_all_later_mutations():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    draft = harness.generate(
        MonthlyGenerationMode.LLM_PLANNER, provider=provider
    ).plan
    target = _cell(draft, "focus")
    confirm = ConfirmMonthlyPlan(
        plan_repository=harness.plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    )

    confirmed = confirm.execute(ConfirmMonthlyPlanCommand(draft.plan_id, TEACHER))
    saves_before = harness.plans.save_count

    assert confirmed.status is PlanStatus.CONFIRMED
    assert confirmed.audit.events[-1].actor_id == TEACHER
    assert confirmed.verification_report is not draft.verification_report
    with pytest.raises(InvalidStateTransitionError):
        EditMonthlyPlanItem(
            plan_repository=harness.plans,
            clock=harness.clock,
            activity_repository=harness.activities,
        ).execute(
            EditMonthlyPlanItemCommand(
                confirmed.plan_id, target.item_id, "No longer editable", TEACHER
            )
        )
    with pytest.raises(InvalidStateTransitionError):
        harness.regenerate(provider).execute(
            RegenerateMonthlyPlanItemCommand(
                confirmed.plan_id, target.item_id, TEACHER
            )
        )
    assert confirm.execute(ConfirmMonthlyPlanCommand(confirmed.plan_id, TEACHER)) is confirmed
    assert harness.plans.save_count == saves_before


class _CountingActivities:
    """Delegates to the JSON Activity repository and counts Catalog loads."""

    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.loads = 0

    def get_catalog(self, catalog_id, catalog_version):
        self.loads += 1
        return self._delegate.get_catalog(catalog_id, catalog_version)


def _confirm_with_counters(harness, monkeypatch):
    activities = _CountingActivities(harness.activities)
    verifier_calls = []
    real_verifier = monthly_support.verify_monthly_activity_ages

    def counting_verifier(plan, *, catalog):
        verifier_calls.append(plan.plan_id)
        return real_verifier(plan, catalog=catalog)

    monkeypatch.setattr(monthly_support, "verify_monthly_activity_ages", counting_verifier)
    confirm = ConfirmMonthlyPlan(
        plan_repository=harness.plans, clock=harness.clock, activity_repository=activities
    )
    return confirm, activities, verifier_calls


def _confirmed_events(plan):
    return [event for event in plan.audit.events if event.event_type is AuditEventType.CONFIRMED]


def test_first_confirm_freshly_verifies_saves_once_and_records_one_confirmation(monkeypatch):
    harness = Harness()
    draft = harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=RequestAwareMonthlyLlm()).plan
    confirm, activities, verifier_calls = _confirm_with_counters(harness, monkeypatch)
    saves_before = harness.plans.save_count

    confirmed = confirm.execute(ConfirmMonthlyPlanCommand(draft.plan_id, TEACHER))

    assert confirmed.status is PlanStatus.CONFIRMED
    assert verifier_calls == [draft.plan_id]
    assert activities.loads == 1
    assert harness.plans.save_count == saves_before + 1
    assert harness.plans.get(draft.plan_id) is confirmed
    assert confirmed.verification_report is not draft.verification_report
    assert [event.actor_id for event in _confirmed_events(confirmed)] == [TEACHER]


@pytest.mark.parametrize("retry_actor", [TEACHER, ActorId("teacher_002")], ids=["same-actor", "other-actor"])
def test_confirm_retry_returns_the_stored_plan_without_any_mutation(monkeypatch, retry_actor):
    harness = Harness()
    draft = harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=RequestAwareMonthlyLlm()).plan
    confirm, activities, verifier_calls = _confirm_with_counters(harness, monkeypatch)
    confirmed = confirm.execute(ConfirmMonthlyPlanCommand(draft.plan_id, TEACHER))
    first_event = _confirmed_events(confirmed)[0]
    saves_before, loads_before, calls_before = harness.plans.save_count, activities.loads, len(verifier_calls)
    later = ConfirmMonthlyPlan(
        plan_repository=harness.plans,
        clock=FixedClock(datetime(2026, 9, 21, 9, 0, tzinfo=UTC)),
        activity_repository=activities,
    )

    retried = later.execute(ConfirmMonthlyPlanCommand(draft.plan_id, retry_actor))

    assert retried is confirmed
    assert harness.plans.get(draft.plan_id) is confirmed
    assert len(verifier_calls) == calls_before
    assert activities.loads == loads_before
    assert harness.plans.save_count == saves_before
    assert retried.audit == confirmed.audit
    assert _confirmed_events(retried) == [first_event]
    assert first_event.actor_id == TEACHER and first_event.occurred_at == NOW
    assert retried.verification_report is confirmed.verification_report


@pytest.mark.parametrize("confirmed_first", [False, True], ids=["draft", "confirmed"])
def test_confirm_still_requires_an_opaque_actor(confirmed_first):
    harness = Harness()
    plan = harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=RequestAwareMonthlyLlm()).plan
    confirm = ConfirmMonthlyPlan(
        plan_repository=harness.plans, clock=harness.clock, activity_repository=harness.activities
    )
    if confirmed_first:
        plan = confirm.execute(ConfirmMonthlyPlanCommand(plan.plan_id, TEACHER))
    saves_before = harness.plans.save_count

    with pytest.raises(MonthlyApplicationError) as exc:
        confirm.execute(ConfirmMonthlyPlanCommand(plan.plan_id, "담임 선생님"))

    assert exc.value.code == "opaque_actor_required"
    assert harness.plans.save_count == saves_before
    assert harness.plans.get(plan.plan_id) is plan


def test_domain_confirm_still_rejects_a_second_transition():
    harness = Harness()
    plan = harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=RequestAwareMonthlyLlm()).plan
    confirmed = plan.confirm(actor_id=TEACHER, occurred_at=NOW)

    with pytest.raises(InvalidStateTransitionError):
        confirmed.confirm(actor_id=TEACHER, occurred_at=NOW)


def test_confirm_allows_a_fresh_not_verified_warning():
    harness = Harness()
    draft = harness.generate().plan
    target = _cell(draft, "outdoor_play")
    edited = EditMonthlyPlanItem(
        plan_repository=harness.plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    ).execute(
        EditMonthlyPlanItemCommand(
            draft.plan_id, target.item_id, "Teacher-authored outdoor play", TEACHER
        )
    )

    confirmed = ConfirmMonthlyPlan(
        plan_repository=harness.plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    ).execute(ConfirmMonthlyPlanCommand(edited.plan_id, TEACHER))

    assert confirmed.status is PlanStatus.CONFIRMED
    assert confirmed.verification_report is not edited.verification_report
    assert confirmed.verification_report is not None
    finding = confirmed.verification_report.findings[0]
    assert finding.finding_kind is FindingKind.NOT_VERIFIED
    assert finding.severity is Severity.WARNING


def test_confirm_allows_a_fresh_supported_age_error_and_stores_the_report():
    harness = Harness()
    draft = _with_age_mismatch(harness, harness.generate().plan)
    assert draft.verification_report is None
    harness.plans.save(draft.plan_id, draft)
    saves_before = harness.plans.save_count

    confirmed = ConfirmMonthlyPlan(
        plan_repository=harness.plans,
        clock=harness.clock,
        activity_repository=harness.activities,
    ).execute(ConfirmMonthlyPlanCommand(draft.plan_id, TEACHER))

    persisted = harness.plans.get(draft.plan_id)
    assert confirmed.status is PlanStatus.CONFIRMED
    assert persisted is confirmed
    assert confirmed.verification_report is not None
    finding = confirmed.verification_report.findings[0]
    assert finding.code == AGE_UNSUPPORTED_CODE
    assert finding.finding_kind is FindingKind.VIOLATION
    assert finding.severity is Severity.ERROR
    assert harness.plans.save_count == saves_before + 1


def test_confirm_verifier_failure_preserves_the_saved_draft(monkeypatch):
    harness = Harness()
    draft = harness.generate().plan
    saves_before = harness.plans.save_count

    monkeypatch.setattr(
        monthly_support, "verify_monthly_activity_ages", _fail_age_verification
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        ConfirmMonthlyPlan(
            plan_repository=harness.plans,
            clock=harness.clock,
            activity_repository=harness.activities,
        ).execute(ConfirmMonthlyPlanCommand(draft.plan_id, TEACHER))

    assert exc.value.code == "monthly_verification_failed"
    assert harness.plans.save_count == saves_before
    assert harness.plans.get(draft.plan_id) is draft


# ---------------------------------------------------------------- V1-6 PR-B section-scoped evidence

EXTENDED_PROFILE = TemplateProfileRef("monthly-profile-extended", "v1")


def _extended_profile(
    template_repository: JsonMonthlyTemplateRepository,
    *,
    goals_required: bool | None = None,
    basic_habit: bool = False,
    focus_variant: SemanticVariant = SemanticVariant.SUBTHEME,
) -> TemplateProfile:
    base = _profile(template_repository, TEMPLATE, EXTENDED_PROFILE)
    template = template_repository.get_template(TEMPLATE.template_id, TEMPLATE.template_version)
    assert template is not None
    sections = [
        replace(section, semantic_variant=focus_variant) if section.section_key == "focus" else section
        for section in base.sections
    ]
    optional = list(base.selected_optional_keys)
    if goals_required is not None:
        sections.append(
            replace(
                template.section("goals"),
                activated=True,
                display_label="Goals",
                visible=True,
                required_for_generation=goals_required,
            )
        )
        optional.append("goals")
    if basic_habit:
        sections.append(
            replace(template.section("habits"), activated=True, display_label="Basic habit", visible=True)
        )
        optional.append("basic_habit")
    return replace(base, selected_optional_keys=tuple(optional), sections=tuple(sections))


def _classification_without(*excluded: SemanticClass) -> InMemoryEvidenceClassificationRepository:
    approved = CLASSIFICATION_REPOSITORY.get_classification()
    return InMemoryEvidenceClassificationRepository(
        replace(
            approved,
            entries=tuple(entry for entry in approved.entries if entry[2] not in excluded),
        )
    )


def _use(harness: Harness, profile: TemplateProfile, classification=None) -> GenerateMonthlyPlanCommand:
    harness.profiles = InMemoryTemplateProfileRepository((profile,))
    if classification is not None:
        harness.context = MonthlyContextPipeline(
            evidence_repository=EVIDENCE_REPOSITORY,
            classification_repository=classification,
            context_builder=ContextPacketBuilder(),
        )
    return replace(harness.command(MonthlyGenerationMode.LLM_PLANNER), profile_ref=profile.profile_ref)


def _cited_classes(cell) -> set[SemanticClass]:
    records = {record.record_id: record for record in EVIDENCE_REPOSITORY.get_store().records}
    classification = CLASSIFICATION_REPOSITORY.get_classification()
    return {
        classification.class_of(records[source.source_id])
        for source in cell.evidence
        if source.source_type is EvidenceSourceType.INSTITUTION_SAMPLE
    }


def test_weekly_theme_focus_fails_closed_before_llm():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    command = _use(harness, _extended_profile(harness.templates, focus_variant=SemanticVariant.WEEKLY_THEME))

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(provider=provider, command=command)

    assert exc.value.code == "monthly_section_evidence_class_unavailable"
    assert "focus" in exc.value.detail
    assert provider.monthly_requests == []
    assert harness.plans.save_count == 0


def test_required_section_without_approved_evidence_fails_closed_before_llm():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    command = _use(
        harness,
        _extended_profile(harness.templates, goals_required=True),
        _classification_without(SemanticClass.GOALS),
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(provider=provider, command=command)

    assert exc.value.code == "monthly_required_section_evidence_missing"
    assert "goals" in exc.value.detail
    assert provider.monthly_requests == []
    assert harness.plans.save_count == 0


def test_optional_section_without_approved_evidence_stays_empty_valid():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    command = _use(
        harness,
        _extended_profile(harness.templates, goals_required=False),
        _classification_without(SemanticClass.GOALS),
    )

    plan = harness.generate(provider=provider, command=command).plan
    goals = plan.section("goals")

    assert len(provider.monthly_requests) == 1
    assert goals is not None and len(goals.cells) == 1
    assert goals.cells[0].value == ""
    assert goals.cells[0].cell_state is CellState.EMPTY_VALID
    assert harness.plans.save_count == 1


def test_goals_basic_habit_and_focus_ground_only_on_their_approved_classes():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    command = _use(harness, _extended_profile(harness.templates, goals_required=True, basic_habit=True))

    plan = harness.generate(provider=provider, command=command).plan

    assert _cited_classes(plan.section("goals").cells[0]) == {SemanticClass.GOALS}
    for cell in plan.section("basic_habit").cells:
        assert cell.cell_state is CellState.FILLED
        assert _cited_classes(cell) == {SemanticClass.BASIC_HABIT}
    for cell in plan.section("focus").cells:
        assert _cited_classes(cell) == {SemanticClass.SUBTHEME}
    for cell in plan.section("outdoor_play").cells:
        assert _cited_classes(cell) <= {SemanticClass.EXCLUDED}


@pytest.mark.parametrize(("target_month", "weeks"), [(YearMonth(2026, 10), 4), (YearMonth(2026, 9), 5)])
def test_basic_habit_uses_the_monthly_pool_for_every_computed_week(target_month, weeks):
    harness = Harness()
    command = replace(
        _use(harness, _extended_profile(harness.templates, basic_habit=True)),
        target_month=target_month,
    )

    plan = harness.generate(provider=RequestAwareMonthlyLlm(), command=command).plan
    cells = plan.section("basic_habit").cells
    records = {record.record_id: record for record in EVIDENCE_REPOSITORY.get_store().records}

    assert len(cells) == weeks == len(plan.active_week_periods)
    assert [cell.week_id for cell in cells] == [period.week_id for period in plan.active_week_periods]
    for cell in cells:
        assert _cited_classes(cell) == {SemanticClass.BASIC_HABIT}
        cited = [s.source_id for s in cell.evidence if s.source_type is EvidenceSourceType.INSTITUTION_SAMPLE]
        assert all(records[ref].week_position is None for ref in cited)


def test_expected_play_focus_grounds_only_on_expected_play_evidence():
    harness = Harness()
    command = _use(harness, _extended_profile(harness.templates, focus_variant=SemanticVariant.EXPECTED_PLAY))

    plan = harness.generate(provider=RequestAwareMonthlyLlm(), command=command).plan

    assert plan.section("focus").cells
    for cell in plan.section("focus").cells:
        assert _cited_classes(cell) == {SemanticClass.EXPECTED_PLAY}


def test_classification_bound_to_other_corpus_fails_closed():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    approved = CLASSIFICATION_REPOSITORY.get_classification()
    command = _use(
        harness,
        _profile(harness.templates, TEMPLATE, EXTENDED_PROFILE),
        InMemoryEvidenceClassificationRepository(replace(approved, evidence_content_sha256="0" * 64)),
    )

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(provider=provider, command=command)

    assert exc.value.code == "evidence_classification_store_mismatch"
    assert provider.monthly_requests == []
    assert harness.plans.save_count == 0


class WrongSourceMonthlyLlm(RequestAwareMonthlyLlm):
    """Grounds outdoor_play on SUBTHEME evidence, which only focus(SUBTHEME) may cite."""

    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        payload = json.loads(super().generate_monthly(request).content)
        subtheme_ref = grounding_ref_for(request, "focus")
        for week in payload["weeks"]:
            for section in week["sections"]:
                if section["section_key"] == "outdoor_play":
                    section.update(reference_id=None, grounding_refs=[subtheme_ref])
        return RawLlmResponse(json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "monthly-1")


def test_wrong_source_provider_response_is_rejected_without_saving():
    harness = Harness()
    provider = WrongSourceMonthlyLlm()

    with pytest.raises(MonthlyApplicationError) as exc:
        harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=provider)

    assert exc.value.code == "monthly_llm_planning_failed"
    assert "WRONG_SOURCE_GROUNDING" in exc.value.__cause__.validation_codes
    assert harness.plans.save_count == 0


def test_focus_regeneration_uses_only_subtheme_evidence():
    harness = Harness()
    provider = RequestAwareMonthlyLlm()
    plan = harness.generate(MonthlyGenerationMode.LLM_PLANNER, provider=provider).plan
    target = _cell(plan, "focus")

    result = harness.regenerate(provider).execute(
        RegenerateMonthlyPlanItemCommand(plan.plan_id, target.item_id, TEACHER)
    )
    regenerated = result.plan.find_cell(target.item_id)[3]
    body = json.loads(provider.cell_requests[-1].user_content)

    assert {item["grounding_class"] for item in body["evidence"]} <= {None, "SUBTHEME"}
    assert _cited_classes(regenerated) == {SemanticClass.SUBTHEME}
