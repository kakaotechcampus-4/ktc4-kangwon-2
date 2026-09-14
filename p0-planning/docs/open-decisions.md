# 쓱싹요정 P0 — Open Decision 재분류

> 기준일: 2026-09-10  
> 대상 위치: docs/open-decisions.md  
> 상태: Yearly P0 Blocking 결정 완료 · 구현 미착수  

## 적용 우선순위

구현 판단은 다음 순서로 따른다.

1. `CLAUDE.md`
2. `docs/demo-source-of-truth.md`
3. `docs/screen-spec.md`
4. `docs/contracts.md`
5. `docs/open-decisions.md`
6. `docs/template-a-validation.md`
7. `references/README.md`
8. `references/official/`
9. `references/samples/`

같은 우선순위 안에서는 최신 승인일과 명시적인 결정 상태를 우선한다. 충돌이 발견되면 구현자가 임의로 해석하지 않고 충돌 위치, 가능한 해석, 영향 범위, 권장안을 보고한다.

이 문서는 기존 Source of Truth와 화면 명세의 Open Decision을 중복 제거하고, 월간 Template A 실측 재검증 결과를 반영해 구현 순서별로 다시 분류한다.

핵심 원칙은 하나다.

> 첫 GenerateYearlyPlan Slice의 의미 있는 구현 착수 자체를 막는 결정만 BLOCKING으로 둔다.

DB의 물리 테이블, LLM 공급자, UI 저장 방식처럼 Port·설정·가역적 기본값으로 격리할 수 있는 항목은 첫 Slice 완료 전에 필요하더라도 NON-BLOCKING으로 분류한다. 각 항목의 실제 마감 시점은 “결정 시점”에 별도로 적는다.

---

## 1. 분류와 상태

### 분류

| 분류 | 의미 |
|---|---|
| BLOCKING | 결정 없이 GenerateYearlyPlan → DRAFT → Edit → Confirm의 핵심 Contract를 안전하게 정의할 수 없음 |
| BLOCKING-BEFORE-MONTHLY | Yearly Slice에는 영향이 없지만 GenerateMonthlyPlan 착수 전 확정 필요 |
| BLOCKING-BEFORE-WEEKLY | Yearly·Monthly Slice에는 영향이 없지만 GenerateWeeklyPlan 착수 전 확정 필요 |
| NON-BLOCKING | 확장 가능한 Port, 설정 또는 가역적 기본값으로 시작할 수 있음 |

### 상태

| 상태 | 의미 |
|---|---|
| OPEN | PM/팀 결정이 필요함 |
| PARTIALLY_RESOLVED | 방향은 확정됐지만 남은 Contract가 있음 |
| PROVISIONAL | 현재 권장안으로 진행 가능하지만 최종 승인이 남음 |
| DEFERRED | 현재 P0 기본 동작은 정해졌고 장기 정책만 후속 결정 |
| RESOLVED_FOR_P0 | P0 범위에서 필요한 결정은 끝남 |

---

## 2. 현재 착수 판정

| 분류 | 등록 개수 | 현재 상태 | ID |
|---|---:|---|---|
| BLOCKING | 3 | `RESOLVED_FOR_P0` 3건 | OD-Y01, OD-Y02, OD-Y03 |
| BLOCKING-BEFORE-MONTHLY | 4 | `RESOLVED_FOR_P0` 4건 | OD-M01, OD-M02, OD-M03, OD-M04 |
| BLOCKING-BEFORE-WEEKLY | 2 | `OPEN` 2건 | OD-W01, OD-W02 |
| NON-BLOCKING | 18 | `PROVISIONAL` 1건 · `PARTIALLY_RESOLVED` 2건 · `DEFERRED` 1건 · `RESOLVED_FOR_P0` 1건 · `CLOSED` 5건 · `OPEN` 8건 | OD-N01 ~ OD-N18 |

OD-Y01~OD-Y03은 2026-09-09에 P0 결정으로 승인되었다. 따라서 GenerateYearlyPlan → DRAFT → Edit → Confirm의 제품·Application Contract를 막는 미결정 항목은 없다. 다만 이번 단계는 문서 결정 완료이며 구현 착수를 뜻하지 않는다. 장기 DB Migration과 공개 HTTP API는 OD-N08의 범위로 남겨 둔다.

OD-M01~OD-M04는 2026-09-11에 P0 결정으로 승인되었다. 따라서 **문서 결정 수준에서 GenerateMonthlyPlan을 막는 미결정 항목은 없다.** 다만 Monthly 착수에는 결정 외에 **M0 데이터 산출물**이 추가로 필요하다.

| M0 산출물 | 상태 | 승인 | runtime_active |
|---|---|---|---|
| `data/templates/monthly_template_a.json` | `monthly-template-a-v0.1.0` | **`HUMAN_APPROVED`** 2026-09-11T10:25:01+09:00 | `true` |
| `data/rules/safety_education_legal_v1.json` | `child-welfare-act-decree-annex6-2022-06-21` | **`HUMAN_APPROVED`** 2026-09-11T10:25:01+09:00 | `true` |
| `data/activities/activity_reference_v0_2_1.json` | `activity-reference-v0.2.1` | **`HUMAN_APPROVED`** 2026-09-13T11:32:20+09:00 | `true` — **현재 Production / Demo default** |
| `data/activities/activity_reference_v0_2.json` | `activity-reference-v0.2.0` | **`HUMAN_APPROVED`** 2026-09-12T00:02:24+09:00 | `true` — default에서 내려왔으나 기존 Plan pin 해소용으로 계속 로드된다 |
| `data/activities/activity_reference_v0.json` | `activity-reference-v0.1.0` | `PENDING_HUMAN_REVIEW` (역사적 artifact) | `false` |

reviewer는 네 승인 파일 모두 `reviewer_ai_lead_001`이다. Template A와 Safety Rule의 검토 기록은 `docs/m0-human-review.md`, Activity Reference v0.2.0의 검토 기록은 `docs/activity-reference-v0-2-draft-human-review.md`, v0.2.1의 검토 기록은 `docs/analysis/monthly-quality-patch-1-review.md` · `docs/analysis/activity-v0-2-1-setting-audit.md` · `docs/analysis/activity-v0-2-1-activation-report.md`에 있다.

#### Activity Catalog version pin 의미

Plan은 생성 시점의 `catalog_id@catalog_version`을 `MonthlyPlan.activity_catalog`에 기록한다. Default가 v0.2.1로 바뀌어도 **v0.2.0으로 생성된 Plan의 Regenerate는 v0.2.0을 정확히 다시 로드한다.** 해소 실패는 실패이며 default로 대체하지 않는다. 기존 Plan Migration은 수행하지 않는다.

#### Rule v2 × Activity Catalog 호환

Selection Rule은 `monthly.activity.reference_candidate_selection` **v2** 하나이고 Catalog version에 따라 분기하지 않는다. 순위 축 중 display quality penalty만 Catalog가 그 metadata를 담고 있을 때 값을 갖는다.

| 조합 | display_quality metadata | 결과 |
|---|---|---|
| Rule v2 + Activity Catalog **v0.2.0** | 없음 (`display_quality`/`display_quality_review_status` 전부 `None`) | penalty가 항상 0이므로 **v1-equivalent ordering** |
| Rule v2 + Activity Catalog **v0.2.1** | 있음 | `HUMAN_CONFIRMED` 항목에만 **display-quality soft penalty 활성**. `AUTO_CANDIDATE` / `UNREVIEWED`는 runtime 중립 |

penalty는 soft다. Hard Exclusion이 아니므로 후보 pool의 크기를 바꾸지 않는다.

`runtime_active`는 독립 스위치가 아니라 파생값이며 `runtime_active == (domain_owner_approval == "HUMAN_APPROVED")`를 항상 만족한다. 수동 activation 우회 경로를 만들지 않는다.

**M0가 완료되어 Monthly M1 설계에 착수할 수 있다.** Activity Reference는 2026-09-12 M2에서 v0.2.0으로 승인·연결되었다(아래 OD-N03 M2-C/M2-D 갱신 참조). M1은 Activity Reference 없이도 동작하며 그 경로는 그대로 유지된다. Template A Optional 5개의 `display_mode`가 `PENDING_HUMAN_DECISION`으로 남아 있으나 전부 default inactive이므로 M1 non-blocking이다.

### 승인된 Monthly 결정 요약

| ID | P0 최종 결정 |
|---|---|
| OD-M01 | Section 활성화·표시·계층·빈 값 정책은 Template instance data가 결정한다. 기본 활성 후보는 `theme`/`outdoor_play`/`safety_education`/`week_axis`, Optional은 `goals`/`habits`/`focus`/Custom. 빈 값은 `RENDER_EMPTY_CELL`, 계층 `max_depth = 2`. `display_mode`의 전국 공통 기본값을 만들지 않고 Section마다 명시하며 값 집합은 확장 가능하다. Template A는 `SAMPLE_DERIVED_NON_NORMATIVE` product adapter다 |
| OD-M02 | `SSUKSAK_P0_CANONICAL_WEEK_POLICY` — Monday-start week 중 월~금 5일 가운데 target month에 3일 이상 포함된 주를 ordered list로 산출하고 경계를 clip하지 않는다. `week_id = YYYY-MM-Wn`은 동일 입력에서 항상 동일하며 Edit/Regenerate/Override로 변경되지 않는다. Override(`week_days`/`active`/`display_group`)는 canonical을 삭제·재번호화하지 않는다. 국가 표준이 아닌 제품 내부 deterministic policy다 |
| OD-M03 | `subtheme`과 `expected_play`를 자동 병합하지 않고 중립 슬롯 `monthly.week.<week>.focus`를 쓴다. `source_label`/`label_variant`/`mapping_confidence`를 보존하고 기관 단위 label mapping을 만들지 않는다. `focus`는 default inactive. 공용 `PlanItem`을 변경해 Yearly Core를 건드리지 않는다 |
| OD-M04 | 법령 Rule은 법정 구분·실시 간격·연간 최소 시간·적용 대상·source/version만 저장하고 월 assignment를 만들지 않는다. Rule은 검증만 하고 배치를 창작하지 않는다. 배치 Source는 기관 제공 연간계획 또는 교사 입력이며, 없으면 임의·LLM 배치와 법적 충족 주장을 금지하고 `법정 요건 미검증 / source required` 상태를 표현한다. 비법정 기관 label을 법정 6구분으로 자동 매핑하지 않고 `emergency_response`/`drill`을 별도 semantic key로 유지한다 |

### 승인된 Yearly 결정 요약

| ID | P0 최종 결정 |
|---|---|
| OD-Y01 | 필수 의미 구조는 `school_year` + `classroom_ref` + 3월~다음 해 2월의 정확히 12개 `MonthPeriod`를 담는 `month_periods[12]` + 각 월의 필수 `theme`; 그 밖의 의미 필드는 Optional; 편집 단위는 `item_id`와 `semantic_key`로 안정적으로 주소화 |
| OD-Y02 | 사람이 검증한 versioned Theme Reference v0를 연간 theme의 Rule 후보 원천으로 사용; Rule이 후보를 선택하고 LLM은 선택된 표현만 다듬음 |
| OD-Y03 | Plan 소유 단위는 `classroom`; Confirm 행위자는 표시 이름이 아닌 opaque `actor_id`/`user_id`; 혼합연령도 classroom당 하나의 Plan |

---

## 3. BLOCKING — P0 결정 완료

### OD-Y01 — Yearly Plan v0의 최소 의미 구조와 주소 체계

- **ID:** OD-Y01
- **P0 최종 결정문:** P0 Yearly Plan의 필수 의미 구조는 `school_year`, `classroom_ref`, 학년도 3월부터 다음 해 2월까지 월 순서가 보장된 정확히 12개의 `MonthPeriod`를 담는 `month_periods[12]`, 각 `MonthPeriod`의 필수 `theme`로 확정한다. 이 밖의 의미 필드는 모두 Optional로 둔다. 편집 가능한 각 항목은 표시 Label이나 물리 저장 위치와 독립된 `item_id`와 `semantic_key`를 안정 주소로 가져야 한다.
- **현재 근거:**
  - docs/demo-source-of-truth.md §14는 `school_year`, `classroom_ref`, 3월~다음 해 2월의 ordered `MonthPeriod` 12개, 각 월의 필수 `theme`, 나머지 Optional 필드와 `item_id`/`semantic_key` 안정 주소를 확정한다.
  - docs/screen-spec.md §11은 같은 Yearly Plan v0 최소 구조와 편집 주소를 화면 Contract로 반영한다.
  - CLAUDE.md §8·§13은 Plan → Sections → Slots/Items 및 DB와 분리된 Structured Output을 요구한다.
  - 연간 실측은 월 주제는 반복되지만 주차·목표·기관 특화 열은 가변임을 보여준다. Monthly Template A의 8행을 연간에 재사용할 수 없다.
