"""놀이 중심 월간 테스트용 계획안 — 가짜 provider 로 진짜 Use Case 를 돌려 만든다.

원본: p0-planning/tests/application/test_play_monthly_generation.py (CURRICULUM · DAILY · DRILLS ·
_parent · _valid · _Provider · _run). Core 생성 입력이 바뀌면 같이 고친다.
도메인 객체를 손으로 짓지 않는다 — Core 검사를 통과한 값만 쓴다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from ssuksak.adapters.deterministic import FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.monthly_reference_repositories import JsonSafetyLegalRuleRepository
from ssuksak.adapters.safety_evidence_classification_repository import (
    JsonSafetyEvidenceClassificationRepository,
)
from ssuksak.adapters.safety_reference_quality_repository import (
    JsonSafetyReferenceQualityRepository,
)
from ssuksak.planning.application.generate_play_monthly_plan import (
    GeneratePlayMonthlyPlan,
    GeneratePlayMonthlyPlanCommand,
)
from ssuksak.planning.application.generate_play_project_plan import PLAY_PROJECT_LAYOUT_V0_2
from ssuksak.planning.domain.curriculum_reference import CurriculumCatalog, CurriculumContent
from ssuksak.planning.domain.daily_life_reference import (
    DailyLifeCatalog,
    DailyLifeEntry,
    DailyLifeKind,
)
from ssuksak.planning.domain.drill_topic_reference import (
    DrillKind,
    DrillOrigin,
    DrillTopic,
    DrillTopicCatalog,
)
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.plan import PlanItem, PlanStatus
from ssuksak.planning.domain.play_monthly_plan import PlayMonthlyPlan
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
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.planner.contracts import (
    RawLlmResponse,
)

from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import UuidGenerator

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
    tuple(
        DailyLifeEntry(f"h{n}", DailyLifeKind.HABIT, "습관", f"합성 습관 {n}", "t.1")
        for n in range(1, 8)
    )
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
    return PlanItem(
        ItemId(item_id),
        value,
        evidence,
        GenerationMethodDetail(GenerationMethod.RULE_LLM, "y", "v"),
    )


def _parent(
    *, status=PlanStatus.CONFIRMED, selected=SELECTED, confirmed=True, **changes
) -> PlayProjectYearlyPlan:
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
        events.append(
            AuditEvent(
                AuditEventType.CONFIRMED, T0, PlanId("parent-1"), actor_id=ActorId("teacher-1")
            )
        )
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
            {
                "name": f"함께 놀이 {n}",
                "description": f"함께 놀이 {n}을 설명해요.",
                "content_ids": ids[:2],
                "parent_ref": None,
            }
            for n in range(1, 6)
        ],
        "free_play": [
            {
                "name": f"자유놀이 {n}",
                "description": f"자유놀이 {n}을 설명해요.",
                "content_ids": ids[2:3],
                "parent_ref": None,
            }
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


def make_play_monthly(
    classroom_ref: str, school_year: int = 2027, month: int = 4
) -> PlayMonthlyPlan:
    """가짜 provider 로 진짜 `GeneratePlayMonthlyPlan` 을 돌려 Core 검사를 통과한 DRAFT."""
    parents = InMemoryPlanRepository()
    parents.save(PlanId("parent-1"), _parent(classroom_ref=classroom_ref, school_year=school_year))
    plans = InMemoryPlanRepository()
    use_case = GeneratePlayMonthlyPlan(
        parent_repository=parents,
        plan_repository=plans,
        curriculum_repository=_Catalogs(CURRICULUM),
        daily_life_repository=_Catalogs(DAILY),
        drill_repository=_Catalogs(DRILLS),
        safety_rule_repository=_Value(RULE),
        evidence_repository=_Value(STORE),
        safety_classification_repository=_Value(CLASSIFIED),
        safety_quality_repository=_Value(QUALITY_TABLE),
        provider=_Provider(),
        clock=FixedClock(datetime(2027, 2, 20, tzinfo=UTC)),
        id_generator=UuidGenerator(),  # 한 테스트에서 여러 장을 만들어도 plan_ref 가 겹치지 않는다
    )
    return use_case.execute(
        GeneratePlayMonthlyPlanCommand(
            parent_plan_id=PlanId("parent-1"),
            classroom_ref=classroom_ref,
            school_year=school_year,
            target_month=YearMonth(school_year if month >= 3 else school_year + 1, month),
            curriculum_catalog_id=CURRICULUM.catalog_id,
            curriculum_catalog_version=CURRICULUM.catalog_version,
            daily_life_catalog_id=DAILY.catalog_id,
            daily_life_catalog_version=DAILY.catalog_version,
            legal_rule_version=LEGAL,
            safety_classification_version=CLASSIFICATION,
            safety_quality_version=QUALITY,
            drill_catalog_id=DRILLS.catalog_id,
            drill_catalog_version=DRILLS.catalog_version,
        )
    )


def save_play_monthly(session, center_id: int, plan: PlayMonthlyPlan) -> Plan:
    """기존 월간과 같은 저장소 · 코덱으로 `plans` 행(kind='monthly')에 넣는다."""
    PostgresPlanRepository(
        session, center_id=center_id, kind="monthly", plan_type=PlayMonthlyPlan
    ).save(plan.plan_id, plan)
    session.commit()
    return session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))
