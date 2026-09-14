# demo-source-of-truth.md — 쓱싹요정 P0 Planning Demo

> 기준일: 2026-09-10  
> 상태: P0 구현 전 제품·도메인 Source of Truth  
> 대상: 만 3세·만 4세·만 5세 및 혼합연령 어린이집 반  
> 범위: 연간 → 월간 → 주간 보육계획안 초안 생성·편집·확정

이 문서는 쓱싹요정 P0에서 **무엇을 만들고 어떤 의미 규칙을 지켜야 하는지**를 정의한다.

구현은 아직 시작하지 않는다. 이 문서와 `docs/screen-spec.md`, `docs/open-decisions.md`의 동기화는 완료됐으며, 별도 착수 승인 후 첫 Vertical Slice를 시작한다.

---

# 0. 문서의 역할

이 문서는 제품 동작과 도메인 의미의 기준이다.

```text
CLAUDE.md
→ 구현 안전 규칙

docs/demo-source-of-truth.md
→ 제품·도메인 의미

docs/screen-spec.md
→ 화면·상태·사용자 동작

docs/contracts.md
→ API·DTO·Persistence Contract

docs/open-decisions.md
→ 미결정 사항·결정 상태·결정 시점

docs/template-a-validation.md
→ Template A 실측 검증 근거

references/README.md → references/official/ → references/samples/
→ Reference 사용 규칙 → 공식 근거 → 실측 자료
```

샘플에 특정 행이나 표현이 있다는 이유만으로 전국 공통 요구사항으로 승격하지 않는다.

---

# 1. 적용 우선순위

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

충돌이 발견되면 구현자가 임의로 해석하지 않고 충돌 위치, 가능한 해석, 영향 범위, 권장안을 보고한다.

---

# 2. P0 목표

P0의 목표는 다음 흐름이 실제로 이어지는 Planning Demo를 완성하는 것이다.

```text
GenerateYearlyPlan
→ YEARLY DRAFT
→ Teacher Edit
→ YEARLY CONFIRMED
→ GenerateMonthlyPlan
→ MONTHLY DRAFT
→ Teacher Edit
→ MONTHLY CONFIRMED
→ GenerateWeeklyPlan
→ WEEKLY DRAFT
→ Teacher Edit
→ WEEKLY CONFIRMED
```

핵심 가치는 문서 세 개를 독립적으로 생성하는 데 있지 않다.

> 공식 교육과정과 우리 원·우리 반의 정보를 근거로 초안을 만들고, 교사가 확정한 상위 계획을 Context와 Constraint로 이어받아 다음 단계 계획을 구체화한다.

---

# 3. P0 포함 범위

- 원 정보 입력
- 반 정보 입력
- 만 3세·만 4세·만 5세
- 혼합연령 지원
- 연간 계획안 생성·편집·셀 단위 재생성·확정
- 승인된 지원 형식의 기존 연간계획안 Import
- Import된 기존 기간 보존과 미작성 잔여 기간 생성
- 월간 계획안 생성·편집·셀 단위 재생성·확정
- 주간 계획안 생성·편집·셀 단위 재생성·확정
- 상위 계획 Confirmation Gate
- Rule 기반 배치·후보 선별
- LLM 기반 최종 표현
- Structured Output 검증
- 생성 근거 표시
- 생성 방식 기록
- 교사 수정·확정 Audit
- Optional 외부 기능의 Fallback

---

# 4. P0 제외 범위

- 보육일지
- 관찰일지
- 알림장
- 아동별 발달평가
- 평가제 전체 자동 대조
- 위험 신호 판정
- HWP 직접 쓰기
- 자동 제출·자동 발송
- 결제·앱스토어 출시
- 만 0~2세 영아반
- 활동 이력 기반 개인화 추천
- 승인된 지원 형식 목록 밖 기관 고유 양식의 범용 자동 파싱

범위 밖 기능은 구현 편의를 이유로 추가하지 않는다.

---

# 5. 핵심 사용자 흐름

```text
온보딩
  ↓
원 정보 + 반 정보 등록
  ↓
계획안 최초 설정
  ├─ 신규 Yearly 생성
  └─ 지원 형식의 기존 Yearly Import + 잔여 기간 생성
  ↓
연간 DRAFT 생성
  ↓
칸 편집 / 이 칸만 다시 생성 / 출처 확인
  ↓
교사 CONFIRMED
  ↓
월간 DRAFT 생성
  ↓
교사 CONFIRMED
  ↓
주간 DRAFT 생성
  ↓
교사 CONFIRMED
```

자동 확정은 없다. `CONFIRMED`는 외부 제출 또는 발송을 뜻하지 않는다.

---

# 6. Plan 상태와 Confirmation Gate

Plan의 핵심 상태는 두 개만 둔다.

```text
DRAFT
CONFIRMED
```

Generation/UI 상태는 Plan 상태와 분리한다.

```text
EMPTY
GENERATING
GENERATION_PARTIAL
ERROR
```

필수 Gate:

- 연간 계획안이 `CONFIRMED`가 아니면 월간 계획안을 생성하지 않는다.
- 월간 계획안이 `CONFIRMED`가 아니면 주간 계획안을 생성하지 않는다.
- 모든 생성 및 재생성 결과는 `DRAFT`다.
- Import 결과와 잔여 기간 생성 결과도 하나의 `DRAFT`로 저장한다.
- P0의 `CONFIRMED`는 읽기 중심이며 편집을 차단한다.
- 확정 취소·재편집·새 Version 정책은 OD-N06에서 후속 결정한다.

---

# 7. Plan 소유권 — OD-Y03 최종 결정

**상태: `RESOLVED_FOR_P0`**

P0에서 모든 Plan의 소유 단위는 `classroom`이다.

```text
daycare
  └─ classroom
       └─ yearly / monthly / weekly plans
```

- `daycare` 귀속은 `classroom`을 통해 추적한다.
- 연간·월간·주간 Plan은 모두 반 단위 Context로 생성하고 조회한다.
- 혼합연령도 연령별 Plan 여러 개로 쪼개지 않고 **하나의 classroom Plan**을 생성한다.
- 포함 연령 집합은 Plan 생성 Context이며, 단일 `age_group` 숫자로 축소하지 않는다.
- 물리 FK와 멀티테넌시 구현은 `docs/contracts.md`에서 확정하되 논리 소유권은 변경하지 않는다.

---

# 8. Confirm Actor — OD-Y03 최종 결정

**상태: `RESOLVED_FOR_P0`**

Plan 확정 행위자는 표시용 담임 이름이 아니라 opaque 식별자로 기록한다.

