# 주간계획안 계약 설계 (W1) — 제안

- 2026-10-20 · 하민 · 기준 develop `c73ef3c`
- **상태: 제안 · 승인 대기.** 이 문서의 계약은 모두 「제안」이다. 승인되기 전에는 W2 이후 구현을 시작하지 않는다.
  승인할 항목은 §15 「결정 요청」에 모았다.
- **코드 · Template JSON · migration · Golden 변경 없음.** 이 문서 하나만 추가한다.
- 근거 표기: `[결정]` PM · 하민이 이미 정했다 · `[선례]` 월간 · 연간에서 이미 정한 같은 종류의 규칙을 따른다 ·
  `[실측]` 원본 · 코드 · 데이터를 열어 확인했다 · `[제안]` 주간 때문에 이 문서가 처음 정한다 · `NOT_VERIFIED` 확인하지 못했다.

**정하는 방식.** 월간 · 연간에서 이미 정한 같은 종류의 문제는 **그 결정을 그대로 따른다**(`[선례]`).
주간에만 있는 문제(토요일 · 부모가 월간 · 주 단위 칸 구성)만 새로 정한다(`[제안]`).

**함께 읽을 문서.** 아래 둘은 2026-10-20 develop 에 머지됐다.

| 문서 | PR | 이 문서에서 쓰는 곳 |
|---|---|---|
| `docs/weekly-reference-survey.md` (W0 조사) | #173 | 샘플 구조 · 연간↔주간 매칭 · Evidence 현황 — 이하 「W0」 |
| ADR-030 ~ 038 (PM 결정 2026-10-19) | #182 | PM-03 · PM-04 · WQ-01 ~ 03 · 후속 결정(U-10) · ADR-032 · 033 · 038 |

### 리뷰 반영 (2026-10-20, Codex 교차 리뷰 · 하민 결정)

첫 판(`47b1d9c`) 대비 바뀐 곳: 스냅샷을 주간 전용 타입으로(§5-2) · 기본생활 키를 `basic_habit` 으로(§6) ·
실내놀이 · 대체놀이 · 대소집단의 근거를 「정확한 원문 행 이름」 분류로(§7) · 안전교육을 칸 상태가 아니라 배치 정보로 나눔(§8) ·
교사 입력 칸의 `MANUAL` 경계(§10-2) · 교사 값과 AI 출력의 검사 구분(§11) · 칸별 부모 스냅샷 보관 위치(§5-3) ·
행사 · 특별활동을 항상 켜진 교사 입력 칸으로(§6) · 평가제 연결을 범위 밖으로(§11-3).

재리뷰 반영(`877ad87` 대비): 법정 충족을 주장하는 문장 삭제(§8, ADR-033 §4) · 빈 칸 분기 우선(§8) ·
AI 출력 검사를 ADR-037 의 세 단계(검사 전 차단 · 저장을 막는 안전교육 근거 오류 · 안내)로 맞춤(§11-1) · 검사기 실행 실패 처리(§11-2).

재리뷰 2 반영(`5146cf8` 대비): 안전교육의 유효한 근거를 줄마다 정의 — 법정 배치(수정 없음)는 공식 근거, 나머지는 부모 칸 정확한 인용(§8) ·
근거 없는 사실은 저장 안 함으로 확정하고 탐지 범위만 미확인으로 남김(§11-1, ADR-032).

---

## 1. 이미 정해진 것

이 문서는 아래를 다시 고르지 않는다.

| 항목 | 결정 | 출처 |
|---|---|---|
| P0 범위 | 주간계획안을 P0 에 넣는다 | `[결정]` ADR-030 PM-04 |
| 생성 경로 | **월간 경유만.** 연간 `CONFIRMED` → 월간 → 월간 `CONFIRMED` → 주간. 월간을 안 쓰는 원(`uses_monthly = false`)은 P0 미지원 | `[결정]` ADR-030 PM-04 · api-spec §9 |
| 출력 형태 | **별도 주간계획안 하나.** 주간 · 일일 보육일지의 계획 칸은 P0 미지원. 의미 구조(WeeklyPlan)와 출력 위치는 나눈다 | `[결정]` ADR-030 「후속 결정」(U-10) |
| 요일 | 기본 월~금 5일. 원 설정으로 토요일을 켠다. 2주 단위는 지원하지 않는다 | `[결정]` ADR-030 WQ-01 |
| 요일별 값 | P0 는 주 단위 값만. 요일별 활동은 칸 하나 안 목록. `repeat_by = DAY` 는 후속 | `[결정]` ADR-030 WQ-02 |
| Template 승인 | 주간 Template 도 `PENDING_HUMAN_REVIEW` 로 발행 → 실제 담당자가 승인. 절차 승인이지 개별 Template 승인이 아니다 | `[결정]` ADR-030 WQ-03 · ADR-027 |
| 확정 취소 | 계획안(연간 · 월간 · 주간)에는 없다 | `[결정]` ADR-030 PM-03 |
| Rule / LLM | Rule 이 후보 · 근거 · 제약 범위를 정함 → LLM 이 그 안에서 값의 의미를 정함 → Rule 이 결과를 검사. **생성은 문서 단위 배치로 부른다(주간 한 주)** | `[결정]` ADR-032 (ADR-014 보충) |
| `generation.method` | `RULE_LLM` · `RULE_ONLY`(근거가 없어 비워 둔 칸 포함) · `IMPORTED` · `MANUAL`(사람이 처음부터 쓴 칸). 교사 수정은 바꾸지 않고 `TEACHER_EDITED` 이벤트 | `[결정]` ADR-032 §2 (PM-12) |
| 혼합연령 | DB 는 범위(`age_min` · `age_max`), Core 는 연령 집합. 반 하나 = 계획 하나 | `[결정]` ADR-038 |
| 날씨 | 주간계획안에도 예보를 쓰지 않는다 | `[결정]` ADR-008 |
| 월간 Core | 구조 동결. **월간 계약 · 타입 · Golden 을 바꾸지 않고** 주간을 붙인다 | `[결정]` ADR-033 |

## 2. 한 장 요약 `[제안]`

```text
WeeklyPlan  (classroom 하나 × WeekId 하나)
├─ week_id           "2026-09-W2"          ← 월간과 같은 주소. 새 번호 체계를 만들지 않는다
├─ week_period       월요일 시작 · 금요일 끝   ← 월간 WeekPeriod 그대로 (Core 동결)
├─ operating_days    MON..FRI | MON..SAT   ← 생성 시점 원 설정 스냅샷. 토요일은 여기에만
├─ target_ages       {3} | {4,5} …         ← ADR-038 연령 집합
├─ parent_lineage    월간 CONFIRMED plan    ← Context · 제약. 칸에 그대로 복사하지 않는다
├─ template_snapshot 주간 전용 스냅샷 (Profile 없음) · 주간 Template A v0.1.0 (PENDING_HUMAN_REVIEW)
└─ sections[]  (repeat_by = NONE 만 · Section 마다 칸 하나)
   ├─ theme · focus · goals · basic_habit            생성 — 월간 승인 근거 분류 재사용
   ├─ indoor_play · indoor_alternative · group_activity
   │                                                 생성 — 주간 근거 분류(새 판, 사람 승인 뒤). 승인 전엔 빈 칸
   ├─ outdoor_play                                   생성 — 승인 Activity Catalog
   ├─ safety_education                               부모 월간 칸의 배치 정보로 분기 (§8)
   └─ family_link · event_schedule · special_program 교사 입력 (생성 안 함, 처음 쓰면 MANUAL)
```

