"""W3a GenerateWeeklyPlan: gates, parent context and the RULE_ONLY path (W1 contract)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ssuksak.planning.application import generate_weekly_plan as weekly
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.application.ports import OptionalContextStatus
from ssuksak.planning.domain.monthly_constraint import CellState
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.monthly_verification import FindingKind
from ssuksak.planning.domain.provenance import EvidenceSource, EvidenceSourceType
from ssuksak.planning.domain.safety_placement import SafetyKind, SafetyPlacement
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.weekly_plan import WEEKDAYS_WITH_SATURDAY, OperatingDay
from ssuksak.planning.rules.monthly_week_periods import deactivate
from ssuksak.planning.rules.safety_placement import OFFICIAL_GROUNDING_MISSING
from ssuksak.planning.application.monthly_support import theme_reference_id
from ssuksak.planning.rules.weekly_verification import PARENT_CITATION_INVALID, verify_weekly_plan

from tests.finalization.weekly_harness import WEEK, WeeklyHarness, weekly_snapshot

GROUNDED = ("focus", "goals", "basic_habit", "indoor_play", "group_activity", "indoor_alternative")
TEACHER_INPUT = ("family_link", "event_schedule", "special_program")


def _code(excinfo) -> str:
    return excinfo.value.code


def test_rule_only_draft_follows_the_contract_per_section():
    harness = WeeklyHarness()
    parent = harness.monthly_parent()
    plan = harness.generate_weekly(parent).plan

    assert plan.status.value == "DRAFT"
    assert plan.week_period == next(p for p in parent.week_periods if p.week_id == WEEK)
    assert plan.parent_lineage.parent_plan_id == parent.plan_id
    assert plan.parent_lineage.parent_item_id is None
    for key in GROUNDED:  # §7-4: no approved weekly grounding yet → that cell only, empty
        cell = plan.cell(key)
        assert (cell.value, cell.cell_state, cell.generation.method.value) == ("", CellState.EMPTY_VALID, "RULE_ONLY")
    for key in TEACHER_INPUT:  # §6-2: never generated
        cell = plan.cell(key)
        assert (cell.value, cell.cell_state, cell.generation) == ("", CellState.EMPTY_VALID, None)
    safety = plan.cell("safety_education")
    assert (safety.value, safety.cell_state, safety.evidence, safety.safety) == ("", CellState.EMPTY_UNRESOLVED, (), None)
    assert harness.weekly_plans.get(plan.plan_id) == plan


def test_theme_and_its_citation_use_the_parents_current_teacher_edited_value():
    harness = WeeklyHarness()
    draft = harness.monthly_parent(confirm=False)
    theme_cell = draft.section("theme").cells[0]
    parent = harness.confirm_monthly(harness.edit_monthly(draft, item_id=theme_cell.item_id, value="교사가 고친 9월 주제"))

    theme = harness.generate_weekly(parent).plan.cell("theme")

    assert theme.value == "교사가 고친 9월 주제"
    assert [(s.parent_item_id, s.snapshot_value) for s in theme.parent_snapshots] == [
        (theme_cell.item_id, "교사가 고친 9월 주제")
    ]
    assert [s.source_type for s in theme.evidence] == [EvidenceSourceType.PARENT_PLAN]


def _parent_with_same_week_activity(harness, candidate):
    """A confirmed parent whose WEEK outdoor cell holds `candidate` as its current value."""
    draft = harness.monthly_parent(confirm=False)
    cell = draft.section("outdoor_play").cell_for_week(WEEK)
    reference = EvidenceSource(
        EvidenceSourceType.ACTIVITY_REFERENCE,
        candidate.activity_id,
        draft.activity_catalog_ref.catalog_version,
        display_name=candidate.label,
    )
    kept = tuple(s for s in cell.evidence if s.source_type is not EvidenceSourceType.ACTIVITY_REFERENCE)
    changed = replace(cell, value=candidate.label, cell_state=CellState.FILLED, evidence=(*kept, reference))
    draft = replace(draft, sections=tuple(
        replace(s, cells=tuple(changed if c.item_id == cell.item_id else c for c in s.cells))
        if s.section_key == "outdoor_play" else s
        for s in draft.sections
    ))
    harness.monthly_plans.save(draft.plan_id, draft)
    return harness.confirm_monthly(draft), changed


def _eligible(harness, parent):
    ref = parent.activity_catalog_ref
    catalog = harness.activities.get_catalog(ref.catalog_id, ref.catalog_version)
    return catalog.eligible_candidates(
        section_key="outdoor_play", calendar_month=WEEK.target_month.calendar_month, ages=parent.target_ages
    )


def test_outdoor_play_prefers_the_parents_same_week_activity():
    probe = WeeklyHarness().monthly_parent()
    used = {c.value for c in probe.section("outdoor_play").cells}
    other = next(c for c in _eligible(WeeklyHarness(), probe) if c.label not in used)
    harness = WeeklyHarness()
    parent, same_week = _parent_with_same_week_activity(harness, other)

    result = harness.generate_weekly(parent)
    outdoor = result.plan.cell("outdoor_play")

    assert outdoor.value == other.label  # §4-2 가점: the parent's same-week choice
    assert result.activity_selection.rule_id == weekly.OUTDOOR_RULE_ID
    assert weekly.PARENT_ACTIVITY_REASON in result.activity_selection.reason_codes
    assert outdoor.generation.rule_id == weekly.OUTDOOR_RULE_ID
    cited = [(s.parent_item_id, s.snapshot_value) for s in outdoor.parent_snapshots]
    assert cited[1] == (same_week.item_id, other.label)  # theme, then the same week


def test_outdoor_bonus_is_not_a_copy_a_theme_linked_candidate_still_wins():
    probe = WeeklyHarness().monthly_parent()
    theme_id = theme_reference_id(probe.section("theme").cells[0].evidence)
    used = {c.value for c in probe.section("outdoor_play").cells}
    eligible = [c for c in _eligible(WeeklyHarness(), probe) if c.label not in used]
    unlinked = next(c for c in eligible if not c.links_theme(theme_id))
    assert any(c.links_theme(theme_id) for c in eligible)  # a theme-linked rival exists
    harness = WeeklyHarness()
    parent, _ = _parent_with_same_week_activity(harness, unlinked)

    result = harness.generate_weekly(parent)

    # The bonus sits after the parent-theme link: the parent's unlinked activity loses.
    assert result.plan.cell("outdoor_play").value != unlinked.label
    assert weekly.PARENT_ACTIVITY_REASON not in result.activity_selection.reason_codes


def test_outdoor_play_gives_no_preference_once_the_teacher_rewrote_the_parent_cell():
    harness = WeeklyHarness()
    draft = harness.monthly_parent(confirm=False)
    cell = draft.section("outdoor_play").cell_for_week(WEEK)
    parent = harness.confirm_monthly(harness.edit_monthly(draft, item_id=cell.item_id, value="교사가 쓴 바깥놀이"))

    result = harness.generate_weekly(parent)

    # The old ACTIVITY_REFERENCE stays as history but is no longer the parent's current choice.
    assert result.activity_selection.rule_id == weekly.OUTDOOR_RULE_ID
    assert weekly.PARENT_ACTIVITY_REASON not in result.activity_selection.reason_codes
    assert cell.item_id not in {s.parent_item_id for s in result.plan.cell("outdoor_play").parent_snapshots}


def test_outdoor_play_avoids_the_parents_other_weeks_and_cites_them():
    harness = WeeklyHarness()
    draft = harness.monthly_parent(confirm=False)
    same = draft.section("outdoor_play").cell_for_week(WEEK)
    parent = harness.confirm_monthly(harness.edit_monthly(draft, item_id=same.item_id, value="교사가 쓴 바깥놀이"))
    others = [c for c in parent.section("outdoor_play").cells if c.week_id != WEEK]

    outdoor = harness.generate_weekly(parent).plan.cell("outdoor_play")

    assert outdoor.value not in {c.value for c in others}
    assert {s.parent_item_id for s in outdoor.parent_snapshots} >= {c.item_id for c in others}
    assert {s.source_type for s in outdoor.evidence} == {
        EvidenceSourceType.PARENT_PLAN, EvidenceSourceType.ACTIVITY_REFERENCE
    }


def test_safety_stays_empty_first_even_when_the_parent_teacher_wrote_one():
    harness = WeeklyHarness()
    draft = harness.monthly_parent(confirm=False)
    cell = next(c for c in draft.section("safety_education").cells if c.week_id == WEEK)
    parent = harness.confirm_monthly(harness.edit_monthly(draft, item_id=cell.item_id, value="교통안전 약속"))

    safety = harness.generate_weekly(parent).plan.cell("safety_education")

    # Writing the parent's teacher sentence is the LLM path (§8); RULE_ONLY claims nothing.
    assert (safety.value, safety.cell_state, safety.safety, safety.parent_snapshots) == (
        "", CellState.EMPTY_UNRESOLVED, None, ()
    )


def test_saturday_changes_only_operating_days():
    def run(**kwargs):
        harness = WeeklyHarness()  # fresh harness each: same deterministic ids
        return weekly_snapshot(harness.generate_weekly(harness.monthly_parent(), **kwargs))

    weekdays, saturday = run(), run(operating_days=WEEKDAYS_WITH_SATURDAY)

    assert saturday.pop("operating_days")[-1] == OperatingDay.SAT.value
    weekdays.pop("operating_days")
    assert saturday == weekdays


def test_parent_must_exist_and_be_confirmed():
    harness = WeeklyHarness()
    draft = harness.monthly_parent(confirm=False)
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(draft)
    assert _code(excinfo) == "parent_monthly_plan_must_be_confirmed"

    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(replace(draft, plan_id=type(draft.plan_id)("monthly-missing"), verification_report=None))
    assert _code(excinfo) == "parent_monthly_plan_not_found"
    assert len(harness.weekly_plans) == 0  # nothing saved


def test_week_must_be_an_active_week_of_the_parent():
    harness = WeeklyHarness()
    parent = harness.monthly_parent()
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(parent, week_id=WeekId("2026-10-W1"))
    assert _code(excinfo) == "weekly_week_not_in_parent"

    inactive = replace(
        parent,
        week_periods=deactivate(parent.week_periods, frozenset({WEEK})),
        sections=tuple(replace(s, cells=tuple(c for c in s.cells if c.week_id != WEEK)) for s in parent.sections),
    )
    harness.monthly_plans.save(inactive.plan_id, inactive)
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(inactive)
    assert _code(excinfo) == "weekly_week_inactive"


class _PendingTemplates:
    """The real Template with its approval taken back: the gate must still refuse it."""

    def __init__(self, real) -> None:
        self._real = real

    def get_template(self, template_id: str, template_version: str):
        template = self._real.get_template(template_id, template_version)
        return None if template is None else replace(template, runtime_active=False)


def test_pending_weekly_template_blocks_generation():
    harness = WeeklyHarness()
    pending = _PendingTemplates(harness.weekly_templates)
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(harness.monthly_parent(), templates=pending)
    assert _code(excinfo) == "monthly_template_not_approved"
    assert len(harness.weekly_plans) == 0


def test_llm_planner_is_refused_not_answered_by_rules():
    harness = WeeklyHarness()
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(harness.monthly_parent(), mode=MonthlyGenerationMode.LLM_PLANNER)
    assert _code(excinfo) == "weekly_generation_mode_unsupported"


def test_optional_context_failure_is_recorded_and_generation_succeeds():
    class Exploding:
        def fetch(self, name):
            raise TimeoutError(name)

    harness = WeeklyHarness()
    result = harness.generate_weekly(
        harness.monthly_parent(), optional_context=Exploding(), optional_context_names=("trend",)
    )

    assert [(r.name, r.status) for r in result.optional_context] == [("trend", OptionalContextStatus.ERROR)]
    assert harness.weekly_plans.get(result.plan.plan_id) == result.plan


def test_verifier_failure_saves_nothing(monkeypatch):
    def broken(plan, catalog, parent):
        raise RuntimeError("verifier down")

    monkeypatch.setattr(weekly, "verify_weekly_plan", broken)
    harness = WeeklyHarness()
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(harness.monthly_parent())
    assert _code(excinfo) == "weekly_verification_failed"
    assert len(harness.weekly_plans) == 0


def test_safety_grounding_violation_blocks_saving(monkeypatch):
    def uncited(plan, catalog, parent):
        cells = tuple(
            replace(c, value="교통안전", cell_state=CellState.FILLED) if c.section_key == "safety_education" else c
            for c in plan.cells
        )
        return verify_weekly_plan(replace(plan, cells=cells), catalog, parent)

    monkeypatch.setattr(weekly, "verify_weekly_plan", uncited)
    harness = WeeklyHarness()
    with pytest.raises(MonthlyApplicationError) as excinfo:
        harness.generate_weekly(harness.monthly_parent())
    assert _code(excinfo) == "weekly_safety_verification_failed"
    assert len(harness.weekly_plans) == 0


def test_safety_grounding_rule_per_row():
    harness = WeeklyHarness()
    draft = harness.monthly_parent(confirm=False)
    safety_cells = draft.section("safety_education").cells
    this_week = next(c for c in safety_cells if c.week_id == WEEK)
    other_week = next(c for c in safety_cells if c.week_id != WEEK)
    draft = harness.edit_monthly(draft, item_id=this_week.item_id, value="교사가 쓴 교통안전 약속")
    draft = harness.edit_monthly(draft, item_id=other_week.item_id, value="다른 주 안전 문장")
    parent = harness.confirm_monthly(draft)
    plan = harness.generate_weekly(parent).plan
    parent_source = plan.cell("theme").evidence[0]  # PARENT_PLAN of this parent

    def cite(cell, value=None):
        return replace(plan.parent_lineage, parent_item_id=cell.item_id, snapshot_value=value or cell.value)

    current = parent.section("safety_education").cell_for_week(WEEK)
    citation = cite(current)
    catalog = harness.activities.get_catalog(plan.activity_catalog_ref.catalog_id, plan.activity_catalog_ref.catalog_version)

    def findings(**changes):
        cells = tuple(
            replace(c, value="교통안전", cell_state=CellState.FILLED, **changes) if c.section_key == "safety_education" else c
            for c in plan.cells
        )
        report = verify_weekly_plan(replace(plan, cells=cells), catalog, parent)
        return [(f.code, f.finding_kind) for f in report.findings if f.location.section_key == "safety_education"]

    invalid = [(PARENT_CITATION_INVALID, FindingKind.VIOLATION)]

    # Teacher-text / supplemental rows: the exact parent citation, no legal category.
    assert findings(evidence=(parent_source,), parent_snapshots=(citation,)) == []
    assert findings() == invalid
    # Citing another parent Cell, or a stale value of the right one, is not grounding.
    theme_cited = plan.cell("theme").parent_snapshots[0]
    assert findings(evidence=(parent_source,), parent_snapshots=(theme_cited,)) == invalid
    other = parent.section("safety_education").cell_for_week(other_week.week_id)
    assert findings(evidence=(parent_source,), parent_snapshots=(cite(other),)) == invalid
    assert findings(evidence=(parent_source,), parent_snapshots=(cite(current, "옛 문장"),)) == invalid
    legal = EvidenceSource(EvidenceSourceType.SAFETY_RULE, "annex6:traffic:1", "v")
    assert findings(evidence=(parent_source, legal), parent_snapshots=(citation,)) == [
        (PARENT_CITATION_INVALID, FindingKind.VIOLATION)
    ]
    # Untouched statutory placement: its own official grounding only.
    statutory = SafetyPlacement(SafetyKind.STATUTORY, "traffic", "p", "l")
    assert findings(safety=statutory, evidence=(parent_source,)) == [(OFFICIAL_GROUNDING_MISSING, FindingKind.VIOLATION)]
    assert findings(safety=statutory, evidence=(legal,)) == []


def test_the_approved_weekly_template_generates_without_test_approval():
    harness = WeeklyHarness()
    plan = harness.generate_weekly(harness.monthly_parent(), templates=harness.weekly_templates).plan
    assert plan.status.value == "DRAFT"
