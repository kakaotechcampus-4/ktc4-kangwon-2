"""놀이 프로젝트 선택이 실제 저장 변환(codec)을 지나도 그대로인지 본다. DB 는 쓰지 않는다.

선택 저장(2026-10-26)은 `AuditEvent.selection_change` · `PlayPeriodRows.selected` 두 칸을 더했다.
옛 본문에는 이 칸이 없다 — 그래도 읽혀야 하고(마이그레이션 없음), 새 칸은 왕복해도 같아야 한다.
"""

import json
from datetime import UTC, datetime

from ssuksak.planning import ActorId, ItemId, PlanId
from ssuksak.planning.domain.plan import PlanItem, PlanStatus
from ssuksak.planning.domain.play_project_plan import (
    PlayPeriod,
    PlayPeriodRows,
    PlayProjectYearlyPlan,
    PlayRow,
)
from ssuksak.planning.domain.provenance import (
    AuditEvent,
    AuditEventType,
    AuditHistory,
    EvidenceSource,
    EvidenceSourceType,
    GenerationMethod,
    GenerationMethodDetail,
)

from app.features.plans.codec import from_jsonable, to_jsonable

AT = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
PLAN = PlanId("pp_plan_001")
TEACHER = ActorId("user_1")
GENERATION = GenerationMethodDetail(GenerationMethod.RULE_LLM, "play_project.generate", "v6")


def _item(n: int, value: str, evidence=()) -> PlanItem:
    item_id = ItemId(f"pp_item_{n:03d}")
    created = AuditEvent(AuditEventType.CREATED, AT, PLAN, item_id=item_id, system_actor="sys")
    return PlanItem(item_id, value, evidence, GENERATION, AuditHistory((created,)))


def _plan() -> PlayProjectYearlyPlan:
    curriculum = (EvidenceSource(EvidenceSourceType.CURRICULUM, "nuri2019.3.1.1", "v0.1.0"),)
    rows = tuple(
        PlayRow(
            f"cand{n}",
            _item(n * 10 + 1, f"놀이 {n}"),
            _item(n * 10 + 2, "솔방울"),
            _item(n * 10 + 3, "지원 방향"),
            _item(n * 10 + 4, "배움", curriculum),
        )
        for n in range(1, 4)
    )
    created = AuditEvent(AuditEventType.CREATED, AT, PLAN, system_actor="sys")
    return PlayProjectYearlyPlan(
        plan_id=PLAN,
        school_year=2026,
        classroom_ref="1",
        target_ages=frozenset({4}),
        status=PlanStatus.DRAFT,
        layout_version="play-project-layout-v0.2.0",
        periods=(PlayPeriodRows(PlayPeriod("m03_m05", (3, 4, 5), "3월~5월"), rows),),
        audit=AuditHistory((created,)),
    )


def _through_db(plan: PlayProjectYearlyPlan) -> PlayProjectYearlyPlan:
    body = json.loads(json.dumps(to_jsonable(plan), ensure_ascii=False))  # JSONB 와 같은 왕복
    return from_jsonable(PlayProjectYearlyPlan, body)


def test_selection_and_its_event_survive_the_codec():
    plan = _plan().select({"m03_m05": ("cand3", "cand1")}, actor_id=TEACHER, occurred_at=AT)
    plan = plan.select({"m03_m05": ("cand1", "cand3")}, actor_id=TEACHER, occurred_at=AT)

    stored = _through_db(plan)

    assert stored == plan
    assert stored.periods[0].selected == ("cand1", "cand3")
    changes = [e.selection_change for e in stored.audit if e.selection_change is not None]
    assert [(c.before, c.after) for c in changes] == [
        ((), ("cand3", "cand1")),
        (("cand3", "cand1"), ("cand1", "cand3")),
    ]
    assert stored.audit.events[-1].event_type is AuditEventType.CANDIDATES_SELECTED


def test_a_body_saved_before_selection_existed_still_reads():
    plan = _plan()
    old = to_jsonable(plan)
    for period in old["periods"]:
        del period["selected"]
        for row in period["candidates"]:
            for name in ("play_name", "materials", "support_direction", "learning"):
                for event in row[name]["audit"]["events"]:
                    del event["selection_change"]
    for event in old["audit"]["events"]:
        del event["selection_change"]
    assert "selection_change" not in json.dumps(old) and '"selected"' not in json.dumps(old)

    assert from_jsonable(PlayProjectYearlyPlan, old) == plan