상태 · 동작은 월간과 같다: `DRAFT` → 편집 · 칸 재생성 → 확정(`CONFIRMED`, read-only).

## 3. 주와 요일 — U-11 데이터 계약

### 3-1. 주 주소는 월간 것을 그대로 쓴다 `[제안]`

- 주간계획안의 주소는 `WeekId`(`YYYY-MM-Wn`)다. 월간 `canonical_week_periods` 가 만든 그 달의 주차를 그대로 쓴다
  (`p0-planning/src/ssuksak/planning/rules/monthly_week_periods.py`).
- **주간 쪽에서 주차를 다시 계산하지 않는다.** 부모 월간계획안의 `week_periods` 에 있는 `WeekId` 만 받는다.
  같은 날짜가 두 달에 걸려도 주인은 하나다 — 월간 규칙이 이미 한 달에 배정했다.
- `[실측]` W0 §4: 샘플의 「N월 N주」 7건과 월 경계 주 13건(I02)이 모두 이 규칙과 같은 달 · 같은 번호였다.

### 3-2. 토요일은 `WeekPeriod` 가 아니라 주간계획안이 가진다 `[제안]`

`WeekPeriod` 는 금요일 끝을 강제한다(`p0-planning/src/ssuksak/planning/domain/week_period.py:60`).
이것을 바꾸면 월간 Core(ADR-033 동결)와 월간 Golden 이 함께 흔들린다. 그래서:

```text
WeekPeriod              그대로. 월~금. 주의 「주소와 소속 달」만 뜻한다
WeeklyPlan.operating_days   (MON, TUE, WED, THU, FRI) 또는 (… , SAT)
표시 기간                 week_period.start_date ~ (operating_days 의 마지막 요일)
```

- 토요일이 바꾸는 것은 **표시 기간과 칸 안 요일 목록뿐**이다. WQ-02 로 값은 주 단위이므로 Section · 칸 수는 같다.
- 토요일만 다음 달로 넘어가는 주(예: 금요일이 말일)는 표시 기간이 다음 달 1일까지 간다. 소속 달 · 주차는 그대로다.
- 일요일은 받지 않는다(PM 결정 범위 밖).

### 3-3. 월 경계 판정에 토요일을 세지 않는다 `[제안]`

- 판정은 지금처럼 「월~금 중 그 달 평일 3일 이상」(`MIN_WEEKDAYS_IN_TARGET_MONTH = 3`) 그대로다.
- 이유: 토요일을 세면 토요일을 켠 원만 주차 배정이 달라진다. `[실측]` 2026-09-28(월) 주는 말일 9/30 이 수요일이라
  지금 규칙으로 `2026-09-W5` 이고 10월 1주는 10/5 주다. 토요일을 세면 10월 쪽도 3일(10/1 ~ 10/3)이 되어
  **두 달이 같은 주를 갖고**, 10월 주차 번호가 하나씩 밀린다.
  월간(토요일을 세지 않음)과 주간의 주소가 어긋나므로, U-11 이 요구한 「주차 번호 불변」을 이것으로 지킨다.

### 3-4. 설정 저장 위치 `[제안]`

| 선택지 | 내용 | 평가 |
|---|---|---|
| **A (권장)** 원 설정 | `centers` 에 bool 컬럼(이름 예: `weekly_saturday_enabled`, 기본 `false`) | PM 표현 「원 설정으로」와 같다. `centers.trends_enabled` 와 같은 모양. migration 1개 |
| B `plan-config` | api-spec §9 의 `plan-config` 에 넣는다 | `plan-config` 는 「계약 안 씀」 상태이고 P0 두 값이 모두 비활성이다 — 이것 하나 때문에 계약을 새로 열어야 한다 |
| C 주간 Template | Template 에 요일 수를 넣는다 | Template 은 사람 승인 대상이라 원마다 다른 값을 넣을 곳이 아니다 |

**Backend 단계(W5)에서 만든다.** W1 은 이름과 의미만 제안한다. 컬럼 이름은 Backend 담당과 정한다.

### 3-5. 설정을 바꾸면 `[선례]` ADR-010 스냅샷

- 주간계획안은 **생성할 때 설정을 읽어 `operating_days` 로 저장한다**(ADR-010 반 정보 스냅샷과 같은 방식).
- 이미 만든 계획안은 바뀌지 않는다. `CONFIRMED` 는 read-only 이고, `DRAFT` 도 자동으로 고치지 않는다.
- 새로 만드는 계획안부터 새 설정을 쓴다. 전체 재생성은 P0 에 없으므로 「기존 DRAFT 에 토요일 반영」은 지원하지 않는다.

## 4. 생성 Gate 와 부모 월간

### 4-1. Gate `[결정]` + `[선례]`

생성 요청은 아래를 **모두** 통과해야 한다. 하나라도 실패하면 계획안 행을 만들지 않는다.

| # | 조건 | 실패 시 (공개 코드는 기존 것 재사용 — §13) |
|---|---|---|
| G1 | 반이 내 원의 반이다 | 404 (월간과 같음) |
| G2 | `week_id` 의 달이 그 반 학년도 안이다 (3월 ~ 다음 해 2월) | 422 `VALIDATION_FAILED` |
| G3 | 그 반 · 그 달 월간계획안이 있고 `CONFIRMED` 다 | 409 `GATE_BLOCKED` `[결정]` PM-04 |
| G4 | `week_id` 가 그 월간의 `week_periods` 안에 있고 `active` 다 | 422 `VALIDATION_FAILED` |
| G5 | 같은 반 · 같은 `week_id` 주간계획안이 없다 (`DRAFT` 든 `CONFIRMED` 든) | 409 `ALREADY_EXISTS` |
| G6 | 주간 Template 이 사람 승인됐다 | 월간 §9-1 「승인 전이면 생성도 막힌다」와 같은 처리 |

- **연간은 직접 보지 않는다.** 월간이 `CONFIRMED` 이면 그 월간을 만들 때 이미 연간 `CONFIRMED` 를 통과했다.
- G6 때문에 **사람이 주간 Template 을 승인하기 전에는 실서버 생성 성공 경로가 없다.** 월간도 v0.2.1 이 승인(2026-10-20)되기 전까지 같았다.
  Core 테스트는 월간 Golden 과 같은 방식(테스트용 승인 Fixture)으로 성공 경로를 검증한다.

### 4-2. 부모 월간은 Context · 제약이다 — 복사 대상이 아니다 `[제안]`

