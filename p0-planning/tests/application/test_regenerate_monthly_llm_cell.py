"""RegenerateMonthlyPlanItem — LLM Cell 재생성 (L7).

실제 API를 호출하지 않는다. FakeLLM에 명시적 Cell 제안을 설정해
Application Use Case 전 경로를 돌린다.

핵심 불변은 하나다. **Target Cell 하나만 바뀐다.**
"""

from __future__ import annotations

import pytest

from ssuksak.planning.application.confirm_monthly_plan import (
    ConfirmMonthlyPlan,
    ConfirmMonthlyPlanCommand,
)
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.monthly_dto import (
    EditMonthlyPlanItemCommand,
    MonthlyCellAddress,
    MonthlyGenerationMode,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.monthly_llm_cell_regeneration import (
    MonthlyLlmCellRegenerator,
    build_month_snapshot,
)
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
    plan_generation_mode,
)
from ssuksak.planning.context import MonthlyContextPacketBuilder
from ssuksak.planning.domain.constraint import CellState
from ssuksak.planning.domain.errors import PlanningError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.retrieval import (
    InMemoryInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode
from ssuksak.shared.llm.monthly import ProposedActivityOrigin
from ssuksak.shared.llm.monthly_cell import MonthlyCellRegenerationProposal
from ssuksak.shared.llm.port import LLMUnavailableError

from .test_generate_monthly_llm_planner import (
    RECORDS,
    SOURCE_TEXT,
    build_wiring,
    focus_items,
    llm_command,
    outdoor_items,
    proposal_for,
)

ACTOR = ActorId("teacher_001")
MODEL = "openai/gpt-4.1-mini"


# ------------------------------------------------------------------ 조립


def make_llm_plan(fake: FakeLLM | None = None):
    """LLM Planner로 만든 DRAFT 하나."""
    fake = fake or FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))
    plan = wiring.use_case.execute(llm_command()).plan
    return wiring, builder, plan


def regenerator(llm, builder, *, model: str = MODEL) -> MonthlyLlmCellRegenerator:
    return MonthlyLlmCellRegenerator(
        context_builder=builder, llm=llm, planner_model=model
    )


def use_case(wiring, llm, builder, *, model: str = MODEL):
    return RegenerateMonthlyPlanItem(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        clock=wiring.use_case._clock,
        activity_reference_repository=wiring.use_case._activities,
        llm_cell_regenerator=regenerator(llm, builder, model=model),
    )


def address(plan, section_key: str, week_index: int = 2) -> MonthlyCellAddress:
    week = [w for w in plan.week_periods if w.active][week_index]
    return MonthlyCellAddress(
        target_month=plan.target_month.value,
        section_key=section_key,
        week_id=week.week_id.value,
    )


def command(plan, section_key: str, week_index: int = 2, **over):
    return RegenerateMonthlyPlanItemCommand(
        plan_id=plan.plan_id.value,
        address=address(plan, section_key, week_index),
        actor_id=ACTOR,
        **over,
    )


def focus_proposal(plan, value: str, week_index: int = 2):
    week = [w for w in plan.week_periods if w.active][week_index]
    return MonthlyCellRegenerationProposal(
        target_week_id=week.week_id.value,
        target_section_key="focus",
        value=value,
        activity_origin=None,
        reference_activity_id=None,
        grounding_refs=[],
    )


def outdoor_synthesized(plan, value: str, refs: list[str], week_index: int = 2):
    week = [w for w in plan.week_periods if w.active][week_index]
    return MonthlyCellRegenerationProposal(
        target_week_id=week.week_id.value,
        target_section_key="outdoor_play",
        value=value,
        activity_origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
        reference_activity_id=None,
        grounding_refs=refs,
    )


def outdoor_reference(plan, activity_id: str, label: str, week_index: int = 2):
    week = [w for w in plan.week_periods if w.active][week_index]
    return MonthlyCellRegenerationProposal(
        target_week_id=week.week_id.value,
        target_section_key="outdoor_play",
        value=label,
        activity_origin=ProposedActivityOrigin.REFERENCE,
        reference_activity_id=activity_id,
        grounding_refs=[],
    )


