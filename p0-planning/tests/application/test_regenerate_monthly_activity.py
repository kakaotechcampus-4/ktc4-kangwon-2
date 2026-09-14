"""outdoor_play Cell Regenerate 검증 (M2-D).

검증 축:
- DRAFT Plan의 outdoor Cell 하나만 승인 Catalog + M2-B Rule로 재생성한다
- Catalog은 Plan 생성 시 기록된 **정확한 version**으로 pin된다. default fallback 없음
- Activity lineage가 없는 M1 Plan은 BLOCKED
- 후보 0은 Generate와 달리 **차단**이다. 기존 Cell을 지우지 않는다
- 실패는 전부 mutation 0 / save 0
- theme / safety / Confirm / Edit 동작은 바뀌지 않는다
- LLM 0회
"""

from __future__ import annotations

import pytest

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_activity_reference_repository import (
    DEFAULT_ACTIVITY_CATALOG_PATH,
    InMemoryActivityReferenceRepository,
    JsonActivityReferenceRepository,
)
from ssuksak.adapters.monthly_repositories import (
    InMemoryMonthlyPlanRepository,
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
)
from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.dto import CatalogSelector
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.monthly_dto import (
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.regenerate_monthly_plan_item import (
    REGENERATABLE_SECTION_KEYS,
    RegenerateMonthlyPlanItem,
)
from ssuksak.planning.domain.activity_reference import (
    ActivationStatus,
    ActivityCandidate,
    ActivityCatalog,
    ActivityEvidence,
    ActivitySetting,
    ActivityThemeLink,
    CurriculumLink,
    THEME_RELATION_OBSERVED_TOGETHER,
)
from ssuksak.planning.domain.constraint import CellState, ConstraintVerification
from ssuksak.planning.domain.errors import FailureCategory, PlanningError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_plan import ActivityCatalogLineage
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
)

from .test_generate_monthly_activity import (
    ACT_CATALOG_ID,
    ACT_VERSION,
    ACT_SELECTOR,
    OUTDOOR,
    PARENT_THEME_ID,
)
from .test_generate_monthly_plan import (
    CATALOG_VERSION,
    CLASSROOM,
    NOW,
    build_parent,
    command,
)

ACTOR = ActorId("teacher_m2d_001")
NEXT_VERSION = "test-activity-reference-v2"
"""Production default가 앞으로 나아가도 기존 Plan은 따라가지 않아야 한다."""


# ------------------------------------------------------------------ 고정 fixture


def candidate(
    activity_id: str,
    label: str,
    *,
    version: str = ACT_VERSION,
    months: tuple[int, ...] = (9,),
    ages: tuple[int, ...] = (4,),
    theme_ids: tuple[str, ...] = (),
    domains: tuple[str, ...] = (),
    evidence_count: int = 1,
) -> ActivityCandidate:
    return ActivityCandidate(
        activity_id=activity_id,
        label=label,
        supported_ages=ages,
        allow_mixed_age=True,
        mixed_age_requires_all_supported=True,
        applicable_months=months,
        placement_slots=(OUTDOOR,),
        setting=ActivitySetting.OUTDOOR,
        source_version=version,
        theme_links=tuple(
            ActivityThemeLink(
                theme_id=t,
                relation=THEME_RELATION_OBSERVED_TOGETHER,
                theme_catalog_version=CATALOG_VERSION,
            )
            for t in theme_ids
        ),
        curriculum_links=tuple(
            CurriculumLink(source_id=f"nuri_{d}", domain=d, source_page=10)
            for d in domains
        ),
        evidence=tuple(
            ActivityEvidence(
                origin_id=f"{activity_id}.origin.{n}",
                page=n + 1,
                age_scope=ages,
                observed_month=months[0],
                observed_label=f"{months[0]}월 관찰 활동",
                observed_section=OUTDOOR,
                observed_source_label="바깥놀이",
            )
            for n in range(evidence_count)
        ),
    )