`[실측]` W0 §6-1: 연간에 주별 항목이 있는 기관(I01 · I02)은 주간이 거의 그대로 따랐지만(111건 중 109건),
놀이 중심 기관(I05 · I06)은 37건 중 9건만 같았다. 벗어나는 방향은 전월 주제 연장 · 아이 관심 · 행사였다.
**월간 → 주간 짝 자료는 읽을 수 있는 것이 없다** (`NOT_VERIFIED`, W0 §7-3).

| 부모 월간 값 (그 `week_id`) | 주간에서 |
|---|---|
| `theme` | `theme` 의 근거 · 출발점 (Context) |
| `focus[week]` | `focus` 의 근거 · 출발점 (Context) |
| `outdoor_play[week]` | `outdoor_play` 후보의 가점 (Context) |
| `goals` · `basic_habit` (켜진 경우) | 같은 칸의 근거 (Context) |
| `safety_education[week]` | 배치 정보에 따라 §8 |

- 부모 값을 그대로 넣는 Rule 을 하드코딩하지 않는다. 결과가 부모와 같아도 되고, 달라도 된다(교사가 고칠 수 있다).
- **부모 월간 칸의 현재 값을 쓴다.** 교사가 월간을 고쳤으면 고친 값이 근거다(교사 확정값 우선 — 루트 `CLAUDE.md`).
- 부모 월간은 `CONFIRMED` 라 바뀌지 않는다. 확정 취소도 없다(PM-03). **그래서 「부모가 바뀌어 stale」 상태는 P0 주간에 없다.**

## 5. WeeklyPlan 의미 구조

### 5-1. 계획안 `[제안]`

월간 `MonthlyPlan` 과 같은 모양으로 둔다. Backend 의 저장 · 응답 코드를 최대한 함께 쓰기 위해서다.

| 필드 | 뜻 | 월간과 비교 |
|---|---|---|
| `plan_id` · `school_year` | 계획안 id · 학년도 | 같음 |
| `week_id` · `week_period` | 주 주소 · 월~금 기간 | 월간은 `target_month` · `week_periods[]` |
| `operating_days` | 요일 스냅샷 (§3) | **새 필드** |
| `daycare_ref` · `classroom_ref` | 소유 | 같음 |
| `target_ages` | 연령 집합 (ADR-038) | 같음 |
| `status` | `DRAFT` · `CONFIRMED` | 같음 |
| `parent_lineage` | 부모 월간 (계획 단위, §5-3) | 월간은 부모 연간 |
| `template_snapshot` | 주간 전용 스냅샷 (§5-2) | **다른 타입** |
| `sections[]` ▸ `cells[]` | 칸. **모든 Section 이 `repeat_by = NONE`** → Section 마다 칸 하나 | 월간은 `NONE` · `WEEK` |
| `constraint_assessments` · `verification_report` | 검증 결과 | 같음 |
| `activity_catalog_ref` | 쓴 Activity Catalog 판 | 같음 |
| `audit` | 변경 이력 | 같음 |

**구현 방식은 W2 에서 최소 변경으로 정한다.** 공통으로 쓸 수 있는 기존 타입(`TemplateSection` · `TemplateRef` · `ParentLineage` ·
`EvidenceSource` · `GenerationMethodDetail` · `AuditHistory` · `CellState` · `SafetyPlacement`)은 재사용한다.
**월간 타입의 필수 조건을 풀거나 월간 타입에 필드를 더하는 일반화는 하지 않는다**(ADR-033).

### 5-2. 주간 전용 Template 스냅샷 `[제안]`

`[실측]` 월간 `TemplateSnapshot` 은 그대로 쓸 수 없다.

- `profile_ref` 가 필수다(`p0-planning/src/ssuksak/planning/domain/monthly_template_snapshot.py:21`). 주간은 Profile 이 없다(§13).
- 옛 키 `habits` 를 거절하고 정식 키는 `basic_habit` 이다(같은 파일 `:49` · `domain/monthly_template_profile.py:40`).
- 켜진 Section 만 담는다(`:57`).

그래서 주간은 **Profile 없는 주간 전용 스냅샷**을 둔다: `base_template_ref` · `institution_ref` · `classroom_ref` · 켜진 `TemplateSection` 목록.
가짜 Profile 을 만들어 월간 스냅샷에 끼우지 않는다.

### 5-3. 칸과 칸별 부모 스냅샷 `[제안]`

칸은 월간 `MonthlyCell` 과 같은 뜻의 필드를 갖고, **칸별 부모 스냅샷을 더한다** — 월간 칸에는 이 필드가 없다(`domain/monthly_plan.py:66`).

| 필드 | 뜻 |
|---|---|
| `item_id` · `section_key` · `value` · `cell_state` · `evidence` · `audit` | 월간과 같음 |
| `generation` | 생성 방식. **교사 입력 칸은 처음 쓰기 전까지 없음(null)** — §10-2 |
| `safety` | 안전교육 칸의 배치 정보 (§8). 없을 수 있음 |
| `parent_snapshots` | **0 개 이상의 `ParentLineage`(칸 단위)** — 근거로 쓴 부모 월간 칸마다 `parent_item_id` · 그때 `snapshot_value` |

- 기존 `ParentLineage` 타입을 그대로 쓴다(`domain/lineage.py`). 한 칸이 부모 칸 여러 개(예: `theme` + `focus[week]`)를 근거로 쓰면 여러 개를 담는다.
- 같은 칸 `evidence` 에는 `EvidenceSource(PARENT_PLAN, source_id = 월간 plan_id)` 를 둔다. Evidence 는 「무엇을 근거로」, 스냅샷은 「그때 어떤 값이었나」다.
- **저장 · 조회 왕복에서 `parent_snapshots` · `generation = null` · `safety` 가 그대로 보존되는 것을 W5 완료 기준에 넣는다.**

## 6. Section 과 주간 Template A

### 6-1. 주간 Template A v0.1.0 `[제안]`

- `template_id = ssuksak.weekly-template-a`, `template_version = weekly-template-a-v0.1.0`.
- `normative_status = SAMPLE_DERIVED_NON_NORMATIVE` — `[실측]` 공식 주간계획안 작성 지침이 없다(W0 §1). 모든 Section 은 샘플 관찰이다.
- `review.domain_owner_approval = PENDING_HUMAN_REVIEW`, `runtime_active = false` 로 발행한다(WQ-03). Claude 가 승인 상태를 바꾸지 않는다.
- 월간 Template 과 같은 키 이름(`semantic_key` · `role` · `activated` · `repeat_by` · `empty_value_policy` · `observed_source_labels` · `evidence`)을 쓴다.
  기본생활은 처음부터 **`basic_habit`** 으로 쓴다(월간 v0.2.1 JSON 의 `habits` 는 옛 이름).
- **JSON 파일은 W2 에서 만든다.** 아래 표가 그 내용의 제안이다.

### 6-2. Section 목록 `[제안]`

기관 수는 `[실측]` W0 §3-1(판독 가능 10기관 기준). P0 는 Profile 이 없으므로 **켜고 끄는 Section 을 두지 않는다** — 아래 Section 은 모두 항상 켜져 있다.