```text
actor_id 또는 user_id
```

- `confirmed_by`에 담임 이름 문자열을 저장하지 않는다.
- Application Use Case는 `ActorId`를 입력받는다.
- 인증 구현이 없더라도 테스트용 Actor를 명시적으로 주입한다.
- 최소 Audit Event는 `event_type`, `occurred_at`, 필수 `plan_id`, 선택 `item_id`, 그리고 사람의 opaque `actor_id/user_id` 또는 시스템 행위자 Marker를 가진다.
- 표시 이름은 필요하면 별도 Profile에서 조회하며 Audit Identity와 혼동하지 않는다.

---

# 9. 원 정보

P0에서 필요한 원 정보:

| 필드 | 필수 | 비고 |
|---|---:|---|
| 원명 | 예 | 표시 문자열 |
| 원장 이름 | 예 | 표시·관리용 Context이며 Confirm Actor가 아님 |
| 지역 | 예 | 기후 Context용. 표시명과 내부 식별값 분리 가능 |
| 교육 강조 방향 | 아니요 | 후보 가중치 |
| 운영 철학 | 아니요 | 자유 입력 또는 검증된 태그 |
| 특성화 프로그램 | 아니요 | Optional Context |
| 회피 소재 | 아니요 | 후보 제외 조건 |
| 원 행사·운영 캘린더 | 아니요 | 미입력 시에도 Core 생성 가능 |

원 프로파일과 연도별 운영 캘린더는 분리한다.

- `원장 이름`은 화면 표시와 관리 Context에만 사용하며 `confirmed_by` 또는 Audit Identity로 사용하지 않는다.
- `교육 강조 방향`, `운영 철학`, `특성화 프로그램`, `회피 소재`는 `온보딩 > 원 정보`에서 선택 입력하고 원 Profile로 저장한다.
- 계획안 최초 설정 화면은 저장된 Optional 원 Profile을 Context로 불러오며, 사용자는 생성 전에 적용 여부와 값을 확인·수정할 수 있어야 한다.
- 성품인사는 `온보딩 3/3`에서 별도의 선택적 원/반 Profile Context로 입력한다. 1~12월 값이 존재해도 Monthly Template A에 `character_greeting` 행을 자동 생성하지 않으며, 명시적으로 활성화된 Custom Section Mapping이 있을 때만 출력한다.

---

# 10. 반 정보와 혼합연령

P0에서 필요한 반 정보:

| 필드 | 필수 | 비고 |
|---|---:|---|
| 반 이름 | 예 | Plan 소유 단위 표시 |
| 연령 | 예 | 만 3세 / 만 4세 / 만 5세 / 혼합연령 |
| 혼합 연령 집합 | 조건부 | 혼합연령이면 2개 이상 |
| 현재 원아 수 | 아니요 | 0 이상의 정수 |
| 담임 이름 | 예 | 표시 정보이며 Actor ID가 아님 |
| 반 특성 | 아니요 | Optional Context |
| 최근 관심 | 아니요 | 수시 변경 Context |

`반 특성`과 `최근 관심`은 `온보딩 > 반 정보`에서 선택 입력한다. 계획안 최초 설정 화면은 저장된 값을 생성 Context로 불러오고, 사용자가 생성 전에 확인·수정할 수 있게 한다. 수정된 `최근 관심`은 이후 생성 Run부터 적용하며 이미 확정된 Plan을 소급 변경하지 않는다.

```text
classroom age composition
≠
activity age_min / age_max
```

샘플 파일명 해석 시 쉼표 `,`는 파일 안의 여러 단일연령 Plan을, 슬래시 `/`는 실제 혼합연령을 뜻할 수 있으므로 원문과 내부 Metadata를 함께 확인한다.

---

# 11. 개인정보 최소화

- 아동 명단 없이 Planning Core가 정상 동작해야 한다.
- 개발·테스트 데이터에 실제 아동 실명을 사용하지 않는다.
- 생년월일, 성별, 건강정보, 가족정보 등 Planning P0에 불필요한 개인정보를 수집하지 않는다.
- 개인 지원이 필요한 경우에도 P0에서는 가능한 범위에서 반 단위 운영 고려사항으로 표현한다.

---

# 12. Reference Data

Reference는 런타임에 PDF 전체를 LLM이 매번 읽고 판단하는 방식으로 사용하지 않는다.

```text
공식 PDF / 실측 Sample
        ↓
사람 검증
        ↓
Machine-readable Reference Data
        ↓
Rule Engine
```

P0 Reference 유형:

- 2019 개정 누리과정
- 사람이 검증한 Theme Reference v0
- 검증된 놀이·활동 후보
- 원·반 Profile
- 원 행사·운영 Calendar
- 법정 안전교육 Rule
- 안전교육 월 배치 Policy
- Calendar / WeekPeriod
- Optional Trend / Climate / Weather Context

모든 versioned Reference는 가능한 경우 해당 Reference 자체의 식별자, `source_version`, `effective_date`를 가진다. Item에 연결되는 Evidence Source의 정규 필드는 §22를 따른다.

---

# 13. Rule / LLM 경계

```text
Rule
→ 무엇을 어디에 넣을지 결정

LLM
→ 이미 선택된 내용을 자연스럽게 표현
```

Rule이 담당한다.

- Section과 Item 역할
- Theme와 Activity 후보 선택
- 연령·누리과정·안전성 필터
- 행사·Calendar 반영
- 법정 안전교육 제약 검증
- 안전교육 월 배치 정책 적용
- 상위 Plan Context·Constraint 적용
- 원 특성 및 Optional Context 적용 여부

LLM은 다음만 담당한다.

- Rule이 선택한 Theme·활동·목표의 자연스러운 문장화
- 사용자에게 보여줄 표현 다듬기
- 정해진 Structured Output Schema의 문자열 생성

LLM이 법정 기준, 슬롯 배치, Theme 후보, 연령 적합성, 안전성, 존재하지 않는 행사·사실을 자유롭게 결정하게 하지 않는다.

---

# 14. Yearly Plan v0 — OD-Y01 최종 결정

**상태: `RESOLVED_FOR_P0`**

Yearly Plan v0의 최소 의미 구조는 다음과 같다.

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

- `school_year`는 3월부터 다음 해 2월까지의 학년도를 뜻한다.
- `classroom_ref`는 §7의 Plan 소유 반을 가리킨다.
- `month_periods`는 정확히 12개의 ordered `MonthPeriod`를 가진다.
- 첫 기간은 해당 학년도 3월, 마지막 기간은 다음 해 2월이다.
- 각 `MonthPeriod`의 `theme`는 필수다.
- 나머지 `goals`, `rationale`, `weekly_focus`, 기관 특화 Section은 Optional이다.
- 연간 주차 하위항목은 가변 길이 Optional Item 집합이며 4주·5주를 강제하지 않는다.

