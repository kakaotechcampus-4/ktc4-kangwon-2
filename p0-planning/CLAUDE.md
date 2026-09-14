# CLAUDE.md — 쓱싹요정 P0 Planning Core

이 파일은 쓱싹요정 P0 계획안 초안 생성 기능을 구현할 때 반드시 지켜야 하는 **구현 안전 규칙**이다.

이번 AI 파트의 우선 목표는 제품 전체 FE/BE를 완성하는 것이 아니라, 다른 팀원이 연결할 수 있는 **Planning Core**를 높은 완성도로 구현하는 것이다.

구현 중 이 문서와 다른 자료가 충돌하면 임의로 해석하지 말고, 충돌 위치·가능한 해석·영향 범위·권장안을 먼저 보고한다.

---

## 1. Source of Truth 우선순위

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

같은 우선순위 안에서는 최신 승인일과 명시적인 결정 상태를 우선한다.

과거 기획서, 과거 테크스펙, 회의 중 폐기된 아이디어는 최신 Source of Truth와 충돌하면 구현하지 않는다.

`references/`는 근거 자료이지 요구사항 문서가 아니다. 공식 문서나 샘플에 내용이 있다는 이유만으로 기능을 새로 추가하지 않는다.

---

## 2. 이번 P0의 목표

이번 P0는 **연간 → 월간 → 주간 계획안 초안 생성 흐름**을 완성하는 것이 목적이다.

핵심 흐름:

```text
GenerateYearlyPlan
    ↓
YEARLY DRAFT
    ↓
Teacher Edit
    ↓
YEARLY CONFIRMED
    ↓
GenerateMonthlyPlan
    ↓
MONTHLY DRAFT
    ↓
Teacher Edit
    ↓
MONTHLY CONFIRMED
    ↓
GenerateWeeklyPlan
    ↓
WEEKLY DRAFT
    ↓
Teacher Edit
    ↓
WEEKLY CONFIRMED
```

### 필수 게이트

- 연간 계획안이 `CONFIRMED`가 아니면 월간 계획안을 생성하지 않는다.
- 월간 계획안이 `CONFIRMED`가 아니면 주간 계획안을 생성하지 않는다.
- AI 생성 결과는 항상 `DRAFT`로 시작한다.
- 자동 확정, 자동 제출, 자동 발송을 구현하지 않는다.
- 교사 확정값은 이후 생성에서 이전 AI 원본보다 우선한다.
- P0에서 `CONFIRMED` Plan은 read-only다. 후속 Version 정책이 확정되기 전까지 기존 Confirmed Plan을 직접 수정하지 않는다.

---

## 3. AI Planning Core 구현 범위

이번 AI 파트의 완료 기준은 제품 FE/BE 전체를 완성하는 것이 아니라, 계획안 생성 기능의 핵심 로직을 독립적으로 검증 가능한 Application Core로 완성하는 것이다.

### 우선 구현 대상

- Domain / Application Logic
- Rule Engine
- Machine-readable Reference
- LLM Port / Adapter
- Validation
- Provenance
- Generate / Edit / Regenerate / Confirm
- Golden Test
- 다른 팀원이 연결할 수 있는 Input / Output Contract와 Port 경계

### 통합을 위해 최소 수준만 구현

- HTTP Adapter
- Persistence Adapter
- 테스트용 UI 또는 실행 Harness

### 현재 AI 파트에서 고도화하지 않음

- 최종 FE 디자인
- 반응형 UI / 애니메이션
- 최종 DB Schema
- 인증/권한 시스템
- 운영 배포 구조
- AWS 인프라 고도화

FE/BE 팀의 구조가 변경되어도 Planning Core 수정이 최소화되도록 Application DTO와 Port를 외부 Adapter에서 분리한다.

---

## 4. P0 범위

### 포함

