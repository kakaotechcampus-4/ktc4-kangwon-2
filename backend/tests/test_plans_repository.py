"""계획안 저장소. 진짜 Postgres 에 진짜 연간계획안을 넣고 꺼낸다.

**모의 객체로 확인하지 않는다.** 이 저장소가 하는 일의 전부가 「도메인 객체를 JSONB 로
바꿔 넣고 똑같이 되돌리는 것」이라, 가짜 계획안을 쓰면 정작 확인해야 할 것을 안 본다.
12개월치가 근거·생성이력·감사기록까지 달고 그대로 돌아오는지가 이 파일의 목적이다.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.deterministic_theme_text_generator import (
    DeterministicThemeTextGenerator,
)
from ssuksak.adapters.json_theme_reference_repository import JsonThemeReferenceRepository
from ssuksak.planning.application.confirm_yearly_plan import ConfirmYearlyPlan
from ssuksak.planning.application.generate_yearly_plan import GenerateYearlyPlan
from ssuksak.planning.application.yearly_dto import (
    CatalogSelector,
    ConfirmYearlyPlanCommand,
    GenerateYearlyPlanCommand,
)
from ssuksak.planning.domain.identifiers import ActorId, PlanId
from ssuksak.planning.domain.yearly_plan import YearlyPlan

from app.features.centers.models import Center
from app.features.plans.models import Plan
from app.features.plans.repository import PostgresPlanRepository
from app.features.plans.runtime import SystemClock, UuidGenerator

NOW = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
ACTOR = ActorId("teacher_001")
SELECTOR = CatalogSelector(
    catalog_id="ssuksak.yearly-theme-reference",
    catalog_version="theme-reference-v0.1.2",
)


def _center(session, name: str = "테스트어린이집") -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _repo(session, center_id: int) -> PostgresPlanRepository[YearlyPlan]:
    return PostgresPlanRepository(session, center_id=center_id, kind="annual", plan_type=YearlyPlan)


def _row(session, plan: YearlyPlan) -> Plan:
    """도메인 id 로 행을 찾는다. 계약의 id 는 정수지만 도메인은 문자열을 쓴다."""
    return session.scalar(select(Plan).where(Plan.plan_ref == plan.plan_id.value))


def _generate(repo) -> YearlyPlan:
    """진짜 연간계획안 12개월치를 만든다. 저장은 repo 가 한다."""
    use_case = GenerateYearlyPlan(
        theme_repository=JsonThemeReferenceRepository(),
        plan_repository=repo,
        text_generator=DeterministicThemeTextGenerator(),
        clock=FixedClock(NOW),
        id_generator=DeterministicIdGenerator("yearly"),
    )
    result = use_case.execute(
        GenerateYearlyPlanCommand(
            school_year=2026,
            classroom_ref="classroom_001",
            target_ages=frozenset({3}),
            catalog=SELECTOR,
        )
    )
    return result.plan


def test_12개월치가_근거와_감사기록까지_그대로_돌아온다(db_session):
    center = _center(db_session)
    repo = _repo(db_session, center.id)
    original = _generate(repo)

    restored = repo.get(original.plan_id)

    # 얼어붙은 dataclass 라 == 가 칸을 하나씩 다 본다. 하나라도 빠지면 여기서 걸린다.
    assert restored == original
    assert len(restored.periods) == 12


def test_조회에_쓰는_칸은_본문에서_나온다(db_session):
    center = _center(db_session)
    plan = _generate(_repo(db_session, center.id))

    row = _row(db_session, plan)
    assert row.center_id == center.id
    assert row.kind == "annual"
    assert row.status == plan.status.value
    assert row.school_year == 2026
    assert row.classroom_ref == "classroom_001"
    assert row.body["status"] == row.status


def test_확정하면_본문과_칸이_같이_바뀐다(db_session):
    center = _center(db_session)
    repo = _repo(db_session, center.id)
    plan = _generate(repo)
    assert _row(db_session, plan).status == "DRAFT"

    ConfirmYearlyPlan(plan_repository=repo, clock=FixedClock(NOW)).execute(
        ConfirmYearlyPlanCommand(plan_id=plan.plan_id, actor_id=ACTOR)
    )

    row = _row(db_session, plan)
    assert row.status == "CONFIRMED"
    assert row.body["status"] == "CONFIRMED"
    assert repo.get(plan.plan_id).status.value == "CONFIRMED"


def test_다른_원의_계획안은_없는_것과_같다(db_session):
    mine = _center(db_session, "우리어린이집")
    other = _center(db_session, "남의어린이집")
    plan = _generate(_repo(db_session, mine.id))

    assert _repo(db_session, other.id).get(plan.plan_id) is None
    assert _repo(db_session, mine.id).get(plan.plan_id) is not None


def test_남의_원_계획안을_같은_id_로_덮어쓰지_못한다(db_session):
    mine = _center(db_session, "우리어린이집")
    other = _center(db_session, "남의어린이집")
    repo = _repo(db_session, mine.id)
    plan = _generate(repo)

    with pytest.raises(Exception, match="다른 원의 계획안이다"):
        _repo(db_session, other.id).save(plan.plan_id, plan)


def test_없는_계획안은_None(db_session):
    center = _center(db_session)
    assert _repo(db_session, center.id).get(PlanId("plan_없는것")) is None


def test_운영용_시계와_id_는_테스트용과_다르다():
    """FixedClock · DeterministicIdGenerator 를 그대로 쓰면 전부 같은 값이 된다."""
    ids = UuidGenerator()
    assert ids.new_plan_id() != ids.new_plan_id()
    assert ids.new_item_id() != ids.new_item_id()
    assert SystemClock().now().tzinfo is not None