def catalog(
    *candidates: ActivityCandidate,
    version: str = ACT_VERSION,
    activation: ActivationStatus = ActivationStatus.HUMAN_APPROVED,
) -> ActivityCatalog:
    return ActivityCatalog(
        catalog_id=ACT_CATALOG_ID,
        catalog_version=version,
        activation_status=activation,
        activities=tuple(candidates),
    )


class BrokenActivityRepository:
    def __init__(self) -> None:
        self.calls = 0

    def get_catalog(self, catalog_id: str, catalog_version: str):
        self.calls += 1
        raise RuntimeError("catalog file is corrupted")


DEFAULT_POOL = (
    candidate("act_a", "가을 산책", evidence_count=4),
    candidate("act_b", "낙엽 모으기", evidence_count=3),
    candidate("act_c", "사방치기", evidence_count=2),
    candidate("act_d", "무궁화 꽃이 피었습니다", evidence_count=1),
    candidate("act_e", "모래놀이", evidence_count=1),
    candidate("act_f", "동대문 놀이", evidence_count=1),
)
"""주차 5개보다 후보가 하나 많아 대안 선택이 관찰된다."""


class Harness:
    """Generate와 Regenerate가 같은 Plan Repository를 공유하는 최소 조립."""

    def __init__(
        self,
        *,
        generate_activities=None,
        regenerate_activities="same",
        with_activity_catalog: bool = True,
    ) -> None:
        self.yearly = InMemoryPlanRepository()
        self.yearly.save(build_parent())
        self.monthly = InMemoryMonthlyPlanRepository()
        self.templates = JsonMonthlyTemplateRepository()
        self.safety = JsonSafetyLegalRuleRepository()
        clock = FixedClock(NOW)
        ids = DeterministicIdGenerator(prefix="m2d")

        if generate_activities is None:
            generate_activities = InMemoryActivityReferenceRepository(
                [catalog(*DEFAULT_POOL)]
            )
        if regenerate_activities == "same":
            regenerate_activities = generate_activities

        self.generate = GenerateMonthlyPlan(
            yearly_plan_repository=self.yearly,
            monthly_plan_repository=self.monthly,
            template_repository=self.templates,
            safety_rule_repository=self.safety,
            clock=clock,
            id_generator=ids,
            optional_context=None,
            activity_reference_repository=generate_activities,
        )
        self.regenerate = RegenerateMonthlyPlanItem(
            monthly_plan_repository=self.monthly,
            template_repository=self.templates,
            clock=clock,
            activity_reference_repository=regenerate_activities,
        )
        self.edit = EditMonthlyPlanItem(
            monthly_plan_repository=self.monthly,
            template_repository=self.templates,
            clock=clock,
        )
        self.confirm = ConfirmMonthlyPlan(
            monthly_plan_repository=self.monthly,
            template_repository=self.templates,
            safety_rule_repository=self.safety,
            clock=clock,
        )
        over = {"activity_catalog": ACT_SELECTOR} if with_activity_catalog else {}
        self.plan = self.generate.execute(command(**over)).plan
        self.saves_after_generate = self.monthly.save_count

    # -------------------------------------------------------------- 도우미

    @property
    def extra_saves(self) -> int:
        return self.monthly.save_count - self.saves_after_generate

    def address(self, week_id: str | None, section_key: str = OUTDOOR):
        return MonthlyCellAddress(
            target_month="2026-09", section_key=section_key, week_id=week_id
        )

    def regen(self, week_id: str | None, section_key: str = OUTDOOR):
        return self.regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=self.plan.plan_id.value,
                address=self.address(week_id, section_key),
                actor_id=ACTOR,
            )
        )

    def snapshot(self) -> dict:
        out = {}
        for section in self.plan.sections:
            for item in section.items:
                key = (
                    section.section_key,
                    item.week_id.value if item.week_id else None,
                )
                out[key] = (
                    item.value,
                    item.cell_state,
                    tuple(
                        (e.source_type, e.source_id, e.source_version)
                        for e in item.evidence
                    ),
                    item.generation.method,
                    item.generation.rule_id,
                    item.generation.rule_version,
                    len(item.audit.events),
                )
        return out

    def plan_level(self) -> tuple:
        return (
            self.plan.status,
            self.plan.template_ref,
            self.plan.parent_lineage,
            self.plan.week_periods,
            self.plan.constraint_assessments,
            self.plan.activity_catalog,
            self.plan.school_year,
            self.plan.classroom_ages,
            len(self.plan.audit.events),
        )