- 원 정보 Context
- 반 정보 Context
- 만 3세 / 만 4세 / 만 5세
- 혼합연령 지원
- 연간 계획안 생성 / 편집 / 선택 Item 재생성 / 확정
- 월간 계획안 생성 / 편집 / 선택 Item 재생성 / 확정
- 주간 계획안 생성 / 편집 / 선택 Item 재생성 / 확정
- 계획안 생성 근거 추적
- Rule 기반 배치/선별
- LLM 기반 최종 문장화
- Validation
- 외부 Optional 기능 실패 시 Fallback
- 승인된 지원 형식에 한한 기존 계획안 Import/부분 생성

### 이번 P0에서 제외

- 전체 보육일지 생성
- 관찰일지
- 알림장
- 아동별 발달평가
- 평가제 전체 자동 대조
- 위험 신호 판정
- HWP 직접 쓰기
- 결제
- 앱스토어 출시
- 자동 제출/발송
- 만 0~2세 영아반
- 활동 이력 기반 개인화 추천
- 승인되지 않은 기관 고유 양식의 범용 자동 파싱

범위 밖 기능을 편의상 추가하지 않는다.

---

## 5. Rule / LLM Boundary

이 프로젝트의 핵심 원칙이다.

```text
Rule
→ 무엇을 어디에 넣을지 결정

LLM
→ 이미 선택된 내용을 자연스럽게 문장화
```

### Rule Engine이 담당

- Section / Item 역할 결정
- Theme Reference 후보의 월·연령 적합성 필터
- 적용 가능한 Theme 후보의 최종 선택
- 법정 안전교육 제약 검증
- 안전교육 월별 배치 정책 적용
- 행사·달력 반영
- 상위 계획안 Context / Constraint 반영
- 연령 적합성 필터
- 누리과정 적합성 필터
- 안전성 필터
- 원 특성 반영
- Activity Candidate Filtering
- 누리과정 영역 균형
- 후보 우선순위 계산
- Optional Context 적용 여부

### LLM이 담당

- Rule이 선택한 주제/활동/목표의 자연스러운 문장화
- 사용자에게 보여줄 표현 다듬기
- 정해진 Structured Output Schema에 맞는 문자열 생성

### LLM 금지

LLM이 다음을 자유롭게 결정하게 하지 않는다.

- 법정 기준
- 안전교육 실시 주기·연간 최소 시간
- 어느 슬롯에 무엇을 배치할지
- 연령 적합성
- 안전성
- Theme Reference 밖의 Theme 자유 생성
- Rule이 선택한 `theme_id` 교체
- 활동 후보의 최종 정책적 선택
- 평가 통과 여부
- 존재하지 않는 행사/사실 생성

### 안전교육 관련 중요 원칙

법령이 직접 정하는 조건과 제품의 월별 배치 정책을 구분한다.

```text
Legal Constraint
≠
Monthly Placement Policy
```

법령의 실시 주기·연간 누적시간 등은 공식 근거를 따른다.

어느 월에 어떤 안전교육을 배치할지는 별도 제품/기관 운영 정책으로 관리한다.

---

## 6. 배치층과 선별층

### 배치층

어느 칸에 어떤 종류의 내용이 들어가는지 결정한다.

우선순위 기본 원칙:

```text
1. 법정 안전교육 제약 / 확정된 안전교육 배치 정책
2. 원 행사·달력
3. 상위 계획안 Context
4. 누리과정 영역 균형
5. Trend / 외부 Context
```

상위 계획안은 하위 계획안 생성의 **Context / Constraint**로 사용한다.

상위 계획의 값을 하위 계획의 특정 칸에 무조건 직접 복사하도록 하드코딩하지 않는다.

### 선별층

배치 조건에 맞는 Theme / Activity 후보 중 무엇을 사용할지 결정한다.

기본 우선순위:

```text
1. 연령 적합성
2. 누리과정 적합성
3. 안전성
4. 원 특성 적합성
5. 놀이성
6. Trend
```

Trend는 항상 하위 우선순위의 가점 요소로 취급한다.

Yearly Theme은 반드시 활성화된 Theme Reference 후보 집합 안에서 Rule이 선택한다.

---

## 7. External Dependency / Fallback

Trend Bot, Weather, 외부 API는 Planning Core의 필수 Dependency가 아니다.

### 반드시 지켜야 하는 원칙

