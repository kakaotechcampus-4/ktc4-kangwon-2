# screen-spec.md — 쓱싹요정 P0 Planning Demo

> 목적: PM 최신 화면 결정과 현재 P0 Source of Truth를 구현 가능한 화면 명세로 고정한다.  
> 이 문서는 UI/상태/사용자 동작을 정의하며, DB/API 세부 구조는 `docs/contracts.md`에서 별도로 확정한다.

---

## 0. 적용 우선순위

화면 구현 판단은 다음 순서를 따른다.

1. `CLAUDE.md`
2. `docs/demo-source-of-truth.md`
3. `docs/screen-spec.md`
4. `docs/contracts.md`
5. `docs/open-decisions.md`
6. `docs/template-a-validation.md`
7. `references/README.md`
8. `references/official/`
9. `references/samples/`

이 문서가 상위 문서와 충돌하면 임의로 해석하지 않고 충돌 내용을 보고한다.

---

# 1. 전체 사용자 흐름

```text
회원가입
  ↓
온보딩 1/3 — 원 정보
  ↓
온보딩 2/3 — 반 정보
  ↓
온보딩 3/3 — 성품인사
  ↓
메인
  ↓
계획안 첫 진입
  ↓
계획안 최초 세팅 1/2 — 작성 방식
  ↓
계획안 최초 세팅 2/2 — 초기 자료
  ↓
연간 계획안
  ↓
DRAFT → 교사 편집 → CONFIRMED
  ↓
월간 계획안
  ↓
DRAFT → 교사 편집 → CONFIRMED
  ↓
주간 계획안
  ↓
DRAFT → 교사 편집 → CONFIRMED
```

Planning P0의 표준 경로는 다음과 같다.

```text
YEARLY CONFIRMED
→ MONTHLY 생성 가능

MONTHLY CONFIRMED
→ WEEKLY 생성 가능
```

자동 확정·자동 제출·자동 발송은 없다.

---

# 2. 온보딩

온보딩은 모든 기능의 공통 전제 정보를 받는다.

계획안 전용 질문은 온보딩이 아니라 **계획안 첫 진입 시점**에 받는다.

---

## 2.1 온보딩 1/3 — 원 정보

### 필드

| 필드 | 필수 | 검증/비고 |
|---|---:|---|
| 원명 | 예 | trim 후 빈 문자열 금지 |
| 원장 이름 | 예 | trim 후 빈 문자열 금지. 표시·관리 Context이며 Audit/Confirm Actor ID가 아님 |
| 지역 | 예 | 도/시 수준. 표시명과 내부 식별값 분리 가능 |

### 원 프로필 상세 — 선택 입력

같은 단계의 접을 수 있는 `프로필 상세 (선택)` 영역에 다음 정보를 둔다. 모두 건너뛸 수 있고, 온보딩 완료 후 원 프로필/계획 설정에서 다시 편집할 수 있다.

| 필드 | 필수 | 비고 |
|---|---:|---|
| 교육 강조 방향 | 아니요 | 후보 가중치 Context |
| 운영 철학 | 아니요 | 자유 입력 또는 검증된 태그 |
| 특성화 프로그램 | 아니요 | Optional Context |
| 회피 소재 | 아니요 | 후보 제외 Context |
| 원 행사·운영 캘린더 | 아니요 | 연도별 운영 정보. 정적 원 프로필과 분리해 저장하며 계획안 최초 세팅에서도 추가·수정 가능 |

이 선택 정보의 누락만으로 Planning Core 생성·편집·확정을 차단하지 않는다.

### 받지 않는 정보

- 학기 기간
- 정원

### 동작

- 필수값 누락 시 다음 단계로 이동하지 않는다.
- 기술적인 코드값은 사용자에게 노출하지 않는다.

---

## 2.2 온보딩 2/3 — 반 정보

### 필드

| 필드 | 필수 | 비고 |
|---|---:|---|
| 반 이름 | 예 | 문자열 |
| 연령 | 예 | 만3세 / 만4세 / 만5세 / 혼합연령 |
| 혼합 연령 집합 | 조건부 | 혼합연령 선택 시 만3·4·5 중 2개 이상 |
| 현재 원아 수 | 아니요 | 0 이상의 정수 |
| 담임 이름 | 예 | 현재 제품 범위 |

### 반 프로필 상세 — 선택 입력

같은 단계의 접을 수 있는 `프로필 상세 (선택)` 영역에 다음 정보를 둔다. 둘 다 건너뛸 수 있고 이후 반 프로필에서 다시 편집할 수 있다.

| 필드 | 필수 | 비고 |
|---|---:|---|
| 반 특성 | 아니요 | Optional Context |
| 최근 관심 | 아니요 | 수시 변경 가능한 Optional Context |

이 선택 정보의 누락만으로 Planning Core 생성·편집·확정을 차단하지 않는다.

### 혼합연령 UI

```text
○ 만 3세
○ 만 4세
○ 만 5세
○ 혼합연령
    □ 만 3세
    □ 만 4세
    □ 만 5세
```

혼합연령은 2개 이상의 연령을 선택해야 한다.

### 아동 명단

- Planning P0 온보딩에서는 아동 이름 목록을 입력받지 않는다.
- Planning P0는 아동 명단 없이 정상 동작한다.
- 명단 미입력 상태가 Planning 생성/편집/확정을 차단하면 안 된다.
- 향후 Observation 기능이 명단을 요구할 경우 해당 기능 진입 시 별도 안내한다.
- 개발·데모 데이터에는 실제 아동 실명을 사용하지 않는다.

---

## 2.3 온보딩 3/3 — 성품인사

### 기본 동작

- 성품인사는 원/반의 선택적 Profile Context로 입력한다.
- 1~12월 기본값은 이 온보딩 Profile 입력에서만 표시한다.
- 월별 값을 수정할 수 있다.
- `사용 안 함` 토글을 제공한다.
- 입력하지 않거나 사용하지 않아도 Planning Core가 정상 동작해야 한다.

