"""Weekly Plan domain invariants (docs/weekly-plan-contract.md §3 · §5 · §6 · §10-2)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ssuksak.adapters.monthly_template_schema import parse_monthly_template_payload
from ssuksak.planning.domain.errors import (
    InvalidDomainValueError,
    InvalidStateTransitionError,
)
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.lineage import ParentLineage
from ssuksak.planning.domain.monthly_constraint import CellState
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.weekly_plan import (
    WEEKDAYS,
    WEEKDAYS_WITH_SATURDAY,
    WEEKLY_INSTITUTION_INPUT_SECTION_KEYS,
    OperatingDay,
    WeeklyCell,
    WeeklyPlan,
    WeeklyTemplateSnapshot,
)
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods

TEMPLATE = Path(__file__).resolve().parents[2] / "data" / "templates" / "weekly_template_a_v0_1_0.json"
NOW = datetime(2026, 9, 20, 1, tzinfo=UTC)
LLM = GenerationMethodDetail(GenerationMethod.RULE_LLM, "weekly.test", "v1")
PARENT = ParentLineage(PlanId("monthly-1"), NOW, ActorId("user_1"))
WEEK = canonical_week_periods(YearMonth(2026, 9))[1]


def _template():
    return parse_monthly_template_payload(json.loads(TEMPLATE.read_text(encoding="utf-8")))


def _snapshot() -> WeeklyTemplateSnapshot:
    return WeeklyTemplateSnapshot.from_template(
        _template(), institution_ref="daycare-1", classroom_ref="class-1"
    )


def _cell(key: str, value: str = "") -> WeeklyCell:
    if key in WEEKLY_INSTITUTION_INPUT_SECTION_KEYS:
        generation = None
    else:
        generation = LLM if value else GenerationMethodDetail(GenerationMethod.RULE_ONLY, "weekly.test", "v1")
    return WeeklyCell(
        item_id=ItemId(f"item-{key}"),
        section_key=key,
        value=value,
        cell_state=CellState.FILLED if value else CellState.EMPTY_VALID,
        generation=generation,
    )


def _plan(**changes) -> WeeklyPlan:
    snapshot = _snapshot()
    cells = tuple(
        _cell(section.section_key, "가을 산책" if section.section_key == "theme" else "")
        for section in snapshot.sections
    )
    values = dict(
        plan_id=PlanId("weekly-1"),
        school_year=2026,
        week_id=WEEK.week_id,
        week_period=WEEK,
        operating_days=WEEKDAYS,
        daycare_ref="daycare-1",
        classroom_ref="class-1",
        target_ages=frozenset({4, 5}),
        status=PlanStatus.DRAFT,
        parent_lineage=PARENT,
        template_snapshot=snapshot,
        cells=cells,
    )
    values.update(changes)
    return WeeklyPlan(**values)


def test_template_is_pending_inactive_and_has_the_contract_sections():
    template = _template()

    assert str(template.template_ref) == "ssuksak.weekly-template-a/weekly-template-a-v0.1.0"
    assert not template.is_active
    assert [section.section_key for section in template.activated_sections] == [
        "theme", "focus", "goals", "basic_habit", "safety_education", "indoor_play",
        "group_activity", "outdoor_play", "indoor_alternative",
        "family_link", "event_schedule", "special_program",
    ]
    assert not template.inactive_sections
    raw = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    teacher_input = {s["semantic_key"] for s in raw["sections"] if s["selection"] == "INSTITUTION_INPUT"}
    assert teacher_input == WEEKLY_INSTITUTION_INPUT_SECTION_KEYS
    # W1 §7-4: missing evidence empties that cell only; only theme (always in the parent) is required.
    assert [s.section_key for s in template.activated_sections if s.required_for_generation] == ["theme"]


def test_a_valid_plan_has_one_cell_per_section_and_saturday_is_optional():
    plan = _plan()

    assert [cell.section_key for cell in plan.cells] == [s.section_key for s in plan.template_snapshot.sections]
    assert _plan(operating_days=WEEKDAYS_WITH_SATURDAY).operating_days[-1] is OperatingDay.SAT


@pytest.mark.parametrize(
    "days",
    [WEEKDAYS[:4], (*WEEKDAYS, OperatingDay.SAT, OperatingDay.SAT), tuple(reversed(WEEKDAYS)), (OperatingDay.SAT,)],
)
def test_operating_days_are_mon_fri_or_mon_sat_only(days):
    with pytest.raises(InvalidDomainValueError, match="operating_days"):
        _plan(operating_days=days)


def test_week_period_must_be_the_period_of_week_id():
    with pytest.raises(InvalidDomainValueError, match="week_period"):
        _plan(week_id=WeekId("2026-09-W3"))


def test_week_must_belong_to_the_school_year():
    february = canonical_week_periods(YearMonth(2026, 2))[0]
    with pytest.raises(InvalidDomainValueError, match="school year"):
        _plan(week_id=february.week_id, week_period=february)


def test_cells_must_match_sections_one_to_one():
    plan = _plan()
    with pytest.raises(InvalidDomainValueError, match="one Cell per"):
        _plan(cells=plan.cells[:-1])
    with pytest.raises(InvalidDomainValueError, match="one Cell per"):
        _plan(cells=(*plan.cells, plan.cells[-1]))


def test_theme_cannot_be_blank():
    cells = tuple(_cell(cell.section_key) for cell in _plan().cells)
    with pytest.raises(InvalidDomainValueError, match="theme"):
        _plan(cells=cells)


def test_parent_lineage_is_plan_level_and_cell_snapshots_are_item_level():
    item_level = ParentLineage(PlanId("monthly-1"), NOW, ActorId("user_1"), ItemId("m-theme"), "가을")
    with pytest.raises(InvalidDomainValueError, match="plan-level"):
        _plan(parent_lineage=item_level)

    cell = replace(_cell("theme", "가을 산책"), parent_snapshots=(item_level,))
    assert cell.parent_snapshots[0].snapshot_value == "가을"
    with pytest.raises(InvalidDomainValueError, match="item-level"):
        replace(cell, parent_snapshots=(PARENT,))


def test_generation_may_be_missing_only_on_an_empty_teacher_input_cell():
    assert _cell("family_link").generation is None
    with pytest.raises(InvalidDomainValueError, match="no generation"):
        WeeklyCell(ItemId("i"), "indoor_play", "", CellState.EMPTY_VALID)
    with pytest.raises(InvalidDomainValueError, match="no generation"):
        WeeklyCell(ItemId("i"), "family_link", "공지", CellState.FILLED)


def test_teacher_input_cell_is_manual_never_generated():
    manual = GenerationMethodDetail(GenerationMethod.MANUAL)
    assert WeeklyCell(ItemId("i"), "event_schedule", "운동회", CellState.FILLED, manual).generation is manual
    with pytest.raises(InvalidDomainValueError, match="MANUAL"):
        WeeklyCell(ItemId("i"), "event_schedule", "운동회", CellState.FILLED, LLM)


@pytest.mark.parametrize(("value", "state"), [("교사가 쓴 놀이", CellState.FILLED), ("", CellState.EMPTY_VALID)])
def test_generated_cell_is_never_manual(value, state):
    # W1 §10-2: a teacher filling or editing a generated cell keeps its method.
    with pytest.raises(InvalidDomainValueError, match="MANUAL is for teacher-input"):
        WeeklyCell(ItemId("i"), "indoor_play", value, state, GenerationMethodDetail(GenerationMethod.MANUAL))


def test_snapshot_rejects_legacy_habits_and_non_weekly_sections():
    sections = _snapshot().sections
    with pytest.raises(InvalidDomainValueError, match="habits"):
        WeeklyTemplateSnapshot(
            base_template_ref=_snapshot().base_template_ref,
            institution_ref="daycare-1",
            sections=(*sections, replace(sections[3], section_key="habits", order=99)),
        )
    with pytest.raises(InvalidDomainValueError, match="duplicate"):
        WeeklyTemplateSnapshot(_snapshot().base_template_ref, "daycare-1", (*sections, sections[0]))
    with pytest.raises(InvalidDomainValueError, match="active"):
        WeeklyTemplateSnapshot(_snapshot().base_template_ref, "daycare-1", (replace(sections[0], activated=False, required_for_generation=False),))
    with pytest.raises(InvalidDomainValueError, match="ascending"):
        WeeklyTemplateSnapshot(_snapshot().base_template_ref, "daycare-1", tuple(reversed(sections)))


def test_confirm_appends_event_and_confirmed_plan_is_read_only():
    confirmed = _plan().confirm(actor_id=ActorId("user_1"), occurred_at=NOW)

    assert confirmed.status is PlanStatus.CONFIRMED
    assert confirmed.audit.events[-1].event_type is AuditEventType.CONFIRMED
    with pytest.raises(InvalidStateTransitionError):
        confirmed.ensure_mutable("edit")
    with pytest.raises(InvalidStateTransitionError):
        confirmed.confirm(actor_id=ActorId("user_1"), occurred_at=NOW)