def outdoor_cells(plan):
    return next(s for s in plan.sections if s.section_key == OUTDOOR).items


def activity_id_of(item) -> str | None:
    for source in item.evidence:
        if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE:
            return source.source_id
    return None


# ================================================== 0. 계약 표면


def test_outdoor_is_now_regeneratable_and_safety_is_not():
    assert REGENERATABLE_SECTION_KEYS == frozenset({"theme", OUTDOOR})


def test_generated_plan_records_activity_catalog_lineage():
    h = Harness()
    assert h.plan.activity_catalog == ActivityCatalogLineage(
        catalog_id=ACT_CATALOG_ID, catalog_version=ACT_VERSION
    )


def test_plan_without_activity_catalog_has_no_lineage():
    h = Harness(with_activity_catalog=False)
    assert h.plan.activity_catalog is None


# ================================================== 1. Normal regenerate


def test_regenerate_outdoor_w2_succeeds():
    h = Harness()
    before = h.snapshot()
    target = ("outdoor_play", "2026-09-W2")

    result = h.regen("2026-09-W2")

    after = h.snapshot()
    assert [k for k in before if before[k] != after[k]] == [target]
    assert h.extra_saves == 1
    assert result.activity_regeneration is not None


def test_regenerated_cell_keeps_rule_only_and_activity_rule():
    h = Harness()
    h.regen("2026-09-W2")
    cell = outdoor_cells(h.plan)[1]
    assert cell.cell_state is CellState.FILLED
    assert cell.generation.method is GenerationMethod.RULE_ONLY
    assert cell.generation.rule_id == ACTIVITY_RULE_ID
    assert cell.generation.rule_version == ACTIVITY_RULE_VERSION


def test_regenerated_cell_evidence_is_activity_reference_with_pinned_version():
    h = Harness()
    h.regen("2026-09-W2")
    cell = outdoor_cells(h.plan)[1]
    assert len(cell.evidence) == 1
    ev = cell.evidence[0]
    assert ev.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
    assert ev.source_id == activity_id_of(cell)
    assert ev.source_version == ACT_VERSION


def test_regenerated_value_is_the_canonical_label_unmodified():
    h = Harness()
    result = h.regen("2026-09-W2")
    cell = outdoor_cells(h.plan)[1]
    outcome = result.activity_regeneration
    assert cell.value == outcome.selected_value
    assert cell.value in {c.label for c in DEFAULT_POOL}


def test_siblings_are_untouched():
    h = Harness()
    before = h.snapshot()
    h.regen("2026-09-W3")
    after = h.snapshot()
    for week in ("2026-09-W1", "2026-09-W2", "2026-09-W4", "2026-09-W5"):
        key = ("outdoor_play", week)
        assert after[key] == before[key], week


def test_plan_level_state_is_untouched():
    h = Harness()
    before = h.plan_level()
    h.regen("2026-09-W2")
    assert h.plan_level() == before


def test_theme_and_safety_cells_are_untouched():
    h = Harness()
    before = h.snapshot()
    h.regen("2026-09-W2")
    after = h.snapshot()
    for key in before:
        if key[0] != "outdoor_play":
            assert after[key] == before[key], key


def test_regenerate_appends_a_regenerated_audit_event():
    h = Harness()
    cell = outdoor_cells(h.plan)[1]
    previous_value = cell.value
    previous_count = len(cell.audit.events)

    result = h.regen("2026-09-W2")

    event = cell.audit.events[-1]
    assert len(cell.audit.events) == previous_count + 1
    assert event.event_type is AuditEventType.REGENERATED
    assert event.actor_id == ACTOR
    assert event.item_id == cell.item_id.value
    assert event.plan_id == h.plan.plan_id.value
    assert event.previous_value == previous_value
    assert event.new_value == cell.value
    assert event.new_method is GenerationMethod.RULE_ONLY
    assert event.occurred_at is not None
    assert result.activity_regeneration.previous_value == previous_value


