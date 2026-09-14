"""OD-N18 — Week Experience를 `focus` Cell로 저장한다.

2026-09-13 Human Decision:

    기존 Template A v0.1.0은 **수정하지 않는다** (RULE_ONLY 호환용).
    `focus`를 활성화한 v0.2.0을 새로 추가하고 LLM Planner가 명시적으로 고른다.
    `week_axis`는 주차 번호·날짜 축으로 그대로 둔다 (AXIS 의미 불변).

실제 API를 호출하지 않는다. FakeLLM Proposal로 Mapping을 검증한다(§11).
"""

from __future__ import annotations

import pytest

from ssuksak.adapters.monthly_repositories import (
    production_monthly_template_repository,
)
from ssuksak.planning.application.confirm_monthly_plan import (
    ConfirmMonthlyPlan,
    ConfirmMonthlyPlanCommand,
)
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.monthly_dto import (
    EditMonthlyPlanItemCommand,
    MonthlyCellAddress,
)
from ssuksak.planning.domain.constraint import CellState
from ssuksak.planning.domain.errors import PlanningError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_template import SectionRole, TemplateRef
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.rules.monthly_llm_validation import WEEK_ORDER_BASIS
from ssuksak.shared.llm.fake import FakeLLM

from .test_generate_monthly_activity import ACT_SELECTOR, Wiring, repo
from .test_generate_monthly_llm_planner import (
    CANDIDATES,
    RULE_ONLY_TEMPLATE,
    TEMPLATE_ID,
    WEEK_EXPERIENCE_TEMPLATE,
    build_wiring,
    focus_items,
    llm_command,
    outdoor_items,
    proposal_for,
    saved_count,
)
from .test_generate_monthly_plan import command


def llm_plan():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    proposal = proposal_for(builder, wiring)
    fake.set_monthly_proposal(proposal)
    return wiring, wiring.use_case.execute(llm_command()).plan, proposal


# ============================================== Template 계약


def test_the_old_template_is_unchanged_and_still_has_no_focus():
    """v0.1.0은 RULE_ONLY 호환용으로 그대로 보존한다 (§2·§4)."""
    template = production_monthly_template_repository().get_template(
        TEMPLATE_ID, RULE_ONLY_TEMPLATE
    )
    active = {s.section_key for s in template.sections if s.activated}
    assert active == {"theme", "week_axis", "outdoor_play", "safety_education"}


def test_the_new_template_activates_only_focus():
    """`focus` 외 다른 inactive Section을 함께 켜지 않는다 (§3)."""
    repository = production_monthly_template_repository()
    old = repository.get_template(TEMPLATE_ID, RULE_ONLY_TEMPLATE)
    new = repository.get_template(TEMPLATE_ID, WEEK_EXPERIENCE_TEMPLATE)
    old_active = {s.section_key for s in old.sections if s.activated}
    new_active = {s.section_key for s in new.sections if s.activated}
    assert new_active - old_active == {"focus"}
    assert old_active - new_active == set()


def test_week_axis_stays_an_axis():
    """AXIS 의미를 바꾸지 않는다 (§2)."""
    template = production_monthly_template_repository().get_template(
        TEMPLATE_ID, WEEK_EXPERIENCE_TEMPLATE
    )
    week_axis = next(s for s in template.sections if s.section_key == "week_axis")
    focus = next(s for s in template.sections if s.section_key == "focus")
    assert week_axis.role is SectionRole.AXIS
    assert focus.role is SectionRole.CONTENT
    assert focus.display_mode.value == "WEEKLY_CELLS"


def test_both_versions_resolve_exactly_and_there_is_no_fallback():
    repository = production_monthly_template_repository()
    assert repository.get_template(TEMPLATE_ID, RULE_ONLY_TEMPLATE) is not None
    assert repository.get_template(TEMPLATE_ID, WEEK_EXPERIENCE_TEMPLATE) is not None
    assert repository.get_template(TEMPLATE_ID, "monthly-template-a-v9.9.9") is None


# ============================================== RULE_ONLY Freeze


def test_rule_only_on_the_old_template_has_no_focus_section():
    """RULE_ONLY에 빈 focus Cell을 추가하지 않는다 (§4)."""
    wiring = Wiring(activities=repo(*CANDIDATES))
    plan = wiring.use_case.execute(command(activity_catalog=ACT_SELECTOR)).plan
    assert not [s for s in plan.sections if s.section_key == "focus"]


def test_rule_only_on_the_new_template_leaves_focus_empty():
    """새 Template을 RULE_ONLY로 써도 실패하지 않는다. focus는 빈 Cell이다."""
    wiring = Wiring(activities=repo(*CANDIDATES))
    wiring.use_case._templates = production_monthly_template_repository()
    result = wiring.use_case.execute(
        command(
            activity_catalog=ACT_SELECTOR,
            template_ref=TemplateRef(TEMPLATE_ID, WEEK_EXPERIENCE_TEMPLATE),
        )
    )
    focus = focus_items(result.plan)
    assert focus
    assert all(i.cell_state is CellState.EMPTY_VALID for i in focus)
    assert all(i.generation.method is GenerationMethod.RULE_ONLY for i in focus)
    assert all(not i.evidence for i in focus)


# ============================================== Mapping


def test_week_experience_is_mapped_to_focus_cells():
    _, plan, proposal = llm_plan()
    assert [i.value for i in focus_items(plan)] == [
        w.experience for w in proposal.weeks
    ]


