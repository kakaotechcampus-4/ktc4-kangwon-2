"""EditMonthlyPlanItem / RegenerateMonthlyPlanItem 검증.

M1-C 범위. Confirm Use Case는 아직 없으므로 CONFIRMED 상태는 Aggregate를
직접 구성해 read-only Gate를 검증한다.
"""

from __future__ import annotations

import dataclasses

import pytest

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.monthly_repositories import JsonMonthlyTemplateRepository
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.monthly_dto import (
    EditMonthlyPlanItemCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    REGENERATABLE_SECTION_KEYS,
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.domain.constraint import CellState, ConstraintKind
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.rules.monthly_theme_derivation import (
    RULE_ID as THEME_RULE_ID,
    RULE_VERSION as THEME_RULE_VERSION,
)

from .test_generate_monthly_plan import NOW, Wiring, build_parent, command

TEACHER = ActorId("teacher_m1c_001")
MONTH = "2026-09"


class Editing:
    """Generate로 DRAFT Plan을 만든 뒤 Edit/Regenerate를 붙인 조립."""

    def __init__(self, *, confirmed: bool = False) -> None:
        self.w = Wiring(parent=build_parent())
        self.plan = self.w.use_case.execute(command()).plan
        if confirmed:
            self.plan.status = PlanStatus.CONFIRMED
        templates = JsonMonthlyTemplateRepository()
        clock = FixedClock(NOW, advance_seconds=1)
        self.edit = EditMonthlyPlanItem(
            monthly_plan_repository=self.w.monthly,
            template_repository=templates,
            clock=clock,
        )
        self.regenerate = RegenerateMonthlyPlanItem(
            monthly_plan_repository=self.w.monthly,
            template_repository=templates,
            clock=clock,
        )
        self.saves_after_generate = self.w.monthly.save_count

    @property
    def extra_saves(self) -> int:
        return self.w.monthly.save_count - self.saves_after_generate

    def address(self, section_key: str, week_id: str | None = None, **kw):
        return MonthlyCellAddress(
            target_month=MONTH, section_key=section_key, week_id=week_id, **kw
        )

    def do_edit(self, section_key, new_value, week_id=None, actor=TEACHER, **kw):
        return self.edit.execute(
            EditMonthlyPlanItemCommand(
                plan_id=self.plan.plan_id.value,
                address=self.address(section_key, week_id, **kw),
                new_value=new_value,
                actor_id=actor,
            )
        )

    def do_regenerate(self, section_key, week_id=None, actor=TEACHER, **kw):
        return self.regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=self.plan.plan_id.value,
                address=self.address(section_key, week_id, **kw),
                actor_id=actor,
            )
        )

    def snapshot_all(self) -> dict:
        return {
            i.item_id.value: (
                i.value,
                i.cell_state,
                i.week_id.value if i.week_id else None,
                i.semantic_key.value,
                len(i.audit.events),
                i.generation.method,
                tuple((e.source_type, e.source_id) for e in i.evidence),
            )
            for i in self.plan.items
        }


def siblings_unchanged(before: dict, after: dict, changed_item_id: str) -> None:
    assert set(before) == set(after), "Cell 집합이 바뀌었다"
    for item_id, snap in before.items():
        if item_id == changed_item_id:
            continue
        assert after[item_id] == snap, f"sibling {item_id}가 변경됐다"


def lineage_unchanged(plan, before) -> None:
    assert plan.parent_lineage == before


# ==================================================== Edit 성공 경로


def test_theme_edit_success():
    e = Editing()
    before = e.snapshot_all()
    lin = e.plan.parent_lineage
    cell = e.plan.section("theme").items[0]

    e.do_edit("theme", "우리나라의 가을 이야기")

    assert cell.value == "우리나라의 가을 이야기"
    assert cell.cell_state is CellState.FILLED
    siblings_unchanged(before, e.snapshot_all(), cell.item_id.value)
    lineage_unchanged(e.plan, lin)
    assert e.extra_saves == 1
    assert e.plan.status is PlanStatus.DRAFT


