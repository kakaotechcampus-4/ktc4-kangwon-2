"""P1 prototype: one play-project period, fake provider, InMemory storage (ADR-042)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.in_memory_plan_repository import InMemoryPlanRepository
from ssuksak.adapters.json_curriculum_reference_repository import (
    JsonCurriculumReferenceRepository,
)
from ssuksak.planning.application.generate_play_project_plan import (
    GeneratePlayProjectPlan,
    GeneratePlayProjectPlanCommand,
    PlayProjectGenerationError,
)
from ssuksak.planning.domain.plan import PlanStatus
from ssuksak.planning.domain.provenance import EvidenceSourceType, GenerationMethod
from ssuksak.planning.domain.theme_reference import ActivationStatus
from ssuksak.planning.planner.contracts import (
    ProposalParseError,
    ProposalRejectedError,
    RawLlmResponse,
)

CATALOG_ID = "ssuksak.nuri-curriculum-content"
VERSION = "nuri-curriculum-content-v0.1.0"


class _Approved:
    """Test-only approved view of the draft; the real file stays PENDING_HUMAN_REVIEW."""

    def __init__(self) -> None:
        self._inner = JsonCurriculumReferenceRepository()

    def get_catalog(self, catalog_id, catalog_version):
        catalog = self._inner.get_catalog(catalog_id, catalog_version)
        return replace(catalog, activation_status=ActivationStatus.HUMAN_APPROVED)


class _FakeProvider:
    def __init__(self, payload: dict | str) -> None:
        self.payload = payload
        self.requests = []

    def generate_play_project(self, request):
        self.requests.append(request)
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return RawLlmResponse(content=content, model="fake")


def _row(n: int, ids=("nuri2019.3.1.1",)) -> dict:
    return {
        "play_name": f"놀이 {n}",
        "materials": "종이 상자, 크레파스 등 준비해 볼 자료",
        "support_direction": "관심이 이어지면 자료를 더해 놀이를 넓혀 갈 수 있도록 돕는다.",
        "learning_content_ids": list(ids),
    }


def _proposal(rows=None, period_key="m03_m05") -> dict:
    return {"period_key": period_key, "rows": rows if rows is not None else [_row(n) for n in range(1, 6)]}


def _run(provider, curriculum=None):
    plans = InMemoryPlanRepository()
    use_case = GeneratePlayProjectPlan(
        curriculum_repository=curriculum or _Approved(),
        plan_repository=plans,
        provider=provider,
        clock=FixedClock(datetime(2027, 2, 1, tzinfo=timezone.utc)),
        id_generator=DeterministicIdGenerator(),
    )
    command = GeneratePlayProjectPlanCommand(
        school_year=2027,
        classroom_ref="classroom-test",
        target_ages=frozenset({4, 5}),
        period_key="m03_m05",
        curriculum_catalog_id=CATALOG_ID,
        curriculum_catalog_version=VERSION,
    )
    return use_case, command, plans


def test_generates_a_draft_period_with_server_rendered_learning():
    provider = _FakeProvider(_proposal([_row(1, ("nuri2019.1.1.2", "nuri2019.5.3.3"))] + [_row(n) for n in range(2, 6)]))
    use_case, command, plans = _run(provider)

    plan = use_case.execute(command)

    assert plan.status is PlanStatus.DRAFT
    assert plans.get(plan.plan_id) == plan
    (period,) = plan.periods
    assert period.period.label == "3월~5월" and len(period.rows) == 5
    first = period.rows[0]
    assert first.learning.value == (
        "신체운동·건강 - 신체활동 즐기기 - 신체 움직임을 조절한다.\n"
        "자연탐구 - 자연과 더불어 살기 - 날씨와 계절의 변화를 생활과 관련짓는다."
    )
    assert [(e.source_type, e.source_id, e.source_version) for e in first.learning.evidence] == [
        (EvidenceSourceType.CURRICULUM, "nuri2019.1.1.2", VERSION),
        (EvidenceSourceType.CURRICULUM, "nuri2019.5.3.3", VERSION),
    ]
    assert first.play_name.evidence == ()  # no institution evidence in P1
    assert first.play_name.generation.method is GenerationMethod.RULE_LLM
    assert first.semantic_key("m03_m05", "learning") == "play_project.m03_m05.row1.learning"
    # The request lets the LLM pick ids only from the active Reference.
    assert len(provider.requests[0].allowed_content_ids) == 59


def test_pending_reference_blocks_before_the_llm_call():
    provider = _FakeProvider(_proposal())
    use_case, command, plans = _run(provider, JsonCurriculumReferenceRepository())

    with pytest.raises(PlayProjectGenerationError) as error:
        use_case.execute(command)

    assert error.value.code == "CURRICULUM_REFERENCE_NOT_ACTIVE"
    assert provider.requests == [] and len(plans) == 0


@pytest.mark.parametrize(
    ("proposal", "code"),
    [
        (_proposal([_row(n) for n in range(1, 5)]), "ROW_COUNT"),
        (_proposal(period_key="m06_m08"), "PERIOD_MISMATCH"),
        (_proposal([_row(1, ("nuri2019.9.9.9",))] + [_row(n) for n in range(2, 6)]), "UNKNOWN_CONTENT_ID"),
        (_proposal([_row(1, ())] + [_row(n) for n in range(2, 6)]), "LEARNING_COUNT"),
        (_proposal([_row(1)] * 5), "DUPLICATE_PLAY_NAME"),
        (_proposal([{**_row(1), "materials": " "}] + [_row(n) for n in range(2, 6)]), "MATERIALS:BLANK_TEXT"),
    ],
)
def test_rejected_proposal_stores_nothing(proposal, code):
    use_case, command, plans = _run(_FakeProvider(proposal))

    with pytest.raises(ProposalRejectedError) as error:
        use_case.execute(command)

    assert code in error.value.validation_codes
    assert len(plans) == 0


def test_safety_words_are_allowed_in_play_text():
    rows = [{**_row(1), "support_direction": "교통안전 규칙을 지키며 산책길을 걸어 본다."}]
    use_case, command, plans = _run(_FakeProvider(_proposal(rows + [_row(n) for n in range(2, 6)])))

    plan = use_case.execute(command)

    assert plan.periods[0].rows[0].support_direction.value.startswith("교통안전")


def test_extra_key_fails_strict_parse():
    rows = [{**_row(1), "domain": "신체운동·건강"}] + [_row(n) for n in range(2, 6)]
    use_case, command, plans = _run(_FakeProvider(_proposal(rows)))

    with pytest.raises(ProposalParseError):
        use_case.execute(command)
    assert len(plans) == 0