def test_outcome_carries_full_traceability():
    h = Harness()
    cell = outdoor_cells(h.plan)[1]
    previous_id = activity_id_of(cell)

    outcome = h.regen("2026-09-W2").activity_regeneration

    assert outcome.address == h.address("2026-09-W2")
    assert outcome.catalog_id == ACT_CATALOG_ID
    assert outcome.catalog_version == ACT_VERSION
    assert outcome.previous_activity_id == previous_id
    assert outcome.selected_activity_id == activity_id_of(cell)
    assert outcome.rule_id == ACTIVITY_RULE_ID
    assert outcome.rule_version == ACTIVITY_RULE_VERSION
    assert outcome.reason == outcome.trace.reason
    assert outcome.trace.week_id == "2026-09-W2"
    assert outcome.trace.section_key == OUTDOOR


def test_rule_only_regenerate_never_uses_the_llm():
    """RULE_ONLY Plan의 재생성은 LLM을 호출하지 않는다.

    L7에서 `llm_cell_regenerator` 주입 지점이 생겼다(LLM Plan 전용). 따라서
    "주입 지점이 없다"가 아니라 **"주입돼 있어도 쓰지 않는다"**가 이제 지켜야 할
    불변이다. 이쪽이 더 강한 보장이다 (L6 §3.1과 같은 판단).
    """
    h = Harness()
    assert h.regenerate._llm_cells is None

    class ExplodingRegenerator:
        def regenerate(self, **_):  # pragma: no cover - 호출되면 실패한다
            raise AssertionError("RULE_ONLY가 LLM Cell Regenerator를 호출했다")

    h.regenerate._llm_cells = ExplodingRegenerator()
    result = h.regen("2026-09-W2")
    assert result.plan is not None
    assert result.cell_regeneration is None


def test_merged_display_mode_is_not_assumed():
    """outdoor는 주차 Cell이므로 week_id 없는 주소는 거부된다."""
    h = Harness()
    with pytest.raises(PlanningError) as exc:
        h.regen(None)
    assert exc.value.failure_category is FailureCategory.INPUT_VALIDATION
    assert h.extra_saves == 0


# ================================================== 2. Current activity penalty


def test_current_activity_is_penalized_and_an_alternative_is_chosen():
    h = Harness()
    cell = outdoor_cells(h.plan)[1]
    previous_id = activity_id_of(cell)

    outcome = h.regen("2026-09-W2").activity_regeneration

    assert outcome.previous_activity_id == previous_id
    assert outcome.selected_activity_id != previous_id
    assert outcome.activity_changed is True
    assert outcome.trace.is_current_activity is False


def test_current_activity_is_not_hard_excluded():
    """대안이 없으면 현재 Activity가 다시 선택된다. 배제가 아니라 penalty다."""
    only = InMemoryActivityReferenceRepository(
        [catalog(candidate("act_only", "유일한 바깥놀이"))]
    )
    h = Harness(generate_activities=only)
    cell = outdoor_cells(h.plan)[1]
    assert activity_id_of(cell) == "act_only"

    outcome = h.regen("2026-09-W2").activity_regeneration

    assert outcome.selected_activity_id == "act_only"
    assert outcome.trace.is_current_activity is True
    assert outcome.trace.repeat_penalty >= 1


def test_sibling_activities_are_passed_as_used_ids():
    """형제 주차의 Activity는 회피 대상이다. 대상 Cell 자신은 제외된다."""
    h = Harness()
    siblings = {
        activity_id_of(c)
        for i, c in enumerate(outdoor_cells(h.plan))
        if i != 1
    }
    previous_id = activity_id_of(outdoor_cells(h.plan)[1])

    outcome = h.regen("2026-09-W2").activity_regeneration

    assert outcome.selected_activity_id not in siblings
    assert outcome.selected_activity_id != previous_id
    assert outcome.trace.reused_in_month is False


