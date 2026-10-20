# Activity Reference v0.2.0-draft — Human Review 자료 (HD-A~HD-H 적용본)

> **Human Approval 직전 검증 자료다. 승인 기록이 아니다.**
>
> ```text
> catalog_version       : activity-reference-v0.2.0-draft
> supersedes            : activity-reference-v0.1.0
> domain_owner_approval : PENDING_HUMAN_REVIEW
> approved_by           : null
> approved_at           : null
> runtime active        : false
> ```
>
> **Claude는 HUMAN_APPROVED / production ready / runtime active를 판단하지 않았다.**

- 대상: `data/activities/activity_reference_v0_2_draft.json`
- 기준: `data/activities/activity_reference_v0.json` (**변경 없음**, SHA `b565254f…`)
- 적용 결정: HD-A · HD-B · HD-C · HD-D · HD-E · HD-F · **HD-G** · **HD-H** (2026-09-11)

---

## 0. Human Decision 적용 결과 요약

| ID | 결정 | 적용 결과 |
|---|---|---|
| **HD-A** | 명시 혼합연령을 age evidence로 인정하되 강도 구별 | v0.1.0 semantics 유지. `age_support_basis`에 `SINGLE_AGE_EVIDENCE` / `MIXED_AGE_EVIDENCE_ONLY` / `SINGLE_AND_MIXED` 기록. §4 통계 분리 |
| **HD-B** | 서진 만4.5세반은 age 근거 아님 | `age_scope: []` 유지. **supported_ages 확장 0건** |
| **HD-C** | AMBIGUOUS 8건 승인 후보 제외 | canonical item 0건. `pending_human_review.ambiguous_items` 보관 |
| **HD-D** | SECTION_LABEL_ECHO 제외 | `실외놀이` 1건 제거 → `section_label_echo_excluded` (원문 Observation 보존) |
| **HD-E** | SAFETY_ADJACENT 5건 보류 | (HD-G로 최종 확정됨 — 아래 참조) |
| **HD-F** | 1기관 관찰은 제외 조건 아님 | 178개 유지. 모든 item에 `observed_institution_count`·`evidence_count`·`origins_used` 부여 |
| **HD-G** | Safety-adjacent 최종 경계 — 구체적 outdoor action/play/object 유무로 판정 | **편입 3 / 제외 2**. 편입분은 원문 표현 그대로, merge 0 |
| **HD-H** | AMBIGUOUS 8건은 v0.2 승인 blocker 아님 | `KEEP_AMBIGUOUS` 유지, pending 보존. 이번 승인 대상 제외 |

---

## 1. 숫자 정합성 Preflight — 41 vs 36 추적 (§1)

### 결론: **정상적인 dedup 결과이며 누락 버그가 아닙니다.**

```
Final Cleanup EXACT 고유 activity_id   : 41
Final Cleanup ALIAS 고유 activity_id   : 10
EXACT ∪ ALIAS                          : 42
Draft CARRIED_OVER_WITH_NEW_EVIDENCE   : 36
차이                                    :  6
```

**`[실측]` 차이는 5가 아니라 6입니다.** 이전 보고의 "41 − 36 = 5"는 ALIAS 매칭을 빼고 센 것이었습니다. 정확한 대응은 `EXACT ∪ ALIAS(42) − 36 = 6`입니다.

### 6건 전수 추적

| activity_id | label | 새 관찰 | 기존 evidence key와 동일? |
|---|---|---|---|
| `act_outdoor_autumn_sky_walk` | 가을 하늘 보며 산책하기 | 시립새봄 m9 p1 | **YES 중복** |
| `act_outdoor_find_autumn_fruits` | 가을 열매 찾기 | 시립새봄 m9 p1 | **YES 중복** |
| `act_outdoor_juldarigi` | 줄다리기 | 시립새봄 m9 p2 | **YES 중복** |
| `act_outdoor_gomujul_nori` | 고무줄 놀이 | 돌고래 m9 p1 | **YES 중복** |
| `act_outdoor_natural_hanbok_colors` | 자연 한복색 찾기 | 돌고래 m9 p1 | **YES 중복** |
| `act_outdoor_nature_mask_making` | 자연물로 탈 꾸미기 | 돌고래 m9 p1 | **YES 중복** |