### 월간 Template과의 관계

- 성품인사를 Monthly Template A의 기본 Section 또는 기본행으로 생성하지 않는다.
- 전국 공통 필수 필드로 하드코딩하지 않는다.
- Profile 값이 존재한다는 이유만으로 월간 출력에 렌더링하지 않는다.
- 기관이 출력을 요구하고 `Custom Section Mapping`을 명시적으로 활성화한 경우에만 해당 Mapping을 통해 선택 렌더링한다.

---

# 3. 메인 화면

## 3.1 계획안 진입 카드

메인에서 Planning 기능으로 진입할 수 있는 카드를 제공한다.

카드에는 최소한 다음을 보여준다.

- 현재 계획안 진행 단계
- 현재 상태
- 다음 가능한 동작
- 차단된 경우 차단 이유

예:

```text
연간계획안 초안 작성 중
→ 이어서 편집하기
```

```text
연간계획안 확정 완료
→ 4월 월간계획안 만들기
```

```text
월간계획안 생성 불가
→ 연간계획안을 먼저 확정해 주세요.
```

## 3.2 차단 안내 원칙

단순히 버튼을 비활성화하지 않는다.

반드시:

```text
왜 차단됐는지
+
무엇을 하면 해결되는지
```

를 같이 보여준다.

예:

> 연간계획안을 확정하면 월간계획안을 만들 수 있어요.

---

# 4. 계획안 최초 세팅

계획안 버튼을 **처음 클릭했을 때 한 번만** 진행한다.

이후에는 저장된 설정을 사용해 바로 Planning 화면으로 진입한다.

---

## 4.1 최초 세팅 1/2 — 작성 방식

### 월간계획안 사용 여부

- OD-W01이 `OPEN`인 동안 값은 `사용`으로 고정한다.
- `사용 안 함` 선택지는 숨기거나 비활성화하고 저장 가능한 선택지로 제공하지 않는다.
- OD-W01에서 YEARLY → WEEKLY 직접 Gate와 parent 관계가 확정된 뒤에만 월간 미사용 설정을 활성화할 수 있다.

### 주간계획 위치

아래 세 항목은 OD-W02의 **후보**다.

```text
○ 별도 주간계획안
○ 주간보육일지 계획칸
○ 일일보육일지 계획칸
```

- OD-W02가 `OPEN`인 동안 이 설정은 저장 가능한 단일 선택으로 활성화하지 않는다. 필요하면 후보 목록과 “주간 구현 전 결정 예정” 안내만 표시한다.
- OD-W02에서 P0 첫 Adapter와 후속 Adapter 범위를 승인한 뒤에만 승인된 선택지를 활성화한다.
- 보육일지의 계획칸 Adapter는 계획 결과의 출력 위치를 뜻하며, P0 제외 범위인 전체 보육일지 생성 기능을 포함한다는 뜻이 아니다.

### OD-W01 — 월간계획안 미사용 경로 `[BLOCKING-BEFORE-WEEKLY]`

현재 P0 표준 흐름은:

```text
연간 → 월간 → 주간
```

이다.

따라서 `월간계획안 미사용`을 실제 선택 가능하게 둘 경우:

- YEARLY → WEEKLY 직접 게이트
- WEEKLY의 parent 관계
- 화면 이동
- API Contract

를 함께 확정해야 한다.

OD-W01 결정 전에는 표준 `YEARLY → MONTHLY → WEEKLY` 경로만 활성화하고 월간 사용 여부는 `사용`으로 고정하며, 구현자가 임의로 `연간 → 주간` 규칙을 만들지 않는다.

---

## 4.2 최초 세팅 2/2 — 초기 자료

### 시작 방식

사용자는 다음 중 하나를 선택한다.

```text
○ 처음부터 만들기
○ 있는 계획안 이어받기
```

### A. 처음부터 만들기

쓱싹요정의 검증된 Reference Data와 입력 정보를 기반으로 연간계획안을 생성한다.

### B. 있는 계획안 이어받기

- 지원 목록에 명시되고 검증된 기존 연간계획안 형식만 업로드
- 업로드한 계획을 읽어 현재 계획 Context로 사용
- 이미 작성된 기간은 보존
- 남은 기간을 생성할 수 있음
- **부분 생성은 P0 포함**

기관 고유 양식을 범용으로 자동 파싱한다고 가정하지 않는다. 화면에는 현재 지원 형식·버전과 필요한 필드를 명시한다. 지원되지 않은 형식은 선택 가능하게 열지 않으며, 임의의 추정 Mapping으로 가져오지 않는다.

지원 형식, 파싱·Mapping, 부분 생성 범위 Contract는 Non-blocking `OD-N09`로 추적하되 **Import Slice 구현·활성화 전에는 반드시 확정**한다. 따라서 부분 생성은 P0 제품 범위에 포함되지만, OD-N09가 `OPEN`인 동안 지원되지 않은 Import 경로를 먼저 활성화하지 않는다.

### 업로드 실패

파싱 실패 시:

- 원본 파일을 보존한다.
- 단순 실패만 표시하지 않는다.
- 오류가 난 위치/이유를 가능한 범위에서 안내한다.
- 수동 입력 또는 다시 업로드할 수 있는 복구 경로를 제공한다.

### 선택 입력 — 안전교육 연간계획안