def test_repeat_is_penalty_not_exclusion_when_pool_is_exhausted():
    """후보 5개 = 주차 5개. 회피가 불가능해도 실패하지 않는다."""
    pool = InMemoryActivityReferenceRepository([catalog(*DEFAULT_POOL[:5])])
    h = Harness(generate_activities=pool)
    before = h.snapshot()

    outcome = h.regen("2026-09-W2").activity_regeneration

    assert outcome.selected_activity_id is not None
    assert h.extra_saves == 1
    cell = outdoor_cells(h.plan)[1]
    assert cell.cell_state is CellState.FILLED
    assert cell.value
    # 대상 Cell 외에는 여전히 아무것도 바뀌지 않았다.
    after = h.snapshot()
    assert [k for k in before if before[k] != after[k]] == [
        ("outdoor_play", "2026-09-W2")
    ]


def test_parent_theme_remains_a_ranking_factor():
    pool = InMemoryActivityReferenceRepository(
        [
            catalog(
                candidate("act_plain", "그냥 산책", evidence_count=5),
                candidate("act_theme", "우리나라 놀이", theme_ids=(PARENT_THEME_ID,)),
                candidate("act_other", "다른 놀이"),
            )
        ]
    )
    h = Harness(generate_activities=pool)
    # W1이 theme 연결 후보를 먼저 가져가므로 W2를 재생성해도 theme가 hard filter가
    # 아님을 확인할 수 있다.
    outcome = h.regen("2026-09-W2").activity_regeneration
    assert outcome.trace.parent_theme_id == PARENT_THEME_ID
    assert outcome.selected_activity_id is not None


def test_empty_curriculum_links_stay_neutral():
    h = Harness()
    outcome = h.regen("2026-09-W2").activity_regeneration
    assert outcome.trace.selected_curriculum_domains == ()
    assert outcome.trace.curriculum_repeat_penalty == 0


# ================================================== 3. Same-value 성공


def test_same_value_regenerate_succeeds():
    only = InMemoryActivityReferenceRepository(
        [catalog(candidate("act_only", "유일한 바깥놀이"))]
    )
    h = Harness(generate_activities=only)
    cell = outdoor_cells(h.plan)[1]
    previous_value = cell.value
    audit_before = len(cell.audit.events)

    outcome = h.regen("2026-09-W2").activity_regeneration

    assert cell.value == previous_value
    assert outcome.value_changed is False
    assert outcome.activity_changed is False
    assert cell.cell_state is CellState.FILLED
    assert len(cell.audit.events) == audit_before + 1
    assert cell.audit.events[-1].event_type is AuditEventType.REGENERATED
    assert h.extra_saves == 1


def test_same_value_regenerate_records_the_reason():
    only = InMemoryActivityReferenceRepository(
        [catalog(candidate("act_only", "유일한 바깥놀이"))]
    )
    h = Harness(generate_activities=only)
    outcome = h.regen("2026-09-W2").activity_regeneration
    assert outcome.trace.candidate_count == 1
    assert outcome.reason


# ================================================== 4. Catalog pinning


def _pinned_and_newer() -> InMemoryActivityReferenceRepository:
    """같은 catalog_id의 v1(pin 대상)과 v2(새 default)를 함께 가진 Repository."""
    return InMemoryActivityReferenceRepository(
        [
            catalog(*DEFAULT_POOL),
            catalog(
                candidate("act_new_only", "v2 전용 활동", version=NEXT_VERSION),
                version=NEXT_VERSION,
            ),
        ]
    )