편집·재생성·근거 연결의 안정 주소:

```text
item_id
semantic_key
```

- 모든 편집 단위는 안정적인 `item_id`를 가진다.
- `semantic_key`는 의미상 위치를 나타낸다.
- 표시 Label, 배열 순번, DB 컬럼명을 편집 주소로 사용하지 않는다.
- LLM DTO는 Application Contract이며 물리 DB 모델과 직접 결합하지 않는다.

예시:

```json
{
  "school_year": 2026,
  "classroom_ref": "classroom_opaque_id",
  "month_periods": [
    {
      "period_key": "2026-03",
      "theme": {
        "item_id": "item_opaque_id",
        "semantic_key": "yearly.month.03.theme",
        "value": "우리 원과 새로운 친구"
      }
    }
  ]
}
```

위 예시는 의미 구조를 보여주기 위한 것이며 최종 HTTP·DB Contract는 아니다.

---

# 15. Theme Reference v0 — OD-Y02 최종 결정

**상태: `RESOLVED_FOR_P0`**

국가 누리과정은 월별 고정 주제를 지정하지 않는다. 따라서 Yearly Theme 후보는 사람이 검증한 versioned `Theme Reference v0`에서 가져온다.

최소 후보 필드:

```text
theme_id
label
applicable_months
age_conditions
curriculum_links
origin_id
source_version
```

처리 원칙:

```text
Theme Reference v0
        ↓
Rule이 적용 가능한 후보를 필터·선택
        ↓
LLM은 선택된 Theme의 표현만 다듬음
        ↓
Schema / Reference / Provenance 검증
```

- LLM이 Theme를 백지에서 자유 생성하지 않는다.
- Theme Reference는 사람이 검증하고 Version을 고정한다.
- `applicable_months`는 후보 적용 조건이지 국가가 정한 월별 필수 주제라는 뜻이 아니다.
- 누리과정 연결은 교육적 연계이며 월별 Theme의 직접 출처라고 과장하지 않는다.
- Theme Reference를 사용한 Theme Item의 Evidence Source는 `THEME_REFERENCE`로 기록한다.
- 이때 Evidence Source의 `source_id`는 `theme_id`다.
- `origin_id`는 Theme Reference가 상위 공식 자료나 검증 자료에서 유래한 경로를 나타내는 upstream lineage metadata이며, Item Evidence Source의 `source_id`를 대신하지 않는다.

---

# 16. Yearly 생성·편집·확정 동작

```text
원·반 정보
+ Calendar
+ Theme Reference v0
+ Curriculum links
+ Optional 행사 Context
        ↓
Rule 후보 선택
        ↓
LLM 표현 정리
        ↓
Validation
        ↓
YEARLY DRAFT
```

- 생성된 12개 Theme Item은 개별 편집 가능하다.
- `이 칸만 다시 생성`은 선택한 Item만 변경한다.
- 다른 Item과 교사 편집값은 보존한다.
- 전체 재생성은 P0에 포함하지 않는다.
- 확정 시 §8의 Actor와 Audit Event를 기록한다.

지원 형식의 기존 Yearly Import도 같은 의미 구조로 정규화한다.

- Importer는 승인된 지원 형식만 받으며 지원 여부를 사전에 판별한다.
- Import된 기존 `MonthPeriod`와 교사 작성값은 보존한다.
- 비어 있거나 미작성으로 판정된 잔여 기간만 생성하며, 기존 값을 암묵적으로 덮어쓰지 않는다.
- Import된 Item은 Generation Method `IMPORTED`, 새로 생성된 Item은 실제 생성 방식에 따라 `RULE_ONLY` 또는 `RULE_LLM`으로 기록한다.
- 지원 형식 목록, Parser 판별, 필드 Mapping, 빈 기간 판정, 정규화 실패 처리는 OD-N09에서 Import Slice 착수 전에 확정한다.
- 지원 형식 밖 임의 기관 양식을 추론해 범용 파싱하는 것은 P0 범위가 아니다.

---

# 17. Plan / Section / Item 공통 구조

특정 행 이름을 물리 Schema로 고정하지 않는다.

```text
Plan
└─ Sections
   ├─ semantic_key
   ├─ source_label
   ├─ display_mode
   └─ Items
      ├─ item_id
      ├─ semantic_key
      ├─ value
      └─ provenance
```

- 내부 의미와 화면 Label을 분리한다.
- 원본 양식의 Label을 보존한다.
- `source_label`은 원본 Template Label과 `semantic_key`의 Mapping을 보존하는 Metadata다. Evidence Source의 `source_id`나 `display_name`으로 사용하지 않는다.
- 같은 의미라도 기관별 표시 Label이 다를 수 있다.
- Section과 Item 수는 Plan Type·기간·Template에 따라 달라질 수 있다.

---

# 18. Monthly Template A v0 Guardrail

월간 실측 재검증 결과, Template A를 고정 `8행 × 고정 주차 열`로 정의할 근거는 없다.

P0에서 확정된 기준:

- 고정 8행 구조를 금지한다.
- 월 주차 수를 4주 또는 5주 상수로 고정하지 않는다.
- `theme`, dynamic weeks, `outdoor_play`, `safety_education`을 기본 지원한다.
- `goals`, `habits`는 Optional Section이다.
- `Optional`은 required 또는 non-empty가 아니며, 비활성화된 Section은 출력에서 생략한다는 뜻이다. 활성화됐지만 비어 있는 Section의 렌더링 정책은 OD-M01에서 확정한다.
- 성품인사는 월간 기본행에서 제거한다.
- 온보딩 Profile의 월별 성품인사 값은 선택 Context일 뿐 Monthly 기본행 생성 근거가 아니다.
- `subtheme`과 `expected_play`는 같은 의미로 자동 병합하지 않는다.
- Section별로 `weekly_cells`와 `monthly_merged_summary`를 허용한다.
- 원본 Label을 보존하고 내부 `semantic_key`에 Mapping한다.
- 안전교육을 항상 n번째 행에 둔다는 가정을 금지한다.

여기서 **기본 지원**은 다음을 뜻한다.

> Template과 Renderer가 해당 의미를 표현할 수 있어야 한다.

전국 필수, 모든 기관 필수, 모든 Cell의 non-empty를 뜻하지 않는다.