| semantic_key | 샘플 표기 예 | 기관 | 만드는 쪽 | 근거 (§7) |
|---|---|---:|---|---|
| `theme` | 주제 · 놀이주제 · 생활주제 | 10 | 생성 · **확정 필수** | 부모 월간 |
| `focus` | 소주제 · 예상놀이주제 | 3 + 계층 2 | 생성 | 월간 분류 `SUBTHEME` · `EXPECTED_PLAY` + 부모 |
| `goals` | 목표 · 교사의 기대 · 놀이목표 | 9 | 생성 | 월간 분류 `GOALS` + 부모 |
| `basic_habit` | 기본생활습관 · 기본생활 | 10 | 생성 | 월간 분류 `BASIC_HABIT` + 부모 |
| `safety_education` | 안전교육 · [교통안전] … | 9 | §8 | 부모 월간 배치 정보 |
| `indoor_play` | 실내자유놀이 · 실내놀이 · 놀이 | 10 | 생성 | 주간 분류 `INDOOR_PLAY` (새 판) |
| `group_activity` | 대·소집단활동 · 이야기나누기 | 9 + 1 | 생성 | 주간 분류 `GROUP_ACTIVITY` (새 판) |
| `outdoor_play` | 바깥놀이 · 실외놀이 | 10 | 생성 | 승인 Activity Catalog + 부모 |
| `indoor_alternative` | 대체놀이 · 대체활동 | 10 | 생성 | 주간 분류 `INDOOR_ALTERNATIVE` (새 판) |
| `family_link` | 귀가 및 가정연계 · 가정통신 · 반 소식 | 10 | **교사 입력** | — |
| `event_schedule` | 행사 · 행사 및 교육 | 6~7 | **교사 입력** | — |
| `special_program` | 특별활동 · 특성화 | 7 | **교사 입력** | — |

- **교사 입력 칸은 생성하지 않는다.** `[선례]` 월간도 `event_schedule` 을 기관 입력 전용으로 두고, 생성 경로에 들어가면 막는다(api-spec §9-1 `VALIDATION_FAILED` 「기관 입력 Section」).
  `[실측]` W0 §6-3: 가정 알림 · 행사 날짜 · 특별활동 시간표는 연간에 없는 기관 운영 정보라, 만들면 없는 사실이 된다.
- `event_schedule` · `special_program` 은 W0 에서 과반(6~7 · 7기관)이라 **항상 켜진 교사 입력 칸**으로 둔다. 켜고 끄는 기능(Profile)을 따로 만들지 않는다.
- 요일별 값(대·소집단 · 행사 · 특별활동)은 칸 하나 안 목록으로 쓴다(WQ-02).
- **후속 후보** — 이번 Template 에 넣지 않는다: `supplies` 준비물(1기관) · 등원 및 맞이하기 · 점심 · 낮잠(6기관, 생활지도 문장) ·
  사회관계증진(4) · 지난주 실행 기록(1, 계획이 아니라 기록) · 기관 고유 행(이달의 책 · 종교 행 · ESG 등).
  월간 Template 의 `candidate_sections_not_yet_defined` 처럼 후보 목록에만 적는다.
- **성품인사는 넣지 않는다**(월간 Template 의 `excluded_sections` 와 같은 이유).
- 혼합반의 「(만4세)… / (만5세)…」 같은 칸 안 연령별 분할은 구조로 만들지 않는다(§9).

## 7. 근거 (Grounding)

### 7-1. 원칙 `[선례]` 월간 근거 분류 (D2)

월간은 기관 자료(Evidence Store)를 **원문 행 이름까지 정확히 맞는 것만** 근거로 쓴다 — 사람이 승인한
`monthly-evidence-semantic-classification-v0.1.0`(`p0-planning/data/evidence/monthly_evidence_semantic_classification_v0_1_0.json`,
`evidence/classification.py`)이 `(source_section, source_label)` → 분류를 정하고, 목록에 없으면 제외다. 주간도 이 방식을 따른다.

- 기관 자료는 `CONTEXT_ONLY` — 원문을 그대로 옮기지 않는다(복사 금지 정책 유지).
- 근거는 **대상 달과 같은 달의 자료만** 쓴다. 다른 달로 넓히지 않는다. **원문에 없는 주차를 추측하지 않는다**(월간의 「`week_position` 추론 없음」과 같음).
- 연령은 **월간 연령 단계를 그대로** 쓴다(`retrieval/ranking.py:23` · `retrieval/models.py:21`):
  같은 단일 연령 → 요청 연령에 든 단일 연령 → 연령이 겹치는 혼합 페이지 순. **연령을 모르는 자료는 근거로 쓰지 않는다.**
  `[실측]` 자료의 연령은 활동 단위가 아니라 **페이지 단위**다 — 혼합 페이지 자료가 반의 모든 연령에 맞는다는 보증은 아니다.
  이 한계는 월간과 같고, 자료는 맥락으로만 쓰고 LLM 이 그 반에 맞는 새 문장을 쓴다.

### 7-2. 월간 분류를 그대로 쓰는 칸

`focus`(`SUBTHEME` · `EXPECTED_PLAY`) · `goals`(`GOALS`) · `basic_habit`(`BASIC_HABIT`) — 월간과 같은 분류 · 같은 판.

### 7-3. 주간 근거 분류 새 판 — `INDOOR_PLAY` · `INDOOR_ALTERNATIVE` · `GROUP_ACTIVITY` `[제안]`

`source_section` 만으로 고르면 다른 칸의 자료가 섞인다. `[실측]` Evidence Store v0.1.0:

| `source_section` | 레코드 | 원문 행 이름 수 | 섞인 예 (행 이름 · 건수) |
|---|---:|---:|---|
| `indoor_play` | 3,353 | 191 | 「대소집단 활동」 160 — 대·소집단 근거로 쓸 수 있다 |
| `indoor_alternative` | 785 | 50 | 「바깥놀이」 194 · 「실외놀이」 74 — 대체놀이가 아니라 바깥놀이 행일 수 있다 |

그래서:

- **새 분류 파일**(예: `weekly-evidence-semantic-classification-v0.1.0`)로 `(source_section, source_label)` → `INDOOR_PLAY` · `INDOOR_ALTERNATIVE` · `GROUP_ACTIVITY` 를 정한다.
  행 이름 241개(191 + 50)를 사람이 검토한다. 월간 분류 파일은 덮어쓰지 않는다.
- 발행 상태는 `PENDING_HUMAN_REVIEW`. **승인 전에는 이 세 칸을 생성하지 않는다** — §7-4 처리(빈 칸)를 따른다.
  승인되면 코드 변경 없이 생성으로 바뀐다.
- `GROUP_ACTIVITY` 는 「대소집단 활동」 같은 행 이름을 분류해 근거를 얻는다. 첫 판(`47b1d9c`)의 「근거 없음 → 비워 둠」을 이것으로 바꾼다.

### 7-4. 근거가 없을 때 `[선례]` 월간 api-spec §9-1 · ADR-019