### 원인

6건 모두 **v0.1.0 origins에 이미 있는 파일**(시립새봄·돌고래)에서 나왔고, `(origin_id, page, 정규화 label)` 키가 v0.1.0 evidence와 **완전히 동일**합니다.

```
예: ('sample.monthly.seobom.2026.09', 1, '가을하늘보며산책하기')
    → v0.1.0 evidence에 이미 존재 → dedup이 건너뜀
```

Final Cleanup 파이프라인이 v0.1.0 corpus를 **다시 스캔**하므로 기존 근거가 재관찰됩니다. Draft는 동일 근거를 중복 적재하지 않으므로 `CARRIED_OVER_WITH_NEW_EVIDENCE`가 되지 않았습니다.

- **age unresolved 때문 아님** (6건 모두 명시 연령 있음)
- **exclusion 때문 아님**
- **parser / draft generation 누락 아님**

Draft에 `reobserved_but_evidence_already_present: 6`으로 기록했고, 테스트가 이 숫자를 고정합니다.

---

## 2. 용어 분리 (§2)

이전 보고의 `"reproduced existing items = 49/49 유지"`는 혼동을 주는 표현이었습니다. 두 개념을 분리합니다.

| 지표 | 값 | 의미 |
|---|---:|---|
| **`CARRIED_OVER_EXISTING_ITEMS`** | **49 / 49** | v0.1.0의 49개가 Draft에 **보존**됨 (삭제·재작성 0) |
| **`REPRODUCED_WITH_NEW_CORPUS_EVIDENCE`** | **36 / 49** | 새 corpus에서 **새 근거가 추가**된 item |
| `REOBSERVED_BUT_EVIDENCE_ALREADY_PRESENT` | 6 / 49 | 재관찰됐으나 동일 근거라 중복 제외 |
| `CARRIED_OVER_UNCHANGED` | 13 / 49 | 새 관찰 없음 (위 6건 포함) |

```
49 (보존) = 36 (새 근거 추가) + 13 (변경 없음)
                                 └ 그중 6건은 재관찰되었으나 동일 근거
```

---

## 3. v0.1.0 → v0.2 Draft delta (§4)

| # | 지표 | v0.1.0 | **v0.2 Draft** |
|---:|---|---:|---:|
| 1 | **total item count** | 49 | **198** |
| 2 | **existing carried-over count** | — | **49** |
| 3 | **existing reproduced-with-new-evidence count** | — | **36** |
| 4 | **new canonical count** | — | **149** |
| 5 | **evidence count** | 74 | **288** |
| 6 | **month coverage** | `[3, 9]` | **`[1…12]`** |
| 7 | **institution coverage** | 11 | **14** (evidence 기준) / 16 (origins 전체) |
| 8 | **supported ages** | `[3,4,5]` | `[3,4,5]` |
| 9 | **single-age support / age** | — | 만3 **102** · 만4 **4** · 만5 **20** |
| 10 | **mixed-only support / age** | — | 만3 **77** · 만4 **96** · 만5 **80** |
| 11 | **aliases approved** | 20 | **20** (+0) |
| 12 | **aliases pending** | — | **12** (10 item) |
| 13 | **ambiguous** | — | **8** (pending) |
| 14 | **safety-adjacent** | — | **편입 3 / 제외 2** (HD-G) |
| 15 | **section-label excluded** | — | **1** (HD-D) |
| 16 | **age unresolved evidence** | — | **14** |
| 17 | **single-institution item count** | — | **178** (90%) |
| 18 | **2+ institution item count** | — | **20** (10%) |