---

# 19. Monthly Section 의미와 Mapping

| 내부 의미 | P0 처리 | 가능한 원본 Label | 표시 방식 |
|---|---|---|---|
| `theme` | 기본 지원 | 주제, 중점놀이 | 월간 요약 또는 Template 정의 |
| `outdoor_play` | 기본 지원 | 바깥놀이, 실외놀이 | `weekly_cells` 또는 `monthly_merged_summary` |
| `safety_education` | 기본 지원 | 안전교육 | `weekly_cells` 또는 `monthly_merged_summary` |
| `goals` | Optional | 목표, 보육목표 | Template 정의 |
| `habits` | Optional | 기본생활습관 | Template 정의 |
| `character_greeting` | 월간 기본행 아님 | 성품인사 | 명시적으로 활성화된 Custom Section Mapping만 허용 |
| `subtheme` | 관계 미확정 | 소주제, 놀이 소주제 | OD-M03 전 자동 병합 금지 |
| `expected_play` | 관계 미확정 | 예상놀이 | OD-M03 전 자동 병합 금지 |

`subtheme`과 `expected_play`의 관계는 다음 중 어느 것도 아직 확정하지 않는다.

```text
완전 동의어
상·하위 관계
서로 다른 의미
기관별 조건부 Mapping
```

따라서 Mapping 시 `source_label`, `mapping_confidence`, 수동 Override를 보존한다.

---

# 20. Dynamic WeekPeriod와 display_mode

월간 Plan의 주차는 Calendar Rule이 ordered `WeekPeriod` 목록으로 반환한다.

최소 의미:

```text
week_id
start_date
end_date
display_label
```

- 주차 개수를 상수로 두지 않는다.
- 대상 기간과 기관 운영 Calendar에서 동적으로 산출한다.
- `week_id`, `start_date`, `end_date`, `display_label`의 논리적 존재는 P0 의미 구조로 확정한다.
- 월 경계와 부분 주 처리, 휴원일 반영, 주차 계산 규칙, `week_id` 생성 형식·안정성, 수동 Override 정책은 OD-M02에서 확정한다.

각 Section은 독립적인 표시 방식을 가질 수 있다.

```text
weekly_cells
monthly_merged_summary
```

예를 들어 같은 `safety_education`이라도 한 기관은 주별 Cell, 다른 기관은 월간 병합 Summary를 사용할 수 있다. 데이터 의미와 화면 위치를 분리한다.

---

# 21. 상위 Plan 계승 규칙

확정된 상위 Plan은 하위 Plan 생성의 `Context / Constraint`다.

```text
Confirmed Yearly
→ Monthly Context / Constraint

Confirmed Monthly
→ Weekly Context / Constraint
```

다음을 하드코딩하지 않는다.

```text
YEARLY.theme
→ MONTHLY 특정 Cell에 문자 그대로 복사
```

기관별 실측에서 상위 계획의 세분화 수준과 실제 월간 전개가 달랐다. 교사가 확정한 의미와 방향은 우선하되, 특정 하위 Cell의 직접 복사를 전국 공통 규칙으로 만들지 않는다.

## 21.1 Yearly → Monthly Contract — 2026-09-11 확정

`parent_yearly_theme_id`는 **immutable parent anchor**다.

하지만 다음은 **강제하지 않는다.**

```text
Yearly value / theme
→ Monthly Cell에 문자 그대로 1:1 복사
```

Monthly에서 세부 theme / focus가 **분화될 수 있다.**

확정 규칙 3가지:

- `parent_yearly_theme_id` **교체 금지**
- lineage **보존**
- **LLM이 parent theme을 교체하면 Validation 실패**

실측 근거는 docs/template-a-validation.md §3.4다. 판독 10기관 중 4기관이 한 월간계획안에
2개 주제를 병기하며, 공립아이사랑어린이집은 같은 기관·같은 달인데 만3세는 1주제,
만4·5세는 2주제다. 시립새봄은 연간 1행에서 4개 반이 서로 다른 월 주제를 골랐다.
따라서 상위 theme을 하위 Cell에 문자 그대로 복사하도록 강제하면 실측과 모순된다.

### ParentYearlyLineage — Contract proposal

아직 코드로 만들지 않는다. 다음 필드를 제안 상태로 남긴다.

```text
ParentYearlyLineage
├─ parent_yearly_plan_id
├─ parent_yearly_period_key
├─ parent_yearly_theme_id
├─ parent_yearly_value          display / audit snapshot. Monthly Cell 복사용이 아니다
├─ reference_catalog_id
├─ reference_version
├─ confirmed_at
└─ confirmed_by
```

Provenance 3축은 유지하고 **4번째 축을 만들지 않는다.** lineage는 1축 Evidence Source로
표현한다. `EvidenceSourceType.PARENT_PLAN`이 이미 존재한다.

### Monthly 생성 Context에 추가로 필요한 값

```text
school_year        1·2월이 school_year + 1이므로 target_month만으로 역산할 수 없다
target_month
ages
age_mode
daycare_ref
classroom_ref
```

`institution event`는 Yearly에서 **상속할 수 없다.** 현재 Yearly Plan Aggregate는 행사를
저장하지 않으므로 Monthly 생성 시 다시 입력받아야 한다. safety rule context는 상속이 아니라
Rule 계층에서 versioned data로 주입한다.

## 21.2 Monthly Edit / Regenerate 최소 단위 — 2026-09-11 확정

P0 Edit / Regenerate 최소 단위는 다음으로 확정한다.

```text
WeekPeriod × Section Cell
```

- **전체 Month regenerate는 P0에 없다.** docs/screen-spec.md §5.3의 전체 재생성 금지와 동일하다.
- **개별 activity 배열 순번을 address로 사용하지 않는다.**
- 현재 `ItemAddress` Contract를 가능한 한 재사용한다. 단 week 식별을 문자열 순번에 취약하게
  넣지 않는지 검토한 뒤 M1 설계에서 최종 DTO를 제안한다.
- `monthly_merged_summary` Section의 Cell은 week에 속하지 않으므로 week 없는 주소를 표현할 수
  있어야 한다.

Use Case 이름은 Yearly 규약을 따른다.

```text
GenerateMonthlyPlan
EditMonthlyPlanItem
RegenerateMonthlyPlanItem
ConfirmMonthlyPlan
```

## 21.3 Monthly LLM 기본 방향 — 2026-09-11 확정

Monthly LLM은 **한 달 전체 1회 Batch**를 기본안으로 확정한다.

