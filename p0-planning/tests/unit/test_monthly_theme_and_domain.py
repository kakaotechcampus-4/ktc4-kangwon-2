from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.monthly_plan import MonthlyPlan, MonthlySection
from ssuksak.planning.domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    SectionCategory,
    SectionRole,
    TemplateRef,
    TemplateSection,
)
from ssuksak.planning.domain.monthly_template_profile import (
    TemplateProfile,
    TemplateProfileRef,
)
from ssuksak.planning.domain.monthly_template_snapshot import TemplateSnapshot
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
from ssuksak.planning.domain.yearly_plan import YearlyPeriod, YearlyPlan
from ssuksak.planning.rules.academic_periods import academic_year_periods
from ssuksak.planning.rules.errors import MonthlyRuleError
from ssuksak.planning.rules.monthly_theme_derivation import derive_monthly_theme
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods

NOW = datetime(2026, 9, 19, 1, tzinfo=UTC)


def _template_snapshot() -> TemplateSnapshot:
    section_specs = (
        ("theme", SectionRole.CONTENT, DisplayMode.MONTHLY_MERGED_SUMMARY),
        ("week_axis", SectionRole.AXIS, None),
        ("outdoor_play", SectionRole.CONTENT, DisplayMode.WEEKLY_CELLS),
        ("safety_education", SectionRole.CONTENT, DisplayMode.WEEKLY_CELLS),
    )
    sections = tuple(
        TemplateSection(
            section_key=key,
            role=role,
            activated=True,
            display_mode=display_mode,
            empty_value_policy=(
                None
                if role is SectionRole.AXIS
                else EmptyValuePolicy.RENDER_EMPTY_CELL
            ),
            display_label=key.replace("_", " ").title(),
            order=order,
            category=SectionCategory.DEFAULT,
            required_for_generation=True,
            visible=True,
        )
        for order, (key, role, display_mode) in enumerate(section_specs)
    )
    return TemplateSnapshot.from_profile(
        TemplateProfile(
            profile_ref=TemplateProfileRef("profile-1", "v1"),
            institution_ref="daycare-1",
            classroom_ref="class-1",
            base_template_ref=TemplateRef("template", "v1"),
            selected_optional_keys=(),
            sections=sections,
        )
    )


def _monthly_sections(snapshot: TemplateSnapshot) -> tuple[MonthlySection, ...]:
    return tuple(
        MonthlySection(
            section_key=section.section_key,
            role=section.role,
            display_mode=section.display_mode,
            empty_value_policy=(
                section.empty_value_policy
                or EmptyValuePolicy.RENDER_EMPTY_CELL
            ),
            parent_section_key=section.parent_section_key,
            source_label=section.source_label,
        )
        for section in snapshot.sections
    )


def _yearly(*, confirmed: bool = True) -> YearlyPlan:
    plan_id = PlanId("yearly-1")
    periods = []
    for index, period in enumerate(academic_year_periods(2026), start=1):
        item_id = ItemId(f"theme-{index}")
        event = AuditEvent(AuditEventType.CREATED, NOW, plan_id, item_id=item_id, system_actor="yearly")
        periods.append(
            YearlyPeriod(
                period,
                PlanItem(
                    item_id,
                    f"theme {period.value}",
                    (EvidenceSource(EvidenceSourceType.THEME_REFERENCE, f"theme-ref-{index}", "theme-v1"),),
                    GenerationMethodDetail(GenerationMethod.RULE_ONLY, "yearly.rule", "v1"),
                    AuditHistory((event,)),
                ),
            )
        )
    plan = YearlyPlan(
        plan_id,
        2026,
        "class-1",
        frozenset({3, 4}),
        PlanStatus.DRAFT,
        tuple(periods),
        AuditHistory((AuditEvent(AuditEventType.CREATED, NOW, plan_id, system_actor="yearly"),)),
    )
    return plan.confirm(actor_id=ActorId("teacher-1"), occurred_at=NOW) if confirmed else plan


def test_theme_derivation_requires_confirmed_yearly_plan():
    with pytest.raises(MonthlyRuleError, match="CONFIRMED"):
        derive_monthly_theme(_yearly(confirmed=False), YearMonth(2026, 9))


def test_theme_derivation_uses_parent_snapshot_and_separate_evidence():
    result = derive_monthly_theme(_yearly(), YearMonth(2026, 9))

    assert result.value == "theme 2026-09"
    assert result.parent_lineage.parent_plan_id == PlanId("yearly-1")
    assert result.parent_lineage.snapshot_value == result.value
    assert tuple(source.source_type for source in result.evidence) == (
        EvidenceSourceType.PARENT_PLAN,
        EvidenceSourceType.THEME_REFERENCE,
    )
    assert result.generation.method is GenerationMethod.RULE_ONLY


def test_theme_derivation_rejects_month_outside_parent():
    with pytest.raises(MonthlyRuleError, match="absent"):
        derive_monthly_theme(_yearly(), YearMonth(2028, 1))


def test_minimal_monthly_structure_uses_current_parent_lineage():
    derivation = derive_monthly_theme(_yearly(), YearMonth(2026, 9))
    snapshot = _template_snapshot()
    plan = MonthlyPlan(
        plan_id=PlanId("monthly-1"),
        school_year=2026,
        target_month=YearMonth(2026, 9),
        daycare_ref="daycare-1",
        classroom_ref="class-1",
        target_ages=frozenset({3, 4}),
        status=PlanStatus.DRAFT,
        parent_lineage=derivation.parent_lineage,
        template_snapshot=snapshot,
        week_periods=canonical_week_periods(YearMonth(2026, 9)),
        sections=_monthly_sections(snapshot),
    )

    assert plan.parent_lineage.parent_item_id is not None
    assert len(plan.active_week_periods) == 5
    assert plan.template_snapshot is snapshot
    assert plan.template_ref is snapshot.base_template_ref
    with pytest.raises(Exception, match="template_snapshot"):
        replace(plan, template_snapshot=None)
    with pytest.raises(FrozenInstanceError):
        plan.status = PlanStatus.CONFIRMED


def test_monthly_month_must_belong_to_school_year():
    derivation = derive_monthly_theme(_yearly(), YearMonth(2026, 9))
    snapshot = _template_snapshot()
    with pytest.raises(Exception, match="school year"):
        MonthlyPlan(
            PlanId("monthly-1"),
            2026,
            YearMonth(2028, 1),
            "daycare-1",
            "class-1",
            frozenset({3}),
            PlanStatus.DRAFT,
            derivation.parent_lineage,
            snapshot,
            canonical_week_periods(YearMonth(2028, 1)),
            _monthly_sections(snapshot),
        )