- Trend API가 실패해도 계획안은 생성되어야 한다.
- 외부 API timeout이 발생해도 Core 생성은 실패하지 않아야 한다.
- Optional Context가 없으면 검증된 기본 Reference로 생성한다.
- 외부 기능 장애를 이유로 P0 생성 요청 전체를 5xx 처리하지 않는다.
- Fallback 사용 여부는 Generation Run에서 확인 가능해야 한다.

구현 시 Optional Dependency는 명시적인 Fallback 경로를 갖는다.

---

## 8. Reference 사용 규칙

공식 근거:

- `references/official/`

실측 샘플:

- `references/samples/`

Machine-readable Reference:

- `data/themes/theme_reference_v0.json`
- 이후 승인된 `data/` 하위 Reference

Reference를 런타임에 매번 LLM이 PDF 전체를 읽고 판단하는 구조로 만들지 않는다.

권장 흐름:

```text
공식 PDF / 실측 Sample
        ↓
사람이 검증
        ↓
Machine-readable Reference Data
        ↓
Rule Engine
```

### Theme Reference

Yearly Theme 후보는 `data/themes/theme_reference_v0.json`을 사용한다.

- 사람이 검증하고 version이 부여된 Catalog만 Rule 후보로 활성화한다.
- `PENDING_HUMAN_REVIEW` 상태의 Catalog는 실제 성공 생성 경로에서 활성 Catalog로 취급하지 않는다.
- `applicable_months`는 제품 후보 조건이지 국가가 정한 월별 필수 주제가 아니다.
- `curriculum_links`는 공식 누리과정과의 교육적 연계이며 Theme의 직접 국가 지정 출처가 아니다.
- Domain 코드에 특정 catalog version을 장기 하드코딩하지 않는다. 활성 version은 Reference metadata/config 경계에서 주입한다.
- Theme Reference 내용이 변경되면 기존 version을 덮어쓰지 말고 새 version을 발행한다.

### Reference Version 의미

Theme Item의 Evidence:

```text
source_type    = THEME_REFERENCE
source_id      = theme_id
source_version = 활성 Theme Reference catalog_version
```

Theme Reference가 파생된 원본 Sample / Official 문서는 별도 lineage로 추적한다.

```text
origin_id
→ origins[]의 항목

origins[].sha256
→ upstream 원본 파일 version/hash
```

`origin_id`나 PDF hash를 Theme Item의 canonical `source_id` 대신 사용하지 않는다.

### 금지

- 법령의 수치를 추측해서 코드에 하드코딩하지 않는다.
- 오래된 법령 판본과 최신 판본을 임의로 병합하지 않는다.
- 특정 샘플의 양식을 전국 표준으로 일반화하지 않는다.
- 샘플에 보인 표현을 국가 의무라고 해석하지 않는다.
- 평가 기준과 법적 의무와 기관 관행을 혼동하지 않는다.
- 파일명의 `-`만 보고 혼합연령이라고 추론하지 않는다.
- 쉼표 `,`가 있는 연령 표기를 혼합연령이라고 해석하지 않는다.
- 월간 Template을 연간 Sample과 대조해 공통성 여부를 판단하지 않는다.

---

## 9. Yearly Plan v0 최소 Contract

Yearly Plan v0의 최소 의미 구조:

```text
YearlyPlan
├─ school_year
├─ classroom_ref
└─ month_periods[12]
   ├─ 3월
   ├─ 4월
   ├─ ...
   └─ 다음 해 2월
```

필수 조건:

- `school_year`
- `classroom_ref`
- 정확히 12개의 ordered `month_periods`
- 3월 → 다음 해 2월 순서
- 각 MonthPeriod의 non-blank `theme`
- 편집 가능한 각 Item의 안정적인 `item_id`
- 편집 가능한 각 Item의 안정적인 `semantic_key`

`goals`, `rationale`, `weekly_focus`, 기관 특화 Section 등은 P0 Yearly 최소 Contract에서는 Optional이다.

Plan 소유 단위는 `classroom`이다.

혼합연령 classroom도 연령별 Plan으로 분할하지 않고 classroom당 하나의 Plan을 소유한다.

---

## 10. 계획안 Template 규칙

