"""Harness end-to-end flow 테스트. FakeLLM만 사용하고 실제 API를 호출하지 않는다.

핵심 검증:
- Generate → Edit → Regenerate → Confirm 이 Use Case를 통해서만 일어난다
- Confirm 이후 Edit/Regenerate 차단이 **Harness if문이 아니라 실제 Gate**에서 온다
- `dev/` 소스가 Domain Aggregate를 직접 변경하지 않는다
"""

from __future__ import annotations

import pathlib
import re

import pytest

from ssuksak.dev import formatting as fmt
from ssuksak.dev.wiring import (
    DEV_CLASSROOM_REF,
    DEV_DAYCARE_REF,
    HarnessSession,
    build_wiring,
    read_catalog_selector,
)
from ssuksak.planning.application.dto import (
    ClassroomContext,
    ConfirmYearlyPlanCommand,
    DaycareContext,
    EditYearlyPlanItemCommand,
    GenerateYearlyPlanCommand,
    ItemAddress,
    PlanningSetup,
    RegenerateYearlyPlanItemCommand,
)
from ssuksak.planning.domain.errors import FailureCategory, Outcome, PlanningError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import AuditEventType, EvidenceSourceType
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode

ACTOR = ActorId("teacher_dev_001")
SEMANTIC = "yearly.month.{:02d}.theme"


def _wiring(mode: FakeLLMMode = FakeLLMMode.POLISH, **kwargs):
    return build_wiring(llm=FakeLLM(mode), **kwargs)


def _generate(wiring, ages=frozenset({4}), school_year=2026):
    command = GenerateYearlyPlanCommand(
        school_year=school_year,
        daycare=DaycareContext(daycare_ref=DEV_DAYCARE_REF),
        classroom=ClassroomContext(classroom_ref=DEV_CLASSROOM_REF, ages=ages),
        planning_setup=PlanningSetup(completed=True, start_mode="CREATE_NEW"),
        catalog=wiring.selector,
    )
    return wiring.generate.execute(command)


def _session_after_generate(wiring, **kwargs) -> HarnessSession:
    session = HarnessSession(selector=wiring.selector)
    result = _generate(wiring, **kwargs)
    session.adopt(result.plan)
    session.absorb_run(result.run)
    return session


def _theme_id(item) -> str | None:
    refs = item.evidence_of_type(EvidenceSourceType.THEME_REFERENCE)
    return refs[0].source_id if refs else None


# ------------------------------------------------------------------ wiring


def test_selector_is_read_from_reference_file_not_hardcoded():
    """catalog_version을 코드에 박지 않고 파일에서 읽는다."""
    import json

    from ssuksak.adapters.json_theme_reference_repository import DEFAULT_CATALOG_PATH

    payload = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    selector = read_catalog_selector()

    assert selector.catalog_id == payload["catalog_id"]
    assert selector.catalog_version == payload["catalog_version"]


def test_wiring_uses_real_approval_state_without_override():
    wiring = _wiring()
    assert wiring.catalog.is_active is True
    assert wiring.catalog.activation_status.value == "HUMAN_APPROVED"


def test_wiring_creates_no_new_persistence_adapter():
    from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository

    wiring = _wiring()
    assert isinstance(wiring.plans, InMemoryPlanRepository)


def test_no_llm_mode_does_not_call_llm():
    llm = FakeLLM()
    wiring = build_wiring(use_llm=False, llm=llm)
    result = _generate(wiring)

    assert not llm.was_called
    assert result.run.llm_invoked is False
    assert all(
        mp.theme.generation.method.value == "RULE_ONLY"
        for mp in result.plan.month_periods
    )


# ---------------------------------------------------------------- Generate


def test_generate_produces_twelve_periods_and_traces():
    wiring = _wiring()
    session = _session_after_generate(wiring)

    assert len(session.plan.month_periods) == 12
    assert session.plan.status is PlanStatus.DRAFT
    assert len(session.traces) == 12
    assert session.plan_id == "dev_plan_001"


def test_session_traces_come_from_use_case_not_recomputed():
    wiring = _wiring()
    result = _generate(wiring)
    session = HarnessSession(selector=wiring.selector)
    session.adopt(result.plan)
    session.absorb_run(result.run)

    for trace in result.run.selection_traces:
        assert session.traces[trace.period_key] is trace


def test_generate_uses_batch_single_request():
    llm = FakeLLM()
    wiring = build_wiring(llm=llm)
    result = _generate(wiring)

    assert llm.batch_call_count == 1
    assert result.run.llm_call_count == 1
    assert result.run.llm_item_count == 12


# -------------------------------------------------------------------- Edit