- **분류:** BLOCKING
- **영향 범위:** GenerateYearlyPlan 출력 DTO, LLM Structured Output, DRAFT 저장, Edit 대상 주소, 셀 재생성, Validation, Provenance 연결, API 응답
- **적용 Contract:**
  - `school_year`, `classroom_ref`, 12개 `MonthPeriod`를 담는 `month_periods`, 각 월의 `theme`는 필수다.
  - `goals`, `rationale`, `weekly_focus`, 주차 하위항목, 기관 특화 Section을 포함한 나머지 의미 필드는 Optional이다.
  - Optional 주차 하위항목을 사용하더라도 가변 길이 Item 집합으로 표현하고 4주/5주를 강제하지 않는다.
  - `item_id`는 항목 인스턴스의 안정적인 식별자, `semantic_key`는 항목 의미의 안정적인 식별자로 사용한다. 표시 Label과 DB 컬럼 위치는 편집 주소로 사용하지 않는다.
  - LLM DTO는 Application Contract로 정의하고 물리 DB 모델과 직접 결합하지 않는다.
- **비결정 범위:** 물리 테이블·컬럼과 공개 HTTP 요청/응답의 최종 형태는 OD-N08에서 결정한다.
- **승인일:** 2026-09-09
- **상태:** RESOLVED_FOR_P0

### OD-Y02 — Theme Reference의 출처와 Rule 선택 Contract

- **ID:** OD-Y02
- **P0 최종 결정문:** P0 연간 theme 후보는 사람이 검증한 versioned Theme Reference v0를 Rule의 후보 원천으로 사용한다. Rule Engine이 Reference 안에서 후보를 선택하고, LLM은 Rule이 선택한 theme의 표현만 다듬는다. LLM이 후보를 자유 생성하거나 선택·교체하는 것은 허용하지 않는다.
- **현재 근거:**
  - CLAUDE.md §4·§5는 배치와 최종 후보 선택을 Rule이 담당하고 LLM의 자유 선택을 금지한다.
  - docs/demo-source-of-truth.md §15는 versioned Theme Reference v0와 Rule 후보 필터·선택 Contract를 확정한다.
  - 공식 Curriculum은 월별 고정 주제 목록이 아니므로 theme를 CURRICULUM에서 직접 정해졌다고 기록할 수 없다.
  - Activity taxonomy와 초기 Reference 데이터의 완료 범위는 OD-N03에서 추적한다.
- **분류:** BLOCKING
- **영향 범위:** Yearly Rule, Reference Data, 후보 조회, LLM 입력, Provenance, Golden Set
- **적용 Contract:**
  - Theme Reference v0의 항목은 최소한 `theme_id`, `label`, `applicable_months`, `age_conditions`, `curriculum_links`, `origin_id`, `source_version`을 제공한다.
  - 사람이 검증하고 version이 부여된 항목만 Rule 후보 집합에 포함한다.
  - 월·연령·반 Context에 따른 후보 적합성 판단과 최종 후보 선택은 Rule이 담당한다.
  - LLM 입력에는 Rule이 선택한 후보를 전달하며, LLM 출력은 그 의미를 유지한 표현 조정으로 제한한다.
  - Theme Reference를 사용한 Item의 Evidence Source는 `source_type=THEME_REFERENCE`, `source_id=theme_id`, `source_version`으로 기록한다.
  - `origin_id`는 Theme Reference가 파생된 상위 원천의 lineage에만 사용하며 Evidence의 canonical `source_id`를 대신하지 않는다. Theme를 국가가 월별로 지정한 것처럼 표시하지 않는다.
- **비결정 범위:** Activity taxonomy 전체와 초기 Reference 데이터의 완료 범위는 OD-N03에서 결정한다.
- **승인일:** 2026-09-09
- **상태:** RESOLVED_FOR_P0

### OD-Y03 — Plan 소유권과 Confirm 행위자의 최소 Identity Contract

- **ID:** OD-Y03
- **P0 최종 결정문:** P0 Plan의 소유 단위는 `classroom`으로 확정한다. Confirm 행위자는 표시용 담임 이름이 아닌 opaque `actor_id`/`user_id`로 식별한다. 혼합연령 반도 연령별 Plan으로 분할하지 않고 해당 classroom에 하나의 Plan을 두며, 포함 연령 집합은 생성 Context로 사용한다.
- **현재 근거:**
  - docs/screen-spec.md §11은 연간 Plan을 반 단위 Context로 관리한다고 정한다.
  - CLAUDE.md §11과 docs/screen-spec.md §8·§9는 누가 언제 확정·수정했는지 추적하도록 요구한다.
  - 반 정보의 담임 이름은 표시 문자열이며 계정·권한 식별자라는 규정이 없다.
  - 첫 Slice는 ConfirmYearlyPlan까지 포함한다.
- **분류:** BLOCKING
- **영향 범위:** Plan FK, 멀티테넌시 경계, 생성·조회 권한, confirmed_by, Audit Event, Confirm API
- **적용 Contract:**
  - YEARLY·MONTHLY·WEEKLY Plan은 모두 하나의 `classroom`에 귀속되고, daycare 귀속은 classroom 관계를 통해 해석한다.
  - Application 계층의 논리 개념은 opaque `ActorId`로 둔다. 인증 계층의 식별자가 `user_id`라면 이를 ActorId로 전달하거나 매핑할 수 있다.
  - Confirm Audit Event에는 opaque 행위자 식별자와 확정 시각을 기록한다. 담임 이름은 표시 정보일 뿐 권한·감사 식별자로 사용하지 않는다.
  - 인증 구현이 아직 없어도 Confirm Use Case에는 ActorId를 주입하고 테스트에서는 실제 사용자 정보가 아닌 테스트용 opaque ID를 사용한다.
  - 혼합연령 classroom은 Plan 하나를 소유하며 포함 연령 집합 전체를 생성·검증 Context로 사용한다.
- **비결정 범위:** 인증 공급자, 권한 모델, 물리 FK·컬럼 이름, 혼합연령의 물리 저장 방식은 각각 후속 Contract와 OD-N02·OD-N08에서 결정한다.
- **승인일:** 2026-09-09
- **상태:** RESOLVED_FOR_P0

---

## 4. BLOCKING-BEFORE-MONTHLY

### OD-M01 — Monthly Template A v0의 남은 Section Contract

- **ID:** OD-M01
- **결정 내용:** Section의 활성화·표시 방식·계층·빈 값 정책은 **코드 전역 기본값이 아니라 Template instance data가 결정한다.**
- **현재 근거:**
  - docs/template-a-validation.md §1·§8·§12는 고정 8행 × 고정 주차 열을 지지하지 않는다.
  - docs/demo-source-of-truth.md §18~§20과 docs/screen-spec.md §12.3은 실측 Guardrail을 P0 Contract로 반영한다.
  - **2026-09-11 재측정(표본 13개 / 기관 11곳 / 정량 분모 10기관)** 결과가 docs/template-a-validation.md §3.1~§3.4·§4.5·§4.6에 있다. 이전 근거의 3/3·2/3·0/3 분모는 이 재측정으로 대체됐다.
  - 전수 관찰(10/10): theme 계열, `outdoor_play`, `safety_education`.
  - 준전수(9/10): 주차 축. **아이사랑어린이집 3파일에는 주차 축이 없다**(§3.2). 따라서 주차 축은 기본 활성 후보이지만 무조건 필수 축이 아니다.
  - 다수: `goals` 8/10, `habits` 6/10, `focus`(subtheme ∪ expected_play) 6/10.
  - **`character_greeting` 0/10.** 1차 0/3에서 확대 표본에서도 전무하다.
  - 2단 라벨 계층은 4기관에서 관찰되고 **3단은 0/10**이다(§4.6). 큰빛에서는 `outdoor_play`가 `놀이`의 하위 Section이다.
  - 한솔빛 3페이지에 `안전교육` 행이 있고 4개 주차 셀이 모두 비어 있다. Section의 존재와 값의 충족을 분리해야 한다.
  - 같은 `outdoor_play`·`safety_education`이 1차 기하 판독에서 `weekly_cells`와 `monthly_merged_summary`로 갈렸다. **확대된 9개 표본의 셀 병합 여부는 미측정**이다(§0 — `pdftoppm` 부재).
- **분류:** BLOCKING-BEFORE-MONTHLY
- **영향 범위:** Monthly DTO/DB, Template renderer, 편집 주소, Validation, 원 양식 Mapping
- **P0 최종 결정 (`RESOLVED_FOR_P0`):**
  - 고정 8행 스키마를 금지하고 의미 기반 Template/Section 정의를 사용한다.
  - Template과 Renderer는 `theme`, dynamic `WeekPeriod` axis, `outdoor_play`, `safety_education`을 표현할 수 있어야 한다. 이 기본 지원은 표현 가능성을 뜻한다.
  - **활성화·표시·계층·빈 값 정책의 결정 주체는 Template instance data다.** 코드에 전역 기본값을 두지 않는다.
  - **기본 활성 후보:** `theme`, `outdoor_play`, `safety_education`, `week_axis`.
  - **Optional / default inactive:** `goals`, `habits`, `focus`(subtheme/expected_play 중립 슬롯), 그 밖의 Custom Section.
  - **빈 값 정책 = `RENDER_EMPTY_CELL`.** Section이 활성화되어 있고 값이 없다는 이유만으로 Section 자체를 삭제하지 않는다. 값이 없다는 사실만으로 생성·저장·확정을 차단하지 않는다.
  - **계층 `max_depth = 2`.** 3단 이상 계층을 P0 기본 Contract로 만들지 않는다.
  - **`display_mode`의 전국 공통 기본값을 만들지 않는다.** 구조는 `Template → Section → display_mode`이며 각 Template instance의 각 Section이 `display_mode`를 명시해야 한다. `global display_mode default = 없음`.
  - 현재 관찰된 `WEEKLY_CELLS`와 `MONTHLY_MERGED_SUMMARY`를 지원한다. **이 두 값만이 영구적으로 전부라고 Contract에 못 박지 않는다.** §3.2의 inline/tagged 유형 등 추가 표현 방식을 수용할 확장 경계를 남긴다.
  - 성품인사는 원/반의 선택적 Profile Context일 뿐 Monthly 출력의 기본행이 아니다. Profile에 값이 있어도 출력에 자동 생성하지 않으며, 사용자가 명시적으로 활성화한 Custom Section에서만 출력할 수 있다.
  - 원본 `source_label`을 보존하고 내부 `semantic_key`와 분리한다. `source_label`은 **Plan 또는 Template instance 단위**로 보존한다(§3.3 — 같은 기관이 연령 페이지별로 다른 라벨을 쓴다). 기관 단위 라벨 Mapping 테이블을 만들지 않는다.
  - 안전교육의 고정 행 번호를 가정하지 않는다.
  - `subtheme`과 `expected_play`는 자동 병합하지 않는다(OD-M03).
  - **Template A는 국가 표준이 아니라 `SAMPLE_DERIVED_NON_NORMATIVE` product adapter다.** 이 성격을 Template 데이터의 `normative_status`로 명시한다.
- **후속으로 남는 것 (P0 차단 아님):**
  - 각 Section의 실제 `display_mode` 값 — Template instance 작성 시 사람이 검토한다. 확대 표본의 병합 여부가 미측정이므로 표본 근거로 정할 수 없다.
  - `display_mode` 값 집합에 inline/tagged 유형을 추가할지 여부
  - Template A 외 추가 Template 범위는 OD-N07
- **승인일:** 2026-09-11
- **상태:** RESOLVED_FOR_P0

### OD-M02 — Dynamic WeekPeriod 산출·경계·ID 안정성·Override 정책

- **ID:** OD-M02
- **결정 내용:** 대상 월의 WeekPeriod 산출 규칙, 경계, `week_id` 형식과 안정성, Override 정책을 **제품 내부 결정론 정책**으로 확정한다.
- **현재 근거:**
  - docs/template-a-validation.md §6은 4주/5주 고정값을 금지하고 실제 기간에서 동적 산출하도록 한다.
  - docs/demo-source-of-truth.md §20은 ordered WeekPeriod의 논리 필드 `week_id`, `start_date`, `end_date`, `display_label`의 존재를 확정한다.
  - **2026-09-11 재측정** docs/template-a-validation.md §6.3: 명시적 날짜 범위를 표기한 기관 3곳 전부가 **월요일 시작**이고 **1주가 전월 8월 31일에 시작**한다. 2/3은 다음 월(10월 2일)로 넘어간다.
  - 요일 폭이 월~금 5일과 월~토 6일로 갈린다(엄지).
  - **주가 대상 월을 타일링하지 않는다.** 엄지는 9월 24~30일을 전혀 덮지 않는다.
  - `display_label`이 실제 범위와 분리된다. 시립새봄은 8월에 시작하는 주를 `9월 1주`로 표기한다.
  - 표시 grouping이 주 목록과 다르다. 아이들세상은 4주·5주를 한 셀로 병합한다.
  - **한 문서 안에서 헤더 주차 수와 본문 참조 주차 수가 어긋난다**(§6.2-7 큰빛 헤더 4주 / 안전교육 본문 5주).
  - 달력월 절단 규칙은 실측 0/3이 지지하고, ISO-8601 목요일 귀속 규칙은 2026-09에서 4주가 되어 관측 다수와 불일치한다.
