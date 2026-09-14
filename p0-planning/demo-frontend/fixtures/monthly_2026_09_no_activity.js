// 자동 생성 파일 — 직접 수정하지 마세요.
// 생성: python demo-frontend/tools/export_fixtures.py
// 이것은 Demo 표시용 FIXTURE 스냅샷이며 Backend Contract가 아닙니다.
window.SSUKSAK_DEMO_FIXTURES = window.SSUKSAK_DEMO_FIXTURES || {};
window.SSUKSAK_DEMO_FIXTURES['2026-09-no-activity'] = {
  "fixture": true,
  "fixture_title": "2026-09 · 만 4세 · Activity Reference 미연결",
  "fixture_note": "Activity Catalog을 주지 않은 생성 결과. 바깥놀이가 EMPTY_VALID로 남는다. 이는 실패가 아니라 '채울 근거가 없다'는 정상 상태다",
  "generated_by": "demo-frontend/tools/export_fixtures.py",
  "header": {
    "school_year": 2026,
    "target_month": "2026-09",
    "calendar_year": 2026,
    "calendar_month": 9,
    "classroom_ref": "dev_classroom_001",
    "daycare_ref": "dev_daycare_001",
    "ages": [
      4
    ],
    "age_mode": "SINGLE",
    "status": "DRAFT",
    "plan_id": "devm_plan_002",
    "template_version": "monthly-template-a-v0.1.0"
  },
  "theme": {
    "week_id": null,
    "value": "우리나라와 세계 여러 나라",
    "cell_state": "FILLED",
    "cell_state_note": "값 있음",
    "generation": {
      "method": "RULE_ONLY",
      "rule_id": "monthly.theme.parent_anchor_derivation",
      "rule_version": "v1"
    },
    "evidence": [
      {
        "source_type": "PARENT_PLAN",
        "source_id": "devm_plan_001",
        "source_version": "theme-reference-v0.1.2",
        "display_name": "우리나라와 세계 여러 나라"
      },
      {
        "source_type": "THEME_REFERENCE",
        "source_id": "yr_theme_korea_and_world_cultures",
        "source_version": "theme-reference-v0.1.2",
        "display_name": null
      }
    ],
    "activity_id": null,
    "audit": [
      {
        "event_type": "CREATED",
        "occurred_at": "2026-09-12T02:06:19+09:00",
        "actor": "SYSTEM"
      }
    ]
  },
  "parent_lineage": {
    "parent_yearly_plan_id": "devm_plan_001",
    "parent_yearly_theme_id": "yr_theme_korea_and_world_cultures",
    "parent_yearly_value": "우리나라와 세계 여러 나라",
    "reference_version": "theme-reference-v0.1.2"
  },
  "activity_catalog": null,
  "weeks": [
    {
      "week_id": "2026-09-W1",
      "ordinal": 1,
      "label": "9월 1주",
      "start": "2026-08-31",
      "end": "2026-09-04",
      "active": true
    },
    {
      "week_id": "2026-09-W2",
      "ordinal": 2,
      "label": "9월 2주",
      "start": "2026-09-07",
      "end": "2026-09-11",
      "active": true
    },
    {
      "week_id": "2026-09-W3",
      "ordinal": 3,
      "label": "9월 3주",
      "start": "2026-09-14",
      "end": "2026-09-18",
      "active": true
    },
    {
      "week_id": "2026-09-W4",
      "ordinal": 4,
      "label": "9월 4주",
      "start": "2026-09-21",
      "end": "2026-09-25",
      "active": true
    },
    {
      "week_id": "2026-09-W5",
      "ordinal": 5,
      "label": "9월 5주",
      "start": "2026-09-28",
      "end": "2026-10-02",
      "active": true
    }
  ],
  "rows": [
    {
      "section_key": "outdoor_play",
      "label": "바깥놀이",
      "source_label": null,
      "cells": [
        {
          "week_id": "2026-09-W1",
          "value": "",
          "cell_state": "EMPTY_VALID",
          "cell_state_note": "채울 근거가 없는 것이 정상",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W2",
          "value": "",
          "cell_state": "EMPTY_VALID",
          "cell_state_note": "채울 근거가 없는 것이 정상",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W3",
          "value": "",
          "cell_state": "EMPTY_VALID",
          "cell_state_note": "채울 근거가 없는 것이 정상",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W4",
          "value": "",
          "cell_state": "EMPTY_VALID",
          "cell_state_note": "채울 근거가 없는 것이 정상",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W5",
          "value": "",
          "cell_state": "EMPTY_VALID",
          "cell_state_note": "채울 근거가 없는 것이 정상",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        }
      ]
    },
    {
      "section_key": "safety_education",
      "label": "안전교육",
      "source_label": null,
      "cells": [
        {
          "week_id": "2026-09-W1",
          "value": "",
          "cell_state": "EMPTY_UNRESOLVED",
          "cell_state_note": "채워야 하는데 배치 source가 없음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W2",
          "value": "",
          "cell_state": "EMPTY_UNRESOLVED",
          "cell_state_note": "채워야 하는데 배치 source가 없음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W3",
          "value": "",
          "cell_state": "EMPTY_UNRESOLVED",
          "cell_state_note": "채워야 하는데 배치 source가 없음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W4",
          "value": "",
          "cell_state": "EMPTY_UNRESOLVED",
          "cell_state_note": "채워야 하는데 배치 source가 없음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-09-W5",
          "value": "",
          "cell_state": "EMPTY_UNRESOLVED",
          "cell_state_note": "채워야 하는데 배치 source가 없음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.template.section_resolution",
            "rule_version": "v1"
          },
          "evidence": [],
          "activity_id": null,
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        }
      ]
    }
  ],
  "constraints": [
    {
      "kind": "STATUTORY_SAFETY_EDUCATION",
      "verification": "NOT_VERIFIED_SOURCE_REQUIRED",
      "rule_version": "child-welfare-act-decree-annex6-2022-06-21",
      "detail": "기관 안전교육 연간계획 또는 교사 직접 입력이 없어 안전교육 배치를 검증하지 못했다. 임의 배치를 생성하지 않았다. 이 상태는 법정 요건 충족 여부에 대한 판정이 아니라 미검증 표시다."
    }
  ],
  "run": {
    "run_id": "devm_run_002",
    "llm_call_count": 0,
    "week_period_count": 5,
    "filled_cell_count": 1,
    "empty_valid_cell_count": 5,
    "empty_unresolved_cell_count": 5,
    "activity_filled_cell_count": 0,
    "activity_unfilled_cell_count": 0,
    "traces": []
  }
};