```text
Rule / Reference
→ selected canonical cells
→ LLM 표현
→ Structured Output
→ reconcile
→ validation
→ save
```

LLM은 다음을 **결정하지 않는다.**

```text
Parent Yearly Theme 교체
WeekPeriod 생성 / 삭제
Section 생성 / 삭제
Activity 후보 최종 선택
연령 적합성
안전성
법정 수치
안전교육 월 / 주 배치
법적 충족 여부
존재하지 않는 행사 / 사실
```

**모델 ID는 Domain에 하드코딩하지 않는다.** 공급자·모델·timeout·retry는 OD-N04 범위이며
설정 경계에서 주입한다.

법정 수치를 LLM 프롬프트에 넣지 않는다. LLM에는 이미 선택된 Cell과 표현 대상 문구만
전달하고 법정 충족 판정은 Rule이 데이터로 계산한다.

---

# 22. Provenance — Evidence Source / Generation Method / Audit History

Provenance는 하나의 Enum으로 표현하지 않는다. 다음 세 축을 분리한다.

## 22.1 Evidence Source

값이 **어떤 근거를 사용했는지** 나타낸다.

```text
CURRICULUM
THEME_REFERENCE
PARENT_PLAN
DAYCARE_PROFILE
CLASSROOM_PROFILE
EVENT
SAFETY_RULE
ACTIVITY_REFERENCE
CALENDAR
TREND
EXTERNAL_CONTEXT
```

각 Item은 `EvidenceSource[]`를 `0..N`개 가진다. 근거가 없는 최초 수동 입력은 빈 배열을 허용하며, 근거가 하나 이상이면 각 항목을 다음 정규 필드로 기록한다.

```text
source_type
source_id
source_version   (optional)
effective_date   (optional)
display_name     (optional)
```

- `source_type`과 `source_id`는 Evidence가 존재하는 각 항목의 필수 필드다.
- `display_name`은 UI 표시용이며 식별이나 무결성 판단에 사용하지 않는다.
- Theme Reference Evidence는 `source_type = THEME_REFERENCE`, `source_id = theme_id`, 필수 `source_version`으로 기록한다.
- Theme Reference의 `origin_id`는 upstream lineage metadata이며 Evidence의 `source_id`가 아니다.
`AI`와 `TEACHER_EDIT`은 Evidence Source가 아니다.

## 22.2 Generation Method

값이 **어떤 방식으로 만들어졌는지** 나타낸다.

```text
RULE_ONLY
RULE_LLM
IMPORTED
MANUAL
```

LLM 사용 여부는 Evidence가 아니라 Generation Method다.

- 각 Item의 현재 값은 하나의 Generation Method를 가진다.
- `RULE_ONLY`와 `RULE_LLM`에는 적용한 Rule을 추적할 수 있도록 Generation Method 상세에 `rule_id`, `rule_version`을 기록한다. 이는 별도의 네 번째 Provenance 축이 아니다.
- `IMPORTED`는 승인된 외부 문서에서 정규화해 만든 최초 값에 사용한다.
- `MANUAL`은 사람이 최초부터 직접 만든 값에만 사용한다.
- `RULE_ONLY`, `RULE_LLM`, `IMPORTED` 또는 `MANUAL`로 만들어진 값을 교사가 수정해도 그 시점의 Generation Method를 `MANUAL`로 덮어쓰지 않고 Audit History에 `TEACHER_EDITED`를 추가한다.
- Item을 재생성하면 현재 값의 Generation Method를 실제 재생성 방식으로 갱신하고, 이전·새 값과 이전·새 Method를 `REGENERATED` Audit Event에 보존한다.

## 22.3 Audit History

값 또는 Plan에 **어떤 변경 행위가 있었는지** 나타낸다.

```text
CREATED
REGENERATED
TEACHER_EDITED
CONFIRMED
```

Audit History는 시간순으로 정렬된 `AuditEvent[]`다. 각 Event의 최소 필드는 다음과 같다.

```text
event_type
occurred_at
plan_id
item_id       (optional; Item 단위 Event일 때 사용)
actor_id 또는 user_id   (사람 행위자)
system_actor            (시스템 행위자 Marker)
```

- 사람 Event는 opaque `actor_id` 또는 `user_id`를 기록하고, 시스템 Event는 명시적인 `system_actor` Marker를 기록한다. 표시 이름 문자열을 Actor 식별자로 대체하지 않는다.
- 교사 수정 후에도 원래 Evidence Source를 삭제하지 않는다.
- 재생성 전 값과 새 값을 Audit으로 추적한다.
- `TEACHER_EDITED`는 Evidence Source `TEACHER_EDIT`로 변환하지 않는다.
- 확정 Event에는 §8의 opaque Actor ID와 시간을 기록한다.

최종적으로 다음 질문에 답할 수 있어야 한다.

- 이 값의 근거는 무엇인가?
- 어떤 방식으로 생성되었는가?
- 어떤 상위 Plan을 사용했는가?
- 누가 무엇을 수정했는가?
- 누가 언제 확정했는가?

---

# 23. 안전교육

법정 제약과 월 배치 정책을 분리한다.

```text
Legal Constraint
≠
Monthly Placement Policy
```

- 법정 실시 간격·누적시간은 versioned `SAFETY_RULE` 데이터로 관리한다.
- 어느 월·주에 배치할지는 별도 제품 또는 기관 운영 Policy다.
- `legal_rule_version`과 `placement_policy_version`을 분리한다.
- 안전교육 Item은 실제 week/date를 보존한다.
- 화면 표시 방식은 Template Section의 `display_mode`가 결정한다.
- `emergency_response`와 `drill`은 관계가 확정될 때까지 별도 semantic key를 허용한다.
- LLM은 선택된 내용의 표현만 정리한다.

안전교육 연간계획안 파일이 없다는 사실 자체는 초기 설정이나 Yearly Core를 차단하지 않는다.

OD-M04는 2026-09-11에 `RESOLVED_FOR_P0`로 확정됐다. 확정 내용은 다음이다.