- 파일 업로드는 선택이다.
- 파일이 없다는 사실 자체는 초기 설정이나 Yearly Core 진행을 차단하지 않는다.
- **OD-M04 `RESOLVED_FOR_P0`(2026-09-11) 기준:** 제품 기본 safety placement policy는 P0에서 발행하지 않는다. 따라서 **자동 대체 폴백이 존재하지 않는다.**
- 배치 Source는 ① 기관·교사가 제공한 안전교육 연간계획 ② 교사 직접 입력 뿐이다.
- 둘 다 없으면 임의 월 배치를 생성하지 않고, LLM으로 배치를 생성하지 않으며, 법적 충족을 주장하지 않는다.
- 이때 Safety Section은 **구조적으로 존재하고 표현 가능하되 값이 없을 수 있다.** 화면은 `법정 요건 미검증 / source required` 상태와 해결 방법(파일 제공 또는 직접 입력)을 안내한다.
- 이 상태의 정확한 표현 방식은 M1 설계에서 승인받는다. 임의 Enum을 만들지 않는다.
- 안전교육의 법정 주기/시간과 월별 배치 정책을 혼동하지 않는다.

### 선택 입력 — 원 자체 행사

- 행사 입력은 선택이다.
- `나중에` 동작을 제공한다.
- 행사 미입력으로 Planning Core가 실패하지 않는다.
- 입력값은 §2.1의 `원 행사·운영 캘린더`와 같은 연도별 운영 Context를 편집한다.

### 생성 Context 확인 — 선택 정보

- 저장된 교육 강조 방향, 운영 철학, 특성화 프로그램, 회피 소재, 원 행사·운영 Calendar, 반 특성, 최근 관심, 성품인사를 한곳에서 요약한다.
- 사용자는 Yearly 생성 전에 각 선택 Context의 적용 여부와 값을 확인·수정할 수 있다.
- 성품인사를 포함한 선택 Context를 적용하지 않아도 Planning Core 생성·편집·확정을 차단하지 않는다.
- 이 확인 화면은 Profile 값을 Monthly 출력 Section으로 자동 변환하지 않는다. 성품인사 출력은 명시적으로 활성화된 Custom Section Mapping이 있을 때만 가능하다.

---

# 5. 계획안 화면 공통 구조

연간·월간·주간 계획안 화면은 동일한 기본 상호작용 원칙을 사용한다.

필수 화면 요소는 7개다.

```text
① 생성
② 칸 클릭 편집
③ 이 칸만 다시 뽑기
④ 출처 표시
⑤ 상태창
⑥ 확정
⑦ 변경 이력
```

---

## 5.1 생성

### EMPTY 상태

생성 전에는:

- 아직 계획안이 없음을 안내
- 생성 가능 조건을 표시
- 조건이 충족되면 `생성` 버튼 활성화

### 생성 시작

생성 요청은 중복 실행되지 않게 한다.

생성 중에는 현재 진행 상태를 표시한다.

---

## 5.2 칸 클릭 편집

DRAFT 상태에서 칸을 클릭하면 직접 수정할 수 있다.

편집은 Planning의 **기본 수정 수단**이다.

교사가 이미 만족한 다른 칸에는 영향을 주지 않는다.

---

## 5.3 이 칸만 다시 뽑기

DRAFT 상태의 개별 칸에 제공한다.

### 원칙

- 선택한 칸만 다시 생성한다.
- 다른 칸은 변경하지 않는다.
- 재생성 이전 값은 변경 이력에 남긴다.
- 새 생성 결과도 DRAFT 상태다.

### 전체 재생성

**P0에서는 전체 재생성 기능을 만들지 않는다.**

이유:

- 만족한 칸까지 사라질 수 있음
- LLM은 비결정적임
- 다음 생성이 더 나을 보장이 없음
- 부분 수정 중심 UX와 충돌함

---

# 6. Provenance와 출처 표시

## 6.1 논리 구조

Provenance는 다음 세 축을 분리한다.

### Evidence Source — 내용의 근거

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

`INSTITUTION_SAMPLE`은 2026-09-13 Human Decision(OD-N13)으로 추가했다. CLAUDE.md §13.1과 같은 목록을 유지한다. Domain Enum 반영은 Monthly LLM Planner 구현 단계(L4~L6)에서 한다.

각 Item의 Evidence는 `EvidenceSource[]` **0..N**이다. 각 Evidence Source는 다음 논리 필드명을 사용한다.

```text
source_type
source_id
source_version?  // optional
effective_date?  // optional
display_name?    // optional
```

- `source_id`는 해당 Item이 실제로 참조한 Evidence record의 식별자다.
- Theme Reference를 사용한 Theme Item은 `source_type=THEME_REFERENCE`, `source_id=theme_id`, 필수 `source_version`으로 연결한다.
- `origin_id`는 Theme Reference 같은 Reference record가 보존하는 상위 원천/원본 식별자다. `source_id`의 별칭이 아니며, 존재할 경우 해당 Evidence의 상세 정보로 연결해 보여준다.
- 화면 Label이나 Template의 `source_label`을 Evidence의 `display_name` 또는 `source_id`로 대체하지 않는다.

### Generation Method — 생성 방식

```text
RULE_ONLY
RULE_LLM
IMPORTED
MANUAL
```

- 각 Item의 **현재 값**은 하나의 Generation Method를 가진다.
- `RULE_ONLY`와 `RULE_LLM`은 적용한 `rule_id`와 `rule_version`을 Generation Method 상세 메타데이터로 가진다.
- `적용된 Rule`은 Generation Method 상세이며 `SAFETY_RULE` Evidence Source와 같은 개념이 아니다. `SAFETY_RULE`은 실제로 인용한 안전 기준·정책 근거가 있을 때만 사용한다.
- `MANUAL`은 사람이 해당 Item의 최초 값을 직접 입력해 생성·Import 결과가 없다는 뜻이다.
- 기존 `RULE_ONLY`, `RULE_LLM`, `IMPORTED` 또는 `MANUAL` Item을 교사가 나중에 고친 것은 Method를 바꾸지 않고 Audit History에 `TEACHER_EDITED`로 추가한다.
- Item을 재생성하면 현재 값의 Generation Method를 실제 재생성 방식으로 갱신하고, 이전·새 값과 이전·새 Method는 `REGENERATED` Audit Event에 보존한다.

### Audit History — 생성 이후의 변경

```text
CREATED
REGENERATED
TEACHER_EDITED
CONFIRMED
```

