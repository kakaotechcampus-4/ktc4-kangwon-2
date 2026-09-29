"""Full Monthly v1 final acceptance gaps not covered by the core E2E flow."""

from __future__ import annotations

import pytest

from ssuksak.adapters.evidence_classification_repository import (
    JsonEvidenceClassificationRepository,
)
from ssuksak.adapters.institution_evidence_repository import (
    JsonInstitutionEvidenceRepository,
)
from ssuksak.planning.domain.monthly_constraint import CellState
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.monthly_template import DisplayMode, SectionRole
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.classification import SemanticClass
from ssuksak.planning.planner.contracts import (
    MONTHLY_CELL_PROMPT_VERSION,
    MONTHLY_PROMPT_VERSION,
)
from ssuksak.planning.rules.monthly_theme_derivation import (
    RULE_ID as THEME_RULE_ID,
)
from ssuksak.planning.rules.monthly_verification import AGE_RULE_REF
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods

from .harness import EXTENDED_PROFILE, TARGET_MONTH, TEACHER, PlanningHarness

_RECORDS = {
    record.record_id: record
    for record in JsonInstitutionEvidenceRepository().get_store().records
}
_CLASSIFICATION = JsonEvidenceClassificationRepository().get_classification()


def _source_types(cell) -> set[EvidenceSourceType]:
    return {source.source_type for source in cell.evidence}


def _cited_records(cell):
    return [
        _RECORDS[source.source_id]
        for source in cell.evidence
        if source.source_type is EvidenceSourceType.INSTITUTION_SAMPLE
    ]


def _cited_classes(cell) -> set[SemanticClass]:
    return {_CLASSIFICATION.class_of(record) for record in _cited_records(cell)}


def test_teacher_confirmed_yearly_value_becomes_the_monthly_theme():
    harness = PlanningHarness()
    generated = harness.generate_yearly().plan
    index = next(
        position
        for position, period in enumerate(generated.periods)
        if period.period == TARGET_MONTH
    )
    ai_value = generated.periods[index].theme.value
    teacher_value = "Teacher-confirmed September theme"
    parent = harness.confirm_yearly(
        harness.edit_yearly(generated, index=index, value=teacher_value)
    )

    plan = harness.generate_monthly(parent, MonthlyGenerationMode.LLM_PLANNER).plan
    theme = plan.section("theme").cells[0]
    parent_evidence = next(
        source
        for source in theme.evidence
        if source.source_type is EvidenceSourceType.PARENT_PLAN
    )

    assert ai_value != teacher_value
    assert parent.periods[index].theme.value == teacher_value
    assert harness.provider.monthly_requests[-1].expected_theme_value == teacher_value
    assert theme.value == teacher_value
    assert parent_evidence.display_name == teacher_value
    assert plan.parent_lineage.parent_item_id == parent.periods[index].theme.item_id
    assert plan.parent_lineage.snapshot_value == teacher_value
    assert plan.parent_lineage.confirmed_by == TEACHER
    assert plan.status is PlanStatus.DRAFT
    assert [event.event_type for event in plan.audit.events] == [AuditEventType.CREATED]
    assert harness.monthly_plans.get(plan.plan_id) is plan


