"""Yearly Slice Application 테스트.

Golden Set이 다루지 않는 경로를 보강한다. 특히 2026-09-10 결정 4의
"다른 후보가 없다면 기존 theme_id 유지" 분기는 Golden Set에 없다
(case 16이 후보 2개인 2026-10을 쓰기 때문).
"""

from __future__ import annotations

import pytest

from ssuksak.planning.application.dto import (
    AgeMode,
    ClassroomContext,
    ConfirmYearlyPlanCommand,
    DaycareContext,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
    ItemAddress,
    PlanningSetup,
    RegenerateYearlyPlanItemCommand,
    yearly_plan_to_contract_dict,
)
from ssuksak.planning.domain.errors import FailureCategory, Outcome, PlanningError
from ssuksak.planning.domain.identifiers import ActorId, InvalidIdentifierError
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType, EvidenceSourceType
from ssuksak.planning.domain.theme_reference import ActivationStatus

from tests.golden import harness as H

ACTOR = ActorId("user_fixture_teacher_001")


def _command(hn: H.Harness, *, ages=frozenset({3}), classroom_ref="c1", age_mode=None):
    return GenerateYearlyPlanCommand(
        school_year=2026,
        daycare=DaycareContext(daycare_ref="d1", region_ref="region_fixture_seoul"),
        classroom=ClassroomContext(
            classroom_ref=classroom_ref,
            ages=ages,
            teacher_name="테스트담임",
            age_mode=age_mode,
        ),
        planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
        catalog=hn.selector,
    )


def _generate(hn: H.Harness, **kwargs):
    return hn.generate().execute(_command(hn, **kwargs))


# ------------------------------------------------------------ 생성 기본


def test_generate_produces_draft_with_twelve_ordered_periods():
    hn = H.make_harness()
    result = _generate(hn)

    assert result.plan.status is PlanStatus.DRAFT
    assert [mp.period_key.value for mp in result.plan.month_periods] == [
        "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08",
        "2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02",
    ]


def test_generate_is_reproducible_for_same_input():
    a = H.make_harness()
    b = H.make_harness()
    ra = _generate(a)
    rb = _generate(b)

    assert H.theme_ids_of(ra.plan) == H.theme_ids_of(rb.plan)
    assert [mp.theme.value for mp in ra.plan.month_periods] == [
        mp.theme.value for mp in rb.plan.month_periods
    ]


def test_contract_dict_excludes_derived_academic_index():
    """academic_index는 derived helper이므로 Contract 직렬화에 없어야 한다."""
    hn = H.make_harness()
    payload = yearly_plan_to_contract_dict(_generate(hn).plan)

    assert set(payload) == {"school_year", "classroom_ref", "status", "month_periods"}
    for period in payload["month_periods"]:
        assert set(period) == {"period_key", "theme"}
        assert set(period["theme"]) == {"item_id", "semantic_key", "value"}
        assert "academic_index" not in period


def test_generation_run_records_selection_reason_and_rule():
    hn = H.make_harness()
    run = _generate(hn).run

    assert len(run.selection_traces) == 12
    for trace in run.selection_traces:
        assert trace.rule_id == "yearly.theme.sample_derived_candidate_selection"
        assert trace.rule_version == "v2"
        assert trace.reason
        assert trace.selected_theme_id


def test_generation_method_detail_carries_selection_reason():
    hn = H.make_harness()
    plan = _generate(hn).plan

    for mp in plan.month_periods:
        assert mp.theme.generation.selection_reason


# ------------------------------------------------------------ Gate 경로


def test_setup_incomplete_blocks_before_llm_and_persistence():
    hn = H.make_harness()
    command = GenerateYearlyPlanCommand(
        school_year=2026,
        daycare=DaycareContext(daycare_ref="d1"),
        classroom=ClassroomContext(classroom_ref="c1", ages=frozenset({3})),
        planning_setup=PlanningSetup(completed=False),
        catalog=hn.selector,
    )
    with pytest.raises(PlanningError) as exc:
        hn.generate().execute(command)

    assert exc.value.outcome is Outcome.BLOCKED
    assert not hn.llm.was_called
    assert hn.plans.save_count == 0


def test_pending_catalog_blocks_generation_end_to_end():
    hn = H.make_harness(activation=ActivationStatus.PENDING_HUMAN_REVIEW)

    with pytest.raises(PlanningError) as exc:
        _generate(hn)

    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert not hn.llm.was_called
    assert hn.plans.save_count == 0


def test_empty_age_set_is_rejected():
    hn = H.make_harness()
    with pytest.raises(PlanningError) as exc:
        _generate(hn, ages=frozenset())

    assert exc.value.failure_category is FailureCategory.INPUT_VALIDATION