현재 샘플에서 확인된 특정 격자 구조는 **기본 Template 후보**이지 전국 표준이 아니다.

따라서 DB/도메인 모델을 특정 행 이름이나 고정 열 수에 완전히 묶지 않는다.

권장 개념:

```text
Plan
 └─ Sections
      └─ Slots / Items
```

또는 최신 Application Contract가 요구하는 동등한 의미 구조를 사용한다.

내부 의미를 나타내는 `semantic_key`와 원본 양식의 `source_label`을 분리한다.

### Monthly Template A Guardrail

- 고정 8행 구조를 만들지 않는다.
- 주차 수를 4주 또는 5주로 고정하지 않는다.
- `theme`, dynamic weeks, `outdoor_play`, `safety_education`을 기본 지원한다.
- `goals`, `habits`는 Optional Section이다.
- 성품인사는 Monthly 기본 Section 또는 기본행으로 자동 생성하지 않는다.
- `subtheme`과 `expected_play`를 같은 의미로 자동 병합하지 않는다.
- Section별 `weekly_cells`, `monthly_merged_summary` 형태의 display mode를 허용한다.
- 원본 `source_label`과 내부 `semantic_key`를 분리한다.
- 안전교육의 물리 행 위치를 Domain Rule로 고정하지 않는다.
- 계층형 Label이 있는 Sample은 계층 정보를 보존할 수 있어야 한다.

Template A 검증은 반드시:

```text
Monthly Sample
↔ Monthly Template A
```

형태로 수행한다.

연간·월간·주간 Sample은 각각 같은 문서군끼리 비교한다.

---

## 11. 혼합연령

P0는 혼합연령을 지원한다.

UI 개념:

```text
만 3세
만 4세
만 5세
혼합연령
 - 만 3세
 - 만 4세
 - 만 5세
```

혼합연령은 2개 이상의 서로 다른 지원 연령을 가져야 한다.

혼합연령을 단일 `age_group` 숫자 하나로 표현하는 설계를 피한다.

Activity의 `age_min` / `age_max`와 Classroom의 연령 구성은 서로 다른 개념으로 취급한다.

Theme Reference 후보는 선택된 모든 연령을 지원해야 한다.

### Sample 연령 표기 주의

```text
만3,4,5세
= 한 파일 안에 만3세 / 만4세 / 만5세 단일연령 계획안이 각각 존재할 수 있음

만3/4세
= 실제 만3세 + 만4세 혼합연령반을 뜻하는 표기
```

`-` 표기는 자료에 따라 의미가 다를 수 있으므로 원문 구조 확인 없이 혼합연령으로 단정하지 않는다.

Windows 파일명에서는 `/`를 사용할 수 없으므로 실제 혼합연령반은 다음처럼 명시하는 방식을 권장한다.

```text
혼합_만3+4세
혼합_만4+5세
혼합_만3+4+5세
```

---

## 12. 개인정보 최소화

P0 Planning은 아동 실명 없이도 동작해야 한다.

### P0에서 필요한 반 정보

- 반 이름
- 연령
- 혼합연령 구성
- 원아 수 — optional
- 담임 이름
- 승인된 경우에 한해 반 특성 / 최근 관심 등 Optional Context

아동 명단이 없어도 Planning Core는 정상 동작해야 한다.

개발/테스트 데이터에는 실제 아동 실명을 사용하지 않는다.

생년월일, 성별, 건강정보, 가족정보 등 P0 Planning에 불필요한 아동 개인정보를 수집하지 않는다.

---

## 13. Provenance

Provenance는 하나의 Enum으로 모든 의미를 표현하지 않는다.

다음 세 축을 분리한다.

### 13.1 Evidence Source

생성된 값이 **어떤 근거를 사용했는지** 나타낸다.

허용되는 Source Type:

```text
CURRICULUM
THEME_REFERENCE
PARENT_PLAN
DAYCARE_PROFILE
CLASSROOM_PROFILE
EVENT
SAFETY_RULE
ACTIVITY_REFERENCE
INSTITUTION_SAMPLE
CALENDAR
TREND
EXTERNAL_CONTEXT
```

