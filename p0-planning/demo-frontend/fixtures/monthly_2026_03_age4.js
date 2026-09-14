// 자동 생성 파일 — 직접 수정하지 마세요.
// 생성: python demo-frontend/tools/export_fixtures.py
// 이것은 Demo 표시용 FIXTURE 스냅샷이며 Backend Contract가 아닙니다.
window.SSUKSAK_DEMO_FIXTURES = window.SSUKSAK_DEMO_FIXTURES || {};
window.SSUKSAK_DEMO_FIXTURES['2026-03-draft'] = {
  "fixture": true,
  "fixture_title": "2026-03 · 만 4세 · DRAFT (4주)",
  "fixture_note": "주차 수가 4인 달. 표가 4열로 렌더링되는지 확인용",
  "generated_by": "demo-frontend/tools/export_fixtures.py",
  "header": {
    "school_year": 2026,
    "target_month": "2026-03",
    "calendar_year": 2026,
    "calendar_month": 3,
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
    "value": "우리 원과 친구",
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
        "display_name": "우리 원과 친구"
      },
      {
        "source_type": "THEME_REFERENCE",
        "source_id": "yr_theme_new_environment_friends",
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
    "parent_yearly_theme_id": "yr_theme_new_environment_friends",
    "parent_yearly_value": "우리 원과 친구",
    "reference_version": "theme-reference-v0.1.2"
  },
  "activity_catalog": {
    "catalog_id": "ssuksak.outdoor-activity-reference",
    "catalog_version": "activity-reference-v0.2.0"
  },
  "weeks": [
    {
      "week_id": "2026-03-W1",
      "ordinal": 1,
      "label": "3월 1주",
      "start": "2026-03-02",
      "end": "2026-03-06",
      "active": true
    },
    {
      "week_id": "2026-03-W2",
      "ordinal": 2,
      "label": "3월 2주",
      "start": "2026-03-09",
      "end": "2026-03-13",
      "active": true
    },
    {
      "week_id": "2026-03-W3",
      "ordinal": 3,
      "label": "3월 3주",
      "start": "2026-03-16",
      "end": "2026-03-20",
      "active": true
    },
    {
      "week_id": "2026-03-W4",
      "ordinal": 4,
      "label": "3월 4주",
      "start": "2026-03-23",
      "end": "2026-03-27",
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
          "week_id": "2026-03-W1",
          "value": "모래놀이",
          "cell_state": "FILLED",
          "cell_state_note": "값 있음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.activity.reference_candidate_selection",
            "rule_version": "v1"
          },
          "evidence": [
            {
              "source_type": "ACTIVITY_REFERENCE",
              "source_id": "act_outdoor_sand_play",
              "source_version": "activity-reference-v0.2.0",
              "display_name": "모래놀이"
            }
          ],
          "activity_id": "act_outdoor_sand_play",
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-03-W2",
          "value": "우리 반 꽃이 피었습니다",
          "cell_state": "FILLED",
          "cell_state_note": "값 있음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.activity.reference_candidate_selection",
            "rule_version": "v1"
          },
          "evidence": [
            {
              "source_type": "ACTIVITY_REFERENCE",
              "source_id": "act_outdoor_v2_068adb33b2",
              "source_version": "activity-reference-v0.2.0",
              "display_name": "우리 반 꽃이 피었습니다"
            }
          ],
          "activity_id": "act_outdoor_v2_068adb33b2",
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-03-W3",
          "value": "안전 약속 지키며 놀이기구 타기",
          "cell_state": "FILLED",
          "cell_state_note": "값 있음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.activity.reference_candidate_selection",
            "rule_version": "v1"
          },
          "evidence": [
            {
              "source_type": "ACTIVITY_REFERENCE",
              "source_id": "act_outdoor_v2_44a1b42fff",
              "source_version": "activity-reference-v0.2.0",
              "display_name": "안전 약속 지키며 놀이기구 타기"
            }
          ],
          "activity_id": "act_outdoor_v2_44a1b42fff",
          "audit": [
            {
              "event_type": "CREATED",
              "occurred_at": "2026-09-12T02:06:19+09:00",
              "actor": "SYSTEM"
            }
          ]
        },
        {
          "week_id": "2026-03-W4",
          "value": "모래 위에 쓰인 우리 반 이름 찾기",
          "cell_state": "FILLED",
          "cell_state_note": "값 있음",
          "generation": {
            "method": "RULE_ONLY",
            "rule_id": "monthly.activity.reference_candidate_selection",
            "rule_version": "v1"
          },
          "evidence": [
            {
              "source_type": "ACTIVITY_REFERENCE",
              "source_id": "act_outdoor_v2_53c399e07b",
              "source_version": "activity-reference-v0.2.0",
              "display_name": "모래 위에 쓰인 우리 반 이름 찾기"
            }
          ],
          "activity_id": "act_outdoor_v2_53c399e07b",
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
          "week_id": "2026-03-W1",
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
          "week_id": "2026-03-W2",
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
          "week_id": "2026-03-W3",
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
          "week_id": "2026-03-W4",
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
    "week_period_count": 4,
    "filled_cell_count": 5,
    "empty_valid_cell_count": 0,
    "empty_unresolved_cell_count": 4,
    "activity_filled_cell_count": 4,
    "activity_unfilled_cell_count": 0,
    "traces": [
      {
        "week_id": "2026-03-W1",
        "reason": "MATCHED_PARENT_THEME",
        "selected_activity_id": "act_outdoor_sand_play",
        "selected_label": "모래놀이",
        "candidate_count": 8,
        "evidence_strength": 2,
        "theme_matched": true,
        "parent_theme_id": "yr_theme_new_environment_friends",
        "rule_id": "monthly.activity.reference_candidate_selection",
        "rule_version": "v1"
      },
      {
        "week_id": "2026-03-W2",
        "reason": "AVOIDED_REPEAT_IN_MONTH",
        "selected_activity_id": "act_outdoor_v2_068adb33b2",
        "selected_label": "우리 반 꽃이 피었습니다",
        "candidate_count": 8,
        "evidence_strength": 1,
        "theme_matched": true,
        "parent_theme_id": "yr_theme_new_environment_friends",
        "rule_id": "monthly.activity.reference_candidate_selection",
        "rule_version": "v1"
      },
      {
        "week_id": "2026-03-W3",
        "reason": "AVOIDED_REPEAT_IN_MONTH",
        "selected_activity_id": "act_outdoor_v2_44a1b42fff",
        "selected_label": "안전 약속 지키며 놀이기구 타기",
        "candidate_count": 8,
        "evidence_strength": 1,
        "theme_matched": true,
        "parent_theme_id": "yr_theme_new_environment_friends",
        "rule_id": "monthly.activity.reference_candidate_selection",
        "rule_version": "v1"
      },
      {
        "week_id": "2026-03-W4",
        "reason": "AVOIDED_REPEAT_IN_MONTH",
        "selected_activity_id": "act_outdoor_v2_53c399e07b",
        "selected_label": "모래 위에 쓰인 우리 반 이름 찾기",
        "candidate_count": 8,
        "evidence_strength": 1,
        "theme_matched": true,
        "parent_theme_id": "yr_theme_new_environment_friends",
        "rule_id": "monthly.activity.reference_candidate_selection",
        "rule_version": "v1"
      }
    ]
  }
};
