"""코드 리뷰 지적 사항에 대한 회귀 테스트.

1. Confirm Reference Validation 우회 금지
2. Edit / Regenerate Actor Validation과 Mutation Atomicity
3. Regenerate 인접 Theme 중복 방지 (9월/10월 양방향)
4. Age Input Validation 보강
"""

from __future__ import annotations

import pytest

from ssuksak.planning.application.confirm_yearly_plan import ConfirmYearlyPlan
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
)
from ssuksak.planning.application.validate_yearly_plan import validate_yearly_plan
from ssuksak.planning.domain.errors import FailureCategory, Outcome, PlanningError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
)

from tests.golden import harness as H

ACTOR = ActorId("user_fixture_teacher_001")
RAW_ACTOR = "테스트담임"  # 담임 표시 이름. ActorId가 아니다.


def _command(hn: H.Harness, *, ages=frozenset({3}), age_mode=None):
    return GenerateYearlyPlanCommand(
        school_year=2026,
        daycare=DaycareContext(daycare_ref="d1"),
        classroom=ClassroomContext(
            classroom_ref="c1", ages=ages, teacher_name=RAW_ACTOR, age_mode=age_mode
        ),
        planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
        catalog=hn.selector,
    )


def _generate(hn: H.Harness, **kwargs):
    return hn.generate().execute(_command(hn, **kwargs))


def _item_state(item):
    """값/Evidence/Method/Audit 상태 스냅샷."""
    return (
        item.value,
        tuple((e.source_type.value, e.source_id, e.source_version) for e in item.evidence),
        item.generation.method.value,
        len(item.audit),
        tuple(e.event_type.value for e in item.audit),
    )


# ==================================================================
# 1. Confirm Reference Validation 우회 금지
# ==================================================================


def test_confirm_fails_when_plan_has_unknown_theme_id():
    """존재하지 않는 theme_id를 가진 Plan은 Confirm에서 걸러진다."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    mp = plan.period("2026-06")
    mp.theme.evidence = [
        EvidenceSource(
            source_type=EvidenceSourceType.THEME_REFERENCE,
            source_id="yr_theme_does_not_exist",
            source_version=hn.catalog.catalog_version,
        )
    ]

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value, actor_id=ACTOR, catalog=hn.selector
            )
        )

    assert exc.value.outcome is Outcome.VALIDATION_FAILED
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert (
        "every_theme_id_must_resolve_in_exact_catalog_version"
        in {v.violated_rule for v in exc.value.violations}
    )

    # 실패 후 DRAFT 유지 + CONFIRMED Audit 미추가
    assert plan.status is PlanStatus.DRAFT
    assert not plan.audit.contains(AuditEventType.CONFIRMED)


def test_confirm_fails_when_plan_has_wrong_source_version():
    """잘못된 source_version을 가진 Plan은 Confirm에서 걸러진다."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    mp = plan.period("2026-04")
    kept = mp.theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0].source_id
    mp.theme.evidence = [
        EvidenceSource(
            source_type=EvidenceSourceType.THEME_REFERENCE,
            source_id=kept,
            source_version="theme-reference-v0.0.0-does-not-exist",
        )
    ]

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value, actor_id=ACTOR, catalog=hn.selector
            )
        )

    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert (
        "theme_id_and_source_version_must_resolve_in_exact_catalog_version"
        in {v.violated_rule for v in exc.value.violations}
    )
    assert plan.status is PlanStatus.DRAFT
    assert not plan.audit.contains(AuditEventType.CONFIRMED)


def test_confirm_fails_when_theme_no_longer_month_eligible():
    """Reference 적합성 검증도 Confirm에서 수행된다."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    # 6월 칸에 6월을 지원하지 않는 Theme을 심는다.
    mp = plan.period("2026-06")
    other = next(t for t in hn.catalog.themes if 6 not in t.applicable_months)
    mp.theme.evidence = [
        EvidenceSource(
            source_type=EvidenceSourceType.THEME_REFERENCE,
            source_id=other.theme_id,
            source_version=hn.catalog.catalog_version,
        )
    ]

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value, actor_id=ACTOR, catalog=hn.selector
            )
        )

    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert plan.status is PlanStatus.DRAFT


def test_confirm_requires_theme_repository_dependency():
    """ThemeReferenceRepository 없이 Confirm을 구성할 수 없다."""
    hn = H.make_harness()
    with pytest.raises(ValueError, match="ThemeReferenceRepository"):
        ConfirmYearlyPlan(
            plan_repository=hn.plans, clock=hn.clock, theme_repository=None
        )


def test_confirm_command_requires_catalog_field():
    """catalog를 생략한 Confirm 명령은 구성 자체가 불가능하다."""
    with pytest.raises(TypeError):
        ConfirmYearlyPlanCommand(plan_id="p1", actor_id=ACTOR)  # type: ignore[call-arg]


def test_confirm_with_none_catalog_is_rejected_not_bypassed():
    """런타임에 catalog=None을 넣어도 Validation을 생략하지 않는다."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value,
                actor_id=ACTOR,
                catalog=None,  # type: ignore[arg-type]
            )
        )

    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert exc.value.violated_rule == (
        "confirm_requires_resolved_theme_reference_catalog"
    )
    assert plan.status is PlanStatus.DRAFT
    assert not plan.audit.contains(AuditEventType.CONFIRMED)