def test_focus_cell_count_matches_the_canonical_week_count():
    _, plan, _ = llm_plan()
    active = [w for w in plan.week_periods if w.active]
    assert len(focus_items(plan)) == len(active)
    assert [i.week_id.value for i in focus_items(plan)] == [
        w.week_id.value for w in active
    ]


def test_focus_cells_are_filled():
    _, plan, _ = llm_plan()
    for item in focus_items(plan):
        assert item.cell_state is CellState.FILLED
        assert item.value.strip()


# ============================================== Provenance (§7)


def test_focus_generation_is_rule_llm():
    _, plan, _ = llm_plan()
    for item in focus_items(plan):
        assert item.generation.method is GenerationMethod.RULE_LLM
        assert item.generation.rule_id == "monthly.llm.evidence_grounded_planner"
        assert item.generation.rule_version == "v1"


def test_focus_evidence_is_empty():
    """특정 EvidenceRecord를 이 문장의 직접 근거로 주장하지 않는다."""
    _, plan, _ = llm_plan()
    for item in focus_items(plan):
        assert item.evidence == []


def test_activity_grounding_is_never_copied_into_focus():
    """§7 금지 — Activity의 grounding_refs를 experience 근거로 복사하지 않는다."""
    _, plan, _ = llm_plan()
    outdoor_sources = {e.source_id for i in outdoor_items(plan) for e in i.evidence}
    assert outdoor_sources, "outdoor에는 근거가 있어야 비교가 의미 있다"
    for item in focus_items(plan):
        assert not item.evidence


def test_focus_never_claims_institution_sample():
    _, plan, _ = llm_plan()
    for item in focus_items(plan):
        assert not item.evidence_of_type(EvidenceSourceType.INSTITUTION_SAMPLE)


def test_week_order_basis_is_planner_composed():
    """Corpus에 week_position이 0건이므로 SOURCE_OBSERVED를 쓰지 않는다 (OD-N14)."""
    assert WEEK_ORDER_BASIS == "PLANNER_COMPOSED"


def test_focus_records_a_created_audit_event():
    _, plan, _ = llm_plan()
    for item in focus_items(plan):
        assert item.audit.contains(AuditEventType.CREATED)


# ============================================== Mode / Template 조합 (§5)


def test_llm_planner_with_the_old_template_fails_loudly():
    """Template을 몰래 바꾸지 않는다. 조용한 데이터 손실도 만들지 않는다."""
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    with pytest.raises(PlanningError) as exc:
        wiring.use_case.execute(
            llm_command(template_ref=TemplateRef(TEMPLATE_ID, RULE_ONLY_TEMPLATE))
        )
    assert "llm_planner_mode_requires_a_week_experience_section" in str(exc.value)
    assert saved_count(wiring) == 0


def test_the_incompatible_combination_never_calls_the_llm():
    """Template이 맞지 않으면 호출 전에 막는다. 비용을 쓰지 않는다."""
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))
    before = fake.monthly_call_count

    with pytest.raises(PlanningError):
        wiring.use_case.execute(
            llm_command(template_ref=TemplateRef(TEMPLATE_ID, RULE_ONLY_TEMPLATE))
        )
    assert fake.monthly_call_count == before


# ============================================== Teacher Edit / Confirm (§8)


def test_teacher_can_edit_a_focus_cell():
    wiring, plan, _ = llm_plan()
    target = focus_items(plan)[0]
    result = EditMonthlyPlanItem(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        clock=wiring.use_case._clock,
    ).execute(
        EditMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=MonthlyCellAddress(
                target_month=plan.target_month.value,
                section_key="focus",
                week_id=target.week_id.value,
            ),
            new_value="교사가 고친 주간 경험",
            actor_id=ActorId("teacher_001"),
        )
    )
    edited = next(i for i in focus_items(result.plan) if i.item_id == target.item_id)
    assert edited.value == "교사가 고친 주간 경험"
    assert edited.audit.contains(AuditEventType.TEACHER_EDITED)


def test_confirmed_focus_cell_is_read_only():
    wiring, plan, _ = llm_plan()
    ConfirmMonthlyPlan(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        safety_rule_repository=wiring.use_case._safety_rules,
        clock=wiring.use_case._clock,
    ).execute(
        ConfirmMonthlyPlanCommand(
            plan_id=plan.plan_id.value, actor_id=ActorId("teacher_001")
        )
    )
    with pytest.raises(PlanningError):
        EditMonthlyPlanItem(
            monthly_plan_repository=wiring.use_case._monthly,
            template_repository=wiring.use_case._templates,
            clock=wiring.use_case._clock,
        ).execute(
            EditMonthlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=MonthlyCellAddress(
                    target_month=plan.target_month.value,
                    section_key="focus",
                    week_id=focus_items(plan)[0].week_id.value,
                ),
                new_value="확정 후 수정",
                actor_id=ActorId("teacher_001"),
            )
        )


# ============================================== Persistence


def test_focus_survives_a_repository_round_trip():
    wiring, plan, proposal = llm_plan()
    stored = wiring.use_case._monthly.get(plan.plan_id.value)
    assert [i.value for i in focus_items(stored)] == [
        w.experience for w in proposal.weeks
    ]
    assert all(i.evidence == [] for i in focus_items(stored))
    assert all(
        i.generation.method is GenerationMethod.RULE_LLM for i in focus_items(stored)
    )