- **분류:** BLOCKING-BEFORE-MONTHLY
- **영향 범위:** Monthly 생성, Calendar Reference, Section Item 배치, 화면 열, 주간 Plan 연결
- **P0 최종 결정 (`RESOLVED_FOR_P0`) — `SSUKSAK_P0_CANONICAL_WEEK_POLICY`:**
  - Calendar 계층은 고정 4주/5주 상수가 아닌 ordered `WeekPeriod` 목록을 반환한다.
  - 각 WeekPeriod에는 논리 필드 `week_id`, `start_date`, `end_date`, `display_label`이 존재한다.
  - **canonical 산출 규칙**
    - Monday-start week를 기준으로 한다.
    - 월~금 5일 가운데 **target calendar month에 3일 이상 포함된 주**를 canonical 목록에 포함한다.
    - 결과는 ordered list다.
    - `start_date`/`end_date`를 **target month 경계로 clip하지 않는다.**
    - `target_month`와 `school_year`를 별도로 보존한다.
  - **`week_id` = `YYYY-MM-Wn`.** `n`은 해당 `target_month`의 canonical ordered WeekPeriod 순번이다.
  - **`week_id`는 동일 입력에서 항상 동일해야 하고 Edit / Regenerate / Override로 변경되면 안 된다.**
  - **Override는 canonical WeekPeriod를 삭제하거나 재번호화하지 않는다.**
  - **P0 Override 3종**
    1. `week_days` — `MON_FRI`, `MON_SAT` 등. 값 집합은 확장 가능하다.
    2. `active` — 휴원·연휴 등으로 특정 canonical week를 비활성화한다.
    3. `display_group` — 표시 병합. 예: 4주·5주를 한 칸으로 병합.
  - **이 규칙은 국가·법정·어린이집 공통 주차 표준이 아니다.** `SSUKSAK_P0_CANONICAL_WEEK_POLICY`라는 이름의 **제품 내부 deterministic policy**로 문서화한다.
  - **기관 실제 양식이 다르면 Override 또는 후속 Template adapter가 우선한다.**
- **검증 근거:** 2026-09 → 5주, 2026-03 → 4주. 관측 9건 중 7건 일치. 불일치 2건(엄지 4주, 큰빛 p.1 헤더 4주)은 기관 운영상 절단이며 Override 대상이다.
- **후속으로 남는 것 (P0 차단 아님):**
  - 공휴일 데이터의 자동 반영. 현재 Calendar Reference가 없어 P0는 기관 입력 Override로만 처리한다.
  - Weekly Plan과의 `week_id` 정합은 OD-W02
- **승인일:** 2026-09-11
- **상태:** RESOLVED_FOR_P0

### OD-M03 — subtheme과 expected_play의 의미 관계

- **ID:** OD-M03
- **결정 내용:** 두 Label을 완전 동의어로 자동 병합하지 않고, **중립 구조 슬롯 1개 + 조건부 Label Mapping + 원본 Label 보존**으로 처리한다.
- **현재 근거:**
  - **2026-09-11 재측정**: `subtheme` 명시 행 **4/10**(괴산하나·해찬솔·한솔빛·아이들세상), `expected_play` 명시 행 **3/10**(괴산하나·예담·큰빛), 둘 중 하나라도 명시된 기관 **6/10**.
  - **정확한 관찰 명제:** 두 Label은 같은 표의 두 독립 행으로 병존한 사례는 관찰되지 않았고, 동일 기관의 Template 계열에서 연령별로 동일 구조 슬롯을 서로 다른 `source_label`로 표현한 사례가 관찰되었다. (docs/template-a-validation.md §3.3 괴산하나 — p.1 만3세는 `예상 놀이`, p.2 만4·5세는 `소주제`이며 둘 다 주차 헤더 직하·주당 1값의 같은 구조 위치다.)
  - 이전 근거 문장 "두 Label이 같은 문서에서 동시에 관찰되지 않았다"는 위 관찰로 **교정됐다.**
  - 같은 기관이 연령 페이지별로 theme·goals 라벨도 다르게 쓴다(`놀이 주제`↔`생활주제`, `교사의 기대`↔`목표`).
  - 시립새봄의 무라벨 열도 주차와 항상 1:1이 아니다.
  - `예상놀이주제`(아이사랑)는 theme 라벨이고 `예상 놀이`는 focus 행 라벨이다. 문자열 부분일치로 매핑하면 계층이 뒤집힌다(§5.1).
  - docs/template-a-validation.md §4.4·§5는 의미 동일성을 미확정으로 둔다.
- **분류:** BLOCKING-BEFORE-MONTHLY
- **영향 범위:** Label Mapping, Monthly Structured Output, Import parser, 편집 UI, Yearly→Monthly Context 해석
- **P0 최종 결정 (`RESOLVED_FOR_P0`):**
  - **`subtheme`과 `expected_play`를 완전 동의어로 자동 병합하지 않는다.** 하나의 필드로 손실 병합하지 않는다.
  - P0에서는 중립 구조 슬롯 **`monthly.week.<week>.focus`** 를 사용할 수 있다.
  - **이것은 장기 의미 표준이 아니라 P0 Template mapping용 neutral slot이다.**
  - **반드시 보존:** `source_label`, `label_variant`, `mapping_confidence`.
  - `label_variant` 값 예: `SUBTHEME_LABELED`, `EXPECTED_PLAY_LABELED`, `UNLABELED`.
  - **두 source label을 같은 문자열 의미로 정규화하지 않는다.**
  - **기관 단위 label mapping을 만들지 않는다.** 같은 기관에서도 연령별 페이지에 따라 label이 달랐다.
  - `focus`는 **default inactive**로 둔다.
  - **공용 `PlanItem`에 `source_label`/`mapping_confidence`를 추가해서 Yearly Core를 변경하지 않는다.** Monthly 전용 metadata가 필요하면 `MonthlyPlanItem` 또는 Monthly item metadata 구조를 별도로 두는 방향으로 설계한다.
- **후속으로 남는 것 (P0 차단 아님):**
  - 두 Label의 최종 의미 관계(동일 / 상하위 / 별개). 동일 구조 슬롯을 점유한다는 사실은 확인됐으나 의미 동일성은 확인되지 않았다. 추가 표본이 필요하다.
  - 중립 이름 `focus`를 장기 Contract로 승격할지 여부. v0에서는 하지 않는다.
  - Import Mapping은 OD-N09
- **승인일:** 2026-09-11
- **상태:** RESOLVED_FOR_P0

### OD-M04 — Safety Rule Data, 월 배치 정책, 출력 Grouping

- **ID:** OD-M04
- **결정 내용:** 검증된 법정 제약만 Machine-readable Rule로 버전 관리하고, **월 배치는 Rule이 창작하지 않는다.** 배치 Source가 없을 때의 상태 표현을 요구한다.
- **현재 근거:**
  - CLAUDE.md §5는 Legal Constraint와 Monthly Placement Policy를 분리하고 둘 다 Rule 계층에서 처리하도록 확정한다.
  - **공식 근거 판본 확인 (2026-09-11):** `references/official/아동복지법_시행령_별표6_교육기준_2022개정.pdf` `<개정 2022. 6. 21.>` = **6구분**. `references/official/2026_보육사업안내_본문.pdf`의 `안전교육 기준(아동복지법 제31조 및 같은 법 시행령 제28조)` 표와 6구분·실시 주기·연간 시간·교육내용 항목이 **완전히 일치**한다. 판본 충돌 없음.
  - `references/official/아동복지법_시행령_제28조_아동안전교육_2026-08.pdf`는 `[시행 2026. 8. 4.] [대통령령 제36558호]`이며 제28조①이 별표6을 그대로 참조한다. 별표6 자체의 최종 개정일이 2022. 6. 21.이라는 뜻이며 판본 충돌이 아니다.
  - **별표6과 시행령 제28조 전문에 특정 월 지정이 0건이다.** 시간 표현은 `2개월에 1회 이상`·`3개월에 1회 이상`·`6개월에 1회 이상`·`연간 N시간 이상`뿐이다. 고정 날짜는 제28조②의 보고 기한 `매년 3월 31일까지` 하나이며 교육 실시 월이 아니다.
  - **2026-09-11 재측정** docs/template-a-validation.md §7.1: `safety_education` 10/10 관찰. 그러나 가장 빈번한 안전 라벨인 **`생활안전`(6/10)이 별표6 구분이 아니다.** `비상대응`/`비상대응훈련` 6/10, `심폐소생술` 3/10, `장애인식 개선 교육` 3/10, `소방안전` 1/10도 별표6 구분이 아니다.
  - 큰빛은 안전교육을 월간 병합 셀 안에 `1주-…5주-`로 주차를 텍스트 인코딩한다. 데이터(week 보존)와 표시(병합)를 분리해야 한다.
  - `emergency_response`를 안전교육과 별도 행으로 두는 기관은 금산군청·아이들세상이다.
- **분류:** BLOCKING-BEFORE-MONTHLY
- **영향 범위:** Safety Rule 데이터, Monthly 배치, Validation, 상태창, Provenance, Template renderer
- **P0 최종 결정 (`RESOLVED_FOR_P0`):**
  - **Legal Constraint와 Monthly Placement Policy를 분리한다.** `legal_rule_version`과 `placement_policy_version`을 분리한다.
  - **법령 Rule은 다음만 저장한다:** 법정 구분 / 실시 간격 / 연간 최소 시간 / 적용 연령·대상 / source·version.
  - **법령 데이터에 특정 월 assignment를 만들지 않는다.**
  - **Rule은 법정 조건을 검증하며 특정 월·주 배치를 자동 창작하지 않는다.**
  - **실제 배치 Source 우선순위:** ① 기관·교사가 제공한 안전교육 연간계획 ② 교사 직접 입력.
  - **둘 다 없을 때**
    - 임의 월 배치 생성 금지
    - LLM 배치 생성 금지
    - 법적 충족 주장 금지
    - Safety Section은 구조적으로 존재·표현 가능
    - 값이 없을 수 있음
    - `법정 요건 미검증 / source required` 상태를 표현할 수 있어야 함
  - **비법정 기관 label**(`생활안전`, `심폐소생술`, `장애인식 개선`, `소방안전`, `비상대응` 등)**을 법정 6구분으로 자동 매핑하지 않는다.**
  - **`emergency_response`와 `drill`을 `safety_education`에 자동 병합하지 않고 별도 semantic key를 유지한다.**
  - 안전교육 Item은 실제 week/date를 보존하고 표시 방식은 Template Section 설정으로 둔다.
  - **제품 기본 safety placement policy는 P0에서 발행하지 않는다.**
  - 월 1회 소방·비상대응훈련은 법령이 아니라 행정지침(2026 보육사업안내)이다. 법령 데이터에 섞지 않는다.
- **후속으로 남는 것 (P0 차단 아님, 단 M1 설계 전 승인 필요):**
  - `법정 요건 미검증 / source required` 상태를 DTO·GenerationRun에서 어떻게 표현할지. **M1 설계 전에 제안하고 승인받는다. 임의 Enum을 만들지 않는다.**
  - 제품 기본 월 배치 정책 발행 여부 — P0 밖
  - 연간 누적시간 실제 집계 — 12개월 Monthly 완성 후에야 계산 가능
  - 안전교육 연간계획안 Import 파서는 OD-N09
- **승인일:** 2026-09-11
- **상태:** RESOLVED_FOR_P0

---

## 5. BLOCKING-BEFORE-WEEKLY

### OD-W01 — 월간계획안 미사용 경로

- **ID:** OD-W01
- **결정 내용:** 월간계획안을 사용하지 않는 경우 YEARLY → WEEKLY 직접 Gate와 parent 관계를 지원할지 확정한다.
- **현재 근거:**
  - P0 표준 경로는 YEARLY → MONTHLY → WEEKLY다.
  - docs/screen-spec.md §4.1은 월간 사용 여부 UI를 두지만 직접 경로의 Gate·parent·API는 Open으로 남긴다.
- **분류:** BLOCKING-BEFORE-WEEKLY
- **영향 범위:** Plan parent, Confirmation Gate, 최초 설정 UI, Weekly 생성 입력, API
- **권장안:**
  - 결정 전에는 `월간계획안 사용` 값을 사용으로 고정하고, `미사용` 선택지는 숨기거나 비활성화한다. 비활성화 상태로 노출할 경우 아직 지원하지 않는 경로임을 안내한다.
  - P0 실행 경로는 표준 YEARLY → MONTHLY → WEEKLY만 활성화한다.
  - 월간 미사용 토글을 실제 선택 가능하게 노출하려면 같은 결정에서 직접 Gate와 Parent Contract를 함께 확정한다.
- **결정 시점:** 월간 미사용 토글 활성화 또는 GenerateWeeklyPlan 착수 전
- **상태:** OPEN

### OD-W02 — Weekly Plan의 Canonical Output과 출력 위치별 Adapter

- **ID:** OD-W02
- **결정 내용:** Weekly Plan의 의미 구조와 별도 주간계획안·주간보육일지 계획칸·일일보육일지 계획칸별 렌더링 Contract를 확정한다.
- **현재 근거:**
  - docs/screen-spec.md §13은 세 출력 위치를 열어두고 정확한 Contract를 미확정으로 둔다.
  - 과거 18칸 가정은 폐기됐다.
  - 현재 주간 Sample 수만으로 전국 공통 고정 양식을 만들 수 없다.
