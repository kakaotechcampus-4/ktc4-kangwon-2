"""GenerateMonthlyPlan — LLM_PLANNER 경로 통합 (L6).

실제 API를 호출하지 않는다. FakeLLM에 명시적 Proposal을 설정해
Application Use Case 전 경로를 돌린다.
"""

from __future__ import annotations

import datetime

import pytest

from ssuksak.ingestion.models import (
    AgeEvidenceType,
    EvidenceRecord,
    EvidenceSourceType as IngestSourceType,
    ExtractionQuality,
    MachineReadability,
    ReusePolicy,
    Setting,
    SourceSection,
)
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_dto import MonthlyGenerationMode
from ssuksak.planning.application.monthly_llm_planning import MonthlyLlmPlanner
from ssuksak.planning.context import MonthlyContextPacketBuilder
from ssuksak.planning.domain.constraint import CellState, ConstraintVerification
from ssuksak.planning.domain.errors import PlanningError
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.adapters.monthly_repositories import (
    production_monthly_template_repository,
)
from ssuksak.planning.domain.monthly_template import TemplateRef
from ssuksak.planning.retrieval import (
    InMemoryInstitutionEvidenceRepository,
    MonthlyEvidenceRetriever,
)
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode
from ssuksak.shared.llm.monthly import (
    MonthlyPlanProposal,
    ProposedActivity,
    ProposedActivityOrigin,
    ProposedWeek,
)
from ssuksak.shared.llm.port import LLMConfigurationError, LLMUnavailableError

from .test_generate_monthly_activity import (  # 기존 Wiring을 재사용한다
    ACT_CATALOG_ID,
    ACT_SELECTOR,
    ACT_VERSION,
    Wiring,
    candidate,
    repo,
)
from .test_generate_monthly_plan import command

MODEL = "openai/gpt-4.1-mini"
CATALOG_VERSION = ACT_VERSION

TEMPLATE_ID = "ssuksak.monthly-template-a"
RULE_ONLY_TEMPLATE = "monthly-template-a-v0.1.0"
WEEK_EXPERIENCE_TEMPLATE = "monthly-template-a-v0.2.0"
"""LLM Planner는 `focus`가 활성화된 Template을 **명시적으로** 요청한다 (OD-N18)."""

CANDIDATES = (
    candidate("act_a", "가을 산책하기"),
    candidate("act_b", "낙엽 모아 던지기"),
    candidate("act_c", "도토리 찾아보기"),
    candidate("act_d", "가을 하늘 바라보기"),
    candidate("act_e", "솔방울 굴리기"),
)

SOURCE_TEXT = "가을 숲 산책하며 열매 모으기"


def rec(rid: str, *, institution: str, text: str, month: int = 9) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=rid,
        source_type=IngestSourceType.INSTITUTION_SAMPLE,
        source_path=f"references/samples/monthly/{institution}.pdf",
        source_sha256=institution.encode().hex().ljust(64, "0")[:64],
        page=1,
        institution_id=institution,
        month=month,
        age_scope=(4,),
        age_evidence_type=AgeEvidenceType.SINGLE_AGE_PAGE,
        monthly_theme="가을",
        source_section=SourceSection.OUTDOOR_PLAY,
        source_label="바깥놀이",
        activity_text=text,
        setting=Setting.OUTDOOR,
        machine_readability=MachineReadability.TEXT_LAYER,
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        extraction_quality=ExtractionQuality.VALID,
        extraction_method="table_line_geometry_v1",
    )


RECORDS = [
    rec("ev_1", institution="가어린이집", text=SOURCE_TEXT),
    rec("ev_2", institution="나어린이집", text="가을 바람 느끼며 걷기"),
    rec("ev_3", institution="다어린이집", text="낙엽 밟으며 소리 듣기"),
]


def build_wiring(fake, *, records=None, model: str = MODEL):
    """RULE_ONLY Wiring에 LLM Planner만 추가로 붙인다.

    Context Builder와 Use Case가 **같은 Catalog**를 쓴다. 서로 다른 Catalog를
    쓰면 Packet이 준 후보와 Plan이 pin한 Catalog가 어긋난다.
    """
    wiring = Wiring(activities=repo(*CANDIDATES))
    catalog = wiring.use_case._activities.get_catalog(ACT_CATALOG_ID, ACT_VERSION)

    store = InMemoryInstitutionEvidenceRepository(
        RECORDS if records is None else records
    ).get_store()
    builder = MonthlyContextPacketBuilder(
        MonthlyEvidenceRetriever(store, activity_catalog=catalog),
        store,
        activity_catalog=catalog,
    )
    planner = MonthlyLlmPlanner(
        context_builder=builder,
        llm=fake,
        planner_model=model,
        activity_catalog=catalog,
    )
    wiring.use_case = GenerateMonthlyPlan(
        yearly_plan_repository=wiring.use_case._yearly,
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=production_monthly_template_repository(),
        safety_rule_repository=wiring.use_case._safety_rules,
        clock=wiring.use_case._clock,
        id_generator=wiring.use_case._ids,
        activity_reference_repository=wiring.use_case._activities,
        llm_planner=planner,
    )
    return wiring, builder


