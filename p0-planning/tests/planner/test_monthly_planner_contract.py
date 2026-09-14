"""Monthly Planner — Port · Proposal · reconcile · FakeLLM (L4).

실제 API를 호출하지 않는다. Live Smoke는 별도 스크립트이며 테스트가 아니다
(CLAUDE.md: 일반 pytest에서 실제 Elice API를 호출하지 않는다).
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from ssuksak.planning.context.models import ActivityOrigin as ContextActivityOrigin
from ssuksak.shared.llm.fake import FakeLLM, FakeLLMMode
from ssuksak.shared.llm.monthly import (
    MonthlyPlannerRequest,
    MonthlyPlanProposal,
    MonthlyProposalError,
    MonthlyProposalViolation,
    ProposedActivity,
    ProposedActivityOrigin,
    ProposedWeek,
    reconcile_monthly_proposal,
)
from ssuksak.shared.llm.port import LLMPort, LLMUnavailableError

THEME = "yr_theme_summer"
WEEKS = ("2026-07-W1", "2026-07-W2")
LABELS = {"act_a": "물총놀이 하기", "act_b": "여름 그늘 산책"}
REFS = frozenset({"E01", "E02"})


def activity(
    *,
    value: str = "물총놀이 하기",
    origin: ProposedActivityOrigin = ProposedActivityOrigin.REFERENCE,
    reference_activity_id: str | None = "act_a",
    grounding_refs: list[str] | None = None,
) -> ProposedActivity:
    return ProposedActivity(
        value=value,
        origin=origin,
        reference_activity_id=reference_activity_id,
        grounding_refs=grounding_refs if grounding_refs is not None else [],
    )


def synthesized(value: str = "여름 물놀이 마당", refs: list[str] | None = None):
    return activity(
        value=value,
        origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
        reference_activity_id=None,
        grounding_refs=refs if refs is not None else ["E01"],
    )


def proposal(weeks=None, *, theme_id: str = THEME) -> MonthlyPlanProposal:
    if weeks is None:
        weeks = [
            ProposedWeek(week_id=WEEKS[0], experience="여름을 느껴요", activity=activity()),
            ProposedWeek(
                week_id=WEEKS[1],
                experience="그늘에서 쉬어요",
                activity=activity(value="여름 그늘 산책", reference_activity_id="act_b"),
            ),
        ]
    return MonthlyPlanProposal(
        theme_id=theme_id, month_flow_rationale="관심에서 표현으로 이어집니다.", weeks=weeks
    )


def reconcile(p: MonthlyPlanProposal, **over):
    kwargs = {
        "expected_theme_id": THEME,
        "expected_week_ids": WEEKS,
        "reference_labels": LABELS,
        "valid_grounding_refs": REFS,
    }
    kwargs.update(over)
    return reconcile_monthly_proposal(p, **kwargs)


# ============================================== Port


def test_port_declares_plan_monthly():
    assert hasattr(LLMPort, "plan_monthly")


def test_port_keeps_the_existing_methods_unchanged():
    """Additive 변경이다. Yearly 경로가 깨지면 안 된다."""
    for name in ("polish_theme", "polish_themes"):
        assert hasattr(LLMPort, name)
    sig = inspect.signature(LLMPort.polish_theme)
    assert list(sig.parameters) == ["self", "request"]


def test_fake_and_adapter_both_satisfy_the_extended_port():
    from ssuksak.adapters.elice_mlapi_adapter import EliceMLAPIAdapter

    for impl in (FakeLLM, EliceMLAPIAdapter):
        for name in ("polish_theme", "polish_themes", "plan_monthly"):
            assert callable(getattr(impl, name, None)), f"{impl.__name__}.{name}"


# ============================================== Request


def request(**over) -> MonthlyPlannerRequest:
    kwargs = {
        "task": "plan_monthly",
        "prompt_version": "test",
        "system_prompt": "system",
        "user_content": "content",
        "expected_theme_id": THEME,
        "expected_week_ids": WEEKS,
        "reference_labels": LABELS,
        "valid_grounding_refs": REFS,
    }
    kwargs.update(over)
    return MonthlyPlannerRequest(**kwargs)


def test_request_rejects_empty_anchors():
    with pytest.raises(ValueError, match="expected_theme_id"):
        request(expected_theme_id="  ")
    with pytest.raises(ValueError, match="expected_week_ids"):
        request(expected_week_ids=())
    with pytest.raises(ValueError, match="중복"):
        request(expected_week_ids=(WEEKS[0], WEEKS[0]))
    with pytest.raises(ValueError, match="비어 있을 수 없다"):
        request(user_content="   ")


# ============================================== Proposal schema


def test_valid_proposal_parses_and_reconciles():
    assert reconcile(proposal()) is not None


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        MonthlyPlanProposal(
            theme_id=THEME,
            month_flow_rationale="x",
            weeks=[
                ProposedWeek(
                    week_id=WEEKS[0], experience="e", activity=activity()
                )
            ],
            surprise="y",
        )


def test_unknown_field_inside_activity_is_rejected():
    with pytest.raises(ValidationError):
        ProposedActivity(
            value="v",
            origin=ProposedActivityOrigin.REFERENCE,
            reference_activity_id="act_a",
            grounding_refs=[],
            confidence=0.9,
        )


def test_invalid_origin_is_rejected():
    with pytest.raises(ValidationError):
        ProposedActivity(
            value="v",
            origin="CORPUS_EVIDENCE",
            reference_activity_id=None,
            grounding_refs=["E01"],
        )


def test_blank_strings_are_rejected():
    for field in ("theme_id", "month_flow_rationale"):
        payload = {
            "theme_id": THEME,
            "month_flow_rationale": "x",
            "weeks": [
                {"week_id": WEEKS[0], "experience": "e",
                 "activity": activity().model_dump()}
            ],
        }
        payload[field] = "   "
        with pytest.raises(ValidationError):
            MonthlyPlanProposal.model_validate(payload)


def test_proposal_has_no_place_for_safety():
    """자리를 만들면 모델이 채운다. 애초에 두지 않는다."""
    assert not [f for f in MonthlyPlanProposal.model_fields if "safety" in f]
    assert not [f for f in ProposedWeek.model_fields if "safety" in f]
    assert not [f for f in ProposedActivity.model_fields if "safety" in f]


def test_proposed_origin_is_a_subset_of_the_context_origin_enum():
    """shared가 planning을 import하지 않으려고 값을 복제했다. 어긋나면 실패한다."""
    proposed = {o.value for o in ProposedActivityOrigin}
    context = {o.value for o in ContextActivityOrigin}
    assert proposed <= context
    assert "CORPUS_EVIDENCE" not in proposed
    assert "CORPUS_EVIDENCE" in context


# ============================================== Theme / Week Lock


def test_theme_id_must_be_returned_unchanged():
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(theme_id="yr_theme_other"))
    assert exc.value.violation is MonthlyProposalViolation.THEME_ID_MISMATCH


def test_missing_week_is_rejected():
    weeks = [ProposedWeek(week_id=WEEKS[0], experience="e", activity=activity())]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks))
    assert exc.value.violation is MonthlyProposalViolation.MISSING_WEEK


def test_unknown_week_is_rejected():
    weeks = [
        ProposedWeek(week_id=WEEKS[0], experience="e", activity=activity()),
        ProposedWeek(week_id="2026-07-W9", experience="e", activity=activity()),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks))
    assert exc.value.violation is MonthlyProposalViolation.EXTRA_WEEK


def test_duplicate_week_is_rejected():
    weeks = [
        ProposedWeek(week_id=WEEKS[0], experience="e", activity=activity()),
        ProposedWeek(week_id=WEEKS[0], experience="e", activity=activity()),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks))
    assert exc.value.violation is MonthlyProposalViolation.DUPLICATE_WEEK


def test_reordered_weeks_are_rejected():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[1], experience="e",
            activity=activity(value="여름 그늘 산책", reference_activity_id="act_b"),
        ),
        ProposedWeek(week_id=WEEKS[0], experience="e", activity=activity()),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks))
    assert exc.value.violation is MonthlyProposalViolation.WEEK_ORDER_MISMATCH


# ============================================== REFERENCE 계약


def test_reference_requires_an_activity_id():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e",
            activity=activity(reference_activity_id=None),
        ),
        ProposedWeek(
            week_id=WEEKS[1], experience="e",
            activity=activity(value="여름 그늘 산책", reference_activity_id="act_b"),
        ),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks))
    assert exc.value.violation is MonthlyProposalViolation.REFERENCE_REQUIRES_ID


def test_reference_id_must_exist_in_the_packet():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e",
            activity=activity(reference_activity_id="act_invented"),
        ),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks), expected_week_ids=(WEEKS[0],))
    assert exc.value.violation is MonthlyProposalViolation.UNKNOWN_REFERENCE_ID


def test_reference_value_must_match_the_catalog_label():
    """id만 맞추고 문구를 바꾸는 것을 막는다."""
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e",
            activity=activity(value="물총놀이를 신나게 해요"),
        ),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks), expected_week_ids=(WEEKS[0],))
    assert exc.value.violation is MonthlyProposalViolation.REFERENCE_VALUE_MISMATCH


def test_reference_value_tolerates_whitespace_only_difference():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e",
            activity=activity(value="물총놀이  하기 "),
        ),
    ]
    assert reconcile(proposal(weeks), expected_week_ids=(WEEKS[0],))


# ============================================== LLM_SYNTHESIZED 계약


def test_synthesized_requires_grounding_refs():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e", activity=synthesized(refs=[])
        ),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks), expected_week_ids=(WEEKS[0],))
    assert exc.value.violation is MonthlyProposalViolation.SYNTHESIZED_REQUIRES_GROUNDING


def test_synthesized_must_not_claim_a_reference_id():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e",
            activity=activity(
                value="새 활동",
                origin=ProposedActivityOrigin.LLM_SYNTHESIZED,
                reference_activity_id="act_a",
                grounding_refs=["E01"],
            ),
        ),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks), expected_week_ids=(WEEKS[0],))
    assert (
        exc.value.violation
        is MonthlyProposalViolation.SYNTHESIZED_MUST_NOT_CLAIM_REFERENCE
    )


def test_grounding_ref_must_exist_in_the_packet():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e", activity=synthesized(refs=["E99"])
        ),
    ]
    with pytest.raises(MonthlyProposalError) as exc:
        reconcile(proposal(weeks), expected_week_ids=(WEEKS[0],))
    assert exc.value.violation is MonthlyProposalViolation.UNKNOWN_GROUNDING_REF


def test_a_valid_synthesized_activity_passes():
    weeks = [
        ProposedWeek(
            week_id=WEEKS[0], experience="e", activity=synthesized(refs=["E01", "E02"])
        ),
    ]
    assert reconcile(proposal(weeks), expected_week_ids=(WEEKS[0],))


def test_violation_summary_carries_no_prompt_body():
    error = MonthlyProposalError(
        MonthlyProposalViolation.MISSING_WEEK, "반환되지 않은 주차: ['W2']"
    )
    assert "W2" in error.summary
    assert "system" not in error.summary


# ============================================== FakeLLM


def test_fake_returns_the_configured_proposal():
    fake = FakeLLM(monthly_proposal=proposal())
    result = fake.plan_monthly(request())
    assert result.theme_id == THEME
    assert fake.monthly_call_count == 1


def test_fake_refuses_when_no_proposal_was_configured():
    with pytest.raises(ValueError, match="설정되지 않았다"):
        FakeLLM().plan_monthly(request())


def test_fake_applies_the_same_reconcile_as_the_adapter():
    fake = FakeLLM(monthly_proposal=proposal(theme_id="yr_theme_other"))
    with pytest.raises(MonthlyProposalError):
        fake.plan_monthly(request())


def test_fake_can_inject_transport_failure():
    fake = FakeLLM(FakeLLMMode.UNAVAILABLE, monthly_proposal=proposal())
    with pytest.raises(LLMUnavailableError):
        fake.plan_monthly(request())


def test_fake_can_inject_schema_failure():
    fake = FakeLLM(FakeLLMMode.SCHEMA_VIOLATION, monthly_proposal=proposal())
    with pytest.raises(ValueError):
        fake.plan_monthly(request())


def test_fake_yearly_behaviour_is_unchanged():
    """plan_monthly 추가가 기존 경로를 건드리지 않았는지 본다."""
    from ssuksak.shared.llm.port import ThemePolishRequest

    fake = FakeLLM()
    out = fake.polish_theme(
        ThemePolishRequest(
            task="polish", selected_theme_id="t1", selected_theme_label="여름",
            period_key="2026-07", ages=(4,),
        )
    )
    assert out.theme_id == "t1"
    assert fake.call_count == 1
    assert fake.monthly_call_count == 0