- **분류:** BLOCKING-BEFORE-WEEKLY
- **영향 범위:** Weekly DTO/DB, Monthly→Weekly Context, Renderer, Export, UI
- **권장안:**
  - 하나의 semantic WeeklyPlan과 출력 위치별 Adapter를 분리한다.
  - P0 첫 Weekly Slice는 별도 주간계획안 Adapter 하나를 먼저 승인하고 나머지는 후속으로 추가한다.
  - 요일/Slot 수를 물리 18칸으로 고정하지 않는다.
  - OD-W02 승인 전에는 후보를 저장·실행 가능한 UI 선택지로 활성화하지 않는다. 보육일지 계획칸 Adapter는 전체 보육일지 생성 범위를 뜻하지 않는다.
- **결정 시점:** GenerateWeeklyPlan DTO와 첫 Weekly renderer 작성 전
- **상태:** OPEN

---

## 6. NON-BLOCKING

### OD-N01 — PostgreSQL 15 최종 팀 확정

- **ID:** OD-N01
- **결정 내용:** DBMS와 주요 버전을 최종 승인한다.
- **현재 근거:** docs/demo-source-of-truth.md §27은 PostgreSQL 15를 최신 팀 방향으로 명시하지만 최종 합의 전에는 Open으로 남기라고 한다.
- **분류:** NON-BLOCKING
- **영향 범위:** Driver, Migration, JSON/Enum/ID 타입, 배포
- **권장안:** Repository Port 뒤에서 PostgreSQL 15 기준으로 준비하되 최종 승인 전 비가역적 DB 기능 의존을 최소화한다.
- **결정 시점:** 첫 영구 Migration 병합 전
- **상태:** PROVISIONAL

### OD-N02 — 혼합연령의 물리 저장 방식

- **ID:** OD-N02
- **결정 내용:** 포함 연령 집합을 조인 테이블, 배열, JSON 중 어떤 방식으로 저장할지 확정한다.
- **현재 근거:** CLAUDE.md §9와 docs/screen-spec.md §2.2는 논리 모델을 복수 연령 집합으로 확정하고 단일 age_group 숫자를 금지한다.
- **분류:** NON-BLOCKING
- **영향 범위:** Classroom Migration, 조회/필터, 혼합연령 Validation
- **권장안:** classroom_age_groups 조인 테이블과 (classroom_id, age) Unique Constraint를 사용한다. Application Contract는 Set<Age>로 유지한다.
- **결정 시점:** Classroom 영구 Migration 작성 전
- **상태:** OPEN

### OD-N03 — Activity taxonomy와 초기 Reference 범위

- **ID:** OD-N03
- **결정 내용:** activity_area, tags, safety_flags의 제어 어휘와 P0 초기 후보 데이터의 범위·완료 기준을 정한다.
- **현재 근거:** Source of Truth §12·§34는 최소 메타데이터 후보를 제시하지만 taxonomy와 초기 범위를 Open으로 둔다.
- **분류:** NON-BLOCKING
- **영향 범위:** Candidate Filtering, Reference ingestion, Golden Set, 품질
- **권장안:** curriculum_domain, activity_area, plan_slot을 분리하고, 초기 범위는 임의 총건수보다 Golden Set의 연령·계절·행사 유무를 충족하는지로 정의한다. 구현은 Repository Port와 소수 Fixture로 먼저 시작한다.
- **확정 Human Decision (2026-09-11, `RESOLVED_FOR_P0` 범위):**
  - **D1 — Activity Catalog 월 커버리지.** 현재 확보된 월간 Activity 표본은 2026-09 중심 + 2026-03 일부뿐이므로 12개월 전체 Activity Reference를 `HUMAN_APPROVED`로 승인하지 않는다. 초기 Activity Reference는 `PENDING_HUMAN_REVIEW`까지만 허용하며 runtime-active Catalog로 사용하지 않는다. 나머지 월을 추론해 채우지 않고, Theme Reference의 `applicable_months`를 Activity 근거로 전용하지 않으며, 근거 없는 Activity를 생성하지 않는다. 추가 월간 표본으로 월 커버리지를 확장한 뒤 별도 Human Review로 승인한다. 현재 자료는 완성 Catalog가 아니라 Contract 검증용 실제 seed다.
  - **D2 — 외부 Source.** 키드키즈·꼬망세 등 외부 Activity Source는 P0 현재 단계에서 NO-GO다. 자동 scraping, 이용약관·robots 우회, 외부 본문 대량 복제를 하지 않으며 M2 blocker로 사용하지 않는다. 영구 제외를 뜻하지 않는다. 이용 허가·라이선스·사용자 제공 자료·합법적으로 확보된 Reference가 생기면 별도 결정으로 다룬다.
  - **D3 — 기관 고유 시설·지역 Activity.** 특정 기관이나 지역에 종속되는 값은 공통 runtime Candidate로 일반화하지 않는다. 의미를 바꿔 canonical Activity로 만드는 억지 일반화도 금지한다. 원문 분석 근거로 보존할 필요가 있으면 upstream evidence에만 남기고 공통 runtime Candidate에는 포함하지 않는다.
  - **D4 — activity_area.** 이번 단계에서 확정하지 않는다. `art`/`physical`/`language`/`sensory`/`nature`/`role_play` 같은 enum을 추측으로 만들지 않는다.
- **확정 M2-A Contract (`RESOLVED_FOR_P0` 범위):**
  - `placement_slots[]`는 Monthly Template semantic_key에 종속되는 통제 어휘이며 P0 허용값은 `outdoor_play` 하나다. `safety_education`은 Domain과 schema가 모두 거부한다.
  - `setting`은 `OUTDOOR` / `INDOOR` / `EITHER`이며 `indoor_alternative` Section과 다른 개념이다. `outdoor_play` slot은 `OUTDOOR` 또는 `EITHER`만 받는다.
  - 연령은 `supported_ages[]` + `allow_mixed_age` + `mixed_age_requires_all_supported`로 표현하고 `min_age`/`max_age`를 쓰지 않는다. `supported_ages`는 evidence `age_scope` 합집합을 넘을 수 없고, `applicable_months`는 관찰된 월을 넘을 수 없다. 혼합연령을 위해 Activity를 복제하지 않는다.
  - Theme 연결은 `theme_links[] = {theme_id, relation, theme_catalog_version}` 다대다이며 relation은 `OBSERVED_TOGETHER`만 허용한다. 문자열 유사도 매칭과 규범적 관계 주장을 금지한다.
  - Human Approval과 activation은 Theme Reference 패턴을 따른다. `runtime_active`는 독립 writable 필드가 아니라 `review.domain_owner_approval`에서 파생되며, Production API에 승인 우회 입력을 두지 않는다.
  - Activity Reference는 SafetyEducationPlan도 SafetyLegalRule도 아니다. `safety_flags` 필드를 두지 않고 법정 안전교육 content를 같은 Catalog에 섞지 않는다.
  - Cell Evidence는 기존 `EvidenceSourceType.ACTIVITY_REFERENCE`를 사용하며 canonical `source_id`는 `activity_id`다. 공용 Provenance Enum을 변경하지 않는다.
- **2026-09-12 추가 해소 (M2-B/M2-C/M2-D/M2-E):** 아래 항목은 실제로 해소되었다. 나머지 열린 결정은 그대로 열려 있다.
  - **D1의 월 커버리지 제약이 해소되었다.** 추가 월간 corpus(128 PDF / 40개 기관) 전사 후 `activity-reference-v0.2.0`을 발행했다. 198 항목 · Evidence 288건 · 월 커버리지 **1~12월 전부**. 2026-09-12T00:02:24+09:00에 `reviewer_ai_lead_001`이 `HUMAN_APPROVED`로 승인했다. v0.1.0은 삭제하지 않고 `PENDING_HUMAN_REVIEW` 상태의 역사적 artifact로 보존한다.
  - **Runtime 연결이 완료되었다.** `DEFAULT_ACTIVITY_CATALOG_PATH`가 v0.2.0을 가리키며, `GenerateMonthlyPlan`이 `outdoor_play` Cell을 `RULE_ONLY`로 채우고 `RegenerateMonthlyPlanItem`이 같은 Catalog로 Cell 하나를 재생성한다. 선택은 `monthly.activity.reference_candidate_selection v1` pure rule이 담당한다.
  - **승인 artifact ↔ runtime schema 분리 방식이 확정되었다(HD-I).** 승인본이 함께 담는 Human Review·품질 metadata는 adapter의 **allowlist projection**으로만 제거하고 Domain Model을 확장하지 않는다. allowlist 밖의 미지 필드는 기존대로 strict schema가 거부한다. 승인 상태는 여전히 `review.domain_owner_approval`에서만 파생되며 projection이 이를 바꾸지 않는다.
  - **Catalog version pinning이 확정되었다.** MonthlyPlan은 생성 시 사용한 `activity_catalog_id`/`activity_catalog_version`을 lineage로 보존하고, Regenerate는 그 정확한 version을 다시 해소한다. 이후 새 version이 Production default가 되어도 기존 Plan이 자동으로 따라가지 않으며, 해소 실패 시 default로 fallback하지 않고 실패한다. lineage가 없는 M1 Plan은 outdoor Regenerate가 차단된다(임의 upgrade 금지).
  - **후보 0의 의미가 경로별로 확정되었다.** 정상 Catalog + eligible candidate 0은 Generate에서 `EMPTY_VALID`(실패 아님)이고 Regenerate에서는 **차단**이다. Regenerate는 이미 존재하는 Cell을 지우지 않는다.
- **남은 Contract (`PARTIALLY_RESOLVED` 범위):** `activity_area`와 `tags`의 제어 어휘(D4), `safety_flags`를 장기적으로 둘지 여부, 외부 Source 확보 시의 ingestion·라이선스 Contract(D2 후속), `placement_slots`를 `focus`·`indoor_alternative`로 넓힐지 여부(각 Section의 Template 결정 선행 필요), v0.2.0 안에 남아 있는 `AMBIGUOUS` 항목 8건의 최종 분류(HD-H에 따라 승인 blocker는 아니다)
- **결정 시점:** `activity_area`는 `play` 계열 Section이 Template에 정의된 뒤, 외부 Source Contract는 이용 허가 확보 뒤, `AMBIGUOUS` 8건은 추가 원문 표본 확보 뒤
- **상태:** PARTIALLY_RESOLVED

### OD-N04 — LLM 공급자·모델·timeout·retry

- **ID:** OD-N04
- **결정 내용:** P0 LLM Adapter, 모델, timeout, retry, 최종 실패 정책을 확정한다.
- **현재 근거:** CLAUDE.md §14는 공급자와 모델을 Wrapper 뒤로 격리하고, Source of Truth §26은 실패를 명확히 반환하도록 한다.
- **분류:** NON-BLOCKING
- **영향 범위:** LLM Adapter, 설정, 비용·지연, Generation Run
- **권장안:** Provider-neutral interface와 Fake Adapter로 Rule·Validation을 먼저 구현한다. 수치는 설정값으로 두고, 재시도 후 실패를 잘못된 Plan 성공으로 처리하지 않는다.
- **결정 시점:** 실제 LLM Adapter 연결 및 성능 테스트 전
- **상태:** OPEN

### OD-N05 — Provenance의 물리 저장 Schema

- **ID:** OD-N05
- **결정 내용:** 이미 확정된 Provenance 논리 Contract를 보존하면서 `EvidenceSource[]`, `GenerationMethod`, `AuditEvent[]`를 어떤 테이블·컬럼·관계로 영구 저장하고 조회할지 확정한다.
- **현재 근거:**
  - CLAUDE.md §11과 screen-spec.md §6·§9가 논리 3축을 이미 확정했다.
  - demo-source-of-truth.md §22와 screen-spec.md §6·§9는 Evidence Source, Generation Method, Audit History의 논리 3축으로 동기화되어 있다.
- **분류:** NON-BLOCKING
- **영향 범위:** Migration, 출처 패널, 재현성, 변경 이력
- **확정 논리 Contract (`RESOLVED_FOR_P0` 범위):**
  - 각 Item은 `EvidenceSource[]`를 `0..N`개 가질 수 있다. 근거가 없는 직접 작성 Item도 유효하며 이 경우 빈 배열을 사용한다.
  - 각 Evidence Source는 최소 `source_type`과 canonical `source_id`를 가지며, versioned 원천이면 `source_version`과 필요한 기준 시점(`effective_date`)을 함께 기록한다.
  - Evidence Source type에는 `THEME_REFERENCE`를 포함한다. Theme Reference Item은 `source_type=THEME_REFERENCE`, `source_id=theme_id`로 연결한다.
  - `origin_id`는 Reference가 파생된 상위 원천의 lineage 식별자이며 Evidence Source의 canonical `source_id`와 같은 필드가 아니고 이를 대신하지 않는다.
  - 각 Item은 `GenerationMethod` 하나를 가지며 method는 `RULE_ONLY`, `RULE_LLM`, `IMPORTED`, `MANUAL` 중 하나다. 적용된 Rule의 `rule_id`와 `rule_version`은 Generation Method metadata로 기록하며 Evidence Source에 넣지 않는다.
  - `MANUAL`은 사용자가 Item을 처음부터 직접 만든 생성 방식이다. 기존 Item을 교사가 수정한 사실은 Generation Method를 `MANUAL`로 덮어쓰지 않고 `TEACHER_EDITED` Audit Event로 남긴다.
  - Generation Method는 Item의 현재 값이 만들어진 방식을 나타낸다. 재생성하면 현재 Method를 실제 재생성 방식으로 갱신하고 이전·새 값과 이전·새 Method를 `REGENERATED` Audit Event에 보존한다.
  - Audit History는 ordered `AuditEvent[]`이며 최소 `CREATED`, `REGENERATED`, `TEACHER_EDITED`, `CONFIRMED` 행위를 추적한다. 각 Event는 대상, 시각, 가능한 경우 opaque Actor ID와 변경 전·후 정보를 가진다.
