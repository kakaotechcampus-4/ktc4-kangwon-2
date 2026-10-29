"""PLAY_MONTHLY first Core unit: generate a DRAFT from a CONFIRMED play-project yearly plan.

Curriculum and daily-life References are synthetic HUMAN_APPROVED catalogs written here; the
real 누리과정 draft stays PENDING_HUMAN_REVIEW. The legal Rule, Evidence Store, safety
classification and quality table are the approved runtime files, so the life-safety slots run
against real records. No child or teacher name appears in any fixture.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.json_curriculum_reference_repository import JsonCurriculumReferenceRepository
from ssuksak.adapters.json_daily_life_reference_repository import JsonDailyLifeReferenceRepository
from ssuksak.adapters.json_drill_topic_reference_repository import JsonDrillTopicReferenceRepository
from ssuksak.adapters.monthly_reference_repositories import JsonSafetyLegalRuleRepository
from ssuksak.adapters.safety_evidence_classification_repository import (
    JsonSafetyEvidenceClassificationRepository,
)
from ssuksak.adapters.safety_reference_quality_repository import JsonSafetyReferenceQualityRepository
from ssuksak.planning.application.generate_play_monthly_plan import (
    PLAY_MONTHLY_LAYOUT_V0_2,
    GeneratePlayMonthlyPlan,
    GeneratePlayMonthlyPlanCommand,
    PlayMonthlyGenerationError,
)
from ssuksak.planning.application.generate_play_project_plan import PLAY_PROJECT_LAYOUT_V0_2
from ssuksak.planning.application.play_monthly_document import play_monthly_document
from ssuksak.planning.domain.curriculum_reference import CurriculumCatalog, CurriculumContent
from ssuksak.planning.domain.daily_life_reference import DailyLifeCatalog, DailyLifeEntry, DailyLifeKind
from ssuksak.planning.domain.drill_topic_reference import DrillKind, DrillOrigin, DrillTopic, DrillTopicCatalog
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.plan import PlanItem, PlanStatus
from ssuksak.planning.domain.play_monthly_plan import SafetyWeek
from ssuksak.planning.domain.play_project_plan import PlayPeriodRows, PlayProjectYearlyPlan, PlayRow
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)
from ssuksak.planning.domain.safety_placement import SafetyKind
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.evidence.safety_classification import SafetyReferenceKind
from ssuksak.planning.evidence.safety_quality import ReferenceQuality
from ssuksak.planning.planner.contracts import ProposalParseError, ProposalRejectedError, RawLlmResponse
from ssuksak.planning.planner.play_monthly import (
    PLAY_MONTHLY_PROMPT_VERSION,
    PLAY_MONTHLY_REPAIR_PROMPT_VERSION,
)

T0 = datetime(2027, 2, 1, tzinfo=UTC)
LEGAL = "child-welfare-act-decree-annex6-2022-06-21"
CLASSIFICATION = "safety-evidence-classification-v0.2.0"
QUALITY = "safety-reference-quality-v0.1.0"
SELECTED = ("cand9", "cand2", "cand4", "cand5", "cand7")  # teacher order, not numeric order

CURRICULUM = CurriculumCatalog(
    "test.curriculum",
    "test-curriculum-v1",
    ActivationStatus.HUMAN_APPROVED,
    tuple(CurriculumContent(f"t.{n}", "영역", "범주", f"합성 내용 {n}") for n in range(1, 7)),
)
DAILY = DailyLifeCatalog(
    "test.daily-life",
    "test-daily-life-v1",
    ActivationStatus.HUMAN_APPROVED,
    CURRICULUM.catalog_id,
    CURRICULUM.catalog_version,
    tuple(DailyLifeEntry(f"h{n}", DailyLifeKind.HABIT, "습관", f"합성 습관 {n}", "t.1") for n in range(1, 8))
    + (
        DailyLifeEntry("he1", DailyLifeKind.HEALTH, "건강", "합성 건강 1", "t.2"),
        DailyLifeEntry("he2", DailyLifeKind.HEALTH, "건강", "합성 건강 2", "t.2"),
        DailyLifeEntry("nu1", DailyLifeKind.NUTRITION, "영양", "합성 영양 1", "t.3"),
    ),
)
ALL_MONTHS = tuple(range(1, 13))
DRILLS = DrillTopicCatalog(
    "test.drills",
    "test-drills-v1",
    ActivationStatus.HUMAN_APPROVED,
    CURRICULUM.catalog_id,
    CURRICULUM.catalog_version,
    (DrillOrigin("test.guide", "합성 안내서", "0" * 64, "1-2"),),
    tuple(
        DrillTopic(topic_id, kind, label, f"합성 {label} 상황", "t.4", months, "test.guide")
        for topic_id, kind, label, months in (
            ("fire_a", DrillKind.FIRE, "화재 가", ALL_MONTHS),
            ("quake", DrillKind.DISASTER, "지진", ALL_MONTHS),
            ("fire_b", DrillKind.FIRE, "화재 나", ALL_MONTHS),
            ("fire_c", DrillKind.FIRE, "화재 다", ALL_MONTHS),
            ("fire_d", DrillKind.FIRE, "화재 라", ALL_MONTHS),
            ("snow", DrillKind.DISASTER, "폭설", (12, 1, 2)),
            ("flood", DrillKind.DISASTER, "수해", (6, 7, 8, 9)),
        )
    ),
)


def _item(item_id: str, value: str, evidence=()) -> PlanItem:
    return PlanItem(ItemId(item_id), value, evidence, GenerationMethodDetail(GenerationMethod.RULE_LLM, "y", "v"))


def _parent(*, status=PlanStatus.CONFIRMED, selected=SELECTED, confirmed=True, **changes) -> PlayProjectYearlyPlan:
    learning = (EvidenceSource(EvidenceSourceType.CURRICULUM, "t.1", "v"),)
    periods = tuple(
        PlayPeriodRows(
            period,
            tuple(
                PlayRow(
                    f"cand{n}",
                    _item(f"{period.key}-{n}-name", f"{period.key} 놀이 {n}"),
                    _item(f"{period.key}-{n}-materials", "종이 상자"),
                    _item(f"{period.key}-{n}-support", "자료를 더해 줍니다."),
                    _item(f"{period.key}-{n}-learning", "학습", learning),
                )
                for n in range(1, 11)
            ),
            selected,
        )
        for period in PLAY_PROJECT_LAYOUT_V0_2.periods
    )
    events = [AuditEvent(AuditEventType.CREATED, T0, PlanId("parent-1"), system_actor="test")]
    if confirmed:
        events.append(AuditEvent(AuditEventType.CONFIRMED, T0, PlanId("parent-1"), actor_id=ActorId("teacher-1")))
    values = dict(
        plan_id=PlanId("parent-1"),
        school_year=2027,
        classroom_ref="classroom-test",
        target_ages=frozenset({4, 5}),
        status=status,
        layout_version=PLAY_PROJECT_LAYOUT_V0_2.layout_version,
        periods=periods,
        audit=AuditHistory(tuple(events)),
    )
    return PlayProjectYearlyPlan(**{**values, **changes})


def _valid(request) -> dict:
    ids = sorted(request.allowed_content_ids)
    return {
        "target_month": request.target_month,
        "theme": "봄 길을 걸어요",
        "rationale": "봄에는 바깥에서 새싹과 꽃을 만나는 놀이가 이어질 것으로 예상합니다.",
        "together": [
            {"name": f"함께 놀이 {n}", "description": f"함께 놀이 {n}을 설명해요.", "content_ids": ids[:2], "parent_ref": None}
            for n in range(1, 6)
        ],
        "free_play": [
            {"name": f"자유놀이 {n}", "description": f"자유놀이 {n}을 설명해요.", "content_ids": ids[2:3], "parent_ref": None}
            for n in range(1, 6)
        ],
        # Contains safety words (교통안전 …) on purpose: ordinary here, not leakage.
        "safety": [
            {"slot": s.slot, "text": f"{s.label} 약속을 함께 알아보아요", "refs": [s.allowed[0][0]]}
            for s in request.safety_slots
        ],
        "habits": [
            {"week_id": w, "entry_id": request.habit_entry_ids[i % len(request.habit_entry_ids)]}
            for i, w in enumerate(request.week_ids)
        ],
        "health_entry_id": "he1",
        "nutrition_entry_id": "nu1",
        "drills": [
            {"topic_id": t, "text": f"{n}번째 상황을 가정해 대피 훈련을 해요"}
            for n, t in enumerate(request.drill_topic_ids, 1)
        ],
    }


class _Provider:
    """Fake LLM: a valid response built from the request, changed by the edit for that call."""

    def __init__(self, *edits) -> None:
        self.edits = edits
        self.requests = []

    def generate_play_monthly(self, request):
        self.requests.append(request)
        data = _valid(request)
        index = len(self.requests) - 1
        if index < len(self.edits) and self.edits[index] is not None:
            self.edits[index](data)
        return RawLlmResponse(json.dumps(data, ensure_ascii=False), "fake")


class _Catalogs:
    def __init__(self, *catalogs) -> None:
        self._catalogs = {(c.catalog_id, c.catalog_version): c for c in catalogs}

    def get_catalog(self, catalog_id, catalog_version):
        return self._catalogs.get((catalog_id, catalog_version))


class _Value:
    def __init__(self, value) -> None:
        self.value = value

    def get_legal_rule(self, version):
        return self.value if self.value.legal_rule_version == version else None

    def get_store(self):
        return self.value

    def get_classification(self):
        return self.value

    def get_quality(self):
        return self.value


RULE = JsonSafetyLegalRuleRepository().get_legal_rule(LEGAL)
STORE = JsonInstitutionEvidenceRepository().get_store()
CLASSIFIED = JsonSafetyEvidenceClassificationRepository().get_classification()
QUALITY_TABLE = JsonSafetyReferenceQualityRepository().get_quality()


def _run(
    *edits,
    parent=None,
    curriculum=CURRICULUM,
    daily=DAILY,
    drills=DRILLS,
    rule=RULE,
    classification=CLASSIFIED,
    quality=QUALITY_TABLE,
    **command_changes,
):
    parents = InMemoryPlanRepository()
    parent = _parent() if parent is None else parent
    if parent is not False:
        parents.save(PlanId("parent-1"), parent)
    plans = InMemoryPlanRepository()
    provider = _Provider(*edits)
    use_case = GeneratePlayMonthlyPlan(
        parent_repository=parents,
        plan_repository=plans,
        curriculum_repository=_Catalogs(curriculum),
        daily_life_repository=_Catalogs(daily),
        drill_repository=_Catalogs(drills),
        safety_rule_repository=_Value(rule),
        evidence_repository=_Value(STORE),
        safety_classification_repository=_Value(classification),
        safety_quality_repository=_Value(quality),
        provider=provider,
        clock=FixedClock(datetime(2027, 2, 20, tzinfo=UTC)),
        id_generator=DeterministicIdGenerator(),
    )
    command = GeneratePlayMonthlyPlanCommand(
        **{
            **dict(
                parent_plan_id=PlanId("parent-1"),
                classroom_ref="classroom-test",
                school_year=2027,
                target_month=YearMonth(2027, 4),
                curriculum_catalog_id=CURRICULUM.catalog_id,
                curriculum_catalog_version=CURRICULUM.catalog_version,
                daily_life_catalog_id=DAILY.catalog_id,
                daily_life_catalog_version=DAILY.catalog_version,
                legal_rule_version=LEGAL,
                safety_classification_version=CLASSIFICATION,
                safety_quality_version=QUALITY,
                drill_catalog_id=DRILLS.catalog_id,
                drill_catalog_version=DRILLS.catalog_version,
            ),
            **command_changes,
        }
    )
    return use_case, command, plans, provider, parents


def test_generates_one_draft_with_the_fixed_initial_shape():
    use_case, command, plans, provider, parents = _run()

    plan = use_case.execute(command)

    assert plan.status is PlanStatus.DRAFT and plan.format == "PLAY_MONTHLY"
    assert plans.save_count == 1 and plans.get(plan.plan_id) == plan
    assert parents.save_count == 1  # only the fixture save; the parent is never written
    assert len(provider.requests) == 1
    assert (len(plan.together), len(plan.free_play)) == (5, 5)
    kinds = [c.kind for c in plan.safety_candidates]
    assert kinds == [SafetyKind.STATUTORY] * 6 + [SafetyKind.SUPPLEMENTAL] * 2
    assert [c.category_id for c in plan.safety_candidates[:6]] == [c.category_id for c in RULE.categories]
    # Candidates are kept apart from placement: every week starts unplaced.
    assert [s.week_id for s in plan.safety_weeks] == [w.week_id for w in plan.weeks]
    assert all(s.candidate_item_id is None for s in plan.safety_weeks)
    assert [h.week_id for h in plan.habits] == [w.week_id for w in plan.weeks]
    assert [h.habit.cell.value for h in plan.habits][:2] == ["합성 습관 1", "합성 습관 2"]
    assert (plan.health.cell.value, plan.health.entry_id) == ("합성 건강 1", "he1")
    assert (plan.nutrition.cell.value, plan.nutrition.entry_id) == ("합성 영양 1", "nu1")
    # Teacher-input cells: blank, never generated, each with its own CREATED event.
    assert tuple(t.semantic_key for t in plan.teacher_inputs) == PLAY_MONTHLY_LAYOUT_V0_2.teacher_input_keys
    assert all(t.value == "" and t.generation is None and t.evidence == () for t in plan.teacher_inputs)
    cells = plan.cells()
    assert all(
        [e.event_type for e in c.audit] == [AuditEventType.CREATED] and c.audit.events[0].system_actor for c in cells
    )
    assert len({c.item_id for c in cells}) == len(cells)
    # A list row's semantic key carries its own item id, not its position.
    assert all(a.cell.semantic_key == f"together.{a.cell.item_id.value}" for a in plan.together)
    # The direction and header strings are Rule copies (layout v0.2.0); the rest is RULE_LLM.
    copies = {plan.direction.item_id, *(c.item_id for c in plan.display.cells())}
    generated = [c for c in cells if c.generation is not None and c.item_id not in copies]
    assert {(c.generation.method, c.generation.rule_version) for c in generated} == {
        (GenerationMethod.RULE_LLM, PLAY_MONTHLY_PROMPT_VERSION)
    }
    assert {
        (c.generation.method, c.generation.rule_version) for c in cells if c.item_id in copies and c.generation
    } == {(GenerationMethod.RULE_ONLY, "play-monthly-layout-v0.2.0")}
    assert [e.event_type for e in plan.audit] == [AuditEventType.CREATED]


def test_snapshot_keeps_parent_references_and_request_fingerprint():
    use_case, command, *_ = _run()
    plan = use_case.execute(command)

    lineage = plan.parent.lineage
    assert (lineage.parent_plan_id, lineage.confirmed_by) == (PlanId("parent-1"), ActorId("teacher-1"))
    assert plan.parent.period_key == "m03_m05"
    assert tuple(p.row_key for p in plan.parent.plays) == SELECTED
    assert plan.parent.plays[0].play_name_item_id == ItemId("m03_m05-9-name")
    refs = plan.references
    assert (refs.curriculum_catalog_version, refs.daily_life_catalog_version) == (
        "test-curriculum-v1",
        "test-daily-life-v1",
    )
    assert (refs.legal_rule_version, refs.evidence_store_sha256) == (LEGAL, STORE.content_sha256)
    assert (refs.safety_classification_version, refs.safety_quality_version) == (CLASSIFICATION, QUALITY)
    assert plan.layout.layout_version == "play-monthly-layout-v0.2.0"

    other, emphasized, *_ = _run(emphasized_row_keys=("cand4",))
    assert other.execute(emphasized).references.request_fingerprint != refs.request_fingerprint


def test_only_selected_plays_of_the_season_reach_the_request():
    use_case, command, _, provider, _ = _run(emphasized_row_keys=("cand5",))
    use_case.execute(command)

    payload = json.loads(provider.requests[0].user_content)
    plays = payload["parent_plays"]
    assert [p["ref"] for p in plays] == [f"m03_m05.{key}" for key in SELECTED]
    assert [p["emphasized"] for p in plays] == [False, False, False, True, False]
    assert (plays[0]["materials"], plays[0]["support_direction"]) == ("종이 상자", "자료를 더해 줍니다.")
    content = provider.requests[0].user_content
    assert "m03_m05 놀이 1\"" not in content and "m03_m05 놀이 3" not in content  # unselected
    assert "m06_m08" not in content  # other season


def test_a_row_cites_the_parent_only_when_it_builds_on_one_play():
    def cite(data):
        data["together"][1]["parent_ref"] = "m03_m05.cand4"

    use_case, command, *_ = _run(cite)
    plan = use_case.execute(command)

    cited = plan.together[1]
    parent_sources = [e for e in cited.cell.evidence if e.source_type is EvidenceSourceType.PARENT_PLAN]
    assert [(e.source_id, e.display_name) for e in parent_sources] == [("parent-1", "m03_m05 놀이 4")]
    assert cited.parent_snapshot.parent_item_id == ItemId("m03_m05-4-name")
    assert cited.parent_snapshot.snapshot_value == "m03_m05 놀이 4"
    others = [a for a in plan.together + plan.free_play if a is not cited]
    assert all(a.parent_snapshot is None and a.cell.cites_only(EvidenceSourceType.CURRICULUM) for a in others)


def test_winter_month_uses_the_parent_school_year_and_selection_order():
    use_case, command, *_ = _run(target_month=YearMonth(2028, 1))
    plan = use_case.execute(command)

    assert plan.parent.period_key == "m12_m02" and plan.school_year == 2027
    assert tuple(p.row_key for p in plan.parent.plays) == SELECTED
    assert all(w.week_id.target_month == YearMonth(2028, 1) for w in plan.weeks)


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        (dict(parent=False), "PARENT_NOT_FOUND"),
        (dict(parent="not a plan"), "PARENT_NOT_PLAY_PROJECT"),
        (dict(parent=_parent(status=PlanStatus.DRAFT)), "PARENT_NOT_CONFIRMED"),
        (dict(classroom_ref="classroom-other"), "PARENT_CLASSROOM_MISMATCH"),
        (dict(parent=_parent(school_year=2026)), "PARENT_SCHOOL_YEAR_MISMATCH"),
        (dict(target_month=YearMonth(2028, 3)), "TARGET_MONTH_OUTSIDE_SCHOOL_YEAR"),
        (dict(parent=_parent(layout_version="unknown-layout")), "PARENT_LAYOUT_UNKNOWN"),
        (dict(parent=_parent(selected=SELECTED[:4])), "PARENT_SELECTION_INCOMPLETE"),
        (dict(parent=_parent(confirmed=False)), "PARENT_CONFIRMATION_MISSING"),
        (dict(emphasized_row_keys=("cand1",)), "EMPHASIS_NOT_SELECTED"),
        (dict(emphasized_row_keys=("cand2", "cand2")), "EMPHASIS_NOT_SELECTED"),
    ],
)
def test_parent_gates_reject_before_the_provider(setup, code):
    use_case, command, plans, provider, _ = _run(**setup)

    with pytest.raises(PlayMonthlyGenerationError) as error:
        use_case.execute(command)

    assert error.value.code == code
    assert provider.requests == [] and plans.save_count == 0


def test_a_parent_without_the_target_season_is_rejected():
    parent = _parent()
    parent = replace(parent, periods=tuple(p for p in parent.periods if p.period.key != "m03_m05"))
    use_case, command, plans, provider, _ = _run(parent=parent)

    with pytest.raises(PlayMonthlyGenerationError, match="PARENT_PERIOD_MISSING"):
        use_case.execute(command)
    assert provider.requests == [] and plans.save_count == 0


def _needs_review(classification):
    return replace(
        classification,
        entries=tuple(
            replace(e, kind=SafetyReferenceKind.NEEDS_REVIEW, supplemental_label=None, review_reason="test")
            if e.supplemental_label == "life_safety"
            else e
            for e in classification.entries
        ),
    )


def _excluded(quality):
    return replace(
        quality,
        entries=tuple(
            replace(e, quality=ReferenceQuality.EXCLUDED, topic_group=None, month_scope=None, reason="test")
            if e.quality is ReferenceQuality.USABLE
            else e
            for e in quality.entries
        ),
    )


def _one_topic(quality):
    return replace(
        quality,
        entries=tuple(
            replace(e, topic_group="same") if e.quality is ReferenceQuality.USABLE else e for e in quality.entries
        ),
    )


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        (dict(curriculum=replace(CURRICULUM, activation_status=ActivationStatus.PENDING_HUMAN_REVIEW)),
         "CURRICULUM_REFERENCE_NOT_ACTIVE"),
        (dict(curriculum_catalog_version="test-curriculum-v0"), "CURRICULUM_REFERENCE_NOT_FOUND"),
        (dict(daily=replace(DAILY, activation_status=ActivationStatus.PENDING_HUMAN_REVIEW)),
         "DAILY_LIFE_REFERENCE_NOT_ACTIVE"),
        (dict(daily=replace(DAILY, curriculum_catalog_version="other")), "DAILY_LIFE_CURRICULUM_MISMATCH"),
        (dict(daily=replace(DAILY, entries=DAILY.entries + (
            DailyLifeEntry("x", DailyLifeKind.HABIT, "습관", "합성", "t.99"),))),
         "DAILY_LIFE_UNKNOWN_CONTENT_ID"),
        (dict(daily=replace(DAILY, entries=DAILY.of_kind(DailyLifeKind.HABIT))), "DAILY_LIFE_REFERENCE_INCOMPLETE"),
        (dict(drills=replace(DRILLS, activation_status=ActivationStatus.PENDING_HUMAN_REVIEW)),
         "DRILL_REFERENCE_NOT_ACTIVE"),
        (dict(drill_catalog_version="test-drills-v0"), "DRILL_REFERENCE_NOT_FOUND"),
        (dict(drills=replace(DRILLS, curriculum_catalog_version="other")), "DRILL_CURRICULUM_MISMATCH"),
        (dict(drills=replace(DRILLS, topics=DRILLS.topics + (
            DrillTopic("x", DrillKind.FIRE, "화재", "합성", "t.99", ALL_MONTHS, "test.guide"),))),
         "DRILL_UNKNOWN_CONTENT_ID"),
        (dict(drills=replace(DRILLS, topics=DRILLS.topics[:4])), "DRILL_TOPICS_INSUFFICIENT"),
        (dict(rule=replace(RULE, runtime_active=False)), "SAFETY_RULE_NOT_ACTIVE"),
        (dict(legal_rule_version="other-rule"), "SAFETY_RULE_NOT_FOUND"),
        (dict(quality=replace(QUALITY_TABLE, runtime_active=False)), "SAFETY_EVIDENCE_NOT_ACTIVE"),
        (dict(safety_classification_version="safety-evidence-classification-v0.1.0"),
         "SAFETY_EVIDENCE_VERSION_MISMATCH"),
        (dict(classification=replace(CLASSIFIED, evidence_content_sha256="0" * 64)), "SAFETY_EVIDENCE_STORE_MISMATCH"),
        (dict(classification=_needs_review(CLASSIFIED)), "LIFE_SAFETY_GROUNDING_INSUFFICIENT"),
        (dict(quality=_excluded(QUALITY_TABLE)), "LIFE_SAFETY_GROUNDING_INSUFFICIENT"),
        (dict(quality=_one_topic(QUALITY_TABLE)), "LIFE_SAFETY_GROUNDING_INSUFFICIENT"),
    ],
)
def test_reference_gates_reject_before_the_provider(setup, code):
    use_case, command, plans, provider, _ = _run(**setup)

    with pytest.raises(PlayMonthlyGenerationError) as error:
        use_case.execute(command)

    assert error.value.code == code
    assert provider.requests == [] and plans.save_count == 0


def test_the_real_pending_curriculum_draft_is_rejected_and_stays_pending():
    real = JsonCurriculumReferenceRepository()
    catalog = real.get_catalog("ssuksak.nuri-curriculum-content", "nuri-curriculum-content-v0.1.0")
    assert catalog.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    use_case, command, plans, provider, _ = _run(
        curriculum=catalog,
        curriculum_catalog_id=catalog.catalog_id,
        curriculum_catalog_version=catalog.catalog_version,
    )

    with pytest.raises(PlayMonthlyGenerationError, match="CURRICULUM_REFERENCE_NOT_ACTIVE"):
        use_case.execute(command)
    assert provider.requests == [] and plans.save_count == 0
    assert real.get_catalog(catalog.catalog_id, catalog.catalog_version).activation_status is (
        ActivationStatus.PENDING_HUMAN_REVIEW
    )


@pytest.mark.parametrize("month", range(1, 13))
def test_life_safety_uses_two_distinct_approved_life_safety_topics(month):
    year = 2027 if month >= 3 else 2028
    use_case, command, *_ = _run(target_month=YearMonth(year, month))
    plan = use_case.execute(command)

    life = plan.safety_candidates[6:]
    assert len({c.topic_group for c in life}) == 2
    records = {r.record_id: r for r in STORE.records}
    for candidate in life:
        assert candidate.cell.evidence and candidate.cell.cites_only(EvidenceSourceType.INSTITUTION_SAMPLE)
        for source in candidate.cell.evidence:
            record = records[source.source_id]
            assert source.source_version == STORE.ingestion_version
            assert CLASSIFIED.runtime_reference(record).supplemental_label == "life_safety"
            assert QUALITY_TABLE.usable_topic_group(record) == candidate.topic_group
            if record.month != month:
                assert QUALITY_TABLE.month_independent_topic_group(record) == candidate.topic_group


def test_statutory_candidates_cite_one_official_item_of_their_own_category():
    use_case, command, *_ = _run()
    plan = use_case.execute(command)

    for candidate in plan.safety_candidates[:6]:
        (source,) = candidate.cell.evidence
        assert source.source_type is EvidenceSourceType.SAFETY_RULE
        assert source.source_id == f"annex6:{candidate.category_id}:1"
        assert source.source_version == LEGAL
        assert source.display_name == RULE.category(candidate.category_id).content_items[0]


def _set(path, value):
    def edit(data):
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return edit


def _other_slot_ref(data):
    data["safety"][0]["refs"] = [data["safety"][1]["refs"][0]]


def _duplicate_slot(data):
    data["safety"][1] = dict(data["safety"][0])


def _unknown_week(data):
    data["habits"][0]["week_id"] = "2027-05-W1"


def _duplicate_name(data):
    data["free_play"][0]["name"] = data["together"][0]["name"]


def _six_rows(data):
    data["together"].append({"name": "여섯째 놀이", "description": "설명", "content_ids": ["t.1"], "parent_ref": None})


@pytest.mark.parametrize(
    ("edit", "code"),
    [
        (_set(("together",), []), "ACTIVITY_COUNT"),
        (_six_rows, "ACTIVITY_COUNT"),
        (_set(("together", 0, "content_ids"), ["t.99"]), "UNKNOWN_CONTENT_ID"),
        (_set(("together", 0, "content_ids"), []), "CONTENT_ID_COUNT"),
        (_set(("together", 0, "content_ids"), ["t.1", "t.2", "t.3", "t.4"]), "CONTENT_ID_COUNT"),
        (_set(("together", 0, "parent_ref"), "m03_m05.cand1"), "UNKNOWN_PARENT_REF"),  # not selected
        (_set(("together", 0, "parent_ref"), "m06_m08.cand9"), "UNKNOWN_PARENT_REF"),  # other season
        (_other_slot_ref, "SAFETY_REF"),
        (_set(("safety", 6, "refs"), ["annex6:traffic_safety:1"]), "SAFETY_REF"),
        (_duplicate_slot, "DUPLICATE_SAFETY_SLOT"),
        (_set(("safety", 0, "slot"), "fire_drill"), "UNKNOWN_SAFETY_SLOT"),
        (_set(("safety", 0, "text"), "[교통안전] 길을 건너요"), "SAFETY_LABEL_IN_TEXT"),
        (_unknown_week, "UNKNOWN_WEEK"),
        (_set(("habits", 1, "entry_id"), "h1"), "DUPLICATE_HABIT"),
        (_set(("health_entry_id",), "nu1"), "UNKNOWN_ENTRY"),
        (_duplicate_name, "DUPLICATE_PLAY_NAME"),
        (_set(("target_month",), "2027-05"), "TARGET_MONTH_MISMATCH"),
        (_set(("theme",), "4월 14일 소풍 놀이"), "UNSUPPORTED_FACT"),
        (_set(("rationale",), "홍길동 선생님과 함께하는 놀이를 예상합니다."), "UNSUPPORTED_FACT"),
        (_set(("together", 0, "description"), "4월 14일에 공원에서 하는 놀이입니다."), "UNSUPPORTED_FACT"),
        (_set(("free_play", 2, "description"), "t.3 내용과 연결되는 놀이입니다."), "SOURCE_IDENTIFIER_LEAKAGE"),
        (_set(("drills",), []), "MISSING_DRILL_TOPIC"),
        (_set(("drills", 0, "topic_id"), "snow"), "UNKNOWN_DRILL_TOPIC"),  # not chosen for April
        (_set(("drills", 1, "topic_id"), "fire_a"), "DUPLICATE_DRILL_TOPIC"),
        (_set(("drills", 0, "text"), "4월 14일 오전에 대피 훈련을 해요"), "UNSUPPORTED_FACT"),
        (_set(("drills", 0, "text"), "fire_a 상황을 가정해 대피 훈련을 해요"), "SOURCE_IDENTIFIER_LEAKAGE"),
        (_set(("safety", 0, "text"), "annex6:traffic_safety:1 길을 건너는 약속을 알아보아요"),
         "SOURCE_IDENTIFIER_LEAKAGE"),
        (_set(("together", 0, "name"), "t.1 봄 산책 놀이"), "SOURCE_IDENTIFIER_LEAKAGE"),
        (_set(("rationale",), "m03_m05.cand4 놀이를 이어 가는 달입니다."), "SOURCE_IDENTIFIER_LEAKAGE"),
        (_set(("theme",), "he1 건강한 봄"), "SOURCE_IDENTIFIER_LEAKAGE"),
    ],
)
def test_invalid_output_is_rejected_after_one_failed_repair(edit, code):
    use_case, command, plans, provider, _ = _run(edit, edit)

    with pytest.raises(ProposalRejectedError) as error:
        use_case.execute(command)

    assert code in error.value.validation_codes
    assert len(provider.requests) == 2 and plans.save_count == 0
    assert provider.requests[1].prompt_version == PLAY_MONTHLY_REPAIR_PROMPT_VERSION


@pytest.mark.parametrize(
    "edit",
    [
        _set(("class_notice",), "교사가 쓸 안내"),  # a teacher-input cell is not a response field
        _set(("safety", 0, "week_id"), "2027-04-W1"),  # weekly placement is the teacher's
        _set(("together", 0, "content_ids"), "t.1"),
        _set(("drills", 0, "assembly_place"), "놀이터"),  # place and route are the teacher's
        _set(("free_play", 0, "description"), None),
        lambda data: data["together"][0].pop("description"),
    ],
)
def test_unrequested_fields_are_parse_errors_and_store_nothing(edit):
    use_case, command, plans, provider, _ = _run(edit)

    with pytest.raises(ProposalParseError):
        use_case.execute(command)
    assert len(provider.requests) == 1 and plans.save_count == 0


def test_repair_fixes_only_the_flagged_row():
    use_case, command, plans, provider, _ = _run(_set(("together", 2, "content_ids"), ["t.99"]))

    plan = use_case.execute(command)

    assert plans.save_count == 1 and len(provider.requests) == 2
    repair = json.loads(provider.requests[1].user_content)
    assert repair["issues"] == [{"location": "together[2]", "code": "UNKNOWN_CONTENT_ID"}]
    versions = [a.cell.generation.rule_version for a in plan.together]
    assert versions == [PLAY_MONTHLY_PROMPT_VERSION] * 2 + [PLAY_MONTHLY_REPAIR_PROMPT_VERSION] + [
        PLAY_MONTHLY_PROMPT_VERSION
    ] * 2
    assert plan.theme.generation.rule_version == PLAY_MONTHLY_PROMPT_VERSION
    assert plan.references.prompt_version == PLAY_MONTHLY_PROMPT_VERSION


def test_repair_that_touches_an_unflagged_location_is_rejected():
    use_case, command, plans, provider, _ = _run(
        _set(("together", 2, "content_ids"), ["t.99"]), _set(("theme",), "다른 놀이 주제")
    )

    with pytest.raises(ProposalRejectedError) as error:
        use_case.execute(command)
    assert error.value.validation_codes == ("REPAIR_CHANGED_UNFLAGGED",)
    assert plans.save_count == 0


def test_repair_cannot_launder_a_fact_through_its_own_previous_response():
    invent = _set(("theme",), "4월 14일 소풍 놀이")
    use_case, command, plans, provider, _ = _run(invent, invent)

    with pytest.raises(ProposalRejectedError, match="UNSUPPORTED_FACT"):
        use_case.execute(command)
    assert "4월 14일" in provider.requests[1].user_content  # present in the repair input, still invented
    assert plans.save_count == 0


def test_fact_checks_allow_public_holidays_and_safety_words():
    use_case, command, plans, *_ = _run(
        _set(("theme",), "어린이날 즐거운 놀이"),
        None,
    )
    plan = use_case.execute(command)
    assert plan.theme.value == "어린이날 즐거운 놀이"
    assert any(c.cell.value.startswith("교통안전") for c in plan.safety_candidates)
    assert plans.save_count == 1


def test_domain_rejects_generated_teacher_input_and_unknown_placement():
    use_case, command, *_ = _run()
    plan = use_case.execute(command)
    generated = GenerationMethodDetail(GenerationMethod.RULE_LLM, "x", "v")
    first = plan.teacher_inputs[0]

    with pytest.raises(InvalidDomainValueError):
        replace(first, value="교사 안내")  # a value without generation
    with pytest.raises(InvalidDomainValueError):
        replace(plan, teacher_inputs=(replace(first, value="AI 안내", generation=generated),) + plan.teacher_inputs[1:])
    with pytest.raises(InvalidDomainValueError):
        replace(plan, safety_weeks=(SafetyWeek(plan.weeks[0].week_id, ItemId("unknown")),) + plan.safety_weeks[1:])
    placed = replace(
        plan,
        safety_weeks=(SafetyWeek(plan.weeks[0].week_id, plan.safety_candidates[0].cell.item_id),)
        + plan.safety_weeks[1:],
    )
    assert placed.safety_weeks[0].candidate_item_id == plan.safety_candidates[0].cell.item_id


def test_drill_candidates_are_five_curriculum_topics_and_the_drill_cell_stays_blank():
    use_case, command, _, provider, _ = _run()
    plan = use_case.execute(command)

    # April has no seasonal topic: the five all-month topics in catalog order.
    assert [d.topic_id for d in plan.drill_candidates] == ["fire_a", "quake", "fire_b", "fire_c", "fire_d"]
    for n, candidate in enumerate(plan.drill_candidates, 1):
        (source,) = candidate.cell.evidence
        assert (source.source_type, source.source_id) == (EvidenceSourceType.CURRICULUM, "t.4")
        assert candidate.cell.semantic_key == f"fire_disaster_drill.candidate.{candidate.topic_id}"
        assert candidate.cell.value == f"{n}번째 상황을 가정해 대피 훈련을 해요"
    assert [d.label for d in plan.drill_candidates] == ["화재 가", "지진", "화재 나", "화재 다", "화재 라"]
    (drill_cell,) = [t for t in plan.teacher_inputs if t.semantic_key == "fire_disaster_drill"]
    assert drill_cell.value == "" and drill_cell.generation is None
    assert (plan.references.drill_catalog_id, plan.references.drill_catalog_version) == (
        "test.drills",
        "test-drills-v1",
    )
    payload = json.loads(provider.requests[0].user_content)
    chosen = [d.topic_id for d in plan.drill_candidates]
    assert [t["topic_id"] for t in payload["drill_topics"]] == list(provider.requests[0].drill_topic_ids) == chosen


@pytest.mark.parametrize(
    ("month", "topics"),
    [
        (1, ["snow", "fire_a", "quake", "fire_b", "fire_c"]),
        (7, ["flood", "fire_a", "quake", "fire_b", "fire_c"]),
        (4, ["fire_a", "quake", "fire_b", "fire_c", "fire_d"]),
    ],
)
def test_seasonal_drill_topics_come_first_in_their_months(month, topics):
    year = 2027 if month >= 3 else 2028
    use_case, command, *_ = _run(target_month=YearMonth(year, month))

    assert [d.topic_id for d in use_case.execute(command).drill_candidates] == topics


def test_repair_rewrites_only_the_flagged_drill_sentence():
    use_case, command, plans, provider, _ = _run(_set(("drills", 2, "text"), "4월 14일에 대피해요"))

    plan = use_case.execute(command)

    repair = json.loads(provider.requests[1].user_content)
    assert repair["issues"] == [{"location": "drills:fire_b", "code": "UNSUPPORTED_FACT"}]
    versions = {d.topic_id: d.cell.generation.rule_version for d in plan.drill_candidates}
    assert versions.pop("fire_b") == PLAY_MONTHLY_REPAIR_PROMPT_VERSION
    assert set(versions.values()) == {PLAY_MONTHLY_PROMPT_VERSION}


def test_the_real_drill_draft_loads_pending_and_is_rejected():
    real = JsonDrillTopicReferenceRepository()
    drills = real.get_catalog("ssuksak.emergency-drill-topics", "emergency-drill-topics-v0.1.0")
    assert drills.activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    assert len(drills.for_month(4)) >= PLAY_MONTHLY_LAYOUT_V0_2.drill_candidate_count
    assert {t.content_id for t in drills.topics} == {"nuri2019.1.3.4"}
    use_case, command, plans, provider, _ = _run(
        drills=drills, drill_catalog_id=drills.catalog_id, drill_catalog_version=drills.catalog_version
    )

    with pytest.raises(PlayMonthlyGenerationError, match="DRILL_REFERENCE_NOT_ACTIVE"):
        use_case.execute(command)
    assert provider.requests == [] and plans.save_count == 0


def _real_references(*, approve_daily_life: bool):
    """The real 누리과정 · daily-life · drill files, approved in memory only where a test needs it."""
    daily = JsonDailyLifeReferenceRepository().get_catalog("ssuksak.daily-life", "daily-life-v0.1.0")
    curriculum = JsonCurriculumReferenceRepository().get_catalog(
        daily.curriculum_catalog_id, daily.curriculum_catalog_version
    )
    drills = JsonDrillTopicReferenceRepository().get_catalog(
        "ssuksak.emergency-drill-topics", "emergency-drill-topics-v0.1.0"
    )
    approved = ActivationStatus.HUMAN_APPROVED
    if approve_daily_life:
        daily = replace(daily, activation_status=approved)
    return dict(
        curriculum=replace(curriculum, activation_status=approved),
        daily=daily,
        drills=replace(drills, activation_status=approved),
        curriculum_catalog_id=curriculum.catalog_id,
        curriculum_catalog_version=curriculum.catalog_version,
        daily_life_catalog_id=daily.catalog_id,
        daily_life_catalog_version=daily.catalog_version,
        drill_catalog_id=drills.catalog_id,
        drill_catalog_version=drills.catalog_version,
    )


def test_the_real_daily_life_file_loads_pending_and_is_rejected():
    references = _real_references(approve_daily_life=False)
    assert references["daily"].activation_status is ActivationStatus.PENDING_HUMAN_REVIEW
    use_case, command, plans, provider, _ = _run(**references)

    with pytest.raises(PlayMonthlyGenerationError, match="DAILY_LIFE_REFERENCE_NOT_ACTIVE"):
        use_case.execute(command)
    assert provider.requests == [] and plans.save_count == 0


def test_the_real_daily_life_sentences_are_copied_with_their_entry_and_curriculum_version():
    references = _real_references(approve_daily_life=True)
    daily, curriculum = references["daily"], references["curriculum"]
    health, nutrition = "ssuksak.daily-life.health.02", "ssuksak.daily-life.nutrition.07"
    use_case, command, plans, provider, _ = _run(
        lambda data: data.update(health_entry_id=health, nutrition_entry_id=nutrition), **references
    )

    plan = use_case.execute(command)

    assert provider.requests[0].habit_entry_ids == tuple(e.entry_id for e in daily.of_kind(DailyLifeKind.HABIT))
    assert (plan.references.daily_life_catalog_id, plan.references.daily_life_catalog_version) == (
        "ssuksak.daily-life",
        "daily-life-v0.1.0",
    )
    picked = [(plan.health, health), (plan.nutrition, nutrition), *((h.habit, h.habit.entry_id) for h in plan.habits)]
    for row, entry_id in picked:
        entry = daily.get(entry_id)
        assert (row.entry_id, row.cell.value) == (entry_id, entry.text)
        assert [(s.source_type, s.source_id, s.source_version) for s in row.cell.evidence] == [
            (EvidenceSourceType.CURRICULUM, entry.content_id, curriculum.catalog_version)
        ]
    # The document's [분류] comes from the plan's own catalog version.
    document = play_monthly_document(plan, daily)
    assert [w.habit_label for w in document.weeks] == [daily.get(h.habit.entry_id).label for h in plan.habits]


def test_domain_rejects_duplicate_drill_topics():
    use_case, command, *_ = _run()
    plan = use_case.execute(command)
    first = plan.drill_candidates[0]

    with pytest.raises(InvalidDomainValueError):
        replace(plan, drill_candidates=plan.drill_candidates + (replace(first, cell=plan.drill_candidates[1].cell),))


def test_a_sentence_about_another_topic_is_not_caught_so_the_label_goes_with_it():
    # Known limit: only ids and invented facts are checked. The teacher sees the Rule's label.
    use_case, command, *_ = _run(_set(("drills", 0, "text"), "지진이 나면 책상 아래로 몸을 숨겨요"))
    first = use_case.execute(command).drill_candidates[0]

    assert (first.topic_id, first.label) == ("fire_a", "화재 가")


def test_drill_origins_need_unique_ids_and_sha256_digests():
    with pytest.raises(InvalidDomainValueError):
        DrillOrigin("test.guide", "합성", "not-a-sha256", "1")
    twice = (DrillOrigin("test.guide", "합성", "0" * 64, "1"), DrillOrigin("test.guide", "합성", "1" * 64, "2"))
    with pytest.raises(InvalidDomainValueError):
        replace(DRILLS, origins=twice)


def test_each_activity_pairs_a_document_name_with_an_edit_screen_description():
    use_case, command, *_ = _run()
    plan = use_case.execute(command)

    for activity in plan.together + plan.free_play:
        name, description = activity.cell, activity.description
        assert description.semantic_key == f"{name.semantic_key}.description"
        assert description.item_id != name.item_id and description.evidence == name.evidence
        assert description.value == f"{name.value}을 설명해요."
        assert description.generation.method is GenerationMethod.RULE_LLM
    assert plan.together[0].cell.semantic_key == f"together.{plan.together[0].cell.item_id.value}"


@pytest.mark.parametrize(
    ("second", "versions"),
    [
        # The repair rewrites only the flagged description; the name keeps its first version.
        (_set(("together", 1, "description"), "물이 담긴 통에 여러 재료를 띄워 보는 놀이입니다."), None),
        # Renaming the play while repairing its description is outside the flagged location.
        (_set(("together", 1, "name"), "다른 놀이 이름"), "REPAIR_CHANGED_UNFLAGGED"),
    ],
)
def test_a_description_repair_stays_inside_the_description(second, versions):
    invent = _set(("together", 1, "description"), "4월 14일에 하는 놀이입니다.")

    def repair(data):
        invent(data)
        second(data)

    use_case, command, plans, provider, _ = _run(invent, repair)
    if versions is not None:
        with pytest.raises(ProposalRejectedError) as error:
            use_case.execute(command)
        assert versions in error.value.validation_codes and plans.save_count == 0
        return
    plan = use_case.execute(command)

    issues = json.loads(provider.requests[1].user_content)["issues"]
    assert issues == [{"location": "together[1].description", "code": "UNSUPPORTED_FACT"}]
    row = plan.together[1]
    assert (row.cell.generation.rule_version, row.description.generation.rule_version) == (
        PLAY_MONTHLY_PROMPT_VERSION,
        PLAY_MONTHLY_REPAIR_PROMPT_VERSION,
    )
    assert row.description.value == "물이 담긴 통에 여러 재료를 띄워 보는 놀이입니다."


def test_domain_keeps_a_description_paired_with_its_name():
    use_case, command, *_ = _run()
    plan = use_case.execute(command)
    first, second = plan.together[:2]

    with pytest.raises(InvalidDomainValueError):
        replace(first, description=second.description)


def test_a_repair_that_removes_the_internal_id_is_stored_clean():
    use_case, command, plans, provider, _ = _run(_set(("together", 3, "name"), "t.2 모래 놀이"))

    plan = use_case.execute(command)

    issues = json.loads(provider.requests[1].user_content)["issues"]
    assert issues == [{"location": "together[3]", "code": "SOURCE_IDENTIFIER_LEAKAGE"}]
    assert plans.save_count == 1 and plan.together[3].cell.value == "함께 놀이 4"


def test_theme_and_rationale_cite_the_parent_period_they_were_written_from():
    use_case, command, *_ = _run()
    plan = use_case.execute(command)

    for cell in (plan.theme, plan.rationale):
        (source,) = cell.evidence
        assert (source.source_type, source.source_id, source.source_version) == (
            EvidenceSourceType.PARENT_PLAN,
            "parent-1",
            "m03_m05",
        )
        assert source.display_name == PLAY_PROJECT_LAYOUT_V0_2.periods[0].label