| 경우 | 처리 |
|---|---|
| 생성 칸에 그 달 · 그 연령 근거가 없다 (분류 미승인 포함) | **그 칸만 비운다** — `cell_state = EMPTY_VALID`, `generation = RULE_ONLY`(ADR-032 「근거가 없어 비워 둔 칸」). 다른 칸 · 생성 전체는 영향 없음 |
| 다른 달 · 다른 연령으로 넓히기 | 하지 않는다 |
| 화면 | 빈 칸을 「미작성」으로 보여 주고 교사가 쓸 수 있다(월간과 같음). 새 칸 상태를 만들지 않는다 |

- 월간에서 「근거 없는 필수 Section」은 Profile 단계에서 막지만(api-spec §9-1), 주간은 Profile 이 없고 근거 칸이 모두 선택이라 생성 전체를 실패시키는 칸은 없다.
  `theme` 은 부모 월간 `theme` 이 늘 있으므로(월간 확정 조건) 비지 않는다.

## 8. 안전교육 `[제안]`

법정 조건과 배치 정책을 나누는 원칙은 월간과 같다. **칸 상태(`FILLED`)가 아니라 부모 월간 칸의 배치 정보(`safety`)로 나눈다.**

`[실측]` 칸 상태만으로는 배치를 알 수 없다:
- 교사가 빈 안전교육 칸에 쓰면 `FILLED` 가 되지만 배치 정보는 생기지 않는다(`application/edit_monthly_plan_item.py:88` · `rules/monthly_cell_state.py:18`).
- 보충 배치는 `SUPPLEMENTAL` 이고 법정 영역(`category_id`)이 없다(`domain/safety_placement.py:104`).
- 교사가 문장을 고쳐도 배치 정보는 그대로 남는다 — 배치 정보와 현재 문장이 어긋날 수 있다.

**부모 칸의 현재 값이 비어 있으면 배치 정보가 있든 없든 마지막 줄(비어 있음)을 먼저 적용한다** — 교사가 법정 배치 칸을 비운 경우도 여기다.
값이 있을 때만 위 네 줄 중 하나로 나눈다.

| 부모 월간 칸 | 주간 칸 | Evidence | 생성 방식 |
|---|---|---|---|
| 법정 배치 (`STATUTORY`) · 교사 수정 없음 | 같은 법정 영역 안에서 주간 문장 | `PARENT_PLAN` · `SAFETY_RULE` | 배치 `RULE_ONLY` / 문장 `RULE_LLM` |
| 법정 배치 · **교사가 문장을 고침** | 부모의 **현재 문장**을 근거로 주간 문장. 배치 정보와 문장의 일치를 보증하지 않는다 | `PARENT_PLAN` (배치 정보는 스냅샷으로만) | `RULE_LLM` |
| 보충 배치 (`SUPPLEMENTAL`) | 부모 문장을 근거로 주간 문장. 법정 영역 없음 | `PARENT_PLAN` | `RULE_LLM` |
| 배치 정보 없음 · 교사가 쓴 문장 | 부모의 현재 문장을 근거로 주간 문장. **문장에서 법정 영역을 추측하지 않는다** | `PARENT_PLAN` | `RULE_LLM` |
| 비어 있음 | `EMPTY_UNRESOLVED` + `NOT_VERIFIED_SOURCE_REQUIRED` (월간과 같음) | — | `RULE_ONLY` |

- 주간은 **안전교육을 새로 배치하지 않는다.** 배치는 월간 Rule 의 몫이다.
- **법정 충족을 주장하지 않는다**(ADR-033 §4). 법정 배치 · 교사 수정 없음인 경우에는 부모의 법정 영역과 공식 근거를 이어받는다.
  `SAFETY_RULE` 은 쓴 근거를 나타낼 뿐 법정 요건 충족을 뜻하지 않는다. 같은 영역을 배치했다고 시수 · 실시 여부까지 확인한 것은 아니다.
  어느 경우에도 충족 · 위반을 단정하지 않는다.
- **AI 출력의 안전교육 근거 오류는 저장을 막는다.** 원칙은 `[선례]` ADR-037 §2 이고, 부모가 월간인 주간에서 **무엇을 유효한 근거로
  인정하는지는 주간 제안**이다 `[제안]`. 위 표의 Evidence 열과 같은 조건으로 검사한다:

  | 주간 칸이 해당하는 줄 | 유효한 근거 (AI 생성 · 재생성 결과) | 어기면 |
  |---|---|---|
  | 법정 배치 · 교사 수정 없음 | 월간과 같은 공식 근거 검사 — 그 법정 영역의 공식 근거(`SAFETY_RULE`)만 | `SAFETY_OFFICIAL_GROUNDING_MISSING` · 저장 안 함 |
  | 법정 배치 + 교사 수정 · 보충 배치 · 배치 정보 없음 · 교사 문장 | **부모 월간의 그 칸을 정확히 인용** — 같은 `week_id` 의 `safety_education` 칸 `parent_item_id` 와 현재 값 `snapshot_value`, `PARENT_PLAN` Evidence. **`SAFETY_RULE` 을 붙이지 않는다**(법정 영역 추측 금지) | 저장 안 함. 주간 검사 코드 이름은 W3 에서 정한다 — 공개 오류 코드는 `GENERATION_FAILED` 그대로 |

  **부모 칸 인용(`parent_snapshots` · `PARENT_PLAN` Evidence)은 LLM 이 적어 내지 않고 Application 이 결정적으로 붙인다** — 어느 부모 칸을
  썼는지는 Rule 이 이미 안다. 그래서 LLM 이 인용을 빠뜨려 생성 전체가 실패하는 일이 없다. 위 검사는 붙인 결과를 확인하는 안전장치로 남긴다.
  보충 배치 줄은 월간처럼 기관 자료(`INSTITUTION_SAMPLE`)를 직접 요구하지 않는다 — 그 기관 자료는 부모 월간이 이미 검사를 통과해 확정한 근거이고,
  주간은 그 부모 칸을 인용한다. **교사가 쓴 안전교육 문장 자체는 이 검사로 막지 않는다**(§11-2). 위 두 줄은 교사 문장을 참고해 **AI 가 만든** 주간 문장에 적용한다.
- `[실측]` 지금 실서버 월간은 배치 정책을 넘기지 않아(api-spec §9-1, D-M4-03) 새 월간의 안전교육 칸이 비어 있다.
  **그래서 P0 에서 실제로 생기는 경우는 「비어 있음」과 「배치 정보 없음 · 교사가 쓴 문장」이다.** 월간이 배치 정책을 켜면
  법정 배치 두 줄과 보충 배치 줄이 쓰인다.

## 9. 혼합연령 `[결정]` ADR-038 + `[선례]`

- 반 하나 = 주간계획안 하나. 연령별로 나누지 않는다(ADR-038 · `docs/schema.md`).
- 바깥놀이 후보(Activity Catalog)는 월간과 같은 혼합반 필터를 쓴다. 기관 자료 근거는 §7-1 의 월간 연령 단계를 쓴다.
- `[실측]` W0 §4: 혼합반 샘플은 일부 활동만 「(만4세)… / (만5세)…」로 나눈다. **P0 는 칸 안에서 연령별로 나눈 구조를 만들지 않는다.**
  교사가 칸 안 문장으로 쓸 수는 있다.
- 떨어진 연령 조합(만 3 + 5세)은 ADR-038 대로 우선 미지원이다.

