"""Monthly **LLM Planner** Golden harness (L9).

`monthly_harness.py`(Rule-only)를 수정하지 않는다. 확정 Parent Yearly를 만드는
부분만 재사용하고, 나머지는 LLM 경로 전용으로 따로 조립한다.

**결정론이 이 harness의 전부다.** 네트워크도 실제 모델도 쓰지 않는다. FakeLLM에
고정 Proposal을 넣고, Application이 그 Proposal로 **무엇을 하는가**를 고정한다.
실제 GPT 문장은 여기서 검증하지 않는다 — Live Quality Smoke가 사람 관찰로 다룬다.

Fake는 Planner algorithm을 흉내 내지 않는다. 흉내 낸 결과를 Golden이 검증하면
계약이 아니라 Fake를 검증하게 된다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_activity_reference_repository import (
    InMemoryActivityReferenceRepository,
)
from ssuksak.adapters.monthly_repositories import (
    InMemoryMonthlyPlanRepository,
    JsonSafetyLegalRuleRepository,
    production_monthly_template_repository,
)
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
from ssuksak.planning.application.confirm_monthly_plan import (
    ConfirmMonthlyPlan,
    ConfirmMonthlyPlanCommand,
)
from ssuksak.planning.application.dto import (
    CatalogSelector,
    ClassroomContext,
    DaycareContext,
    PlanningSetup,
)
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_dto import (
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    MonthlyGenerationMode,
    RegenerateMonthlyPlanItemCommand,
    SafetyRuleSelector,
)
from ssuksak.planning.application.monthly_llm_cell_regeneration import (
    MonthlyLlmCellRegenerator,
)
from ssuksak.planning.application.monthly_llm_planning import (
    MonthlyContextRequest,
    MonthlyLlmPlanner,
)
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.context import MonthlyContextPacketBuilder
from ssuksak.planning.domain.activity_reference import (
    ActivationStatus,
    ActivityCandidate,
    ActivityCatalog,
    ActivityEvidence,
    ActivitySetting,
)
from ssuksak.planning.domain.identifiers import ActorId, PeriodKey
from ssuksak.planning.domain.monthly_template import TemplateRef
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage
from ssuksak.planning.domain.provenance import AuditEventType
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
from ssuksak.shared.llm.monthly_cell import MonthlyCellRegenerationProposal

from .monthly_harness import (
    CATALOG_ID,
    CATALOG_VERSION,
    CLASSROOM_REF,
    DAYCARE_REF,
    NOW,
    PARENT,
    SAFETY_VERSION,
    TEACHER_ACTOR,
    build_parent_yearly,
)

SUITE_PATH = Path(__file__).resolve().parent / "monthly_llm_cases.json"


def load_suite() -> dict[str, Any]:
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))


SUITE = load_suite()
FROZEN = SUITE["frozen_invariants"]
REFS = SUITE["reference_fixtures"]

TEMPLATE_ID = REFS["template_llm"]["template_id"]
LLM_TEMPLATE_VERSION = REFS["template_llm"]["template_version"]
RULE_ONLY_TEMPLATE_VERSION = REFS["template_rule_only"]["template_version"]
ACT_CATALOG_ID = REFS["activity_catalog"]["catalog_id"]
ACT_CATALOG_VERSION = REFS["activity_catalog"]["catalog_version"]
ACT_SELECTOR = CatalogSelector(ACT_CATALOG_ID, ACT_CATALOG_VERSION)
PLANNER_MODEL = REFS["planner_model"]

CASE_A_MONTH = "2026-06"
CASE_B_MONTH = "2026-07"
AGES = (4,)
OUTDOOR = "outdoor_play"
FOCUS = "focus"


def case(case_id: str) -> dict[str, Any]:
    for c in SUITE["cases"]:
        if c["case_id"] == case_id:
            return c
    raise KeyError(case_id)


# ------------------------------------------------------------ 고정 Fixture


COPYABLE_SOURCE_TEXT = "여름 텃밭에 물 주며 자란 모습 살펴보기"
"""exact-copy 거부를 실제로 태우기 위한 Source 문장.