- **남은 물리 Contract (`OPEN` 범위):** 테이블 분리 여부, JSON 사용 여부, FK·Index·보존 기간, 조회 API의 물리 형태를 확정한다. 어떤 방식을 택해도 `item_id`와 위 논리 필드·카디널리티를 손실하지 않는다.
- **결정 시점:** Provenance 영구 Migration과 조회 API 작성 전
- **상태:** OPEN

### OD-N06 — DRAFT 저장, 자동저장, CONFIRMED 이후 Version 정책

- **ID:** OD-N06
- **결정 내용:** P0의 확정된 명시적 저장·미저장 이탈·CONFIRMED 편집 차단을 적용하고, 자동저장, 동시 편집 충돌, 확정 취소·재편집·새 Version 정책을 후속 확정한다.
- **현재 근거:** screen-spec.md §8.2는 P0 CONFIRMED를 읽기 중심·편집 차단으로 정하고, §17은 명시적 저장과 미저장 이탈 경고를 P0 동작으로 확정하면서 자동저장·충돌·Version 세부를 OD-N06에 둔다.
- **분류:** NON-BLOCKING
- **영향 범위:** Edit API, UI 상태, 충돌 처리, Revision/Audit
- **확정 P0 Contract (`RESOLVED_FOR_P0` 범위):** DRAFT 편집은 명시적으로 저장하고, 저장하지 않은 변경이 있으면 이탈 전에 경고하며, CONFIRMED Plan의 직접 편집을 차단한다.
- **남은 Contract (`PARTIALLY_RESOLVED` 범위):** 자동저장 도입 여부와 주기·실패 표시, 동시 편집 충돌 감지·해결, 확정 취소, CONFIRMED 재편집, 새 Version 생성·연결·표시 정책
- **결정 시점:** 자동저장 또는 다중 편집을 활성화하기 전 해당 정책을 확정하고, CONFIRMED 후속 편집을 지원하기 전 Version 정책을 확정
- **상태:** PARTIALLY_RESOLVED

### OD-N07 — Template A 외 추가 Template 범위

- **ID:** OD-N07
- **결정 내용:** P0에서 Template A 외 몇 개의 기관 양식 Adapter를 제공할지 정한다.
- **현재 근거:** Source of Truth §17·§30은 양식 다양성을 인정하지만 P0에는 최소 Mapping만 허용한다.
- **분류:** NON-BLOCKING
- **영향 범위:** Renderer, Import Mapping, 테스트 범위
- **권장안:** P0는 semantic model + Template A v0 하나에 집중하고 추가 Template은 실제 파일럿 우선순위로 결정한다.
- **결정 시점:** Monthly Template A end-to-end 통과 후
- **상태:** DEFERRED

### OD-N08 — Yearly HTTP API와 물리 Persistence Contract

- **ID:** OD-N08
- **결정 내용:** Generate/Read/Edit/Regenerate/Confirm의 endpoint, 요청·응답, 동시성 제어와 물리 테이블 구조를 확정한다.
- **현재 근거:** Source of Truth §28·§31은 Vertical Slice와 동작을 정하지만 docs/contracts.md는 아직 없다. CLAUDE.md §13·§15는 Application Contract와 DB 모델의 직접 결합을 금지한다.
- **분류:** NON-BLOCKING
- **영향 범위:** FE/BE 연결, Migration, 오류 코드, 동시 편집
- **권장안:** 승인된 OD-Y01~Y03을 기준으로 Use Case와 Port를 먼저 구현하고, 외부 HTTP/DB Contract는 별도 docs/contracts.md에서 확정한다. optimistic version 필드를 검토한다.
- **결정 시점:** FE/BE 통합과 영구 Migration 병합 전
- **상태:** OPEN

### OD-N09 — Yearly import 지원 형식·Parser·Normalization Contract

- **ID:** OD-N09
- **결정 내용:** `있는 계획안 이어받기`에서 허용할 Yearly 파일 형식과 버전, 형식별 Parser/Adapter, canonical Yearly Plan으로의 Normalization·검증·오류 처리 Contract를 확정한다.
- **현재 근거:**
  - docs/screen-spec.md §4.2·§14는 기존 Yearly 계획 업로드와 부분 생성을 별도 import 경로로 둔다.
  - docs/demo-source-of-truth.md §4·§30은 기관 고유 양식의 범용 자동 파싱을 P0에서 제외하고 명시적 Template/Adapter Mapping만 허용한다.
  - 승인된 OD-Y01은 Normalize 결과가 `school_year`, `classroom_ref`, ordered 12 `MonthPeriod`, 각 월의 필수 `theme`와 안정 주소를 충족하도록 요구한다.
- **분류:** NON-BLOCKING
- **영향 범위:** 업로드 UI, 형식별 Parser/Adapter, Normalization, Import Validation, 오류·경고, `IMPORTED` Generation Method, 부분 생성
- **확정 Guardrail (`RESOLVED_FOR_P0` 범위):**
  - P0 import는 명시적으로 승인되고 테스트된 파일 형식·버전·Template만 허용한다.
  - 승인 목록에 없는 파일은 추측으로 파싱하지 않고 지원하지 않는 형식으로 명확히 거절한다.
  - 임의 기관 양식을 자동 추론하는 범용 Parser는 P0 범위에서 제외한다.
- **남은 Contract (`OPEN` 범위):** 승인 형식·버전 목록, 파일 크기·인코딩 제한, Template 식별, 필드·월 Mapping, 누락·중복·순서 오류의 Normalize 규칙, 사용자 검토/수정 Gate, 부분 생성 기준, 실패·경고 응답을 확정한다.
- **결정 시점:** `있는 계획안 이어받기` import Slice 착수 전
- **상태:** OPEN

---

### OD-N10 — Theme Reference Reviewer Identity

- **ID:** OD-N10
- **P0 최종 결정문:** Theme Reference 승인자(`approved_by`)는 인증 provider의 로그인
  `user_id`에 의존하지 않고 인증과 독립적인 **opaque reviewer identifier**를 사용한다.
  형식은 `reviewer_<role>_<sequence>`다. 실제 인증·권한 시스템이 도입되면 후속
  Contract에서 매핑 또는 마이그레이션한다.
- **현재 근거:**
  - P0에는 인증 구현이 없다(OD-Y03 비결정 범위).
  - CLAUDE.md §8과 data/themes/README.md는 승인자와 승인 시각을 기록하도록 요구하지만
    식별자 형식을 규정하지 않았다.
  - 저장소에 존재하던 `user_fixture_teacher_001` 등은 테스트 fixture이며 실제 승인자
    식별자로 쓸 수 없다.
- **분류:** NON-BLOCKING
- **영향 범위:** Theme Reference `review.approved_by`, 사람 검토 Gate 기록, 후속 감사
- **적용 Contract:**
  - `approved_by`는 `reviewer_<role>_<sequence>` 형식의 opaque 식별자다.
  - 로그인 `user_id`가 아니고 테스트 fixture도 아니다.
  - **Plan Confirm의 담임교사 `actor_id`(OD-Y03)와 다른 개념이므로 섞지 않는다.**
    전자는 Reference 카탈로그를 검토한 도메인 담당자, 후자는 계획안을 확정한 교사다.
  - `approved_at`은 시간대 오프셋을 포함한 ISO-8601로 기록한다.
  - 승인 metadata 변경만으로 `catalog_version`을 새로 발행하지 않는다.
- **현재 값:** `theme-reference-v0.1.2`의 reviewer는 `reviewer_ai_lead_001`,
  승인 시각은 `2026-09-11T01:11:07+09:00`이다.
- **비결정 범위:** 인증 도입 후의 `user_id` 매핑 방식, reviewer 역할 목록,
  다중 승인자 요구 여부는 후속 Contract에서 결정한다.
- **승인일:** 2026-09-11
- **상태:** RESOLVED_FOR_P0

### OD-N11 — Reference Adapter의 승인 우회 입력 (기술부채)

- **ID:** OD-N11
- **결정 내용:** 기존 Reference Adapter가 생성자·parse 함수 keyword로 받는 승인 상태 주입 입력(`activation_override` / `approval_override`)을 Production Integration 전에 제거할지, 남긴다면 어떤 경계로 격리할지 확정한다.
- **현재 근거:**
  - 2026-09-11 Monthly M2-B Preflight에서 `JsonActivityReferenceRepository` / `load_activity_catalog_from_dict` / `parse_activity_reference_payload`의 `activation_override`를 **제거**했다. Activity 계열 Production API에는 더 이상 승인 우회 입력이 없다.
  - 같은 Preflight에서 동일 패턴이 **기존 코드에 남아 있음**을 확인했다.

    | 대상 | 파라미터 |
    |---|---|
    | `JsonThemeReferenceRepository.__init__` · `load_catalog_from_dict` · `parse_theme_reference_payload` | `activation_override` |
    | `JsonMonthlyTemplateRepository.__init__` · `load_template_from_dict` · `parse_monthly_template_payload` | `approval_override` |
    | `JsonSafetyLegalRuleRepository.__init__` · `load_safety_legal_rule_from_dict` · `parse_safety_legal_rule_payload` | `approval_override` |

  - 세 대상은 Yearly Core / Monthly M1 Core의 frozen 영역이며 Golden Set(`gate_unapproved_theme_reference` 등)과 다수 테스트가 이 입력을 사용한다. M2-B 범위에서 수정하면 frozen 경계와 회귀 방어선을 동시에 건드리게 되므로 변경하지 않았다.
  - CLAUDE.md §8은 `PENDING_HUMAN_REVIEW` Catalog를 운영 활성으로 취급하지 않도록 요구한다. 승인 상태는 `review.domain_owner_approval`에서만 파생되어야 하며 요청자가 지정할 수 없다.
- **분류:** NON-BLOCKING
- **영향 범위:** Theme Reference / Monthly Template / Safety Legal Rule Adapter, 승인 Gate의 무결성, 테스트 fixture 구성 방식, 향후 HTTP·DI 경계
- **현재 위험 평가:** P0 범위에서는 Composition Root가 이 값을 넘기지 않으므로 실제 우회는 발생하지 않는다. 위험은 **Production Integration 이후** 외부 caller나 설정 경로가 이 keyword에 도달할 수 있게 되는 시점에 생긴다.
- **후속 작업으로 확정된 방향:** Production Integration 전에 별도 **Security / Contract Hygiene** 작업으로 재검토한다. Activity 계열에 적용한 것과 같은 방식 — Production API에서 우회 입력을 제거하고, 승인 상태가 필요한 테스트는 (A) 승인된 Domain fixture를 직접 구성하거나 (B) 승인된 JSON fixture를 임시 경로에 만들어 실제 Adapter로 로드하는 방식으로 전환 — 을 기본안으로 둔다. 실제 승인 데이터 파일은 수정하지 않는다.
- **비결정 범위:** 세 Adapter를 동시에 정리할지 단계적으로 할지, Golden Set의 미승인 차단 case를 어떤 fixture 형태로 재구성할지, 테스트 전용 진입점을 별도 모듈로 분리할지는 해당 작업에서 결정한다.
- **결정 시점:** Production Integration(HTTP Adapter 또는 실제 배포 Composition Root) 작성 전
- **상태:** OPEN

### OD-N12 (= OD-ACTIVITY-INGESTION-01) — 재현 가능한 Activity Reference ingestion pipeline (기술부채)

- **ID:** OD-N12 · 별칭 `OD-ACTIVITY-INGESTION-01`
- **결정 내용:** `Source PDF → observation → normalization → Activity Reference` 전 구간을 재현하는 Production-grade ingestion pipeline을 만들 것인지, 만든다면 어느 경계에 둘 것인지 확정한다.
- **현재 근거:**
  - 2026-09-13 Setting Provenance Audit(`docs/analysis/activity-v0-2-1-setting-audit.md` §2)에서 **저장소에 그 pipeline이 존재하지 않음**을 확인했다. `grep -rln '"setting"' --include=*.py analysis src` 결과 `setting` 값을 **계산**하는 코드는 없고 스키마 검증과 감사 도구만 있다.
  - 즉 v0.2.0 / v0.2.1의 Activity·Evidence는 사람이 수행한 전사 작업의 산출물이며, 그 작업을 파일 하나에서 다시 돌려 재생성할 수 없다. 재현 가능한 근거는 Artifact 자신이 기록한 `setting_semantics` · `evidence_semantics` · `exclusion_policy`와 근거별 `observed_section` / `observed_source_label`뿐이다.
  - Monthly Quality Patch 1에서 만든 `analysis/tools/cell_extract.py` 계열 추출 모듈은 **문제 재현과 감사에는 유효**하다(조각 Activity의 근본 원인 확정, setting 전수 재검증). 그러나 전체 Catalog를 생성하지 않고, 미복원 사례를 남기며, 프로젝트 dependency가 아닌 로컬 격리 도구다.
  - **따라서 이 분석 모듈을 Production ingestion pipeline이라고 선언하지 않는다.**