def test_confirm_blocks_on_pending_catalog():
    """Confirm도 HUMAN_APPROVED Gate를 확인한다."""
    from ssuksak.planning.domain.theme_reference import ActivationStatus

    approved = H.make_harness()
    plan = _generate(approved).plan

    pending_catalog = H.build_catalog(
        activation=ActivationStatus.PENDING_HUMAN_REVIEW
    )
    approved.themes = type(approved.themes)([pending_catalog])

    with pytest.raises(PlanningError) as exc:
        approved.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value, actor_id=ACTOR, catalog=approved.selector
            )
        )

    assert exc.value.outcome is Outcome.BLOCKED
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert plan.status is PlanStatus.DRAFT
    assert not plan.audit.contains(AuditEventType.CONFIRMED)


def test_confirm_unresolved_catalog_version_is_rejected():
    hn = H.make_harness()
    plan = _generate(hn).plan

    from ssuksak.planning.application.dto import CatalogSelector

    with pytest.raises(PlanningError) as exc:
        hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=plan.plan_id.value,
                actor_id=ACTOR,
                catalog=CatalogSelector(
                    hn.catalog.catalog_id, "theme-reference-v9.9.9"
                ),
            )
        )

    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert plan.status is PlanStatus.DRAFT


def test_validator_refuses_to_skip_reference_validation_silently():
    """Validator 계층에서도 catalog 생략을 막는다."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    with pytest.raises(ValueError, match="Reference Validation"):
        validate_yearly_plan(plan, catalog=None)

    # 의도적으로 끄려면 명시해야 한다.
    validate_yearly_plan(
        plan, catalog=None, require_theme_reference_evidence=False
    )


# ==================================================================
# 2. Actor Validation과 Mutation Atomicity
# ==================================================================


def test_edit_with_raw_string_actor_leaves_plan_untouched():
    hn = H.make_harness()
    plan = _generate(hn).plan

    found = plan.find_item(period_key="2026-05", semantic_key="yearly.month.05.theme")
    item = found[1]
    before = _item_state(item)
    saves_before = hn.plans.save_count

    with pytest.raises(PlanningError) as exc:
        hn.edit().execute(
            EditYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key="2026-05", semantic_key="yearly.month.05.theme"
                ),
                new_value="이 값은 반영되면 안 된다",
                actor_id=RAW_ACTOR,  # type: ignore[arg-type]
            )
        )

    assert exc.value.outcome is Outcome.VALIDATION_FAILED
    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert exc.value.violated_rule == "edit_requires_opaque_actor_id"

    # 값 / Evidence / Method / Audit 전부 불변
    assert _item_state(item) == before
    assert not item.audit.contains(AuditEventType.TEACHER_EDITED)
    # 저장도 일어나지 않는다
    assert hn.plans.save_count == saves_before


def test_edit_with_none_actor_leaves_plan_untouched():
    hn = H.make_harness()
    plan = _generate(hn).plan
    found = plan.find_item(period_key="2026-05", semantic_key="yearly.month.05.theme")
    before = _item_state(found[1])
    saves_before = hn.plans.save_count

    with pytest.raises(PlanningError) as exc:
        hn.edit().execute(
            EditYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key="2026-05", semantic_key="yearly.month.05.theme"
                ),
                new_value="반영 금지",
                actor_id=None,  # type: ignore[arg-type]
            )
        )

    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert _item_state(found[1]) == before
    assert hn.plans.save_count == saves_before


def test_regenerate_with_raw_string_actor_leaves_plan_untouched_and_skips_llm():
    hn = H.make_harness()
    plan = _generate(hn).plan

    found = plan.find_item(period_key="2026-10", semantic_key="yearly.month.10.theme")
    item = found[1]
    before = _item_state(item)
    saves_before = hn.plans.save_count
    llm_before = hn.llm.call_count

    with pytest.raises(PlanningError) as exc:
        hn.regenerate().execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key="2026-10", semantic_key="yearly.month.10.theme"
                ),
                actor_id=RAW_ACTOR,  # type: ignore[arg-type]
                catalog=hn.selector,
            )
        )

    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert exc.value.violated_rule == "regenerate_requires_opaque_actor_id"

    assert _item_state(item) == before
    assert not item.audit.contains(AuditEventType.REGENERATED)
    assert hn.plans.save_count == saves_before
    assert hn.llm.call_count == llm_before, "Actor 검증 실패인데 LLM이 호출되었다"


def test_regenerate_with_none_actor_leaves_plan_untouched_and_skips_llm():
    hn = H.make_harness()
    plan = _generate(hn).plan
    found = plan.find_item(period_key="2026-10", semantic_key="yearly.month.10.theme")
    before = _item_state(found[1])
    saves_before = hn.plans.save_count
    llm_before = hn.llm.call_count

    with pytest.raises(PlanningError) as exc:
        hn.regenerate().execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key="2026-10", semantic_key="yearly.month.10.theme"
                ),
                actor_id=None,  # type: ignore[arg-type]
                catalog=hn.selector,
            )
        )

    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert _item_state(found[1]) == before
    assert hn.plans.save_count == saves_before
    assert hn.llm.call_count == llm_before


def test_whole_plan_is_unchanged_after_failed_edit():
    """대상 Item뿐 아니라 Plan 전체가 불변이어야 한다."""
    from tests.golden.invariants import snapshot_items

    hn = H.make_harness()
    plan = _generate(hn).plan
    before = snapshot_items(plan)

    with pytest.raises(PlanningError):
        hn.edit().execute(
            EditYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key="2026-05", semantic_key="yearly.month.05.theme"
                ),
                new_value="x",
                actor_id=RAW_ACTOR,  # type: ignore[arg-type]
            )
        )

    assert snapshot_items(plan) == before


def test_llm_failure_during_regenerate_leaves_plan_untouched():
    """LLM 실패도 Mutation 이전이므로 Plan이 누출되지 않는다."""
    from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode

    hn = H.make_harness()
    plan = _generate(hn).plan

    found = plan.find_item(period_key="2026-10", semantic_key="yearly.month.10.theme")
    before = _item_state(found[1])

    hn.llm = FakeLLM(FakeLLMMode.UNAVAILABLE)

    with pytest.raises(PlanningError) as exc:
        hn.regenerate().execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key="2026-10", semantic_key="yearly.month.10.theme"
                ),
                actor_id=ACTOR,
                catalog=hn.selector,
            )
        )

    assert exc.value.failure_category is FailureCategory.LLM_FAILURE
    assert _item_state(found[1]) == before
    assert not found[1].audit.contains(AuditEventType.REGENERATED)


# ==================================================================
# 3. Regenerate 인접 Theme 중복 방지 — 9월/10월 양방향
# ==================================================================


def _adjacent_duplicates(plan) -> list[tuple[str, str]]:
    ids = H.theme_ids_of(plan)
    ordered = [ids[mp.period_key.value] for mp in plan.month_periods]
    return [(a, b) for a, b in zip(ordered, ordered[1:]) if a == b]


def test_generation_baseline_has_no_adjacent_duplicates():
    hn = H.make_harness()
    plan = _generate(hn).plan
    assert not _adjacent_duplicates(plan)

    ids = H.theme_ids_of(plan)
    assert ids["2026-09"] == "yr_theme_korea_and_world_cultures"
    assert ids["2026-10"] == "yr_theme_autumn_and_nature"


def test_regenerate_october_does_not_duplicate_september():
    hn = H.make_harness()
    plan = _generate(hn).plan
    september = H.theme_ids_of(plan)["2026-09"]

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

    ids = H.theme_ids_of(regen.plan)
    assert ids["2026-10"] != september, "Regenerate가 9월과 동일 Theme을 만들었다"
    assert not _adjacent_duplicates(regen.plan)


def test_regenerate_september_does_not_duplicate_october():
    hn = H.make_harness()
    plan = _generate(hn).plan
    october = H.theme_ids_of(plan)["2026-10"]

    regen = hn.regenerate().execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(
                period_key="2026-09", semantic_key="yearly.month.09.theme"
            ),
            actor_id=ACTOR,
            catalog=hn.selector,
        )
    )

    ids = H.theme_ids_of(regen.plan)
    assert ids["2026-09"] != october, "Regenerate가 10월과 동일 Theme을 만들었다"
    assert not _adjacent_duplicates(regen.plan)


@pytest.mark.parametrize("period,semantic", [
    ("2026-09", "yearly.month.09.theme"),
    ("2026-10", "yearly.month.10.theme"),
])
def test_repeated_regenerate_never_creates_adjacent_duplicate(period, semantic):
    """같은 칸을 여러 번 다시 뽑아도 인접 중복이 생기지 않는다."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    for _ in range(5):
        regen = hn.regenerate().execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(period_key=period, semantic_key=semantic),
                actor_id=ACTOR,
                catalog=hn.selector,
            )
        )
        assert not _adjacent_duplicates(regen.plan)
        validate_yearly_plan(regen.plan, catalog=hn.catalog)


