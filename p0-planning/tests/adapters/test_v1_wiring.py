import json

import pytest

from ssuksak.adapters import monthly_composition
from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning.application.monthly_dto import (
    GenerateMonthlyPlanCommand,
    RegenerateMonthlyPlanItemCommand,
)
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.domain.errors import InvalidDomainValueError
from ssuksak.planning.domain.identifiers import ActorId
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.domain.year_month import YearMonth
from tests.finalization.harness import (
    PlanningHarness,
    ACTIVITY_CATALOG,
    LLM_PROFILE,
    SAFETY_RULE,
)


class RecordingProvider(RequestAwareMonthlyLlm):
    def __init__(self):
        self.requests = []

    def generate_monthly(self, request):
        self.requests.append(request)
        return super().generate_monthly(request)

    def generate_cell(self, request):
        self.requests.append(request)
        return super().generate_cell(request)


def _setup():
    harness = PlanningHarness()
    parent = harness.confirm_yearly(harness.generate_yearly().plan)
    provider = RecordingProvider()
    generate = monthly_composition.monthly_generation(
        parent_plan_repository=harness.yearly_plans,
        plan_repository=harness.monthly_plans,
        profile_repository=harness.profiles,
        template_repository=harness.generation_templates,
        provider=provider,
        clock=harness.clock,
        id_generator=harness.monthly_ids,
    )
    command = GenerateMonthlyPlanCommand(
        parent.plan_id,
        YearMonth(2026, 9),
        "daycare_001",
        LLM_PROFILE,
        SAFETY_RULE,
        MonthlyGenerationMode.LLM_PLANNER,
        activity_catalog=ACTIVITY_CATALOG,
        parent_subthemes=("교사가 확정한 가을 열매", "서로 다른 나뭇잎"),
    )
    return harness, provider, generate, command


def test_monthly_generation_and_regeneration_reuse_confirmed_annual_snapshot():
    harness, provider, generate, command = _setup()
    plan = generate.execute(command).plan
    assert plan.parent_subthemes == command.parent_subthemes
    target = plan.section("focus").cells[0]
    regenerate = monthly_composition.monthly_regeneration(
        plan_repository=harness.monthly_plans, provider=provider, clock=harness.clock
    )
    result = regenerate.execute(
        RegenerateMonthlyPlanItemCommand(
            plan.plan_id,
            target.item_id,
            ActorId("reviewer_test"),
        )
    )
    plan = result.plan
    assert len(provider.requests) == 2
    for request in provider.requests:
        payload = json.loads(request.user_content)
        assert len(payload["curriculum_context"]["contents"]) == 59
        assert tuple(payload["parent_subthemes"]) == command.parent_subthemes
    request_version = provider.requests[-1].prompt_version
    regenerated = plan.find_cell(target.item_id)[3]
    assert request_version == "monthly-cell-planner-v15"
    assert result.planner_outcome.prompt_version == request_version
    assert regenerated.generation.rule_version == request_version
    change = regenerated.audit.events[-1].generation_change
    assert change.before == target.generation
    assert change.after == regenerated.generation
    assert change.after.rule_version == request_version
    assert harness.monthly_plans.get(plan.plan_id) == plan


def test_curriculum_failure_stops_before_provider_and_storage(monkeypatch):
    def unavailable():
        raise InvalidDomainValueError("unapproved")

    monkeypatch.setattr(monthly_composition, "v1_curriculum_catalog", unavailable)
    harness, provider, generate, command = _setup()
    with pytest.raises(MonthlyApplicationError, match="curriculum") as error:
        generate.execute(command)
    assert error.value.code == "curriculum_reference_unavailable"
    assert provider.requests == []
    assert not harness.monthly_plans._plans


def test_teacher_memo_reaches_prompt_marks_evidence_and_survives_regeneration():
    from dataclasses import replace

    from ssuksak.planning.planner.teacher_memo import TEACHER_MEMO_EVIDENCE, cell_address

    harness, provider, generate, command = _setup()
    plan = generate.execute(replace(command, teacher_memo="자연물 놀이를 많이")).plan
    first = provider.requests[0]
    payload = json.loads(first.user_content)
    assert payload["teacher_memo"]["text"] == "자연물 놀이를 많이"
    assert first.prompt_version.endswith("+teacher-memo-v1")
    assert plan.teacher_memo == "자연물 놀이를 많이"
    marked = [
        cell
        for section in plan.sections
        for cell in section.cells
        if TEACHER_MEMO_EVIDENCE in cell.evidence
    ]
    # the mock marks only the first allowed address
    assert [cell_address(c.week_id, c.section_key) for c in marked] == list(first.memo_addresses[:1])
    assert "theme" not in first.memo_addresses and not any(
        a.endswith("safety_education") for a in first.memo_addresses
    )

    target = plan.section("focus").cells[0]
    regenerate = monthly_composition.monthly_regeneration(
        plan_repository=harness.monthly_plans, provider=provider, clock=harness.clock
    )
    plan = regenerate.execute(
        RegenerateMonthlyPlanItemCommand(plan.plan_id, target.item_id, ActorId("reviewer_test"))
    ).plan
    assert json.loads(provider.requests[-1].user_content)["teacher_memo"]["text"] == "자연물 놀이를 많이"
    assert TEACHER_MEMO_EVIDENCE in plan.find_cell(target.item_id)[3].evidence


