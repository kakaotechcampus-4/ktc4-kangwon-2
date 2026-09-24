"""Context Packet -> provider -> parsed and validated single-cell proposal."""

from __future__ import annotations

from ..context.models import MonthlyContextPacket
from ..domain.monthly_template_snapshot import TemplateSnapshot
from ..domain.week_period import WeekId
from .cell_prompt import build_monthly_cell_request
from .cell_validation import validate_monthly_cell_proposal
from .contracts import (
    is_compatible_monthly_model,
    MonthlyCellPlanningOutcome,
    MonthlyCellSnapshot,
    ProposalRejectedError,
)
from .parser import parse_monthly_cell_proposal
from .ports import MonthlyCellPlanningProvider


class MonthlyCellPlanner:
    def __init__(self, provider: MonthlyCellPlanningProvider) -> None:
        self._provider = provider

    def plan(
        self,
        packet: MonthlyContextPacket,
        snapshot: TemplateSnapshot,
        *,
        target_week_id: WeekId | None,
        target_section_key: str,
        month_snapshot: tuple[MonthlyCellSnapshot, ...],
    ) -> MonthlyCellPlanningOutcome:
        request = build_monthly_cell_request(
            packet,
            snapshot,
            target_week_id=target_week_id,
            target_section_key=target_section_key,
            month_snapshot=month_snapshot,
        )
        response = self._provider.generate_cell(request)
        if not is_compatible_monthly_model(response.model):
            raise ProposalRejectedError(("UNEXPECTED_MODEL",))
        proposal = parse_monthly_cell_proposal(response.content)
        validation = validate_monthly_cell_proposal(
            proposal, packet, request
        )
        if not validation.is_valid:
            raise ProposalRejectedError(validation.codes)
        return MonthlyCellPlanningOutcome(
            proposal=proposal,
            model=response.model,
            prompt_version=request.prompt_version,
            packet_fingerprint=request.packet_fingerprint,
            plan_snapshot_fingerprint=request.plan_snapshot_fingerprint,
            request_id=response.request_id,
        )
