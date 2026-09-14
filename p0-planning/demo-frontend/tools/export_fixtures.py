"""Demo fixture 생성기 (일회성 도구).

**이 파일은 Demo가 실행될 때 쓰이지 않는다.** `index.html`은 이미 생성된
`fixtures/*.js`만 읽으며 Backend를 전혀 import하지 않는다. 이 스크립트는
"Demo에 박힌 숫자가 어디서 왔는지"를 재현 가능하게 남기기 위한 기록용이다.

실행 (저장소 루트에서):

    python demo-frontend/tools/export_fixtures.py

생성물:

    demo-frontend/fixtures/monthly_2026_09_age4.js     2026-09 / 만4세 / DRAFT
    demo-frontend/fixtures/monthly_2026_09_confirmed.js 같은 Plan의 CONFIRMED
    demo-frontend/fixtures/monthly_2026_09_no_activity.js Activity 미연결 (EMPTY_VALID)
    demo-frontend/fixtures/monthly_2026_03_age4.js     2026-03 / 만4세 / 4주

주의:

- Production 코드를 읽기만 한다. 수정하지 않는다.
- 출력 JSON 구조는 **Demo 표시용 view model**이며 Backend Contract가 아니다.
  Backend DTO가 바뀌어도 이 파일만 고치면 된다.
- LLM / 네트워크를 쓰지 않는다.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ssuksak.dev.monthly_wiring import (  # noqa: E402
    DEV_ACTOR,
    build_monthly_wiring,
)
from ssuksak.planning.application.monthly_dto import (  # noqa: E402
    ConfirmMonthlyPlanCommand,
    GenerateMonthlyPlanCommand,
)
from ssuksak.planning.domain.provenance import EvidenceSourceType  # noqa: E402

OUT_DIR = ROOT / "demo-frontend" / "fixtures"

DISPLAY_LABELS = {
    "theme": "주제",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
}

CELL_STATE_NOTE = {
    "FILLED": "값 있음",
    "EMPTY_VALID": "채울 근거가 없는 것이 정상",
    "EMPTY_UNRESOLVED": "채워야 하는데 배치 source가 없음",
}


def _generate(wiring):
    return wiring.generate.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=wiring.parent_yearly.plan_id.value,
            school_year=wiring.school_year,
            target_month=wiring.target_month,
            daycare=wiring.daycare,
            classroom=wiring.classroom,
            planning_setup=wiring.planning_setup,
            template_ref=wiring.template_ref,
            safety_rule=wiring.safety_rule,
            catalog=wiring.catalog,
            activity_catalog=wiring.activity_catalog,
        )
    )


def _cell_view(item) -> dict:
    evidence = [
        {
            "source_type": e.source_type.value,
            "source_id": e.source_id,
            "source_version": e.source_version,
            "display_name": e.display_name,
        }
        for e in item.evidence
    ]
    return {
        "week_id": item.week_id.value if item.week_id else None,
        "value": item.value,
        "cell_state": item.cell_state.value,
        "cell_state_note": CELL_STATE_NOTE.get(item.cell_state.value, ""),
        "generation": {
            "method": item.generation.method.value,
            "rule_id": item.generation.rule_id,
            "rule_version": item.generation.rule_version,
        },
        "evidence": evidence,
        "activity_id": next(
            (
                e.source_id
                for e in item.evidence
                if e.source_type is EvidenceSourceType.ACTIVITY_REFERENCE
            ),
            None,
        ),
        "audit": [
            {
                "event_type": a.event_type.value,
                "occurred_at": a.occurred_at.isoformat(),
                "actor": a.actor_id.value if a.actor_id else (a.system_actor or "-"),
            }
            for a in item.audit.events
        ],
    }


def _view_model(plan, run, *, title: str, note: str) -> dict:
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
        if section.section_key in ("theme", "week_axis"):
            continue
        if not section.items:
            continue
        rows.append(
            {
                "section_key": section.section_key,
                "label": DISPLAY_LABELS.get(section.section_key, section.section_key),
                "source_label": section.source_label,
                "cells": [_cell_view(i) for i in section.items],
            }
        )
    return {
        "fixture": True,
        "fixture_title": title,
        "fixture_note": note,
        "generated_by": "demo-frontend/tools/export_fixtures.py",
        "header": {
            "school_year": plan.school_year,
            "target_month": plan.target_month.value,
            "calendar_year": int(plan.target_month.value[:4]),
            "calendar_month": int(plan.target_month.value[5:7]),
            "classroom_ref": plan.classroom_ref,
            "daycare_ref": plan.daycare_ref,
            "ages": sorted(plan.classroom_ages),
            "age_mode": plan.age_mode,
            "status": plan.status.value,
            "plan_id": plan.plan_id.value,
            "template_version": plan.template_ref.template_version,
        },
        "theme": _cell_view(theme_section.items[0]) if theme_section.items else None,
        "parent_lineage": {
            "parent_yearly_plan_id": plan.parent_lineage.parent_yearly_plan_id,
            "parent_yearly_theme_id": plan.parent_lineage.parent_yearly_theme_id,
            "parent_yearly_value": plan.parent_lineage.parent_yearly_value,
            "reference_version": plan.parent_lineage.reference_version,
        },
        "activity_catalog": (
            None
            if plan.activity_catalog is None
            else {
                "catalog_id": plan.activity_catalog.catalog_id,
                "catalog_version": plan.activity_catalog.catalog_version,
            }
        ),
        "weeks": weeks,
        "rows": rows,
        "constraints": [
            {
                "kind": a.kind.value,
                "verification": a.verification.value,
                "rule_version": a.rule_version,
                "detail": a.detail,
            }
            for a in plan.constraint_assessments
        ],
        "run": None
        if run is None
        else {
            "run_id": run.run_id,
            "llm_call_count": run.llm_call_count,
            "week_period_count": run.week_period_count,
            "filled_cell_count": run.filled_cell_count,
            "empty_valid_cell_count": run.empty_valid_cell_count,
            "empty_unresolved_cell_count": run.empty_unresolved_cell_count,
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
                    "theme_matched": t.theme_matched,
                    "parent_theme_id": t.parent_theme_id,
                    "rule_id": t.rule_id,
                    "rule_version": t.rule_version,
                }
                for t in run.activity_selection_traces
            ],
        },
    }


def _write(name: str, global_key: str, payload: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    text = (
        "// 자동 생성 파일 — 직접 수정하지 마세요.\n"
        "// 생성: python demo-frontend/tools/export_fixtures.py\n"
        "// 이것은 Demo 표시용 FIXTURE 스냅샷이며 Backend Contract가 아닙니다.\n"
        "window.SSUKSAK_DEMO_FIXTURES = window.SSUKSAK_DEMO_FIXTURES || {};\n"
        f"window.SSUKSAK_DEMO_FIXTURES[{global_key!r}] = {body};\n"
    )
    target = OUT_DIR / f"{name}.js"
    target.write_text(text, encoding="utf-8")
    print(f"  wrote {target.relative_to(ROOT)}  ({len(text):,} bytes)")


def main() -> int:
    print("Demo fixture 생성 (Production 코드는 읽기 전용)")

    # 1) 2026-09 / 만4세 / DRAFT + 같은 Plan의 CONFIRMED
    w = build_monthly_wiring()
    result = _generate(w)
    _write(
        "monthly_2026_09_age4",
        "2026-09-draft",
        _view_model(
            result.plan,
            result.run,
            title="2026-09 · 만 4세 · DRAFT",
            note="실제 Composition 실행 결과 스냅샷 (LLM 0회 / 네트워크 0회)",
        ),
    )
    confirmed = w.confirm.execute(
        ConfirmMonthlyPlanCommand(plan_id=result.plan.plan_id.value, actor_id=DEV_ACTOR)
    ).plan
    _write(
        "monthly_2026_09_confirmed",
        "2026-09-confirmed",
        _view_model(
            confirmed,
            result.run,
            title="2026-09 · 만 4세 · CONFIRMED",
            note="같은 Plan을 ConfirmMonthlyPlan으로 확정한 상태. "
            "안전교육은 여전히 미검증이다 (CONFIRMED ≠ Safety verified)",
        ),
    )

    # 2) Activity Reference 없이 생성한 Plan — EMPTY_VALID 표시 확인용
    w_m1 = build_monthly_wiring()
    r_m1 = w_m1.generate.execute(
        GenerateMonthlyPlanCommand(
            parent_yearly_plan_id=w_m1.parent_yearly.plan_id.value,
            school_year=w_m1.school_year,
            target_month=w_m1.target_month,
            daycare=w_m1.daycare,
            classroom=w_m1.classroom,
            planning_setup=w_m1.planning_setup,
            template_ref=w_m1.template_ref,
            safety_rule=w_m1.safety_rule,
            catalog=w_m1.catalog,
            # activity_catalog을 주지 않는다 (Optional)
        )
    )
    _write(
        "monthly_2026_09_no_activity",
        "2026-09-no-activity",
        _view_model(
            r_m1.plan,
            r_m1.run,
            title="2026-09 · 만 4세 · Activity Reference 미연결",
            note="Activity Catalog을 주지 않은 생성 결과. 바깥놀이가 EMPTY_VALID로 "
            "남는다. 이는 실패가 아니라 '채울 근거가 없다'는 정상 상태다",
        ),
    )

    # 3) 4주 달
    w4 = build_monthly_wiring(target_month="2026-03")
    r4 = _generate(w4)
    _write(
        "monthly_2026_03_age4",
        "2026-03-draft",
        _view_model(
            r4.plan,
            r4.run,
            title="2026-03 · 만 4세 · DRAFT (4주)",
            note="주차 수가 4인 달. 표가 4열로 렌더링되는지 확인용",
        ),
    )

    print("완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