# ADR-066: hidden per-week activity description, one LLM request, never a failure.


def _detail_plan(provider_class=None):
    harness, provider, generate, command = _setup()
    if provider_class is not None:
        provider = provider_class()
        generate = monthly_composition.monthly_generation(
            parent_plan_repository=harness.yearly_plans,
            plan_repository=harness.monthly_plans,
            profile_repository=harness.profiles,
            template_repository=harness.generation_templates,
            provider=provider,
            clock=harness.clock,
            id_generator=harness.monthly_ids,
        )
    return harness, provider, generate.execute(command).plan


class DetailDroppingProvider(RecordingProvider):
    """W1 omits the detail, W2 breaks the 1-2 sentence rule; the rest keep the mock detail."""

    def generate_monthly(self, request):
        from dataclasses import replace

        raw = super().generate_monthly(request)
        payload = json.loads(raw.content)
        outdoor = [s for w in payload["weeks"] for s in w["sections"] if s["section_key"] == "outdoor_play"]
        del outdoor[0]["detail"]
        outdoor[1]["detail"] = "친구와 달려요. 나뭇잎을 모아요. 함께 웃어요."
        return replace(raw, content=json.dumps(payload, ensure_ascii=False))


def test_activity_detail_fills_hidden_week_cells_without_touching_the_activity():
    from ssuksak.planning.domain.provenance import GenerationMethod

    harness, provider, plan = _detail_plan()
    request = provider.requests[0]
    assert request.detail_section_keys == ("outdoor_play",)
    assert request.prompt_version.endswith("+activity-detail-v1")
    assert plan.template_snapshot.section("outdoor_play_detail").visible is False
    outdoor, detail = plan.section("outdoor_play").cells, plan.section("outdoor_play_detail").cells
    assert [c.week_id for c in detail] == [c.week_id for c in outdoor]
    for parent, cell in zip(outdoor, detail):
        assert cell.item_id != parent.item_id and cell.value.endswith("즐겁게 놀아요.")
        assert cell.generation.method is GenerationMethod.RULE_LLM
        assert cell.generation.rule_version == request.prompt_version
        assert cell.evidence == parent.evidence
    _, _, dropped = _detail_plan(DetailDroppingProvider)
    assert [c.value for c in dropped.section("outdoor_play").cells] == [c.value for c in outdoor]


def test_missing_or_invalid_detail_is_empty_and_does_not_block_confirm():
    from ssuksak.planning.domain.monthly_constraint import CellState
    from ssuksak.planning.domain.plan import PlanStatus
    from ssuksak.planning.domain.provenance import AuditEventType, GenerationMethod

    harness, provider, plan = _detail_plan(DetailDroppingProvider)
    assert len(provider.requests) == 1  # no repair call for a detail
    detail = plan.section("outdoor_play_detail").cells
    for cell in detail[:2]:
        assert cell.value == "" and cell.cell_state is CellState.EMPTY_VALID
        assert cell.generation.method is GenerationMethod.RULE_ONLY and cell.evidence == ()
    assert all(cell.value for cell in detail[2:])
    plan = harness.edit_monthly(plan, item_id=detail[0].item_id, value="교사가 쓴 설명이에요.")
    edited = plan.find_cell(detail[0].item_id)[3]
    assert edited.value == "교사가 쓴 설명이에요."
    assert edited.audit.events[-1].event_type is AuditEventType.TEACHER_EDITED
    assert harness.confirm_monthly(plan).status is PlanStatus.CONFIRMED


def test_plan_saved_before_activity_details_still_edits_and_confirms():
    from dataclasses import replace

    from ssuksak.planning.domain.monthly_template_snapshot import ACTIVITY_DETAIL_SECTION_KEYS
    from ssuksak.planning.domain.plan import PlanStatus

    harness, _, plan = _detail_plan()
    details = set(ACTIVITY_DETAIL_SECTION_KEYS.values())
    snapshot = plan.template_snapshot
    old = replace(
        plan,
        template_snapshot=replace(
            snapshot, sections=tuple(s for s in snapshot.sections if s.section_key not in details)
        ),
        sections=tuple(s for s in plan.sections if s.section_key not in details),
    )
    harness.monthly_plans.save(old.plan_id, old)
    target = old.section("outdoor_play").cells[1]
    old = harness.edit_monthly(old, item_id=target.item_id, value="교사가 고친 바깥놀이")
    assert old.section("outdoor_play_detail") is None
    assert harness.confirm_monthly(old).status is PlanStatus.CONFIRMED