## 10. 동작 (Use Case)

월간 §9-1 · §9-3 과 같은 규칙을 쓴다(`[선례]`). 다른 곳만 적는다.

### 10-1. 생성 — `GenerateWeeklyPlan`

- 입력: `class_id` · `week_id`. 부모 월간은 서버가 반 + 달로 찾는다(월간이 부모 연간을 찾는 방식과 같음).
- 결과: 항상 `DRAFT`. 부분 결과를 저장하지 않는다.
- **문서 단위 배치 호출** — 한 주를 한 번에 부른다. 칸마다 부르지 않는다(ADR-032).
- **제품 생성 모드는 월간과 같은 LLM 경로**다. 결정론 Rule 경로(`RULE_ONLY`)는 Core 테스트용으로 남는다(월간과 같음).
- **필수 LLM 호출이 실패하면 Rule 결과로 조용히 대체하지 않는다** — `GENERATION_FAILED` 500, 저장 없음(월간과 같음).
  Optional 외부 기능(트렌드 등)만 Fallback 한다. Fallback 사용 여부는 실행 기록에 남긴다.
- 동기 처리(월간과 같음). 생성 Section 은 월간 기본보다 많지만 칸은 Section 마다 하나다. 호출 크기 · 시간은 `NOT_VERIFIED` — W7 에서 재고,
  월간 기준(타임아웃 30초) 안에 들지 않으면 처리 방식을 다시 정한다.

### 10-2. 칸 편집 — `EditWeeklyPlanCell` `[선례]` + `[제안]`

- `DRAFT` 에서만. 동시 수정은 **월간과 같은 `expected_revision`** — 다르면 `STALE_WRITE` 409.
  비교와 저장을 한 번에 하고, LLM 을 기다리는 동안 transaction 을 잡지 않는 월간 방식도 그대로 따른다(ADR-035).
- 막는 경우는 월간과 같다: 값이 그대로 · `theme` 을 비움 · 빈 칸을 다른 빈 값으로.
- **교사 입력의 생성 방식** — 주간 편집은 월간 편집 계약을 바꾸지 않고 주간 Use Case 에서 정한다:

| 칸 | 처음 상태 | 교사가 처음 쓰면 | 그 뒤 고치거나 비우면 |
|---|---|---|---|
| 교사 입력 칸 (`family_link` · `event_schedule` · `special_program`) | `value = ""` · `EMPTY_VALID` · `generation = null` | `generation = MANUAL` + `TEACHER_EDITED` | `MANUAL` 유지 + `TEACHER_EDITED` |
| 생성 칸 (값 있음) | `RULE_LLM` 등 | — | 생성 방식 유지 + `TEACHER_EDITED` (ADR-032 §2) |
| 생성 칸 (근거가 없어 빈 칸) | `RULE_ONLY` · `EMPTY_VALID` | 생성 방식 유지(`RULE_ONLY`) + `TEACHER_EDITED` | 같음 |

  `MANUAL` 은 「사람이 처음부터 쓴 칸」(ADR-032)이므로 **처음부터 교사 입력 전용인 Section 에만** 쓴다.
  생성 칸이 비어 있었다는 이유로 `MANUAL` 로 바꾸지 않는다 — 교사 수정으로 생성 방식을 덮지 않는다(루트 `CLAUDE.md`).
- `[실측]` 월간 응답은 `generation = null` 칸에서 깨진다(Core Error Audit — 월간 `_detail` 이 `cell.generation.method` 를 읽음).
  **주간 응답은 `generation = null` 을 처음부터 받아야 한다** — W5 완료 기준.

### 10-3. 칸 재생성 — `RegenerateWeeklyPlanCell` `[선례]`

- `DRAFT` 에서만, `expected_revision` 같음. 고른 칸만. 다른 칸의 `item_id` · 값 · Evidence · 부모 스냅샷을 보존한다. `item_id` · `semantic_key` 는 그대로다.
- 대상: 생성 칸. **교사 입력 칸은 재생성 대상이 아니다.** 안전교육은 §8 의 생성 경우(`RULE_LLM` 문장)만 다시 쓴다 — 배치는 바꾸지 않는다.
- 새 값의 생성 방식으로 갱신하고, 이전 값 · 방식과 새 값 · 방식을 `REGENERATED` 이벤트에 남긴다.

### 10-4. 확정 — `ConfirmWeeklyPlan` `[선례]`

- opaque `actor_id` 필수. `DRAFT` → `CONFIRMED`. 제출 · 발송하지 않는다. 확정 취소 없음(PM-03).
- **`theme` 이 비어 있으면 확정을 막는다**(연간 PM-08 · 월간과 같은 기준). 다른 빈 칸은 막지 않고 화면이 확정 전에 보여 준다.
  확정할 때 검사를 다시 돌리지만 **검사 결과가 확정을 막지 않는다** — 월간과 같다(`application/confirm_monthly_plan.py:41`).
  구조 · 소유 · Provenance 같은 불변식이 깨진 계획안은 애초에 만들어지지 않는다(§11-1).
- 재확정 요청은 월간(api-spec §9-3)과 같은 멱등 규칙 — 이미 `CONFIRMED` 면 `expected_revision` 과 상관없이 200, 저장된 그대로, 이력도 그대로.
  확정 뒤 편집 · 재생성은 `ALREADY_CONFIRMED` 409.

## 11. 검사

**AI 가 만든 값과 교사가 쓴 값을 다르게 다룬다.**

### 11-1. AI 출력 — 세 단계로 나눈다 `[선례]` ADR-037 §2

생성 · 재생성 결과는 서버 경계에서 검사한다. 실패를 성공으로 저장하지 않는다(루트 `CLAUDE.md` · ADR-032).
월간과 같이 **검사 전에 막는 것 · 저장을 막는 예외 · 안내(finding)** 를 나눈다. 같은 종류의 검사는 월간과 같은 단계에 둔다.

| 단계 | 검사 | 처리 |
|---|---|---|
| 검사 전 차단 | Structured Output Schema · 필수 필드 | 수리 1회 뒤에도 어기면 `GENERATION_FAILED` 500, 저장 안 함 (api-spec §9-1) |
| 검사 전 차단 | Section 집합이 Template 스냅샷과 같다 (빠짐 · 추가 없음) · `item_id` · `semantic_key` · Provenance 누락 | 저장 안 함 |
| 검사 전 차단 | 모르는 Reference id · 그 칸에 쓸 수 없는 근거(다른 Section 분류 · 다른 달 · 연령 단계 밖) · 바깥놀이 근거 연령 불일치 | 저장 안 함 (월간과 같음) |
| 검사 전 차단 | 교사 입력 칸에 LLM 값 · 법정 배치 · 교사 수정 없음 줄에서 법정 영역 교체 | 저장 안 함 `[제안]` |
| 저장을 막는 예외 | 안전교육 근거 오류 — 공식 근거 누락 · 부모 칸 인용 누락 · 잘못된 인용 (§8 의 근거 검사 표) | 저장 안 함 |
| 검사 전 차단 | 근거 없는 사실 — 허용된 입력 · 근거에 없는 행사 · 날짜 · 사람 정보를 AI 가 사실로 더함 (ADR-032 「근거 없는 사실」) | 저장 안 함. **탐지 방법과 검증할 수 있는 범위는 W3 에서 확인한다** `NOT_VERIFIED`. 탐지하지 못한 범위를 「검사 통과」로 표시하지 않는다. 날짜 · 사람 언급을 모두 막는다는 뜻은 아니다 |
| 안내 | 그 밖의 finding — 예: `ACTIVITY_AGE_UNSUPPORTED` | **DRAFT 와 검사 결과를 저장한다.** 확정도 막지 않는다 |