def test_regenerate_keeps_theme_and_appends_audit_when_no_safe_alternative():
    """인접 안전한 대안이 없으면 theme_id 유지 + REGENERATED Audit."""
    hn = H.make_harness()
    plan = _generate(hn).plan

    found = plan.find_item(period_key="2026-10", semantic_key="yearly.month.10.theme")
    before_theme = found[1].evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[
        0
    ].source_id
    before_audit = len(found[1].audit)

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

    item = regen.plan.find_item(item_id=found[1].item_id.value)[1]
    after_theme = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0].source_id

    assert after_theme == before_theme
    assert len(item.audit) == before_audit + 1
    assert item.audit.contains(AuditEventType.REGENERATED)
    assert regen.plan.status is PlanStatus.DRAFT

    trace = regen.run.trace_for("2026-10")
    assert trace is not None
    assert trace.reason == "KEPT_CURRENT_THEME_TO_AVOID_ADJACENT_REPEAT"


# ==================================================================
# 4. Age Input Validation
# ==================================================================


def test_empty_ages_is_rejected():
    hn = H.make_harness()
    with pytest.raises(PlanningError) as exc:
        _generate(hn, ages=frozenset())
    assert exc.value.failure_category is FailureCategory.INPUT_VALIDATION
    assert exc.value.violated_rule == "classroom_requires_at_least_one_age"