def llm_command(**over):
    """LLM Planner Mode. 승인 Catalog도 함께 pin한다(§28)."""
    base = dict(
        generation_mode=MonthlyGenerationMode.LLM_PLANNER,
        activity_catalog=ACT_SELECTOR,
        template_ref=TemplateRef(TEMPLATE_ID, WEEK_EXPERIENCE_TEMPLATE),
    )
    base.update(over)
    return command(**base)


def proposal_for(builder, wiring, *, week_activity=None, ages=(4,)):
    """Use Case가 만들 Packet과 같은 Packet으로 Proposal을 구성한다."""
    packet = _packet(builder, wiring, ages)
    refs = sorted(
        {i.ref for i in packet.institution_evidence}
        | {i.ref for i in packet.other_outdoor_evidence}
    )
    weeks = []
    for index, slot in enumerate(packet.week_slots, start=1):
        activity = week_activity(index, refs) if week_activity else ProposedActivity(
            value=f"가을 놀이 {index}",
            origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
            reference_activity_id=None,
            grounding_refs=[refs[0]],
        )
        weeks.append(
            ProposedWeek(
                week_id=slot.week_id,
                experience=f"{index}주차 가을 경험을 나눠요.",
                activity=activity,
            )
        )
    return MonthlyPlanProposal(
        theme_id=packet.parent_theme.theme_id,
        month_flow_rationale="관심에서 표현으로 이어지도록 구성했습니다.",
        weeks=weeks,
    )


def _packet(builder, wiring, ages):
    from ssuksak.planning.application.monthly_llm_planning import MonthlyContextRequest
    from ssuksak.planning.domain.identifiers import PeriodKey

    cmd = llm_command()
    parent = wiring.use_case._yearly.get(cmd.parent_yearly_plan_id)
    period = next(
        p for p in parent.month_periods if p.period_key.value == cmd.target_month
    )
    anchor = period.theme.evidence[0]
    confirmed = next(
        e for e in parent.audit if e.event_type is AuditEventType.CONFIRMED
    )
    from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage

    lineage = ParentYearlyLineage(
        parent_yearly_plan_id=parent.plan_id.value,
        parent_yearly_period_key=period.period_key.value,
        parent_yearly_theme_id=anchor.source_id,
        parent_yearly_value=period.theme.value,
        reference_catalog_id=cmd.catalog.catalog_id,
        reference_version=anchor.source_version or "",
        confirmed_at=confirmed.occurred_at,
        confirmed_by=confirmed.actor_id.value,
    )
    return builder.build(
        MonthlyContextRequest(
            school_year=str(cmd.school_year),
            target_month=PeriodKey(cmd.target_month),
            classroom_ages=tuple(sorted(cmd.classroom.ages)),
            age_mode=cmd.classroom.effective_age_mode.value,
            parent_lineage=lineage,
            daycare_ref=cmd.daycare.daycare_ref,
            classroom_ref=cmd.classroom.classroom_ref,
        )
    )


def outdoor_items(plan):
    section = next(s for s in plan.sections if s.section_key == "outdoor_play")
    return section.items


def focus_items(plan):
    section = next(s for s in plan.sections if s.section_key == "focus")
    return section.items


# ============================================== 성공 경로


def test_llm_planner_creates_a_draft():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    result = wiring.use_case.execute(llm_command())

    assert result.plan.status is PlanStatus.DRAFT
    assert result.run.generation_mode == "LLM_PLANNER"
    assert result.run.llm_invoked is True
    assert result.run.llm_call_count == 1
    assert fake.monthly_call_count == 1


def test_outdoor_cells_come_from_the_proposal():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    proposal = proposal_for(builder, wiring)
    fake.set_monthly_proposal(proposal)

    plan = wiring.use_case.execute(llm_command()).plan
    values = [i.value for i in outdoor_items(plan)]
    assert values == [w.activity.value for w in proposal.weeks]
    for item in outdoor_items(plan):
        assert item.cell_state is CellState.FILLED