보조 지표: origins 14 → **61**, theme_links 57 → **164**, curriculum_links **0 유지**, HD-D/HD-G로 제외된 신규 후보 **3**.

---

## 4. 연령 지원 — "지원됨"과 "근거 강도" 분리 (§3, HD-A)

| 연령 | 지원 item | 단일연령 근거 있음 | **혼합 근거만** |
|---:|---:|---:|---:|
| 만3 | 179 | **102** (57%) | 77 (43%) |
| **만4** | **100** | **4** (4%) | **96 (96%)** |
| 만5 | 100 | 20 (20%) | 80 (80%) |

### ⚠ 만4세 경고 (유지)

**`[실측]` 만4세를 지원하는 100개 item 중 단일 만4세 근거를 가진 것은 4개(4%)뿐입니다.**

단일 만4세 근거 보유 item:

| activity_id | label |
|---|---|
| `act_outdoor_autumn_outing` | 가을 나들이 |
| `act_outdoor_ddakji_chigi` | 딱지 치기 |
| `act_outdoor_gomusin_throwing` | 고무신 멀리 던지기 |
| `act_outdoor_v2_08c8ca6c8f` | (신규 후보) |

나머지 96개는 `MIXED_AGE_EVIDENCE_ONLY`이며 evidence 출처가 **우리어린이집(만3~5세 혼합) 중심**입니다.

**HD-A에 따라 이 96개의 만4세 지원은 유효합니다.** 다만 `MIXED_AGE_EVIDENCE_ONLY`를 단일연령 근거와 동일하게 표현하지 않았고, item마다 `age_support_review_required: ["4", ...]`로 표시했습니다.

### ⚠ 혼합연령 기관 다양성 경고 (유지)

```
혼합연령 명시 evidence : 우리 · 큰빛  = 2기관
  └ 우리어린이집이 대부분
```

혼합반 운영 관행의 기관 간 편차를 검증할 표본이 부족합니다.

---

## 5. HD-D — SECTION_LABEL_ECHO 제외 1건

canonical Activity Candidate에서 제외했고 **원문 Observation은 보존**했습니다.

| label | origin | page | 월 | age_scope | section |
|---|---|---:|---:|---|---|
| `실외놀이` | `sample.monthly.aideulsesang.2026.09` | 1 | 9 | `[5]` | outdoor_play |
| `실외놀이` | `sample.monthly.aideulsesang.2026.09` | 2 | 9 | `[]` | outdoor_play |

```
draft_exclusion : SECTION_LABEL_ECHO_EXCLUDE
위치            : pending_human_review.section_label_echo_excluded
```

`[판단]` 아이들세상어린이집의 바깥놀이 depth-2 하위 행 라벨(`나들이` / `실외놀이` / `텃밭`)이 활동명으로 추출된 것입니다. 새 Production enum을 만들지 않고 Draft review metadata 범위에서 처리했습니다.

---

## 6. HD-G — Safety-adjacent 5건 최종 판정

**판정 기준(HD-G)**: 구체적인 outdoor action / play / object가 있으면 Candidate로 인정하고,
구체적 활동 없이 일반적인 안전 행동·태도만 나타내면 제외한다.
법정 SafetyEducation과 Activity Reference의 분리는 계속 유지한다.

| # | observed label | institution | month | age scope | outdoor section | **HD-G 판정** | 근거 |
|---:|---|---|---:|---|---|---|---|
| 1 | `바깥놀이를 안전하게 해요` | 한솔빛 | 3 | `[5]` | ✅ | **EXCLUDE** | 구체적 활동 없는 일반 안전 지침 |
| 2 | `안전 관련 표지판 찾아보며 산책하기` | 우리 | 8 | `[3,4,5]` | ✅ | **INCLUDE_AS_ACTIVITY** | 구체적 행동/도구 존재 |
| 3 | `안전 약속 지키며 놀이기구 타기` | 우리 | 3 | `[3,4,5]` | ✅ | **INCLUDE_AS_ACTIVITY** | 구체적 행동/도구 존재 |
| 4 | `안전하게 놀이해요` | 예일 | 1 | `[3]` | ✅ | **EXCLUDE** | 구체적 활동 없는 일반 안전 지침 |
| 5 | `훌라후프로 안전하게 놀아요` | 서진 | 1 | `[3]` | ✅ | **INCLUDE_AS_ACTIVITY** | 구체적 행동/도구 존재 |

