"""Elice Adapter의 Monthly Planner 경로 (L4).

**실제 API를 호출하지 않는다.** client를 주입해 전 경로를 네트워크 없이 태운다.
Live Smoke는 `analysis/experiments/monthly_llm_vnext/live_smoke_l4.py`다.
"""

from __future__ import annotations

import pytest

from ssuksak.adapters.elice_mlapi_adapter import (
    MAX_REPAIR_ATTEMPTS,
    EliceMLAPIAdapter,
)
from ssuksak.shared.llm.config import LLMApiStyle, LLMConfig
from ssuksak.shared.llm.monthly import (
    MonthlyPlannerRequest,
    MonthlyPlanProposal,
    MonthlyProposalError,
    MonthlyProposalViolation,
    ProposedActivity,
    ProposedActivityOrigin,
    ProposedWeek,
)
from ssuksak.shared.llm.port import LLMConfigurationError, LLMUnavailableError

THEME = "yr_theme_summer"
WEEKS = ("2026-07-W1", "2026-07-W2")
LABELS = {"act_a": "물총놀이 하기", "act_b": "여름 그늘 산책"}
REFS = frozenset({"E01"})


def config(**over) -> LLMConfig:
    kwargs = {
        "base_url": "https://example.invalid/v1",
        "model": "test-model",
        "timeout_seconds": 5.0,
        "max_retries": 1,
        "api_key": "unit-test-placeholder",
        "reasoning_effort": None,
        "api_style": LLMApiStyle.CHAT_COMPLETIONS,
    }
    kwargs.update(over)
    return LLMConfig(**kwargs)


def request() -> MonthlyPlannerRequest:
    return MonthlyPlannerRequest(
        task="plan_monthly",
        prompt_version="monthly-planner-prompt-test",
        system_prompt="system",
        user_content="context",
        expected_theme_id=THEME,
        expected_week_ids=WEEKS,
        reference_labels=LABELS,
        valid_grounding_refs=REFS,
        packet_fingerprint="f" * 64,
    )


def good_proposal(theme_id: str = THEME) -> MonthlyPlanProposal:
    return MonthlyPlanProposal(
        theme_id=theme_id,
        month_flow_rationale="관심에서 표현으로 이어집니다.",
        weeks=[
            ProposedWeek(
                week_id=WEEKS[0], experience="여름을 느껴요",
                activity=ProposedActivity(
                    value=LABELS["act_a"],
                    origin=ProposedActivityOrigin.REFERENCE,
                    reference_activity_id="act_a",
                    grounding_refs=[],
                ),
            ),
            ProposedWeek(
                week_id=WEEKS[1], experience="그늘에서 쉬어요",
                activity=ProposedActivity(
                    value=LABELS["act_b"],
                    origin=ProposedActivityOrigin.REFERENCE,
                    reference_activity_id="act_b",
                    grounding_refs=[],
                ),
            ),
        ],
    )


# ------------------------------------------------------------- Fake client


class _Message:
    def __init__(self, parsed, refusal=None):
        self.parsed = parsed
        self.refusal = refusal


class _Choice:
    def __init__(self, parsed, refusal=None):
        self.message = _Message(parsed, refusal)


class _Response:
    def __init__(self, parsed, refusal=None):
        self.choices = [_Choice(parsed, refusal)]
        self.id = "resp_test"
        self.usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()


class _Completions:
    def __init__(self, script):
        self._script = list(script)
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        item = self._script.pop(0) if self._script else self._script_default()
        if isinstance(item, Exception):
            raise item
        return _Response(item)

    @staticmethod
    def _script_default():
        raise AssertionError("스크립트보다 많이 호출되었다")


class _Client:
    def __init__(self, script):
        self.chat = type("C", (), {"completions": _Completions(script)})()

    @property
    def calls(self):
        return self.chat.completions.calls


def adapter(script, *, cfg: LLMConfig | None = None, records=None):
    client = _Client(script)
    return (
        EliceMLAPIAdapter(
            cfg or config(),
            client=client,
            telemetry_sink=(records.append if records is not None else None),
            sleep=lambda _: None,
        ),
        client,
    )


# ============================================== 정상 경로


def test_a_valid_proposal_is_returned_after_one_call():
    llm, client = adapter([good_proposal()])
    result = llm.plan_monthly(request())
    assert result.theme_id == THEME
    assert len(client.calls) == 1


def test_the_request_prompt_is_sent_verbatim():
    """Prompt 본문은 Adapter가 아니라 Request가 들고 온다."""
    llm, client = adapter([good_proposal()])
    llm.plan_monthly(request())
    messages = client.calls[0]["messages"]
    assert messages[0]["content"] == "system"
    assert messages[1]["content"] == "context"


def test_structured_output_schema_is_passed_to_the_provider():
    llm, client = adapter([good_proposal()])
    llm.plan_monthly(request())
    assert client.calls[0]["response_format"] is MonthlyPlanProposal