def test_outdoor_edit_to_filled():
    e = Editing()
    cell = e.plan.section("outdoor_play").items[1]
    before = e.snapshot_all()

    e.do_edit("outdoor_play", "가을 숲 산책", week_id="2026-09-W2")

    assert cell.value == "가을 숲 산책"
    assert cell.cell_state is CellState.FILLED
    siblings_unchanged(before, e.snapshot_all(), cell.item_id.value)


def test_outdoor_edit_back_to_empty_is_valid():
    e = Editing()
    e.do_edit("outdoor_play", "가을 숲 산책", week_id="2026-09-W2")
    cell = e.plan.section("outdoor_play").items[1]
    assert cell.cell_state is CellState.FILLED

    e.do_edit("outdoor_play", "", week_id="2026-09-W2")

    assert cell.value == ""
    assert cell.cell_state is CellState.EMPTY_VALID


def test_safety_edit_to_filled():
    e = Editing()
    cell = e.plan.section("safety_education").items[0]

    e.do_edit("safety_education", "교통안전 - 신호등 알기", week_id="2026-09-W1")

    assert cell.value == "교통안전 - 신호등 알기"
    assert cell.cell_state is CellState.FILLED


def test_safety_edit_to_empty_stays_unresolved_while_source_missing():
    """교사가 값을 지웠다는 이유만으로 EMPTY_VALID로 바꾸지 않는다."""
    e = Editing()
    e.do_edit("safety_education", "교통안전", week_id="2026-09-W1")
    cell = e.plan.section("safety_education").items[0]
    assert cell.cell_state is CellState.FILLED

    e.do_edit("safety_education", "", week_id="2026-09-W1")

    assert cell.value == ""
    assert cell.cell_state is CellState.EMPTY_UNRESOLVED
    assessment = e.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert assessment.is_unresolved


# ---------------------------------------- CellState 전이 matrix


@pytest.mark.parametrize(
    "section_key,week_id,new_value,expected",
    [
        ("theme", None, "새 주제", CellState.FILLED),
        ("outdoor_play", "2026-09-W1", "바깥 놀이", CellState.FILLED),
        ("outdoor_play", "2026-09-W1", "", CellState.EMPTY_VALID),
        ("outdoor_play", "2026-09-W1", "   ", CellState.EMPTY_VALID),
        ("safety_education", "2026-09-W1", "안전교육", CellState.FILLED),
        ("safety_education", "2026-09-W1", "", CellState.EMPTY_UNRESOLVED),
        ("safety_education", "2026-09-W1", "   ", CellState.EMPTY_UNRESOLVED),
    ],
)
def test_cell_state_transition_matrix(section_key, week_id, new_value, expected):
    e = Editing()
    e.do_edit(section_key, new_value, week_id=week_id)
    found = e.plan.find_cell(section_key=section_key, week_id=week_id)
    assert found[1].cell_state is expected


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_theme_blank_edit_is_blocked(blank: str):
    e = Editing()
    original = e.plan.section("theme").items[0].value
    before = e.snapshot_all()

    with pytest.raises(PlanningError) as exc:
        e.do_edit("theme", blank)

    assert exc.value.failure_category is FailureCategory.REQUIRED_VALUE_VALIDATION
    assert exc.value.violated_rule == "theme_cell_is_required_and_non_blank"
    assert e.plan.section("theme").items[0].value == original
    assert e.snapshot_all() == before
    assert e.extra_saves == 0


# ------------------------------------------- Edit Provenance


def test_edit_preserves_generation_method_and_evidence():
    e = Editing()
    cell = e.plan.section("theme").items[0]
    method_before = cell.generation
    evidence_before = list(cell.evidence)

    e.do_edit("theme", "교사가 다듬은 주제")

    assert cell.generation is method_before
    assert cell.generation.method is GenerationMethod.RULE_ONLY
    assert cell.evidence == evidence_before
    assert cell.evidence_of_type(EvidenceSourceType.PARENT_PLAN)
    assert cell.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)


