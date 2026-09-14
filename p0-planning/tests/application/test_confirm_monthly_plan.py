"""ConfirmMonthlyPlan / require_confirmed_parent_monthly 검증.

핵심 Product Contract:

    status = CONFIRMED  = 교사가 작성 결과를 확정했다
                       != 법정 안전교육 충족 / Safety 검증 완료 / 법률 준수 판정

따라서 `CONFIRMED`와 `NOT_VERIFIED_SOURCE_REQUIRED`가 동시에 존재할 수 있고,
Confirm은 `ConstraintAssessment`를 절대 바꾸지 않는다.
"""

from __future__ import annotations

import pytest

from ssuksak.adapters.deterministic import FixedClock
from ssuksak.adapters.monthly_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.monthly_dto import ConfirmMonthlyPlanCommand
from ssuksak.planning.domain.constraint import (
    CellState,
    ConstraintKind,
    ConstraintVerification,
)
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType
from ssuksak.planning.rules import gates

from .test_generate_monthly_plan import NOW, Wiring, build_parent, command
from .test_monthly_edit_regenerate import Editing, TEACHER


class Confirming(Editing):
    """Edit/Regenerate 조립에 Confirm을 더한다."""

    def __init__(
        self,
        *,
        template_approval: str | None = None,
        safety_approval: str | None = None,
        **kw,
    ) -> None:
        super().__init__(**kw)
        self.confirm = ConfirmMonthlyPlan(
            monthly_plan_repository=self.w.monthly,
            template_repository=JsonMonthlyTemplateRepository(
                approval_override=template_approval
            ),
            safety_rule_repository=JsonSafetyLegalRuleRepository(
                approval_override=safety_approval
            ),
            clock=FixedClock(NOW, advance_seconds=1),
        )

    def do_confirm(self, actor=TEACHER, plan_id: str | None = None):
        return self.confirm.execute(
            ConfirmMonthlyPlanCommand(
                plan_id=plan_id or self.plan.plan_id.value, actor_id=actor
            )
        )

    def plan_snapshot(self) -> tuple:
        return (
            self.plan.parent_lineage,
            self.plan.template_ref,
            tuple(w.week_id.value for w in self.plan.week_periods),
            self.plan.constraint_assessments,
            tuple(s.section_key for s in self.plan.sections),
            len(self.plan.audit.events),
        )


def fill_all_safety(c: Confirming) -> None:
    for week in c.plan.week_periods:
        c.do_edit(
            "safety_education", f"{week.display_label} 안전교육", week_id=week.week_id.value
        )


# ==================================================== 성공 경로


def test_draft_to_confirmed():
    c = Confirming()
    assert c.plan.status is PlanStatus.DRAFT
    saves = c.extra_saves

    result = c.do_confirm()

    assert result.plan is c.plan
    assert c.plan.status is PlanStatus.CONFIRMED
    assert c.extra_saves == saves + 1


def test_confirm_appends_plan_level_audit():
    c = Confirming()
    before = len(c.plan.audit.events)

    c.do_confirm()

    assert len(c.plan.audit.events) == before + 1
    event = c.plan.audit.events[-1]
    assert event.event_type is AuditEventType.CONFIRMED
    assert event.actor_id == TEACHER
    assert event.plan_id == c.plan.plan_id.value
    assert event.occurred_at is not None


def test_confirm_uses_clock_port_not_wall_clock():
    c = Confirming()
    c.do_confirm()
    # FixedClock 기반이므로 실제 시각이 아니라 주입된 시각을 쓴다.
    assert c.plan.audit.events[-1].occurred_at.year == NOW.year
    assert c.plan.audit.events[-1].occurred_at.tzinfo is not None


def test_confirm_does_not_add_cell_level_audit():
    c = Confirming()
    before = {i.item_id.value: len(i.audit.events) for i in c.plan.items}
    c.do_confirm()
    after = {i.item_id.value: len(i.audit.events) for i in c.plan.items}
    assert after == before


def test_confirm_is_not_a_content_transformation():
    """Confirm이 바꾸는 것은 status와 Plan-level Audit뿐이다."""
    c = Confirming()
    cells_before = c.snapshot_all()
    lineage = c.plan.parent_lineage
    template_ref = c.plan.template_ref
    weeks = c.plan.week_periods
    constraints = c.plan.constraint_assessments
    sections = [s.section_key for s in c.plan.sections]

    c.do_confirm()

    assert c.snapshot_all() == cells_before
    assert c.plan.parent_lineage == lineage
    assert c.plan.parent_lineage.parent_yearly_theme_id == lineage.parent_yearly_theme_id
    assert c.plan.template_ref == template_ref
    assert c.plan.week_periods == weeks
    assert c.plan.constraint_assessments == constraints
    assert [s.section_key for s in c.plan.sections] == sections