@pytest.mark.parametrize("ages", [
    frozenset({2}),
    frozenset({6}),
    frozenset({0}),
    frozenset({2, 3}),
    frozenset({3, 4, 5, 6}),
])
def test_unsupported_ages_are_rejected(ages):
    """P0 지원 연령은 {3,4,5}다. 만 0~2세 영아반은 제외 범위."""
    hn = H.make_harness()
    with pytest.raises(PlanningError) as exc:
        _generate(hn, ages=ages)
    assert exc.value.failure_category is FailureCategory.INPUT_VALIDATION
    assert exc.value.violated_rule == "classroom_ages_must_be_supported_by_p0"


@pytest.mark.parametrize("ages", [
    frozenset({3}),
    frozenset({4}),
    frozenset({5}),
    frozenset({3, 4}),
    frozenset({4, 5}),
    frozenset({3, 4, 5}),
])
def test_supported_age_combinations_are_accepted(ages):
    hn = H.make_harness()
    result = _generate(hn, ages=ages)
    assert result.plan.classroom_ages == ages


def test_explicit_single_mode_with_two_ages_is_rejected():
    hn = H.make_harness()
    with pytest.raises(PlanningError) as exc:
        _generate(hn, ages=frozenset({3, 4}), age_mode=AgeMode.SINGLE)
    assert exc.value.violated_rule == "single_age_mode_requires_exactly_one_age"
    assert hn.plans.save_count == 0


def test_explicit_mixed_mode_with_one_age_is_rejected():
    hn = H.make_harness()
    with pytest.raises(PlanningError) as exc:
        _generate(hn, ages=frozenset({4}), age_mode=AgeMode.MIXED)
    assert exc.value.violated_rule == (
        "mixed_age_requires_at_least_two_distinct_supported_ages"
    )
    assert hn.plans.save_count == 0


def test_age_validation_runs_before_llm_and_persistence():
    hn = H.make_harness()
    with pytest.raises(PlanningError):
        _generate(hn, ages=frozenset({2}))
    assert not hn.llm.was_called
    assert hn.plans.save_count == 0


@pytest.mark.parametrize("ages,mode", [
    (frozenset({3}), AgeMode.SINGLE),
    (frozenset({3, 4}), AgeMode.MIXED),
    (frozenset({3, 4, 5}), AgeMode.MIXED),
])
def test_consistent_age_mode_is_accepted(ages, mode):
    hn = H.make_harness()
    result = _generate(hn, ages=ages, age_mode=mode)
    assert result.plan.classroom_ages == ages
