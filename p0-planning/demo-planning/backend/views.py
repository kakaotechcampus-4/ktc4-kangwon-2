"""Domain 객체 → Demo 화면용 JSON 변환.

**표시용 view model이며 Backend Contract가 아니다.** Production DTO가 바뀌면
이 파일만 고치면 된다. 판단·계산을 하지 않고 이미 결정된 값을 옮겨 담기만 한다.
"""

from __future__ import annotations

import calendar

from ssuksak.planning.domain.provenance import EvidenceSourceType

__all__ = ["error_view", "monthly_view", "yearly_view"]

SECTION_LABELS = {
    "theme": "주제",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
    "goals": "목표",
    "habits": "기본생활습관",
    "focus": "중심 경험",
}
"""교사에게 보이는 label.

`focus` · `week_axis` 같은 **내부 이름을 사용자에게 그대로 노출하지 않는다.**
`focus`는 주차별 중심 경험을 담으므로 그대로 "중심 경험"으로 보여준다
(2026-09-14 L8. 이전 "주간 중점"에서 바꿨다 — 담는 내용이 무엇인지 더 분명하다).
""" 

ROW_DISPLAY_ORDER = {
    "focus": 1,
    "outdoor_play": 2,
    "safety_education": 3,
    "habits": 4,
    "goals": 5,
}
"""화면 행 순서. **표시 전용이며 Template이나 Plan의 Section 순서를 바꾸지 않는다.**

그 주의 중심 경험 → 활동 → 안전교육 순이 교사가 읽기 자연스럽다.
"""

CELL_STATE_NOTE = {
    "FILLED": "값 있음",
    "EMPTY_VALID": "채울 근거가 없는 것이 정상입니다",
    "EMPTY_UNRESOLVED": "채워야 하지만 배치 source가 없어 비워 두었습니다",
}

MONTH_LABELS = {
    3: "3월", 4: "4월", 5: "5월", 6: "6월", 7: "7월", 8: "8월",
    9: "9월", 10: "10월", 11: "11월", 12: "12월", 1: "1월", 2: "2월",
}


def _generation(detail) -> dict:
    return {
        "method": detail.method.value,
        "rule_id": detail.rule_id,
        "rule_version": detail.rule_version,
    }


def _evidence(sources) -> list[dict]:
    return [
        {
            "source_type": e.source_type.value,
            "source_id": e.source_id,
            "source_version": e.source_version,
            "display_name": e.display_name,
        }
        for e in sources
    ]


def _audit(trail) -> list[dict]:
    return [
        {
            "event_type": e.event_type.value,
            "occurred_at": e.occurred_at.isoformat(),
            "actor": e.actor_id.value if e.actor_id else (e.system_actor or "-"),
            "previous_value": e.previous_value,
            "new_value": e.new_value,
        }
        for e in trail.events
    ]


def _activity_id(item) -> str | None:
    for source in item.evidence:
        if source.source_type is EvidenceSourceType.ACTIVITY_REFERENCE:
            return source.source_id
    return None


# ------------------------------------------------------------------- Yearly


def yearly_view(plan, run=None) -> dict:
    months = []
    for period in plan.month_periods:
        theme = period.theme
        months.append(
            {
                "period_key": period.period_key.value,
                "calendar_month": period.period_key.calendar_month,
                "month_label": MONTH_LABELS.get(
                    period.period_key.calendar_month,
                    f"{period.period_key.calendar_month}월",
                ),
                "item_id": theme.item_id.value,
                "semantic_key": theme.semantic_key.value,
                "value": theme.value,
                "generation": _generation(theme.generation),
                "evidence": _evidence(theme.evidence),
                "theme_id": next(
                    (
                        e.source_id
                        for e in theme.evidence
                        if e.source_type is EvidenceSourceType.THEME_REFERENCE
                    ),
                    None,
                ),
                "audit": _audit(theme.audit),
            }
        )

    return {
        "plan_id": plan.plan_id.value,
        "school_year": plan.school_year,
        "status": plan.status.value,
        "classroom_ref": plan.classroom_ref,
        "ages": sorted(plan.classroom_ages),
        "months": months,
        "audit": _audit(plan.audit),
        "run": None
        if run is None
        else {
            "run_id": run.run_id,
            "llm_invoked": run.llm_invoked,
            "llm_call_count": run.llm_call_count,
            "catalog_id": getattr(run, "catalog_id", None),
            "catalog_version": getattr(run, "catalog_version", None),
            "traces": [
                {
                    "period_key": t.period_key,
                    "reason": t.reason,
                    "selected_theme_id": t.selected_theme_id,
                    "rule_id": t.rule_id,
                    "rule_version": t.rule_version,
                    "eligible_count": len(t.eligible_theme_ids),
                    "evidence_strength": t.evidence_strength,
                    "avoided_adjacent_repeat": t.avoided_adjacent_repeat,
                }
                for t in getattr(run, "selection_traces", ())
            ],
        },
    }


# ------------------------------------------------------------------ Monthly


def _cell_view(item) -> dict:
    return {
        "week_id": item.week_id.value if item.week_id else None,
        "item_id": item.item_id.value,
        "value": item.value,
        "cell_state": item.cell_state.value,
        "cell_state_note": CELL_STATE_NOTE.get(item.cell_state.value, ""),
        "generation": _generation(item.generation),
        "evidence": _evidence(item.evidence),
        "activity_id": _activity_id(item),
        "audit": _audit(item.audit),
    }