`AI`와 `TEACHER_EDIT`은 Evidence Source가 아니다. LLM 사용 여부는 Generation Method로, 교사의 수정과 확정은 Audit History로 표시한다.

Audit Event는 발생 순서를 보존하며 화면에서는 `occurred_at`과 ordered `AuditEvent[]`의 안정적인 순서에 따라 오래된 것부터 최신 순으로 표시한다. 별도 물리 순서 필드가 필요한지는 OD-N05에서 확정한다.

## 6.2 셀 표시

Evidence Source가 하나 이상인 칸에는 **좌상단 점 하나**를 표시한다. 이 점은 개별 Source 하나가 아니라 해당 Item의 `EvidenceSource[]` 전체가 존재한다는 집계 Marker다. Evidence 개수와 관계없이 점은 하나만 표시한다.

Evidence가 0개인 Item을 포함해 **모든 Item**에 `정보/이력` 진입 동작을 제공한다. 따라서 `MANUAL` Item도 Generation Method와 Audit History를 열어볼 수 있다. 출처 점은 Evidence가 있는 Item의 빠른 진입 수단일 뿐, 유일한 Provenance 진입 수단이 아니다.

다음 방식은 사용하지 않는다.

- 셀 내부 긴 인라인 각주
- 출처 Chip 여러 개
- 제출 문서에 남는 출처 Marker

## 6.3 우측 Provenance 패널

출처 점 또는 해당 Item의 `정보/이력` 동작을 클릭하면 우측 패널을 연다.

최소 표시 정보:

- `EvidenceSource[]`의 **모든** 근거: `source_type`, `source_id`, 선택적 `display_name`, `source_version`, `effective_date`
- Evidence가 0개이면 숨기지 않고 `등록된 근거 없음` 표시
- `origin_id`가 있는 Reference의 경우 `source_id`와 구분되는 원천 식별자로 상세 표시
- 필요한 경우 `PARENT_PLAN` Evidence를 통한 상위 계획 참조
- Generation Method와 상세 메타데이터
- `RULE_ONLY` 또는 `RULE_LLM`이면 `rule_id`, `rule_version`을 `적용된 Rule`로 표시
- 해당 Item의 전체 Audit Event와 현재 Plan에 적용되는 Plan-level `CONFIRMED` Event를 발생 순서대로 구분 표시

세 축을 하나의 Source Type enum으로 합치지 않는다.

## 6.4 내보내기

내보내기 시:

- 출처 점 제거
- 우측 패널 정보 제거

제출용 문서에는 UI용 Provenance Marker가 포함되지 않는다.

## 6.5 출처 표시 토글

P0에서는 출처 표시를 완전히 꺼버리는 설정 토글을 만들지 않는다.

---

# 7. 상태창

계획안 화면에서 현재 구조/검증 상태를 요약한다.

현재 상태창 후보:

```text
빈 칸 N
안전교육 미배정 N
연속 3주 동일 활동 N
```

### 동작

각 항목은 클릭 가능한 목록으로 제공한다.

예:

```text
연속 3주 동일 활동 2
    ↓
클릭
    ↓
해당 셀로 이동
```

### 주의

상태창의 구체 Rule은 `docs/contracts.md` 및 Rule Data가 확정되기 전 임의로 확대하지 않는다.

---

# 8. 확정

DRAFT 상태에서 교사가 `확정`을 실행할 수 있다.

확정 UI에는 다음 의미를 명확히 표시한다.

```text
확정
≠
자동 제출
```

예:

> 확정해도 외부 기관으로 자동 제출되지 않습니다.

## 8.1 상태 전환

```text
DRAFT
→ CONFIRMED
```

## 8.2 확정 이후

현재 P0에서는 `CONFIRMED` 상태를 읽기 중심으로 표시한다.

확정 후에는 편집을 차단한다. 이는 OD-N06에서 이미 확정된 P0 경계다. 확정 취소·재편집·새 Version의 남은 정책은 OD-N06에서 별도로 결정하며, 그 전까지 임의로 다시 편집 가능하게 구현하지 않는다.

확정 행위자는 표시용 담임 이름이 아니라 opaque `actor_id` 또는 `user_id`로 기록한다.

## 8.3 다음 단계 Gate

```text
YEARLY CONFIRMED
→ MONTHLY 생성 활성화

MONTHLY CONFIRMED
→ WEEKLY 생성 활성화
```

---

# 9. 변경 이력

변경 이력은 Evidence Source와 분리한다.

최소 Event Type:

```text
CREATED
REGENERATED
TEACHER_EDITED
CONFIRMED
```

화면에서는 최소 다음 질문에 답할 수 있어야 한다.

- 언제 처음 생성되었는가
- 어떤 칸이 다시 생성되었는가
- 교사가 어떤 값을 수정했는가
- 언제 확정되었는가

Audit Event는 발생 순서를 보존해 오래된 것부터 최신 순으로 표시한다. 교사 수정은 Evidence Source나 Generation Method를 덮어쓰지 않고 `TEACHER_EDITED` Event로 추가한다.

각 Audit Event는 최소 `event_type`, `occurred_at`, `plan_id`, 선택적 `item_id`, 그리고 사람의 opaque `actor_id/user_id` 또는 시스템 행위자 Marker를 가진다. `Audit History`는 이 ordered `AuditEvent[]`의 사용자용 명칭이다.

P0 화면에서 전체 diff UI의 세부 형태는 후속 결정으로 남길 수 있다.

---

# 10. Plan 상태와 UI/Run 상태

DB의 핵심 Plan 상태는 다음 두 개만 사용한다.

```text
DRAFT
CONFIRMED
```

화면/Generation Run에는 별도의 상태가 존재할 수 있다.

