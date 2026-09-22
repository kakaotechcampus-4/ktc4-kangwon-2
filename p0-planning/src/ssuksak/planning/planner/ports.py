"""Narrow provider capabilities required by the Monthly planners."""

from __future__ import annotations

from typing import Protocol

from .contracts import MonthlyCellPlanningRequest, MonthlyPlanningRequest, RawLlmResponse


class MonthlyPlanningProvider(Protocol):
    def generate_monthly(self, request: MonthlyPlanningRequest) -> RawLlmResponse: ...


class MonthlyCellPlanningProvider(Protocol):
    def generate_cell(self, request: MonthlyCellPlanningRequest) -> RawLlmResponse: ...
