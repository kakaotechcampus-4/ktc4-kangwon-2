"""Context Packet -> provider -> parsed and validated Monthly proposal."""

from __future__ import annotations

import logging

from ..context.models import MonthlyContextPacket
from ..domain.monthly_template_snapshot import TemplateSnapshot
from .contracts import (
    MONTHLY_REPAIR_PROMPT_VERSION,
    MONTHLY_SAFETY_REPAIR_PROMPT_VERSION,
    is_compatible_monthly_model,
    MonthlyPlanningOutcome,
    MonthlyPlanningRequest,
    ProposalRejectedError,
)
from .parser import parse_monthly_proposal
from .ports import MonthlyPlanningProvider
from .prompt import build_monthly_planning_request, build_monthly_repair_request
from .validation import validate_monthly_proposal

_log = logging.getLogger(__name__)

# OD-N04: content findings a single repair generation may fix. Anything else
# (model, parse, structure, placement, AXIS, theme, unknown refs) fails closed.
# SAFETY_GROUNDING_MISMATCH is a ref choice inside a fixed slot, like
# WRONG_SOURCE_GROUNDING; SAFETY_PLACEMENT_MISMATCH changes the slot and fails closed.
# Safety focus/quality findings are re-selection or rewriting inside the same slot.
REPAIRABLE_CODES = frozenset(
    {
        "SOURCE_TEXT_COPY", "TEXT_POLICY", "WRONG_SOURCE_GROUNDING", "SAFETY_GROUNDING_MISMATCH",
        "SAFETY_FOCUS_MISMATCH", "SAFETY_MULTIPLE_SENTENCES", "SAFETY_DUPLICATE_CONTENT", "SAFETY_DUPLICATE_REFERENCE",
    }
)


def finding_summary(issues) -> str:
    """Code, location and stable reason per finding; no generated or evidence text."""
    return "; ".join(
        f"{issue.code.value}@{issue.week_id or 'month'}/{issue.field}"
        + (f" reason={issue.reason}" if issue.reason else "")
        + (f" expected={issue.expected}" if issue.expected else "")
        + (f" actual={issue.actual}" if issue.actual else "")
        for issue in issues
    )


class MonthlyPlanner:
    def __init__(self, provider: MonthlyPlanningProvider) -> None:
        self._provider = provider

    def plan(
        self, packet: MonthlyContextPacket, snapshot: TemplateSnapshot
    ) -> MonthlyPlanningOutcome:
        request = build_monthly_planning_request(packet, snapshot)
        response, proposal, validation = self._attempt(packet, request)
        if not validation.is_valid and set(validation.codes) <= REPAIRABLE_CODES:
            # At most one repair call: 2 provider calls in total, never 3.
            _log.info("Monthly LLM repair attempted: %s", finding_summary(validation.issues))
            request = build_monthly_repair_request(
                request, response.content, validation.issues
            )
            try:
                response, proposal, validation = self._attempt(packet, request)
            except Exception:
                _log.warning("Monthly LLM repair failed before validation")
                raise
            if validation.is_valid:
                _log.info("Monthly LLM repair succeeded")
            else:
                _log.warning("Monthly LLM repair failed: %s", finding_summary(validation.issues))
        if not validation.is_valid:
            if request.prompt_version not in (MONTHLY_REPAIR_PROMPT_VERSION, MONTHLY_SAFETY_REPAIR_PROMPT_VERSION):
                _log.warning("Monthly LLM proposal rejected: %s", finding_summary(validation.issues))
            raise ProposalRejectedError(validation.codes, validation.issues)
        return MonthlyPlanningOutcome(
            proposal=proposal,
            model=response.model,
            prompt_version=request.prompt_version,
            packet_fingerprint=request.packet_fingerprint,
            request_id=response.request_id,
        )

    def _attempt(self, packet: MonthlyContextPacket, request: MonthlyPlanningRequest):
        response = self._provider.generate_monthly(request)
        if not is_compatible_monthly_model(response.model):
            raise ProposalRejectedError(("UNEXPECTED_MODEL",))
        proposal = parse_monthly_proposal(response.content)
        return response, proposal, validate_monthly_proposal(proposal, packet, request)