`INSTITUTION_SAMPLE`은 2026-09-13 Human Decision(OD-N13)으로 추가했다. 승인된 Activity
Reference가 아니라 **실제 기관 계획안 Corpus에서 관찰된 Source**를 Grounding 근거로
참조했을 때 쓴다. `ACTIVITY_REFERENCE`를 대체하지 않는다 — 승인 Catalog에서 고른 값은
계속 `ACTIVITY_REFERENCE`다.

`AI`와 `TEACHER_EDIT`은 Evidence Source가 아니다. **LLM 생성 여부도 Evidence Source가
아니다.** 값이 어떻게 만들어졌는지는 Generation Method(§13.2)로, 그 값이 어느 근거를
썼는지는 Evidence Source로 표현한다. 두 축은 독립이므로
`INSTITUTION_SAMPLE` + `RULE_LLM` 조합은 정상이다.

각 Evidence Source는 최소한 다음 논리 필드를 가진다.

```text
source_type
source_id
source_version?   // optional
effective_date?   // optional
display_name?     // optional
```

Theme Reference를 사용한 Theme Item:

```text
source_type    = THEME_REFERENCE
source_id      = theme_id
source_version = 활성 Theme Reference catalog_version
```

### 13.2 Generation Method

값이 **어떤 방식으로 만들어졌는지** 별도로 기록한다.

```text
RULE_ONLY
RULE_LLM
IMPORTED
MANUAL
```

예:

```text
안전교육 배치
→ RULE_ONLY

Rule이 선택한 내용을 LLM이 자연스럽게 표현
→ RULE_LLM

기존 계획안 업로드
→ IMPORTED

사용자가 Item을 처음부터 직접 작성
→ MANUAL
```

기존 Item을 교사가 수정했다는 이유로 Generation Method를 `MANUAL`로 덮어쓰지 않는다.

LLM 사용 여부는 Evidence Source가 아니라 Generation Method로 표현한다.

적용된 Rule의 `rule_id` / `rule_version`은 Generation Method metadata 또는 동등한 실행 metadata로 추적하고 Evidence Source에 넣지 않는다.

### 13.3 Change / Audit History

교사의 수정과 확정은 Evidence Source와 분리하여 변경 이력으로 관리한다.

최소 Event Type:

```text
CREATED
REGENERATED
TEACHER_EDITED
CONFIRMED
```

교사 수정 후에도 원래 생성에 사용된 Evidence Source는 삭제하지 않는다.

재생성 시 현재 Generation Method는 실제 새 생성 방식으로 갱신하되, 이전 값/방식과 새 값/방식은 `REGENERATED` Audit Event에서 추적할 수 있어야 한다.

최종적으로 다음 질문에 답할 수 있어야 한다.

- 이 값의 근거는 무엇인가?
- 어떤 방식으로 생성되었는가?
- 어떤 상위 계획을 사용했는가?
- 교사가 수정했는가?
- 누가 언제 확정했는가?

DB의 최종 테이블 구조는 `docs/contracts.md` 및 DB 협의 전까지 임의로 확정하지 않는다.

---

## 14. Validation

LLM 출력은 신뢰하지 않고 서버/Application 경계에서 검증한다.

### 공통 최소 검증

- Structured Output Schema 통과 여부
- 필수 필드 누락 여부
- 계획 타입/기간 유효성
- 부모 계획 존재 및 `CONFIRMED` 여부
- Plan 소유 classroom 일치 여부
- 연령 범위 위반 여부
- 존재하지 않는 Reference ID / Version 사용 여부
- 법정/안전 Rule 위반 여부
- 빈 문자열/빈 Item 정책 위반 여부
- 필요한 Provenance 누락 여부
- `item_id` / `semantic_key` 안정 주소 누락 여부

### Yearly 최소 검증

- 정확히 `month_periods[12]`
- 순서가 3월 → 다음 해 2월
- 중복/누락 MonthPeriod 없음
- 각 MonthPeriod의 `theme`가 non-blank
- 각 Theme의 `theme_id`가 활성 Theme Reference에서 resolve
- 각 Theme의 `source_version`이 활성 catalog version과 일치
- 선택된 Theme가 해당 월에 적용 가능
- 선택된 Theme가 classroom의 전체 연령 집합을 지원
- Rule이 선택하지 않은 Theme를 LLM이 새로 생성하거나 교체하지 않음