# ------------------------------------------ Safety unresolved


def test_confirm_succeeds_with_unresolved_safety():
    c = Confirming()
    assessment = c.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert assessment.verification is (
        ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    )
    assert all(
        i.cell_state is CellState.EMPTY_UNRESOLVED
        for i in c.plan.section("safety_education").items
    )

    c.do_confirm()

    assert c.plan.status is PlanStatus.CONFIRMED
    after = c.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert after is assessment
    assert after.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED


def test_confirmed_and_unresolved_coexist():
    """status = CONFIRMED != Safety verified."""
    c = Confirming()
    c.do_confirm()
    assert c.plan.status is PlanStatus.CONFIRMED
    assert len(c.plan.unresolved_constraints) == 1


def test_confirm_with_all_safety_cells_filled_keeps_constraint_unresolved():
    """Cell content completeness와 Safety source verification은 분리된다."""
    c = Confirming()
    fill_all_safety(c)

    safety = c.plan.section("safety_education")
    assert all(i.cell_state is CellState.FILLED for i in safety.items)
    assert all(i.value for i in safety.items)

    before = c.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    c.do_confirm()

    assert c.plan.status is PlanStatus.CONFIRMED
    after = c.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION)
    assert after is before
    assert after.verification is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    assert after.required_source_kinds == (
        "INSTITUTION_ANNUAL_SAFETY_PLAN",
        "TEACHER_INPUT",
    )


def test_confirm_never_sets_verified():
    """Confirm이 Constraint를 VERIFIED로 바꾸면 실패다."""
    for prep in (lambda c: None, fill_all_safety):
        c = Confirming()
        prep(c)
        c.do_confirm()
        assert (
            c.plan.constraint(ConstraintKind.STATUTORY_SAFETY_EDUCATION).verification
            is not ConstraintVerification.VERIFIED
        )


def test_confirm_succeeds_with_empty_valid_outdoor():
    c = Confirming()
    assert all(
        i.cell_state is CellState.EMPTY_VALID
        for i in c.plan.section("outdoor_play").items
    )
    c.do_confirm()
    assert c.plan.status is PlanStatus.CONFIRMED


# ------------------------------------------------- 실패 경로


def test_already_confirmed_is_blocked():
    c = Confirming()
    c.do_confirm()
    saves = c.extra_saves
    audit_len = len(c.plan.audit.events)
    cells = c.snapshot_all()
    constraints = c.plan.constraint_assessments

    with pytest.raises(PlanningError) as exc:
        c.do_confirm()

    assert exc.value.failure_category is FailureCategory.PLAN_STATE_GATE
    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"
    assert c.plan.status is PlanStatus.CONFIRMED
    assert len(c.plan.audit.events) == audit_len
    assert c.snapshot_all() == cells
    assert c.plan.constraint_assessments is constraints
    assert c.extra_saves == saves


@pytest.mark.parametrize("bad_actor", [None, "teacher_dev_001", ""])
def test_invalid_actor_is_blocked(bad_actor):
    c = Confirming()
    before = c.plan_snapshot()
    cells = c.snapshot_all()
    saves = c.extra_saves

    with pytest.raises((PlanningError, ValueError)) as exc:
        c.do_confirm(actor=ActorId(bad_actor) if bad_actor == "" else bad_actor)

    if isinstance(exc.value, PlanningError):
        assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert c.plan.status is PlanStatus.DRAFT
    assert c.plan_snapshot() == before
    assert c.snapshot_all() == cells
    assert c.extra_saves == saves


def test_missing_plan_is_blocked():
    c = Confirming()
    with pytest.raises(PlanningError) as exc:
        c.do_confirm(plan_id="no_such_plan")
    assert exc.value.violated_rule == "target_monthly_plan_must_exist"


# ------------------------------- Reference invalidation


def test_template_unapproved_at_confirm_is_blocked():
    c = Confirming(template_approval="PENDING_HUMAN_REVIEW")
    before = c.plan_snapshot()
    saves = c.extra_saves

    with pytest.raises(PlanningError) as exc:
        c.do_confirm()

    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert exc.value.violated_rule == (
        "only_human_approved_template_instance_is_eligible"
    )
    assert c.plan.status is PlanStatus.DRAFT
    assert c.plan_snapshot() == before
    assert c.extra_saves == saves