# ============================================== Repair


def test_a_contract_violation_triggers_exactly_one_repair():
    llm, client = adapter([good_proposal(theme_id="wrong"), good_proposal()])
    result = llm.plan_monthly(request())
    assert result.theme_id == THEME
    assert len(client.calls) == 2


def test_the_repair_call_carries_the_original_context_and_the_violation():
    llm, client = adapter([good_proposal(theme_id="wrong"), good_proposal()])
    llm.plan_monthly(request())
    repair = client.calls[1]["messages"][1]["content"]
    assert repair.startswith("context")
    assert MonthlyProposalViolation.THEME_ID_MISMATCH.value in repair


def test_repair_is_not_unlimited():
    llm, client = adapter(
        [good_proposal(theme_id="wrong")] * (MAX_REPAIR_ATTEMPTS + 1)
    )
    with pytest.raises(MonthlyProposalError) as exc:
        llm.plan_monthly(request())
    assert exc.value.violation is MonthlyProposalViolation.THEME_ID_MISMATCH
    assert len(client.calls) == MAX_REPAIR_ATTEMPTS + 1


def test_no_empty_or_rule_only_proposal_is_substituted_on_failure():
    """조용한 fallback을 만들지 않는다 (OD-N15)."""
    llm, _ = adapter([good_proposal(theme_id="wrong")] * 2)
    with pytest.raises(MonthlyProposalError):
        llm.plan_monthly(request())


# ============================================== Transport 실패


class _Timeout(Exception):
    pass


_Timeout.__name__ = "APITimeoutError"


class _Auth(Exception):
    pass


_Auth.__name__ = "AuthenticationError"


def test_transient_failure_is_retried_then_succeeds():
    llm, client = adapter([_Timeout("t"), good_proposal()])
    assert llm.plan_monthly(request()).theme_id == THEME
    assert len(client.calls) == 2


def test_transport_failure_becomes_llm_unavailable():
    llm, _ = adapter([_Timeout("t"), _Timeout("t")])
    with pytest.raises(LLMUnavailableError):
        llm.plan_monthly(request())


def test_auth_failure_is_not_retried():
    llm, client = adapter([_Auth("bad key")])
    with pytest.raises(LLMConfigurationError):
        llm.plan_monthly(request())
    assert len(client.calls) == 1


def test_missing_parsed_output_is_a_schema_error():
    llm, _ = adapter([None])
    with pytest.raises(ValueError, match="parsed"):
        llm.plan_monthly(request())


# ============================================== Telemetry


def test_telemetry_records_the_monthly_call_without_prompt_or_key():
    records: list = []
    llm, _ = adapter([good_proposal()], records=records)
    llm.plan_monthly(request())

    assert len(records) == 1
    payload = records[0].to_log_dict()
    assert payload["operation"] == "plan_monthly"
    assert payload["item_count"] == len(WEEKS)
    assert payload["retry_count"] == 0
    assert payload["template_version"] == "monthly-planner-prompt-test"
    assert payload["repair_count"] == 0

    blob = str(payload)
    assert "unit-test-placeholder" not in blob
    assert "system" not in blob
    assert "context" not in blob


def test_telemetry_counts_the_repair_attempt():
    records: list = []
    llm, _ = adapter([good_proposal(theme_id="wrong"), good_proposal()], records=records)
    llm.plan_monthly(request())
    assert [r.extra["repair_count"] for r in records] == [0, 1]


def test_telemetry_rejects_a_prompt_body_key():
    """`prompt_version`을 쓰지 않은 이유를 고정한다."""
    from ssuksak.shared.llm.telemetry import LLMCallRecord

    with pytest.raises(ValueError, match="민감 키"):
        LLMCallRecord(
            operation="plan_monthly", provider="p", model="m", success=True,
            latency_ms=1, retry_count=0, item_count=1,
            extra={"prompt_version": "v1"},
        )


# ============================================== Yearly 경로 불변


def test_the_yearly_batch_path_still_works():
    from ssuksak.shared.llm.batch import (
        PolishedThemeOut,
        ThemeBatchPolishItem,
        ThemeBatchPolishRequest,
        ThemeBatchPolishResponse,
    )

    response = ThemeBatchPolishResponse(
        themes=[PolishedThemeOut(period_key="2026-07", theme_id="t1", value="여름이에요")]
    )
    llm, client = adapter([response])
    out = llm.polish_themes(
        ThemeBatchPolishRequest(
            task="polish", school_year=2026, ages=(4,),
            items=(ThemeBatchPolishItem(
                period_key="2026-07", theme_id="t1", label="여름"),),
        )
    )
    assert out.themes[0].value == "여름이에요"
    assert client.calls[0]["response_format"] is ThemeBatchPolishResponse