@pytest.mark.parametrize(
    ("ages", "month"),
    [
        (frozenset({3}), YearMonth(2026, 10)),
        (frozenset({4}), YearMonth(2026, 9)),
        (frozenset({5}), YearMonth(2026, 10)),
        (frozenset({3, 4}), YearMonth(2026, 9)),
    ],
    ids=["age3-4week", "age4-5week", "age5-4week", "mixed-age34-5week"],
)
def test_extended_profile_final_acceptance(ages, month):
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly(ages).plan)
    plan = harness.generate_monthly(
        parent,
        MonthlyGenerationMode.LLM_PLANNER,
        target_month=month,
        profile=EXTENDED_PROFILE,
    ).plan
    snapshot = plan.template_snapshot
    profile = harness.profiles.get_profile(
        EXTENDED_PROFILE.profile_id, EXTENDED_PROFILE.profile_version
    )
    week_ids = tuple(period.week_id for period in canonical_week_periods(month))

    def contract(section):
        return (
            section.section_key,
            section.order,
            section.display_label,
            section.display_mode,
            section.semantic_variant,
            section.required_for_generation,
            section.visible,
        )

    # Snapshot is the exact Profile contract; a hidden week_axis still drives the weeks.
    assert snapshot.profile_ref == EXTENDED_PROFILE
    assert [contract(section) for section in snapshot.sections] == [
        contract(section) for section in profile.ordered_sections
    ]
    assert [section.section_key for section in plan.sections] == [
        section.section_key for section in snapshot.sections
    ]
    week_axis = snapshot.section("week_axis")
    assert week_axis.role is SectionRole.AXIS
    assert week_axis.visible is False and week_axis.required_for_generation
    assert len(week_ids) == (4 if month == YearMonth(2026, 10) else 5)
    assert tuple(period.week_id for period in plan.active_week_periods) == week_ids
    assert harness.provider.monthly_requests[-1].expected_week_ids == week_ids
    assert plan.target_ages == ages

    # Placement: weekly Sections have one cell per active week, merged ones a single week-less cell.
    placements = {section.section_key: section.display_mode for section in plan.sections}
    assert {key for key, mode in placements.items() if mode is DisplayMode.WEEKLY_CELLS} == {
        "outdoor_play", "safety_education", "focus", "basic_habit"
    }
    assert {
        key for key, mode in placements.items() if mode is DisplayMode.MONTHLY_MERGED_SUMMARY
    } == {"theme", "goals"}
    for section in plan.sections:
        expected = {
            DisplayMode.WEEKLY_CELLS: week_ids,
            DisplayMode.MONTHLY_MERGED_SUMMARY: (None,),
            None: (),
        }[section.display_mode]
        assert tuple(cell.week_id for cell in section.cells) == expected

    # Provenance: Evidence, Generation Method and Audit stay separate; LLM use is a Method.
    theme = plan.section("theme").cells[0]
    assert _source_types(theme) == {
        EvidenceSourceType.PARENT_PLAN, EvidenceSourceType.THEME_REFERENCE
    }
    assert (theme.generation.method, theme.generation.rule_id) == (
        GenerationMethod.RULE_ONLY, THEME_RULE_ID
    )
    assert plan.parent_lineage.snapshot_value == theme.value
    for key, semantic_class in (
        ("goals", SemanticClass.GOALS),
        ("basic_habit", SemanticClass.BASIC_HABIT),
        ("focus", SemanticClass.SUBTHEME),
    ):
        for cell in plan.section(key).cells:
            assert _source_types(cell) == {
                EvidenceSourceType.PARENT_PLAN, EvidenceSourceType.INSTITUTION_SAMPLE
            }
            assert _cited_classes(cell) == {semantic_class}
            assert (cell.generation.method, cell.generation.rule_version) == (
                GenerationMethod.RULE_LLM, MONTHLY_PROMPT_VERSION
            )
    assert all(
        record.week_position is None
        for cell in plan.section("basic_habit").cells
        for record in _cited_records(cell)
    )
    for cell in plan.section("outdoor_play").cells:
        assert _source_types(cell) <= {
            EvidenceSourceType.PARENT_PLAN,
            EvidenceSourceType.ACTIVITY_REFERENCE,
            EvidenceSourceType.INSTITUTION_SAMPLE,
        }
        assert _cited_classes(cell) <= {SemanticClass.EXCLUDED}
    for cell in plan.section("safety_education").cells:
        assert _source_types(cell) == {EvidenceSourceType.SAFETY_RULE}
        assert cell.cell_state is CellState.EMPTY_UNRESOLVED
    assert all(
        [event.event_type for event in cell.audit.events] == [AuditEventType.CREATED]
        for cell in plan.cells
    )
    assert plan.status is PlanStatus.DRAFT
    assert plan.verification_report.executed_rules == (AGE_RULE_REF,)

    # Month-level goals regeneration: target (goals, None) only, null target week, cell prompt v4.
    goals = plan.section("goals").cells[0]
    after_goals = harness.regenerate_monthly(plan, item_id=goals.item_id).plan
    goals_request = harness.provider.cell_requests[-1]
    regenerated = after_goals.find_cell(goals.item_id)[3]
    assert goals_request.target_week_id is None
    assert goals_request.prompt_version == MONTHLY_CELL_PROMPT_VERSION
    assert (regenerated.section_key, regenerated.week_id) == ("goals", None)
    assert _cited_classes(regenerated) == {SemanticClass.GOALS}
    assert regenerated.audit.events[-1].event_type is AuditEventType.REGENERATED
    assert all(
        after_goals.find_cell(cell.item_id)[3] is cell
        for cell in plan.cells
        if cell.item_id != goals.item_id
    )
    assert after_goals.verification_report is not plan.verification_report

    # The last computed week is a valid weekly target.
    last_habit = after_goals.section("basic_habit").cells[-1]
    after_habit = harness.regenerate_monthly(after_goals, item_id=last_habit.item_id).plan
    assert last_habit.week_id == week_ids[-1]
    assert harness.provider.cell_requests[-1].target_week_id == week_ids[-1]
    assert _cited_classes(after_habit.find_cell(last_habit.item_id)[3]) == {
        SemanticClass.BASIC_HABIT
    }
    assert harness.monthly_plans.get(plan.plan_id) is after_habit