- 법령 Rule은 **법정 구분 / 실시 간격 / 연간 최소 시간 / 적용 연령·대상 / source·version만** 저장한다.
- **법령 데이터에 특정 월 assignment를 만들지 않는다.**
- Rule은 법정 조건을 **검증**하며 특정 월·주 배치를 **자동 창작하지 않는다.**
- 배치 Source는 ① 기관·교사가 제공한 안전교육 연간계획 ② 교사 직접 입력이다.
- 둘 다 없으면 임의 월 배치 생성, LLM 배치 생성, 법적 충족 주장을 모두 금지한다. Safety Section은 구조적으로 존재·표현 가능하되 값이 없을 수 있고, `법정 요건 미검증 / source required` 상태를 표현할 수 있어야 한다.
- **제품 기본 safety placement policy는 P0에서 발행하지 않는다.** 따라서 “확정된 최소 폴백”은 존재하지 않으며 그렇게 부르지 않는다.
- 비법정 기관 label(`생활안전`, `심폐소생술`, `장애인식 개선`, `소방안전`, `비상대응` 등)을 법정 6구분으로 자동 매핑하지 않는다.
- `emergency_response`와 `drill`을 `safety_education`에 자동 병합하지 않고 별도 semantic key를 유지한다.

**우회 금지 조항의 P0 해석**은 docs/screen-spec.md §20.1에 있다. 요약하면 M1 구조 Slice는
허용하되 placement 자동 생성·source 없는 내용 생성·법적 충족 claim은 금지한다.

법정 근거 판본은 `references/official/아동복지법_시행령_별표6_교육기준_2022개정.pdf`
`<개정 2022. 6. 21.>`이며 `references/official/2026_보육사업안내_본문.pdf`의 안전교육 기준
표와 6구분·주기·시간이 일치한다. Machine-readable transcription은
`data/rules/safety_education_legal_v1.json`이고 현재 `PENDING_HUMAN_REVIEW`다.

`법정 요건 미검증 / source required` 상태를 DTO·GenerationRun에서 어떻게 표현할지는
M1 설계 전에 제안하고 승인받는다.

---

# 24. Weekly Plan

Weekly Plan은 Confirmed Monthly Plan의 해당 기간을 Context와 Constraint로 사용한다.

현재 확정된 원칙:

- 물리 18칸 또는 고정 요일·Slot 수를 가정하지 않는다.
- 하나의 semantic WeeklyPlan과 출력 위치별 Adapter를 분리한다.
- 혼합연령은 같은 놀이 안에서 참여 수준과 교사 지원 수준을 조정한다.
- 날씨는 실제 날짜가 있는 Weekly에서만 본격적으로 반영한다.
- Weather 실패 시 기본 계획을 생성하고 대체 제안을 생략하거나 안전한 기본값을 사용한다.

별도 주간계획안·주간보육일지 계획칸·일일보육일지 계획칸은 OD-W02의 출력 Adapter 후보다. OD-W02 승인 전에는 어느 후보도 실행 가능한 설정으로 간주하지 않는다. 보육일지 계획칸 Adapter는 계획 결과를 해당 위치에 렌더링하는 범위이며, P0 제외 범위인 전체 보육일지 생성 기능을 포함하지 않는다.

월간 미사용 경로는 OD-W01, Canonical Output과 첫 Adapter는 OD-W02에서 주간 구현 전에 확정한다.

---

# 25. Optional 외부 Context와 Fallback

Trend Bot, Weather API, 지역별 Climate Profile은 Planning Core의 필수 Dependency가 아니다.

```text
Trend 실패
→ 검증된 기본 Reference만 사용

Weather 실패
→ 날씨 반영 없이 Weekly 생성

Climate 정보 없음
→ 기본 계절 Context 사용
```

- Optional Context 부재를 이유로 전체 생성 요청을 5xx 처리하지 않는다.
- 외부 소재는 검증·승인된 후보만 사용한다.
- Trend는 연령 적합성·누리과정 적합성·안전성·원 특성·놀이성보다 낮은 우선순위의 가점 요소다.
- Fallback 사용 여부는 Generation Run에서 확인 가능해야 한다.

## 25.1 Monthly Optional Context — 2026-09-11 확정

기존 `OptionalContextProvider` 재사용 방향을 승인한다. Monthly 전용 Provider를 새로 만들지
않는다.

Weather / Climate / Trend / 외부 검색은 **P1 optional enrichment**다.

**없음 / 실패 / timeout이어도 P0 Monthly 생성이 실패하면 안 된다.**

Yearly에서 쓰는 `OptionalContextResult` / `OptionalContextStatus`는 실패를 예외가 아니라
결과 객체로 표현하므로 Monthly에서도 그대로 쓸 수 있다. LLM 실패는 Optional Fallback이
아니므로 `fallbacks_used`에 넣지 않는다.

---

# 26. Validation

LLM 출력을 신뢰하지 않고 서버 측에서 검증한다.

최소 검증:

- Structured Output Schema
- 필수 필드 누락
- Plan Type과 기간
- Yearly `month_periods[12]`와 3월~다음 해 2월 순서
- 각 MonthPeriod의 필수 `theme`
- 부모 Plan 존재 및 `CONFIRMED` 여부
- Plan 소유 classroom 일치
- 연령 범위
- 존재하는 Reference ID와 Version
- 법정·안전 Rule
- 빈 문자열·빈 Item 정책
- `item_id` / `semantic_key` 안정 주소
- 필요한 Evidence Source / Generation Method / Audit History 누락

Validation 실패를 성공으로 저장하거나 조용히 통과시키지 않는다.

---

# 27. DB 기준

- 장기 물리 Schema를 구현 편의로 임의 확정하지 않는다.
- Application Contract와 Persistence Model을 분리한다.
- Plan / Section / Item의 의미 구조를 특정 Template의 행 이름과 결합하지 않는다.
- 복수 Evidence Source, Generation Method, Audit History를 논리적으로 분리한다.
- 포함 연령 집합의 논리 표현은 Set이며 물리 저장 방식은 OD-N02에서 확정한다.
- PostgreSQL 15는 현재 권장 방향이지만 최종 결정은 OD-N01이다.

---

# 28. API / Application Contract 기준

첫 Slice는 다음 Use Case를 기준으로 한다.

```text
GenerateYearlyPlan
EditYearlyPlanItem
RegenerateYearlyPlanItem
ConfirmYearlyPlan
```

- Actor는 Application 경계에서 주입한다.
- Item 편집·재생성은 `item_id`와 의미 주소를 사용한다.
- LLM Structured Output은 DB Model과 직접 결합하지 않는다.
- 외부 HTTP endpoint, 오류 코드, 동시성 제어, Persistence Contract는 `docs/contracts.md`에서 확정한다.
- OD-Y01~Y03을 반영한 Use Case와 Port 설계는 가능하지만 구현은 별도 착수 승인 전 시작하지 않는다.

---

# 29. 화면 공통 동작

연간·월간·주간 화면은 다음 동작을 공통으로 제공한다.

```text
생성
칸 클릭 편집
이 칸만 다시 생성
출처 확인
상태창
확정
변경 이력
```