def any_ref(builder, wiring) -> str:
    from ssuksak.planning.rules.monthly_llm_validation import build_packet_index

    from .test_generate_monthly_llm_planner import _packet

    index = build_packet_index(_packet(builder, wiring, (4,)))
    for ref in sorted(index.by_ref):
        grounded = index.by_ref[ref]
        if grounded.single_age is None or grounded.single_age == 4:
            return ref
    raise AssertionError("쓸 수 있는 근거가 없다")


def snapshot(plan) -> dict:
    """Target-only 검증용. 모든 Cell의 값·상태·Provenance를 뜬다."""
    out = {}
    for section in plan.sections:
        for item in section.items:
            key = (section.section_key, item.week_id.value if item.week_id else None)
            out[key] = (
                item.value,
                item.cell_state,
                item.generation.method,
                item.generation.rule_id,
                tuple((e.source_type, e.source_id) for e in item.evidence),
                len(item.audit),
            )
    return out


def changed_keys(before: dict, after: dict) -> set:
    return {k for k in before if before[k] != after[k]} | (set(after) - set(before))


# ============================================== Mode 파생


def test_plan_generation_mode_is_derived_from_item_provenance():
    _, _, plan = make_llm_plan()
    assert plan_generation_mode(plan) is MonthlyGenerationMode.LLM_PLANNER


def test_a_rule_only_plan_is_detected_as_rule_only():
    from .test_generate_monthly_activity import ACT_SELECTOR, Wiring, repo
    from .test_generate_monthly_llm_planner import CANDIDATES
    from .test_generate_monthly_plan import command as generate_command

    wiring = Wiring(activities=repo(*CANDIDATES))
    plan = wiring.use_case.execute(
        generate_command(activity_catalog=ACT_SELECTOR)
    ).plan
    assert plan_generation_mode(plan) is MonthlyGenerationMode.RULE_ONLY


def test_mismatched_mode_is_rejected():
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    with pytest.raises(PlanningError) as exc:
        use_case(wiring, fake, builder).execute(
            command(plan, "focus", generation_mode=MonthlyGenerationMode.RULE_ONLY)
        )
    assert "regenerate_mode_must_match_the_plan_generation_path" in str(exc.value)
    assert fake.cell_call_count == 0


# ============================================== focus 재생성


def test_focus_regenerate_changes_only_the_target_cell():
    wiring, builder, plan = make_llm_plan()
    before = snapshot(plan)
    target = address(plan, "focus")

    fake = FakeLLM()
    fake.set_cell_proposal(
        focus_proposal(plan, "가을 열매와 나뭇잎의 변화를 비교하며 탐색해요")
    )
    result = use_case(wiring, fake, builder).execute(command(plan, "focus"))

    after = snapshot(result.plan)
    assert changed_keys(before, after) == {("focus", target.week_id)}


def test_focus_regenerate_writes_the_new_value():
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "새로 쓴 중심 경험입니다"))
    result = use_case(wiring, fake, builder).execute(command(plan, "focus"))

    item = next(
        i for i in focus_items(result.plan)
        if i.week_id.value == address(plan, "focus").week_id
    )
    assert item.value == "새로 쓴 중심 경험입니다"
    assert item.cell_state is CellState.FILLED


def test_focus_regenerate_keeps_the_paired_outdoor_cell():
    wiring, builder, plan = make_llm_plan()
    week_id = address(plan, "focus").week_id
    paired_before = next(
        i for i in outdoor_items(plan) if i.week_id.value == week_id
    )
    before = (paired_before.value, list(paired_before.evidence))

    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "새로 쓴 중심 경험입니다"))
    result = use_case(wiring, fake, builder).execute(command(plan, "focus"))

    paired_after = next(
        i for i in outdoor_items(result.plan) if i.week_id.value == week_id
    )
    assert (paired_after.value, list(paired_after.evidence)) == before