| UI/Run 상태 | 화면 표시 | 허용 동작 |
|---|---|---|
| `EMPTY` | 생성 전 안내 | 생성/업로드 |
| `GENERATING` | 생성 진행 표시 | 중복 요청 방지 |
| `DRAFT` | 초안 배지 | 편집, 셀 재생성, 출처, 확정 |
| `GENERATION_PARTIAL` | 일부 생성 실패 표시 | 실패 셀 재시도/직접 편집 |
| `CONFIRMED` | 확정자·확정 시각 | 조회 중심 |
| `ERROR` | 복구 가능한 오류 안내 | 안전한 재시도 |

`GENERATION_PARTIAL`은 `plans.status` Enum에 넣지 않는다.

즉:

```text
Plan Status
= DRAFT | CONFIRMED

Generation/UI State
= EMPTY | GENERATING | GENERATION_PARTIAL | ERROR ...
```

처럼 의미를 분리한다.

---

# 11. 연간 계획안 화면

## 11.1 생성 조건

- 원 정보 존재
- 반 정보 존재
- 사람이 검증한 versioned Theme Reference v0 사용 가능
- 계획안 최초 세팅 완료

## 11.2 Yearly Plan v0 최소 구조

연간 생성 결과는 항상 `DRAFT`이며 다음 구조를 필수로 한다.

```text
YearlyPlan
├─ school_year
├─ classroom_ref
└─ month_periods[12]
   └─ 3월부터 다음 해 2월까지 각 MonthPeriod
      └─ theme (required)
```

세부 원칙:

- `month_periods`는 3월부터 다음 해 2월까지 정확히 12개이며 순서를 보존한다.
- 각 MonthPeriod의 `theme`는 필수다.
- goals 또는 rationale, weekly_focus, 기관 특화 Section은 Optional이다.
- 주차 하위항목은 필요한 경우에만 가변 길이 Optional Item으로 두며 4주/5주를 강제하지 않는다.
- 모든 편집 단위는 안정적인 `item_id`와 `semantic_key`를 가진다.
- 표시 Label이나 물리 DB 컬럼명을 편집·재생성 주소로 사용하지 않는다.

## 11.3 Theme 선택

- 사람이 검증한 versioned Theme Reference v0를 Rule의 후보 원천으로 사용한다.
- Rule이 적용 월·연령·반 Context에 맞는 후보를 선택한다.
- LLM은 Rule이 선택한 theme의 표현만 다듬고, 새 theme를 자유 선택하거나 정책적으로 확정하지 않는다.
- 공식 누리과정이 월별 주제를 직접 정한 것처럼 표시하지 않는다.

## 11.4 소유권과 혼합연령

- Plan 소유 단위는 `classroom`이다.
- daycare 귀속은 classroom을 통해 표현한다.
- 혼합연령 반도 포함 연령 집합을 생성 Context로 사용하는 하나의 classroom Plan을 생성한다.
- 담임 이름은 표시 정보이며 Plan 소유권 또는 Confirm Actor 식별자로 사용하지 않는다.

### 중요

연간 Sample의 공통 구조를 월간 Template A로 강제하지 않는다.

---

# 12. 월간 계획안 화면

## 12.1 생성 조건

대상 연간계획안이:

```text
CONFIRMED
```

상태여야 한다.

## 12.2 상위 계획 반영

Confirmed Yearly Plan은 월간 생성의:

```text
Context / Constraint
```

로 사용한다.

연간 값을 월간 특정 셀에 무조건 그대로 복사하도록 화면/로직을 고정하지 않는다.

## 12.3 Monthly Template A v0

Template A는 전국 표준 고정 양식이 아니라 의미 기반 Section을 렌더링하는 P0 기본 Template이다.

- 기존의 고정 8행 정의는 제거한다.
- Section 수와 순서는 의미 구조와 선택된 Template에 따라 달라질 수 있다.

### 기본 지원

```text
theme
dynamic WeekPeriod axis
outdoor_play
safety_education
```

- 대상 월의 주차는 고정 4주/5주가 아니라 ordered `WeekPeriod` 목록으로 동적 산출한다.
- 각 WeekPeriod가 안정적으로 참조할 `week_id` 필드를 가진다는 사실은 확정이다.
- `week_id`의 생성 형식·재산출 시 안정성, 정확한 주 경계·부분 주·휴원일·기관 Calendar Override 정책은 OD-M02에서 확정한다.
- `outdoor_play`와 `safety_education`은 기본 지원하되 특정 행 번호나 표시 위치에 고정하지 않는다.

### Optional Section

```text
goals
habits
```

- goals와 habits는 필수 non-empty Section으로 승격하지 않는다.
- `Optional`은 required 또는 non-empty가 아니라는 뜻이다. 비활성화된 Optional Section은 출력에서 생략하며, 값이 없다는 사실만으로 생성·저장·확정을 차단하지 않는다. 빈 기본행을 항상 렌더링한다는 뜻이 아니다.
- Optional Section의 기본 활성화 여부, 빈 값일 때 숨김/빈 행/안내 상태 중 무엇을 렌더링할지, 계층 Label 기본값은 OD-M01의 남은 Contract에서 확정한다. 그 전에는 임의의 빈 행 정책을 전역 기본값으로 만들지 않는다.
- 성품인사는 월간 기본 Section 또는 기본행에서 제거한다.
- 온보딩 Profile 값은 그 자체로 월간 출력에 렌더링되지 않는다.
- 기관 요구가 있고 `Custom Section Mapping`이 명시적으로 활성화된 경우에만 선택 렌더링한다.

### Section 표시와 Label

각 Section은 필요에 따라 다음 표시 방식을 가질 수 있다.

```text
weekly_cells
monthly_merged_summary
```

- 표시 방식은 Section별로 결정하며 모든 Section에 하나의 방식을 강제하지 않는다.
- 원본 양식 Label은 `source_label`로 보존하고 내부 의미는 `semantic_key`로 Mapping한다.
- `source_label`은 Template/Import Mapping 메타데이터이며 Evidence Source 필드가 아니다.
- 계층형 Label을 허용한다.
- 안전교육을 항상 특정 번째 행에 배치하지 않는다.

