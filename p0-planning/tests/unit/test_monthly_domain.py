"""Monthly Domain 타입 검증.

확정된 Contract를 타입 수준에서 고정한다.

- ParentYearlyLineage는 immutable snapshot이고 anchor 변경 경로가 없다
- MonthlyPlanItem은 공용 PlanItem과 별도 타입이며 공용 PlanItem을 바꾸지 않는다
- weekly item은 valid WeekId를 참조하고 merged item은 week_id=None이다
- EMPTY_VALID와 EMPTY_UNRESOLVED를 구분한다
- ConstraintAssessment는 해결 방법 없는 미검증 상태를 허용하지 않는다
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime

import pytest

from ssuksak.planning.domain.constraint import (
    CellState,
    ConstraintAssessment,
    ConstraintKind,
    ConstraintVerification,
)
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.identifiers import (
    InvalidIdentifierError,
    ItemId,
    PeriodKey,
    PlanId,
    SemanticKey,
)
from ssuksak.planning.domain.monthly_plan import (
    LabelVariant,
    MappingConfidence,
    MonthlyPlan,
    MonthlyPlanItem,
    MonthlySection,
)
from ssuksak.planning.domain.monthly_template import (
    DisplayMode,
    EmptyValuePolicy,
    SectionRole,
    TemplateRef,
)
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.domain.plan import PlanItem, PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditTrail,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
    SYSTEM_ACTOR_MARKER,
)
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.rules.monthly_week_periods import canonical_week_periods

NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
RULE = GenerationMethodDetail(
    method=GenerationMethod.RULE_ONLY,
    rule_id="monthly.template.section_resolution",
    rule_version="v1",
)


def lineage(**over) -> ParentYearlyLineage:
    base = dict(
        parent_yearly_plan_id="yearly_plan_001",
        parent_yearly_period_key="2026-09",
        parent_yearly_theme_id="yr_theme_korea_and_world_cultures",
        parent_yearly_value="우리나라와 세계 여러 나라",
        reference_catalog_id="ssuksak.yearly-theme-reference",
        reference_version="theme-reference-v0.1.2",
        confirmed_at=NOW,
        confirmed_by="teacher_dev_001",
    )
    base.update(over)
    return ParentYearlyLineage(**base)


# ------------------------------------------------- ParentYearlyLineage


def test_lineage_is_frozen():
    lin = lineage()
    with pytest.raises(dataclasses.FrozenInstanceError):
        lin.parent_yearly_theme_id = "other"  # type: ignore[misc]


def test_lineage_anchor_alias_points_to_theme_id():
    lin = lineage()
    assert lin.anchor_theme_id == lin.parent_yearly_theme_id


@pytest.mark.parametrize(
    "field",
    [
        "parent_yearly_plan_id",
        "parent_yearly_period_key",
        "parent_yearly_theme_id",
        "parent_yearly_value",
        "reference_catalog_id",
        "reference_version",
        "confirmed_by",
    ],
)
def test_lineage_rejects_blank_required_field(field: str):
    with pytest.raises(ValueError, match=field):
        lineage(**{field: "   "})


def test_lineage_requires_datetime_confirmed_at():
    with pytest.raises(TypeError, match="confirmed_at"):
        lineage(confirmed_at="2026-09-11")


def test_lineage_has_no_mutator_methods():
    """anchor를 바꿀 수 있는 메서드가 타입에 없다."""
    callables = [
        n
        for n in dir(ParentYearlyLineage)
        if not n.startswith("_")
        and callable(getattr(ParentYearlyLineage, n, None))
    ]
    assert callables == []


def test_plan_does_not_expose_lineage_replacement():
    plan = build_plan()
    setters = [n for n in dir(plan) if n.startswith("set_") or n.startswith("replace_")]
    assert setters == []


# ----------------------------------------------------------- Constraint


def test_constraint_kind_has_only_approved_value():
    assert [k.value for k in ConstraintKind] == ["STATUTORY_SAFETY_EDUCATION"]


def test_constraint_verification_has_only_approved_values():
    assert [v.value for v in ConstraintVerification] == [
        "VERIFIED",
        "NOT_VERIFIED_SOURCE_REQUIRED",
        "NOT_APPLICABLE",
    ]


def test_cell_state_has_three_values():
    assert [s.value for s in CellState] == [
        "FILLED",
        "EMPTY_VALID",
        "EMPTY_UNRESOLVED",
    ]


def test_unresolved_constraint_requires_source_kinds():
    """해결 방법을 안내할 수 없는 미검증 상태를 만들지 않는다."""
    with pytest.raises(ValueError, match="required_source_kinds"):
        ConstraintAssessment(
            kind=ConstraintKind.STATUTORY_SAFETY_EDUCATION,
            verification=ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED,
            rule_version="child-welfare-act-decree-annex6-2022-06-21",
        )


def test_unresolved_constraint_accepts_source_kinds():
    assessment = ConstraintAssessment(
        kind=ConstraintKind.STATUTORY_SAFETY_EDUCATION,
        verification=ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED,
        rule_version="child-welfare-act-decree-annex6-2022-06-21",
        required_source_kinds=("INSTITUTION_ANNUAL_SAFETY_PLAN", "TEACHER_INPUT"),
        affected_section_keys=("safety_education",),
    )
    assert assessment.is_unresolved is True


def test_verified_constraint_needs_no_source_kinds():
    assessment = ConstraintAssessment(
        kind=ConstraintKind.STATUTORY_SAFETY_EDUCATION,
        verification=ConstraintVerification.VERIFIED,
        rule_version="child-welfare-act-decree-annex6-2022-06-21",
    )
    assert assessment.is_unresolved is False


def test_constraint_requires_rule_version():
    with pytest.raises(ValueError, match="rule_version"):
        ConstraintAssessment(
            kind=ConstraintKind.STATUTORY_SAFETY_EDUCATION,
            verification=ConstraintVerification.NOT_APPLICABLE,
            rule_version="  ",
        )


def test_constraint_is_frozen():
    a = ConstraintAssessment(
        kind=ConstraintKind.STATUTORY_SAFETY_EDUCATION,
        verification=ConstraintVerification.NOT_APPLICABLE,
        rule_version="v1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.verification = ConstraintVerification.VERIFIED  # type: ignore[misc]


# ------------------------------------------------------ MonthlyPlanItem


def item(**over) -> MonthlyPlanItem:
    base = dict(
        item_id=ItemId("m_item_001"),
        semantic_key=SemanticKey.monthly_section("outdoor_play"),
        value="",
        generation=RULE,
        cell_state=CellState.EMPTY_VALID,
    )
    base.update(over)
    return MonthlyPlanItem(**base)


def test_monthly_item_is_a_distinct_type_from_shared_plan_item():
    assert MonthlyPlanItem is not PlanItem
    assert not issubclass(MonthlyPlanItem, PlanItem)


def test_shared_plan_item_is_unchanged():
    """공용 PlanItem에 Monthly 전용 필드를 추가하지 않았다."""
    names = {f.name for f in dataclasses.fields(PlanItem)}
    assert names == {
        "item_id", "semantic_key", "value", "generation", "evidence", "audit",
    }


def test_monthly_item_has_monthly_only_fields():
    names = {f.name for f in dataclasses.fields(MonthlyPlanItem)}
    assert {
        "week_id", "cell_state", "source_label", "label_variant", "mapping_confidence",
    } <= names


def test_monthly_item_reuses_shared_provenance_types():
    it = item(
        evidence=[
            EvidenceSource(
                source_type=EvidenceSourceType.PARENT_PLAN,
                source_id="yearly_plan_001",
                source_version="theme-reference-v0.1.2",
            )
        ],
        audit=AuditTrail(
            [
                AuditEvent(
                    event_type=AuditEventType.CREATED,
                    occurred_at=NOW,
                    plan_id="m_plan_001",
                    system_actor=SYSTEM_ACTOR_MARKER,
                )
            ]
        ),
    )
    assert isinstance(it.generation, GenerationMethodDetail)
    assert isinstance(it.evidence[0], EvidenceSource)
    assert isinstance(it.audit, AuditTrail)
    assert it.evidence_of_type(EvidenceSourceType.PARENT_PLAN)


def test_weekly_item_references_valid_week_id():
    week = canonical_week_periods(PeriodKey("2026-09"))[1]
    it = item(week_id=week.week_id)
    assert it.week_id == WeekId("2026-09-W2")
    assert it.is_merged_cell is False


def test_merged_item_has_no_week_id():
    it = item(week_id=None)
    assert it.is_merged_cell is True


def test_week_id_must_be_week_id_type_not_string():
    """문자열 순번을 주소로 쓰지 않는다."""
    with pytest.raises(TypeError, match="WeekId"):
        item(week_id="2026-09-W2")


def test_filled_cell_requires_value():
    with pytest.raises(ValueError, match="FILLED일 수 없다"):
        item(value="", cell_state=CellState.FILLED)


def test_value_requires_filled_state():
    with pytest.raises(ValueError, match="FILLED여야 한다"):
        item(value="가을과 자연", cell_state=CellState.EMPTY_VALID)


def test_empty_valid_and_empty_unresolved_are_distinguished():
    valid = item(cell_state=CellState.EMPTY_VALID)
    unresolved = item(cell_state=CellState.EMPTY_UNRESOLVED)
    assert valid.cell_state is not unresolved.cell_state
    assert valid.cell_state.is_empty and unresolved.cell_state.is_empty


def test_label_variant_and_mapping_confidence_are_optional():
    it = item(
        source_label="예상 놀이",
        label_variant=LabelVariant.EXPECTED_PLAY_LABELED,
        mapping_confidence=MappingConfidence.HIGH,
    )
    assert it.source_label == "예상 놀이"
    assert it.label_variant is LabelVariant.EXPECTED_PLAY_LABELED
    assert item().label_variant is None


def test_label_variant_values():
    assert [v.value for v in LabelVariant] == [
        "SUBTHEME_LABELED", "EXPECTED_PLAY_LABELED", "UNLABELED",
    ]


def test_semantic_key_does_not_encode_week_position():
    """monthly.week.02.outdoor_play 형태를 만들지 않는다."""
    key = SemanticKey.monthly_section("outdoor_play")
    assert key.value == "monthly.section.outdoor_play"
    assert "week" not in key.value
    assert "02" not in key.value


def test_same_section_keeps_semantic_key_across_display_modes():
    """display_mode가 바뀌어도 Section 의미 식별자는 그대로다."""
    weekly = item(week_id=WeekId("2026-09-W1"))
    merged = item(week_id=None)
    assert weekly.semantic_key == merged.semantic_key


@pytest.mark.parametrize("bad", ["Outdoor", "outdoor-play", "2play", "", "monthly.x"])
def test_monthly_section_key_rejects_invalid(bad: str):
    with pytest.raises(InvalidIdentifierError):
        SemanticKey.monthly_section(bad)


def test_yearly_semantic_key_factory_is_unchanged():
    assert SemanticKey.yearly_month_theme(9).value == "yearly.month.09.theme"


# -------------------------------------------------------- MonthlySection


def test_axis_section_cannot_hold_items():
    with pytest.raises(ValueError, match="AXIS"):
        MonthlySection(
            semantic_key=SemanticKey.monthly_section("week_axis"),
            section_key="week_axis",
            role=SectionRole.AXIS,
            display_mode=None,
            empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
            items=[item()],
        )


def test_section_item_for_week_finds_merged_cell_with_none():
    section = MonthlySection(
        semantic_key=SemanticKey.monthly_section("theme"),
        section_key="theme",
        role=SectionRole.CONTENT,
        display_mode=DisplayMode.MONTHLY_MERGED_SUMMARY,
        empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
        items=[item(value="우리나라", cell_state=CellState.FILLED)],
    )
    assert section.item_for_week(None) is not None
    assert section.item_for_week("2026-09-W1") is None


# ------------------------------------------------------------ MonthlyPlan


def build_plan(status: PlanStatus = PlanStatus.DRAFT) -> MonthlyPlan:
    wp = canonical_week_periods(PeriodKey("2026-09"))
    theme = MonthlySection(
        semantic_key=SemanticKey.monthly_section("theme"),
        section_key="theme",
        role=SectionRole.CONTENT,
        display_mode=DisplayMode.MONTHLY_MERGED_SUMMARY,
        empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
        items=[
            MonthlyPlanItem(
                item_id=ItemId("m_item_theme"),
                semantic_key=SemanticKey.monthly_section("theme"),
                value="우리나라와 세계 여러 나라",
                generation=RULE,
                cell_state=CellState.FILLED,
                week_id=None,
            )
        ],
    )
    outdoor = MonthlySection(
        semantic_key=SemanticKey.monthly_section("outdoor_play"),
        section_key="outdoor_play",
        role=SectionRole.CONTENT,
        display_mode=DisplayMode.WEEKLY_CELLS,
        empty_value_policy=EmptyValuePolicy.RENDER_EMPTY_CELL,
        items=[
            MonthlyPlanItem(
                item_id=ItemId(f"m_item_out_{i}"),
                semantic_key=SemanticKey.monthly_section("outdoor_play"),
                value="",
                generation=RULE,
                cell_state=CellState.EMPTY_VALID,
                week_id=w.week_id,
            )
            for i, w in enumerate(wp, start=1)
        ],
    )
    return MonthlyPlan(
        plan_id=PlanId("m_plan_001"),
        school_year=2026,
        target_month=PeriodKey("2026-09"),
        daycare_ref="dev_daycare_001",
        classroom_ref="dev_classroom_001",
        classroom_ages=frozenset({4}),
        age_mode="SINGLE",
        status=status,
        parent_lineage=lineage(),
        template_ref=TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.1.0"),
        week_periods=wp,
        sections=[theme, outdoor],
    )


def test_week_periods_are_plan_level_axis_not_section_owned():
    plan = build_plan()
    assert len(plan.week_periods) == 5
    section_fields = {f.name for f in dataclasses.fields(MonthlySection)}
    assert "week_periods" not in section_fields


def test_find_cell_by_section_and_week():
    plan = build_plan()
    found = plan.find_cell(section_key="outdoor_play", week_id="2026-09-W3")
    assert found is not None
    section, cell = found
    assert section.section_key == "outdoor_play"
    assert cell.week_id == WeekId("2026-09-W3")


def test_find_cell_merged_uses_none_week_id():
    plan = build_plan()
    found = plan.find_cell(section_key="theme", week_id=None)
    assert found is not None
    assert found[1].is_merged_cell


def test_find_cell_by_item_id():
    plan = build_plan()
    found = plan.find_cell(item_id="m_item_theme")
    assert found is not None and found[1].item_id.value == "m_item_theme"


def test_find_cell_returns_none_for_unknown_address():
    plan = build_plan()
    assert plan.find_cell(section_key="outdoor_play", week_id="2026-09-W9") is None
    assert plan.find_cell(section_key="habits", week_id=None) is None


def test_active_week_periods_filter_keeps_canonical_list():
    from ssuksak.planning.rules.monthly_week_periods import deactivate

    plan = build_plan()
    plan.week_periods = deactivate(plan.week_periods, frozenset({"2026-09-W2"}))
    assert len(plan.week_periods) == 5
    assert len(plan.active_week_periods) == 4
    assert [w.week_id.ordinal for w in plan.week_periods] == [1, 2, 3, 4, 5]


def test_confirmed_plan_is_read_only():
    plan = build_plan(PlanStatus.CONFIRMED)
    with pytest.raises(PlanningError) as exc:
        plan.ensure_mutable("EditMonthlyPlanItem")
    assert exc.value.failure_category is FailureCategory.PLAN_STATE_GATE
    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"


def test_draft_plan_is_mutable():
    build_plan(PlanStatus.DRAFT).ensure_mutable("EditMonthlyPlanItem")


def test_plan_reuses_shared_plan_status():
    assert build_plan().status is PlanStatus.DRAFT
    assert [s.value for s in PlanStatus] == ["DRAFT", "CONFIRMED"]


def test_constraint_lookup_and_unresolved_filter():
    plan = build_plan()
    assert plan.unresolved_constraints == ()
    plan.constraint_assessments = (
        ConstraintAssessment(
            kind=ConstraintKind.STATUTORY_SAFETY_EDUCATION,
            verification=ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED,
            rule_version="child-welfare-act-decree-annex6-2022-06-21",
            required_source_kinds=("TEACHER_INPUT",),
        ),
    )
    assert plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION) is not None
    assert len(plan.unresolved_constraints) == 1


def test_items_collects_all_cells():
    plan = build_plan()
    assert len(plan.items) == 1 + 5


def test_domain_module_has_no_pydantic_import():
    """Domain은 직렬화 라이브러리에 의존하지 않는다. Yearly와 같은 규칙이다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "ssuksak" / "planning"
    for name in (
        "domain/monthly_plan.py",
        "domain/week_period.py",
        "domain/parent_lineage.py",
        "domain/constraint.py",
        "domain/monthly_template.py",
        "rules/monthly_week_periods.py",
        "rules/monthly_template_resolver.py",
    ):
        assert "pydantic" not in (root / name).read_text(encoding="utf-8"), name