- **분류:** NON-BLOCKING
- **영향 범위:** Activity Reference의 재생성 가능성, Corpus 증분 수집 시의 비용, v0.3 이후 버전 발행 방식, Reference 변경의 감사 추적
- **현재 위험 평가:** P0 범위에서는 승인된 Artifact가 Source of Truth이고 version pin으로 재현성이 보장되므로 생성 경로 부재가 런타임 위험을 만들지 않는다. 위험은 **Corpus를 늘리거나 v0.3을 발행할 때** 같은 수기 작업을 반복해야 한다는 비용과, 전사 판단의 재검증 가능성이 Artifact 기록에만 의존한다는 점이다.
- **비결정 범위:** pipeline을 만들 것인지 자체, 만든다면 `analysis/` 도구를 승격할지 별도 모듈로 작성할지, 사람 검증 단계를 어디에 둘지, 산출물 diff를 어떻게 승인 Gate에 연결할지.
- **결정 시점:** ~~Activity Reference v0.3 착수 전 또는 Corpus 증분 수집 착수 전~~
- **상태:** **CLOSED — 2026-09-13 (Monthly LLM Planner L1 완료)**
- **해소 방식:** Activity Catalog 재구축이 아니라 **Evidence Ingestion Pipeline 제품화**로 닫았다.

  ```text
  PDF → 셀 기하 추출 → 면 단위 연령/Section/Setting 판정 → strict EvidenceRecord
      → extraction quality → grounding eligibility(파생) → 재현 가능한 Evidence Store
  ```

  | 완료조건 | 결과 |
  |---|---|
  | cell geometry productionized | `src/ssuksak/ingestion/cells.py` + `adapters/pymupdf_source_reader.py` (Port 뒤 격리) |
  | deterministic ingestion | 같은 입력 → 같은 `content_sha256` (2회 재현 확인, 테스트 고정) |
  | strict EvidenceRecord | `ingestion/models.py` pydantic `extra="forbid"` + frozen + 파생값 |
  | outdoor loss < 2% | **16% → 0.00%** (286행 중 0건 손실) |
  | fragment regression | `건너기` · `장화 신고 물웅덩이` · `우리집에 왜 왔니?` · `놀이를 해요.` 단독 VALID **0건** |
  | indoor alternative regression | 누출 **0건**, false outdoor **0건** |
  | full Corpus reproducible ingestion | 349 파일 · 664면 · 12,367 record |

- **닫지 않은 부분:** Activity Reference **v0.2.2 승격 범위**는 그대로 OPEN이다.
  Evidence Store는 Corpus 관찰값이고 canonical Catalog가 아니다(§18 Versioning).
  승격은 사람 승인 경로로 별도 진행한다.
- **보고서:** `docs/analysis/monthly-llm-planner-l1-evidence-ingestion.md`


### OD-N16 — Evidence Ingestion의 PDF 라이브러리 의존성 (신규)

- **ID:** OD-N16
- **분류:** NON-BLOCKING
- **상태:** OPEN
- **쟁점:** `pymupdf`를 `pyproject.toml`의 프로젝트 의존성으로 넣을 것인가.
- **현재 처리 (L1):** 넣지 않았다. `ingestion.ports.SourceDocumentReader` Protocol 뒤에
  격리하고 `adapters/pymupdf_source_reader.py`가 **함수 안에서 lazy import**한다.
  - Planning Core 런타임은 PDF를 읽지 않는다. Evidence Store **빌드 시점**에만 필요하다.
  - 그래서 `pyproject.toml`을 건드리지 않았고 전체 테스트가 PDF 라이브러리 없이 돈다
    (Fake Reader 주입, CLAUDE.md §17 Port 우선 원칙).
  - 빌드는 격리 설치 경로를 `PYTHONPATH`로 지정해 실행한다.
- **결정해야 할 것:**
  1. Evidence Store 재빌드를 CI에 넣을 것인가. 넣는다면 의존성이 필요하다.
  2. 넣는다면 일반 dependency인가 optional extra(`[project.optional-dependencies]`)인가.
  3. 라이선스(PyMuPDF는 AGPL / 상용 듀얼) 검토가 선행되어야 한다.
- **현재 위험:** 낮다. Artifact가 저장소에 있으므로 재빌드 없이도 L2~L6이 진행된다.
- **결정 시점:** Evidence Store 재빌드를 자동화할 때, 또는 Production 배포 구성 확정 시
- **이번 L1에서 닫지 않는다.**

---

### OD-N18 — Week Experience를 담을 Section (Template A v0.2.0)

- **ID:** OD-N18
- **분류:** NON-BLOCKING (단 Week Experience 저장을 차단한다)
- **상태:** **`CLOSED` — 2026-09-13 Human Decision**
- **문제:** L4 Proposal은 주차마다 `experience`(그 주의 중심 경험)를 돌려주는데
  **승인 Monthly Template A에 그것을 담을 활성 CONTENT Section이 없다.**

  ```text
  week_axis     role=AXIS      → MonthlySection이 Item 보유를 금지한다
                                 ("AXIS Section은 Item을 갖지 않는다")
                                 Resolver도 cell_count_for() = 0을 준다
  focus         role=CONTENT   → 의미상 맞는 자리(관측 label `소주제`·`예상 놀이`)
                display=WEEKLY_CELLS
                activated=false   activation_basis=OPTIONAL_DEFAULT_INACTIVE
  ```

  활성 CONTENT Section은 `theme` · `outdoor_play` · `safety_education` 셋뿐이다.
- **Provenance 자체는 표현 가능하다.** 지시문이 우려한 부분은 해결된다 —
  `GenerationMethodDetail(RULE_LLM, rule_id, rule_version)` + `evidence=[]`이면
  "LLM이 구성했고 특정 Evidence record를 인용하지 않는다"는 뜻이 되어 과장이 없다.
  Domain은 FILLED Cell에 Evidence를 요구하지 않는다(`theme`만 예외).
  **Activity의 `grounding_refs`를 experience의 Evidence로 복사하지 않았고,
  근거 없이 `INSTITUTION_SAMPLE`을 주장하지도 않았다.**
- **막힌 것은 Section 배치다.** `focus`를 활성화하면
  1. Template A의 승인 내용을 바꾸게 되고(`normative_status` 있는 Artifact),
  2. RULE_ONLY 경로에도 주차마다 빈 `focus` Cell이 생겨 기존 Golden 결과가 바뀐다.
  둘 다 구현자가 임의로 결정할 사안이 아니다.
- **L6에서의 처리:** `week.experience`를 **Plan Item으로 저장하지 않았다.**
  가짜 Section을 만들지도, `week_axis`에 억지로 넣지도 않았다. Proposal 자체는
  검증을 통과했고 주차 수는 `MonthlyGenerationRun.llm_item_count`에 남는다.
- **결정해야 할 것:**
  1. `focus`를 활성화할 것인가(= Template A 개정). 그러면 RULE_ONLY에서 그 Cell을
     어떻게 둘 것인가(빈 Cell 허용 / Rule로도 채움).
  2. 아니면 Week Experience 전용 Section을 새로 정의할 것인가.
  3. 아니면 P0에서 Week Experience를 저장하지 않고 Planner 내부 신호로만 쓸 것인가.
- **승인 결정 (2026-09-13):**
  1. **기존 Template A v0.1.0을 수정하지 않는다.** RULE_ONLY 호환용으로 그대로
     보존하며 Artifact SHA `1f35322dd52f832b…`가 바뀌지 않는다.
  2. **새 version `monthly-template-a-v0.2.0`을 추가한다**
     (`data/templates/monthly_template_a_v0_2_0.json`). `focus` 하나만
     `activated: true`로 바꾸고 그 밖의 Section 정의는 v0.1.0과 동일하다.
     두 version이 **공존한다** — v0.2.0이 v0.1.0을 대체하지 않는다.
  3. `week_axis`는 계속 `role=AXIS`이며 주차 번호·날짜 축 역할만 한다.
     **AXIS 의미를 바꾸지 않았다.**
  4. `goals` · `habits` · `emergency_response` · `drill` · `indoor_alternative` ·
     `special_program` · `event_schedule`은 **함께 활성화하지 않았다.**
- **Mapping:** `proposal.weeks[i].experience` → `focus[week_id]`.
  Week ID의 Source of Truth는 계속 canonical WeekPeriod이며 Proposal의
  `week_id`는 검증 anchor다.
- **Provenance:** `RULE_LLM` / `monthly.llm.evidence_grounded_planner` / `v1` /
  `week_order_basis = PLANNER_COMPOSED` / **`evidence = []`**.
  빈 Evidence는 "근거가 없다"가 아니라 **"특정 EvidenceRecord를 이 문장의 직접
  근거로 주장하지 않는다"**는 뜻이다. Activity의 `grounding_refs`를 복사하지
  않았고, 근거 없이 `INSTITUTION_SAMPLE`을 부여하지도, `SOURCE_OBSERVED`를
  쓰지도 않았다(Corpus `week_position` 보유 0건).
- **Template 선택:** Use Case가 Mode를 보고 Template을 몰래 바꾸지 않는다.
  호출자가 `template_ref`로 명시한다. `LLM_PLANNER`인데 Template에 `focus`가
  없으면 **조용히 experience를 버리지 않고**
  `llm_planner_mode_requires_a_week_experience_section`으로 실패한다.
- **RULE_ONLY 영향 없음:** v0.1.0으로 생성하면 `focus` Section 자체가 없다.
  v0.2.0을 RULE_ONLY로 써도 실패하지 않으며 `focus`는 `EMPTY_VALID`가 된다.
  Golden을 수정하지 않았다.
- **남은 것:** `focus`가 Generated Cell이 되었으므로 **L7에서 Regenerate 대상
  범위를 다시 판단해야 한다** (A. `outdoor_play`만 / B. `focus`와
  `outdoor_play` 각각). 이번 단계에서 임의 구현하지 않았다.

---

### OD-N17 — Monthly Context Packet의 Age Evidence Strength 단계 수 (신규)

- **ID:** OD-N17
- **분류:** NON-BLOCKING
- **상태:** `OPEN` — 2026-09-13 L3에서 발견
- **문제:** L3 지시문 §8·§9는 Context용 enum을 `LOW | MODERATE | STRONG` 3단계로
  제시했다. 그런데 이미 확정된 판정 기준
  (`docs/analysis/new-reference-evidence-impact-2026-09.md` §4.1)은
  `MODERATE` 아래에 **서로 다른 두 단계**를 갖는다.

  ```text
  STRONG      단일연령 독립기관 >= 3
  MODERATE    단일연령 독립기관 == 2, 또는 1이면서 그 면에 바깥놀이 행이 있음
  WEAK        단일연령 독립기관 == 1 (바깥놀이 행 없음), 또는 혼합 근거 기관 >= 3
  VERY_WEAK   그 외
  ```

- **L3에서의 처리:** **확정 기준 4단계를 그대로 구현했다.** 두 단계를 `LOW`로
  합치려면 "단일연령 기관 1곳"과 "연령 근거 전무"를 같은 값으로 취급해야 하고,
  그것은 확정 기준을 재해석하는 새 임의 기준이다. 지시문 §9가
  "기존 기준을 Context용 enum으로 그대로 옮길 수 없다면 Open Decision으로 남기고
  임의 확정하지 않는다"고 했으므로 합치지 않았다.
- **결정해야 할 것:**
  1. Context enum을 3단계로 축약할 것인가.
  2. 축약한다면 `WEAK` / `VERY_WEAK` 구분을 버려도 되는가. 두 값은 UI에서
     "근거가 적다"와 "근거가 없다"로 다르게 안내될 수 있다.
- **관련 사실(L3 실측):** 등급은 그 달 Corpus 전체를 보지만 Packet에는 Top-K만
  담기므로 둘이 어긋날 수 있다. 2027-02 만5세는 `STRONG`(단3)인데 Packet 안의
  만5세 단일연령 근거는 1건이다. L3는 이를 `age_context.single_age_grounding_count`로
  **사실로 노출**했고 새 임계값은 만들지 않았다.
- **현재 위험:** 낮다. 4단계로도 L4 Planner는 막히지 않는다.
- **결정 시점:** L4 Prompt가 연령 강도를 자연어로 표현하는 방식을 정할 때
- **이번 L3에서 닫지 않는다.**

---

### OD-N13 — Monthly LLM Planner의 Evidence Source Type (`INSTITUTION_SAMPLE`)

- **ID:** OD-N13
- **분류:** NON-BLOCKING (단 Monthly LLM Planner L1 착수를 차단했음)
- **상태:** **CLOSED — 2026-09-13 Human Decision**
- **승인 결정:**
  - `EvidenceSourceType`에 **`INSTITUTION_SAMPLE`**을 추가한다.
  - 의미: 실제 기관 계획안 / 놀이자료 / Institution Corpus에서 관찰된 Source를
    Plan Item Grounding 근거로 참조할 때 쓴다.
  - `ACTIVITY_REFERENCE`를 대체하지 않는다. 승인 Catalog에서 고른 값은 계속
    `ACTIVITY_REFERENCE`다.