def test_explicit_mixed_mode_with_single_age_is_rejected():
    hn = H.make_harness()
    with pytest.raises(PlanningError) as exc:
        _generate(hn, ages=frozenset({4}), age_mode=AgeMode.MIXED)

    assert exc.value.violated_rule == (
        "mixed_age_requires_at_least_two_distinct_supported_ages"
    )


def test_age_mode_is_derived_when_not_supplied():
    single = ClassroomContext(classroom_ref="c", ages=frozenset({3}))
    mixed = ClassroomContext(classroom_ref="c", ages=frozenset({3, 4}))

    assert single.effective_age_mode is AgeMode.SINGLE
    assert mixed.effective_age_mode is AgeMode.MIXED


# ------------------------------------------- 혼합연령 classroom 단일 Plan


def test_mixed_age_classroom_gets_exactly_one_plan():
    hn = H.make_harness()
    result = _generate(hn, ages=frozenset({3, 4}))

    assert hn.plans.stored_count == 1
    assert result.plan.classroom_ages == frozenset({3, 4})


def test_mixed_age_themes_support_every_selected_age():
    hn = H.make_harness()
    result = _generate(hn, ages=frozenset({3, 4, 5}))

    for _mp, ref in [
        (mp, mp.theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0])
        for mp in result.plan.month_periods
    ]:
        candidate = hn.catalog.get(ref.source_id)
        assert {3, 4, 5}.issubset(set(candidate.supported_ages))


# ------------------------------------------- Optional Dependency Fallback


def test_trend_timeout_does_not_fail_core_and_is_recorded():
    hn = H.make_harness(optional_outcomes={"trend": "TIMEOUT"})
    command = GenerateYearlyPlanCommand(
        school_year=2026,
        daycare=DaycareContext(daycare_ref="d1"),
        classroom=ClassroomContext(classroom_ref="c1", ages=frozenset({5})),
        planning_setup=PlanningSetup(completed=True),
        catalog=hn.selector,
        optional_context_requested={"trend": {"result": "TIMEOUT"}},
    )
    result = hn.generate().execute(command)

    assert len(result.plan.month_periods) == 12
    assert result.run.used_fallback
    assert any("trend" in f for f in result.run.fallbacks_used)
    # TREND Evidence는 붙지 않는다.
    assert not any(
        ev.source_type is EvidenceSourceType.TREND
        for item in result.plan.items
        for ev in item.evidence
    )


def test_optional_provider_raising_does_not_break_core():
    """Provider가 규약을 어기고 예외를 던져도 Core는 성공해야 한다."""

    class ExplodingProvider:
        def fetch(self, requested):
            raise RuntimeError("외부 API 폭발")

    hn = H.make_harness()
    hn.optional_context = ExplodingProvider()

    command = GenerateYearlyPlanCommand(
        school_year=2026,
        daycare=DaycareContext(daycare_ref="d1"),
        classroom=ClassroomContext(classroom_ref="c1", ages=frozenset({3})),
        planning_setup=PlanningSetup(completed=True),
        catalog=hn.selector,
        optional_context_requested={"trend": {}},
    )
    result = hn.generate().execute(command)

    assert len(result.plan.month_periods) == 12
    assert result.run.used_fallback


# ------------------------------------------------------------ Regenerate


def test_regenerate_keeps_theme_id_when_no_other_candidate_exists():
    """결정 4의 두 번째 분기. Golden Set에는 없는 경로다.

    2026-05는 eligible 후보가 1개이므로 theme_id와 Evidence가 유지되고
    LLM이 표현만 다시 만든다. 값이 반드시 달라져야 한다는 Contract는 없다.
    """
    hn = H.make_harness()
    result = _generate(hn)
    plan = result.plan

    found = plan.find_item(period_key="2026-05", semantic_key="yearly.month.05.theme")
    assert found is not None
    _mp, item = found

    eligible = hn.catalog.eligible_candidates(5, plan.classroom_ages)
    assert len(eligible) == 1, "이 테스트는 후보가 1개인 달을 전제로 한다"

    before_theme_id = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0].source_id
    before_item_id = item.item_id.value
    before_semantic = item.semantic_key.value
    before_audit_len = len(item.audit)

    regen = hn.regenerate().execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(
                period_key="2026-05", semantic_key="yearly.month.05.theme"
            ),
            actor_id=ACTOR,
            catalog=hn.selector,
        )
    )

    after = regen.plan.find_item(item_id=before_item_id)
    assert after is not None
    _mp2, after_item = after

    after_theme_id = after_item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[
        0
    ].source_id

    assert after_theme_id == before_theme_id, "대체 후보가 없으면 theme_id를 유지한다"
    assert after_item.item_id.value == before_item_id
    assert after_item.semantic_key.value == before_semantic
    assert after_item.audit.contains(AuditEventType.REGENERATED)
    assert len(after_item.audit) == before_audit_len + 1
    assert regen.plan.status is PlanStatus.DRAFT