def test_edit_appends_teacher_edited_audit():
    e = Editing()
    cell = e.plan.section("theme").items[0]
    before_value = cell.value
    before_len = len(cell.audit.events)

    e.do_edit("theme", "교사 수정본")

    assert len(cell.audit.events) == before_len + 1
    event = cell.audit.events[-1]
    assert event.event_type is AuditEventType.TEACHER_EDITED
    assert event.actor_id == TEACHER
    assert event.previous_value == before_value
    assert event.new_value == "교사 수정본"
    assert event.item_id == cell.item_id.value
    assert event.previous_method is event.new_method
    assert event.occurred_at is not None


def test_edit_does_not_create_evidence_source():
    e = Editing()
    cell = e.plan.section("outdoor_play").items[0]
    e.do_edit("outdoor_play", "산책", week_id="2026-09-W1")
    assert cell.evidence == []


# -------------------------------------------- Edit 주소 검증


def test_edit_rejects_wrong_target_month():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.edit.execute(
            EditMonthlyPlanItemCommand(
                plan_id=e.plan.plan_id.value,
                address=MonthlyCellAddress("2026-10", "theme"),
                new_value="x",
                actor_id=TEACHER,
            )
        )
    assert exc.value.violated_rule == "cell_address_target_month_must_match_plan"
    assert e.extra_saves == 0


def test_edit_rejects_unknown_section():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("goals", "x")
    assert exc.value.violated_rule == "cell_address_section_must_exist"


def test_edit_rejects_axis_section():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("week_axis", "x")
    assert exc.value.violated_rule == "axis_section_has_no_addressable_cell"


def test_weekly_section_requires_week_id():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("outdoor_play", "x", week_id=None)
    assert exc.value.violated_rule == "weekly_section_address_requires_week_id"


def test_merged_section_must_omit_week_id():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("theme", "x", week_id="2026-09-W1")
    assert exc.value.violated_rule == "merged_section_address_must_omit_week_id"


def test_edit_rejects_week_id_from_other_month():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("outdoor_play", "x", week_id="2026-10-W1")
    assert exc.value.violated_rule == "cell_address_week_id_must_exist_in_plan"


def test_edit_rejects_nonexistent_week_id():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("outdoor_play", "x", week_id="2026-09-W9")
    assert exc.value.violated_rule == "cell_address_week_id_must_exist_in_plan"


def test_edit_rejects_mismatched_item_id():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("theme", "x", item_id="not_this_item")
    assert exc.value.violated_rule == (
        "cell_address_item_id_must_match_resolved_cell"
    )


def test_edit_accepts_matching_item_id():
    e = Editing()
    cell = e.plan.section("theme").items[0]
    e.do_edit("theme", "일치하는 주소", item_id=cell.item_id.value)
    assert cell.value == "일치하는 주소"


def test_edit_requires_existing_plan():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.edit.execute(
            EditMonthlyPlanItemCommand(
                plan_id="no_such_plan",
                address=e.address("theme"),
                new_value="x",
                actor_id=TEACHER,
            )
        )
    assert exc.value.violated_rule == "target_monthly_plan_must_exist"


@pytest.mark.parametrize("bad_actor", [None, "teacher_dev_001"])
def test_edit_requires_opaque_actor(bad_actor):
    e = Editing()
    before = e.snapshot_all()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("theme", "x", actor=bad_actor)
    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert e.snapshot_all() == before
    assert e.extra_saves == 0


# --------------------------------------- CONFIRMED read-only


def test_edit_on_confirmed_plan_is_blocked():
    e = Editing(confirmed=True)
    before = e.snapshot_all()
    with pytest.raises(PlanningError) as exc:
        e.do_edit("theme", "x")
    assert exc.value.failure_category is FailureCategory.PLAN_STATE_GATE
    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"
    assert e.snapshot_all() == before
    assert e.extra_saves == 0