### 편입 3건 — 원문 표현 그대로

| activity_id | label | 기관 | 월 | 연령 |
|---|---|---|---|---|
| `act_outdoor_v2_1cffee74db` | 안전 관련 표지판 찾아보며 산책하기 | ['uri'] | [8] | [3, 4, 5] |
| `act_outdoor_v2_44a1b42fff` | 안전 약속 지키며 놀이기구 타기 | ['uri'] | [3] | [3, 4, 5] |
| `act_outdoor_v2_b52ef53a20` | 훌라후프로 안전하게 놀아요 | ['seojin'] | [1] | [3] |

**`[실측]` 편입 3건 검증:**

- `label`에서 "안전"을 제거하거나 표현을 일반화하지 **않았습니다**
- `label_derivation_type: DIRECT_TRANSCRIPTION`
- `aliases: []` — 기존 canonical과 semantic/fuzzy merge **0건**
- 별도 Candidate로 유지 (예: `안전 약속 지키며 놀이기구 타기`는 v0.1.0의
  `바깥 놀이터에서 지켜야 할 약속을 정해요`와 병합하지 않음)

### 제외 2건 — 원문 Observation 보존

| label | institution | month | 사유 |
|---|---|---:|---|
| `바깥놀이를 안전하게 해요` | 한솔빛 | 3 | 구체적 놀이 행동·대상 없음. **v0.1.0의 기존 판정과 일관** |
| `안전하게 놀이해요` | 예일 | 1 | 구체적 놀이 행동·도구·대상 없음 |

```
draft_exclusion : SAFETY_ADJACENT_EXCLUDE_HD_G
위치            : pending_human_review.safety_adjacent_excluded_hd_g
```

원문 Observation(evidence)은 삭제하지 않고 보존했습니다.

---

## 7. HD-F — 1기관 관찰 item 유지

```
전체 198  →  1기관 178 (90%)  /  2기관 이상 20 (10%)
```

**1기관 관찰을 제외 조건으로 쓰지 않았습니다(HD-F).** 모든 item이 아래 허용 조건을 만족합니다.

- 명확한 outdoor activity · 완전한 label · institution-specific 아님 · indoor alternative 아님 · community linkage 아님 · ambiguous 아님 · age evidence contract 충족

모든 item에 provenance를 부여했습니다.

```json
"observed_institution_count": 1,
"observed_institutions": ["예일"],
"evidence_count": 1,
"origins_used": ["sample.monthly.yeil.2025.11"]
```

### 2기관 이상 재현 20건 (stronger evidence — runtime hard gate 아님)