def test_regenerate_does_not_require_value_to_change():
    """Regenerate가 반드시 값을 바꿔야 한다는 Contract로 만들지 않았다."""
    from ssuksak.shared.llm.fake import FakeLLMMode

    hn = H.make_harness(llm_mode=FakeLLMMode.ECHO_LABEL)
    result = _generate(hn)
    plan = result.plan

    found = plan.find_item(period_key="2026-05", semantic_key="yearly.month.05.theme")
    before_value = found[1].value

    regen = hn.regenerate().execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(
                period_key="2026-05", semantic_key="yearly.month.05.theme"
            ),
            actor_id=ACTOR,
            catalog=hn.selector,
        )
    )
    after_value = regen.plan.find_item(item_id=found[1].item_id.value)[1].value

    # 동일해도 성공이며 REGENERATED Audit이 남는다.
    assert after_value == before_value
    assert regen.plan.find_item(item_id=found[1].item_id.value)[1].audit.contains(
        AuditEventType.REGENERATED
    )


def test_regenerate_preserves_event_evidence_on_the_item():
    """Theme Evidence만 교체하고 EVENT Evidence는 보존한다."""
    from ssuksak.planning.application.dto import EventInput

    hn = H.make_harness()
    command = GenerateYearlyPlanCommand(
        school_year=2026,
        daycare=DaycareContext(daycare_ref="d1"),
        classroom=ClassroomContext(classroom_ref="c1", ages=frozenset({4})),
        planning_setup=PlanningSetup(completed=True),
        catalog=hn.selector,
        events=(
            EventInput(
                event_id="event_fixture_autumn_forest_2026",
                label="가을 숲 체험",
                starts_on="2026-10-16",
            ),
        ),
    )
    plan = hn.generate().execute(command).plan

    found = plan.find_item(period_key="2026-10", semantic_key="yearly.month.10.theme")
    assert any(
        e.source_type is EvidenceSourceType.EVENT for e in found[1].evidence
    )

    regen = hn.regenerate().execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(
                period_key="2026-10", semantic_key="yearly.month.10.theme"
            ),
            actor_id=ACTOR,
            catalog=hn.selector,
        )
    )
    after = regen.plan.find_item(item_id=found[1].item_id.value)[1]

    assert any(e.source_type is EvidenceSourceType.EVENT for e in after.evidence)
    assert any(
        e.source_type is EvidenceSourceType.THEME_REFERENCE for e in after.evidence
    )


def test_regenerate_on_unknown_item_is_rejected():
    hn = H.make_harness()
    plan = _generate(hn).plan

    with pytest.raises(PlanningError) as exc:
        hn.regenerate().execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(item_id="does_not_exist"),
                actor_id=ACTOR,
                catalog=hn.selector,
            )
        )
    assert exc.value.failure_category is FailureCategory.INPUT_VALIDATION


# ------------------------------------------------------------------ Edit


def test_edit_preserves_evidence_and_generation_method():
    hn = H.make_harness()
    plan = _generate(hn).plan

    found = plan.find_item(period_key="2026-05", semantic_key="yearly.month.05.theme")
    item = found[1]
    before_evidence = [(e.source_type, e.source_id) for e in item.evidence]
    before_method = item.generation.method

    hn.edit().execute(
        EditYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(
                period_key="2026-05", semantic_key="yearly.month.05.theme"
            ),
            new_value="소중한 나와 가족",
            actor_id=ACTOR,
        )
    )

    assert [(e.source_type, e.source_id) for e in item.evidence] == before_evidence
    assert item.generation.method is before_method, "교사 편집이 Method를 덮어썼다"
    assert item.value == "소중한 나와 가족"
    assert item.audit.contains(AuditEventType.TEACHER_EDITED)


def test_edit_rejects_blank_value():
    hn = H.make_harness()
    plan = _generate(hn).plan

    with pytest.raises(PlanningError) as exc:
        hn.edit().execute(
            EditYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key="2026-05", semantic_key="yearly.month.05.theme"
                ),
                new_value="   ",
                actor_id=ACTOR,
            )
        )
    assert exc.value.failure_category is FailureCategory.REQUIRED_VALUE_VALIDATION