def test_regenerate_on_confirmed_plan_is_blocked():
    e = Editing(confirmed=True)
    before = e.snapshot_all()
    with pytest.raises(PlanningError) as exc:
        e.do_regenerate("theme")
    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"
    assert e.snapshot_all() == before
    assert e.extra_saves == 0


# =============================================== Regenerate


def test_regeneratable_sections_are_theme_and_outdoor():
    """M2-D에서 `outdoor_play`가 열렸다. safety_education은 계속 제외된다."""
    assert REGENERATABLE_SECTION_KEYS == frozenset({"theme", "outdoor_play"})
    assert "safety_education" not in REGENERATABLE_SECTION_KEYS


def test_theme_regenerate_success():
    e = Editing()
    e.do_edit("theme", "교사가 바꾼 값")
    cell = e.plan.section("theme").items[0]
    before = e.snapshot_all()
    lin = e.plan.parent_lineage

    e.do_regenerate("theme")

    assert cell.value == lin.parent_yearly_value
    assert cell.cell_state is CellState.FILLED
    siblings_unchanged(before, e.snapshot_all(), cell.item_id.value)
    lineage_unchanged(e.plan, lin)


def test_theme_regenerate_same_value_is_success():
    """재파생 결과가 같아도 성공이다."""
    e = Editing()
    cell = e.plan.section("theme").items[0]
    original = cell.value

    result = e.do_regenerate("theme")

    assert cell.value == original
    assert result.plan.status is PlanStatus.DRAFT
    assert e.extra_saves == 1
    assert cell.audit.events[-1].event_type is AuditEventType.REGENERATED


def test_regenerate_keeps_address_and_identity():
    e = Editing()
    cell = e.plan.section("theme").items[0]
    item_id, key, week = cell.item_id, cell.semantic_key, cell.week_id

    e.do_regenerate("theme")

    assert cell.item_id == item_id
    assert cell.semantic_key == key
    assert cell.week_id is None and week is None


def test_regenerate_preserves_parent_anchor():
    e = Editing()
    anchor_before = e.plan.parent_lineage.parent_yearly_theme_id

    e.do_regenerate("theme")

    cell = e.plan.section("theme").items[0]
    theme_ev = cell.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0]
    assert theme_ev.source_id == anchor_before
    assert e.plan.parent_lineage.parent_yearly_theme_id == anchor_before


def test_regenerate_provenance():
    e = Editing()
    cell = e.plan.section("theme").items[0]
    before_value = cell.value

    e.do_regenerate("theme")

    assert cell.generation.method is GenerationMethod.RULE_ONLY
    assert cell.generation.rule_id == THEME_RULE_ID
    assert cell.generation.rule_version == THEME_RULE_VERSION
    assert cell.evidence_of_type(EvidenceSourceType.PARENT_PLAN)
    assert cell.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)

    event = cell.audit.events[-1]
    assert event.event_type is AuditEventType.REGENERATED
    assert event.actor_id == TEACHER
    assert event.previous_value == before_value
    assert event.new_value == cell.value


def test_regenerate_constraint_assessments_unchanged():
    e = Editing()
    before = e.plan.constraint_assessments
    e.do_regenerate("theme")
    assert e.plan.constraint_assessments == before


# ---------------------------------------- Regenerate 차단


@pytest.mark.parametrize(
    "section_key,week_id",
    [("outdoor_play", "2026-09-W1"), ("safety_education", "2026-09-W1")],
)
def test_regenerate_blocked_sections(section_key: str, week_id: str):
    e = Editing()
    before = e.snapshot_all()

    with pytest.raises(PlanningError) as exc:
        e.do_regenerate(section_key, week_id=week_id)

    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert exc.value.violated_rule == "regenerate_requires_resolved_candidate_source"
    assert e.snapshot_all() == before
    assert e.extra_saves == 0


def test_outdoor_block_reason_mentions_activity_reference():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_regenerate("outdoor_play", week_id="2026-09-W1")
    assert "Activity Reference" in str(exc.value)


def test_safety_block_reason_mentions_placement_source():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_regenerate("safety_education", week_id="2026-09-W1")
    detail = str(exc.value)
    assert "배치 source" in detail
    assert "임의 배치와 LLM 생성을 하지 않는다" in detail