def monthly_view(plan, run=None) -> dict:
    weeks = [
        {
            "week_id": w.week_id.value,
            "ordinal": index,
            "label": w.display_label,
            "start": w.start_date.isoformat(),
            "end": w.end_date.isoformat(),
            "active": w.active,
        }
        for index, w in enumerate(plan.week_periods, start=1)
    ]

    theme_section = plan.section("theme")
    rows = []
    for section in plan.sections:
        if section.section_key in ("theme", "week_axis") or not section.items:
            continue
        rows.append(
            {
                "section_key": section.section_key,
                "label": SECTION_LABELS.get(section.section_key, section.section_key),
                "cells": [_cell_view(i) for i in section.items],
            }
        )
    # 표시 순서만 정한다. Template의 Section 정의나 Plan의 sections 순서를
    # 바꾸지 않는다. `focus`는 Template JSON에서 마지막에 정의돼 있지만 화면에서는
    # 그 주의 중심 경험이 먼저 오고 활동이 따라오는 편이 읽기 자연스럽다.
    rows.sort(key=lambda r: ROW_DISPLAY_ORDER.get(r["section_key"], 99))

    year = int(plan.target_month.value[:4])
    month = int(plan.target_month.value[5:7])
    # 달의 첫날·마지막 날. **주차 날짜가 아니다.**
    #
    # 주차 경계는 Domain의 canonical WeekPeriod가 정하며 대상 월 밖으로 나갈 수
    # 있다(OD-M02 — 7월 1주가 6/29에 시작한다). 여기서 만드는 것은 문서 머리말의
    # `기간: 2026.06.01 ~ 2026.06.30`뿐이고, 달력 산술이라 Domain 결정이 아니다.
    # Frontend가 날짜를 스스로 계산하지 않도록 View가 대신 계산해 준다.
    month_last_day = calendar.monthrange(year, month)[1]

    return {
        "plan_id": plan.plan_id.value,
        "school_year": plan.school_year,
        "target_month": plan.target_month.value,
        "calendar_year": year,
        "calendar_month": month,
        "month_start": f"{year:04d}-{month:02d}-01",
        "month_end": f"{year:04d}-{month:02d}-{month_last_day:02d}",
        "status": plan.status.value,
        "daycare_ref": plan.daycare_ref,
        "classroom_ref": plan.classroom_ref,
        "ages": sorted(plan.classroom_ages),
        "age_mode": plan.age_mode,
        "template_version": plan.template_ref.template_version,
        "theme": _cell_view(theme_section.items[0]) if theme_section.items else None,
        "parent_lineage": {
            "parent_yearly_plan_id": plan.parent_lineage.parent_yearly_plan_id,
            "parent_yearly_period_key": plan.parent_lineage.parent_yearly_period_key,
            "parent_yearly_theme_id": plan.parent_lineage.parent_yearly_theme_id,
            "parent_yearly_value": plan.parent_lineage.parent_yearly_value,
            "reference_catalog_id": plan.parent_lineage.reference_catalog_id,
            "reference_version": plan.parent_lineage.reference_version,
        },
        "activity_catalog": None
        if plan.activity_catalog is None
        else {
            "catalog_id": plan.activity_catalog.catalog_id,
            "catalog_version": plan.activity_catalog.catalog_version,
        },
        "weeks": weeks,
        "rows": rows,
        "constraints": [
            {
                "kind": a.kind.value,
                "verification": a.verification.value,
                "rule_version": a.rule_version,
                "required_source_kinds": list(a.required_source_kinds),
                "detail": a.detail,
            }
            for a in plan.constraint_assessments
        ],
        "audit": _audit(plan.audit),
        "run": None
        if run is None
        else {
            "run_id": run.run_id,
            "week_period_count": run.week_period_count,
            "generated_cell_count": run.generated_cell_count,
            "filled_cell_count": run.filled_cell_count,
            "empty_valid_cell_count": run.empty_valid_cell_count,
            "empty_unresolved_cell_count": run.empty_unresolved_cell_count,
            "llm_invoked": run.llm_invoked,
            "llm_call_count": run.llm_call_count,
            "generation_mode": run.generation_mode,
            # Debug Panel 전용. Prompt 본문·API Key·Source 전문은 담기지 않는다.
            "planner_model": run.planner_model,
            "prompt_version": run.prompt_version,
            "planner_validation_repair_count": run.planner_validation_repair_count,
            "planner_repaired_violations": list(run.planner_repaired_violations),
            "activity_catalog_id": run.activity_catalog_id,
            "activity_catalog_version": run.activity_catalog_version,
            "activity_filled_cell_count": run.activity_filled_cell_count,
            "activity_unfilled_cell_count": run.activity_unfilled_cell_count,
            "traces": [
                {
                    "week_id": t.week_id,
                    "reason": t.reason,
                    "selected_activity_id": t.selected_activity_id,
                    "selected_label": t.selected_label,
                    "candidate_count": t.candidate_count,
                    "evidence_strength": t.evidence_strength,
                    "repeat_penalty": t.repeat_penalty,
                    "theme_matched": t.theme_matched,
                    "parent_theme_id": t.parent_theme_id,
                    "rule_id": t.rule_id,
                    "rule_version": t.rule_version,
                }
                for t in run.activity_selection_traces
            ],
        },
    }


# -------------------------------------------------------------------- Error


def error_view(error) -> dict:
    """PlanningError를 그대로 옮긴다. 문구를 새로 만들지 않는다."""
    return {
        "ok": False,
        "kind": "PLANNING_ERROR",
        "outcome": error.outcome.value,
        "failure_category": error.failure_category.value,
        "violated_rule": error.violated_rule,
        "violations": [
            {
                "category": v.category.value,
                "violated_rule": v.violated_rule,
                "detail": v.detail,
                "period_key": v.period_key,
            }
            for v in error.violations
        ],
        "message": str(error),
    }
