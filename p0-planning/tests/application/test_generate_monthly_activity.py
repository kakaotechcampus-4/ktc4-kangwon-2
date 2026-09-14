"""GenerateMonthlyPlan ↔ Activity Reference 연결 검증 (M2-C).

검증 축:
- Activity Catalog selector가 있으면 `outdoor_play`가 RULE_ONLY로 채워진다
- 선택은 GenerateMonthlyPlan이 아니라 **M2-B pure rule**이 한다
- 후보 0은 `EMPTY_VALID`다. 실패도 `EMPTY_UNRESOLVED`도 아니다
- Catalog/Repository 실패는 Generate 실패이며 Plan 저장이 0회다
- selector가 없으면 M1과 완전히 동일하게 동작한다
- theme / safety_education 동작은 바뀌지 않는다
- LLM 호출 0회
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
from ssuksak.planning.application.dto import CatalogSelector
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
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
from ssuksak.planning.domain.provenance import (
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
    REASON_NO_ELIGIBLE_CANDIDATE,
    select_activity_for_cell,
)

from .test_generate_monthly_plan import (
    CATALOG_ID,
    CATALOG_VERSION,
    CLASSROOM,
    NOW,
    SAFETY_VERSION,
    TEMPLATE_REF,
    build_parent,
    command,
)

ACT_CATALOG_ID = "test.outdoor-activity-reference"
ACT_VERSION = "test-activity-reference-v1"
ACT_SELECTOR = CatalogSelector(ACT_CATALOG_ID, ACT_VERSION)
OUTDOOR = "outdoor_play"

PARENT_THEME_ID = "yr_theme_09"
"""`build_parent()`가 9월 Theme Evidence에 넣는 source_id."""


# ------------------------------------------------------------------ 고정 fixture


def evidence(
    month: int, *, origin: str, page: int = 1, ages: tuple[int, ...] = (4,)
) -> ActivityEvidence:
    return ActivityEvidence(
        origin_id=origin,
        page=page,
        age_scope=ages,
        observed_month=month,
        observed_label=f"{month}월 관찰 활동",
        observed_section=OUTDOOR,
        observed_source_label="바깥놀이",
    )


def candidate(
    activity_id: str,
    label: str,
    *,
    months: tuple[int, ...] = (9,),
    ages: tuple[int, ...] = (4,),
    setting: ActivitySetting = ActivitySetting.OUTDOOR,
    slots: tuple[str, ...] = (OUTDOOR,),
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
        placement_slots=slots,
        setting=setting,
        source_version=ACT_VERSION,
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
            evidence(
                months[0],
                origin=f"{activity_id}.origin.{n}",
                page=n + 1,
                ages=ages,
            )
            for n in range(evidence_count)
        ),
    )


def catalog(
    *candidates: ActivityCandidate,
    activation: ActivationStatus = ActivationStatus.HUMAN_APPROVED,
) -> ActivityCatalog:
    return ActivityCatalog(
        catalog_id=ACT_CATALOG_ID,
        catalog_version=ACT_VERSION,
        activation_status=activation,
        activities=tuple(candidates),
    )


class BrokenActivityRepository:
    """Catalog 파일이 깨졌을 때처럼 조회 자체가 실패하는 Repository."""

    def __init__(self) -> None:
        self.calls = 0

    def get_catalog(self, catalog_id: str, catalog_version: str):
        self.calls += 1
        raise RuntimeError("catalog file is corrupted")


class Wiring:
    """M1 Wiring과 같은 구성에 ActivityReferenceRepository만 더한다."""

    def __init__(self, *, activities=None, parent=None) -> None:
        self.yearly = InMemoryPlanRepository()
        self.yearly.save(parent if parent is not None else build_parent())
        self.monthly = InMemoryMonthlyPlanRepository()
        self.activities = activities
        self.use_case = GenerateMonthlyPlan(
            yearly_plan_repository=self.yearly,
            monthly_plan_repository=self.monthly,
            template_repository=JsonMonthlyTemplateRepository(),
            safety_rule_repository=JsonSafetyLegalRuleRepository(),
            clock=FixedClock(NOW),
            id_generator=DeterministicIdGenerator(prefix="m2c"),
            optional_context=None,
            activity_reference_repository=activities,
        )


def repo(*candidates, activation=ActivationStatus.HUMAN_APPROVED):
    return InMemoryActivityReferenceRepository([catalog(*candidates, activation=activation)])


def run(*candidates, activation=ActivationStatus.HUMAN_APPROVED, **over):
    w = Wiring(activities=repo(*candidates, activation=activation))
    result = w.use_case.execute(command(activity_catalog=ACT_SELECTOR, **over))
    return w, result


def outdoor_items(plan):
    section = next(s for s in plan.sections if s.section_key == OUTDOOR)
    return section.items


# ================================================== 1. 생성 (FILLED 경로)


def test_outdoor_cells_are_filled_from_the_activity_catalog():
    _, result = run(
        candidate("act_a", "가을 산책"),
        candidate("act_b", "낙엽 모으기"),
        candidate("act_c", "사방치기"),
        candidate("act_d", "무궁화 꽃이 피었습니다"),
        candidate("act_e", "모래놀이"),
    )
    items = outdoor_items(result.plan)
    assert len(items) == 5  # 2026-09 canonical week 5개
    assert all(i.cell_state is CellState.FILLED for i in items)
    assert all(i.value for i in items)


def test_each_cell_holds_exactly_one_activity_label():
    """여러 활동을 한 문자열로 이어 붙이지 않는다."""
    labels = {"가을 산책", "낙엽 모으기", "사방치기", "무궁화 꽃이 피었습니다", "모래놀이"}
    _, result = run(*[candidate(f"act_{i}", label) for i, label in enumerate(sorted(labels))])
    for item in outdoor_items(result.plan):
        assert item.value in labels
        for separator in (",", "/", "·", ";", "\n"):
            assert separator not in item.value


def test_filled_cell_uses_rule_only_with_the_m2_b_rule_id():
    _, result = run(candidate("act_a", "가을 산책"))
    for item in outdoor_items(result.plan):
        assert item.generation.method is GenerationMethod.RULE_ONLY
        assert item.generation.rule_id == ACTIVITY_RULE_ID
        assert item.generation.rule_version == ACTIVITY_RULE_VERSION


def test_filled_cell_evidence_points_to_activity_reference():
    _, result = run(candidate("act_a", "가을 산책"))
    for item in outdoor_items(result.plan):
        assert len(item.evidence) == 1
        ev = item.evidence[0]
        assert ev.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
        assert ev.source_id == "act_a"
        assert ev.source_version == ACT_VERSION


def test_audit_records_the_generated_activity_value():
    _, result = run(candidate("act_a", "가을 산책"))
    for item in outdoor_items(result.plan):
        created = item.audit.events[0]
        assert created.new_value == item.value
        assert created.new_method is GenerationMethod.RULE_ONLY


def test_run_reports_catalog_identity_and_counts():
    _, result = run(
        candidate("act_a", "가을 산책"), candidate("act_b", "낙엽 모으기")
    )
    run_ = result.run
    assert run_.activity_catalog_id == ACT_CATALOG_ID
    assert run_.activity_catalog_version == ACT_VERSION
    assert run_.activity_filled_cell_count == 5
    assert run_.activity_unfilled_cell_count == 0
    assert len(run_.activity_selection_traces) == 5


def test_traces_cover_every_outdoor_week_in_order():
    _, result = run(candidate("act_a", "가을 산책"))
    weeks = [i.week_id.value for i in outdoor_items(result.plan)]
    assert [t.week_id for t in result.run.activity_selection_traces] == weeks
    assert all(isinstance(t.week_id, str) for t in result.run.activity_selection_traces)
    assert all(t.section_key == OUTDOOR for t in result.run.activity_selection_traces)
    assert all(t.target_month == "2026-09" for t in result.run.activity_selection_traces)


def test_plan_is_still_a_draft_and_saved_once():
    w, result = run(candidate("act_a", "가을 산책"))
    assert w.monthly.save_count == 1
    assert result.plan.status.value == "DRAFT"


# ================================================== 2. 선택 (M2-B rule 위임)


def test_selection_matches_the_pure_rule_called_directly():
    """Application이 선택을 재구현하지 않았음을 결과 동일성으로 확인한다."""
    cands = [
        candidate("act_a", "가을 산책", evidence_count=1),
        candidate("act_b", "낙엽 모으기", evidence_count=3),
        candidate("act_c", "사방치기", evidence_count=2),
    ]
    _, result = run(*cands)
    catalog_ = catalog(*cands)
    eligible = catalog_.eligible_candidates(
        section_key=OUTDOOR, calendar_month=9, ages=frozenset({4})
    )

    used: set[str] = set()
    domains: dict[str, int] = {}
    expected = []
    for item in outdoor_items(result.plan):
        selection = select_activity_for_cell(
            candidates=eligible,
            target_month="2026-09",
            section_key=OUTDOOR,
            week_id=item.week_id.value,
            parent_theme_id=PARENT_THEME_ID,
            used_activity_ids=frozenset(used),
            used_curriculum_domains=domains,
        )
        chosen = selection.candidate
        assert chosen is not None
        expected.append(chosen.label)
        used.add(chosen.activity_id)
        for link in chosen.curriculum_links:
            domains[link.domain] = domains.get(link.domain, 0) + 1

    assert [i.value for i in outdoor_items(result.plan)] == expected


def test_repeat_is_avoided_while_distinct_candidates_remain():
    _, result = run(
        candidate("act_a", "가을 산책"),
        candidate("act_b", "낙엽 모으기"),
        candidate("act_c", "사방치기"),
        candidate("act_d", "무궁화 꽃이 피었습니다"),
        candidate("act_e", "모래놀이"),
    )
    ids = [e.source_id for i in outdoor_items(result.plan) for e in i.evidence]
    assert len(set(ids)) == 5


def test_repeat_is_a_penalty_not_a_hard_exclusion():
    """후보가 주차 수보다 적어도 실패하지 않고 재사용한다."""
    _, result = run(candidate("act_a", "가을 산책"), candidate("act_b", "낙엽 모으기"))
    items = outdoor_items(result.plan)
    assert all(i.cell_state is CellState.FILLED for i in items)
    ids = [e.source_id for i in items for e in i.evidence]
    assert set(ids) == {"act_a", "act_b"}
    assert len(ids) == 5


def test_parent_theme_link_is_preferred_over_alphabetical_order():
    _, result = run(
        candidate("act_a", "가을 산책"),
        candidate("act_z", "우리나라 전통놀이", theme_ids=(PARENT_THEME_ID,)),
    )
    first = outdoor_items(result.plan)[0]
    assert first.evidence[0].source_id == "act_z"
    assert result.run.activity_selection_traces[0].theme_matched is True
    assert result.run.activity_selection_traces[0].parent_theme_id == PARENT_THEME_ID


def test_empty_curriculum_links_are_neutral_not_excluding():
    """`curriculum_links = []`는 정상이다. 영역 태깅을 생성하지 않는다."""
    _, result = run(candidate("act_a", "가을 산책", domains=()))
    items = outdoor_items(result.plan)
    assert all(i.cell_state is CellState.FILLED for i in items)
    assert all(
        t.selected_curriculum_domains == ()
        for t in result.run.activity_selection_traces
    )


def test_single_institution_evidence_is_not_excluded():
    """institution_count == 1 배제 같은 새 hard filter를 넣지 않는다."""
    _, result = run(candidate("act_a", "가을 산책", evidence_count=1))
    assert all(i.cell_state is CellState.FILLED for i in outdoor_items(result.plan))


def test_theme_mismatch_is_not_excluded():
    _, result = run(candidate("act_a", "가을 산책", theme_ids=("yr_theme_other",)))
    assert all(i.cell_state is CellState.FILLED for i in outdoor_items(result.plan))


# ================================================== 3. 후보 0 → EMPTY_VALID


def test_zero_candidates_leaves_empty_valid_cells():
    _, result = run(candidate("act_a", "봄 산책", months=(4,)))  # 9월 후보 없음
    items = outdoor_items(result.plan)
    assert len(items) == 5
    assert all(i.cell_state is CellState.EMPTY_VALID for i in items)
    assert all(i.value == "" for i in items)
    assert all(i.evidence == [] for i in items)


def test_zero_candidates_is_not_unresolved():
    _, result = run(candidate("act_a", "봄 산책", months=(4,)))
    assert all(
        i.cell_state is not CellState.EMPTY_UNRESOLVED
        for i in outdoor_items(result.plan)
    )


def test_zero_candidates_is_recorded_in_the_run_not_as_failure():
    w, result = run(candidate("act_a", "봄 산책", months=(4,)))
    assert w.monthly.save_count == 1
    assert result.run.activity_unfilled_cell_count == 5
    assert result.run.activity_filled_cell_count == 0
    assert all(
        t.reason == REASON_NO_ELIGIBLE_CANDIDATE
        for t in result.run.activity_selection_traces
    )


def test_zero_candidates_keeps_template_rule_provenance():
    """빈 Cell은 Activity rule_id를 달지 않는다. Template 추적만 남는다."""
    _, result = run(candidate("act_a", "봄 산책", months=(4,)))
    for item in outdoor_items(result.plan):
        assert item.generation.rule_id != ACTIVITY_RULE_ID


def test_age_mismatch_produces_empty_valid_not_failure():
    _, result = run(candidate("act_a", "가을 산책", ages=(3,)))  # 반은 만4세
    assert all(i.cell_state is CellState.EMPTY_VALID for i in outdoor_items(result.plan))


def test_indoor_only_activity_is_not_placed_in_outdoor():
    _, result = run(
        candidate("act_a", "실내 미술", setting=ActivitySetting.INDOOR)
    )
    assert all(i.cell_state is CellState.EMPTY_VALID for i in outdoor_items(result.plan))


def test_empty_catalog_produces_empty_valid_cells():
    w = Wiring(activities=InMemoryActivityReferenceRepository([catalog()]))
    result = w.use_case.execute(command(activity_catalog=ACT_SELECTOR))
    assert all(i.cell_state is CellState.EMPTY_VALID for i in outdoor_items(result.plan))
    assert w.monthly.save_count == 1


# ================================================== 4. Catalog / Repository 실패


def test_unknown_catalog_id_fails_generation():
    w = Wiring(activities=repo(candidate("act_a", "가을 산책")))
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(
            command(activity_catalog=CatalogSelector("no.such.catalog", ACT_VERSION))
        )
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert w.monthly.save_count == 0


def test_unknown_catalog_version_fails_generation():
    w = Wiring(activities=repo(candidate("act_a", "가을 산책")))
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(
            command(activity_catalog=CatalogSelector(ACT_CATALOG_ID, "no-such-version"))
        )
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert w.monthly.save_count == 0


def test_pending_catalog_is_blocked_not_silently_empty():
    w = Wiring(
        activities=repo(
            candidate("act_a", "가을 산책"),
            activation=ActivationStatus.PENDING_HUMAN_REVIEW,
        )
    )
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command(activity_catalog=ACT_SELECTOR))
    assert exc.value.failure_category is FailureCategory.PREREQUISITE_GATE
    assert w.monthly.save_count == 0


def test_broken_repository_fails_generation_without_saving():
    broken = BrokenActivityRepository()
    w = Wiring(activities=broken)
    with pytest.raises(RuntimeError):
        w.use_case.execute(command(activity_catalog=ACT_SELECTOR))
    assert broken.calls == 1
    assert w.monthly.save_count == 0


def test_selector_without_repository_fails_generation():
    w = Wiring(activities=None)
    with pytest.raises(PlanningError) as exc:
        w.use_case.execute(command(activity_catalog=ACT_SELECTOR))
    assert exc.value.failure_category is FailureCategory.REFERENCE_VALIDATION
    assert w.monthly.save_count == 0


def test_catalog_failure_happens_before_duplicate_and_optional_context():
    """Reference Gate 단계이므로 Plan 조회·저장이 전혀 일어나지 않는다."""
    w = Wiring(activities=repo(candidate("act_a", "가을 산책")))
    with pytest.raises(PlanningError):
        w.use_case.execute(
            command(activity_catalog=CatalogSelector(ACT_CATALOG_ID, "nope"))
        )
    assert w.monthly.stored_count == 0


# ================================================== 5. 기존 동작 보존


def test_without_selector_outdoor_stays_empty_valid():
    w = Wiring(activities=repo(candidate("act_a", "가을 산책")))
    result = w.use_case.execute(command())  # activity_catalog 미지정
    assert all(i.cell_state is CellState.EMPTY_VALID for i in outdoor_items(result.plan))
    assert all(i.evidence == [] for i in outdoor_items(result.plan))


def test_without_selector_run_activity_fields_stay_default():
    w = Wiring(activities=repo(candidate("act_a", "가을 산책")))
    result = w.use_case.execute(command())
    assert result.run.activity_catalog_id is None
    assert result.run.activity_catalog_version is None
    assert result.run.activity_filled_cell_count == 0
    assert result.run.activity_unfilled_cell_count == 0
    assert result.run.activity_selection_traces == ()


def test_without_repository_generation_still_succeeds():
    w = Wiring(activities=None)
    result = w.use_case.execute(command())
    assert w.monthly.save_count == 1
    assert all(i.cell_state is CellState.EMPTY_VALID for i in outdoor_items(result.plan))


def test_theme_section_is_unaffected_by_the_activity_catalog():
    _, with_catalog = run(candidate("act_a", "가을 산책"))
    w = Wiring(activities=None)
    without = w.use_case.execute(command())

    def theme(plan):
        section = next(s for s in plan.sections if s.section_key == "theme")
        item = section.items[0]
        return item.value, item.cell_state, item.generation.rule_id

    assert theme(with_catalog.plan) == theme(without.plan)


def test_safety_education_is_never_linked_to_the_activity_catalog():
    _, result = run(candidate("act_a", "가을 산책", slots=(OUTDOOR, )))
    section = next(s for s in result.plan.sections if s.section_key == "safety_education")
    assert all(i.cell_state is CellState.EMPTY_UNRESOLVED for i in section.items)
    assert all(i.evidence == [] for i in section.items)
    assert all(i.generation.rule_id != ACTIVITY_RULE_ID for i in section.items)


def test_safety_constraint_assessment_is_unchanged():
    _, result = run(candidate("act_a", "가을 산책"))
    assessment = result.plan.constraint_assessments[0]
    assert (
        assessment.verification
        is ConstraintVerification.NOT_VERIFIED_SOURCE_REQUIRED
    )


def test_cell_counts_shift_from_empty_valid_to_filled_only():
    w = Wiring(activities=None)
    baseline = w.use_case.execute(command()).run
    _, filled = run(candidate("act_a", "가을 산책"))
    assert filled.run.generated_cell_count == baseline.generated_cell_count
    assert filled.run.filled_cell_count == baseline.filled_cell_count + 5
    assert filled.run.empty_valid_cell_count == baseline.empty_valid_cell_count - 5
    assert (
        filled.run.empty_unresolved_cell_count == baseline.empty_unresolved_cell_count
    )


def test_rule_only_never_uses_the_llm_planner():
    """RULE_ONLY에서는 LLM 호출이 0회다.

    L6에서 `llm_planner` 주입 지점이 생겼다(generation_mode=LLM_PLANNER 전용).
    따라서 "주입 지점이 없다"가 아니라 **"주입돼 있어도 쓰지 않는다"**가
    이제 지켜야 할 불변이다. 이쪽이 더 강한 보장이다.
    """
    w = Wiring(activities=repo(candidate("act_a", "가을 산책")))
    assert w.use_case._llm_planner is None

    class ExplodingPlanner:
        def plan(self, **_):  # pragma: no cover - 호출되면 테스트가 실패한다
            raise AssertionError("RULE_ONLY가 LLM Planner를 호출했다")

    w.use_case._llm_planner = ExplodingPlanner()
    result = w.use_case.execute(command())
    assert result.run is not None
    assert result.run.generation_mode == "RULE_ONLY"
    assert result.run.llm_invoked is False
    assert result.run.llm_call_count == 0


# ================================================== 6. 승인된 실제 Catalog


def test_real_approved_catalog_fills_september_outdoor_cells():
    real = JsonActivityReferenceRepository(DEFAULT_ACTIVITY_CATALOG_PATH)
    selector_payload = real.get_catalog(
        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
    )
    assert selector_payload is not None and selector_payload.is_active

    w = Wiring(activities=real)
    result = w.use_case.execute(
        command(
            activity_catalog=CatalogSelector(
                selector_payload.catalog_id, selector_payload.catalog_version
            )
        )
    )
    items = outdoor_items(result.plan)
    assert all(i.cell_state is CellState.FILLED for i in items)
    assert len({e.source_id for i in items for e in i.evidence}) == 5
    assert all(
        e.source_version == "activity-reference-v0.2.1"
        for i in items
        for e in i.evidence
    )


def test_real_approved_catalog_does_not_change_theme_or_safety():
    real = JsonActivityReferenceRepository(DEFAULT_ACTIVITY_CATALOG_PATH)
    w = Wiring(activities=real)
    result = w.use_case.execute(
        command(
            activity_catalog=CatalogSelector(
                "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
            )
        )
    )
    by_key = {s.section_key: s for s in result.plan.sections}
    assert by_key["theme"].items[0].cell_state is CellState.FILLED
    assert all(
        i.cell_state is CellState.EMPTY_UNRESOLVED
        for i in by_key["safety_education"].items
    )


def test_reading_the_real_catalog_does_not_modify_it():
    before = DEFAULT_ACTIVITY_CATALOG_PATH.read_bytes()
    w = Wiring(activities=JsonActivityReferenceRepository(DEFAULT_ACTIVITY_CATALOG_PATH))
    w.use_case.execute(
        command(
            activity_catalog=CatalogSelector(
                "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
            )
        )
    )
    assert DEFAULT_ACTIVITY_CATALOG_PATH.read_bytes() == before


# ================================================== 7. 다른 월 / 다른 반


def test_march_2026_has_four_outdoor_cells():
    """주차 수를 4 또는 5로 고정하지 않는다."""
    _, result = run(
        candidate("act_a", "봄 산책", months=(3,)),
        candidate("act_b", "새싹 관찰", months=(3,)),
        target_month="2026-03",
    )
    items = outdoor_items(result.plan)
    assert len(items) == 4
    assert all(i.cell_state is CellState.FILLED for i in items)


def test_mixed_age_classroom_requires_all_supported_ages():
    from ssuksak.planning.application.dto import ClassroomContext

    parent = build_parent()
    w = Wiring(
        activities=repo(candidate("act_a", "가을 산책", ages=(4,))), parent=parent
    )
    result = w.use_case.execute(
        command(
            activity_catalog=ACT_SELECTOR,
            classroom=ClassroomContext(
                classroom_ref=CLASSROOM, ages=frozenset({3, 4})
            ),
        )
    )
    assert all(i.cell_state is CellState.EMPTY_VALID for i in outdoor_items(result.plan))


def test_mixed_age_classroom_accepts_fully_supported_activity():
    from ssuksak.planning.application.dto import ClassroomContext

    w = Wiring(activities=repo(candidate("act_a", "가을 산책", ages=(3, 4))))
    result = w.use_case.execute(
        command(
            activity_catalog=ACT_SELECTOR,
            classroom=ClassroomContext(
                classroom_ref=CLASSROOM, ages=frozenset({3, 4})
            ),
        )
    )
    assert all(i.cell_state is CellState.FILLED for i in outdoor_items(result.plan))


# ================================================== 8. Regenerate 차단 유지


def test_outdoor_regenerate_stays_blocked_even_when_filled():
    """M2-C는 Generate만 연결한다. outdoor Regenerate는 여전히 BLOCKED다."""
    from ssuksak.adapters.monthly_repositories import JsonMonthlyTemplateRepository
    from ssuksak.planning.application.monthly_dto import (
        MonthlyCellAddress,
        RegenerateMonthlyPlanItemCommand,
    )
    from ssuksak.planning.application.regenerate_monthly_plan_item import (
        RegenerateMonthlyPlanItem,
    )
    from ssuksak.planning.domain.identifiers import ActorId

    w, result = run(candidate("act_a", "가을 산책"))
    item = outdoor_items(result.plan)[0]
    assert item.cell_state is CellState.FILLED

    regenerate = RegenerateMonthlyPlanItem(
        monthly_plan_repository=w.monthly,
        template_repository=JsonMonthlyTemplateRepository(),
        clock=FixedClock(NOW),
    )
    with pytest.raises(PlanningError) as exc:
        regenerate.execute(
            RegenerateMonthlyPlanItemCommand(
                plan_id=result.plan.plan_id.value,
                address=MonthlyCellAddress(
                    target_month="2026-09",
                    section_key=OUTDOOR,
                    week_id=item.week_id.value,
                ),
                actor_id=ActorId("teacher_m2c_001"),
            )
        )
    assert exc.value.failure_category is not None
    assert item.value == "가을 산책"  # 대상 Cell이 mutation되지 않았다