Validation 실패를 성공으로 저장하거나 조용히 통과시키지 않는다.

---

## 15. Structured Output

LLM 출력은 자유 텍스트 전체 문서가 아니라 구조화된 스키마로 받는다.

예:

```json
{
  "theme_id": "yr_theme_example",
  "value": "봄의 변화를 함께 살펴보아요."
}
```

단, LLM은 `theme_id`를 선택하거나 바꾸지 못한다. Rule에서 선택된 `theme_id`를 입력으로 받아 의미를 유지한 표현만 생성한다.

Pydantic 등 서버/Application 측 스키마 검증을 사용한다.

LLM 출력 형식을 DB 모델과 직접 결합하지 말고 Application Contract를 사이에 둔다.

---

## 16. LLM Wrapper

LLM 공급자와 모델을 도메인 코드에 직접 박지 않는다.

권장:

```text
shared/
└─ llm/
```

또는 프로젝트 컨벤션에 맞는 추상화 계층을 사용한다.

목적:

- 모델 교체
- 공급자 교체
- timeout / retry
- token / cost 측정
- structured output
- logging
- fallback

을 Planning 도메인과 분리한다.

첫 Slice에서는 Rule / Validation 검증을 위해 Fake LLM을 먼저 사용할 수 있다.

실제 LLM Adapter는 Core 규칙과 Golden Test가 안정된 뒤 연결한다.

---

## 17. DB / API 임의 결정 금지

DB Schema와 API Contract가 미확정인 경우 Claude가 편의를 위해 장기 구조를 임의로 확정하지 않는다.

특히 다음은 Source of Truth와 팀 협의를 확인한다.

- PostgreSQL 최종 버전
- Plan hierarchy의 물리 저장 방식
- 혼합연령 저장 방식
- Activity taxonomy
- Template / Section / Item 저장 구조
- Provenance 저장 구조
- LLM 모델 / 공급자
- HTTP endpoint / 공개 오류 코드
- 동시성 제어 방식

필요하면 최소 구현안을 제안하되 `제안`임을 명시하고, 사용자 승인 전 장기 Contract로 확정하지 않는다.

### Port 우선 원칙

Planning Core는 다음 종류의 외부 의존성을 Port로 분리하는 방향을 우선한다.

```text
ThemeReferenceRepository
PlanRepository
LLMPort
Clock
IdGenerator
OptionalContextProvider
```

개발/테스트 단계에서는 다음과 같은 가역 Adapter를 사용할 수 있다.

```text
JsonThemeReferenceRepository
InMemoryPlanRepository
FakeLLM
FixedClock
DeterministicIdGenerator
```

이 Adapter를 최종 PostgreSQL / FastAPI / 실제 LLM 구현과 동일시하지 않는다.

---

## 18. Architecture

현재 구현은 다음 관점을 따른다.

```text
Service-Based Architecture
→ 도메인 경계 사고

Modular Monolith
→ 현재 실제 배포/애플리케이션 형태

Vertical Slice Architecture
→ 기능 구현 단위
```

Annual / Monthly / Weekly를 각각 별도 서비스로 분리하지 않는다.

Planning 도메인 안에서 Vertical Slice로 구현한다.

물리 Folder 구조는 기존 코드베이스 컨벤션을 우선하며, 새 Architecture를 이유로 대규모 이동/리팩터링하지 않는다.

---

## 19. 첫 Vertical Slice

첫 구현 목표:

```text
GenerateYearlyPlan
        ↓
YEARLY DRAFT
        ↓
EditYearlyPlanItem
        ↓
RegenerateYearlyPlanItem
        ↓
ConfirmYearlyPlan
```

핵심 Use Case:

```text
GenerateYearlyPlan
EditYearlyPlanItem
RegenerateYearlyPlanItem
ConfirmYearlyPlan
```

### 상태 규칙

