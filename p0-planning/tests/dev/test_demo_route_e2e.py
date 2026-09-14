"""Demo route **결정론 E2E** (L9 §12).

`test_demo_llm_integration.py`는 조립과 화면 문구를 **읽어서** 확인한다. 이 파일은
route handler를 **실제로 돌린다.** 네트워크는 쓰지 않는다 — Composition Root의
`llm=` seam으로 FakeLLM을 넣는다.

읽기 검사만으로는 잡히지 않는 것을 여기서 잡는다.

- Composition이 정한 mode·Template이 정말 Command에 실려 가는가
- LLM 실패가 정말 503과 분류된 kind로 나가는가 (500 UNEXPECTED가 아니라)
- 실패 뒤에도 정말 Rule 결과로 대체되지 않는가
- 화면 payload에 Prompt·Key·Source 전문이 정말 없는가

**Demo Backend는 Business Logic을 갖지 않는다.** 여기서 검증하는 것은 route가
Use Case 결과를 어떻게 다루는가이며, 계획 규칙 자체는 Golden이 고정한다.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEMO_BACKEND = ROOT / "demo-planning" / "backend"
if str(DEMO_BACKEND) not in sys.path:
    sys.path.insert(0, str(DEMO_BACKEND))

from ssuksak.planning.application.monthly_dto import (  # noqa: E402
    MonthlyGenerationMode,
)
from ssuksak.planning.application.monthly_llm_planning import (  # noqa: E402
    MonthlyContextRequest,
)
from ssuksak.planning.domain.errors import PlanningError  # noqa: E402
from ssuksak.planning.domain.identifiers import PeriodKey  # noqa: E402
from ssuksak.planning.domain.parent_lineage import ParentYearlyLineage  # noqa: E402
from ssuksak.planning.domain.provenance import AuditEventType  # noqa: E402
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode  # noqa: E402
from ssuksak.shared.llm.monthly import (  # noqa: E402
    MonthlyPlanProposal,
    ProposedActivity,
    ProposedActivityOrigin,
    ProposedWeek,
)
from ssuksak.shared.llm.monthly_cell import (  # noqa: E402
    MonthlyCellRegenerationProposal,
)
from ssuksak.shared.llm.port import LLMUnavailableError  # noqa: E402

import app as demo_app  # noqa: E402

TARGET_MONTH = "2026-09"
AGES = [4]
ACTOR = "teacher_demo_e2e"


# ------------------------------------------------------------------ 조립


@pytest.fixture
def session(monkeypatch):
    """FakeLLM을 넣은 Demo Session. 실제 API를 부르지 않는다."""
    fake = FakeLLM()
    built = demo_app.Session(yearly_use_llm=False, monthly_llm=True, llm=fake)
    assert built.wiring is not None, built.llm_config_error
    monkeypatch.setattr(demo_app, "SESSION", built)
    built.fake = fake
    return built


def _lineage(session, target_month: str) -> ParentYearlyLineage:
    parent = session.yearly_plan
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
        reference_catalog_id=session.wiring.theme_selector.catalog_id,
        reference_version=anchor.source_version or "",
        confirmed_at=confirmed.occurred_at,
        confirmed_by=confirmed.actor_id.value,
    )


def _packet(session, target_month: str):
    """Composition이 조립한 **그** Builder로 Packet을 만든다.

    Fake가 돌려줄 Proposal은 Use Case가 실제로 보낼 Packet과 같은 주차·같은
    후보 위에서 만들어져야 한다. 그래야 Fake가 Planner를 흉내 내지 않고도
    유효한 응답이 된다.
    """
    planner = session.wiring.monthly_generate._llm_planner
    return planner._builder.build(
        MonthlyContextRequest(
            school_year=str(session.yearly_plan.school_year),
            target_month=PeriodKey(target_month),
            classroom_ages=tuple(AGES),
            age_mode="SINGLE",
            parent_lineage=_lineage(session, target_month),
            daycare_ref=session.daycare_ref,
            classroom_ref=session.yearly_plan.classroom_ref,
        )
    )


def _proposal(packet, *, synthesized_weeks: frozenset[int] = frozenset()) -> MonthlyPlanProposal:
    available = list(packet.reference_activities)
    refs = sorted(
        {i.ref for i in packet.institution_evidence}
        | {i.ref for i in packet.other_outdoor_evidence}
    )
    weeks = []
    for index, slot in enumerate(packet.week_slots, start=1):
        if index not in synthesized_weeks and index - 1 < len(available):
            chosen = available[index - 1]
            activity = ProposedActivity(
                value=chosen.label,
                origin=ProposedActivityOrigin.REFERENCE,
                reference_activity_id=chosen.activity_id,
                grounding_refs=[],
            )
        else:
            activity = ProposedActivity(
                value=f"{index}주차 바깥놀이를 새로 구성했어요",
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
        month_flow_rationale="관심에서 표현으로 이어지도록 구성했습니다.",
        weeks=weeks,
    )


def _yearly_confirmed(session) -> dict:
    demo_app.api_yearly_generate(
        {"school_year": 2026, "classroom_ref": "demo_class_e2e", "ages": AGES}
    )
    return demo_app.api_yearly_confirm({"actor_id": ACTOR})


def _monthly_generate(session, *, synthesized_weeks: frozenset[int] = frozenset()) -> dict:
    _yearly_confirmed(session)
    session.fake.set_monthly_proposal(
        _proposal(
            _packet(session, TARGET_MONTH), synthesized_weeks=synthesized_weeks
        )
    )
    return demo_app.api_monthly_generate(
        {"target_month": TARGET_MONTH, "ages": AGES}
    )


def _monthly_row(state: dict, section_key: str) -> dict:
    return next(r for r in state["monthly"]["rows"] if r["section_key"] == section_key)


# ============================================================ 성공 경로


def test_demo_route_generates_a_monthly_plan_through_the_llm_path(session):
    state = _monthly_generate(session)

    monthly = state["monthly"]
    assert monthly["status"] == "DRAFT"
    assert monthly["template_version"] == "monthly-template-a-v0.2.0"
    assert monthly["run"]["generation_mode"] == "LLM_PLANNER"
    assert monthly["run"]["llm_invoked"] is True
    assert session.fake.monthly_call_count == 1
    # Composition이 정한 mode·Template이 실제로 실려 갔다.
    assert session.wiring.monthly_generation_mode is MonthlyGenerationMode.LLM_PLANNER


def test_demo_route_shows_the_week_experience_row_first(session):
    state = _monthly_generate(session)
    keys = [r["section_key"] for r in state["monthly"]["rows"]]
    assert keys.index("focus") < keys.index("outdoor_play")
    assert _monthly_row(state, "focus")["label"] == "중심 경험"
    assert "week_axis" not in keys


def test_demo_route_regenerates_only_the_target_cell(session):
    state = _monthly_generate(session)
    week_id = state["monthly"]["weeks"][1]["week_id"]
    before = {
        r["section_key"]: [c["value"] for c in r["cells"]]
        for r in state["monthly"]["rows"]
    }

    plan = session.monthly_plan
    session.fake.set_cell_proposal(
        MonthlyCellRegenerationProposal(
            target_week_id=week_id,
            target_section_key="focus",
            value="다시 구성한 중심 경험이에요.",
            activity_origin=None,
            reference_activity_id=None,
            grounding_refs=[],
        )
    )
    state = demo_app.api_monthly_regenerate(
        {"section_key": "focus", "week_id": week_id, "actor_id": ACTOR}
    )

    after = {
        r["section_key"]: [c["value"] for c in r["cells"]]
        for r in state["monthly"]["rows"]
    }
    assert after["outdoor_play"] == before["outdoor_play"]
    assert after["safety_education"] == before["safety_education"]
    changed = [i for i, (a, b) in enumerate(zip(after["focus"], before["focus"])) if a != b]
    assert changed == [1], "Target 주차 하나만 바뀐다"
    assert session.monthly_plan.plan_id == plan.plan_id, "새 Plan을 만들지 않는다"


def test_demo_route_confirm_then_blocks_further_changes(session):
    state = _monthly_generate(session)
    state = demo_app.api_monthly_confirm({"actor_id": ACTOR})
    assert state["monthly"]["status"] == "CONFIRMED"

    week_id = state["monthly"]["weeks"][1]["week_id"]
    calls_before = session.fake.cell_call_count
    with pytest.raises(PlanningError) as exc:
        demo_app.api_monthly_regenerate(
            {"section_key": "focus", "week_id": week_id, "actor_id": ACTOR}
        )
    assert exc.value.violated_rule == "confirmed_monthly_plan_is_read_only"
    assert session.fake.cell_call_count == calls_before


# ============================================================ 실패 경로


def test_demo_route_classifies_llm_failure_instead_of_a_generic_500(session):
    """L8에서 고친 것이 회귀하지 않는지 실제로 돌려서 확인한다."""
    _yearly_confirmed(session)
    session.fake.mode = FakeLLMMode.UNAVAILABLE

    with pytest.raises(LLMUnavailableError):
        demo_app.api_monthly_generate({"target_month": TARGET_MONTH, "ages": AGES})

    # route가 이 예외를 503 + 분류된 kind로 바꾼다는 것은 handler가 안다.
    source = (DEMO_BACKEND / "app.py").read_text("utf-8")
    assert "except LLMUnavailableError" in source
    assert '"kind": "LLM_UNAVAILABLE"' in source


def test_demo_route_never_falls_back_to_rule_only_after_a_failure(session):
    """실패한 뒤 화면에 Rule 결과가 대신 나타나지 않는다 (OD-N15)."""
    _yearly_confirmed(session)
    session.fake.mode = FakeLLMMode.UNAVAILABLE

    with pytest.raises(LLMUnavailableError):
        demo_app.api_monthly_generate({"target_month": TARGET_MONTH, "ages": AGES})

    state = demo_app.api_state({})
    assert state["monthly"] is None
    assert session.wiring.monthly_plans.stored_count == 0


def test_demo_route_requires_a_confirmed_parent(session):
    demo_app.api_yearly_generate(
        {"school_year": 2026, "classroom_ref": "demo_class_e2e", "ages": AGES}
    )  # 확정하지 않는다

    with pytest.raises(PlanningError) as exc:
        demo_app.api_monthly_generate({"target_month": TARGET_MONTH, "ages": AGES})
    assert "confirmed" in exc.value.violated_rule.lower()
    assert session.fake.monthly_call_count == 0, "Gate 전에 비용을 쓰지 않는다"


# ============================================================ 노출 금지


def test_demo_state_payload_carries_no_prompt_key_or_source_text(session):
    state = _monthly_generate(session)
    week_id = state["monthly"]["weeks"][1]["week_id"]
    session.fake.set_cell_proposal(
        MonthlyCellRegenerationProposal(
            target_week_id=week_id,
            target_section_key="focus",
            value="다시 구성한 중심 경험이에요.",
            activity_origin=None,
            reference_activity_id=None,
            grounding_refs=[],
        )
    )
    state = demo_app.api_monthly_regenerate(
        {"section_key": "focus", "week_id": week_id, "actor_id": ACTOR}
    )

    payload = json.dumps(state, ensure_ascii=False, default=str)
    for banned in (
        "system_prompt",
        "user_content",
        "ELICE_MLAPI",
        "api_key",
        "Authorization",
        "grounding_source_ids",
    ):
        assert banned not in payload

    # Debug 값은 있어도 되지만 Prompt **본문**은 아니다.
    assert state["monthly"]["run"]["prompt_version"]
    assert "packet_fingerprint" not in json.dumps(
        state["monthly"]["rows"], ensure_ascii=False
    )


def test_newly_written_activities_never_copy_corpus_source_text(session):
    """새로 쓴 활동만 exact-copy 금지 대상이다 (L5 §21).

    **승인 Catalog label은 대상이 아니다.** 그 Catalog 자체가 기관 Sample을
    사람이 검토해 만든 것이라 Corpus 문장과 같을 수 있고, 그것은 복사가 아니라
    승인된 값을 고른 것이다. 두 경우를 섞어서 막으면 `사방치기` 같은 정상
    Reference 활동이 위반으로 보인다.
    """
    from ssuksak.planning.rules.monthly_llm_text_policy import (
        normalize_for_comparison,
    )

    state = _monthly_generate(session, synthesized_weeks=frozenset({1}))
    packet = _packet(session, TARGET_MONTH)
    sources = {
        normalize_for_comparison(item.text)
        for item in list(packet.institution_evidence)
        + list(packet.other_outdoor_evidence)
    }
    assert sources, "비교할 Source가 없으면 이 test는 아무것도 지키지 못한다"

    synthesized = [
        c
        for r in state["monthly"]["rows"]
        for c in r["cells"]
        if c["value"]
        and any(e["source_type"] == "INSTITUTION_SAMPLE" for e in c["evidence"])
    ]
    assert synthesized, "새로 쓴 활동이 하나도 없으면 이 test는 비어 있다"
    leaked = [
        c["value"] for c in synthesized
        if normalize_for_comparison(c["value"]) in sources
    ]
    assert not leaked, f"Corpus 원문이 그대로 화면에 나갔다: {len(leaked)}건"