### 미확정 관계

`subtheme`과 `expected_play`는 같은 의미로 확인되지 않았다.

- 두 필드를 자동 동의어로 합치지 않는다.
- 원본 Label과 Mapping 근거를 보존한다.
- 정확한 관계와 Mapping Contract는 OD-M03에서 확정한다.

### 남은 Monthly 결정

- OD-M01 — 기본 활성화·표시 방식·계층 Label·빈 값 정책
- OD-M02 — Dynamic WeekPeriod 경계·Override와 `week_id` 생성·안정성 규칙
- OD-M03 — subtheme과 expected_play 의미 관계
- OD-M04 — Safety Rule Data·월 배치 정책·출력 Grouping

Template A를 전국 공통 필수 8행으로 구현하지 않는다. 여기서 “기본 지원”은 전국 의무 또는 모든 Section의 필수 non-empty를 뜻하지 않는다.

---

# 13. 주간 계획안 화면

## 13.1 생성 조건

대상 월간계획안이:

```text
CONFIRMED
```

상태여야 한다.

## 13.2 상위 계획 반영

Confirmed Monthly Plan을 주간 생성의 Context / Constraint로 사용한다.

## 13.3 출력 위치

최초 세팅 값에 따라 주간 계획 결과가 들어갈 위치가 달라질 수 있다.

```text
별도 주간계획안
주간보육일지 계획칸
일일보육일지 계획칸
```

정확한 의미 구조와 출력 위치별 Adapter Contract는 OD-W02 및 `docs/contracts.md`에서 확정한다. P0 첫 Weekly Slice 전까지 요일/Slot 수를 고정 18칸으로 가정하지 않는다.

OD-W02가 `OPEN`인 동안 세 후보 중 어느 것도 구현 완료된 Adapter로 간주하거나 실행 가능한 설정으로 노출하지 않는다. 승인 후에는 OD-W02가 정한 첫 Adapter만 활성화하고, 보육일지 계획칸 Adapter를 제공하더라도 전체 보육일지 생성 기능으로 범위를 확대하지 않는다.

### 주의

주간계획안은 국가 정보공개포털 공시 대상 표준양식으로 가정하지 않는다.

기관별 양식 다양성을 고려한다.

---

# 14. 부분 생성 — 기존 계획 이어받기

지원 목록에 명시되고 검증된 기존 연간계획안 형식을 업로드한 경우 이미 작성된 기간을 보존한다. 기관 고유 양식을 범용 파싱하거나 지원되지 않은 형식에 추정 Mapping을 적용하지 않는다.

예:

```text
3월~8월 기존 계획 존재
        ↓
9월~2월 생성
```

### 원칙

- 기존 값을 자동 덮어쓰지 않는다.
- 생성 대상 범위를 화면에서 명확하게 보여준다.
- Imported 값과 새 생성값을 구분할 수 있어야 한다.
- 생성 방식은 Provenance에서 별도로 관리한다.
- 지원 형식·버전과 Mapping 결과를 사용자에게 보여준다.
- 지원되지 않은 형식은 Import를 실행하지 않고 지원 형식 안내, 수동 입력 또는 다시 업로드할 수 있는 복구 경로를 제공한다.
- OD-N09가 `OPEN`인 동안 Import Slice를 활성화하지 않는다. OD-N09는 P0 전체의 Yearly 직접 생성 흐름을 막지 않는 Non-blocking 결정이지만, Import/부분 생성 Slice 착수 전에는 확정해야 한다.

```text
기존 업로드
→ IMPORTED

새 Rule+LLM 생성
→ RULE_LLM
```

---

# 15. 접근성

- 출처 점은 색만으로 의미를 전달하지 않는다.
- 출처 점/버튼에 접근성 Label을 제공한다.
- 병합 셀이 존재할 경우 키보드 탐색 순서를 내부 필드 순서와 맞춘다.
- Disabled 상태는 색만으로 표현하지 않는다.
- 오류와 경고는 시각적으로 구분한다.

---

# 16. 오류/경고 문구 원칙

기술 오류명만 노출하지 않는다.

사용자가 다음 행동을 알 수 있도록 안내한다.

### 예

나쁜 예:

```text
PARENT_PLAN_NOT_CONFIRMED
```

좋은 예:

```text
월간계획안을 만들려면 먼저 연간계획안을 확정해 주세요.
```

### 차단 오류

작업을 진행할 수 없는 경우.

예:

- 상위 계획 미확정
- 필수 입력 누락
- 계획 구조 자체 생성 실패

### 경고

계획안은 존재하지만 확인이 필요한 경우.

예:

- 빈 칸 존재
- 반복 활동
- 안전교육 배치 확인 필요

경고와 차단 오류를 같은 수준으로 취급하지 않는다.

---

# 17. 저장/이탈

P0의 기본 저장 방식은 명시적 저장이다. `명시적 저장`, `저장되지 않은 변경 이탈 경고`, `CONFIRMED 읽기 중심·편집 차단`은 OD-N06에서 확정된 P0 경계다.

DRAFT 편집 중 저장되지 않은 변경사항이 있는 상태에서 화면을 이탈할 경우:

- 변경사항이 남아 있음을 사용자에게 알린다.
- 저장 또는 이탈을 선택할 수 있게 한다.

자동저장, 동시 편집 충돌 처리, CONFIRMED 이후 확정 취소·재편집·새 Version 정책은 OD-N06의 남은 Contract와 FE/BE Contract에서 확정한다. 따라서 OD-N06 상태는 `PARTIALLY_RESOLVED`이며, 구현자가 남은 정책을 임의로 추가하지 않는다.

---

# 18. Decision Register — OD-Y / OD-M / OD-W / OD-N

세부 근거·영향 범위·권장안은 `docs/open-decisions.md`를 따른다. 이 절은 화면에 직접 영향을 주는 현재 결정 상태를 요약한다.