def test_safety_rule_unapproved_at_confirm_is_blocked():
    c = Confirming(safety_approval="PENDING_HUMAN_REVIEW")
    before = c.plan_snapshot()

    with pytest.raises(PlanningError) as exc:
        c.do_confirm()

    assert exc.value.violated_rule == (
        "only_human_approved_safety_legal_rule_is_eligible"
    )
    assert c.plan.status is PlanStatus.DRAFT
    assert c.plan_snapshot() == before


def test_template_missing_at_confirm_is_blocked():
    class Missing:
        def get_template(self, *_a):
            return None

    c = Confirming()
    c.confirm = ConfirmMonthlyPlan(
        monthly_plan_repository=c.w.monthly,
        template_repository=Missing(),
        safety_rule_repository=JsonSafetyLegalRuleRepository(),
        clock=FixedClock(NOW),
    )
    with pytest.raises(PlanningError) as exc:
        c.do_confirm()
    assert exc.value.violated_rule == "template_id_and_version_must_resolve_exactly"
    assert c.plan.status is PlanStatus.DRAFT


def test_safety_rule_missing_at_confirm_is_blocked():
    class Missing:
        def get_legal_rule(self, *_a):
            return None

    c = Confirming()
    c.confirm = ConfirmMonthlyPlan(
        monthly_plan_repository=c.w.monthly,
        template_repository=JsonMonthlyTemplateRepository(),
        safety_rule_repository=Missing(),
        clock=FixedClock(NOW),
    )
    with pytest.raises(PlanningError) as exc:
        c.do_confirm()
    assert exc.value.violated_rule == (
        "safety_legal_rule_version_must_resolve_exactly"
    )
    assert c.plan.status is PlanStatus.DRAFT


def test_confirm_does_not_auto_upgrade_to_latest_version():
    """다른 version을 반환하면 exact mismatch로 차단한다."""
    from ssuksak.planning.domain.monthly_template import TemplateRef

    real = JsonMonthlyTemplateRepository()

    class Drifting:
        def get_template(self, template_id, template_version):
            tpl = real.get_template(template_id, template_version)
            if tpl is None:
                return None
            object.__setattr__(
                tpl, "template_ref", TemplateRef(template_id, "monthly-template-a-v9")
            )
            return tpl

    c = Confirming()
    c.confirm = ConfirmMonthlyPlan(
        monthly_plan_repository=c.w.monthly,
        template_repository=Drifting(),
        safety_rule_repository=JsonSafetyLegalRuleRepository(),
        clock=FixedClock(NOW),
    )
    with pytest.raises(PlanningError) as exc:
        c.do_confirm()
    assert exc.value.violated_rule == "template_id_and_version_must_resolve_exactly"
    assert c.plan.status is PlanStatus.DRAFT


def test_confirm_resolves_exact_versions_from_plan():
    """호출자가 version을 넘기지 않고 Plan이 보존한 값을 쓴다."""
    import dataclasses

    seen = {}
    real_t, real_s = JsonMonthlyTemplateRepository(), JsonSafetyLegalRuleRepository()

    class SpyT:
        def get_template(self, tid, tver):
            seen["template"] = (tid, tver)
            return real_t.get_template(tid, tver)

    class SpyS:
        def get_legal_rule(self, ver):
            seen["safety"] = ver
            return real_s.get_legal_rule(ver)

    c = Confirming()
    c.confirm = ConfirmMonthlyPlan(
        monthly_plan_repository=c.w.monthly,
        template_repository=SpyT(),
        safety_rule_repository=SpyS(),
        clock=FixedClock(NOW),
    )
    c.do_confirm()

    assert seen["template"] == (
        c.plan.template_ref.template_id,
        c.plan.template_ref.template_version,
    )
    assert seen["safety"] == c.plan.constraint(
        ConstraintKind.STATUTORY_SAFETY_EDUCATION
    ).rule_version
    # Command에는 selector가 없다.
    fields = {f.name for f in dataclasses.fields(ConfirmMonthlyPlanCommand)}
    assert fields == {"plan_id", "actor_id"}


# --------------------------------------------- Validation / atomicity


def test_validation_failure_blocks_confirm_and_keeps_draft():
    c = Confirming()
    # theme Cell을 직접 비워 구조를 깨뜨린다(Validator가 잡아야 한다).
    theme = c.plan.section("theme").items[0]
    theme.value = ""
    theme.cell_state = CellState.EMPTY_VALID
    before = c.plan_snapshot()
    saves = c.extra_saves

    with pytest.raises(PlanningError) as exc:
        c.do_confirm()

    assert exc.value.violated_rule == "theme_cell_is_required_and_non_blank"
    assert c.plan.status is PlanStatus.DRAFT
    assert c.plan_snapshot() == before
    assert c.extra_saves == saves