- 전체 재생성은 P0에 포함하지 않는다.
- 출처는 셀의 짧은 Marker와 우측 상세 패널로 제공한다.
- Evidence Source UI와 Generation Method·Audit History UI의 의미를 섞지 않는다.
- 출처 Marker와 패널 내용은 제출용 내보내기에 포함하지 않는다.
- 차단 시 이유와 해결 방법을 함께 표시한다.

세부 상호작용은 `docs/screen-spec.md`를 따른다.

---

# 30. Template / Adapter 원칙

```text
Semantic Plan
        ↓
Template / Output Adapter
        ↓
기관별 표시 구조
```

- Template A는 월간 P0 Adapter 후보 하나이지 전국 표준이 아니다.
- 원본 Label과 계층을 보존할 수 있어야 한다.
- 의미가 같은 Label은 Mapping하되 근거 없는 동의어 통합을 하지 않는다.
- 안전교육 등 Section의 물리 행 위치를 Domain Rule로 만들지 않는다.
- 추가 Template 범위는 OD-N07에서 정한다.

---

# 31. 테스트 기준

결정론적 Rule은 Unit Test를 작성한다.

- Confirmation Gate
- Theme Reference 후보 필터·선택
- Yearly `month_periods[12]`
- MonthPeriod 순서와 학년도 경계
- Age Fit
- Safety Rule
- Parent Plan Validation
- Optional Dependency Fallback
- Item 단위 재생성의 비선택 Item 보존

LLM은 문장 전체를 exact match하지 않는다.

- Schema
- 필수 필드
- Reference 범위
- 선택되지 않은 사실 추가 여부
- 금지된 자유 결정 여부
- Validation 통과 여부

Golden Set에는 만 3세·4세·5세·혼합연령, 행사 있음·없음, Trend 있음·없음, 상위 Plan Gate 실패를 포함한다.

---

# 32. P0 완료 기준

- [ ] 원·반 정보로 Yearly DRAFT를 생성한다.
- [ ] Yearly가 3월~다음 해 2월의 `month_periods[12]`를 가진다.
- [ ] 각 월 Theme이 사람이 검증한 Theme Reference v0와 연결된다.
- [ ] 교사가 Yearly Item을 편집하고 선택 Item만 재생성할 수 있다.
- [ ] opaque Actor ID로 Yearly를 확정한다.
- [ ] OD-N09에서 승인된 Yearly 형식은 기존 기간을 보존하고 미작성 잔여 기간만 생성할 수 있다.
- [ ] 지원되지 않은 형식은 추정 Mapping 없이 거절하고 수동 입력·재업로드 복구 경로를 제공한다.
- [ ] Confirmed Yearly를 Context로 Monthly DRAFT를 생성한다.
- [ ] Monthly Template A가 dynamic weeks와 Section별 display_mode를 지원한다.
- [ ] Monthly를 편집·확정한다.
- [ ] Confirmed Monthly를 Context로 Weekly DRAFT를 생성한다.
- [ ] Weekly를 편집·확정한다.
- [ ] Evidence Source / Generation Method / Audit History 세 축을 구분해 확인할 수 있다.
- [ ] Optional 외부 기능 실패 시 Core 생성이 계속된다.

---

# 33. 현재 착수 상태

문서 기준 상태:

```text
공식 자료 보완                            완료
references/README.md                     갱신 완료 (2026-09-11, 월간 13표본 반영)
Provenance 논리 기준 통일                 완료
screen-spec.md                           동기화 완료
Monthly Template A 실측 재검증            2차 재측정 완료 (2026-09-11, 기관 11곳)
Open Decision 재분류                      완료
OD-Y01~Y03 P0 결정                        승인 (2026-09-09)
Yearly Planning Core 구현                 완료 (435 passed / Golden 22/22)
Elice MLAPI Adapter + Live Smoke          완료
Yearly Dev Harness                        완료
Theme Reference v0.1.2                    HUMAN_APPROVED
OD-M01~M04 P0 결정                        승인 (2026-09-11)
M0 데이터 초안                             작성 완료, PENDING_HUMAN_REVIEW
Monthly Core 구현                          미착수
Weekly                                    미착수
```

OD-Y01~Y03은 2026-09-09에, OD-M01~M04는 2026-09-11에 `RESOLVED_FOR_P0`로 닫혔다.

Yearly Vertical Slice(`GenerateYearlyPlan → Edit → Regenerate Item → Confirm`)는 완료
기준점으로 동결됐다.

다음 단계는 **M0 Human Review**다. 두 데이터 초안이 사람 검토를 통과하기 전에는 runtime
active로 취급하지 않는다.

```text
data/templates/monthly_template_a.json        PENDING_HUMAN_REVIEW
data/rules/safety_education_legal_v1.json     PENDING_HUMAN_REVIEW
```

Activity Reference는 미작성이고 OD-N03이 `OPEN`이므로 Activity 생성 기능은 M2 blocker로
유지한다. M1 구조 Slice는 Activity Reference 없이 착수할 수 있다.

---

# 34. Decision Register

이전 임시 ID 체계는 사용하지 않는다. P0 결정 등록부는 `OD-Y / OD-M / OD-W / OD-N` 체계로 통일한다.

## 34.1 Yearly — P0 승인 완료

| ID | 결정 | 분류 | 상태 |
|---|---|---|---|
| OD-Y01 | Yearly 최소 구조 = `school_year + classroom_ref + month_periods[12] + 각 월 theme`, 나머지 Optional, `item_id/semantic_key` 안정 주소 | BLOCKING | `RESOLVED_FOR_P0` |
| OD-Y02 | 사람이 검증한 versioned Theme Reference v0를 Rule 후보 원천으로 사용하고 LLM은 표현만 담당 | BLOCKING | `RESOLVED_FOR_P0` |
| OD-Y03 | Plan 소유 = classroom, Confirm actor = opaque `actor_id/user_id`, 혼합연령도 classroom 단위 Plan | BLOCKING | `RESOLVED_FOR_P0` |

## 34.2 Monthly 전 결정

| ID | 결정 대상 | 분류 | 상태 | 승인일 |
|---|---|---|---|---|
| OD-M01 | Template A v0의 Section 활성화·표시·계층·빈 값 정책의 결정 주체 | BLOCKING-BEFORE-MONTHLY | `RESOLVED_FOR_P0` | 2026-09-11 |
| OD-M02 | Dynamic WeekPeriod 산출·경계·`week_id` 안정성·Override 정책 | BLOCKING-BEFORE-MONTHLY | `RESOLVED_FOR_P0` | 2026-09-11 |
| OD-M03 | `subtheme`과 `expected_play`의 의미 관계와 Mapping | BLOCKING-BEFORE-MONTHLY | `RESOLVED_FOR_P0` | 2026-09-11 |
| OD-M04 | Safety Rule Data·월 배치 정책·비상대응/대피훈련 Grouping | BLOCKING-BEFORE-MONTHLY | `RESOLVED_FOR_P0` | 2026-09-11 |