def test_focus_provenance_is_rule_llm_with_no_evidence():
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "새로 쓴 중심 경험입니다"))
    result = use_case(wiring, fake, builder).execute(command(plan, "focus"))

    item = next(
        i for i in focus_items(result.plan)
        if i.week_id.value == address(plan, "focus").week_id
    )
    assert item.generation.method is GenerationMethod.RULE_LLM
    assert item.generation.rule_id == "monthly.llm.evidence_grounded_planner"
    assert item.generation.rule_version == "v1"
    assert item.evidence == []


def test_focus_regenerate_sees_the_whole_month():
    """Target만 보여주지 않는다 (§3)."""
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "새로 쓴 중심 경험입니다"))
    use_case(wiring, fake, builder).execute(command(plan, "focus"))

    content = fake.cell_calls[0].user_content
    for week in [w for w in plan.week_periods if w.active]:
        assert week.week_id.value in content
    for item in outdoor_items(plan):
        assert item.value in content
    assert "★" in content


# ============================================== outdoor 재생성


def test_outdoor_synthesized_regenerate_changes_only_the_target():
    wiring, builder, plan = make_llm_plan()
    before = snapshot(plan)
    target = address(plan, "outdoor_play")

    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_synthesized(plan, "새 가을 바깥놀이", [any_ref(builder, wiring)])
    )
    result = use_case(wiring, fake, builder).execute(
        command(plan, "outdoor_play")
    )

    after = snapshot(result.plan)
    assert changed_keys(before, after) == {("outdoor_play", target.week_id)}


def test_outdoor_synthesized_records_institution_sample_evidence():
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_synthesized(plan, "새 가을 바깥놀이", [any_ref(builder, wiring)])
    )
    result = use_case(wiring, fake, builder).execute(
        command(plan, "outdoor_play")
    )

    item = next(
        i for i in outdoor_items(result.plan)
        if i.week_id.value == address(plan, "outdoor_play").week_id
    )
    grounding = item.evidence_of_type(EvidenceSourceType.INSTITUTION_SAMPLE)
    assert grounding
    assert {e.source_id for e in grounding} <= {r.record_id for r in RECORDS}
    assert item.generation.method is GenerationMethod.RULE_LLM


def test_outdoor_reference_records_activity_reference_evidence():
    wiring, builder, plan = make_llm_plan()
    from .test_generate_monthly_llm_planner import _packet

    packet = _packet(builder, wiring, (4,))
    used = {
        e.source_id
        for i in outdoor_items(plan)
        for e in i.evidence_of_type(EvidenceSourceType.ACTIVITY_REFERENCE)
    }
    chosen = next(
        (c for c in packet.reference_activities if c.activity_id not in used), None
    )
    if chosen is None:
        pytest.skip("쓰지 않은 승인 후보가 없다")

    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_reference(plan, chosen.activity_id, chosen.label)
    )
    result = use_case(wiring, fake, builder).execute(
        command(plan, "outdoor_play")
    )

    item = next(
        i for i in outdoor_items(result.plan)
        if i.week_id.value == address(plan, "outdoor_play").week_id
    )
    refs = item.evidence_of_type(EvidenceSourceType.ACTIVITY_REFERENCE)
    assert refs and refs[0].source_id == chosen.activity_id
    assert item.value == chosen.label


def test_outdoor_regenerate_keeps_the_paired_focus_cell():
    wiring, builder, plan = make_llm_plan()
    week_id = address(plan, "outdoor_play").week_id
    before = next(i for i in focus_items(plan) if i.week_id.value == week_id).value

    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_synthesized(plan, "새 가을 바깥놀이", [any_ref(builder, wiring)])
    )
    result = use_case(wiring, fake, builder).execute(
        command(plan, "outdoor_play")
    )
    after = next(
        i for i in focus_items(result.plan) if i.week_id.value == week_id
    ).value
    assert after == before