def test_save_failure_rolls_back_status_and_audit():
    c = Confirming()
    audit_before = list(c.plan.audit.events)

    def boom(_plan):
        raise RuntimeError("저장 실패")

    c.w.monthly.save = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="저장 실패"):
        c.do_confirm()

    assert c.plan.status is PlanStatus.DRAFT
    assert list(c.plan.audit.events) == audit_before


def test_confirm_requires_both_reference_repositories():
    with pytest.raises(ValueError, match="Reference 재검증"):
        ConfirmMonthlyPlan(
            monthly_plan_repository=None,
            template_repository=None,
            safety_rule_repository=JsonSafetyLegalRuleRepository(),
            clock=FixedClock(NOW),
        )


def test_confirm_has_no_llm_dependency():
    import inspect

    params = inspect.signature(ConfirmMonthlyPlan.__init__).parameters
    assert "llm" not in params
    src = inspect.getsource(ConfirmMonthlyPlan)
    assert "polish" not in src and "LLMPort" not in src


# ----------------------------------- Confirm 이후 read-only


def test_edit_after_confirm_is_blocked():
    c = Confirming()
    c.do_confirm()
    cells = c.snapshot_all()
    saves = c.extra_saves

    with pytest.raises(PlanningError) as exc:
        c.do_edit("theme", "확정 후 수정")

    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"
    assert c.snapshot_all() == cells
    assert c.extra_saves == saves


def test_regenerate_after_confirm_is_blocked():
    c = Confirming()
    c.do_confirm()
    cells = c.snapshot_all()

    with pytest.raises(PlanningError) as exc:
        c.do_regenerate("theme")

    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"
    assert c.snapshot_all() == cells


def test_generate_after_confirm_is_still_duplicate_blocked():
    """Confirm 때문에 새 Revision Plan을 만들지 않는다."""
    c = Confirming()
    c.do_confirm()
    stored = c.w.monthly.stored_count

    with pytest.raises(PlanningError) as exc:
        c.w.use_case.execute(command())

    assert exc.value.violated_rule == (
        "monthly_plan_is_unique_per_classroom_and_target_month"
    )
    assert c.w.monthly.stored_count == stored


# ==================================== require_confirmed_parent_monthly


def test_weekly_gate_passes_for_confirmed_monthly():
    c = Confirming()
    c.do_confirm()
    gates.require_confirmed_parent_monthly(c.plan)  # 예외 없음


def test_weekly_gate_passes_even_when_safety_unresolved():
    """CONFIRMED != Safety verified. Constraint 미해결이 Weekly를 막지 않는다."""
    c = Confirming()
    c.do_confirm()
    assert len(c.plan.unresolved_constraints) == 1
    gates.require_confirmed_parent_monthly(c.plan)


def test_weekly_gate_passes_with_empty_cells():
    """outdoor EMPTY_VALID / safety EMPTY_UNRESOLVED여도 통과한다."""
    c = Confirming()
    c.do_confirm()
    empty = [i for i in c.plan.items if i.cell_state is not CellState.FILLED]
    assert len(empty) == 10
    gates.require_confirmed_parent_monthly(c.plan)


def test_weekly_gate_blocks_draft_monthly():
    c = Confirming()
    with pytest.raises(PlanningError) as exc:
        gates.require_confirmed_parent_monthly(c.plan)
    assert exc.value.failure_category is FailureCategory.CONFIRMATION_GATE
    assert exc.value.violated_rule == (
        "weekly_generation_requires_confirmed_monthly_plan"
    )


def test_weekly_gate_blocks_missing_monthly():
    with pytest.raises(PlanningError) as exc:
        gates.require_confirmed_parent_monthly(None)
    assert exc.value.violated_rule == (
        "weekly_generation_requires_confirmed_monthly_plan"
    )


def test_weekly_gate_mirrors_yearly_gate_shape():
    import inspect

    monthly = inspect.signature(gates.require_confirmed_parent_monthly)
    yearly = inspect.signature(gates.require_confirmed_parent_yearly)
    assert len(monthly.parameters) == len(yearly.parameters) == 1
    assert monthly.return_annotation == yearly.return_annotation


def test_yearly_gate_is_unchanged():
    """additive 추가가 기존 Gate 동작을 바꾸지 않았다."""
    parent = build_parent(status=PlanStatus.DRAFT)
    with pytest.raises(PlanningError) as exc:
        gates.require_confirmed_parent_yearly(parent)
    assert exc.value.violated_rule == (
        "monthly_generation_requires_confirmed_yearly_plan"
    )
