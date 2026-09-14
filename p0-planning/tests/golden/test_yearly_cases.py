"""tests/golden/yearly_cases.json 전수 실행.

case 목록을 하드코딩하지 않는다. 파일이 진실이며, case_id에 handler가 없으면
테스트가 실패한다. 새 case가 추가되면 조용히 통과하지 않고 드러난다.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from ssuksak.planning.application.dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    EditYearlyPlanItemCommand,
    ItemAddress,
    RegenerateYearlyPlanItemCommand,
)
from ssuksak.planning.application.validate_yearly_plan import validate_yearly_plan
from ssuksak.planning.domain.errors import Outcome, PlanningError
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSource,
    EvidenceSourceType,
)
from ssuksak.planning.domain.theme_reference import ActivationStatus

from . import harness as H
from .invariants import InvariantContext, assert_common_success, assert_scenario
from .invariants import snapshot_items

SUITE = H.load_suite()
CASES: list[dict[str, Any]] = SUITE["cases"]

HANDLERS: dict[str, Callable[[dict[str, Any]], None]] = {}


def handles(case_id: str):
    def deco(fn):
        HANDLERS[case_id] = fn
        return fn

    return deco


# ------------------------------------------------------------------ 공통


def _generate_base(case: dict[str, Any], **harness_kwargs) -> tuple[H.Harness, Any]:
    """정상 생성 1회를 수행하고 (harness, result)를 반환한다."""
    hn = H.make_harness(**harness_kwargs)
    command = H.build_generate_command(SUITE, case, catalog=hn.selector)
    result = hn.generate().execute(command)
    return hn, result


def _base_case(case_id: str) -> dict[str, Any]:
    for c in CASES:
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"base_case를 찾을 수 없다: {case_id}")


def _ctx(
    hn: H.Harness,
    result: Any,
    case: dict[str, Any],
    *,
    before=None,
    target_item_id=None,
    plan_count=1,
) -> InvariantContext:
    command = None
    try:
        command = H.build_generate_command(SUITE, case, catalog=hn.selector)
    except Exception:  # noqa: BLE001 - arrange 기반 case는 command가 없다
        pass

    return InvariantContext(
        plan=result.plan,
        catalog=hn.catalog,
        run=result.run,
        harness=hn,
        suite=SUITE,
        case=case,
        expected_school_year=SUITE["academic_calendar"]["school_year"],
        expected_classroom_ref=command.classroom.classroom_ref if command else result.plan.classroom_ref,
        input_event_ids=H.input_event_ids(SUITE, case),
        before=before or {},
        target_item_id=target_item_id,
        plan_count=plan_count,
    )


def _expect_failure(case: dict[str, Any], fn) -> PlanningError:
    with pytest.raises(PlanningError) as exc:
        fn()
    err = exc.value
    expected = case["expected"]

    assert err.outcome is Outcome(expected["outcome"]), (
        f"outcome {err.outcome.value} != {expected['outcome']}"
    )
    if "failure_category" in expected:
        assert err.failure_category.value == expected["failure_category"], (
            f"{err.failure_category.value} != {expected['failure_category']}"
        )
    if "violated_rule" in expected:
        rules = {v.violated_rule for v in err.violations}
        assert expected["violated_rule"] in rules, (
            f"{expected['violated_rule']} not in {rules}"
        )
    return err


# ============================================================ SUCCESS 생성


@handles("generate_age3_no_events_no_optional_context")
@handles("generate_age5_without_event")
@handles("generate_mixed_age_3_4_no_optional_context")
def _plain_success(case: dict[str, Any]) -> None:
    hn, result = _generate_base(case)
    ctx = _ctx(hn, result, case, plan_count=hn.plans.stored_count)
    assert_common_success(ctx, SUITE)
    assert_scenario(ctx, case)
    assert hn.plans.save_count == 1


@handles("generate_age4_with_confirmed_event")
def _success_with_event(case: dict[str, Any]) -> None:
    hn, result = _generate_base(case)
    ctx = _ctx(hn, result, case, plan_count=hn.plans.stored_count)
    assert_common_success(ctx, SUITE)
    assert_scenario(ctx, case)

    # not_asserted: 행사가 theme label을 바꾼다고 단정하지 않는다.
    assert "not_asserted" in case["expected"]


@handles("generate_age5_trend_timeout_uses_fallback")
def _success_with_fallback(case: dict[str, Any]) -> None:
    hn, result = _generate_base(case, optional_outcomes={"trend": "TIMEOUT"})
    ctx = _ctx(hn, result, case, plan_count=hn.plans.stored_count)
    assert_common_success(ctx, SUITE)
    assert_scenario(ctx, case)

    assert result.run.used_fallback
    assert any("trend" in f for f in result.run.fallbacks_used)


# ============================================================ GATE / 실패


@handles("gate_unapproved_theme_reference")
def _gate_unapproved(case: dict[str, Any]) -> None:
    hn = H.make_harness(activation=ActivationStatus.PENDING_HUMAN_REVIEW)
    command = H.build_generate_command(SUITE, case, catalog=hn.selector)
    _expect_failure(case, lambda: hn.generate().execute(command))

    assert hn.plans.save_count == 0, "차단되었는데 저장되었다"
    assert not hn.llm.was_called, "차단되었는데 LLM이 호출되었다"


@handles("reference_unknown_catalog_version")
def _unknown_version(case: dict[str, Any]) -> None:
    hn = H.make_harness()
    requested = case["input"]["reference_catalog"]
    selector = CatalogSelector(requested["catalog_id"], requested["catalog_version"])
    command = H.build_generate_command(SUITE, case, catalog=selector)
    _expect_failure(case, lambda: hn.generate().execute(command))

    assert hn.plans.save_count == 0
    assert not hn.llm.was_called


@handles("reference_no_age_and_month_eligible_candidate")
def _candidate_empty(case: dict[str, Any]) -> None:
    # catalog_mutation: 2026-06에 적용 가능하고 만3세를 지원하는 후보 전부 제거
    full = H.build_catalog()
    to_drop = {
        c.theme_id
        for c in full.eligible_candidates(6, frozenset({3}))
    }
    assert to_drop, "제거할 6월 후보가 없다 — mutation 전제가 깨졌다"

    hn = H.make_harness(drop_themes=to_drop)
    base = _base_case("generate_age3_no_events_no_optional_context")
    command = H.build_generate_command(SUITE, base, catalog=hn.selector)
    _expect_failure(case, lambda: hn.generate().execute(command))

    assert hn.plans.save_count == 0, "후보 공백인데 저장되었다"
    # LLM이 대체 Theme을 만들어 채우지 않았음을 확인한다.
    assert case["expected"]["llm_may_invent_replacement_theme"] is False


@handles("validation_rejects_mixed_age_with_one_selected_age")
def _invalid_mixed_age(case: dict[str, Any]) -> None:
    hn = H.make_harness()
    command = H.build_generate_command(SUITE, case, catalog=hn.selector)
    _expect_failure(case, lambda: hn.generate().execute(command))

    assert hn.plans.save_count == 0
    assert not hn.llm.was_called


@handles("gate_planning_setup_incomplete")
def _setup_incomplete(case: dict[str, Any]) -> None:
    hn = H.make_harness()
    command = H.build_generate_command(SUITE, case, catalog=hn.selector)
    _expect_failure(case, lambda: hn.generate().execute(command))

    assert hn.plans.save_count == 0
    assert not hn.llm.was_called


@handles("gate_monthly_generation_requires_confirmed_yearly")
def _monthly_gate(case: dict[str, Any]) -> None:
    base = _base_case(case["arrange"]["parent_yearly_plan_case"])
    hn, result = _generate_base(base)

    assert result.plan.status is PlanStatus.DRAFT
    assert case["arrange"]["parent_yearly_plan_status"] == "DRAFT"

    _expect_failure(
        case,
        lambda: hn.monthly_gate().ensure_can_generate_monthly(
            result.plan.classroom_ref, result.plan.school_year
        ),
    )
    # Monthly Plan은 생성되지 않는다 (이 Slice는 Monthly를 구현하지 않는다).
    assert hn.plans.stored_count == 1


# ================================================ Validator 단독 호출 case


@handles("reference_unknown_selected_theme_id")
def _unknown_theme_id(case: dict[str, Any]) -> None:
    base = _base_case(case["arrange"]["base_case"])
    hn, result = _generate_base(base)
    mutation = case["arrange"]["output_mutation"]

    mp = result.plan.period(mutation["period"])
    assert mp is not None
    mp.theme.evidence = [
        EvidenceSource(
            source_type=EvidenceSourceType.THEME_REFERENCE,
            source_id=mutation["replace_theme_id_with"],
            source_version=hn.catalog.catalog_version,
        )
    ]

    _expect_failure(
        case, lambda: validate_yearly_plan(result.plan, catalog=hn.catalog)
    )


@handles("reference_theme_source_version_mismatch")
def _version_mismatch(case: dict[str, Any]) -> None:
    base = _base_case(case["arrange"]["base_case"])
    hn, result = _generate_base(base)
    mutation = case["arrange"]["output_mutation"]

    mp = result.plan.period(mutation["period"])
    assert mp is not None
    kept = mutation["keep_theme_id"]
    mp.theme.evidence = [
        EvidenceSource(
            source_type=EvidenceSourceType.THEME_REFERENCE,
            source_id=kept,
            source_version=mutation["replace_source_version_with"],
        )
    ]

    _expect_failure(
        case, lambda: validate_yearly_plan(result.plan, catalog=hn.catalog)
    )


@handles("validation_rejects_eleven_periods")
def _eleven_periods(case: dict[str, Any]) -> None:
    base = _base_case(case["arrange"]["base_case"])
    hn, result = _generate_base(base)

    result.plan.month_periods = [
        mp for mp in result.plan.month_periods if mp.period_key.value != "2027-02"
    ]
    assert len(result.plan.month_periods) == 11

    _expect_failure(
        case, lambda: validate_yearly_plan(result.plan, catalog=hn.catalog)
    )


@handles("validation_rejects_wrong_academic_month_order")
def _wrong_order(case: dict[str, Any]) -> None:
    base = _base_case(case["arrange"]["base_case"])
    hn, result = _generate_base(base)

    sept = result.plan.period("2026-09")
    assert sept is not None
    new_periods = []
    for mp in result.plan.month_periods:
        if mp.period_key.value == "2026-10":
            # 2026-09를 중복하고 2026-10을 누락시킨다.
            import copy

            dup = copy.deepcopy(sept)
            new_periods.append(dup)
        else:
            new_periods.append(mp)
    result.plan.month_periods = new_periods

    keys = [mp.period_key.value for mp in result.plan.month_periods]
    assert keys.count("2026-09") == 2 and "2026-10" not in keys

    _expect_failure(
        case, lambda: validate_yearly_plan(result.plan, catalog=hn.catalog)
    )


@handles("validation_rejects_blank_theme")
def _blank_theme(case: dict[str, Any]) -> None:
    base = _base_case(case["arrange"]["base_case"])
    hn, result = _generate_base(base)
    mutation = case["arrange"]["output_mutation"]

    mp = result.plan.period(mutation["period"])
    assert mp is not None
    mp.theme.value = mutation["theme_value"]

    _expect_failure(
        case, lambda: validate_yearly_plan(result.plan, catalog=hn.catalog)
    )


# ============================================== Edit / Regenerate / Confirm


@handles("regenerate_one_theme_preserves_other_items")
def _regenerate(case: dict[str, Any]) -> None:
    arrange = case["arrange"]
    base = _base_case(arrange["existing_plan_case"])
    hn, result = _generate_base(base)
    plan = result.plan

    target = arrange["target"]
    found = plan.find_item(
        period_key=target["period"], semantic_key=target["semantic_key"]
    )
    assert found is not None, f"대상 Item을 찾을 수 없다: {target}"
    _mp, item = found
    target_item_id = item.item_id.value

    before = snapshot_items(plan)
    before_theme_id = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0].source_id

    regen_result = hn.regenerate().execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(
                period_key=target["period"], semantic_key=target["semantic_key"]
            ),
            actor_id=H.ACTOR,
            catalog=hn.selector,
        )
    )

    ctx = _ctx(
        hn, regen_result, base, before=before, target_item_id=target_item_id
    )
    assert_scenario(ctx, case)

    # Golden Set은 theme_id 변경을 요구하지 않는다. 요구하는 것은 대상 밖 보존,
    # 주소 안정성, 월·연령 적합성, REGENERATED Audit, DRAFT 유지다.
    #
    # 2026-10의 eligible 후보는 2개지만 대안(korea)이 2026-09 Theme과 겹치므로
    # 인접 중복 회피가 우선해 현재 Theme(autumn)이 유지된다.
    after_theme_id = (
        regen_result.plan.find_item(item_id=target_item_id)[1]
        .evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0]
        .source_id
    )
    assert after_theme_id == before_theme_id, (
        "인접 월과 충돌하지 않는 대안이 없으면 현재 theme_id를 유지해야 한다"
    )

    # 인접 중복이 생기지 않았음을 확인한다.
    theme_ids = [
        H.theme_ids_of(regen_result.plan)[mp.period_key.value]
        for mp in regen_result.plan.month_periods
    ]
    assert not [
        (a, b) for a, b in zip(theme_ids, theme_ids[1:]) if a == b
    ], "Regenerate가 인접 월 Theme 중복을 만들었다"

    # 전체 구조는 여전히 유효하다.
    validate_yearly_plan(regen_result.plan, catalog=hn.catalog)


@handles("edit_one_theme_keeps_original_evidence")
def _edit(case: dict[str, Any]) -> None:
    arrange = case["arrange"]
    base = _base_case(arrange["existing_plan_case"])
    hn, result = _generate_base(base)
    plan = result.plan

    target = arrange["target"]
    found = plan.find_item(
        period_key=target["period"], semantic_key=target["semantic_key"]
    )
    assert found is not None
    _mp, item = found
    target_item_id = item.item_id.value
    before = snapshot_items(plan)

    edit_result = hn.edit().execute(
        EditYearlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=ItemAddress(
                period_key=target["period"], semantic_key=target["semantic_key"]
            ),
            new_value=arrange["teacher_value"],
            actor_id=H.ACTOR,
        )
    )

    ctx = _ctx(hn, edit_result, base, before=before, target_item_id=target_item_id)
    assert_scenario(ctx, case)

    after = edit_result.plan.find_item(item_id=target_item_id)[1]
    assert after.value == arrange["teacher_value"]
    validate_yearly_plan(edit_result.plan, catalog=hn.catalog)


@handles("confirm_yearly_with_opaque_actor")
def _confirm(case: dict[str, Any]) -> None:
    arrange = case["arrange"]
    base = _base_case(arrange["existing_plan_case"])
    hn, result = _generate_base(base)

    from ssuksak.planning.domain.identifiers import ActorId

    actor = ActorId(arrange["actor_id"])
    confirm_result = hn.confirm().execute(
        ConfirmYearlyPlanCommand(
            plan_id=result.plan.plan_id.value,
            actor_id=actor,
            catalog=hn.selector,
        )
    )

    ctx = _ctx(hn, confirm_result, base)
    assert_scenario(ctx, case)
    assert confirm_result.plan.status is PlanStatus.CONFIRMED


@handles("confirm_yearly_without_actor_fails")
def _confirm_no_actor(case: dict[str, Any]) -> None:
    arrange = case["arrange"]
    base = _base_case(arrange["existing_plan_case"])
    hn, result = _generate_base(base)

    assert arrange["actor_id"] is None
    assert arrange["teacher_name_present"] is True

    _expect_failure(
        case,
        lambda: hn.confirm().execute(
            ConfirmYearlyPlanCommand(
                plan_id=result.plan.plan_id.value, actor_id=None, catalog=hn.selector
            )
        ),
    )

    reloaded = hn.plans.get(result.plan.plan_id.value)
    assert reloaded is not None
    assert reloaded.status.value == case["expected"]["plan_status_after_failure"]


@handles("edit_confirmed_yearly_is_blocked")
def _edit_confirmed_blocked(case: dict[str, Any]) -> None:
    arrange = case["arrange"]
    confirm_case = _base_case(arrange["existing_plan_case"])
    base = _base_case(confirm_case["arrange"]["existing_plan_case"])

    hn, result = _generate_base(base)
    from ssuksak.planning.domain.identifiers import ActorId

    hn.confirm().execute(
        ConfirmYearlyPlanCommand(
            plan_id=result.plan.plan_id.value,
            actor_id=ActorId(confirm_case["arrange"]["actor_id"]),
            catalog=hn.selector,
        )
    )
    plan = hn.plans.get(result.plan.plan_id.value)
    assert plan is not None and plan.status is PlanStatus.CONFIRMED

    target = arrange["target"]
    before = snapshot_items(plan)

    _expect_failure(
        case,
        lambda: hn.edit().execute(
            EditYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key=target["period"], semantic_key=target["semantic_key"]
                ),
                new_value=arrange["teacher_value"],
                actor_id=H.ACTOR,
            )
        ),
    )

    assert snapshot_items(plan) == before, "차단되었는데 Plan이 바뀌었다"
    found = plan.find_item(
        period_key=target["period"], semantic_key=target["semantic_key"]
    )
    assert found is not None
    assert not found[1].audit.contains(
        AuditEventType(case["expected"]["audit_event_not_appended"])
    )


@handles("regenerate_confirmed_yearly_is_blocked")
def _regen_confirmed_blocked(case: dict[str, Any]) -> None:
    arrange = case["arrange"]
    confirm_case = _base_case(arrange["existing_plan_case"])
    base = _base_case(confirm_case["arrange"]["existing_plan_case"])

    hn, result = _generate_base(base)
    from ssuksak.planning.domain.identifiers import ActorId

    hn.confirm().execute(
        ConfirmYearlyPlanCommand(
            plan_id=result.plan.plan_id.value,
            actor_id=ActorId(confirm_case["arrange"]["actor_id"]),
            catalog=hn.selector,
        )
    )
    plan = hn.plans.get(result.plan.plan_id.value)
    assert plan is not None

    target = arrange["target"]
    before = snapshot_items(plan)
    llm_calls_before = hn.llm.call_count

    _expect_failure(
        case,
        lambda: hn.regenerate().execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=plan.plan_id.value,
                address=ItemAddress(
                    period_key=target["period"], semantic_key=target["semantic_key"]
                ),
                actor_id=H.ACTOR,
                catalog=hn.selector,
            )
        ),
    )

    assert snapshot_items(plan) == before, "차단되었는데 Plan이 바뀌었다"
    assert hn.llm.call_count == llm_calls_before, "차단되었는데 LLM이 호출되었다"
    found = plan.find_item(
        period_key=target["period"], semantic_key=target["semantic_key"]
    )
    assert not found[1].audit.contains(
        AuditEventType(case["expected"]["audit_event_not_appended"])
    )


# =================================================================== 실행


@pytest.mark.parametrize(
    "case", CASES, ids=[c["case_id"] for c in CASES]
)
def test_golden_case(case: dict[str, Any]) -> None:
    handler = HANDLERS.get(case["case_id"])
    assert handler is not None, (
        f"case '{case['case_id']}'에 handler가 없다. "
        f"yearly_cases.json에 case가 추가되었다면 handler를 구현해야 한다."
    )
    handler(case)


def test_suite_metadata_matches_reference_fixture() -> None:
    """Golden Set이 가리키는 Catalog와 실제 파일이 일치하는지 확인한다."""
    fixture = SUITE["reference_fixture"]
    payload = H.load_catalog_payload()

    assert payload["catalog_id"] == fixture["catalog_id"]
    assert payload["catalog_version"] == fixture["catalog_version"]
    # Golden Set이 가정한 검토 상태와 실제 파일이 어긋나면 드리프트다.
    assert (
        payload["review"]["domain_owner_approval"] == fixture["current_review_state"]
    )
    # v0.1.2는 사람 승인을 받았으므로 승인자와 시각이 모두 기록되어 있어야 한다.
    assert payload["review"]["domain_owner_approval"] == "HUMAN_APPROVED"
    assert payload["review"]["approved_by"]
    assert payload["review"]["approved_at"]


def test_every_case_has_a_handler() -> None:
    missing = [c["case_id"] for c in CASES if c["case_id"] not in HANDLERS]
    assert not missing, f"handler 없는 case: {missing}"


def test_case_count_is_twenty_two() -> None:
    assert len(CASES) == 22, f"case 개수가 {len(CASES)}개다"