def test_regenerate_blocked_does_not_return_empty_success():
    """차단은 예외이며 빈 값을 성공처럼 반환하지 않는다."""
    e = Editing()
    cell = e.plan.section("safety_education").items[0]
    with pytest.raises(PlanningError):
        e.do_regenerate("safety_education", week_id="2026-09-W1")
    assert cell.value == ""
    assert cell.cell_state is CellState.EMPTY_UNRESOLVED
    assert len(cell.audit.events) == 1


def test_regenerate_rejects_invalid_address():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_regenerate("theme", week_id="2026-09-W1")
    assert exc.value.violated_rule == "merged_section_address_must_omit_week_id"
    assert e.extra_saves == 0


def test_regenerate_rejects_unknown_section():
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_regenerate("habits")
    assert exc.value.violated_rule == "cell_address_section_must_exist"


@pytest.mark.parametrize("bad_actor", [None, "teacher_dev_001"])
def test_regenerate_requires_opaque_actor(bad_actor):
    e = Editing()
    with pytest.raises(PlanningError) as exc:
        e.do_regenerate("theme", actor=bad_actor)
    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert e.extra_saves == 0


def test_regenerate_does_not_call_llm():
    import inspect

    params = inspect.signature(RegenerateMonthlyPlanItem.__init__).parameters
    assert "llm" not in params
    src = inspect.getsource(RegenerateMonthlyPlanItem)
    assert "polish" not in src


# ================================================ 불변성 종합


def test_edit_does_not_touch_template_ref_or_week_periods():
    e = Editing()
    template_ref = e.plan.template_ref
    weeks = e.plan.week_periods
    e.do_edit("theme", "값")
    assert e.plan.template_ref == template_ref
    assert e.plan.week_periods == weeks


def test_failed_validation_rolls_back_mutation(monkeypatch):
    """검증 실패 시 in-memory Plan에 변경이 남지 않는다."""
    import ssuksak.planning.application.edit_monthly_plan_item as mod

    e = Editing()
    cell = e.plan.section("outdoor_play").items[0]
    before = e.snapshot_all()

    def boom(*_args, **_kwargs):
        raise RuntimeError("검증 실패")

    monkeypatch.setattr(mod, "validate_monthly_plan", boom)
    with pytest.raises(RuntimeError, match="검증 실패"):
        e.do_edit("outdoor_play", "새 값", week_id="2026-09-W1")

    assert cell.value == ""
    assert cell.cell_state is CellState.EMPTY_VALID
    assert e.snapshot_all() == before
    assert e.extra_saves == 0


def test_failed_validation_rolls_back_regenerate(monkeypatch):
    import ssuksak.planning.application.regenerate_monthly_plan_item as mod

    e = Editing()
    e.do_edit("theme", "교사 값")
    cell = e.plan.section("theme").items[0]
    before = e.snapshot_all()

    monkeypatch.setattr(
        mod, "validate_monthly_plan", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("검증 실패")
        )
    )
    with pytest.raises(RuntimeError):
        e.do_regenerate("theme")

    assert cell.value == "교사 값"
    assert e.snapshot_all() == before
    # 앞선 성공 Edit 1회만 저장됐고 실패한 Regenerate는 저장하지 않았다.
    assert e.extra_saves == 1


def test_edit_then_regenerate_sequence_keeps_plan_valid():
    e = Editing()
    e.do_edit("theme", "1차 수정")
    e.do_edit("outdoor_play", "산책", week_id="2026-09-W1")
    e.do_regenerate("theme")

    theme = e.plan.section("theme").items[0]
    outdoor = e.plan.section("outdoor_play").items[0]
    assert theme.value == e.plan.parent_lineage.parent_yearly_value
    assert outdoor.value == "산책"
    assert outdoor.cell_state is CellState.FILLED
    assert e.plan.status is PlanStatus.DRAFT
    assert len(e.plan.items) == 11