| 기관 | activity_id | label | 월 | 연령 | 구분 |
|---:|---|---|---|---|---|
| **6** | `act_outdoor_mugunghwa_flower_game` | 무궁화 꽃이 피었습니다 | [9] | [3,4,5] | 기존 |
| **6** | `act_outdoor_traditional_play` | 전통놀이 | [9,10] | [3,4,5] | 기존 |
| 4 | `act_outdoor_ganggangsullae` | 강강술래 | [9] | [3,5] | 기존 |
| 3 | `act_outdoor_autumn_outing` | 가을 나들이 | [9] | [3,4,5] | 기존 |
| 3 | `act_outdoor_sabangchigi` | 사방치기 | [2,9] | [3,4,5] | 기존 |
| 3 | `act_outdoor_sand_play` | 모래놀이 | [1,3,8,9] | [3,4,5] | 기존 |
| 3 | `act_outdoor_tuho` | 투호놀이 | [9,10] | [3,4,5] | 기존 |
| 2 | `act_outdoor_daemun_nori` | 대문놀이 | [9,10] | [3,4,5] | 기존 |
| 2 | `act_outdoor_dongdaemun_nori` | 동대문 놀이 | [9] | [3,4,5] | 기존 |
| 2 | `act_outdoor_find_autumn_leaves` | 가을 단풍 찾아보기 | [9,10] | [3,4,5] | 기존 |
| 2 | `act_outdoor_hanbok_outing` | 한복 입고 나들이 가요 | [9] | [3,4] | 기존 |
| 2 | `act_outdoor_korea_symbol_treasure_hunt` | 우리나라 상징 보물찾기 | [3,9] | [3,4] | 기존 |
| 2 | `act_outdoor_pinwheel_running` | 바람개비 들고 시원하게 달리기 | [5,9] | [3,4,5] | 기존 |
| 2 | `act_outdoor_sand_desert` | 모래사막을 구성해요 | [9] | [5] | 기존 |
| 2 | `act_outdoor_sand_old_painting` | 모래 위에 옛 그림을 그려요 | [9] | [3,4] | 기존 |
| 2 | `act_outdoor_traditional_play_fair` | 전통 놀이 한마당 | [9] | [3,4] | 기존 |
| **2** | `act_outdoor_v2_30126d803b` | 산책하며 내가 좋아하는 색깔 자연물 찾기 | [5] | [3,4,5] | **신규** |
| **2** | `act_outdoor_v2_468020296d` | 돌멩이에 얼굴 표정 그리기 | [5] | [3,4,5] | **신규** |
| **2** | `act_outdoor_v2_9d7e335dfc` | 우리가 좋아했던 장소 산책하기 | [2] | [3,4,5] | **신규** |
| **2** | `act_outdoor_v2_cc6b7c4d1b` | 스카프가 바람을 만났어요 | [11] | [3] | **신규** |

---

## 8. 월 coverage

| 월 | item 수 | 해당 월 evidence 기관 |
|---:|---:|---:|
| 3 | 18 | 4 |
| 4 | 16 | 3 |
| 5 | 12 | 3 |
| 6 | 13 | 3 |
| 7 | 16 | 3 |
| 8 | 11 | 3 |
| **9** | **52** | **12** |
| 10 | 15 | 3 |
| 11 | 11 | 3 |
| 12 | 17 | 3 |
| 1 | 13 | 3 |
| 2 | 11 | 3 |

각 Activity의 `applicable_months`는 **그 Activity가 실제 관찰된 월만** 담습니다.

---

## 9. 기관 coverage

| 기관 | evidence | | 기관 | evidence |
|---|---:|---|---|---:|
| 우리 | 72 | | 괴산하나 | 11 |
| 예일 | 50 | | 예담 | 10 |
| 서진 | 38 | | 엄지 | 7 |
| 시립새봄 | 24 | | 해찬솔 | 6 |
| 한솔빛 | 18 | | 돌고래 | 5 |
| 공립아이사랑 | 17 | | 금산군청 | 2 |
| 아이들세상 | 14 | | 큰빛 | 11 |

두루미는 HD-2에 따라 Activity evidence에서 제외(`EXCLUDE_NO_OUTDOOR_SECTION`)되어 0건입니다.

---

## 10. 보류 목록 (pending_human_review)

| 항목 | 건수 | 규칙 |
|---|---:|---|
| `ambiguous_items` | 8 | HD-C·HD-H. `KEEP_AMBIGUOUS`. **v0.2 승인 blocker 아님** |
| `hd1_unresolved_age_items` | 36 | HD-B. 존재 근거로만 사용 |
| `new_candidates_skipped_no_age_evidence` | 20 | 명시 연령 근거 없어 후보 미생성 |
| `section_label_echo_excluded` | 1 | HD-D |
| `safety_adjacent_excluded_hd_g` | 2 | HD-G 제외 |
| `safety_adjacent_included_hd_g` | 3 | HD-G 편입 (canonical에 포함됨) |