def test_edit_goes_through_use_case_and_preserves_provenance():
    wiring = _wiring()
    session = _session_after_generate(wiring)

    found = session.plan.find_item(
        period_key="2026-05", semantic_key=SEMANTIC.format(5)
    )
    _, item = found
    before_value = item.value
    before_evidence = [(e.source_type, e.source_id) for e in item.evidence]
    before_method = item.generation.method

    result = wiring.edit.execute(
        EditYearlyPlanItemCommand(
            plan_id=session.plan_id,
            address=ItemAddress(
                period_key="2026-05", semantic_key=SEMANTIC.format(5)
            ),
            new_value="우리 가족의 소중함을 알아보아요.",
            actor_id=ACTOR,
        )
    )
    session.adopt(result.plan)

    _, after = session.plan.find_item(
        period_key="2026-05", semantic_key=SEMANTIC.format(5)
    )
    assert after.value == "우리 가족의 소중함을 알아보아요."
    assert after.value != before_value
    assert [(e.source_type, e.source_id) for e in after.evidence] == before_evidence
    assert after.generation.method is before_method
    assert after.audit.contains(AuditEventType.TEACHER_EDITED)

    text = fmt.format_edit_result(
        "2026-05", after, previous_value=before_value, previous_method=before_method
    )
    assert "[성공]" in text
    assert before_value in text
    assert "Evidence" in text


def test_edit_with_blank_value_is_rejected_by_use_case():
    wiring = _wiring()
    session = _session_after_generate(wiring)

    with pytest.raises(PlanningError) as exc:
        wiring.edit.execute(
            EditYearlyPlanItemCommand(
                plan_id=session.plan_id,
                address=ItemAddress(
                    period_key="2026-05", semantic_key=SEMANTIC.format(5)
                ),
                new_value="   ",
                actor_id=ACTOR,
            )
        )
    assert exc.value.failure_category is FailureCategory.REQUIRED_VALUE_VALIDATION


# -------------------------------------------------------------- Regenerate


def test_regenerate_updates_only_that_period_trace():
    wiring = _wiring()
    session = _session_after_generate(wiring)
    before_traces = dict(session.traces)

    result = wiring.regenerate.execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=session.plan_id,
            address=ItemAddress(
                period_key="2026-10", semantic_key=SEMANTIC.format(10)
            ),
            actor_id=ACTOR,
            catalog=wiring.selector,
        )
    )
    session.adopt(result.plan)
    session.absorb_run(result.run)

    assert len(session.traces) == 12
    for key, trace in before_traces.items():
        if key == "2026-10":
            continue
        assert session.traces[key] is trace
    assert session.traces["2026-10"] is result.run.selection_traces[0]


def test_regenerate_identical_value_is_reported_as_success_not_error():
    """Contract상 동일 결과도 성공이다."""
    wiring = _wiring(FakeLLMMode.ECHO_LABEL)
    session = _session_after_generate(wiring)

    found = session.plan.find_item(
        period_key="2026-05", semantic_key=SEMANTIC.format(5)
    )
    _, item = found
    before_value = item.value
    before_theme = _theme_id(item)

    result = wiring.regenerate.execute(
        RegenerateYearlyPlanItemCommand(
            plan_id=session.plan_id,
            address=ItemAddress(
                period_key="2026-05", semantic_key=SEMANTIC.format(5)
            ),
            actor_id=ACTOR,
            catalog=wiring.selector,
        )
    )
    session.adopt(result.plan)
    session.absorb_run(result.run)

    _, after = session.plan.find_item(
        period_key="2026-05", semantic_key=SEMANTIC.format(5)
    )
    assert after.value == before_value  # 동일
    assert after.audit.contains(AuditEventType.REGENERATED)

    text = fmt.format_regenerate_result(
        "2026-05",
        after,
        previous_value=before_value,
        previous_theme_id=before_theme,
        new_theme_id=_theme_id(after),
        trace=session.traces.get("2026-05"),
        run=result.run,
    )
    assert "[성공]" in text
    assert "기존 값과 동일" in text
    assert "오류가 아닙니다" in text


# ----------------------------------------------------------------- Confirm


def test_confirm_transitions_draft_to_confirmed():
    wiring = _wiring()
    session = _session_after_generate(wiring)
    assert session.plan.status is PlanStatus.DRAFT

    result = wiring.confirm.execute(
        ConfirmYearlyPlanCommand(
            plan_id=session.plan_id, actor_id=ACTOR, catalog=wiring.selector
        )
    )
    session.adopt(result.plan)

    assert session.plan.status is PlanStatus.CONFIRMED
    assert session.plan.audit.contains(AuditEventType.CONFIRMED)
    events = [e for e in session.plan.audit if e.event_type is AuditEventType.CONFIRMED]
    assert str(events[-1].actor_id) == "teacher_dev_001"


def test_confirm_without_actor_is_rejected_by_use_case():
    wiring = _wiring()
    session = _session_after_generate(wiring)

    with pytest.raises(PlanningError) as exc:
        wiring.confirm.execute(
            ConfirmYearlyPlanCommand(
                plan_id=session.plan_id, actor_id=None, catalog=wiring.selector
            )
        )
    assert exc.value.failure_category is FailureCategory.ACTOR_VALIDATION
    assert session.plan.status is PlanStatus.DRAFT


# ------------------------- Confirm 이후 차단이 실제 Gate에서 오는지


