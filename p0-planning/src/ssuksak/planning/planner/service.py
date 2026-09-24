"""Context Packet -> provider -> parsed and validated Monthly proposal."""

from __future__ import annotations

from ..context.models import MonthlyContextPacket
from ..domain.monthly_template_snapshot import TemplateSnapshot
from .contracts import (
    is_compatible_monthly_model,
    MonthlyPlanningOutcome,
    ProposalRejectedError,
)
from .parser import parse_monthly_proposal
from .ports import MonthlyPlanningProvider
from .prompt import build_monthly_planning_request
from .validation import validate_monthly_proposal


class MonthlyPlanner:
    def __init__(self, provider: MonthlyPlanningProvider) -> None:
        self._provider = provider

    def plan(
        self, packet: MonthlyContextPacket, snapshot: TemplateSnapshot
    ) -> MonthlyPlanningOutcome:
        request = build_monthly_planning_request(packet, snapshot)
        response = self._provider.generate_monthly(request)
        if not is_compatible_monthly_model(response.model):
            raise ProposalRejectedError(("UNEXPECTED_MODEL",))
        proposal = parse_monthly_proposal(response.content)
        validation = validate_monthly_proposal(proposal, packet, request)
        if not validation.is_valid:
            raise ProposalRejectedError(validation.codes)
        return MonthlyPlanningOutcome(
            proposal=proposal,
            model=response.model,
            prompt_version=request.prompt_version,
            packet_fingerprint=request.packet_fingerprint,
            request_id=response.request_id,
        )
