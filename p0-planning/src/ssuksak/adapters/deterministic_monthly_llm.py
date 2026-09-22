"""Deterministic test adapter for the two Monthly planning capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field

from ssuksak.planning.planner.contracts import (
    MONTHLY_MODEL,
    MonthlyCellPlanningRequest,
    MonthlyPlanningRequest,
    RawLlmResponse,
)


@dataclass(slots=True)
class DeterministicMonthlyLlm:
    monthly_content: str
    cell_content: str
    model: str = MONTHLY_MODEL
    monthly_requests: list[MonthlyPlanningRequest] = field(default_factory=list)
    cell_requests: list[MonthlyCellPlanningRequest] = field(default_factory=list)

    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse:
        self.monthly_requests.append(request)
        return RawLlmResponse(self.monthly_content, self.model, "fake-monthly-1")

    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse:
        self.cell_requests.append(request)
        return RawLlmResponse(self.cell_content, self.model, "fake-cell-1")