Golden이 이 문장을 그대로 활동명으로 제안하면 L5 Validator가 막아야 한다.
"""


def _record(rid: str, *, institution: str, text: str, month: int) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=rid,
        source_type=IngestSourceType.INSTITUTION_SAMPLE,
        source_path=f"references/samples/monthly/{institution}.pdf",
        source_sha256=institution.encode().hex().ljust(64, "0")[:64],
        page=1,
        institution_id=institution,
        month=month,
        age_scope=AGES,
        age_evidence_type=AgeEvidenceType.SINGLE_AGE_PAGE,
        monthly_theme=f"{month}월",
        source_section=SourceSection.OUTDOOR_PLAY,
        source_label="바깥놀이",
        activity_text=text,
        setting=Setting.OUTDOOR,
        machine_readability=MachineReadability.TEXT_LAYER,
        reuse_policy=ReusePolicy.CONTEXT_ONLY,
        extraction_quality=ExtractionQuality.VALID,
        extraction_method="table_line_geometry_v1",
    )


GOLDEN_RECORDS = [
    _record("gev_06_1", institution="가어린이집", text="모래밭에서 물길 만들기", month=6),
    _record("gev_06_2", institution="나어린이집", text="그늘에서 비눗방울 불기", month=6),
    _record("gev_06_3", institution="다어린이집", text="빗소리 들으며 걷기", month=6),
    _record("gev_07_1", institution="가어린이집", text=COPYABLE_SOURCE_TEXT, month=7),
    _record("gev_07_2", institution="나어린이집", text="물놀이 도구 가지고 놀기", month=7),
    _record("gev_07_3", institution="다어린이집", text="나무 그늘 아래 쉬어 가기", month=7),
]


def copyable_source_text(month: int) -> str:
    """그 달 Corpus에 **실제로 있는** 문장. exact-copy 거부를 태우는 데 쓴다.

    문자열을 따로 적어 두지 않는 이유는, Fixture record를 고치면 이 값도 함께
    따라와야 하기 때문이다. 어긋나면 "거부됐다"가 아니라 "그냥 통과했다"가 된다.
    """
    return next(r.activity_text for r in GOLDEN_RECORDS if r.month == month)


def _activity(activity_id: str, label: str, *, month: int) -> ActivityCandidate:
    return ActivityCandidate(
        activity_id=activity_id,
        label=label,
        supported_ages=AGES,
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=(month,),
        placement_slots=(OUTDOOR,),
        setting=ActivitySetting.OUTDOOR,
        source_version=ACT_CATALOG_VERSION,
        theme_links=(),
        curriculum_links=(),
        evidence=(
            ActivityEvidence(
                origin_id=f"{activity_id}.origin.0",
                page=1,
                age_scope=AGES,
                observed_month=month,
                observed_label=f"{month}월 관찰 활동",
                observed_section=OUTDOOR,
                observed_source_label="바깥놀이",
            ),
        ),
    )


GOLDEN_ACTIVITIES = tuple(
    _activity(f"gact_{month}_{n}", f"{month}월 바깥놀이 {n}", month=month)
    for month in (6, 7)
    for n in range(1, 8)
)


def activity_repository() -> InMemoryActivityReferenceRepository:
    return InMemoryActivityReferenceRepository(
        [
            ActivityCatalog(
                catalog_id=ACT_CATALOG_ID,
                catalog_version=ACT_CATALOG_VERSION,
                activation_status=ActivationStatus.HUMAN_APPROVED,
                activities=GOLDEN_ACTIVITIES,
            )
        ]
    )


# --------------------------------------------------------------- Fake LLM


class SequencedFakeLLM(FakeLLM):
    """호출 순서대로 미리 정한 Proposal을 돌려준다.

    repair 경로를 결정론적으로 고정하려면 "첫 응답"과 "고친 응답"이 달라야
    한다. Queue가 마르면 마지막 값을 계속 돌려준다 — 고치지 못하는 모델을
    뜻한다.
    """

    def __init__(self, *, mode: FakeLLMMode = FakeLLMMode.POLISH) -> None:
        super().__init__(mode)
        self._monthly_queue: list[object] = []

    def queue_monthly(self, *proposals: object) -> None:
        self._monthly_queue = list(proposals)

    def plan_monthly(self, request):
        if self._monthly_queue:
            self._monthly_proposal = self._monthly_queue.pop(0)
        return super().plan_monthly(request)


class MisconfiguredLLM(FakeLLM):
    """설정이 없는 Adapter를 흉내 낸다.

    `FakeLLMMode.UNAVAILABLE`(일시 장애)과 **다른 실패**다. 둘을 하나로 묶으면
    "잠시 후 다시 시도하세요"를 설정 오류에도 보여 주게 된다.
    """

    def plan_monthly(self, request):
        from ssuksak.shared.llm.port import LLMConfigurationError

        self.monthly_calls.append(request)
        raise LLMConfigurationError("FakeLLM: LLM 설정이 없다")

    def regenerate_monthly_cell(self, request):
        from ssuksak.shared.llm.port import LLMConfigurationError

        self.cell_calls.append(request)
        raise LLMConfigurationError("FakeLLM: LLM 설정이 없다")


# ---------------------------------------------------------------- Harness


class LlmGoldenHarness:
    """LLM Planner 경로 전용 조립.

    Rule-only harness와 달리 `focus`가 활성화된 Template(v0.2.0)과 LLM Planner를
    **명시적으로** 넣는다. 환경을 보고 고르지 않는다.
    """

    def __init__(
        self,
        *,
        llm: FakeLLM | None = None,
        with_planner: bool = True,
    ) -> None:
        self.llm = llm if llm is not None else SequencedFakeLLM()

        self.yearly = InMemoryPlanRepository()
        self.yearly.save(build_parent_yearly())
        self.monthly = InMemoryMonthlyPlanRepository()
        self.activities = activity_repository()
        self.catalog = self.activities.get_catalog(
            ACT_CATALOG_ID, ACT_CATALOG_VERSION
        )

        store = InMemoryInstitutionEvidenceRepository(GOLDEN_RECORDS).get_store()
        self.builder = MonthlyContextPacketBuilder(
            MonthlyEvidenceRetriever(store, activity_catalog=self.catalog),
            store,
            activity_catalog=self.catalog,
        )

        templates = production_monthly_template_repository()
        clock = FixedClock(NOW, advance_seconds=1)

        planner = (
            MonthlyLlmPlanner(
                context_builder=self.builder,
                llm=self.llm,
                planner_model=PLANNER_MODEL,
                activity_catalog=self.catalog,
            )
            if with_planner
            else None
        )
        self.cell_regenerator = (
            MonthlyLlmCellRegenerator(
                context_builder=self.builder,
                llm=self.llm,
                planner_model=PLANNER_MODEL,
            )
            if with_planner
            else None
        )

        self.generate = GenerateMonthlyPlan(
            yearly_plan_repository=self.yearly,
            monthly_plan_repository=self.monthly,
            template_repository=templates,
            safety_rule_repository=JsonSafetyLegalRuleRepository(),
            clock=clock,
            id_generator=DeterministicIdGenerator(prefix="golden_llm"),
            optional_context=None,
            activity_reference_repository=self.activities,
            llm_planner=planner,
        )
        shared = {
            "monthly_plan_repository": self.monthly,
            "template_repository": templates,
            "clock": clock,
        }
        self.edit = EditMonthlyPlanItem(**shared)
        self.regenerate_item = RegenerateMonthlyPlanItem(
            activity_reference_repository=self.activities,
            llm_cell_regenerator=self.cell_regenerator,
            **shared,
        )
        self.confirm = ConfirmMonthlyPlan(
            safety_rule_repository=JsonSafetyLegalRuleRepository(), **shared
        )

    # ---- 조회 편의

    @property
    def monthly_plan_persisted(self) -> bool:
        return self.monthly.save_count > 0

    @property
    def save_count(self) -> int:
        return self.monthly.save_count

    def packet(self, target_month: str):
        """Use Case가 만들 것과 **같은** Packet을 만든다."""
        return self.builder.build(
            MonthlyContextRequest(
                school_year=str(PARENT["school_year"]),
                target_month=PeriodKey(target_month),
                classroom_ages=AGES,
                age_mode="SINGLE",
                parent_lineage=self.lineage(target_month),
                daycare_ref=DAYCARE_REF,
                classroom_ref=CLASSROOM_REF,
            )
        )

    def lineage(self, target_month: str) -> ParentYearlyLineage:
        parent = self.yearly.get(PARENT["plan_id"])
        period = next(
            p for p in parent.month_periods if p.period_key.value == target_month
        )
        anchor = period.theme.evidence[0]
        confirmed = next(
            e for e in parent.audit if e.event_type is AuditEventType.CONFIRMED
        )
        return ParentYearlyLineage(
            parent_yearly_plan_id=parent.plan_id.value,
            parent_yearly_period_key=period.period_key.value,
            parent_yearly_theme_id=anchor.source_id,
            parent_yearly_value=period.theme.value,
            reference_catalog_id=CATALOG_ID,
            reference_version=anchor.source_version or "",
            confirmed_at=confirmed.occurred_at,
            confirmed_by=confirmed.actor_id.value,
        )


# ---------------------------------------------------------------- Command


def generate_command(
    *,
    target_month: str = CASE_A_MONTH,
    template_version: str = LLM_TEMPLATE_VERSION,
    mode: MonthlyGenerationMode = MonthlyGenerationMode.LLM_PLANNER,
) -> GenerateMonthlyPlanCommand:
    return GenerateMonthlyPlanCommand(
        parent_yearly_plan_id=PARENT["plan_id"],
        school_year=PARENT["school_year"],
        target_month=target_month,
        daycare=DaycareContext(daycare_ref=DAYCARE_REF),
        classroom=ClassroomContext(
            classroom_ref=CLASSROOM_REF, ages=frozenset(AGES)
        ),
        planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
        template_ref=TemplateRef(TEMPLATE_ID, template_version),
        safety_rule=SafetyRuleSelector(SAFETY_VERSION),
        catalog=CatalogSelector(CATALOG_ID, CATALOG_VERSION),
        activity_catalog=ACT_SELECTOR,
        generation_mode=mode,
        optional_context_requested={},
    )


MERGED_SECTION_KEYS = frozenset({"theme"})
"""주차 Cell이 아니라 월 단위 병합 Cell인 Section. 주소에 week_id를 넣지 않는다."""


def address(plan, section_key: str, *, week_index: int = 1) -> MonthlyCellAddress:
    week_id = (
        None
        if section_key in MERGED_SECTION_KEYS
        else [w for w in plan.week_periods if w.active][week_index].week_id.value
    )
    return MonthlyCellAddress(
        target_month=plan.target_month.value,
        section_key=section_key,
        week_id=week_id,
    )


def regenerate_command(plan, section_key: str, *, week_index: int = 1, **over):
    return RegenerateMonthlyPlanItemCommand(
        plan_id=plan.plan_id.value,
        address=address(plan, section_key, week_index=week_index),
        actor_id=TEACHER_ACTOR,
        **over,
    )


def edit_command(plan, section_key: str, value: str, *, week_index: int = 1):
    return EditMonthlyPlanItemCommand(
        plan_id=plan.plan_id.value,
        address=address(plan, section_key, week_index=week_index),
        new_value=value,
        actor_id=TEACHER_ACTOR,
    )


def confirm_command(plan, actor: ActorId = TEACHER_ACTOR):
    return ConfirmMonthlyPlanCommand(plan_id=plan.plan_id.value, actor_id=actor)


# --------------------------------------------------------------- Proposal


def _refs(packet) -> list[str]:
    return sorted(
        {i.ref for i in packet.institution_evidence}
        | {i.ref for i in packet.other_outdoor_evidence}
    )


def reference_only_proposal(packet) -> MonthlyPlanProposal:
    """Case A — 모든 주차를 승인 Catalog에서 고른 Proposal."""
    available = list(packet.reference_activities)
    if len(available) < len(packet.week_slots):
        raise AssertionError(
            "Golden fixture가 주차 수만큼의 승인 활동을 제공하지 못했다. "
            "Fixture를 고쳐라 — 기대값을 낮추지 않는다."
        )
    weeks = [
        ProposedWeek(
            week_id=slot.week_id,
            experience=f"{index}주차 중심 경험을 함께 나눠요.",
            activity=ProposedActivity(
                value=available[index - 1].label,
                origin=ProposedActivityOrigin.REFERENCE,
                reference_activity_id=available[index - 1].activity_id,
                grounding_refs=[],
            ),
        )
        for index, slot in enumerate(packet.week_slots, start=1)
    ]
    return MonthlyPlanProposal(
        theme_id=packet.parent_theme.theme_id,
        month_flow_rationale="관심에서 표현으로 이어지도록 구성했습니다.",
        weeks=weeks,
    )


def mixed_proposal(packet, *, synthesized_value: str | None = None):
    """Case B — REFERENCE와 LLM_SYNTHESIZED가 섞인 Proposal.

    홀수 주차는 승인 Catalog, 짝수 주차는 Evidence를 근거로 새로 쓴 활동이다.

    Args:
        synthesized_value: 새로 쓴 활동명. Source 문장을 그대로 넣으면
            L5 Validator가 막아야 한다 — 그것이 이 인자의 용도다.
    """
    refs = _refs(packet)
    available = list(packet.reference_activities)
    weeks = []
    for index, slot in enumerate(packet.week_slots, start=1):
        if index % 2 == 1 and available:
            chosen = available[((index - 1) // 2) % len(available)]
            activity = ProposedActivity(
                value=chosen.label,
                origin=ProposedActivityOrigin.REFERENCE,
                reference_activity_id=chosen.activity_id,
                grounding_refs=[],
            )
        else:
            activity = ProposedActivity(
                value=(
                    synthesized_value
                    if synthesized_value is not None
                    else f"{index}주차 바깥놀이를 새로 구성했어요"
                ),
                origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
                reference_activity_id=None,
                grounding_refs=[refs[0]],
            )
        weeks.append(
            ProposedWeek(
                week_id=slot.week_id,
                experience=f"{index}주차 중심 경험을 함께 나눠요.",
                activity=activity,
            )
        )
    return MonthlyPlanProposal(
        theme_id=packet.parent_theme.theme_id,
        month_flow_rationale="여름 놀이를 몸으로 경험하도록 구성했습니다.",
        weeks=weeks,
    )


def focus_proposal(plan, value: str, *, week_index: int = 1):
    week = [w for w in plan.week_periods if w.active][week_index]
    return MonthlyCellRegenerationProposal(
        target_week_id=week.week_id.value,
        target_section_key=FOCUS,
        value=value,
        activity_origin=None,
        reference_activity_id=None,
        grounding_refs=[],
    )


def outdoor_synthesized_proposal(
    plan, value: str, refs: list[str], *, week_index: int = 1
):
    week = [w for w in plan.week_periods if w.active][week_index]
    return MonthlyCellRegenerationProposal(
        target_week_id=week.week_id.value,
        target_section_key=OUTDOOR,
        value=value,
        activity_origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
        reference_activity_id=None,
        grounding_refs=refs,
    )


def outdoor_reference_proposal(
    plan, activity_id: str, label: str, *, week_index: int = 1
):
    week = [w for w in plan.week_periods if w.active][week_index]
    return MonthlyCellRegenerationProposal(
        target_week_id=week.week_id.value,
        target_section_key=OUTDOOR,
        value=label,
        activity_origin=ProposedActivityOrigin.REFERENCE,
        reference_activity_id=activity_id,
        grounding_refs=[],
    )


# --------------------------------------------------------------- 실행 편의


def generate(harness: LlmGoldenHarness, *, target_month: str = CASE_A_MONTH, **over):
    """Case A 기본 조건으로 DRAFT Monthly Plan 하나를 만든다."""
    packet = harness.packet(target_month)
    harness.llm.set_monthly_proposal(reference_only_proposal(packet))
    return harness.generate.execute(
        generate_command(target_month=target_month, **over)
    )


def section_items(plan, section_key: str):
    return next(s for s in plan.sections if s.section_key == section_key).items


def cell_at(plan, section_key: str, *, week_index: int = 1):
    """주소가 가리키는 Cell 하나. 주소 규칙을 테스트가 다시 쓰지 않게 한다."""
    items = section_items(plan, section_key)
    if section_key in MERGED_SECTION_KEYS:
        return items[0]
    week_id = [w for w in plan.week_periods if w.active][week_index].week_id.value
    return next(i for i in items if i.week_id and i.week_id.value == week_id)


def cell_snapshot(plan) -> dict:
    """Cell 단위 불변성 비교용 스냅샷."""
    return {
        item.item_id.value: (
            item.value,
            item.cell_state,
            item.week_id.value if item.week_id else None,
            item.semantic_key.value,
            len(item.audit.events),
            item.generation.method,
            item.generation.rule_id,
            tuple(
                (e.source_type, e.source_id, e.source_version) for e in item.evidence
            ),
        )
        for item in plan.items
    }
