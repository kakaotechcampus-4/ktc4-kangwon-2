"""The mock Monthly provider also words safety and drill candidates (LLM_MODE=mock)."""

import hashlib

from ssuksak.adapters.request_aware_monthly_llm import RequestAwareMonthlyLlm
from ssuksak.planning.domain.monthly_plan import MonthlyGenerationMode
from tests.application.test_monthly_application import (
    Harness,
    _candidate_harness,
    _drill_command,
)

# SHA-256 of the response for an ordinary v1 request (no candidates, no drill), taken before candidates were added.
ORDINARY_RESPONSE_SHA256 = "675d1646f1d108ed5c59f223f89d47230d93a40589278308d740fd8db7afbd40"


class RecordingProvider(RequestAwareMonthlyLlm):
    def __init__(self):
        self.requests = []

    def generate_monthly(self, request):
        self.requests.append(request)
        return super().generate_monthly(request)


def test_plain_mock_words_all_eight_safety_candidates():
    harness, command = _candidate_harness()
    plan = harness.generate(provider=RecordingProvider(), command=command).plan

    assert len(plan.safety_candidates) == 8
    assert all(c.cell.value.strip() for c in plan.safety_candidates)


def test_plain_mock_words_drill_candidates():
    harness = Harness()
    plan = harness.generate(provider=RecordingProvider(), command=_drill_command(harness)).plan

    assert plan.drill_candidates
    assert all(c.cell.value.strip() for c in plan.drill_candidates)


def test_response_without_candidate_keys_is_byte_identical():
    provider = RecordingProvider()
    Harness().generate(MonthlyGenerationMode.LLM_PLANNER, provider=provider)
    response = RequestAwareMonthlyLlm().generate_monthly(provider.requests[0])

    assert hashlib.sha256(response.content.encode("utf-8")).hexdigest() == ORDINARY_RESPONSE_SHA256