## 18.1 Yearly — P0 승인 완료

| ID | 결정 | 상태 |
|---|---|---|
| OD-Y01 | `school_year + classroom_ref + month_periods[12] + 각 월 theme`를 Yearly v0 필수 구조로 사용하고, 나머지는 Optional로 둔다. 편집 단위는 `item_id`와 `semantic_key`로 주소화한다. | RESOLVED_FOR_P0 |
| OD-Y02 | 사람이 검증한 versioned Theme Reference v0를 Rule 후보 원천으로 사용하고, LLM은 선택된 theme의 표현만 다듬는다. | RESOLVED_FOR_P0 |
| OD-Y03 | Plan 소유 단위는 classroom, Confirm Actor는 opaque `actor_id`/`user_id`로 한다. 혼합연령도 classroom 단위 Plan 하나를 사용한다. | RESOLVED_FOR_P0 |

## 18.2 Monthly 착수 전

| ID | 결정 대상 | 상태 | 승인일 |
|---|---|---|---|
| OD-M01 | Template A Section의 활성화·표시·계층·빈 값 정책의 결정 주체 | RESOLVED_FOR_P0 | 2026-09-11 |
| OD-M02 | Dynamic WeekPeriod 산출·경계·Override와 `week_id` 안정성 | RESOLVED_FOR_P0 | 2026-09-11 |
| OD-M03 | `subtheme`과 `expected_play`의 의미 관계 및 Mapping | RESOLVED_FOR_P0 | 2026-09-11 |
| OD-M04 | Safety Rule Data, 월 배치 정책, 비상대응·대피훈련 Grouping | RESOLVED_FOR_P0 | 2026-09-11 |

화면에 직접 영향을 주는 결정은 다음이다. 상세는 docs/open-decisions.md §4에 있다.

- Section의 활성화 여부와 표시 방식은 **선택된 Template instance가 결정**한다. 화면에 전역 기본값을 두지 않는다.
- **`display_mode`는 Section마다 명시**되며 `WEEKLY_CELLS`·`MONTHLY_MERGED_SUMMARY` 두 값으로 영구 고정하지 않는다.
- 활성 Section에 값이 없어도 **Section 자체를 삭제하지 않는다**(`RENDER_EMPTY_CELL`). 값 없음만으로 생성·저장·확정을 차단하지 않는다.
- 계층 Label은 **2단까지**만 기본 지원한다.
- 주차 열은 `SSUKSAK_P0_CANONICAL_WEEK_POLICY`로 산출한다. 첫 주가 전월에 시작하거나 마지막 주가 다음 월에 끝날 수 있고, `display_label`(예: `9월 1주`)은 실제 날짜 범위와 분리된다. `display_group` Override로 두 주를 한 칸에 병합해 표시할 수 있다.
- `subtheme`/`expected_play`는 중립 슬롯 하나로 표시하되 **원본 Label을 화면에 보존**한다.
- `focus`는 **Template version이 정한다.** `monthly-template-a-v0.1.0`에서는 비활성이고, `monthly-template-a-v0.2.0`(2026-09-13 OD-N18)에서는 활성이며 주차별 **중심 경험**을 담는다. 두 version은 공존하며 어느 쪽도 다른 쪽으로 자동 대체되지 않는다. 화면은 `focus`·`week_axis` 같은 내부 이름을 그대로 노출하지 않고 `중심 경험`으로 표시하며, 행 순서는 중심 경험 → 바깥놀이 → 안전교육 → 기본생활습관 → 목표다. **행 순서는 표시 전용이며 Template의 Section 정의를 바꾸지 않는다.**
- 안전교육은 **구조로는 항상 표현 가능하지만 값이 없을 수 있다.** 배치 Source가 없으면 임의 배치를 생성하지 않고 `법정 요건 미검증 / source required` 상태를 안내한다. 이 상태의 정확한 표현 방식은 M1 설계에서 승인받는다.

## 18.3 Weekly 착수 전

| ID | 남은 결정 | 상태 |
|---|---|---|
| OD-W01 | 월간 미사용 시 YEARLY → WEEKLY 직접 Gate와 parent 관계 | OPEN |
| OD-W02 | semantic WeeklyPlan과 출력 위치별 Adapter Contract | OPEN |

## 18.4 Non-blocking

| ID | 결정 항목 | 상태 |
|---|---|---|
| OD-N01 | PostgreSQL 15 최종 팀 확정 | PROVISIONAL |
| OD-N02 | 혼합연령의 물리 저장 방식 | OPEN |
| OD-N03 | Activity taxonomy와 초기 Reference 범위 | OPEN |
| OD-N04 | LLM 공급자·모델·timeout·retry | OPEN |
| OD-N05 | Provenance의 물리 저장 Schema | OPEN |
| OD-N06 | 명시적 저장·이탈 경고·CONFIRMED 편집 차단은 P0 확정. 자동저장·충돌·확정 이후 Version 정책은 남은 Contract | PARTIALLY_RESOLVED |
| OD-N07 | Template A 외 추가 Template 범위 | DEFERRED |
| OD-N08 | Yearly HTTP API와 물리 Persistence Contract | OPEN |
| OD-N09 | 지원 Yearly Import 형식·버전, 파싱·Mapping, 부분 생성 범위 Contract. P0 전체에는 Non-blocking이나 Import Slice 전에는 필수 | OPEN |

OD-Y01~OD-Y03은 P0 제품·Application Contract로 승인되었다. 물리 DB/API 세부는 OD-N 계열과 `docs/contracts.md`에서 별도로 확정한다.

---

# 19. P0 화면 Acceptance Criteria

## 공통