def test_outdoor_regenerate_sees_the_paired_focus_as_context():
    wiring, builder, plan = make_llm_plan()
    week_id = address(plan, "outdoor_play").week_id
    paired = next(i for i in focus_items(plan) if i.week_id.value == week_id).value

    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_synthesized(plan, "새 가을 바깥놀이", [any_ref(builder, wiring)])
    )
    use_case(wiring, fake, builder).execute(command(plan, "outdoor_play"))
    assert paired in fake.cell_calls[0].user_content


# ============================================== 중복 / 검증


def test_duplicate_activity_across_weeks_is_rejected():
    wiring, builder, plan = make_llm_plan()
    other = outdoor_items(plan)[0]
    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_synthesized(plan, other.value, [any_ref(builder, wiring)])
    )
    with pytest.raises(PlanningError) as exc:
        use_case(wiring, fake, builder).execute(command(plan, "outdoor_play"))
    assert "activity_must_not_repeat_within_a_month" in str(exc.value)


def test_duplicate_focus_across_weeks_is_rejected():
    wiring, builder, plan = make_llm_plan()
    other = focus_items(plan)[0]
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, other.value))
    with pytest.raises(PlanningError) as exc:
        use_case(wiring, fake, builder).execute(command(plan, "focus"))
    assert "week_experience_must_not_repeat_within_a_month" in str(exc.value)


def test_exact_source_copy_is_rejected():
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_synthesized(plan, SOURCE_TEXT, [any_ref(builder, wiring)])
    )
    with pytest.raises(PlanningError) as exc:
        use_case(wiring, fake, builder).execute(command(plan, "outdoor_play"))
    assert "copies_source_text_exactly" in str(exc.value)


def test_safety_leakage_in_focus_is_rejected():
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "이번 주 안전교육은 교통안전입니다"))
    with pytest.raises(PlanningError) as exc:
        use_case(wiring, fake, builder).execute(command(plan, "focus"))
    assert "statutory_safety_education" in str(exc.value)


# ============================================== Atomicity


def saved(wiring) -> int:
    return wiring.use_case._monthly.save_count


def test_llm_failure_leaves_the_plan_untouched():
    wiring, builder, plan = make_llm_plan()
    before = snapshot(plan)
    saves = saved(wiring)

    fake = FakeLLM(FakeLLMMode.UNAVAILABLE)
    fake.set_cell_proposal(focus_proposal(plan, "무시된다"))
    with pytest.raises(LLMUnavailableError):
        use_case(wiring, fake, builder).execute(command(plan, "focus"))

    stored = wiring.use_case._monthly.get(plan.plan_id.value)
    assert snapshot(stored) == before
    assert saved(wiring) == saves


def test_validation_failure_leaves_the_plan_untouched():
    wiring, builder, plan = make_llm_plan()
    before = snapshot(plan)
    saves = saved(wiring)

    fake = FakeLLM()
    fake.set_cell_proposal(
        outdoor_synthesized(plan, SOURCE_TEXT, [any_ref(builder, wiring)])
    )
    with pytest.raises(PlanningError):
        use_case(wiring, fake, builder).execute(command(plan, "outdoor_play"))

    stored = wiring.use_case._monthly.get(plan.plan_id.value)
    assert snapshot(stored) == before
    assert saved(wiring) == saves


def test_success_saves_exactly_once():
    wiring, builder, plan = make_llm_plan()
    saves = saved(wiring)
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "새로 쓴 중심 경험입니다"))
    use_case(wiring, fake, builder).execute(command(plan, "focus"))
    assert saved(wiring) == saves + 1


def test_missing_regenerator_fails_without_falling_back_to_rule():
    wiring, _, plan = make_llm_plan()
    bare = RegenerateMonthlyPlanItem(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        clock=wiring.use_case._clock,
        activity_reference_repository=wiring.use_case._activities,
    )
    before = snapshot(plan)
    with pytest.raises(PlanningError) as exc:
        bare.execute(command(plan, "outdoor_play"))
    assert "llm_cell_regenerate_requires_a_regenerator_dependency" in str(exc.value)
    assert snapshot(wiring.use_case._monthly.get(plan.plan_id.value)) == before