def test_regenerate_uses_the_pinned_version_not_the_newer_one():
    h = Harness(
        generate_activities=InMemoryActivityReferenceRepository([catalog(*DEFAULT_POOL)]),
        regenerate_activities=_pinned_and_newer(),
    )
    outcome = h.regen("2026-09-W2").activity_regeneration
    assert outcome.catalog_version == ACT_VERSION
    assert outcome.selected_activity_id != "act_new_only"
    assert outcome.selected_activity_id in {c.activity_id for c in DEFAULT_POOL}
    assert outdoor_cells(h.plan)[1].evidence[0].source_version == ACT_VERSION


def test_missing_pinned_version_fails_without_falling_back():
    """새 version만 있는 Repository에서 기존 Plan은 재생성되지 않는다."""
    newer_only = InMemoryActivityReferenceRepository(
        [
            catalog(
                candidate("act_new_only", "v2 전용 활동", version=NEXT_VERSION),
                version=NEXT_VERSION,
            )
        ]
    )
    h = Harness(
        generate_activities=InMemoryActivityReferenceRepository([catalog(*DEFAULT_POOL)]),
        regenerate_activities=newer_only,
    )
    before = h.snapshot()

    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2")

    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_pinning_ignores_the_production_default_repository():
    """Repository가 실제 production catalog여도 Plan의 pin을 따른다."""
    h = Harness(
        generate_activities=InMemoryActivityReferenceRepository([catalog(*DEFAULT_POOL)]),
        regenerate_activities=JsonActivityReferenceRepository(
            DEFAULT_ACTIVITY_CATALOG_PATH
        ),
    )
    before = h.snapshot()
    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2")
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_real_approved_catalog_round_trips_generate_and_regenerate():
    real = JsonActivityReferenceRepository(DEFAULT_ACTIVITY_CATALOG_PATH)
    real_selector = CatalogSelector(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
    )
    yearly = InMemoryPlanRepository()
    yearly.save(build_parent())
    monthly = InMemoryMonthlyPlanRepository()
    templates = JsonMonthlyTemplateRepository()
    clock = FixedClock(NOW)
    ids = DeterministicIdGenerator(prefix="m2dreal")
    generate = GenerateMonthlyPlan(
        yearly_plan_repository=yearly,
        monthly_plan_repository=monthly,
        template_repository=templates,
        safety_rule_repository=JsonSafetyLegalRuleRepository(),
        clock=clock,
        id_generator=ids,
        activity_reference_repository=real,
    )
    plan = generate.execute(command(activity_catalog=real_selector)).plan
    assert plan.activity_catalog.catalog_version == "activity-reference-v0.2.1"

    regenerate = RegenerateMonthlyPlanItem(
        monthly_plan_repository=monthly,
        template_repository=templates,
        clock=clock,
        activity_reference_repository=real,
    )
    outcome = regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=MonthlyCellAddress(
                target_month="2026-09", section_key=OUTDOOR, week_id="2026-09-W2"
            ),
            actor_id=ACTOR,
        )
    ).activity_regeneration
    assert outcome.catalog_version == "activity-reference-v0.2.1"
    assert outcome.selected_activity_id.startswith("act_outdoor_")
    assert outdoor_cells(plan)[1].cell_state is CellState.FILLED


# ================================================== 5. Legacy M1 Plan


def test_legacy_plan_without_lineage_is_blocked():
    h = Harness(with_activity_catalog=False)
    before = h.snapshot()

    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2")

    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert exc.value.violated_rule == "regenerate_requires_resolved_candidate_source"
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_legacy_plan_is_not_upgraded_to_the_default_catalog():
    h = Harness(with_activity_catalog=False)
    with pytest.raises(PlanningError):
        h.regen("2026-09-W2")
    assert h.plan.activity_catalog is None
    assert outdoor_cells(h.plan)[1].cell_state is CellState.EMPTY_VALID


# ================================================== 6. Candidate 0


def _april_only_repo() -> InMemoryActivityReferenceRepository:
    """같은 id/version이지만 9월 후보가 없는 Catalog."""
    return InMemoryActivityReferenceRepository(
        [catalog(candidate("act_spring", "봄 산책", months=(4,)))]
    )