def test_week_ids_come_from_canonical_periods_not_the_proposal():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    plan = wiring.use_case.execute(llm_command()).plan
    canonical = [w.week_id.value for w in plan.week_periods if w.active]
    assert [i.week_id.value for i in outdoor_items(plan)] == canonical


def test_theme_still_comes_from_the_parent_rule():
    """Theme은 LLM 출력이 아니라 확정 Yearly에서 만든다 (§18)."""
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    plan = wiring.use_case.execute(llm_command()).plan
    theme = next(s for s in plan.sections if s.section_key == "theme").items[0]
    assert theme.generation.method is GenerationMethod.RULE_ONLY
    assert theme.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    assert theme.evidence_of_type(EvidenceSourceType.PARENT_PLAN)


def test_safety_semantics_are_unchanged():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    result = wiring.use_case.execute(llm_command())
    safety = next(
        s for s in result.plan.sections if s.section_key == "safety_education"
    )
    assert all(i.cell_state is CellState.EMPTY_UNRESOLVED for i in safety.items)
    assert all(not i.evidence for i in safety.items)
    assert result.run.has_unresolved_requirement
    assert result.plan.constraint_assessments[0].verification is (
        ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    )


# ============================================== Provenance


def test_synthesized_activity_records_institution_sample_evidence():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    plan = wiring.use_case.execute(llm_command()).plan
    item = outdoor_items(plan)[0]
    assert item.generation.method is GenerationMethod.RULE_LLM
    assert item.generation.rule_id == "monthly.llm.evidence_grounded_planner"
    assert item.generation.rule_version == "v1"

    grounding = item.evidence_of_type(EvidenceSourceType.INSTITUTION_SAMPLE)
    assert grounding
    assert {e.source_id for e in grounding} <= {r.record_id for r in RECORDS}
    assert all(e.source_version for e in grounding)


def test_reference_activity_records_activity_reference_evidence():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    packet = _packet(builder, wiring, (4,))
    if not packet.reference_activities:
        pytest.skip("승인 Catalog 후보가 이 달에 없다")
    chosen = packet.reference_activities[0]

    def week_activity(index, refs):
        if index == 1:
            return ProposedActivity(
                value=chosen.label,
                origin=ProposedActivityOrigin.REFERENCE,
                reference_activity_id=chosen.activity_id,
                grounding_refs=[],
            )
        return ProposedActivity(
            value=f"가을 놀이 {index}",
            origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
            reference_activity_id=None,
            grounding_refs=[refs[0]],
        )

    fake.set_monthly_proposal(
        proposal_for(builder, wiring, week_activity=week_activity)
    )
    plan = wiring.use_case.execute(llm_command()).plan
    item = outdoor_items(plan)[0]
    refs = item.evidence_of_type(EvidenceSourceType.ACTIVITY_REFERENCE)
    assert refs and refs[0].source_id == chosen.activity_id
    assert refs[0].source_version == CATALOG_VERSION
    assert item.generation.method is GenerationMethod.RULE_LLM


def test_llm_synthesized_is_never_an_evidence_source_type():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    plan = wiring.use_case.execute(llm_command()).plan
    for item in outdoor_items(plan):
        for evidence in item.evidence:
            assert evidence.source_type.value != "LLM_SYNTHESIZED"


def test_run_records_planner_lineage():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    run = wiring.use_case.execute(llm_command()).run
    assert run.planner_model == MODEL
    assert run.prompt_version == "monthly-planner-prompt-v0.1.1"
    assert run.packet_fingerprint
    assert run.context_packet_version == "monthly-context-packet-v0.1.0"
    assert run.retrieval_version
    assert run.evidence_store_sha256


def test_run_never_stores_prompt_or_credentials():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    run = wiring.use_case.execute(llm_command()).run
    blob = repr(run)
    assert "당신은" not in blob
    assert "ELICE" not in blob
    assert SOURCE_TEXT not in blob


def test_activity_catalog_is_pinned_on_the_plan():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    plan = wiring.use_case.execute(llm_command()).plan
    assert plan.activity_catalog is not None
    assert plan.activity_catalog.catalog_version == CATALOG_VERSION


# ============================================== Atomicity / 실패


def saved_count(wiring) -> int:
    return wiring.use_case._monthly.stored_count


def test_llm_unavailable_saves_nothing():
    fake = FakeLLM(FakeLLMMode.UNAVAILABLE)
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    with pytest.raises(LLMUnavailableError):
        wiring.use_case.execute(llm_command())
    assert saved_count(wiring) == 0


def test_schema_failure_saves_nothing():
    fake = FakeLLM(FakeLLMMode.SCHEMA_VIOLATION)
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    with pytest.raises(ValueError):
        wiring.use_case.execute(llm_command())
    assert saved_count(wiring) == 0