# ============================================== Repair


class ScriptedCellLLM:
    def __init__(self, proposals):
        self._proposals = list(proposals)
        self.requests: list = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def regenerate_monthly_cell(self, request):
        self.requests.append(request)
        if not self._proposals:
            raise AssertionError("스크립트보다 많이 호출되었다")
        return self._proposals.pop(0)


def test_exact_copy_is_repaired_then_saved():
    wiring, builder, plan = make_llm_plan()
    ref = any_ref(builder, wiring)
    scripted = ScriptedCellLLM(
        [
            outdoor_synthesized(plan, SOURCE_TEXT, [ref]),
            outdoor_synthesized(plan, "새로 구성한 가을 바깥놀이", [ref]),
        ]
    )
    saves = saved(wiring)
    result = use_case(wiring, scripted, builder).execute(
        command(plan, "outdoor_play")
    )

    assert scripted.call_count == 2
    assert result.cell_regeneration.validation_repair_count == 1
    assert saved(wiring) == saves + 1
    item = next(
        i for i in outdoor_items(result.plan)
        if i.week_id.value == address(plan, "outdoor_play").week_id
    )
    assert item.value == "새로 구성한 가을 바깥놀이"


def test_repair_failure_is_atomic():
    wiring, builder, plan = make_llm_plan()
    ref = any_ref(builder, wiring)
    before = snapshot(plan)
    saves = saved(wiring)
    bad = outdoor_synthesized(plan, SOURCE_TEXT, [ref])
    scripted = ScriptedCellLLM([bad, bad, bad])

    with pytest.raises(PlanningError):
        use_case(wiring, scripted, builder).execute(command(plan, "outdoor_play"))

    assert scripted.call_count == 2
    assert saved(wiring) == saves
    assert snapshot(wiring.use_case._monthly.get(plan.plan_id.value)) == before


def test_non_repairable_violation_does_not_retry():
    wiring, builder, plan = make_llm_plan()
    scripted = ScriptedCellLLM([focus_proposal(plan, "새로 쓴 중심 경험입니다")])
    with pytest.raises(PlanningError):
        use_case(wiring, scripted, builder, model="").execute(
            command(plan, "focus")
        )
    assert scripted.call_count == 1


def test_the_repair_request_reuses_the_same_packet_and_snapshot():
    wiring, builder, plan = make_llm_plan()
    ref = any_ref(builder, wiring)
    scripted = ScriptedCellLLM(
        [
            outdoor_synthesized(plan, SOURCE_TEXT, [ref]),
            outdoor_synthesized(plan, "새로 구성한 가을 바깥놀이", [ref]),
        ]
    )
    use_case(wiring, scripted, builder).execute(command(plan, "outdoor_play"))

    first, second = scripted.requests
    assert second.packet_fingerprint == first.packet_fingerprint
    assert second.user_content.startswith(first.user_content)
    assert SOURCE_TEXT not in second.user_content.split(first.user_content)[1]


# ============================================== Gate / Audit


def test_confirmed_plan_blocks_before_any_provider_call():
    wiring, builder, plan = make_llm_plan()
    ConfirmMonthlyPlan(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        safety_rule_repository=wiring.use_case._safety_rules,
        clock=wiring.use_case._clock,
    ).execute(
        ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=ACTOR)
    )
    saves = saved(wiring)

    for section_key in ("focus", "outdoor_play"):
        fake = FakeLLM()
        fake.set_cell_proposal(focus_proposal(plan, "무시된다"))
        with pytest.raises(PlanningError):
            use_case(wiring, fake, builder).execute(command(plan, section_key))
        assert fake.cell_call_count == 0
    assert saved(wiring) == saves