def test_zero_candidates_blocks_instead_of_emptying_the_cell():
    h = Harness(regenerate_activities=_april_only_repo())
    before = h.snapshot()
    cell = outdoor_cells(h.plan)[1]
    previous_value = cell.value

    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2")

    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert (
        exc.value.violated_rule
        == "regenerate_requires_at_least_one_eligible_candidate"
    )
    assert cell.value == previous_value
    assert cell.cell_state is CellState.FILLED
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_zero_candidates_keeps_evidence_and_siblings():
    h = Harness(regenerate_activities=_april_only_repo())
    cell = outdoor_cells(h.plan)[1]
    evidence_before = list(cell.evidence)
    with pytest.raises(PlanningError):
        h.regen("2026-09-W2")
    assert cell.evidence == evidence_before
    assert all(c.cell_state is CellState.FILLED for c in outdoor_cells(h.plan))


# ================================================== 7. Reference / Repository 실패


def test_inactive_catalog_blocks_without_mutation():
    pending = InMemoryActivityReferenceRepository(
        [catalog(*DEFAULT_POOL, activation=ActivationStatus.PENDING_HUMAN_REVIEW)]
    )
    h = Harness(regenerate_activities=pending)
    before = h.snapshot()
    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2")
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_repository_error_propagates_without_mutation():
    broken = BrokenActivityRepository()
    h = Harness(regenerate_activities=broken)
    before = h.snapshot()
    with pytest.raises(RuntimeError):
        h.regen("2026-09-W2")
    assert broken.calls == 1
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_missing_repository_blocks_without_mutation():
    h = Harness(regenerate_activities=None)
    before = h.snapshot()
    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2")
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_unknown_catalog_id_blocks_without_mutation():
    other = InMemoryActivityReferenceRepository([])
    h = Harness(regenerate_activities=other)
    before = h.snapshot()
    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2")
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert h.snapshot() == before
    assert h.extra_saves == 0


# ================================================== 8. 기존 동작 보존


def test_theme_regenerate_is_unchanged():
    h = Harness()
    theme = h.plan.section("theme").items[0]
    before_value = theme.value
    before_evidence = list(theme.evidence)

    h.regen(None, section_key="theme")

    assert theme.value == before_value == h.plan.parent_lineage.parent_yearly_value
    assert [
        (e.source_type, e.source_id, e.source_version) for e in theme.evidence
    ] == [(e.source_type, e.source_id, e.source_version) for e in before_evidence]
    assert theme.generation.rule_id != ACTIVITY_RULE_ID
    assert theme.audit.events[-1].event_type is AuditEventType.REGENERATED


def test_theme_regenerate_does_not_receive_an_activity_outcome():
    h = Harness()
    result = h.regen(None, section_key="theme")
    assert result.activity_regeneration is None


def test_safety_regenerate_is_still_blocked():
    h = Harness()
    before = h.snapshot()
    with pytest.raises(PlanningError) as exc:
        h.regen("2026-09-W2", section_key="safety_education")
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert exc.value.violated_rule == "regenerate_requires_resolved_candidate_source"
    assert "배치 source" in str(exc.value)
    assert h.snapshot() == before
    assert h.extra_saves == 0


def test_safety_cells_keep_their_unresolved_meaning():
    h = Harness()
    h.regen("2026-09-W2")
    safety = h.plan.section("safety_education")
    assert all(i.cell_state is CellState.EMPTY_UNRESOLVED for i in safety.items)
    assert all(i.evidence == [] for i in safety.items)
    assert (
        h.plan.constraint_assessments[0].verification
        is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    )


def test_confirmed_plan_blocks_outdoor_regenerate():
    h = Harness()
    h.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=h.plan.plan_id.value, actor_id=ACTOR)
    )
    confirmed_saves = h.monthly.save_count
    before = h.snapshot()

    with pytest.raises(PlanningError):
        h.regen("2026-09-W2")

    assert h.snapshot() == before
    assert h.monthly.save_count == confirmed_saves