- `GenerateYearlyPlan` 성공 결과는 `DRAFT`
- `EditYearlyPlanItem`은 `DRAFT`에서만 허용
- `RegenerateYearlyPlanItem`은 `DRAFT`에서만 허용
- `ConfirmYearlyPlan`은 유효한 `DRAFT`를 `CONFIRMED`로 전이
- `CONFIRMED`에서 Edit 요청은 차단
- `CONFIRMED`에서 Regenerate 요청은 차단
- Confirm은 opaque `ActorId`를 요구
- 담임 표시 이름은 Confirm Actor ID를 대체하지 못함
- Confirm은 제출/발송을 수행하지 않음

### Regenerate 규칙

- 선택한 Item만 다시 생성한다.
- 선택하지 않은 Item의 `item_id`, 값, Evidence를 보존한다.
- 대상 Item의 `item_id`와 `semantic_key`는 안정적으로 유지한다.
- 새 Theme도 동일 월·연령 조건을 충족하는 활성 Theme Reference 후보여야 한다.
- 전체 Yearly 재생성은 P0에 포함하지 않는다.

첫 Slice가 테스트까지 통과한 뒤 다음 단계로 간다.

```text
GenerateMonthlyPlan
→ Edit
→ Regenerate Item
→ Confirm

GenerateWeeklyPlan
→ Edit
→ Regenerate Item
→ Confirm
```

---

## 20. Golden Set / 테스트 원칙

### Rule

결정론적 Rule은 Unit Test를 작성한다.

최소 예:

- Theme Reference 승인 Gate
- Theme Candidate Filtering
- Age Fit
- Academic month order
- Reference version 검증
- Confirmation Gate
- Parent Plan Validation
- Optional Dependency Fallback
- Regenerate의 비선택 Item 보존
- Confirmed Plan의 Edit/Regenerate 차단

### LLM

문장 전체를 exact match하지 않는다.

다음을 검증한다.

- Schema
- 필수 필드
- Reference 범위
- 선택된 `theme_id` 유지
- 금지된 사실 추가 여부
- Validation 통과 여부

### Golden Set

Yearly 첫 Slice는 다음 파일을 기준으로 검증한다.

```text
tests/golden/yearly_cases.json
```

Golden Set은 최소 다음을 포함한다.

- 만 3세
- 만 4세
- 만 5세
- 혼합연령
- 행사 있음 / 없음
- Optional Context 없음
- Trend timeout / fallback
- 미승인 Theme Reference Gate
- 잘못된 Catalog Version
- 존재하지 않는 Theme ID
- MonthPeriod 누락/중복/순서 오류
- 빈 Theme
- Edit
- Regenerate
- Confirm
- Confirm Actor 누락
- Confirmed 상태 Edit 차단
- Confirmed 상태 Regenerate 차단
- 상위 Plan `CONFIRMED` Gate 실패

Monthly는 Golden을 **두 개** 둔다. 하나가 다른 하나를 대체하지 않는다.

```text
tests/golden/monthly_cases.json       Rule 경로의 기존 동작 (LLM 0회, 완전 결정론)
tests/golden/monthly_llm_cases.json   LLM 경로의 Application 계약
```

LLM Golden이 고정하는 것은 "모델이 무슨 문장을 쓰는가"가 아니라 **"주어진
Proposal에 대해 Application이 무엇을 하는가"**다. FakeLLM에 고정 Proposal을 넣어
결정론을 확보하고, 실제 모델 문장은 expected로 굳히지 않는다. 자연어 품질은
Golden이 아니라 사람이 관찰하는 Live Quality Smoke가 다룬다.

**새 결과가 나왔다는 이유로 expected를 갱신하지 않는다.** 계약이 바뀐 것인지
회귀인지 먼저 판단하고, 계약 변경이면 근거를 보고서에 남긴다.

승인 Artifact(Template / Evidence Store / Activity Catalog / 법정 Rule)의 SHA는
`tests/golden/test_monthly_llm_freeze.py`가 고정한다. Artifact가 바뀌면 Golden이
통과하더라도 **같은 계약이 아니므로** 여기서 먼저 실패해야 한다.