- [ ] 사용자가 현재 Plan 상태를 알 수 있다.
- [ ] 생성 가능/불가능 이유를 알 수 있다.
- [ ] DRAFT에서 셀을 수정할 수 있다.
- [ ] DRAFT에서 셀 하나만 다시 생성할 수 있다.
- [ ] 전체 재생성 기능은 없다.
- [ ] 근거가 있는 셀에서 Provenance를 열어볼 수 있다.
- [ ] 근거가 없는 Item에서도 일반 `정보/이력` 동작으로 Generation Method와 Audit History를 열어볼 수 있다.
- [ ] 하나의 출처 점이 Item의 `EvidenceSource[]` 전체를 나타내며 패널에서 모든 근거를 확인할 수 있다.
- [ ] Evidence가 없으면 패널에 `등록된 근거 없음`이 표시된다.
- [ ] Evidence Source, Generation Method, Audit History가 서로 분리되어 표시된다.
- [ ] 출처 UI는 내보내기에 포함되지 않는다.
- [ ] 확정이 자동 제출이 아님을 알 수 있다.
- [ ] 변경 이력을 확인할 수 있다.
- [ ] Confirm Actor가 opaque `actor_id`/`user_id`로 기록된다.
- [ ] Optional 외부 기능 실패가 Core 화면 전체 실패로 보이지 않는다.

## 연간

- [ ] 연간 DRAFT는 `school_year`, `classroom_ref`, 3월~다음 해 2월의 `month_periods[12]`를 가진다.
- [ ] 12개 MonthPeriod마다 theme가 존재한다.
- [ ] 편집·셀 재생성 대상은 안정적인 `item_id`와 `semantic_key`로 식별된다.
- [ ] Theme는 versioned Theme Reference v0 후보에서 Rule이 선택하고 LLM은 표현만 다듬는다.
- [ ] 혼합연령도 classroom 단위 Plan 하나로 생성된다.
- [ ] 교사 수정 후 CONFIRMED할 수 있다.
- [ ] CONFIRMED 후 월간 생성 가능 상태가 된다.
- [ ] OD-N09에서 승인된 지원 Yearly 형식은 기존 기간을 보존하고 남은 기간만 생성할 수 있다.
- [ ] 지원되지 않은 형식은 Import가 실행되지 않으며 수동 입력 또는 재업로드 복구 경로를 제공한다.

## 월간

- [ ] 연간 미확정 시 생성이 차단된다.
- [ ] 차단 이유와 해결 방법을 표시한다.
- [ ] 연간 확정 후 월간 DRAFT를 만들 수 있다.
- [ ] 주차 열은 대상 기간에서 동적으로 생성된다.
- [ ] theme, outdoor_play, safety_education을 기본 지원한다.
- [ ] goals와 habits는 Optional이다.
- [ ] 성품인사를 월간 기본행으로 생성하지 않는다.
- [ ] 성품인사는 명시적으로 활성화된 Custom Section Mapping 없이는 월간 출력에 렌더링되지 않는다.
- [ ] Section별로 `weekly_cells`와 `monthly_merged_summary`를 표시할 수 있다.
- [ ] `subtheme`과 `expected_play`를 자동 병합하지 않는다.
- [ ] 교사 수정 후 CONFIRMED할 수 있다.

## 주간

- [ ] 월간 미확정 시 생성이 차단된다.
- [ ] 월간 확정 후 주간 DRAFT를 만들 수 있다.
- [ ] OD-W02에서 승인된 출력 Adapter만 선택·실행할 수 있다.
- [ ] 보육일지 계획칸 Adapter는 전체 보육일지 생성 기능으로 오인되지 않는다.
- [ ] 교사 수정 후 CONFIRMED할 수 있다.

---

# 20. 구현 시 금지사항

1. 전체 재생성 버튼을 임의로 추가하지 않는다.
2. 출처 표시 토글을 임의로 추가하지 않는다.
3. `AI`를 Evidence Source로 표시하지 않는다.
4. `TEACHER_EDIT`을 Evidence Source로 표시하지 않는다.
5. `CONFIRMED`를 자동 제출 상태로 취급하지 않는다.
6. 상위 계획 미확정인데 하위 계획 생성 버튼을 정상 실행시키지 않는다.
7. 월간 Template A를 전국 표준 8행으로 하드코딩하지 않는다.
8. 연간 Sample을 Monthly Template A 검증 자료로 사용하지 않는다.
9. 아동 명단 미입력을 Planning P0 차단 조건으로 만들지 않는다.
10. OD-M/OD-W/OD-N의 미결정 항목을 구현 편의를 위해 임의로 확정하지 않는다.
11. OD-N09에서 승인되지 않은 Yearly 형식을 지원 대상으로 노출하거나 추정 Mapping으로 가져오지 않는다.
12. 확정된 Safety fallback이 있는 것처럼 처리하지 않는다. P0에는 제품 기본 배치 정책이 없다(OD-M04 `RESOLVED_FOR_P0`). Source 없이 안전교육 내용을 생성하거나 법적 충족을 주장하지 않는다. **M1 구조 Slice에서 Safety Section을 구조로만 표현하는 것은 우회가 아니라 요구되는 동작이다** — 아래 P0 해석 참조.
13. OD-W02 승인 전 주간 출력 위치 후보를 저장·실행 가능한 Adapter로 활성화하지 않는다.

## 20.1 Safety 우회 금지 조항의 P0 해석 — 2026-09-11 확정

`관련 Monthly 생성 Slice를 우회 실행하지 않는다`의 P0 해석을 다음으로 확정한다.

**M1 구조 Slice 자체는 허용한다.** 단 다음 4가지를 지킬 때만이다.

```text
허용   Safety Section의 구조 표현
금지   Safety placement 자동 생성
금지   source 없는 Safety 내용 생성
금지   법적 충족 claim
```

즉 M1은 Safety 기능을 우회해서 가짜 완성 결과를 만드는 Slice가 아니라, **Safety의
unresolved 상태를 정직하게 표현하는 구조 Slice**다.

실제 Safety 배치·검증 기능은 M2에서 배치 Source가 주어진 경우에 구현한다.