def test_edit_still_works_on_a_regenerated_cell():
    h = Harness()
    h.regen("2026-09-W2")
    cell = outdoor_cells(h.plan)[1]

    h.edit.execute(
        EditMonthlyPlanItemCommand(
            plan_id=h.plan.plan_id.value,
            address=h.address("2026-09-W2"),
            new_value="교사가 고친 바깥놀이",
            actor_id=ACTOR,
        )
    )

    assert cell.value == "교사가 고친 바깥놀이"
    assert cell.audit.events[-1].event_type is AuditEventType.TEACHER_EDITED
    assert cell.audit.contains(AuditEventType.REGENERATED)


def test_regenerate_after_teacher_edit_keeps_the_original_activity_evidence():
    """교사 수정은 Evidence를 지우지 않는다(CLAUDE.md §13).

    따라서 재생성 시 `previous_activity_id`는 여전히 원래 Rule이 고른 Activity이고
    `previous_value`는 교사가 쓴 문자열이다. label 역검색을 하지 않는다는 계약이
    여기서 그대로 드러난다.
    """
    h = Harness()
    original_id = activity_id_of(outdoor_cells(h.plan)[1])
    h.edit.execute(
        EditMonthlyPlanItemCommand(
            plan_id=h.plan.plan_id.value,
            address=h.address("2026-09-W2"),
            new_value="교사가 쓴 값",
            actor_id=ACTOR,
        )
    )
    outcome = h.regen("2026-09-W2").activity_regeneration
    assert outcome.previous_activity_id == original_id
    assert outcome.previous_value == "교사가 쓴 값"
    assert outcome.selected_activity_id != original_id
    assert outdoor_cells(h.plan)[1].cell_state is CellState.FILLED


def test_cell_without_activity_evidence_has_no_current_activity():
    """ACTIVITY_REFERENCE Evidence가 없으면 현재 Activity penalty가 없다."""
    h = Harness()
    cell = outdoor_cells(h.plan)[1]
    cell.evidence = []  # Import된 Cell처럼 Activity 근거가 없는 상태
    outcome = h.regen("2026-09-W2").activity_regeneration
    assert outcome.previous_activity_id is None
    assert outcome.trace.is_current_activity is False
    assert outcome.selected_activity_id is not None


def test_weekly_gate_is_unaffected_by_outdoor_regenerate():
    from ssuksak.planning.rules import gates

    h = Harness()
    h.regen("2026-09-W2")
    with pytest.raises(PlanningError):
        gates.require_confirmed_parent_monthly(h.plan)

    h.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=h.plan.plan_id.value, actor_id=ACTOR)
    )
    gates.require_confirmed_parent_monthly(h.plan)


# ================================================== 9. Wiring 최소 검증


def test_dev_wiring_supports_outdoor_regenerate():
    """Composition Root가 실제로 조립 가능한지만 확인한다(M2-E에서 확장)."""
    from ssuksak.dev.monthly_wiring import DEV_ACTOR, build_monthly_wiring
    from ssuksak.planning.application.monthly_dto import GenerateMonthlyPlanCommand

    w = build_monthly_wiring()
    plan = w.generate.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=w.parent_yearly.plan_id.value,
            school_year=w.school_year,
            target_month=w.target_month,
            daycare=w.daycare,
            classroom=w.classroom,
            planning_setup=w.planning_setup,
            template_ref=w.template_ref,
            safety_rule=w.safety_rule,
            catalog=w.catalog,
            activity_catalog=w.activity_catalog,
        )
    ).plan
    before = [i.value for i in outdoor_cells(plan)]

    outcome = w.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=MonthlyCellAddress(
                target_month=w.target_month, section_key=OUTDOOR, week_id="2026-09-W2"
            ),
            actor_id=DEV_ACTOR,
        )
    ).activity_regeneration

    after = [i.value for i in outdoor_cells(plan)]
    assert outcome.catalog_version == "activity-reference-v0.2.1"
    assert after[1] == outcome.selected_value
    assert after[0] == before[0] and after[2:] == before[2:]