Golden Set 내부 `failure_category`와 `rule_id`는 테스트 의미 식별자이며 공개 HTTP 오류 코드로 자동 승격하지 않는다.

---

## 21. AI 품질 / 비용 / 속도

실제 LLM 호출에는 최소한 다음을 기록할 수 있어야 한다.

- 요청 종류
- 모델
- 입력 토큰
- 출력 토큰
- latency
- 성공 / 실패
- validation 결과
- retry 횟수

API Key, 전체 Prompt, 개인정보를 일반 애플리케이션 로그에 그대로 남기지 않는다.

Fake LLM 테스트 단계에서는 실제 token/cost 기록을 요구하지 않는다.

---

## 22. Import 경계

기존 연간계획안 Import와 부분 생성은 P0 제품 범위에 포함될 수 있으나, 지원 형식 Contract가 승인되기 전 임의 범용 파서를 구현하지 않는다.

- 승인된 지원 형식만 Import한다.
- Import된 기존 작성값은 보존한다.
- 비어 있거나 미작성으로 판정된 기간만 생성한다.
- Import된 Item의 Generation Method는 `IMPORTED`
- 새로 생성된 Item은 실제 생성 방식에 따라 `RULE_ONLY` 또는 `RULE_LLM`
- 지원되지 않은 형식을 LLM 추측 Mapping으로 강행하지 않는다.

지원 형식·Parser 판별·Mapping·빈 기간 판정은 관련 Open Decision이 닫힌 뒤 구현한다.

첫 GenerateYearlyPlan Core Slice 구현을 위해 Import를 선행 구현할 필요는 없다.

---

## 23. 작업 시작 절차

Claude Code는 구현 전에 반드시 다음을 수행한다.

1. `CLAUDE.md` 읽기
2. `docs/demo-source-of-truth.md` 읽기
3. `docs/screen-spec.md` 확인
4. `docs/contracts.md`가 있으면 확인
5. `docs/open-decisions.md` 확인
6. 관련 작업이 Monthly라면 `docs/template-a-validation.md` 확인
7. `references/README.md` 확인
8. 필요한 Reference만 선택적으로 확인
9. 관련 `data/` Reference와 `tests/golden/` Fixture 확인
10. 현재 코드베이스 구조 분석
11. Source of Truth와 코드 Gap 보고
12. 현재 Slice 구현 계획 제시
13. 사용자 승인 후 구현

대규모 리팩터링이나 범위 확장은 임의로 시작하지 않는다.

### 첫 Yearly Slice 착수 시 반드시 확인

```text
data/themes/theme_reference_v0.json
tests/golden/yearly_cases.json
```

Theme Reference가 `PENDING_HUMAN_REVIEW`라면 실제 성공 경로를 운영 활성 상태로 간주하지 않는다.

---

## 24. 애매할 때의 원칙

명세가 모호하거나 서로 충돌하면:

```text
추측해서 구현
```

하지 않고,

```text
충돌 위치
현재 가능한 해석
영향 범위
권장안
```

을 보고한다.

**모호함을 숨기지 않는 것이 임의 구현보다 우선한다.**

---

## 25. 현재 구현 순서

현재 P0 구현은 다음 순서를 기본으로 한다.

```text
1. Theme Reference 최종 사람 검토 / 승인
2. 현재 코드베이스 구조 분석
3. GenerateYearlyPlan Slice 구현 계획
4. 구현 계획 검토 / 승인
5. Domain / Application / Rule / Validation 구현
6. JSON Theme Reference Adapter + InMemory Repository + Fake LLM
7. GenerateYearlyPlan
8. EditYearlyPlanItem
9. RegenerateYearlyPlanItem
10. ConfirmYearlyPlan
11. yearly_cases.json Golden Test 통과
12. 실제 LLM Adapter 연결
13. Yearly Slice 통합 검증
14. Monthly 착수 전 Open Decision 정리
15. Monthly Slice 구현
16. Weekly 착수 전 Open Decision 정리
17. Weekly Slice 구현
```

현재 단계에서 FE/BE 제품 고도화 때문에 AI Planning Core 구현을 지연하지 않는다.