### 11-2. 교사 값 — 내용 검사로 막지 않는다 `[선례]`

- 교사가 쓰거나 고친 현재 값을 우선하고 보존한다. 내용 검사 결과로 교사 값을 **자동 수정 · 재생성하지 않고, 저장 · 확정을 막지 않는다.**
  편집 · 확정 때 검사를 다시 돌려 **막지 않는 안내**(`verification` · `constraints`)로만 보여 준다 — 월간과 같다.
- 막는 것은 내용이 아니라 동작 규칙뿐이다: 소유 검사 · `expected_revision` · `CONFIRMED` 수정 금지 · §10-2 의 세 경우 · 빈 `theme` 확정.
- 안전교육 칸이 비어 있거나 근거가 없어도 교사 편집 · 확정은 막히지 않는다. 칸 상태(`EMPTY_UNRESOLVED`)와 제약 표시만 달라진다(월간과 같음).
  §11-1 의 안전교육 근거 오류 예외는 AI 생성 · 재생성 결과에만 적용한다.
- **검사기 실행 실패는 finding 이 아니다.** 검사기가 돌지 못하면 finding 으로 대신하지 않고 `GENERATION_FAILED` 500 으로 처리하며
  저장 · 확정하지 않는다(ADR-037 §2 · api-spec §9-3). 확정은 직전에 검사를 **새로** 돌린다 — 이미 `CONFIRMED` 인 재확정 요청은 다시 돌리지 않는다.

### 11-3. 범위 밖

평가제 검사와의 연결은 이 계약에 넣지 않는다. 평가제 전체 자동 대조는 P0 제외 범위이고, 평가제 4-1 이 지금 세는 것은 확정 월간뿐이다.
주간 확정본을 평가제가 셀지는 평가제 담당이 따로 정한다.

## 12. Provenance `[선례]`

월간과 같은 세 축이다. 새 Source Type 을 만들지 않는다.

| 칸 | Evidence Source | Generation Method |
|---|---|---|
| `theme` | `PARENT_PLAN` | `RULE_LLM` |
| `focus` · `goals` · `basic_habit` | `PARENT_PLAN` + `INSTITUTION_SAMPLE` | `RULE_LLM` |
| `indoor_play` · `indoor_alternative` · `group_activity` | `INSTITUTION_SAMPLE` (+ `PARENT_PLAN`) | `RULE_LLM` · 근거 없으면 `RULE_ONLY`(빈 칸) |
| `outdoor_play` | `ACTIVITY_REFERENCE` (+ `PARENT_PLAN`) | `RULE_LLM` |
| `safety_education` | §8 표 | §8 표 |
| 교사 입력 칸 | — | 처음 쓰면 `MANUAL` (§10-2) |

`[결정]` PM-12: LLM 경로로 설계된 칸은 FakeLLM 으로 돌려도 `RULE_LLM` 이다. mock 여부는 실행 기록에서 구분한다.

## 13. Backend API 초안 `[선례]` 월간 모양

월간(api-spec §9-1 · §9-3 · §9-5)과 같은 모양 · 같은 공개 오류 코드다. **새 공개 오류 코드를 만들지 않는다.**

```text
POST   /api/plans/weekly                               생성        { "class_id": 1, "week_id": "2026-09-W2" }
GET    /api/plans/weekly/{id}                          단건
GET    /api/plans/weekly?class_id=&month=              목록        그 달 주간계획안들
PUT    /api/plans/weekly/{id}/cells/{item_id}          칸 편집      { "value": "…", "expected_revision": 3 }
POST   /api/plans/weekly/{id}/cells/{item_id}/regenerate  칸 재생성 { "expected_revision": 3 }
POST   /api/plans/weekly/{id}/confirm                  확정        { "expected_revision": 3 }
GET    /api/plans/weekly/{id}/audit                    변경 이력
```

- `week_id` 의 연도는 **달력 연도**다 — 2026 학년도 2월 2주는 `2027-02-W2`. `school_year` 는 받지 않는다(반이 정한다).
- 응답은 월간 응답과 같은 틀에 `week_id` · `week_period` · `operating_days` · 칸별 `parent_snapshots` 를 더한다. 칸 `generation` 은 null 일 수 있다.
- `profile_ref` 를 받지 않는다 — 주간 TemplateProfile 은 P0 에 두지 않는다(D-W1-06).
- 저장: 월간이 쓰는 `plans` 테이블 구조를 따르되 물리 설계는 **Backend 담당과 W5 에서 정한다**(DB 임의 확정 금지).

## 14. 구현 순서 (W2 ~ W7) `[제안]`

각 단계는 테스트를 통과한 뒤 다음으로 간다. 각 단계 = PR 하나.

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| W2 | Domain(`WeeklyPlan` · 주간 스냅샷 · 칸 `parent_snapshots`) + 주간 Template A v0.1.0 JSON(`PENDING_HUMAN_REVIEW`) + `test_freeze` SHA 고정 | Domain Unit Test · **월간 테스트 · Golden 변화 없음** |
| W2-E | 주간 근거 분류 새 판(§7-3) 초안 — 행 이름 241개 분류 · `PENDING_HUMAN_REVIEW` | 사람 검토 요청. W3 와 병렬 가능 — 승인 전에는 세 칸이 빈 칸 |
| W3 | `GenerateWeeklyPlan` Core — Gate · 부모 Context · 근거 선택 · 안전교육 분기 · FakeLLM · 검사 | 주간 Golden(`weekly_rule.json` · `weekly_llm.json`) |
| W4 | Edit · Regenerate cell · Confirm | 교사 입력 `MANUAL` · 비선택 칸 보존 · CONFIRMED 차단 Golden |
| W5 | Backend 저장 · API(§13) · 토요일 원 설정 컬럼 | Backend 테스트 · ruff · CI · `parent_snapshots` · `generation = null` 왕복 |
| W6 | FE API client · MSW | FE 검사 · 화면은 담당 확인 뒤 |
| W7 | 실제 LLM 연결 · Live Quality Smoke(사람 관찰) | 유료 호출 별도 승인 후 |

**Golden 두 개를 나눈다**(월간과 같음): `weekly_rule.json` 은 결정론 Rule 경로(LLM 0회)의 동작, `weekly_llm.json` 은 FakeLLM 에 고정 Proposal 을 넣은
제품 LLM 경로의 Application 계약이다. 하나가 다른 하나를 대신하지 않는다.

Golden 최소 사례:

- 대상 · Gate: 만 3 · 4 · 5세 · 혼합(만 4+5세) · 부모 월간 `DRAFT` · 부모 없음 · `week_id` 가 월간 밖 / 비활성 주 · 학년도 밖 · 2027-02 주 · 중복 생성 ·
  미승인 Template · 잘못된 Template version
- 토요일: 켬 / 끔 · 토요일만 다음 달로 넘어가는 표시 기간 · 설정 변경 뒤 기존 `DRAFT` · `CONFIRMED` 불변
- 근거: 없는 Reference id · 다른 Section 근거(검사 실패) · 그 달 · 연령 근거 없음 → 빈 칸 · 주간 분류 미승인 → 세 칸 빈 칸 · 연령 모름 자료 제외
- 안전교육: 법정 배치 · 법정 배치 + 교사 수정 · **법정 배치였던 칸을 교사가 비움(빈 칸 분기)** · 보충 배치 · 배치 정보 없는 교사 문장 · 빈 칸 ·
  법정 영역 교체(저장 안 함) · 공식 근거 누락(저장 안 함) · 부모 칸 인용 누락 · 다른 칸 인용 · 교사 문장 줄에 `SAFETY_RULE`(저장 안 함) ·
  교사가 쓴 안전교육 문장은 편집 · 확정 통과
- 근거 없는 사실: 입력에 없는 행사 · 날짜를 AI 가 더함(저장 안 함) · 허용된 입력(부모 월간 값 등)에 있는 행사를 쓰는 것은 통과
- 검사: finding 이 있어도 DRAFT 저장 · 확정 통과 · 검사기 실행 실패 시 저장 · 확정 안 함
- 교사 입력: 교사 입력 칸에 LLM 값(검사 실패) · 처음 입력 `MANUAL` · 다시 고침 · 비우기 — Generation · Audit 보존
- 동작: Edit · Regenerate(비선택 칸 · 부모 스냅샷 보존) · Confirm · Confirm actor 없음 · CONFIRMED 편집 · 재생성 차단 · 빈 theme 확정 차단 ·
  stale revision · 재확정 시 이력 불변
- 실패: 수리 실패 시 저장 · revision · Audit 불변 · 필수 LLM 실패가 Rule 결과로 대체되지 않음 · Optional 기능 timeout fallback

## 15. 결정 요청

이 문서의 승인 = 아래 항목의 승인이다. 고르지 않은 항목은 구현하지 않는다.

| ID | 쟁점 | 권장 | 근거 종류 | 영향 |
|---|---|---|---|---|
| D-W1-01 | 주 주소 | 월간 `WeekId` 그대로 (§3-1) | 제안 | W2 · W3 |
| D-W1-02 | 토요일 표현 | `WeekPeriod` 불변 · 주간계획안 `operating_days` (§3-2) | 제안 | W2. 월간 동결(ADR-033) |
| D-W1-03 | 월 경계에 토요일 | 세지 않음 (§3-3) | 제안 | W3 |
| D-W1-04 | 설정 위치 · 변경 | 원 설정 bool · 생성 시 스냅샷 · 기존 계획안 불변 (§3-4 · §3-5) | 제안 + 선례 | W5 migration |
| D-W1-05 | Section 목록 | §6-2 표 · `basic_habit` · 행사 · 특별활동은 항상 켜진 교사 입력 · 준비물 후속 | 제안 | W2 Template |
| D-W1-06 | 주간 TemplateProfile · 스냅샷 | Profile 없음 · 주간 전용 스냅샷 (§5-2) | 제안 | W2 · W5 API |
| D-W1-07 | 동시 수정 | 월간과 같은 `expected_revision` (§10-2) | 선례 | W4 · W5 |
| D-W1-08 | 실내 · 대체 · 대소집단 근거 | 주간 근거 분류 새 판 · 사람 승인 · 승인 전 빈 칸 (§7-3) | 선례(D2 방식) | W2-E · W3 |
| D-W1-09 | 안전교육 | 배치 정보로 분기 · 교사 문장 우선 · 영역 추측 안 함 · 법정 배치(수정 없음)는 공식 근거, 나머지는 부모 칸 정확한 인용을 유효한 근거로 (§8) | 선례(근거 오류 차단) + 제안(유효한 근거) | W3 |
| D-W1-10 | 확정 조건 · 교사 값 | 빈 `theme` 만 막음 · 내용 검사는 안내만 (§10-4 · §11-2) | 선례 | W4 |
| D-W1-11 | 근거 없을 때 · 연령 | 그 칸만 `EMPTY_VALID` · 다른 달 · 연령으로 안 넓힘 · 월간 연령 단계 (§7-1 · §7-4) | 선례 | W3 |
| D-W1-12 | 교사 입력 생성 방식 | 교사 입력 Section 만 처음 쓰면 `MANUAL` (§10-2) | 선례(ADR-032) + 제안 | W4 · W5 |
| D-W1-13 | 칸별 부모 스냅샷 | 칸에 `parent_snapshots` 0개 이상 · 왕복 보존 (§5-3) | 제안 | W2 · W5 |

**PM · 팀 몫으로 남기는 것** (이 문서가 정하지 않는다):

- 주간 Template A · 주간 근거 분류의 개별 사람 승인 — 승인자 id · 기록 위치가 월간과 같이 미정이다(ADR-027).
- 토요일 컬럼 이름 · 원 설정 화면 위치 — Backend · 화면 담당.
- 주간 확정본의 평가제 연결 — 평가제 담당(§11-3).
- Evidence Store 주간 수집(새 판) — 122개 미수집 파일 · 개인정보 칸 제외 · 사람 검토(W0 §8).

## 16. 확인하지 못한 것

- **월간 → 주간 연결은 실측 근거가 없다** `NOT_VERIFIED`. 같은 기관 월간 · 주간 짝이 I10 하나이고 이미지 PDF 다(W0 §7-3).
  §4-2 의 「Context 로만 쓴다」는 연간↔주간 실측(W0 §6-1)에서 끌어낸 판단이다.
- **주간 근거 분류 뒤 실제 근거 양** — 행 이름 분류 전이라 칸별 · 달별 · 연령별 건수를 모른다. 단일 연령 페이지만 보면 만 4세 대체놀이 근거가
  한 달 2건인 달이 있다(`source_section` 기준 집계). 분류 뒤 다시 센다.
- 혼합반에서 혼합 페이지 근거가 실제로 모든 연령에 맞는지 — 자료 연령이 페이지 단위라 확인할 수 없다(§7-1).
- 근거 없는 사실(행사 · 날짜 · 사람 정보)의 탐지 방법과 검증할 수 있는 범위 — W3 에서 월간 검사 코드를 확인한 뒤 정한다(§11-1).
  저장 차단 원칙은 정해져 있고(ADR-032), 탐지 범위만 미확인이다.
- LLM 호출 크기 · 시간 — W7 에서 잰다.
- 토요일을 켠 원에서 토요일 칸에 무엇을 쓰는지 — 샘플 2기관(I02 · I03)뿐이다. 값이 주 단위라 Section 영향은 없다고 보았다.
- 공식 주간계획안 작성 지침은 `references/official/` 에서 찾지 못했다.
