"""Deterministic Weekly LLM provider for development and tests (``LLM_MODE=mock``).

Every answer is derived from the request — its targets, allowed refs, parent context and
ranked outdoor candidates — so it keeps passing Core validation when those change. It
never calls a network and must never stand in for a failed real provider.
"""

from __future__ import annotations

import json

from ssuksak.planning.planner.contracts import MONTHLY_MODEL, RawLlmResponse
from ssuksak.planning.planner.weekly import WeeklyPlanningRequest


class RequestAwareWeeklyLlm:
    def __init__(self) -> None:
        self.requests: list[WeeklyPlanningRequest] = []

    def generate_weekly(self, request: WeeklyPlanningRequest) -> RawLlmResponse:
        self.requests.append(request)
        body = json.loads(request.user_content)
        if "original_request" in body:  # a repair answers the same way
            body = body["original_request"]
        parent = body["parent"]
        theme = parent["theme"]
        again = "다시 쓴 " if body.get("task") == "weekly_cell" else ""  # W4b: a regenerated value differs
        sections = []
        for target in body["targets"]:
            key, refs = target["section_key"], target["allowed_grounding_refs"]
            value, reference_id, grounding = f"{again}{theme} — 이번 주 {key} 계획", None, refs[:1]
            if target.get("activity_type"):
                noun = "자유놀이" if key.startswith("indoor_play.candidate.") else "활동"
                value = f"{target['activity_type']} {noun} {key.rsplit('.', 1)[-1]}: 자료 속 대상을 함께 탐색합니다."
            elif key == "theme":
                value, grounding = f"{again}{theme} 속 이번 주 놀이", []
            elif key == "outdoor_play":
                if target.get("parent_groundable"):
                    value = f"{again}{parent[key]}" if refs else parent[key]
                    grounding = refs[:1] if again else []
                elif target["reference_candidates"]:
                    reference_id, value = (target["reference_candidates"][0][k] for k in ("reference_id", "label"))
                    grounding = []
            elif key == "safety_education":
                value, grounding = f"{again}이번 주에도 {parent['safety_education']}", []
            if target.get("days"):  # ADR-051: one distinct value per requested day
                sections.append({"section_key": key, "reference_id": None, "days": [
                    {"day": day, "value": f"{value} {day}", "unresolved": False, "grounding_refs": grounding}
                    for day in target["days"]
                ]})
                continue
            sections.append({
                "section_key": key, "value": value, "unresolved": False,
                "grounding_refs": grounding, "reference_id": reference_id,
            })
        answer = {"week_id": body["week"]["week_id"], "sections": sections}
        if getattr(request, "memo_addresses", None) is not None and not request.repair_targets:
            answer["memo_applied"] = list(request.memo_addresses[:1])  # exercises the evidence path
            answer["memo_skipped"] = []
        content = json.dumps(answer, ensure_ascii=False)
        return RawLlmResponse(content=content, model=MONTHLY_MODEL)