def test_success_saves_exactly_once():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    wiring.use_case.execute(llm_command())
    assert saved_count(wiring) == 1


def test_llm_planner_mode_without_a_planner_fails_loudly():
    """조용히 RULE_ONLY로 내려가지 않는다 (§32)."""
    wiring, _ = build_wiring(FakeLLM())
    wiring.use_case._llm_planner = None  # Planner만 뺀다
    with pytest.raises(PlanningError) as exc:
        wiring.use_case.execute(llm_command())
    assert "llm_planner_mode_requires_a_planner_dependency" in str(exc.value)
    assert saved_count(wiring) == 0


def test_no_silent_rule_only_fallback_on_llm_failure():
    fake = FakeLLM(FakeLLMMode.UNAVAILABLE)
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    with pytest.raises(LLMUnavailableError):
        wiring.use_case.execute(llm_command())
    # Rule-only 결과가 대신 저장되지 않았다.
    assert saved_count(wiring) == 0


def test_missing_planner_model_is_rejected_before_save():
    """Provenance를 채울 수 없으면 저장하지 않는다."""
    fake = FakeLLM()
    wiring, builder = build_wiring(fake, model="")
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    with pytest.raises(PlanningError) as exc:
        wiring.use_case.execute(llm_command())
    assert "provenance" in str(exc.value).lower()
    assert saved_count(wiring) == 0


# ============================================== Repair


class ScriptedLLM:
    """정해진 Proposal을 순서대로 돌려준다. Planner를 흉내 내지 않는다."""

    def __init__(self, proposals):
        self._proposals = list(proposals)
        self.requests: list = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def plan_monthly(self, request):
        self.requests.append(request)
        if not self._proposals:
            raise AssertionError("스크립트보다 많이 호출되었다")
        return self._proposals.pop(0)


def copy_proposal(builder, wiring):
    """W1이 CONTEXT_ONLY 원문을 그대로 복사한 Proposal."""

    def week_activity(index, refs):
        value = SOURCE_TEXT if index == 1 else f"가을 놀이 {index}"
        return ProposedActivity(
            value=value,
            origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
            reference_activity_id=None,
            grounding_refs=[refs[0]],
        )

    return proposal_for(builder, wiring, week_activity=week_activity)


def test_exact_copy_is_repaired_and_then_saved():
    """§15 — 실제 결함 유형의 repair E2E."""
    wiring, builder = build_wiring(FakeLLM())
    clean = proposal_for(builder, wiring)
    scripted = ScriptedLLM([copy_proposal(builder, wiring), clean])
    wiring, builder = build_wiring(scripted)

    result = wiring.use_case.execute(llm_command())

    assert scripted.call_count == 2
    assert result.run.llm_call_count == 2
    assert result.run.planner_validation_repair_count == 1
    assert "synthesized_activity_copies_source_text_exactly" in (
        result.run.planner_repaired_violations
    )
    assert saved_count(wiring) == 1
    assert outdoor_items(result.plan)[0].value != SOURCE_TEXT


def test_the_repair_request_reuses_the_same_packet():
    wiring, builder = build_wiring(FakeLLM())
    clean = proposal_for(builder, wiring)
    scripted = ScriptedLLM([copy_proposal(builder, wiring), clean])
    wiring, builder = build_wiring(scripted)
    wiring.use_case.execute(llm_command())

    first, second = scripted.requests
    assert second.packet_fingerprint == first.packet_fingerprint
    assert second.user_content.startswith(first.user_content)
    assert "규칙을 위반" in second.user_content
    assert SOURCE_TEXT not in second.user_content.split(first.user_content)[1]


def test_repair_failure_saves_nothing():
    """§16 — 두 번 다 복사면 Generate 실패."""
    wiring, builder = build_wiring(FakeLLM())
    bad = copy_proposal(builder, wiring)
    scripted = ScriptedLLM([bad, bad])
    wiring, builder = build_wiring(scripted)

    with pytest.raises(PlanningError) as exc:
        wiring.use_case.execute(llm_command())
    assert scripted.call_count == 2
    assert saved_count(wiring) == 0
    assert "repair 후에도" in str(exc.value)


def test_a_second_repair_cycle_is_not_started():
    wiring, builder = build_wiring(FakeLLM())
    bad = copy_proposal(builder, wiring)
    scripted = ScriptedLLM([bad, bad, bad])
    wiring, builder = build_wiring(scripted)

    with pytest.raises(PlanningError):
        wiring.use_case.execute(llm_command())
    assert scripted.call_count == 2