def test_edit_by_item_id_address_works():
    hn = H.make_harness()
    plan = _generate(hn).plan
    item_id = plan.month_periods[0].theme.item_id.value

    hn.edit().execute(
        EditYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(item_id=item_id),
            new_value="새 값",
            actor_id=ACTOR,
        )
    )
    assert plan.find_item(item_id=item_id)[1].value == "새 값"


def test_item_address_requires_a_stable_address():
    with pytest.raises(ValueError):
        ItemAddress()
    with pytest.raises(ValueError):
        ItemAddress(period_key="2026-05")


# --------------------------------------------------------------- Confirm


def test_confirm_requires_opaque_actor_and_keeps_draft_on_failure():
    hn = H.make_harness()
    plan = _generate(hn).plan

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value, actor_id=None, catalog=hn.selector
            )
        )

    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert hn.plans.get(plan.plan_id.value).status is PlanStatus.DRAFT


def test_teacher_display_name_cannot_be_used_as_actor_id():
    """ActorId는 별도 타입이며 원시 문자열을 런타임에서도 거부한다."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value,
                actor_id="테스트담임",  # type: ignore[arg-type]
                catalog=hn.selector,
            )
        )

    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert exc.value.violated_rule == "confirm_requires_opaque_actor_id"
    assert hn.plans.get(plan.plan_id.value).status is PlanStatus.DRAFT


def test_audit_event_rejects_raw_string_actor():
    """방어 심층화: Audit 계층에서도 원시 문자열 actor를 막는다."""
    from datetime import UTC, datetime

    from ssuksak.planning.domain.provenance import AuditEvent

    with pytest.raises(TypeError, match="ActorId"):
        AuditEvent(
            event_type=AuditEventType.CONFIRMED,
            occurred_at=datetime(2026, 9, 10, tzinfo=UTC),
            plan_id="p1",
            actor_id="테스트담임",  # type: ignore[arg-type]
        )


def test_actor_id_rejects_blank():
    for bad in ("", "   "):
        with pytest.raises(InvalidIdentifierError):
            ActorId(bad)


def test_confirm_records_actor_and_time_then_locks_plan():
    hn = H.make_harness()
    plan = _generate(hn).plan

    confirmed = hn.confirm().execute(
        ConfirmYearlyPlanCommand(
            plan_id=plan.plan_id.value, actor_id=ACTOR, catalog=hn.selector
        )
    ).plan

    assert confirmed.status is PlanStatus.CONFIRMED
    events = [e for e in confirmed.audit if e.event_type is AuditEventType.CONFIRMED]
    assert len(events) == 1
    assert str(events[0].actor_id) == "user_fixture_teacher_001"
    assert events[0].occurred_at is not None

    with pytest.raises(PlanningError):
        confirmed.ensure_mutable("probe")


def test_confirm_twice_is_rejected():
    hn = H.make_harness()
    plan = _generate(hn).plan
    cmd = ConfirmYearlyPlanCommand(
        plan_id=plan.plan_id.value, actor_id=ACTOR, catalog=hn.selector
    )
    hn.confirm().execute(cmd)

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(cmd)
    assert exc.value.failure_category is FailureCategory.PLAN_STATE_GATE


def test_no_submit_or_send_capability_exists():
    """Confirm은 자동 제출·발송이 아니다. 그런 기능이 존재하지 않는다."""
    hn = H.make_harness()
    confirm = hn.confirm()

    for forbidden in ("submit", "send", "dispatch", "export_to_authority", "notify"):
        assert not hasattr(confirm, forbidden)
        assert not hasattr(hn.plans, forbidden)


# ------------------------------------------------------- 하위 단계 Gate


def test_monthly_gate_blocks_on_draft_and_allows_after_confirm():
    hn = H.make_harness()
    plan = _generate(hn).plan
    gate = hn.monthly_gate()

    with pytest.raises(PlanningError) as exc:
        gate.ensure_can_generate_monthly(plan.classroom_ref, plan.school_year)
    assert exc.value.failure_category is FailureCategory.CONFIRMATION_GATE

    hn.confirm().execute(
        ConfirmYearlyPlanCommand(
            plan_id=plan.plan_id.value, actor_id=ACTOR, catalog=hn.selector
        )
    )
    parent = gate.ensure_can_generate_monthly(plan.classroom_ref, plan.school_year)
    assert parent.status is PlanStatus.CONFIRMED


def test_monthly_gate_blocks_when_no_yearly_plan_exists():
    hn = H.make_harness()
    with pytest.raises(PlanningError) as exc:
        hn.monthly_gate().ensure_can_generate_monthly("missing_classroom", 2026)
    assert exc.value.failure_category is FailureCategory.CONFIRMATION_GATE
