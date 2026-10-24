"""P1 prototype: one play-project period, fake provider, InMemory storage (ADR-042)."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ssuksak.adapters import elice_openai_monthly
from ssuksak.adapters.deterministic import DeterministicIdGenerator, FixedClock
from ssuksak.adapters.elice_openai_monthly import (
    EliceOpenAiMonthlyAdapter,
    MonthlyLlmConfig,
    MonthlyLlmProviderError,
)
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


def _row(n: int, ids=("nuri2019.3.1.1", "nuri2019.3.1.2")) -> dict:
    return {
        "play_name": f"놀이 {n}",
        "materials": "종이 상자, 크레파스 등 준비해 볼 자료",
        "support_direction": "관심이 이어지면 자료를 더해 놀이를 넓혀 갈 수 있도록 돕는다.",
        "learning_content_ids": list(ids),
    }


def _proposal(rows=None, period_key="m03_m05") -> dict:
    return {"period_key": period_key, "rows": rows if rows is not None else [_row(n) for n in range(1, 11)]}


def _rest() -> list[dict]:
    return [_row(n) for n in range(2, 11)]


def _run(provider, curriculum=None):
    plans = InMemoryPlanRepository()
    use_case = GeneratePlayProjectPlan(
        curriculum_repository=curriculum or _Approved(),
        plan_repository=plans,
        provider=provider,
        clock=FixedClock(datetime(2027, 2, 1, tzinfo=UTC)),
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
    provider = _FakeProvider(_proposal([_row(1, ("nuri2019.1.1.2", "nuri2019.5.3.3"))] + _rest()))
    use_case, command, plans = _run(provider)

    plan = use_case.execute(command)

    assert plan.status is PlanStatus.DRAFT
    assert plans.get(plan.plan_id) == plan
    (period,) = plan.periods
    assert period.period.label == "3월~5월" and len(period.candidates) == 10
    first = period.candidates[0]
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
    assert first.semantic_key("m03_m05", "learning") == "play_project.m03_m05.cand1.learning"
    # The request lets the LLM pick ids only from the active Reference.
    assert len(provider.requests[0].allowed_content_ids) == 59
    assert provider.requests[0].row_count == 10


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
        (_proposal([_row(n) for n in range(1, 6)]), "ROW_COUNT"),  # 5 rows: the old shape
        (_proposal(period_key="m06_m08"), "PERIOD_MISMATCH"),
        (_proposal([_row(1, ("nuri2019.9.9.9", "nuri2019.3.1.1"))] + _rest()), "UNKNOWN_CONTENT_ID"),
        (_proposal([_row(1, ("nuri2019.3.1.1",))] + _rest()), "LEARNING_COUNT"),  # 2~3 since 10-24
        (_proposal([_row(1, ("nuri2019.1.1.1", "nuri2019.1.1.2", "nuri2019.1.1.3", "nuri2019.1.2.1"))] + _rest()), "LEARNING_COUNT"),
        (_proposal([_row(1)] * 10), "DUPLICATE_PLAY_NAME"),
        (_proposal([{**_row(1), "materials": " "}] + _rest()), "MATERIALS:BLANK_TEXT"),
    ],
)
def test_rejected_proposal_stores_nothing(proposal, code):
    use_case, command, plans = _run(_FakeProvider(proposal))

    with pytest.raises(ProposalRejectedError) as error:
        use_case.execute(command)

    assert code in error.value.validation_codes
    assert len(plans) == 0


def test_other_periods_plays_reach_the_request_and_an_exact_repeat_is_rejected():
    provider = _FakeProvider(_proposal())
    use_case, command, plans = _run(provider)

    with pytest.raises(ProposalRejectedError) as error:
        use_case.execute(replace(command, avoid_play_names=("놀이  3", "봄 산책")))

    assert json.loads(provider.requests[0].user_content)["avoid_play_names"] == ["놀이  3", "봄 산책"]
    assert "DUPLICATE_PLAY_NAME" in error.value.validation_codes
    assert len(plans) == 0


@pytest.mark.parametrize(
    "text",
    [
        "4월 17일 오전 10시에 모여 산책 놀이를 지원하면 봄꽃을 살펴볼 것으로 기대해봅니다.",
        "김가상 선생님과 함께 산책 놀이를 지원하면 봄꽃을 살펴볼 것으로 기대해봅니다.",
        "매주 월요일에 산책 놀이를 지원하면 봄꽃을 살펴볼 것으로 기대해봅니다.",
    ],
)
def test_a_date_time_or_teacher_name_not_in_the_input_is_rejected(text):
    rows = [{**_row(1), "support_direction": text}]
    use_case, command, plans = _run(_FakeProvider(_proposal(rows + _rest())))

    with pytest.raises(ProposalRejectedError) as error:
        use_case.execute(command)

    assert "SUPPORT_DIRECTION:UNSUPPORTED_FACT" in error.value.validation_codes
    assert len(plans) == 0


def test_holiday_names_stay_allowed():
    rows = [{**_row(1), "support_direction": "어린이날을 앞두고 선생님과 함께 놀이를 지원합니다."}]
    use_case, command, plans = _run(_FakeProvider(_proposal(rows + _rest())))

    use_case.execute(command)

    assert len(plans) == 1


class _Response(io.BytesIO):
    status = 200


def _streaming_adapter(monkeypatch, *chunks, done=True):
    lines = ["data: " + json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks]
    body = "".join(lines + (["data: [DONE]\n"] if done else [])).encode()
    monkeypatch.setattr(
        elice_openai_monthly.urllib_request, "urlopen", lambda *a, **kw: _Response(body)
    )
    return EliceOpenAiMonthlyAdapter(MonthlyLlmConfig("https://offline.invalid/v1", "test-only"))


def _content(finish_reason="stop") -> dict:
    content = json.dumps(_proposal(), ensure_ascii=False)
    return {"choices": [{"delta": {"content": content}, "finish_reason": finish_reason}]}


def test_a_cleanly_finished_stream_is_stored(monkeypatch):
    use_case, command, plans = _run(_streaming_adapter(monkeypatch, _content()))

    use_case.execute(command)

    assert len(plans) == 1


@pytest.mark.parametrize(
    ("chunks", "done"),
    [
        ((_content(),), False),  # valid JSON, connection closed before [DONE]
        ((_content(None), {"error": {"message": "PRIVATE"}}), True),
        ((_content("length"),), True),  # valid JSON, but the reply was cut at the cap
    ],
)
def test_a_stream_that_did_not_finish_cleanly_stores_nothing(monkeypatch, chunks, done):
    use_case, command, plans = _run(_streaming_adapter(monkeypatch, *chunks, done=done))

    with pytest.raises(MonthlyLlmProviderError):
        use_case.execute(command)

    assert len(plans) == 0


def test_safety_words_are_allowed_in_play_text():
    rows = [{**_row(1), "support_direction": "교통안전 규칙을 지키며 산책길을 걸어 본다."}]
    use_case, command, _ = _run(_FakeProvider(_proposal(rows + _rest())))

    plan = use_case.execute(command)

    assert plan.periods[0].candidates[0].support_direction.value.startswith("교통안전")


def test_extra_key_fails_strict_parse():
    rows = [{**_row(1), "domain": "신체운동·건강"}] + _rest()
    use_case, command, plans = _run(_FakeProvider(_proposal(rows)))

    with pytest.raises(ProposalParseError):
        use_case.execute(command)
    assert len(plans) == 0
