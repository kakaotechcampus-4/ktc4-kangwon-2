"""Golden Set invariant 검사기.

rule_id → 검사 함수 레지스트리. yearly_cases.json에 있는 rule_id가
레지스트리에 없으면 테스트가 실패한다. 조용히 넘어가지 않게 하는 것이 목적이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ssuksak.planning.domain.plan import PlanStatus, YearlyPlan
from ssuksak.planning.domain.provenance import AuditEventType, EvidenceSourceType
from ssuksak.planning.domain.theme_reference import ThemeCatalog
from ssuksak.planning.rules.periods import expected_period_key_values

_ALLOWED_METHODS = {"RULE_ONLY", "RULE_LLM"}


@dataclass
class ItemSnapshot:
    value: str
    semantic_key: str
    evidence: tuple[tuple[str, str], ...]
    audit_len: int
    method: str


def snapshot_items(plan: YearlyPlan) -> dict[str, ItemSnapshot]:
    return {
        item.item_id.value: ItemSnapshot(
            value=item.value,
            semantic_key=item.semantic_key.value,
            evidence=tuple(
                (e.source_type.value, e.source_id) for e in item.evidence
            ),
            audit_len=len(item.audit),
            method=item.generation.method.value,
        )
        for item in plan.items
    }


@dataclass
class InvariantContext:
    plan: YearlyPlan
    catalog: ThemeCatalog
    run: Any = None
    harness: Any = None
    suite: dict[str, Any] = field(default_factory=dict)
    case: dict[str, Any] = field(default_factory=dict)
    expected_school_year: int | None = None
    expected_classroom_ref: str | None = None
    expected_ages: frozenset[int] | None = None
    input_event_ids: set[str] = field(default_factory=set)
    before: dict[str, ItemSnapshot] = field(default_factory=dict)
    target_item_id: str | None = None
    plan_count: int = 1

    # ------------------------------------------------------------ helper

    def theme_refs(self):
        for mp in self.plan.month_periods:
            for ref in mp.theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE):
                yield mp, ref

    def all_evidence(self):
        for item in self.plan.items:
            for ev in item.evidence:
                yield item, ev


Checker = Callable[[InvariantContext, Any], None]
REGISTRY: dict[str, Checker] = {}


def check(rule_id: str):
    def deco(fn: Checker) -> Checker:
        REGISTRY[rule_id] = fn
        return fn

    return deco


# ------------------------------------------------------ 공통 성공 invariant


@check("yearly.output.status_is_draft")
def _status_is_draft(ctx: InvariantContext, expected: Any) -> None:
    assert (ctx.plan.status is PlanStatus.DRAFT) == expected, (
        f"status={ctx.plan.status.value}"
    )


@check("yearly.output.school_year_preserved")
def _school_year(ctx: InvariantContext, expected: Any) -> None:
    assert ctx.plan.school_year == expected, f"{ctx.plan.school_year} != {expected}"


@check("yearly.output.classroom_owner_preserved")
def _classroom_owner(ctx: InvariantContext, expected: Any) -> None:
    assert bool(ctx.plan.classroom_ref) == expected
    if ctx.expected_classroom_ref is not None:
        assert ctx.plan.classroom_ref == ctx.expected_classroom_ref


@check("yearly.period.count")
def _period_count(ctx: InvariantContext, expected: Any) -> None:
    assert len(ctx.plan.month_periods) == expected


@check("yearly.period.academic_order")
def _period_order(ctx: InvariantContext, expected: Any) -> None:
    actual = [mp.period_key.value for mp in ctx.plan.month_periods]
    assert actual == list(expected), f"{actual} != {expected}"
    # 학년도 산출 Rule과도 일치해야 한다.
    assert actual == list(expected_period_key_values(ctx.plan.school_year))


@check("yearly.theme.required_and_non_blank_each_period")
def _theme_non_blank(ctx: InvariantContext, expected: Any) -> None:
    for mp in ctx.plan.month_periods:
        ok = mp.theme is not None and bool(mp.theme.value.strip())
        assert ok == expected, f"{mp.period_key.value} theme={mp.theme.value!r}"


@check("yearly.item.stable_address")
def _stable_address(ctx: InvariantContext, expected: Any) -> None:
    seen: set[str] = set()
    for mp in ctx.plan.month_periods:
        item = mp.theme
        if expected.get("item_id_present"):
            assert item.item_id.value.strip(), f"{mp.period_key.value} item_id 없음"
        if expected.get("semantic_key_present"):
            assert item.semantic_key.value.strip()
        if expected.get("label_or_array_index_not_used_as_address"):
            # 주소가 표시 Label이나 배열 순번이 아님을 확인한다.
            assert item.item_id.value != item.value, "item_id가 표시 값과 같다"
            assert not item.item_id.value.isdigit(), "item_id가 배열 순번이다"
            # semantic_key는 의미 주소이며 월을 담는다.
            assert item.semantic_key.value == (
                f"yearly.month.{mp.period_key.calendar_month:02d}.theme"
            )
        assert item.item_id.value not in seen, "item_id 중복"
        seen.add(item.item_id.value)


@check("yearly.reference.catalog_version_exact")
def _catalog_version_exact(ctx: InvariantContext, expected: Any) -> None:
    assert ctx.catalog.catalog_version == expected
    for mp, ref in ctx.theme_refs():
        assert ref.source_version == expected, f"{mp.period_key.value} {ref.source_version}"


@check("yearly.reference.theme_id_resolves")
def _theme_id_resolves(ctx: InvariantContext, expected: Any) -> None:
    for mp, ref in ctx.theme_refs():
        resolved = ctx.catalog.get(ref.source_id) is not None
        assert resolved == expected, f"{mp.period_key.value} {ref.source_id}"


@check("yearly.reference.month_eligible")
def _month_eligible(ctx: InvariantContext, expected: Any) -> None:
    for mp, ref in ctx.theme_refs():
        cand = ctx.catalog.get(ref.source_id)
        assert cand is not None
        assert cand.supports_month(mp.period_key.calendar_month) == expected


@check("yearly.reference.age_set_eligible")
def _age_eligible(ctx: InvariantContext, expected: Any) -> None:
    for mp, ref in ctx.theme_refs():
        cand = ctx.catalog.get(ref.source_id)
        assert cand is not None
        assert cand.supports_age_set(ctx.plan.classroom_ages) == expected


@check("yearly.provenance.axes_are_separate")
def _provenance_axes(ctx: InvariantContext, expected: Any) -> None:
    ev_spec = expected["evidence_source"]
    allowed_methods = set(expected["generation_method_allowed"])
    audit_contains = expected["audit_contains"]

    for mp in ctx.plan.month_periods:
        item = mp.theme
        refs = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
        assert refs, f"{mp.period_key.value} THEME_REFERENCE Evidence 없음"
        ref = refs[0]

        assert ref.source_type.value == ev_spec["source_type"]
        if ev_spec.get("source_id_resolves_to_theme_id"):
            assert ctx.catalog.get(ref.source_id) is not None
        if ev_spec.get("source_version_present"):
            assert ref.source_version

        # 2축: Generation Method는 Evidence와 별개 필드다.
        assert item.generation.method.value in allowed_methods
        assert item.generation.rule_id, "RULE_* method는 rule_id를 가져야 한다"
        assert item.generation.rule_version

        # 3축: Audit
        for event_type in audit_contains:
            assert item.audit.contains(AuditEventType(event_type))

        # AI / TEACHER_EDIT은 Evidence Source가 아니다.
        for e in item.evidence:
            assert e.source_type.value not in ("AI", "TEACHER_EDIT")


@check("yearly.llm_does_not_select_or_replace_theme")
def _llm_no_theme_selection(ctx: InvariantContext, expected: Any) -> None:
    assert ctx.run is not None, "GenerationRun이 필요하다"
    rule_choice = {t.period_key: t.selected_theme_id for t in ctx.run.selection_traces}
    for mp, ref in ctx.theme_refs():
        assert (ref.source_id == rule_choice[mp.period_key.value]) == expected, (
            f"{mp.period_key.value}: Evidence {ref.source_id} != Rule 선택 "
            f"{rule_choice[mp.period_key.value]}"
        )


@check("yearly.no_unprovided_facts_or_events")
def _no_unprovided_events(ctx: InvariantContext, expected: Any) -> None:
    claimed = {
        ev.source_id
        for _item, ev in ctx.all_evidence()
        if ev.source_type is EvidenceSourceType.EVENT
    }
    assert claimed.issubset(ctx.input_event_ids) == expected, (
        f"입력되지 않은 행사 주장: {claimed - ctx.input_event_ids}"
    )


# ----------------------------------------------------- scenario invariant


@check("yearly.optional_context.absence_does_not_block")
def _optional_absence(ctx: InvariantContext, expected: Any) -> None:
    assert (ctx.plan is not None and len(ctx.plan.month_periods) == 12) == expected


@check("yearly.event.evidence_absent_when_no_event_input")
def _no_event_evidence(ctx: InvariantContext, expected: Any) -> None:
    has = any(
        ev.source_type is EvidenceSourceType.EVENT for _i, ev in ctx.all_evidence()
    )
    assert (not has) == expected


@check("yearly.trend.evidence_absent_when_no_trend_input")
def _no_trend_evidence(ctx: InvariantContext, expected: Any) -> None:
    has = any(
        ev.source_type is EvidenceSourceType.TREND for _i, ev in ctx.all_evidence()
    )
    assert (not has) == expected


@check("yearly.event.claims_are_subset_of_input_event_ids")
def _event_subset(ctx: InvariantContext, expected: Any) -> None:
    claimed = {
        ev.source_id
        for _i, ev in ctx.all_evidence()
        if ev.source_type is EvidenceSourceType.EVENT
    }
    assert claimed.issubset(set(expected)), f"{claimed} ⊄ {expected}"


@check("yearly.event.if_used_period_matches_event_date")
def _event_period(ctx: InvariantContext, expected: Any) -> None:
    for mp in ctx.plan.month_periods:
        for ev in mp.theme.evidence:
            if ev.source_type is EvidenceSourceType.EVENT:
                assert mp.period_key.value == expected, (
                    f"EVENT Evidence가 {mp.period_key.value}에 붙었는데 기대는 {expected}"
                )


@check("yearly.event.if_used_has_event_evidence")
def _event_evidence_shape(ctx: InvariantContext, expected: Any) -> None:
    found = [
        ev
        for _i, ev in ctx.all_evidence()
        if ev.source_type is EvidenceSourceType.EVENT
    ]
    assert found, "EVENT Evidence가 없다"
    assert any(
        ev.source_type.value == expected["source_type"]
        and ev.source_id == expected["source_id"]
        for ev in found
    )


@check("yearly.event.does_not_bypass_theme_reference")
def _event_no_bypass(ctx: InvariantContext, expected: Any) -> None:
    # 행사가 붙은 기간도 Theme은 여전히 Theme Reference에서 나와야 한다.
    for mp in ctx.plan.month_periods:
        refs = mp.theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
        assert bool(refs) == expected, f"{mp.period_key.value}"
        assert ctx.catalog.get(refs[0].source_id) is not None


@check("yearly.age_context.is_exact_set")
def _age_exact(ctx: InvariantContext, expected: Any) -> None:
    assert sorted(ctx.plan.classroom_ages) == list(expected)


@check("yearly.february.reference_is_age_eligible")
def _february_age(ctx: InvariantContext, expected: Any) -> None:
    feb = [mp for mp in ctx.plan.month_periods if mp.period_key.calendar_month == 2]
    assert feb, "2월 기간이 없다"
    for mp in feb:
        ref = mp.theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0]
        cand = ctx.catalog.get(ref.source_id)
        assert cand is not None
        assert cand.supports_age_set(ctx.plan.classroom_ages) == expected


@check("yearly.mixed_age.preserve_age_set")
def _mixed_preserve(ctx: InvariantContext, expected: Any) -> None:
    assert sorted(ctx.plan.classroom_ages) == list(expected)


@check("yearly.mixed_age.one_plan_per_classroom")
def _mixed_one_plan(ctx: InvariantContext, expected: Any) -> None:
    assert ctx.plan_count == expected, f"Plan 개수 {ctx.plan_count} != {expected}"


@check("yearly.mixed_age.no_single_age_collapse")
def _mixed_no_collapse(ctx: InvariantContext, expected: Any) -> None:
    assert (len(ctx.plan.classroom_ages) >= 2) == expected


@check("yearly.reference.supports_every_selected_age")
def _supports_every_age(ctx: InvariantContext, expected: Any) -> None:
    for mp, ref in ctx.theme_refs():
        cand = ctx.catalog.get(ref.source_id)
        assert cand is not None
        for age in ctx.plan.classroom_ages:
            assert (age in cand.supported_ages) == expected


@check("yearly.optional_dependency.failure_does_not_fail_core")
def _optional_failure_ok(ctx: InvariantContext, expected: Any) -> None:
    assert (ctx.plan is not None and len(ctx.plan.month_periods) == 12) == expected


@check("yearly.fallback.uses_base_reference")
def _fallback_base_reference(ctx: InvariantContext, expected: Any) -> None:
    for mp, ref in ctx.theme_refs():
        assert (ctx.catalog.get(ref.source_id) is not None) == expected


@check("yearly.trend.evidence_absent_after_timeout")
def _no_trend_after_timeout(ctx: InvariantContext, expected: Any) -> None:
    has = any(
        ev.source_type is EvidenceSourceType.TREND for _i, ev in ctx.all_evidence()
    )
    assert (not has) == expected


@check("yearly.generation_run.records_fallback")
def _run_records_fallback(ctx: InvariantContext, expected: Any) -> None:
    assert ctx.run is not None
    assert ctx.run.used_fallback == expected, f"fallbacks={ctx.run.fallbacks_used}"


# ------------------------------------------------------------- Regenerate


@check("yearly.regenerate.only_target_item_may_change")
def _regen_only_target(ctx: InvariantContext, expected: Any) -> None:
    after = snapshot_items(ctx.plan)
    changed = [
        item_id
        for item_id, snap in after.items()
        if item_id in ctx.before
        and (
            snap.value != ctx.before[item_id].value
            or snap.evidence != ctx.before[item_id].evidence
        )
    ]
    assert set(changed).issubset({ctx.target_item_id}) == expected, (
        f"대상 밖 변경: {set(changed) - {ctx.target_item_id}}"
    )


@check("yearly.regenerate.non_target_item_ids_values_and_evidence_preserved")
def _regen_preserve(ctx: InvariantContext, expected: Any) -> None:
    after = snapshot_items(ctx.plan)
    assert set(after) == set(ctx.before), "item_id 집합이 바뀌었다"
    for item_id, snap in ctx.before.items():
        if item_id == ctx.target_item_id:
            continue
        assert after[item_id].value == snap.value, f"{item_id} 값 변경"
        assert after[item_id].evidence == snap.evidence, f"{item_id} Evidence 변경"
        assert after[item_id].semantic_key == snap.semantic_key


@check("yearly.regenerate.target_item_id_and_semantic_key_stable")
def _regen_target_stable(ctx: InvariantContext, expected: Any) -> None:
    after = snapshot_items(ctx.plan)
    assert ctx.target_item_id in after, "대상 item_id가 사라졌다"
    assert (
        after[ctx.target_item_id].semantic_key
        == ctx.before[ctx.target_item_id].semantic_key
    ) == expected


@check("yearly.regenerate.new_reference_is_month_and_age_eligible")
def _regen_eligible(ctx: InvariantContext, expected: Any) -> None:
    found = ctx.plan.find_item(item_id=ctx.target_item_id)
    assert found is not None
    mp, item = found
    ref = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)[0]
    cand = ctx.catalog.get(ref.source_id)
    assert cand is not None
    ok = cand.supports_month(mp.period_key.calendar_month) and cand.supports_age_set(
        ctx.plan.classroom_ages
    )
    assert ok == expected


@check("yearly.regenerate.audit_appends")
def _regen_audit(ctx: InvariantContext, expected: Any) -> None:
    found = ctx.plan.find_item(item_id=ctx.target_item_id)
    assert found is not None
    _mp, item = found
    assert item.audit.contains(AuditEventType(expected))
    assert len(item.audit) > ctx.before[ctx.target_item_id].audit_len


@check("yearly.regenerate.plan_remains_draft")
def _regen_draft(ctx: InvariantContext, expected: Any) -> None:
    assert (ctx.plan.status is PlanStatus.DRAFT) == expected


# -------------------------------------------------------------------- Edit


@check("yearly.edit.only_target_item_changes")
def _edit_only_target(ctx: InvariantContext, expected: Any) -> None:
    after = snapshot_items(ctx.plan)
    changed = [
        item_id
        for item_id, snap in after.items()
        if item_id in ctx.before and snap.value != ctx.before[item_id].value
    ]
    assert (changed == [ctx.target_item_id]) == expected, f"변경된 Item: {changed}"


@check("yearly.edit.original_reference_evidence_preserved")
def _edit_evidence_preserved(ctx: InvariantContext, expected: Any) -> None:
    after = snapshot_items(ctx.plan)
    same = after[ctx.target_item_id].evidence == ctx.before[ctx.target_item_id].evidence
    assert same == expected, "교사 편집이 Evidence를 바꿨다"
    # Generation Method도 덮어쓰지 않는다.
    assert after[ctx.target_item_id].method == ctx.before[ctx.target_item_id].method


@check("yearly.edit.does_not_create_teacher_edit_evidence_source")
def _edit_no_teacher_evidence(ctx: InvariantContext, expected: Any) -> None:
    found = ctx.plan.find_item(item_id=ctx.target_item_id)
    assert found is not None
    _mp, item = found
    has = any(
        getattr(e.source_type, "value", e.source_type) in ("TEACHER_EDIT", "AI")
        for e in item.evidence
    )
    assert (not has) == expected


@check("yearly.edit.audit_appends")
def _edit_audit(ctx: InvariantContext, expected: Any) -> None:
    found = ctx.plan.find_item(item_id=ctx.target_item_id)
    assert found is not None
    _mp, item = found
    assert item.audit.contains(AuditEventType(expected))


@check("yearly.edit.plan_remains_draft")
def _edit_draft(ctx: InvariantContext, expected: Any) -> None:
    assert (ctx.plan.status is PlanStatus.DRAFT) == expected


# ----------------------------------------------------------------- Confirm


@check("yearly.confirm.status_transition")
def _confirm_status(ctx: InvariantContext, expected: Any) -> None:
    assert ctx.plan.status.value == expected


@check("yearly.confirm.actor_is_opaque_id_not_teacher_display_name")
def _confirm_actor(ctx: InvariantContext, expected: Any) -> None:
    events = [
        e for e in ctx.plan.audit if e.event_type is AuditEventType.CONFIRMED
    ]
    assert events, "CONFIRMED Audit Event가 없다"
    event = events[-1]
    assert event.actor_id is not None
    # 담임 표시 이름이 actor로 기록되지 않았음을 확인한다.
    fixture_teacher = ctx.suite["fixtures"]["classrooms"]["age3"]["teacher_name"]
    assert str(event.actor_id) != fixture_teacher
    assert bool(str(event.actor_id)) == expected


@check("yearly.confirm.audit_appends")
def _confirm_audit(ctx: InvariantContext, expected: Any) -> None:
    assert ctx.plan.audit.contains(AuditEventType(expected))


@check("yearly.confirm.does_not_submit_or_send")
def _confirm_no_submit(ctx: InvariantContext, expected: Any) -> None:
    # 제출·발송 기능이 애초에 존재하지 않는다는 구조적 확인.
    for forbidden in ("submit", "send", "export_to_authority"):
        assert not hasattr(ctx.harness.plans, forbidden)
        assert not hasattr(ctx.harness.confirm(), forbidden)
    assert expected is True


@check("yearly.confirm.plan_becomes_read_only")
def _confirm_read_only(ctx: InvariantContext, expected: Any) -> None:
    from ssuksak.planning.domain.errors import PlanningError

    try:
        ctx.plan.ensure_mutable("probe")
    except PlanningError:
        assert expected is True
        return
    raise AssertionError("CONFIRMED Plan이 read-only가 아니다")


# ---------------------------------------------------------------- 실행기


def assert_invariant(ctx: InvariantContext, rule_id: str, expected: Any) -> None:
    checker = REGISTRY.get(rule_id)
    assert checker is not None, (
        f"rule_id '{rule_id}'에 대한 invariant 검사기가 없다. "
        f"yearly_cases.json에 새 rule_id가 추가되었다면 검사기를 구현해야 한다."
    )
    checker(ctx, expected)


def assert_common_success(ctx: InvariantContext, suite: dict[str, Any]) -> None:
    for inv in suite["common_success_invariants"]:
        assert_invariant(ctx, inv["rule_id"], inv["expected"])


def assert_scenario(ctx: InvariantContext, case: dict[str, Any]) -> None:
    for inv in case.get("expected", {}).get("scenario_invariants", []) or []:
        key = "expected" if "expected" in inv else "expected_plan_count"
        assert_invariant(ctx, inv["rule_id"], inv[key])
