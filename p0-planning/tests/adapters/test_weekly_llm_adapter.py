"""W7a: the weekly path over the real Elice/OpenAI adapter, with a fake transport (no network).

The transport answers with the deterministic weekly mock's content, so these tests pin what
the adapter sends (strict schema per request kind) and that the planner accepts what the
schema allows — never what a real model writes.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ssuksak.adapters.elice_openai_monthly import (
    EliceOpenAiMonthlyAdapter,
    MonthlyLlmConfig,
    MonthlyLlmProviderError,
)
from ssuksak.adapters.request_aware_weekly_llm import RequestAwareWeeklyLlm
from ssuksak.planning.application.monthly_errors import MonthlyApplicationError
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from ssuksak.planning.planner.contracts import MONTHLY_MODEL
from ssuksak.planning.planner.weekly import OUTDOOR_KEY, weekly_response_schema

from tests.finalization.weekly_harness import WeeklyHarness

LLM = MonthlyGenerationMode.LLM_PLANNER


class MockTransport:
    """Answers like RequestAwareWeeklyLlm; `edits` change one answer each (None = untouched)."""

    def __init__(self, *edits, model: str = MONTHLY_MODEL, error: Exception | None = None):
        self.edits, self.model, self.error, self.calls = list(edits), model, error, []

    def post_json(self, url, *, headers, payload, timeout):
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        user = payload["messages"][1]["content"]
        answer = json.loads(RequestAwareWeeklyLlm().generate_weekly(SimpleNamespace(user_content=user)).content)
        edit = self.edits.pop(0) if self.edits else None
        if edit is not None:
            edit(answer)
        content = json.dumps(answer, ensure_ascii=False)
        return {"id": f"req-{len(self.calls)}", "model": self.model, "choices": [{"message": {"content": content}}]}


def _adapter(transport) -> EliceOpenAiMonthlyAdapter:
    return EliceOpenAiMonthlyAdapter(MonthlyLlmConfig("https://mlapi.elice.io/v1", "secret"), transport=transport)


def _conforms(value, schema) -> bool:
    """The JSON Schema keywords the weekly schema uses, and nothing more."""
    if "anyOf" in schema:
        return any(_conforms(value, branch) for branch in schema["anyOf"])
    if "enum" in schema and value not in schema["enum"]:
        return False
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if kind is not None and not isinstance(value, types[kind]):
        return False
    if kind == "object":
        props = schema["properties"]
        return set(value) == set(props) == set(schema["required"]) and all(
            _conforms(value[k], props[k]) for k in props
        )
    if kind == "array":
        return (
            len(value) <= schema.get("maxItems", len(value))
            and len(value) >= schema.get("minItems", 0)
            and all(_conforms(item, schema["items"]) for item in value)
        )
    return True


def _sent(transport, index=0):
    payload = transport.calls[index]
    return payload["response_format"]["json_schema"], json.loads(
        RequestAwareWeeklyLlm().generate_weekly(SimpleNamespace(user_content=payload["messages"][1]["content"])).content
    )


def _set(key, **fields):
    def edit(answer):
        next(s for s in answer["sections"] if s["section_key"] == key).update(fields)
    return edit


def _llm_parent(harness):
    return harness.confirm_monthly(harness.monthly_parent(confirm=False, mode=LLM))


def test_a_document_request_is_strict_and_the_mock_answer_conforms():
    harness = WeeklyHarness()
    transport = MockTransport()
    plan = harness.generate_weekly(_llm_parent(harness), mode=LLM, provider=_adapter(transport)).plan

    spec, answer = _sent(transport)
    assert spec["name"] == "weekly_plan_proposal" and spec["strict"] is True
    assert transport.calls[0]["model"] == MONTHLY_MODEL and "temperature" not in transport.calls[0]
    assert _conforms(answer, spec["schema"])
    assert plan.cell("indoor_play").generation.method.value == "RULE_LLM"  # W3c targets go through too


def test_a_cell_request_allows_only_its_section():
    harness = WeeklyHarness()
    plan = harness.generate_weekly(_llm_parent(harness), mode=LLM).plan
    transport = MockTransport()
    harness.regenerate_weekly(plan, section_key="goals", provider=_adapter(transport))

    spec, answer = _sent(transport)
    assert spec["name"] == "weekly_cell_proposal"
    items = spec["schema"]["properties"]["sections"]["items"]
    assert items["properties"]["section_key"]["enum"] == ["goals"]
    assert _conforms(answer, spec["schema"])


def test_a_repair_request_allows_only_the_flagged_sections():
    harness = WeeklyHarness()
    transport = MockTransport(_set("theme", value="10월 3일 개천절 행사 준비"), None)
    harness.generate_weekly(_llm_parent(harness), mode=LLM, provider=_adapter(transport))

    assert len(transport.calls) == 2
    repair = transport.calls[1]["response_format"]["json_schema"]["schema"]
    assert repair["properties"]["sections"]["items"]["properties"]["section_key"]["enum"] == ["theme"]


def test_outdoor_reference_id_and_label_are_locked_as_pairs():
    harness = WeeklyHarness()
    harness.generate_weekly(_llm_parent(harness), mode=LLM)
    request = harness.weekly_provider.requests[0]
    schema = weekly_response_schema(request)
    (first_id, first_label), (_, second_label) = request.reference_candidates[:2]

    def answer(value, reference_id):
        return {"week_id": request.week_id.value, "sections": [{
            "section_key": OUTDOOR_KEY, "value": value, "unresolved": False,
            "grounding_refs": [], "reference_id": reference_id,
        }]}

    assert _conforms(answer(first_label, first_id), schema)
    assert not _conforms(answer(second_label, first_id), schema)  # another candidate's label
    theme_unresolved = {"week_id": request.week_id.value, "sections": [{
        "section_key": "theme", "value": "", "unresolved": True, "grounding_refs": [], "reference_id": None,
    }]}
    assert not _conforms(theme_unresolved, schema)


@pytest.mark.parametrize(
    "transport",
    [MockTransport(error=MonthlyLlmProviderError("Elice MLAPI request failed")), MockTransport(model="other-model")],
    ids=["provider error", "unexpected model"],
)
def test_provider_failures_save_nothing_and_log_only_codes(transport, caplog):
    harness = WeeklyHarness()
    parent = _llm_parent(harness)
    with caplog.at_level("INFO", logger="ssuksak.planning.planner"):
        with pytest.raises(MonthlyApplicationError) as excinfo:
            harness.generate_weekly(parent, mode=LLM, provider=_adapter(transport))
    assert excinfo.value.code == "weekly_llm_planning_failed"
    assert len(harness.weekly_plans) == 0
    assert "Weekly LLM planning failed: kind=document" in caplog.text
    assert "secret" not in caplog.text


def test_a_planned_request_logs_one_content_free_line(caplog):
    harness = WeeklyHarness()
    parent = _llm_parent(harness)
    with caplog.at_level("INFO", logger="ssuksak.planning.planner"):
        plan = harness.generate_weekly(parent, mode=LLM, provider=_adapter(MockTransport())).plan
    assert "Weekly LLM planned: kind=document repaired=0 fingerprint=" in caplog.text
    assert plan.cell("theme").value not in caplog.text  # never generated text


def test_the_request_fingerprint_covers_what_was_sent():
    harness = WeeklyHarness()
    plan = harness.generate_weekly(_llm_parent(harness), mode=LLM).plan
    harness.regenerate_weekly(plan, section_key="goals")
    document, cell = harness.weekly_provider.requests
    assert document.packet_fingerprint == cell.packet_fingerprint  # the monthly Packet is the same
    assert document.request_fingerprint != cell.request_fingerprint  # what was sent is not