- **축 분리 확정:**

  ```text
  EvidenceSourceType   = 무엇을 근거로 했는가
  GenerationMethod     = 어떤 방식으로 값이 만들어졌는가
  activity_origin      = Activity 값이 Reference인가 Corpus인가 합성인가
  ```

  세 축은 독립이므로 다음 조합이 정상이다.

  ```text
  EvidenceSourceType : INSTITUTION_SAMPLE
  GenerationMethod   : RULE_LLM
  activity_origin    : LLM_SYNTHESIZED
  ```

  **LLM 생성 여부를 EvidenceSourceType으로 표현하지 않는다.**
  `LLM_SYNTHESIZED`는 Evidence Source Type이 아니다.
- **origin별 Evidence 매핑 (확정):**

  | activity_origin | 필수 필드 | EvidenceSource |
  |---|---|---|
  | `REFERENCE` | `reference_activity_id` | `ACTIVITY_REFERENCE` |
  | `CORPUS_EVIDENCE` | `grounding_source_ids` | grounding에 쓰인 실제 Source Type (`INSTITUTION_SAMPLE` 등). **reuse policy가 Product Output 직접 사용을 명시 허용한 Record에 한정** |
  | `LLM_SYNTHESIZED` | `grounding_source_ids` | grounding에 쓰인 실제 Source Type들. `GenerationMethod = RULE_LLM` |
- **근거:** `docs/analysis/monthly-llm-planner-vnext-design.md` §11·§16.
  대안 (a) Evidence 미기록은 CLAUDE.md §14 "필요한 Provenance 누락" 검증에 걸리고,
  (b) `EXTERNAL_CONTEXT` 재사용은 의미가 다르다(Trend/Weather 계열 Optional Context용).
- **파급:** `CLAUDE.md` §13.1과 `docs/screen-spec.md` §6.1의 허용 목록을 이번 승인 근거로
  갱신했다. **Domain Enum(`provenance.py`) 반영과
  `tests/unit/test_provenance_axes.py::test_evidence_source_types_match_screen_spec_list`
  갱신은 구현 단계(L4~L6)에서 한다.** L0에서는 Contract만 확정한다.

---

### OD-N14 — `week_order_basis` (주차 순서의 Provenance)

- **ID:** OD-N14
- **분류:** NON-BLOCKING (단 Monthly LLM Planner L1 착수를 차단했음)
- **상태:** **CLOSED — 2026-09-13 Human Decision**
- **승인 결정:** 다음 세 값을 도입한다.

  | 값 | 의미 | 조건 |
  |---|---|---|
  | `SOURCE_OBSERVED` | 원문 Source가 실제 Week Position을 명시한 경우 | Evidence에 `week_position != None`이 **실제로** 존재해야 한다. **추정 금지** |
  | `PLANNER_COMPOSED` | Evidence는 "그 달에 어떤 경험이 등장하는가"만 Grounding하고, W1→W5 순서는 Planner가 구성한 경우 | 새 LLM Monthly Generate의 **기본값** |
  | `TEACHER_ORDERED` | 교사가 Week 순서를 직접 수정·재배치한 경우 | Teacher Edit가 Planner보다 우선한다 |

- **현재 실측:** Evidence Store Prototype 3,603 record 중 `week_position` 보유 **0건**이다.
  따라서 `SOURCE_OBSERVED`는 현재 Runtime 결과에서 사실상 사용되지 않는다.
- **UI / Export 정책 (확정):**
  - Main Monthly Plan 화면에서 국가 기준·공식 순서처럼 보여주지 않는다.
  - **금지 표현:** `공식 권장 1주차` · `누리과정 기준 순서` · `표준 주차`
  - **허용 표현:** `AI가 구성한 주차 흐름` · `교사가 조정한 주차 흐름` ·
    `Source에서 확인된 주차`
  - Main Cell에 배지를 강제하지 않는다. Audit / Detail 영역에서 추적 가능하게 한다.
  - Export에서도 `PLANNER_COMPOSED`를 공식·법정 순서처럼 표현하지 않는다.
- **근거:** Week Experience 문서가 33 → 88로 늘었는데도 position별 concept 분포가 평평하다
  (`docs/analysis/new-reference-evidence-impact-2026-09.md` §5.3 Q7-4). 순서 근거가 없는데
  결과에는 순서가 있으므로, 그 간극을 Provenance로 명시한다.
  CLAUDE.md §5.3.3의 "월 배정을 법정 요건처럼 표시하지 않는다"와 같은 성격의 제약이다.

---

### OD-N15 — `generation_mode` (`RULE_ONLY` / `LLM_PLANNER`)

- **ID:** OD-N15
- **분류:** NON-BLOCKING (단 Monthly LLM Planner L1 착수를 차단했음)
- **상태:** **CLOSED — 2026-09-13 Human Decision**
- **승인 결정:** 두 Mode를 도입한다.

  | Mode | 내용 | 목적 |
  |---|---|---|
  | `RULE_ONLY` | 현재 Monthly v1 경로 (Rule v2 선택) | 기존 Golden 보존 · 회귀 테스트 · 호환성 · 명시적 fallback/debug |
  | `LLM_PLANNER` | Evidence Retrieval → Context Packet → GPT-4.1 mini → Validator → DRAFT | 새 Product 목표 경로. 최종 Production / Demo 활성화 목표 |

- **Silent Fallback 금지 (확정):**

  ```text
  generation_mode = LLM_PLANNER  +  LLM 호출 실패
      → Generate 실패

  금지: LLM 실패 → 자동으로 RULE_ONLY 생성
  ```

  `RULE_ONLY`는 **명시적으로 선택되었을 때만** 사용한다.
  이는 CLAUDE.md §7의 Optional Dependency Fallback과 다른 경로다. Trend/Weather 실패는
  Core가 성공해야 하지만, Planner LLM은 필수 단계다.
- **Migration / Compatibility 정책 (확정):**
  - 구현 중 기존 Test와 Golden을 깨지 않기 위해 기존 경로를 **명시적 `RULE_ONLY`**로 보존한다.
  - Production LLM Planner가 L1~L9 · Live Smoke · Demo · Golden · 전체 Regression을
    통과한 뒤에만 Production / Demo Composition이 **명시적으로** `LLM_PLANNER`를 선택한다.
  - **Use Case 내부에서 조용히 Mode를 바꾸지 않는다.**

---

### 2026-09-13 L0에서 함께 확정한 파생 Contract

OD-N13~N15에 딸린 세부 규약이다. 별도 OD로 등록하지 않고 여기에 기록한다.

#### (1) Evidence Reuse Policy

`docs/analysis/monthly-llm-planner-vnext-design.md` §5.2의 `reuse_policy`를 다음으로 확정한다.

```text
CONTEXT_ONLY              P0 기본값. Grounding Context로만 쓴다.
                          원문 Activity 문자열을 Product 값으로 그대로 복사하지 않는다.
PRODUCT_OUTPUT_ALLOWED    Product Output 직접 사용이 명시적으로 허용된 Record.
                          현재 P0에 해당 Record는 없다.
```

- Enum 이름 제안: **`EvidenceReusePolicy`** — 기존 `EmptyValuePolicy`(`monthly_template.py`)와
  같은 `<Noun>Policy` 명명, 값은 저장소 전역 규약대로 `SCREAMING_SNAKE_CASE`다.
- 값 이름은 `OUTPUT_ALLOWED`보다 `PRODUCT_OUTPUT_ALLOWED`를 권장한다. `OUTPUT`만으로는
  LLM 출력인지 내보내기 출력인지 모호하다. 이 한 글자 차이는 제안이며 최종 명명은
  L1 구현 시 확정한다.
- **귀결:** `CONTEXT_ONLY` Record를 근거로 만든 Activity의 origin은 **`LLM_SYNTHESIZED`**다.
  `CORPUS_EVIDENCE` origin은 `PRODUCT_OUTPUT_ALLOWED` Record에만 쓸 수 있다.
  현재 P0에는 그런 Record가 없으므로 **`CORPUS_EVIDENCE`는 사실상 비활성**이며,
  임의로 direct reuse를 허용하지 않는다.

#### (2) Evidence 추출 품질 Guardrail (L1 완료조건에 포함)

Prototype 실측에서 줄 기반 추출은 바깥놀이 행의 **41/253 ≈ 16%** 내용을 잃었다.
따라서 EvidenceRecord는 추출 품질 상태를 표현해야 한다.

```text
VALID          셀 기하 추출이 온전한 항목을 복원했다
NEEDS_REVIEW   잘림·중복 의심 등으로 사람 확인이 필요하다
INVALID        fragment · indoor-alternative leakage · section label echo 등
```

- Enum 이름 제안: **`EvidenceExtractionQuality`** — 기존 `ActivityDisplayQuality`와 같은 명명.
- **`grounding_eligible`는 저장 필드가 아니라 파생값이다.**

  ```text
  grounding_eligible == (extraction_quality == VALID)
  ```

  CLAUDE.md §8의 `runtime_active == (domain_owner_approval == HUMAN_APPROVED)`와 같은
  파생 원칙을 따른다. 독립 writable 스위치를 만들지 않는다.
- **Runtime Retrieval은 `grounding_eligible`한 Record만 Planner Context에 넣는다.**
  "깨진 문자열도 Context니까 넣어도 된다"는 정책을 쓰지 않는다.
- **L1 완료조건 (기존 설계 유지):**

  ```text
  셀 기하 추출 기반
  바깥놀이 행 내용 손실 < 2%
  fragment regression PASS
  wrap regression PASS
  indoor alternative regression PASS
  ```

#### (3) Monthly LLM 결과의 기본 Provenance

```text
GenerationMethod : RULE_LLM
rule_id          : monthly.llm.evidence_grounded_planner
rule_version     : v1
planner_model    : config에서 읽은 실제 model id (코드에 하드코딩하지 않는다)
prompt_version   : 실제 Production Prompt version
week_order_basis : PLANNER_COMPOSED
```

`GenerationMethod`에 새 값을 만들지 않는다. `RULE_LLM`을 그대로 쓴다 — Rule이 후보와
제약을 정하고 LLM이 구성하는 구조이므로 CLAUDE.md §13.2의 정의에 그대로 들어맞는다.

---

## 7. Template A 실측으로 확정된 P0 기준

아래 표는 실측으로 확정된 P0 **Guardrail**을 정리한다. 각 Guardrail 자체는 더 이상 Open Decision이 아니지만, 표에서 별도 OD를 가리키는 세부 의미·기본값·계산 정책은 해당 OD 상태를 따른다. Open Decision ID는 `OD-Y / OD-M / OD-W / OD-N` 체계만 사용한다.

| 확정 기준 | 현재 근거 | 영향 범위 | 적용 원칙 | 상태 |
|---|---|---|---|---|
| 월간 8행 고정 구조 금지 | template-a-validation §1·§8 | Monthly Schema/Renderer | 의미 기반 Section 정의 사용 | RESOLVED_FOR_P0 |
| 월 주차 수는 dynamic weeks | 2026-09-11 재측정: 9월 5주 다수, 3월 4주, 주차 축 없는 기관 1곳 | Calendar/UI 열 | 가변 WeekPeriod 목록 사용; 계산 세부는 OD-M02 `RESOLVED_FOR_P0` | RESOLVED_FOR_P0 |
| Section별 weekly/monthly merged 표시 지원 | 바깥놀이·안전교육이 두 방식으로 관찰. 제3의 inline 태그 유형도 관찰(아이사랑) | Renderer/Mapping | display_mode를 Section 속성으로 둠. **전국 공통 기본값 없음**, 값 집합 확장 가능 — OD-M01 `RESOLVED_FOR_P0` | RESOLVED_FOR_P0 |
| goals와 habits는 Optional | 각 2/3 관찰 | Monthly Template/Validation | required로 승격하지 않음 | RESOLVED_FOR_P0 |
| 성품인사는 월간 기본행에서 제거 | 기본 0/3, 보조에서도 미관찰 | Monthly Template | Profile에는 선택 저장 가능; 출력은 명시적으로 활성화된 Custom Section Mapping만 허용 | RESOLVED_FOR_P0 |
| `subtheme`/`expected_play` 자동 병합 금지 | 같은 표의 두 독립 행으로 병존한 사례 없음. 동일 기관에서 연령별로 같은 구조 슬롯을 다른 `source_label`로 표현한 사례 관찰 | Mapping/DTO | 자동 병합 금지 확정. 중립 슬롯 + 라벨 보존은 OD-M03 `RESOLVED_FOR_P0`. 최종 의미 관계는 후속 | RESOLVED_FOR_P0 |
| 원본 Label을 보존하며 내부 의미에 Mapping | 동일 의미의 다양한 실측 Label | Import/Renderer/Provenance | source_label과 semantic_key 분리 | RESOLVED_FOR_P0 |
| 안전교육의 고정 행 번호 금지 | 위치·병합·비상대응 구조가 기관별 상이 | Monthly Template | 데이터와 표시 위치를 분리 | RESOLVED_FOR_P0 |

---

## 8. 그 밖에 종료된 선행 쟁점