def test_non_repairable_violation_does_not_call_the_llm_again():
    """§14 — Packet 문제면 재호출하지 않는다."""
    wiring, builder = build_wiring(FakeLLM())
    clean = proposal_for(builder, wiring)
    scripted = ScriptedLLM([clean])
    # planner_model이 비면 PROVENANCE_INCOMPLETE — repairable이 아니다.
    wiring, builder = build_wiring(scripted, model="")

    with pytest.raises(PlanningError):
        wiring.use_case.execute(llm_command())
    assert scripted.call_count == 1
    assert saved_count(wiring) == 0


# ============================================== 기존 Contract 회귀


def test_saved_llm_plan_round_trips():
    fake = FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))

    plan = wiring.use_case.execute(llm_command()).plan
    stored = wiring.use_case._monthly.get(plan.plan_id.value)
    assert stored is not None
    assert stored.status is PlanStatus.DRAFT
    assert stored.parent_lineage.parent_yearly_theme_id
    assert stored.activity_catalog.catalog_version == CATALOG_VERSION
    item = next(
        i for i in outdoor_items(stored)
        if i.evidence_of_type(EvidenceSourceType.INSTITUTION_SAMPLE)
    )
    assert item.generation.method is GenerationMethod.RULE_LLM
    assert item.audit.contains(AuditEventType.CREATED)


# ============================================== §48 기존 Monthly Contract


def llm_plan(fake=None):
    fake = fake or FakeLLM()
    wiring, builder = build_wiring(fake)
    fake.set_monthly_proposal(proposal_for(builder, wiring))
    return wiring, wiring.use_case.execute(llm_command()).plan


def test_teacher_edit_works_on_an_llm_plan():
    """교사 수정이 LLM 생성보다 우선한다 (§34)."""
    from ssuksak.planning.application.edit_monthly_plan_item import (
        EditMonthlyPlanItem,
    )
    from ssuksak.planning.application.monthly_dto import (
        EditMonthlyPlanItemCommand,
        MonthlyCellAddress,
    )
    from ssuksak.planning.domain.identifiers import ActorId

    wiring, plan = llm_plan()
    target = outdoor_items(plan)[0]
    use_case = EditMonthlyPlanItem(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        clock=wiring.use_case._clock,
    )
    result = use_case.execute(
        EditMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=MonthlyCellAddress(
                target_month=plan.target_month.value,
                section_key="outdoor_play",
                week_id=target.week_id.value,
            ),
            new_value="교사가 고친 활동",
            actor_id=ActorId("teacher_001"),
        )
    )
    edited = next(
        i for i in outdoor_items(result.plan) if i.item_id == target.item_id
    )
    assert edited.value == "교사가 고친 활동"
    assert edited.audit.contains(AuditEventType.TEACHER_EDITED)
    # 원래 생성 근거는 지워지지 않는다 (CLAUDE.md §13.3).
    assert edited.evidence


def test_confirm_works_on_an_llm_plan_with_unresolved_safety():
    from ssuksak.planning.application.confirm_monthly_plan import (
        ConfirmMonthlyPlan,
        ConfirmMonthlyPlanCommand,
    )
    from ssuksak.planning.domain.identifiers import ActorId

    wiring, plan = llm_plan()
    use_case = ConfirmMonthlyPlan(
        monthly_plan_repository=wiring.use_case._monthly,
        template_repository=wiring.use_case._templates,
        safety_rule_repository=wiring.use_case._safety_rules,
        clock=wiring.use_case._clock,
    )
    result = use_case.execute(
        ConfirmMonthlyPlanCommand(
            plan_id=plan.plan_id.value, actor_id=ActorId("teacher_001")
        )
    )
    assert result.plan.status is PlanStatus.CONFIRMED
    assert result.plan.constraint_assessments[0].verification is (
        ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    )


def test_confirmed_llm_plan_is_read_only():
    from ssuksak.planning.application.confirm_monthly_plan import (
        ConfirmMonthlyPlan,
        ConfirmMonthlyPlanCommand,
    )
    from ssuksak.planning.application.edit_monthly_plan_item import (
        EditMonthlyPlanItem,
    )
    from ssuksak.planning.application.monthly_dto import (
        EditMonthlyPlanItemCommand,
        MonthlyCellAddress,
    )
    from ssuksak.planning.domain.identifiers import ActorId

    wiring, plan = llm_plan()
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
                    section_key="outdoor_play",
                    week_id=outdoor_items(plan)[0].week_id.value,
                ),
                new_value="확정 후 수정",
                actor_id=ActorId("teacher_001"),
            )
        )
