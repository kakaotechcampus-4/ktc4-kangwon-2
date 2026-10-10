"""월간 계획안 저장. 진짜 Postgres 에 Core 가 만든 진짜 MonthlyPlan 을 넣고 꺼낸다.

결정 문서 12.6 PR-2 (월간 왕복 · 반 · 월 unique · `plans` revision).

연간(test_plans_repository.py)과 같은 생각이다 — 가짜 계획안을 쓰지 않는다. GenerateMonthlyPlan ·
EditMonthlyPlanItem · RegenerateMonthlyPlanItem · ConfirmMonthlyPlan 이 Postgres 저장소를 직접
읽고 쓰고, 부모 연간도 Postgres 에서, Profile 도 M2 의 Postgres 저장소에서 나온다.

기반 Template v0.1.1 · v0.2.1 은 **사람 승인 대기**다. Profile 은 OD-N11 (A) — 테스트 안에서만
`replace(template, runtime_active=True)` — 로 만든다. 데이터 파일과 운영 코드는 그대로다.
LLM 경로는 네트워크 없는 결정적 provider 로 돈다(p0-planning
`tests/finalization/harness.py` 의 RequestAwareMonthlyLlm 을 줄여 옮겼다).
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.deterministic_theme_text_generator import (
    DeterministicThemeTextGenerator,
)
from ssuksak.adapters.evidence_classification_repository import (
    JsonEvidenceClassificationRepository,
)
from ssuksak.adapters.institution_evidence_repository import JsonInstitutionEvidenceRepository
from ssuksak.adapters.json_activity_reference_repository import JsonActivityReferenceRepository
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository
from ssuksak.adapters.monthly_reference_repositories import (
    JsonMonthlyTemplateRepository,
    JsonSafetyLegalRuleRepository,
    JsonSafetyPlacementPolicyRepository,
)
from ssuksak.adapters.safety_evidence_classification_repository import (
    JsonSafetyEvidenceClassificationRepository,
)
from ssuksak.adapters.safety_reference_quality_repository import (
    JsonSafetyReferenceQualityRepository,
)
from ssuksak.planning.application.confirm_monthly_plan import ConfirmMonthlyPlan
from ssuksak.planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ssuksak.planning.application.edit_monthly_plan_item import EditMonthlyPlanItem
from ssuksak.planning.application.generate_monthly_plan import GenerateMonthlyPlan
from ssuksak.planning.application.generate_yearly_plan import GenerateYearlyPlan
from ssuksak.planning.application.monthly_dto import (
    ActivityCatalogSelector,
    ConfirmMonthlyPlanCommand,
    EditMonthlyPlanItemCommand,
    GenerateMonthlyPlanCommand,
    RegenerateMonthlyPlanItemCommand,
    SafetyRuleSelector,
)
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.application.monthly_support import MonthlyContextPipeline
from ssuksak.planning.application.regenerate_monthly_plan_item import RegenerateMonthlyPlanItem
from ssuksak.planning.application.yearly_dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    GenerateYearlyPlanCommand,
)
from ssuksak.planning.context.builder import ContextPacketBuilder
from ssuksak.planning.domain.errors import InvalidDomainValueError, InvalidStateTransitionError
from ssuksak.planning.domain.identifiers import ActorId, ItemId, PlanId
from ssuksak.planning.domain.monthly_constraint import CellState
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode, MonthlyPlan
from ssuksak.planning.domain.monthly_template import (
    RepeatBy,
    SectionRole,
    SemanticVariant,
    TemplateRef,
)
from ssuksak.planning.domain.monthly_verification import VerificationReport
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import (
    AuditEventType,
    EvidenceSourceType,
    GenerationMethod,
)
from ssuksak.planning.domain.week_period import WeekId
from ssuksak.planning.domain.year_month import YearMonth
from ssuksak.planning.domain.yearly_plan import YearlyPlan
from ssuksak.planning.planner.cell_service import MonthlyCellPlanner
from ssuksak.planning.planner.contracts import MONTHLY_MODEL, RawLlmResponse
from ssuksak.planning.planner.service import MonthlyPlanner

from app.db import engine
from app.features.auth.models import User
from app.features.centers.models import Center, Class
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.template_profiles.models import TemplateProfileVersion
from app.features.template_profiles.repository import PostgresTemplateProfileRepository

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
TEACHER = ActorId("teacher_001")
SEPTEMBER = YearMonth(2026, 9)
PLAIN = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.1.1")
FOCUS = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.2.1")
LABELS = {
    "theme": "주제",
    "week_axis": "주",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
    "focus": "소주제",
}
RULE = MonthlyGenerationMode.RULE_ONLY
LLM = MonthlyGenerationMode.LLM_PLANNER


class ApprovedTemplates:
    """OD-N11 (A): 실제 파일을 읽어 테스트 안에서만 승인 상태로 바꾼다."""

    def __init__(self):
        self._real = JsonMonthlyTemplateRepository()

    def get_template(self, template_id, template_version):
        template = self._real.get_template(template_id, template_version)
        return None if template is None else replace(template, runtime_active=True)


def _grounding_ref(request, section_key: str) -> str | None:
    """이 Section 의 grounding_class 에 맞는 첫 근거 ref."""
    body = json.loads(request.user_content)
    expected = next(
        (
            section.get("grounding_class")
            for section in body["generation_schema"]["sections"]
            if section["section_key"] == section_key
        ),
        None,
    )
    refs = sorted(e["grounding_ref"] for e in body["evidence"] if e["grounding_class"] == expected)
    return refs[0] if refs else None


class RequestAwareMonthlyLlm:
    """요청만 보고 응답을 만든다. 네트워크 없음."""

    def generate_monthly(self, request) -> RawLlmResponse:
        reference_id, reference_label = request.reference_labels[0]

        def cell(key: str, index: int) -> dict:
            if key == "safety_education":  # 안전교육 근거가 없다 — 미해결로 둔다
                return {
                    "section_key": key,
                    "value": "",
                    "unresolved": True,
                    "reference_id": None,
                    "grounding_refs": [],
                }
            if key == "outdoor_play" and index == 1:
                return {
                    "section_key": key,
                    "value": reference_label,
                    "unresolved": False,
                    "reference_id": reference_id,
                    "grounding_refs": [],
                }
            return {
                "section_key": key,
                "value": f"{key} {index}주 놀이",
                "unresolved": False,
                "reference_id": None,
                "grounding_refs": [_grounding_ref(request, key)],
            }

        weekly = [
            s.section_key
            for s in request.template_snapshot.sections
            if s.role is not SectionRole.AXIS and s.repeat_by is RepeatBy.WEEK
        ]
        payload = {
            "target_month": request.target_month.value,
            "month_sections": [
                {
                    "section_key": "theme",
                    "value": request.expected_theme_value,
                    "unresolved": False,
                    "reference_id": request.expected_theme_id,
                    "grounding_refs": [],
                }
            ],
            "weeks": [
                {
                    "week_id": week_id.value,
                    "sections": [
                        cell(key, index)
                        for key in weekly
                        if key == "safety_education"
                        or (key == "outdoor_play" and index == 1)
                        or _grounding_ref(request, key) is not None
                    ],
                }
                for index, week_id in enumerate(request.expected_week_ids, start=1)
            ],
        }
        return RawLlmResponse(json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "fake-1")

    def generate_cell(self, request) -> RawLlmResponse:
        payload = {
            "target_month": request.target_month.value,
            "target_week_id": None
            if request.target_week_id is None
            else request.target_week_id.value,
            "section": {
                "section_key": request.target_section_key,
                "value": f"다시 만든 {request.target_section_key}",
                "unresolved": False,
                "reference_id": None,
                "grounding_refs": [_grounding_ref(request, request.target_section_key)],
            },
        }
        return RawLlmResponse(json.dumps(payload, ensure_ascii=False), MONTHLY_MODEL, "fake-cell-1")


class Planning:
    """한 원 · 한 반의 연간 → 월간 흐름. 모든 저장소가 Postgres 다."""

    def __init__(self, session, center: Center, user: User, classroom: Class, *, ids: str):
        self.session = session
        self.center, self.user, self.classroom = center, user, classroom
        self.yearly = PostgresPlanRepository(
            session, center_id=center.id, kind="annual", plan_type=YearlyPlan
        )
        self.monthly = PostgresPlanRepository(
            session, center_id=center.id, kind="monthly", plan_type=MonthlyPlan
        )
        self.profiles = PostgresTemplateProfileRepository(session, center_id=center.id)
        self.clock = FixedClock(NOW)
        self.yearly_ids = DeterministicIdGenerator(f"{ids}-yearly")
        self.monthly_ids = DeterministicIdGenerator(f"{ids}-monthly")
        self.activities = JsonActivityReferenceRepository()
        self.provider = RequestAwareMonthlyLlm()
        self.context = MonthlyContextPipeline(
            evidence_repository=JsonInstitutionEvidenceRepository(),
            classification_repository=JsonEvidenceClassificationRepository(),
            context_builder=ContextPacketBuilder(),
            safety_classification_repository=JsonSafetyEvidenceClassificationRepository(),
            safety_quality_repository=JsonSafetyReferenceQualityRepository(),
        )

    def confirmed_yearly(self) -> YearlyPlan:
        plan = (
            GenerateYearlyPlan(
                theme_repository=JsonThemeReferenceRepository(),
                plan_repository=self.yearly,
                text_generator=DeterministicThemeTextGenerator(),
                clock=self.clock,
                id_generator=self.yearly_ids,
            )
            .execute(
                GenerateYearlyPlanCommand(
                    school_year=2026,
                    classroom_ref=str(self.classroom.id),
                    target_ages=frozenset({3, 4}),
                    catalog=CatalogSelector(
                        "ssuksak.yearly-theme-reference", "theme-reference-v0.1.2"
                    ),
                )
            )
            .plan
        )
        return ConfirmYearlyPlan(plan_repository=self.yearly, clock=self.clock).execute(
            ConfirmYearlyPlanCommand(plan.plan_id, TEACHER)
        )

    def profile(self, mode: MonthlyGenerationMode):
        """RULE_ONLY 는 v0.1.1(focus 없음), LLM 은 v0.2.1(focus = 소주제)."""
        return self.profiles.start_from_reference(
            ApprovedTemplates(),
            PLAIN if mode is RULE else FOCUS,
            selected_optional_keys=() if mode is RULE else ("focus",),
            display_labels=LABELS,
            focus_variant=None if mode is RULE else SemanticVariant.SUBTHEME,
            actor_id=self.user.id,
        )

    def generate(self, parent, mode, *, month=SEPTEMBER, profile=None) -> MonthlyPlan:
        return (
            GenerateMonthlyPlan(
                parent_plan_repository=self.yearly,
                plan_repository=self.monthly,
                profile_repository=self.profiles,
                # Core 최종 승인 검사(ADR-027)도 OD-N11 (A) 객체로 본다. 실제 파일은 승인 대기다.
                template_repository=ApprovedTemplates(),
                safety_repository=JsonSafetyLegalRuleRepository(),
                activity_repository=self.activities,
                clock=self.clock,
                id_generator=self.monthly_ids,
                context_pipeline=self.context,
                planner=None if mode is RULE else MonthlyPlanner(self.provider),
                safety_placement_repository=JsonSafetyPlacementPolicyRepository(),
            )
            .execute(
                GenerateMonthlyPlanCommand(
                    parent_yearly_plan_id=parent.plan_id,
                    target_month=month,
                    daycare_ref=str(self.center.id),
                    profile_ref=profile or self.profile(mode),
                    safety_rule=SafetyRuleSelector("child-welfare-act-decree-annex6-2022-06-21"),
                    generation_mode=mode,
                    activity_catalog=ActivityCatalogSelector(
                        "ssuksak.outdoor-activity-reference", "activity-reference-v0.2.1"
                    ),
                )
            )
            .plan
        )

    def edit(self, plan_id, item_id, value) -> MonthlyPlan:
        return EditMonthlyPlanItem(
            plan_repository=self.monthly, clock=self.clock, activity_repository=self.activities
        ).execute(EditMonthlyPlanItemCommand(plan_id, item_id, value, TEACHER))

    def regenerate(self, plan_id, item_id) -> MonthlyPlan:
        return (
            RegenerateMonthlyPlanItem(
                plan_repository=self.monthly,
                clock=self.clock,
                activity_repository=self.activities,
                context_pipeline=self.context,
                cell_planner=MonthlyCellPlanner(self.provider),
            )
            .execute(RegenerateMonthlyPlanItemCommand(plan_id, item_id, TEACHER))
            .plan
        )

    def confirm(self, plan_id) -> MonthlyPlan:
        return ConfirmMonthlyPlan(
            plan_repository=self.monthly, clock=self.clock, activity_repository=self.activities
        ).execute(ConfirmMonthlyPlanCommand(plan_id, TEACHER))

    def reload(self, plan_id) -> MonthlyPlan:
        """identity map 을 비우고 DB 에서 다시 읽는다 — 메모리의 객체가 아니라 저장된 JSONB 다."""
        self.session.expunge_all()
        return self.monthly.get(plan_id)

    def row(self, plan_id) -> Plan:
        return self.session.scalar(select(Plan).where(Plan.plan_ref == plan_id.value))


def _center(session, name) -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _user(session, center, email) -> User:
    user = User(
        email=email,
        name="선생",
        password_hash=b"x" * 64,
        password_salt=b"y" * 16,
        center_id=center.id,
    )
    session.add(user)
    session.flush()
    return user


def _class(session, center, name="햇살반") -> Class:
    classroom = Class(
        center_id=center.id,
        name=name,
        school_year=2026,
        age_min=3,
        age_max=4,
        teacher_name="선생",
    )
    session.add(classroom)
    session.flush()
    return classroom


def _planning(session, name, email, *, ids) -> Planning:
    center = _center(session, name)
    return Planning(
        session, center, _user(session, center, email), _class(session, center), ids=ids
    )


@pytest.fixture
def a(db_session) -> Planning:
    return _planning(db_session, "가원", "a@example.com", ids="a")


@pytest.fixture
def b(db_session) -> Planning:
    return _planning(db_session, "나원", "b@example.com", ids="b")


def _cells(plan: MonthlyPlan) -> dict:
    return {cell.item_id: cell for cell in plan.cells}


# ── 저장 · 복원 ───────────────────────────────────────────────────────────


def test_RULE_ONLY_DRAFT_가_Postgres_를_거쳐_그대로_돌아온다(a):
    parent = a.confirmed_yearly()
    profile_ref = a.profile(RULE)
    plan = a.generate(parent, RULE, profile=profile_ref)

    restored = a.reload(plan.plan_id)
    assert restored is not plan
    # 얼어붙은 dataclass 라 == 가 칸을 하나씩 다 본다 — Snapshot · Section · Cell · 근거 · 감사 ·
    # 검증 보고서까지. 하나라도 어긋나면 여기서 걸린다.
    assert restored == plan

    # 타입도 되돌아온다(문자열 · dict · list 로 남지 않는다).
    assert isinstance(restored.plan_id, PlanId)
    assert isinstance(restored.target_month, YearMonth) and restored.target_month == SEPTEMBER
    assert isinstance(restored.target_ages, frozenset) and restored.target_ages == {3, 4}
    assert isinstance(restored.sections, tuple) and isinstance(restored.week_periods, tuple)
    assert restored.status is PlanStatus.DRAFT
    assert restored.generation_mode is RULE
    assert isinstance(restored.verification_report, VerificationReport)
    for cell in restored.cells:
        assert isinstance(cell.item_id, ItemId)
        assert cell.week_id is None or isinstance(cell.week_id, WeekId)
        assert isinstance(cell.cell_state, CellState)
        assert isinstance(cell.evidence, tuple)
    assert {c.item_id for c in restored.cells} == {c.item_id for c in plan.cells}

    # 생성 당시 구조 · Profile · 부모.
    snapshot = restored.template_snapshot
    assert snapshot.profile_ref == profile_ref
    assert {s.section_key: s.repeat_by for s in snapshot.sections} == {
        "theme": RepeatBy.NONE,
        "week_axis": None,
        "outdoor_play": RepeatBy.WEEK,
        "safety_education": RepeatBy.WEEK,
    }
    assert {s.section_key: s.repeat_by for s in restored.sections} == {
        s.section_key: s.repeat_by for s in snapshot.sections
    }
    assert restored.parent_lineage.parent_plan_id == parent.plan_id
    assert restored.parent_lineage == plan.parent_lineage

    # 조회 칸은 본문에서 나온다.
    row = a.row(plan.plan_id)
    assert (row.kind, row.status, row.target_month, row.revision) == (
        "monthly",
        "DRAFT",
        "2026-09",
        1,
    )
    assert (row.center_id, row.classroom_ref, row.school_year) == (
        a.center.id,
        str(a.classroom.id),
        2026,
    )
    assert row.confirmed_at is None


def test_LLM_결과와_근거_Grounding_이_그대로_돌아온다(a):
    plan = a.generate(a.confirmed_yearly(), LLM)
    restored = a.reload(plan.plan_id)

    assert restored == plan
    assert restored.generation_mode is LLM
    assert restored.template_snapshot.section("focus").repeat_by is RepeatBy.WEEK
    methods = {c.generation.method for c in restored.cells if c.generation is not None}
    assert {GenerationMethod.RULE_ONLY, GenerationMethod.RULE_LLM} <= methods
    llm_cell = next(
        c
        for c in restored.cells
        if c.generation and c.generation.method is GenerationMethod.RULE_LLM
    )
    assert (
        llm_cell.generation == _cells(plan)[llm_cell.item_id].generation
    )  # rule_id · rule_version
    sources = {e.source_type for c in restored.cells for e in c.evidence}
    assert {
        EvidenceSourceType.PARENT_PLAN,
        EvidenceSourceType.THEME_REFERENCE,
        EvidenceSourceType.ACTIVITY_REFERENCE,
        EvidenceSourceType.INSTITUTION_SAMPLE,
    } <= sources
    assert restored.verification_report == plan.verification_report
    assert restored.constraint_assessments == plan.constraint_assessments


def test_주차_수와_Section_구성이_달라도_그대로_돌아온다(a):
    """고정 칸 수를 가정하지 않는다. 같은 반의 다른 달 · 다른 Profile."""
    parent = a.confirmed_yearly()
    rule, llm = a.profile(RULE), a.profile(LLM)
    plans = [
        a.generate(parent, mode, month=month, profile=profile)
        for mode, month, profile in (
            (RULE, YearMonth(2026, 9), rule),
            (LLM, YearMonth(2026, 10), llm),
            (RULE, YearMonth(2027, 2), rule),
        )
    ]
    shapes = {(len(p.week_periods), len(p.sections), len(p.cells)) for p in plans}
    assert len({weeks for weeks, _, _ in shapes}) > 1  # 주차 수가 다르다
    assert len({sections for _, sections, _ in shapes}) > 1  # Section 구성이 다르다

    for plan in plans:
        restored = a.reload(plan.plan_id)
        assert restored == plan
        weekly = [s for s in restored.sections if s.repeat_by is RepeatBy.WEEK]
        assert all(len(s.cells) == len(restored.week_periods) for s in weekly)
    assert [a.row(p.plan_id).target_month for p in plans] == ["2026-09", "2026-10", "2027-02"]


# ── 편집 · 재생성 · 확정 후 저장 ────────────────────────────────────────────


def test_칸을_고치면_그_칸만_바뀌어_저장된다(a):
    plan = a.generate(a.confirmed_yearly(), RULE)
    target = plan.section("outdoor_play").cells[0]

    a.edit(plan.plan_id, target.item_id, "교사가 쓴 바깥놀이")
    restored = a.reload(plan.plan_id)

    edited = _cells(restored)[target.item_id]
    assert edited.value == "교사가 쓴 바깥놀이"
    assert edited.audit.events[-1].event_type is AuditEventType.TEACHER_EDITED
    assert edited.audit.events[-1].actor_id == TEACHER
    assert (edited.generation, edited.evidence) == (target.generation, target.evidence)
    before, after = _cells(plan), _cells(restored)
    assert {k: v for k, v in after.items() if k != target.item_id} == {
        k: v for k, v in before.items() if k != target.item_id
    }
    assert a.row(plan.plan_id).revision == 2


def test_칸을_다시_만들면_새_값과_근거_이력이_저장된다(a):
    plan = a.generate(a.confirmed_yearly(), LLM)
    target = plan.section("focus").cells[0]

    regenerated = a.regenerate(plan.plan_id, target.item_id)
    restored = a.reload(plan.plan_id)

    assert restored == regenerated
    cell = _cells(restored)[target.item_id]
    assert cell.item_id == target.item_id and cell.week_id == target.week_id
    assert cell.value == "다시 만든 focus"
    event = cell.audit.events[-1]
    assert event.event_type is AuditEventType.REGENERATED
    assert event.generation_change.before == target.generation
    assert event.generation_change.after == cell.generation
    assert any(e.source_type is EvidenceSourceType.INSTITUTION_SAMPLE for e in cell.evidence)
    others = {k: v for k, v in _cells(restored).items() if k != target.item_id}
    assert others == {k: v for k, v in _cells(plan).items() if k != target.item_id}


def test_확정하면_상태와_메타데이터가_저장되고_다시_고칠_수_없다(a):
    plan = a.generate(a.confirmed_yearly(), LLM)
    a.confirm(plan.plan_id)
    restored = a.reload(plan.plan_id)

    assert restored.status is PlanStatus.CONFIRMED
    event = restored.audit.events[-1]
    assert (event.event_type, event.actor_id, event.occurred_at) == (
        AuditEventType.CONFIRMED,
        TEACHER,
        NOW,
    )
    row = a.row(plan.plan_id)
    assert (row.status, row.confirmed_at, row.revision) == ("CONFIRMED", NOW, 2)

    focus = restored.section("focus").cells[0]
    for change in (
        lambda: a.edit(plan.plan_id, focus.item_id, "확정 뒤 수정"),
        lambda: a.regenerate(plan.plan_id, focus.item_id),
    ):
        with pytest.raises(InvalidStateTransitionError):
            change()
    # 다시 확정은 Core 계약상 멱등이다 — 그대로 돌려주고 저장하지 않는다.
    assert a.confirm(plan.plan_id) == restored
    assert a.reload(plan.plan_id) == restored
    assert a.row(plan.plan_id).revision == 2  # 거절 · 멱등 요청은 저장하지 않았다


# ── 원 격리 · 종류 · 무결성 ───────────────────────────────────────────────


def test_다른_원은_같은_PlanId_로_읽지도_덮어쓰지도_고치지도_못한다(a, b):
    plan = a.generate(a.confirmed_yearly(), RULE)
    item = plan.section("outdoor_play").cells[0].item_id

    assert a.monthly.get(plan.plan_id) is not None
    assert b.monthly.get(plan.plan_id) is None
    with pytest.raises(InvalidDomainValueError, match="다른 원의 계획안이다"):
        b.monthly.save(plan.plan_id, plan)
    for change in (
        lambda: b.edit(plan.plan_id, item, "남의 원 수정"),
        lambda: b.confirm(plan.plan_id),
    ):
        with pytest.raises(MonthlyApplicationError) as excinfo:
            change()
        assert excinfo.value.code == "monthly_plan_not_found"
    assert a.reload(plan.plan_id) == plan
    assert a.row(plan.plan_id).center_id == a.center.id


def test_종류가_다른_저장소로는_읽지도_덮어쓰지도_못한다(a):
    parent = a.confirmed_yearly()
    plan = a.generate(parent, RULE)

    assert a.yearly.get(plan.plan_id) is None
    assert a.monthly.get(parent.plan_id) is None
    with pytest.raises(InvalidDomainValueError, match="다른 종류의 계획안이다"):
        a.monthly.save(parent.plan_id, plan)  # 같은 id 의 연간을 월간으로 바꾸지 못한다
    with pytest.raises(InvalidDomainValueError, match="다른 종류의 계획안이다"):
        a.yearly.save(plan.plan_id, parent)
    assert a.yearly.get(parent.plan_id) == parent
    assert a.row(parent.plan_id).target_month is None  # 연간은 대상 월이 없다
    assert a.monthly.get(PlanId("plan_없는것")) is None
    with pytest.raises(InvalidDomainValueError):
        a.monthly.get(plan.plan_id.value)


def test_같은_반_같은_달_월간은_하나뿐이고_실패해도_있던_계획안은_남는다(a, b):
    parent = a.confirmed_yearly()
    profile = a.profile(RULE)
    first = a.generate(parent, RULE, profile=profile)

    with pytest.raises(IntegrityError, match="uq_plans_monthly_per_classroom_month"):
        with a.session.begin_nested():
            a.generate(parent, RULE, profile=profile)
    assert a.reload(first.plan_id) == first
    count = select(Plan.plan_ref).where(Plan.kind == "monthly", Plan.center_id == a.center.id)
    assert list(a.session.scalars(count)) == [first.plan_id.value]

    # 다른 달 · 다른 원의 같은 달은 된다.
    a.generate(parent, RULE, month=YearMonth(2026, 10), profile=profile)
    b.generate(b.confirmed_yearly(), RULE)


def test_migration이_월간_칸과_제약을_올린다(db_session, a):
    inspector = inspect(db_session.connection())
    columns = {c["name"]: c for c in inspector.get_columns("plans")}
    assert columns["revision"]["nullable"] is False
    assert columns["target_month"]["nullable"] is True
    indexes = {i["name"]: i for i in inspector.get_indexes("plans")}
    assert indexes["uq_plans_monthly_per_classroom_month"]["unique"]
    assert indexes["uq_plans_monthly_per_classroom_month"]["column_names"] == [
        "center_id",
        "classroom_ref",
        "target_month",
    ]
    checks = {c["name"] for c in inspector.get_check_constraints("plans")}
    assert "ck_plans_target_month_kind" in checks

    # 월간인데 대상 월이 없거나, 연간인데 대상 월이 있으면 DB 가 막는다.
    for kind, month in (("monthly", None), ("annual", "2026-09")):
        with pytest.raises(IntegrityError, match="ck_plans_target_month_kind"):
            with db_session.begin_nested():
                db_session.add(
                    Plan(
                        plan_ref=f"bad-{kind}",
                        center_id=a.center.id,
                        kind=kind,
                        school_year=2026,
                        classroom_ref="1",
                        target_month=month,
                        status="DRAFT",
                        body={},
                    )
                )


# ── 동시 저장 ─────────────────────────────────────────────────────────────


def test_동시에_저장해도_revision_은_빠짐없이_오른다(_schema):
    """서로 다른 연결. 앞 저장이 행을 잡은 동안 뒤 저장은 기다리고, revision 은 DB 가 더한다.

    본문은 아직 나중 저장이 이긴다 — 읽은 revision 과 비교해 409 를 내는 것은 편집 API 몫이다
    (결정 문서 12.4 D-3, PR-4). 여기서는 그 비교의 바탕인 revision 이 경쟁에서 새지 않는지 본다.
    """
    with Session(engine) as session:
        planning = _planning(
            session, "월간 동시성 테스트원", "monthly-concurrency@example.com", ids="race"
        )
        plan = planning.generate(planning.confirmed_yearly(), RULE)
        session.commit()
        center_id, user_id = planning.center.id, planning.user.id

    def repo(session):
        return PostgresPlanRepository(
            session, center_id=center_id, kind="monthly", plan_type=MonthlyPlan
        )

    def save_later():
        with Session(engine) as session:
            repo(session).save(plan.plan_id, plan)
            session.commit()

    first = Session(engine)
    try:
        repo(first).save(plan.plan_id, plan)  # 행을 잡고 아직 커밋하지 않았다
        with ThreadPoolExecutor(max_workers=1) as executor:
            later = executor.submit(save_later)
            with engine.connect() as watcher:
                for _ in range(200):
                    waiting = watcher.scalar(
                        text("SELECT count(*) FROM pg_locks WHERE NOT granted")
                    )
                    watcher.rollback()
                    if waiting:
                        break
                    time.sleep(0.05)
                else:
                    pytest.fail("뒤 저장이 앞 저장의 행 잠금을 기다리지 않았다")
            first.commit()
            later.result(timeout=10)
        with Session(engine) as session:
            row = session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))
            assert row.revision == 3  # 생성 1 → 두 저장이 각각 +1
    finally:
        first.close()
        with Session(engine) as session:
            for model in (Plan, TemplateProfileVersion):
                session.execute(delete(model).where(model.center_id == center_id))
            session.execute(delete(Class).where(Class.center_id == center_id))
            session.execute(delete(User).where(User.id == user_id))
            session.execute(delete(Center).where(Center.id == center_id))
            session.commit()