---

## 11. 병합·태깅 금지 준수

```
fuzzy merge / embedding / semantic / LLM merge   0
이름 일반화 재작성 / 기관 고유 활동 일반화           0
aliases 임의 추가                                0  (v0.1.0의 20건 그대로)
curriculum_links 임의 부여                       0  (198개 전부 빈 배열)
theme_links label 유사도·LLM mapping             0
기계적 동일 문자열 병합                            1
```

alias 후보 12건은 `alias_candidates_pending_review`로 10개 item에 분리 보관했고, 해당 evidence에 `matched_via: RELATED_EXPRESSION` + `match_note`를 남겼습니다.

---

## 12. Contract 검증

실제 `parse_activity_reference_payload()`로 Draft의 core projection(draft 전용 필드 제거)을 파싱해 통과했습니다.

```
items 198 · month_coverage (1…12) · PENDING_HUMAN_REVIEW · is_active False
12개월 × 4개 연령 조합 전수 → eligible_candidates() 모두 ()
```

Domain 불변식 통과: `supported_ages ⊆ 관찰 age_scope` · `applicable_months ⊆ 관찰 월` · `placement_slots = [outdoor_play]` · `setting = OUTDOOR` · `source_version = catalog_version` · `month_coverage`가 실제 후보 월과 일치 · origin_id 전수 선언 · activity_id/label 중복 0 · origins SHA-256 전수 일치.

---

## 13. 승인 전 남은 Human Decision — **없음**

HD-A ~ HD-H 적용으로 이전에 남아 있던 2건이 모두 해소됐습니다.

| 이전 미결 | 해소 |
|---|---|
| HD-E 5건의 최종 분류 | **HD-G로 확정** — 편입 3 / 제외 2 |
| AMBIGUOUS 8건 최종 분류 | **HD-H로 확정** — v0.2 승인 blocker 아님. `KEEP_AMBIGUOUS` 유지하고 향후 corpus에서 재검토 |

### 승인 시 함께 확인할 경고 (해소되지 않음 — 기록 유지)

이 셋은 데이터의 성질이며 승인을 막는 결함이 아닙니다. 다만 승인 판단에 반드시 반영해야 합니다.

| # | 경고 | 수치 |
|---:|---|---|
| 1 | **Age evidence** — 만4세 근거 강도 | 지원 100 / 단일근거 **4 (4%)** / 혼합근거만 **96 (96%)** |
| 2 | **Institution diversity** — 1기관 전용 Activity 다수 | **178 / 198 (90%)**. hard exclusion 사유는 아니나 evidence strength가 낮음 |
| 3 | **Reproducibility** — 신규 중 2기관 exact 재현 적음 | 신규 149 중 **4건(2.7%)**. 자동 제외 조건 아니며 추가 corpus로 계속 확장 |

명시적 mixed-age evidence는 HD-A에 따라 **유효**하지만 single-age evidence와 **동일한 강도로 표현하지 않았습니다**(`age_support_basis` / `age_support_review_required`).

---

## 14. 승인 절차

1. §13의 2건 Human Decision 수령
2. `activity-reference-v0.2.0`(draft 접미사 제거) 발행
3. `review.domain_owner_approval` → `HUMAN_APPROVED`, `approved_by` → `reviewer_<role>_<sequence>`(OD-N10), `approved_at` → 실제 처리 시각
4. `runtime_active`는 승인 상태에서 자동 파생 (독립 필드 없음, 우회 경로 없음)
5. 그 뒤에야 M2-C가 실질 의미를 가짐

**현재 Draft 상태로는 M2-C를 진행해도 runtime 후보가 항상 0입니다.**