def _confirmed_session(wiring) -> HarnessSession:
    session = _session_after_generate(wiring)
    result = wiring.confirm.execute(
        ConfirmYearlyPlanCommand(
            plan_id=session.plan_id, actor_id=ACTOR, catalog=wiring.selector
        )
    )
    session.adopt(result.plan)
    assert session.plan.status is PlanStatus.CONFIRMED
    return session


def test_edit_after_confirm_is_blocked_by_application_gate():
    wiring = _wiring()
    session = _confirmed_session(wiring)

    with pytest.raises(PlanningError) as exc:
        wiring.edit.execute(
            EditYearlyPlanItemCommand(
                plan_id=session.plan_id,
                address=ItemAddress(
                    period_key="2026-05", semantic_key=SEMANTIC.format(5)
                ),
                new_value="확정 후에는 바뀌면 안 되는 값",
                actor_id=ACTOR,
            )
        )

    assert exc.value.outcome is Outcome.BLOCKED
    assert exc.value.failure_category is FailureCategory.PLAN_STATE_GATE
    assert exc.value.violated_rule == "confirmed_yearly_plan_is_read_only"

    text = fmt.format_planning_error("MonthPeriod 수정", exc.value)
    assert "PLAN_STATE_GATE" in text
    assert "confirmed_yearly_plan_is_read_only" in text
    assert "Traceback" not in text


def test_regenerate_after_confirm_is_blocked_by_application_gate():
    llm = FakeLLM()
    wiring = build_wiring(llm=llm)
    session = _confirmed_session(wiring)
    calls_before = llm.call_count

    with pytest.raises(PlanningError) as exc:
        wiring.regenerate.execute(
            RegenerateYearlyPlanItemCommand(
                plan_id=session.plan_id,
                address=ItemAddress(
                    period_key="2026-10", semantic_key=SEMANTIC.format(10)
                ),
                actor_id=ACTOR,
                catalog=wiring.selector,
            )
        )

    assert exc.value.outcome is Outcome.BLOCKED
    assert exc.value.failure_category is FailureCategory.PLAN_STATE_GATE
    # Gate가 LLM 호출 전에 차단한다
    assert llm.call_count == calls_before

    text = fmt.format_planning_error("MonthPeriod 재생성", exc.value)
    assert "PLAN_STATE_GATE" in text


def test_plan_is_unchanged_after_blocked_edit():
    wiring = _wiring()
    session = _confirmed_session(wiring)
    before = [mp.theme.value for mp in session.plan.month_periods]

    with pytest.raises(PlanningError):
        wiring.edit.execute(
            EditYearlyPlanItemCommand(
                plan_id=session.plan_id,
                address=ItemAddress(
                    period_key="2026-05", semantic_key=SEMANTIC.format(5)
                ),
                new_value="x",
                actor_id=ACTOR,
            )
        )

    assert [mp.theme.value for mp in session.plan.month_periods] == before


# ----------------------------------------- Domain 직접 Mutation 금지 가드


def test_dev_sources_do_not_mutate_domain_objects_directly():
    """`dev/` 소스에 Domain 속성 직접 대입이 없어야 한다.

    상태 변경은 반드시 Application Use Case를 통해야 한다(§9·§18).
    """
    dev_dir = pathlib.Path(__file__).resolve().parents[2] / "src" / "ssuksak" / "dev"
    forbidden = [
        re.compile(r"\.value\s*=\s*[^=]"),
        re.compile(r"\.status\s*=\s*[^=]"),
        re.compile(r"\.evidence\s*=\s*[^=]"),
        re.compile(r"\.generation\s*=\s*[^=]"),
        re.compile(r"\.month_periods\s*=\s*[^=]"),
        re.compile(r"\.audit\.append\("),
        re.compile(r"\.replace_item_value\("),
        re.compile(r"\.confirm\(\s*AuditEvent"),
    ]

    offenders: list[str] = []
    for path in sorted(dev_dir.glob("*.py")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            code = line.split("#", 1)[0]
            for pattern in forbidden:
                if pattern.search(code):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")

    assert not offenders, "dev/가 Domain을 직접 변경한다:\n" + "\n".join(offenders)


def test_dev_sources_only_change_state_through_use_cases():
    """상태 변경 호출이 Use Case execute()로만 이루어지는지 확인한다."""
    harness = (
        pathlib.Path(__file__).resolve().parents[2]
        / "src" / "ssuksak" / "dev" / "yearly_harness.py"
    ).read_text(encoding="utf-8")

    for use_case in ("generate", "edit", "regenerate", "confirm"):
        assert f"wiring.{use_case}.execute(" in harness, use_case


def test_dev_package_does_not_import_domain_mutators():
    """Harness가 Aggregate 변경 API를 import하지 않는다."""
    dev_dir = pathlib.Path(__file__).resolve().parents[2] / "src" / "ssuksak" / "dev"
    sources = "\n".join(
        p.read_text(encoding="utf-8") for p in dev_dir.glob("*.py")
    )
    assert "AuditEvent" not in sources
    assert "GenerationMethodDetail" not in sources
