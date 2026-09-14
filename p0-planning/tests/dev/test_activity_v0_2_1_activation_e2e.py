"""v0.2.1 Activation E2E — Production Composition으로 실제 Use Case를 실행한다.

여기서 쓰는 Reference는 전부 승인 artifact다. Fake Catalog도 Mock도 없고
Network 0회 / LLM 0회다(Monthly는 Rule 전용, 상위 Yearly fixture는 `use_llm=False`).

고정하는 Contract:

    새 Plan        → default v0.2.1을 pin
    기존 v0.2.0 Plan → Regenerate가 **v0.2.0을 정확히** 다시 로드
    Default fallback으로 기존 Plan의 version이 바뀌지 않는다
"""

from __future__ import annotations

import pytest

from ssuksak.dev.monthly_wiring import DEV_ACTOR, build_monthly_wiring
from ssuksak.planning.application.dto import CatalogSelector
from ssuksak.planning.application.monthly_dto import (
    GenerateMonthlyPlanCommand,
    MonthlyCellAddress,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.domain.constraint import CellState
from ssuksak.planning.domain.provenance import EvidenceSourceType
from ssuksak.planning.rules.monthly_activity_selection import (
    RULE_ID as ACTIVITY_RULE_ID,
    RULE_VERSION as ACTIVITY_RULE_VERSION,
)

CATALOG_ID = "ssuksak.outdoor-activity-reference"
VER_0 = "activity-reference-v0.2.0"
VER_1 = "activity-reference-v0.2.1"
OUTDOOR = "outdoor_play"

FRAGMENTS = ("건너기", "장화 신고 물웅덩이", "우리집에 왜 왔니?", "놀이를 해요.")


def generate(w, **over):
    base = dict(
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
    base.update(over)
    return w.generate.execute(GenerateMonthlyPlanCommand(**base))


def outdoor(plan):
    section = plan.section(OUTDOOR)
    return section.items if section else []


def labels(plan):
    return [i.value for i in outdoor(plan)]


# ============================================== Production Generate


@pytest.mark.parametrize("age", [3, 4, 5])
def test_new_generate_pins_the_new_default_and_uses_rule_v2(age):
    w = build_monthly_wiring(target_month="2026-09", ages=frozenset({age}))
    result = generate(w)
    plan = result.plan

    assert w.activity_catalog.catalog_version == VER_1
    assert plan.activity_catalog.catalog_version == VER_1
    assert all(i.cell_state is CellState.FILLED for i in outdoor(plan))
    assert {
        (i.generation.rule_id, i.generation.rule_version) for i in outdoor(plan)
    } == {(ACTIVITY_RULE_ID, ACTIVITY_RULE_VERSION)}
    assert ACTIVITY_RULE_VERSION == "v2"
    assert result.run.llm_invoked is False


@pytest.mark.parametrize("age", [3, 4, 5])
def test_every_activity_evidence_records_the_new_catalog_version(age):
    w = build_monthly_wiring(target_month="2026-09", ages=frozenset({age}))
    plan = generate(w).plan
    versions = {
        e.source_version
        for i in outdoor(plan)
        for e in i.evidence
        if e.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
    }
    assert versions == {VER_1}


# ============================================== Exact Catalog Pinning


@pytest.mark.parametrize("version", [VER_0, VER_1])
def test_regenerate_loads_the_exact_pinned_catalog(version):
    """Scenario A(legacy v0.2.0) / Scenario B(new v0.2.1)."""
    w = build_monthly_wiring(target_month="2026-09", ages=frozenset({4}))
    plan = generate(w, activity_catalog=CatalogSelector(CATALOG_ID, version)).plan
    assert plan.activity_catalog.catalog_version == version

    before = labels(plan)
    outcome = w.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=MonthlyCellAddress(
                target_month="2026-09", section_key=OUTDOOR, week_id="2026-09-W2"
            ),
            actor_id=DEV_ACTOR,
        )
    ).activity_regeneration

    assert outcome.catalog_version == version
    saved = w.monthly_plans.get(plan.plan_id.value)
    assert saved.activity_catalog.catalog_version == version
    after = labels(saved)
    assert [after[0], *after[2:]] == [before[0], *before[2:]]


def test_legacy_plan_is_not_upgraded_to_the_new_default():
    """Default가 v0.2.1이어도 v0.2.0 Plan은 v0.2.0에 머문다."""
    w = build_monthly_wiring(target_month="2026-09", ages=frozenset({4}))
    plan = generate(w, activity_catalog=CatalogSelector(CATALOG_ID, VER_0)).plan
    w.regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan_id=plan.plan_id.value,
            address=MonthlyCellAddress(
                target_month="2026-09", section_key=OUTDOOR, week_id="2026-09-W2"
            ),
            actor_id=DEV_ACTOR,
        )
    )
    saved = w.monthly_plans.get(plan.plan_id.value)
    assert saved.activity_catalog.catalog_version == VER_0
    versions = {
        e.source_version
        for i in outdoor(saved)
        for e in i.evidence
        if e.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
    }
    assert versions == {VER_0}, "v0.2.1 Evidence가 섞이면 실패다"


# ============================================== 품질 Regression


def test_july_age3_has_no_fragment_activity():
    """Patch 1 이전에는 W3가 조각 `건너기`였다."""
    w = build_monthly_wiring(target_month="2026-07", ages=frozenset({3}))
    plan = generate(w).plan
    got = labels(plan)
    assert plan.activity_catalog.catalog_version == VER_1
    for fragment in FRAGMENTS:
        assert fragment not in got
    assert "장화 신고 물웅덩이 건너기" in got


def test_september_age5_does_not_select_the_generic_label():
    """`전통놀이`는 Catalog에 남아 있지만 soft penalty로 밀린다."""
    w = build_monthly_wiring(target_month="2026-09", ages=frozenset({5}))
    plan = generate(w).plan
    got = labels(plan)
    assert "전통놀이" not in got
    assert got[1] == "강강술래"


def test_legacy_v0_2_0_still_reproduces_the_old_generic_selection():
    """같은 Case를 v0.2.0으로 pin하면 예전 결과가 그대로 나온다.

    display quality penalty가 **Catalog metadata에서** 오는 것이지 Rule이 label을
    판단하는 것이 아님을 보여준다.
    """
    w = build_monthly_wiring(target_month="2026-09", ages=frozenset({5}))
    plan = generate(w, activity_catalog=CatalogSelector(CATALOG_ID, VER_0)).plan
    assert labels(plan)[1] == "전통놀이"