| 확정 기준 | 현재 근거 | 영향 범위 | 적용 원칙 | 상태 |
|---|---|---|---|---|
| 학년도는 3월~다음 해 2월 | screen-spec §11.2, 연간 실측 | Yearly 기간/정렬 | school_year 의미를 Contract에 명시 | RESOLVED_FOR_P0 |
| Plan 단계와 Gate는 YEARLY→MONTHLY→WEEKLY | CLAUDE §2, SOT §6, screen-spec §1 | Parent/Gate | 표준 경로 유지 | RESOLVED_FOR_P0 |
| Logical Provenance는 Evidence Source / Generation Method / Audit History 3축 | CLAUDE §11, SOT §22, screen-spec §6·§9 | 출처/변경 이력 | 세 축을 별도로 유지 | RESOLVED_FOR_P0 |
| 안전교육 법정 제약과 월 배치 정책 분리 | CLAUDE §4 | Rule/표시 문구 | 둘을 별도 Version 데이터로 관리 | RESOLVED_FOR_P0 |
| P0 CONFIRMED는 읽기 중심·편집 차단 | screen-spec §8.2 | Edit/Confirm UI | 장기 Version 정책은 OD-N06 | RESOLVED_FOR_P0 |
| screen-spec 부재 문제 해소 | docs/screen-spec.md 존재 | UI Contract | 이후 계약은 docs/contracts.md로 분리 | RESOLVED_FOR_P0 |

---

## 9. Source of Truth 동기화 완료

아래 문서 정합성 작업은 2026-09-10 기준으로 완료했다.

- [x] 세 문서의 적용 우선순위를 동일한 9단계 canonical chain으로 통일
- [x] docs/demo-source-of-truth.md §18~§20 — 고정 8행 금지, 기본 지원 의미, Optional Section, dynamic weeks, Section별 display_mode 반영
- [x] docs/screen-spec.md §2.3·§12.3 — 성품인사를 Optional Profile Context로 유지하되 월간 기본행에서 제거
- [x] docs/demo-source-of-truth.md §22와 docs/screen-spec.md §6·§9 — Evidence Source / Generation Method / Audit History 3축으로 통일
- [x] docs/demo-source-of-truth.md §34와 docs/screen-spec.md §18 — Open Decision을 `OD-Y / OD-M / OD-W / OD-N` 체계로 대체
- [x] OD-Y01~OD-Y03 — P0 최종 결정문 승인 및 `RESOLVED_FOR_P0` 처리
- [x] 지원 Yearly Import만 P0에 포함하고 범용 자동 파싱은 제외하며 남은 Contract를 OD-N09로 등록

이 완료 상태는 문서 결정과 동기화를 뜻하며 구현 착수를 뜻하지 않는다.

---

## 10. 결정 완료 체크

GenerateYearlyPlan Slice 착수 전:

- [x] OD-Y01 승인 — 2026-09-09, `RESOLVED_FOR_P0`
- [x] OD-Y02 승인 — 2026-09-09, `RESOLVED_FOR_P0`
- [x] OD-Y03 승인 — 2026-09-09, `RESOLVED_FOR_P0`

GenerateMonthlyPlan 착수 전:

- [x] OD-M01 승인 — 2026-09-11, `RESOLVED_FOR_P0`
- [x] OD-M02 승인 — 2026-09-11, `RESOLVED_FOR_P0`
- [x] OD-M03 승인 — 2026-09-11, `RESOLVED_FOR_P0`
- [x] OD-M04 승인 — 2026-09-11, `RESOLVED_FOR_P0`
- [x] `data/templates/monthly_template_a.json` Human Review — 2026-09-11T10:25:01+09:00, `HUMAN_APPROVED`, `reviewer_ai_lead_001`
- [x] `data/rules/safety_education_legal_v1.json` Human Review — 2026-09-11T10:25:01+09:00, `HUMAN_APPROVED`, `reviewer_ai_lead_001`

**M0 완료. Monthly M1 설계에 착수할 수 있다.**

M1 설계 중에 다루는 항목 (M1 착수를 막지 않음):

- [ ] OD-M04의 `법정 요건 미검증 / source required` 상태를 DTO·GenerationRun에서 표현하는 방식 — M1 설계 시 제안·승인. 임의 Enum을 만들지 않는다
- [ ] Template A Optional 5개(`emergency_response` · `drill` · `indoor_alternative` · `special_program` · `event_schedule`)의 `display_mode` — 전부 default inactive이므로 **M1 non-blocking**. 추가 표본 재측정 또는 사람 판단으로 후속 확정

GenerateMonthlyPlan Activity 생성(M2) 착수 전:

- [ ] OD-N03 승인 — Activity Reference 미작성. **M2 blocker이며 M1 blocker가 아니다**

GenerateWeeklyPlan 착수 전:

- [ ] OD-W01 승인
- [ ] OD-W02 승인

Monthly LLM Planner (L1 Evidence Ingestion) 착수 전:

- [x] OD-N13 승인 — 2026-09-13, `CLOSED` (`INSTITUTION_SAMPLE` 추가, 3축 분리 확정)
- [x] OD-N14 승인 — 2026-09-13, `CLOSED` (`week_order_basis` 3값 + UI/Export 정책)
- [x] OD-N15 승인 — 2026-09-13, `CLOSED` (`generation_mode` 2값 + silent fallback 금지)

**L0 Contract 완료. L1 Evidence Ingestion에 착수할 수 있다.**

Monthly LLM Planner (L2 Evidence Retrieval) 착수 전:

- [x] L1 Evidence Ingestion 완료 — 2026-09-13, outdoor loss 16% → 0.00%
- [x] OD-N12(= OD-ACTIVITY-INGESTION-01) — 2026-09-13, `CLOSED`
- [ ] OD-N16 — PDF 라이브러리 의존성. L2를 막지 않는다

Monthly LLM Planner (L4 LLM Planner) 착수 전:

- [x] L2 Evidence Retrieval 완료 — 2026-09-13
- [x] L3 Monthly Context Packet 완료 — 2026-09-13
- [ ] OD-N17 — Age Strength 단계 수. L4를 막지 않는다
- [ ] Official Evidence Adapter — 첫 Smoke는 막지 않으나 "공식 자료 기반" 표시는 선행 필요

Monthly LLM Planner (L5 Proposal Validator) 착수 전:

- [x] L4 GPT-4.1 mini Planner 완료 — 2026-09-13, Live Smoke 3/3 성공
- [ ] **exact-copy 검출은 L5 필수 항목이다.** L4 Live Smoke에서 `LLM_SYNTHESIZED`
      2건이 모두 `CONTEXT_ONLY` 근거 문장의 글자 그대로 복사였다. Prompt 강화
      (v0.1.0 → v0.1.1)로는 사라지지 않고 다른 Case로 옮겨 갔다.
      근거: `docs/analysis/monthly-llm-planner-l4-gpt-planner.md` §14.3
- [x] **exact-copy 검출 완료 — 2026-09-13 L5.** `SYNTHESIZED_EXACT_SOURCE_COPY`가
      실측 결함 2건을 모두 REJECT한다. 근거:
      `docs/analysis/monthly-llm-planner-l5-proposal-validator.md` §6
- [ ] OD-N04 — `MAX_REPAIR_ATTEMPTS = 1`을 제품 정책으로 승격할지 사람 결정 필요

Monthly LLM Planner (L6 Generate Integration) 착수 전:

- [x] L5 Deterministic Proposal Validator 완료 — 2026-09-13
- [ ] OD-N04 — repair 루프를 실제로 돌려 본 뒤 `MAX_REPAIR_ATTEMPTS` 기본값 확정.
      L4 Live Smoke 3회에서 repair 발생 0회였으므로 아직 근거가 부족하다
- [ ] 동월 만3/4/5세 실제 품질 비교 — Demo 전 Quality Gate

Monthly LLM Planner (L7 Regenerate Integration) 착수 전:

- [x] L6 GenerateMonthlyPlan 통합 완료 — 2026-09-13, Application Live Smoke 성공
- [x] **OD-N18 — 2026-09-13 `CLOSED`.** Template A v0.2.0(`focus` 활성)을 추가하고
      `week.experience`를 `focus` Cell로 저장한다. v0.1.0은 불변
- [x] **Regenerate 대상 범위 — 2026-09-13 `B` 확정.** `focus`와 `outdoor_play`를
      각각 독립 Cell로 재생성한다. L7에서 구현·검증 완료

Monthly LLM Planner (L8 Demo Integration) 착수 전:

- [x] L7 Cell Regenerate 통합 완료 — 2026-09-13, Live Regenerate Smoke 2/2 성공
- [ ] **Evidence Store historical resolution이 없다.** Plan이 pin한 SHA와 현재
      Store가 다를 때 과거 Store를 해소할 경로가 없다. 지금은 Store가 하나뿐이라
      드러나지 않지만 **Evidence Store v0.2 발행 전에 결정해야 한다.**
      근거: `docs/analysis/monthly-llm-planner-l7-cell-regenerate.md` §17.1
- [ ] **동시 Teacher Edit 위험.** Domain에 revision·updated_at·optimistic
      concurrency가 없어 LLM 호출(1.7~2.1초) 중 다른 Edit가 들어오면 오래된
      Context 결과가 저장될 수 있다. L7에서 새 동시성 장치를 만들지 않고
      `plan_snapshot_fingerprint`로 관측만 가능하게 했다. 다중 사용자 편집 전 결정
- [ ] OD-N04 — L7에서도 repair 0회. call budget(정상 1 / worst 4)은 확정됐으나
      발생 빈도 표본이 여전히 얇다

Monthly LLM Planner (L9 Golden / Final Freeze) 착수 전:

- [x] L8 Demo Integration 완료 — 2026-09-14, 실제 Demo route로 2 Case 성공
- [ ] **Golden을 어느 경로 기준으로 고정할 것인가.** Demo 기본은 LLM_PLANNER지만
      LLM 결과는 결정론이 아니다. Rule-only(23ms·LLM 0회·완전 결정론)를 Golden
      기준으로 유지할지, LLM 경로에 별도 Contract Golden을 둘지 L9에서 결정한다.
      근거: `docs/analysis/monthly-llm-planner-l8-demo-integration.md` §7·§13.4
- [ ] **Production global default 전환 여부** — L8은 Demo Composition만 바꿨다
- [ ] OD-N04 — L6 실측: 정상 1회 · worst case 4회. 근거는 생겼으나 repair 실제
      발생 빈도 표본이 아직 얇다

Monthly LLM Planner v1 **FROZEN** (L9 Golden / Final Freeze) 이후:

- [x] L9 Golden / E2E / Final Freeze 완료 — 2026-09-14
- [x] **Golden 기준 결정 — 2026-09-14.** Rule-only Golden(`monthly_cases.json`,
      43 case, LLM 0회)을 **그대로 유지**하고, LLM 경로는 별도 Contract
      Golden(`monthly_llm_cases.json`, 16 case)을 둔다. 두 파일은 서로 다른 것을
      지킨다 — 저쪽은 Rule 경로의 기존 동작, 이쪽은 LLM 경로의 Application 계약.
      실제 GPT 문장을 expected로 굳히지 않는다.
      근거: `docs/analysis/monthly-llm-planner-l9-final-freeze.md` §3
- [x] **Production global default 전환 — 전환하지 않았다 (2026-09-14).**
      저장소에 Production Composition Root가 **존재하지 않는다.** Composition은
      `src/ssuksak/dev/wiring.py` · `dev/monthly_wiring.py`(dev harness)와
      `demo-planning/backend/composition.py`(Demo) 셋뿐이고 `pyproject.toml`에
      entry point가 없다. `GenerateMonthlyPlanCommand.generation_mode`의
      Application 기본값은 여전히 `RULE_ONLY`이며, `LLM_PLANNER`는 Demo
      Composition이 명시적으로 고른다. **"Production이 LLM으로 전환됐다"고
      말할 수 있는 대상 자체가 없다.**
      근거: 같은 보고서 §9
- [ ] **OD-N04 — 첫 live repair 관측 (2026-09-14). 여전히 열려 있다.**
      L9 Live Smoke 2회 중 1회에서 **L4 contract repair가 1회 발생**해 회복했다
      (telemetry record 4 vs 논리 호출 3). 직후 재실행에서는 3/3 repair=0.
      L4~L8 통틀어 repair 발생을 관측한 것은 이번이 처음이다. **L5 validation
      repair는 여전히 live 발생 0회다.** 표본 1건으로 기본값을 제품 정책으로
      승격하지 않는다. 근거: 같은 보고서 §11
- [ ] **OD-N17 — Age Strength 4단계. 구현 값으로 동결했을 뿐 닫지 않았다.**
      임계값은 `new-reference-evidence-impact-2026-09.md` §4.1을 그대로 쓴다
- [ ] **Evidence Store historical resolution** — L7에서 올린 항목이 그대로 열려
      있다. Store v0.2 발행 전에 결정해야 한다
- [ ] **동시 Teacher Edit** — L7에서 올린 항목이 그대로 열려 있다. L9는 새
      동시성 장치를 만들지 않았다
- [ ] **동월 만3/4/5세 실제 품질 비교** — 여전히 사람 관찰 항목이다. Golden이
      대신하지 않는다

Yearly Import/부분 생성 Slice 착수 전:

- [ ] OD-N09 승인

NON-BLOCKING 항목은 각 항목의 “결정 시점” 전까지 닫는다.