§18의 고정 8행 금지, 동적 `WeekPeriod`, 기본 지원 의미, goals/habits Optional, 성품인사 기본행 제거, `subtheme`/`expected_play` 자동 병합 금지, Section별 display mode, 원본 Label 보존은 이미 확정된 Guardrail이며 이번 결정으로 유지된다.

P0 최종 결정 내용은 docs/open-decisions.md §2 `승인된 Monthly 결정 요약`과 §4에 있다. 핵심은 다음 4가지다.

- **OD-M01** — 활성화·표시·계층·빈 값 정책의 결정 주체는 **Template instance data**다. 코드에 전역 기본값을 두지 않는다. 기본 활성 후보는 `theme`/`outdoor_play`/`safety_education`/`week_axis`, Optional은 `goals`/`habits`/`focus`/Custom Section이다. 빈 값은 `RENDER_EMPTY_CELL`, 계층은 `max_depth = 2`. **`display_mode`의 전국 공통 기본값을 만들지 않고** 각 Template instance의 각 Section이 명시하며, `WEEKLY_CELLS`·`MONTHLY_MERGED_SUMMARY` 두 값만이 영구적으로 전부라고 고정하지 않는다. Template A는 `SAMPLE_DERIVED_NON_NORMATIVE` product adapter다.
- **OD-M02** — `SSUKSAK_P0_CANONICAL_WEEK_POLICY`. Monday-start week 중 월~금 5일 가운데 target calendar month에 3일 이상 포함된 주를 ordered list로 산출하고, `start_date`/`end_date`를 월 경계로 clip하지 않으며 `target_month`와 `school_year`를 별도 보존한다. `week_id = YYYY-MM-Wn`은 동일 입력에서 항상 동일하고 Edit/Regenerate/Override로 변경되지 않는다. Override(`week_days`/`active`/`display_group`)는 canonical을 삭제·재번호화하지 않는다. **국가·법정·어린이집 공통 주차 표준이 아니라 제품 내부 deterministic policy다.**
- **OD-M03** — 두 Label을 자동 병합하지 않고 중립 슬롯 `monthly.week.<week>.focus`를 쓴다. `source_label`·`label_variant`·`mapping_confidence`를 보존하고 **기관 단위 label mapping을 만들지 않는다.** `focus`는 default inactive다. 공용 `PlanItem`을 변경해 Yearly Core를 건드리지 않는다.
- **OD-M04** — 법령 Rule은 법정 구분·실시 간격·연간 최소 시간·적용 대상·source/version만 저장하고 **월 assignment를 만들지 않는다.** Rule은 검증만 하고 배치를 창작하지 않는다. 배치 Source는 기관 제공 안전교육 연간계획 또는 교사 직접 입력이며, 둘 다 없으면 임의·LLM 배치와 법적 충족 주장을 금지하고 `법정 요건 미검증 / source required` 상태를 표현한다. 비법정 기관 label을 법정 6구분으로 자동 매핑하지 않고 `emergency_response`/`drill`을 별도 semantic key로 유지한다.

결정과 별개로 Monthly 착수에는 M0 데이터 산출물이 필요하다. `data/templates/monthly_template_a.json`과 `data/rules/safety_education_legal_v1.json`은 2026-09-11에 초안이 작성됐고 둘 다 `PENDING_HUMAN_REVIEW`다. 사람 검토 전에는 runtime active로 취급하지 않는다. Activity Reference는 미작성이며 OD-N03이 `OPEN`이므로 Activity 생성 기능은 M2 blocker로 유지한다.

## 34.3 Weekly 전 결정

| ID | 결정 대상 | 분류 | 상태 |
|---|---|---|---|
| OD-W01 | 월간계획안 미사용 시 YEARLY → WEEKLY 직접 Gate와 Parent 관계 | BLOCKING-BEFORE-WEEKLY | `OPEN` |
| OD-W02 | Weekly Canonical Output과 출력 위치별 Adapter | BLOCKING-BEFORE-WEEKLY | `OPEN` |

## 34.4 Non-blocking

| ID | 결정 대상 | 결정 시점 | 상태 |
|---|---|---|---|
| OD-N01 | PostgreSQL 15 최종 팀 확정 | 첫 영구 Migration 병합 전 | `PROVISIONAL` |
| OD-N02 | 혼합연령 물리 저장 방식 | Classroom 영구 Migration 전 | `OPEN` |
| OD-N03 | Activity taxonomy와 초기 Reference 범위 | 실제 Seeding·E2E 품질 검증 전 | `OPEN` |
| OD-N04 | LLM 공급자·모델·timeout·retry | 실제 Adapter 연결 전 | `OPEN` |
| OD-N05 | Provenance 물리 저장 Schema | 영구 Migration·조회 API 전 | `OPEN` |
| OD-N06 | 명시적 DRAFT 저장·미저장 이탈 경고·CONFIRMED 편집 차단은 P0 확정; 자동저장·동시 편집 충돌·확정 취소·재편집·후속 Version 정책은 미결정 | 자동저장·다중 편집 또는 CONFIRMED 후속 편집 기능을 활성화하기 전 | `PARTIALLY_RESOLVED` |
| OD-N07 | Template A 외 추가 Template 범위 | Template A E2E 후 | `DEFERRED` |
| OD-N08 | Yearly HTTP API와 물리 Persistence Contract | FE/BE 통합·영구 Migration 전 | `OPEN` |
| OD-N09 | 지원 Yearly Import 형식 목록, Parser 판별, 필드 Mapping·빈 기간 판정·정규화·실패 Contract | Yearly Import Slice 착수 전 | `OPEN` |

NON-BLOCKING 항목은 Port·설정·가역적 기본값으로 격리하고 각 결정 시점 전까지 닫는다.

---

## 최종 원칙

> Rule은 검증된 후보와 배치를 결정하고, LLM은 그 결정을 자연스럽게 표현하며, 교사는 DRAFT를 검토·수정한 뒤 opaque Actor Identity로 확정한다.

> Template은 의미 구조를 표현하는 Adapter이며, 특정 기관 샘플의 고정 행·열 구조를 전국 공통 Domain Model로 만들지 않는다.