def test_regenerated_audit_event_is_recorded():
    wiring, builder, plan = make_llm_plan()
    week_id = address(plan, "focus").week_id
    old = next(i for i in focus_items(plan) if i.week_id.value == week_id).value

    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "새로 쓴 중심 경험입니다"))
    result = use_case(wiring, fake, builder).execute(command(plan, "focus"))

    item = next(i for i in focus_items(result.plan) if i.week_id.value == week_id)
    event = item.audit.events[-1]
    assert event.event_type is AuditEventType.REGENERATED
    assert event.actor_id == ACTOR
    assert event.previous_value == old
    assert event.new_value == "새로 쓴 중심 경험입니다"


def test_teacher_edited_target_can_be_explicitly_regenerated():
    wiring, builder, plan = make_llm_plan()
    target = address(plan, "focus")
    EditMonthlyPlanItem(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        clock=wiring.use_case._clock,
    ).execute(
        EditMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=target,
            new_value="교사가 고친 값",
            actor_id=ACTOR,
        )
    )

    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "AI가 다시 쓴 값"))
    result = use_case(wiring, fake, builder).execute(command(plan, "focus"))

    item = next(
        i for i in focus_items(result.plan) if i.week_id.value == target.week_id
    )
    assert item.value == "AI가 다시 쓴 값"
    # history는 지워지지 않는다.
    types = item.audit.types()
    assert AuditEventType.CREATED in types
    assert AuditEventType.TEACHER_EDITED in types
    assert AuditEventType.REGENERATED in types


def test_teacher_edited_non_target_is_never_touched():
    wiring, builder, plan = make_llm_plan()
    edited = address(plan, "focus", week_index=0)
    EditMonthlyPlanItem(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        clock=wiring.use_case._clock,
    ).execute(
        EditMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=edited,
            new_value="교사가 고친 값",
            actor_id=ACTOR,
        )
    )

    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "AI가 다시 쓴 값", week_index=2))
    result = use_case(wiring, fake, builder).execute(
        command(plan, "focus", week_index=2)
    )

    untouched = next(
        i for i in focus_items(result.plan) if i.week_id.value == edited.week_id
    )
    assert untouched.value == "교사가 고친 값"
    assert AuditEventType.REGENERATED not in untouched.audit.types()


# ============================================== Lineage / Gate


def test_theme_is_not_llm_regeneratable():
    """theme은 parent anchor에서 Rule로 재파생한다. LLM이 만들지 않는다."""
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "무시된다"))
    result = use_case(wiring, fake, builder).execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=MonthlyCellAddress(
                target_month=plan.target_month.value,
                section_key="theme",
                week_id=None,
            ),
            actor_id=ACTOR,
        )
    )
    theme = next(
        s for s in result.plan.sections if s.section_key == "theme"
    ).items[0]
    assert theme.generation.method is GenerationMethod.RULE_ONLY
    assert fake.cell_call_count == 0


def test_safety_is_still_blocked():
    wiring, builder, plan = make_llm_plan()
    fake = FakeLLM()
    with pytest.raises(PlanningError):
        use_case(wiring, fake, builder).execute(
            command(plan, "safety_education")
        )
    assert fake.cell_call_count == 0


def test_plan_lineage_is_not_upgraded():
    wiring, builder, plan = make_llm_plan()
    before = (
        plan.template_ref.template_version,
        plan.activity_catalog.catalog_version,
        plan.parent_lineage.parent_yearly_theme_id,
    )
    fake = FakeLLM()
    fake.set_cell_proposal(focus_proposal(plan, "새로 쓴 중심 경험입니다"))
    result = use_case(wiring, fake, builder).execute(command(plan, "focus"))
    assert (
        result.plan.template_ref.template_version,
        result.plan.activity_catalog.catalog_version,
        result.plan.parent_lineage.parent_yearly_theme_id,
    ) == before


def test_month_snapshot_follows_canonical_week_order():
    _, _, plan = make_llm_plan()
    weeks = [w.week_id.value for w in plan.week_periods if w.active]
    assert [row[0] for row in build_month_snapshot(plan)] == weeks
