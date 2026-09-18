# API 계약 — P0 6주차

> **이 파일이 계약 원본이다.** 노션이나 Slack 사본이 아니라 여기를 고친다 —
> 계약 변경이 PR diff 에 보여야 FE·BE 가 어긋나지 않는다.
> PM 이 엔드포인트·UI states 를 잡았고 **Response 스키마는 BE 가 채운다**(맨 아래 목록).
> 2026-09-19 갱신 — 커밋된 DB·ADR·FE 와 전면 대조. 출처를 3축(Evidence·Generation·Audit)으로 교체,
> 칸 수정을 `PUT` 으로, 목록 조회 신설, 계획 문서 구성(`plan-config`)을 7주차로 이관.
> **`plan-config` 가 빠지면서 이후 절 번호가 하나씩 당겨졌다.**

---

## 이 문서를 쓰는 법

```
BE   이 계약대로 구현한다.  구현하고 나서 문서화하지 않는다
FE   이 계약을 다시 정의하지 않는다.  MSW 목업을 이 형식으로 만든다
```

**`UI states` 를 꼭 보라.** FE 가 화면을 못 그리는 건 보통 이것 때문이다 —
"로딩 중", "하나도 없을 때", "실패했을 때" 를 서버가 안 알려주면 FE 가 추측한다.

## 공통

```
Base        /api
Content     application/json
인증        P1(8주차)부터.  지금은 없음
날짜        ISO 8601 (2026-03-01)
연령        학년도 기준 연 나이 3·4·5.  만 나이 아님
```

**인증이 붙기 전에는 실제 아동 실명을 입력하지 않는다.** 개발·데모는 가명으로 한다 (ADR-004).

**공통 에러 형식**

```json
{ "error": { "code": "VALIDATION_FAILED", "message": "사람이 읽는 문장",
             "fields": ["age_min"] } }
```

**`fields` 는 항상 배열이다.** 하나여도 `["age_min"]` 이다 — FE 가 단수·복수를 분기하지 않게 한다.
점 표기로 위치를 가리킨다(`months.3`). 배열 원소는 인덱스가 아니라 **의미 있는 키**를 쓴다.
**서버는 첫 번째에서 멈추지 않고 전부 모아서 반환한다.**

| code | status | 뜻 |
|---|---|---|
| `VALIDATION_FAILED` | 422 | 입력값이 규격 밖 |
| `NOT_FOUND` | 404 | 대상 없음 |
| `GATE_BLOCKED` | 409 | 층 게이트 — 연간이 확정 전인데 월간 요청 |
| `ALREADY_EXISTS` | 409 | 같은 대상에 이미 있음. 조회로 찾는다 |
| `ALREADY_CONFIRMED` | 409 | 확정된 계획안을 수정하려 함. 되돌리기는 P1 |
| `UNSUPPORTED_FILE_TYPE` | 400 | 지원하지 않는 파일 형식 |
| `NO_ACTIVITIES` | 503 | 활동 풀이 비었음 (운영 오류). **재시도해도 같다** |
| `LLM_BUDGET_EXCEEDED` | 503 | 팀 LLM 예산 한도 도달. 운영 문의. **아직 낼 수 있는 서버가 없다** ↓ |
| `GENERATION_FAILED` | 500 | 생성 실패. **부분 결과를 저장하지 않는다** |

**409 가 셋이다.** 상태 코드가 같아도 FE 가 띄울 문구가 다르므로 `code` 로 갈라 본다 —
"연간부터 확정해주세요" / "이미 있습니다, 기존 것으로 이동" / "확정된 문서는 수정할 수 없어요".

> **`LLM_BUDGET_EXCEEDED` 는 예약된 코드다.** 지금 LLM 을 부르는 유일한 곳이
> `frontend/app/api/assistant/route.ts`(Next.js 라우트)라 **`shared/llm` 토큰 카운터를 거치지 않는다.**
> 호출 위치가 정해져야 이 에러를 낼 주체가 생긴다(맨 아래 「채워야 할 곳」). 그 전까지 FE 는 이 코드를 받지 않는다.

---

## 1. 원 — `POST /api/centers`

**Request**

```json
{ "name": "서충주어린이집", "director_name": "김원장", "region": "충청북도 충주시" }
```

**Response** `201`

```json
{ "id": 1, "name": "...", "director_name": "...", "region": "...", "created_at": "..." }
```

**UI states**

| | |
|---|---|
| loading | 저장 중 — 버튼 비활성 |
| empty | 해당 없음 |
| success | S2 로 이동 |
| error | `VALIDATION_FAILED` — 입력값 유지, 해당 칸에 표시 |

**중복 생성을 막지 않는다.** 이름만으로 `UNIQUE` 를 걸면 다른 지역의 같은 이름 원이 막힌다.
계정 단위 판단은 인증이 붙는 P1 이다.

---

## 2. 반 — `POST /api/centers/{center_id}/classes`

**Request**

```json
{ "name": "햇님반", "age_min": 3, "age_max": 4,
  "child_count": 18, "teacher_name": "김선생", "consent_confirmed": true }
```

`age_min` ≤ `age_max`, 둘 다 3~5. `child_count` 는 **선택**(null 허용, 양의 정수).

**`school_year` 는 받지 않는다. 서버가 요청 시각 기준으로 채운다.**
화면에 학년도를 고르는 칸이 없으므로 교사는 어차피 값을 정하지 않는다. 남는 것은
"누가 계산하느냐"뿐인데, FE 가 계산하면 브라우저 시계에 의존한다. 기기 시계가 하루 틀리면
3월 1일 전후에 만든 반이 다른 학년도로 들어가고, `UNIQUE(center_id, name, school_year)`
때문에 **같은 반이 두 행으로 갈라진다.** 화면에 안 보이는 값이라 아무도 눈치채지 못한다.
**서버 시간대는 KST 로 고정한다** — UTC 로 계산하면 3월 1일 00:00~09:00 에 만든 반이
전년도로 들어간다. 경계는 3월 1일이다(`2026` = 2026-03 ~ 2027-02).

> 「2027학년도 반 미리 만들기」 화면이 생기면 request 에 `school_year` 를 **optional 로 추가**한다.
> 보내면 그 값을 쓰고 안 보내면 서버가 채운다 — 기존 계약을 깨지 않는다.

**FE 는 연령 체크박스 3개를 두 값으로 바꿔 보낸다.**

```
[v]만3 [ ]만4 [ ]만5  → 3 · 3        [v]만3 [v]만4 [ ]만5  → 3 · 4
[ ]만3 [v]만4 [ ]만5  → 4 · 4        [ ]만3 [v]만4 [v]만5  → 4 · 5
[ ]만3 [ ]만4 [v]만5  → 5 · 5        [v]만3 [v]만4 [v]만5  → 3 · 5
```

**떨어진 조합은 범위로 채운다.** 만3·만5 만 고르면 `3 · 5` 다 — 만 4세만 빼는 반은 실무에 없다.
**FE 는 이 경우 「만 3~5세반」으로 표시한다.** 「만 3·5세반」으로 쓰면 본 것과 저장된 것이 달라진다.

> **`selected_ages` 같은 배열을 보내지 않는다.** `classes` 는 `age_min`·`age_max` **범위 컬럼**이고
> `CHECK (age_min <= age_max)` 가 걸려 있어 「4세만 제외」를 애초에 표현할 수 없다.
> 배열을 보내면 서버가 범위로 바꿔야 하는데, 그 변환 규칙이 두 곳에 생긴다.

혼합반이 실측 39% 다. **숫자 하나로 받으면 혼합반을 못 만든다.**

**`consent_confirmed` 는 동의 확인 체크박스다.** `true` 면 서버가
`classes.consent_confirmed_at` 에 현재 시각을 넣는다. 체크박스 자체는 **증빙이 아니라
교사에게 알리는 장치**다(PRD S2) — 컬럼을 두는 이유는 **복원**이다. 「나중에 입력할래요」로
건너뛰면 아동이 0명이라, 아동 수로 복원하면 교사가 들어올 때마다 다시 체크해야 한다.

`consent_confirmed` 가 `false` 이거나 없으면 `consent_confirmed_at` 은 `null` 로 둔다.
**검증 실패가 아니다** — 아동 명단을 건너뛰는 경로가 정상이다(§2-1).

**Response** `201` — 생성된 반. `school_year` 와 `consent_confirmed_at` 을 포함한다.

**`GET /api/centers/{center_id}/classes`** → `{ "items": [...] }`

**UI states**

| | |
|---|---|
| loading | 목록 스켈레톤 |
| **empty** | `items: []` — "반을 추가해 주세요" + 추가 버튼 |
| success | 반 카드 목록 |
| error | 해당 카드에만 표시, 나머지 유지 |

**수정(PUT·PATCH)은 P1 이다.** 설정 화면의 수정 버튼은 자리만 잡아둔 것이다.
**반 이름 수정은 단순 UPDATE 가 아니다** — `UNIQUE(center_id, name, school_year)` 가 걸려 있고
`plans` 스냅샷과의 관계도 정해야 한다.

---

## 2-1. 아동 명단 — `POST /api/classes/{class_id}/children`

**Request**

```json
{ "name": "이승석" }
```

**이름 하나만 받는다.** 생년월일·성별·건강정보를 받지 않는다 (ADR-004).

**Response** `201`

```json
{ "id": 7, "class_id": 1, "name": "이승석", "code": "승석", "created_at": "..." }
```

**`code` 는 서버가 등록 시점에 발급한다.** 받침 있는 더미 한글 이름이다 —
영문 토큰이면 조사가 복원 후 틀어진다(`Child1이` / `Child2가`).
나중에 발급하면 이미 쌓인 기록을 다시 훑어야 한다.

**`code` 를 응답에 포함한다.** 화면에 배지로 보여준다 — 교사가 "LLM 에는 이 이름이 나간다"를 안다.

**`code` 발급 규칙**

- 실제 아동 이름에서 파생하지 않는다.
- 서버가 관리하는 한글 가명 Pool 에서 자동 발급한다. Pool 은 `backend/resources/` 에 둔다.
- 동일한 `class_id` 안에서는 중복되지 않는다 — **`UNIQUE(class_id, code)` 로 DB 가 지킨다.**
  발급 로직에 버그가 있어도 잘못된 데이터가 들어가지 않는다. 경합 재시도는 만들지 않는다.
- 한 번 발급된 `code` 는 해당 아동이 삭제되기 전까지 변경하지 않는다.
- **삭제된 아동의 `code` 는 재사용해도 된다.** 행이 사라지면 제약이 풀린다. 발급 이력을
  따로 남기지 않는다.
- **`code` 는 LLM 전송 시에만 쓴다. 기록·조회·참조는 `children.id` 로 한다.**
  P1 관찰일지가 아동을 `code` 로 참조하면 재등록 때 끊긴다.

**`GET /api/classes/{class_id}/children`** → `{ "items": [...] }`

> 목록 응답 봉투는 **`{ items }` 하나로 통일한다.** `items.length` 로 알 수 있는 `count` 를
> 따로 보내지 않는다 — `child_count`(반의 목표 원아 수)와 이름이 비슷해 혼동된다.

**`DELETE /api/children/{id}`** → `204`. 오타 수정은 삭제 후 재등록이다.
P0 에서는 아동 기록이 없는 온보딩 단계에서만 일어난다. 이름 수정(PATCH)은 P1 이다.

**UI states**

| | |
|---|---|
| loading | 명단 스켈레톤 |
| **empty** | `items: []` — "아직 등록된 아동이 없어요. 위에서 이름을 입력해 추가해주세요" |
| success | 번호 + 코드 배지 + 실명. 하단에 "현재 N명의 아동이 등록되어 있어요" |
| error | 추가 실패 — **입력한 이름을 지우지 않는다** |

**0명이어도 다음 단계로 간다.** 「나중에 입력할래요」 버튼이 있다.
건너뛰면 메인 화면에 배너를 띄운다 — 문구는 *"관찰일지를 쓰려면 명단이 필요합니다"*.
**계획안(P0)은 명단 없이도 정상 작동한다.** 지금 막힌 게 아니라는 뜻이 전달돼야 한다.

---

## 3. 성품인사 — `GET·PUT /api/centers/{center_id}/greetings`

**GET Response**

```json
{ "enabled": false, "items": [ { "month": 3, "text": "..." }, ... ] }
```

12개. 원이 설정한 적 없으면 **기본 12개를 채워서 내려준다.** 빈 배열을 주지 않는다.

**`enabled` 기본값은 `false` 다.** 충청북도 수집분 23개 중 성품인사가 있는 건 0개다 —
쓰는 원이 소수라 기본을 off 로 둔다. (ADR-012)

**호출 지점은 온보딩이 아니라 설정 화면(7주차)이다.** 계약 자체는 안 바뀐다.
**6주차에 FE 가 이 엔드포인트를 부르지 않는다.** (ADR-012 — 온보딩 S4 를 비웠다)

**PUT Request** — 같은 형식. **전체 교체다.**

```
items 는 정확히 12개다.                          그 외는 VALIDATION_FAILED 422
month 는 1~12 가 각각 정확히 한 번씩 나온다.       누락·중복은 422
enabled: false 면 items 를 무시하고 enabled 만 갱신한다.
```

화면이 **12칸 폼**이라 12개월이 한 화면에 나오고 「설정 완료」를 한 번 누른다.
부분 교체로 두면 FE 가 어느 칸이 바뀌었는지 따로 추적해야 하고,
"`enabled` 만 끄는 요청"과 "3월 문구만 바꾸는 요청"을 따로 정의해야 한다.

**UI states**

| | |
|---|---|
| empty | **발생하지 않는다** — 서버가 기본값을 채운다 |
| success | 12칸 폼 |

---

## 4. 연간계획안 생성 — `POST /api/plans/annual`   ★ 6주차 핵심

**Request**

```json
{ "class_id": 1, "form_id": null }
```

**`school_year` 를 받지 않는다.** `class_id` 가 학년도를 결정한다 — `classes` 행은
학년도마다 새로 만든다(schema.md 불변규칙 5). 따로 받으면 불일치 경로만 생긴다.

**`form_id` 는 원이 등록한 기관 양식이다**(§8). `null` 이면 기본 양식으로 만든다.
6주차 화면은 기본 양식만 쓴다.

**Response** `201`

```json
{
  "id": 10,
  "class_id": 1,
  "school_year": 2026,
  "status": "DRAFT",
  "months": [
    {
      "month": 3,
      "theme": "봄과 나",
      "sub_themes": ["새로운 친구", "봄이 왔어요"],
      "evidence": [
        { "source_type": "THEME_REFERENCE",
          "source_id": "theme-ref-2026",
          "source_version": "v0.1.2",
          "display_name": "연간계획안 주제 참고자료" }
      ],
      "generation": { "method": "RULE_LLM",
                      "rule_id": "annual-theme", "rule_version": "v1" }
    }
  ]
}
```

**`months` 는 항상 12개다.** 3월 시작 ~ 익년 2월.

### 출처는 세 축이다 — 한 값에 섞지 않는다

`source_type` 이라는 단일 필드는 **없앴다.** CLAUDE.md 와 `p0-planning` 이 정한 3축을 쓴다.

```
Evidence     이 값이 어디서 왔나     CURRICULUM · THEME_REFERENCE · PARENT_PLAN · SAFETY_RULE
                                    ACTIVITY_REFERENCE · CALENDAR · EVENT · TREND …
Generation   어떻게 만들어졌나       RULE_ONLY · RULE_LLM · IMPORTED · MANUAL · TEACHER_EDIT
Audit        나중에 무슨 일이 있었나  CREATED · REGENERATED · TEACHER_EDITED · CONFIRMED
```

- **`evidence` 는 배열이다.** 한 칸이 여러 근거를 가질 수 있다.
- **`generation.method` 가 `RULE_ONLY`·`RULE_LLM` 이면 `rule_id`·`rule_version` 이 필수다.**
- **「AI」는 출처가 아니라 제조 방법이다.** AI 가 만든 값도 근거는 누리과정·주제·상위 계획안이다.
- **`audit` 은 이 응답에 싣지 않는다.** 쓰기 생명주기가 달라 별도로 관리한다(§9).
  S6 화면이 필요로 하는 것은 `evidence` 와 `generation` 뿐이다.

**S6 의 좌상단 점은 `generation.method` 를 본다.** 교사가 고친 칸(`TEACHER_EDIT`)과
시스템이 만든 칸을 구분한다. 근거를 눌렀을 때 펼치는 것은 `evidence` 다.

### 생성 방식

**RAG 로 생성하고 규칙 엔진이 검사한다.** ADR-005 의 「배치·선별은 규칙 엔진, LLM 은
문장화만」을 뒤집는다 — 생성과 검사의 순서가 반대다.

**ADR-003 도 같이 깨진다.** ADR-003 은 P0a(5~6주차)를 「결정론적 초안 생성」으로 정의하고
*"P0a 가 결정론적이라 golden set 이 성립한다"*, *"golden set 을 6주차 말에 반드시 고정한다"* 로
검증 전략을 세웠다. **RAG 를 쓰면 출력이 매번 달라져 golden set 이 성립하지 않는다.**
대체 검증 전략(예: 규칙 검사 통과 여부만 고정 검증)을 정해야 한다.

**ADR 작성 예정 — ADR-003 · ADR-005 두 개를 대체한다.**

법정 안전교육 시수·날짜·고유명사처럼 **틀리면 안 되는 값은 규칙 엔진이 원문과 대조한다.**
검사에 실패하면 `GENERATION_FAILED` 500 이고 **부분 결과를 저장하지 않는다.**

> 안전교육 시수는 연 44시간이다(아동복지법 시행령 별표6 — 교통안전 2개월 1회,
> 실종·유괴 3개월 1회, 성폭력·아동학대 6개월 1회). **서버 상수로 둔다.** 원마다 다른 값이
> 필요해지면 그때 `plan-config` 를 만든다(§9).

**결정론을 약속하지 않는다.** LLM 이 개입하므로 같은 입력이라도 문구가 달라질 수 있다.
FE 는 목업을 고정값으로 만들되, **실제 응답이 매번 같다고 가정하지 않는다.**

### 반당 하나다

같은 `class_id` 에 연간계획안이 이미 있으면 새로 만들지 않는다.

```json
409  { "error": { "code": "ALREADY_EXISTS",
                  "message": "이 반의 연간계획안이 이미 있습니다.",
                  "fields": ["class_id"] } }
```

`DRAFT` 든 `CONFIRMED` 든 같은 코드다 — FE 가 할 행동이 "기존 것으로 이동" 으로 같다.
기존 것은 §5 목록 조회로 찾는다.

**재생성·삭제는 P0 에 없다.** 마음에 안 드는 칸은 §6 으로 고친다.

**UI states**

| | |
|---|---|
| **loading** | ★ 수 초 걸린다. 진행 표시가 없으면 교사가 다시 누른다 |
| empty | 발생하지 않는다 — 12개월이 항상 찬다 |
| success | S6 으로 이동 |
| error | `NO_ACTIVITIES` 503 → "활동 데이터가 없습니다" (운영 문의). **자동 재시도하지 않는다**<br>`LLM_BUDGET_EXCEEDED` 503 → 운영 문의<br>`ALREADY_EXISTS` 409 → 기존 계획안으로 이동<br>`GENERATION_FAILED` 500 → 재시도 버튼. **부분 저장 없음** |

---

## 5. 조회 — `GET /api/plans/annual/{id}` · `GET /api/plans/annual?class_id=`

**단건** `GET /api/plans/annual/{id}` — 생성과 같은 형식.

**목록** `GET /api/plans/annual?class_id=1`

```json
{ "items": [
    { "id": 10, "class_id": 1, "school_year": 2026,
      "status": "DRAFT", "created_at": "...", "confirmed_at": null }
] }
```

**요약만 담는다.** `months` 12개는 넣지 않는다 — 상세는 단건 조회가 준다.
`school_year` 를 쿼리로 받지 않는다. `class_id` 가 결정한다.

**이 API 가 없으면 번호를 잃은 계획안을 영영 못 찾는다.** 새로고침 한 번이면 끝이고,
교사는 다시 만들기를 누른다. 홈의 "내 반 계획안"과 반 카드의 상태 배지도 이 API 를 쓴다.

| | |
|---|---|
| loading | 표 스켈레톤 |
| **empty** | `items: []` — "아직 계획안이 없어요" + 생성 버튼 |
| error | `NOT_FOUND` 404 |

---

## 6. 칸 수정 — `PUT /api/plans/annual/{id}/months/{month}`

**Request** — **`theme` · `sub_themes` 둘 다 필수다.**

```json
{ "theme": "고친 주제", "sub_themes": ["...", "..."] }
```

**`PATCH` 가 아니라 `PUT` 인 이유** — 전체 교체다. `PATCH` 로 두면 "일부만 보내도 되겠지"로
구현할 여지가 남고, `theme` 만 보냈을 때 `sub_themes` 가 **조용히 사라진다.** 교사는 저장됐다고
믿고 §7 확정에서야 발견한다. 필드 누락은 `VALIDATION_FAILED` 422 이고 부분 저장이 되지 않는다.

**Response** — 그 달 객체 하나. **전체를 다시 안 준다.**

**수정된 칸은 `generation.method` 만 `TEACHER_EDIT` 으로 바뀐다.**
**`evidence` 는 그대로 유지한다** — 교사가 문구를 고쳐도 그 칸의 근거(누리과정·주제·상위 계획안)는
바뀌지 않는다. 이전 `generation` 은 Audit 에 `TEACHER_EDITED` 이벤트로 남는다.

**확정된 계획안은 수정할 수 없다.**

```json
409  { "error": { "code": "ALREADY_CONFIRMED",
                  "message": "확정된 계획안은 수정할 수 없습니다.", "fields": [] } }
```

**UI states**

| | |
|---|---|
| loading | 그 칸만 흐리게. **화면 전체를 막지 않는다** |
| success | 그 칸만 갱신 |
| error | **그 칸만 롤백.** 나머지 수정분 유지 |

---

## 7. 확정 — `POST /api/plans/annual/{id}/confirm`

**Request** — 없음

**Response** `200` → `{ "id": 10, "status": "CONFIRMED", "confirmed_at": "..." }`

**되돌리기는 P1.** 확정 후 수정 요청은 `ALREADY_CONFIRMED` 409 다(§6).

**재호출은 멱등이다.** 이미 `CONFIRMED` 인 계획안에 다시 오면 **`200` 에 현재 상태를 돌려준다.**
409 로 막지 않는다 — 네트워크 재시도나 더블클릭으로 두 번 도착하는 것이 정상 경로인데,
여기에 409 를 주면 FE 가 진짜 실패와 구분하지 못한다. **`confirmed_at` 은 최초 확정 시각을 유지한다.**

| | |
|---|---|
| loading | 버튼 비활성 + 스피너 |
| success | 상태 배지 `확정됨` |
| error | `VALIDATION_FAILED` 422 — 빈 칸이 남았을 때. **빈 달을 전부 내려준다**<br>`fields: ["months.3", "months.7", "months.9"]` |

---

## 8. 양식 — `POST /api/forms/parse` (구현됨) · 등록은 7주차

**`POST /api/forms/parse`** — hwp/hwpx 를 받아 표 구조와 라벨 후보를 돌려준다. 수린 구현(PR #6).
**저장하지 않는다.** 요청·응답만으로 끝나는 순수 변환이다.

**양식 등록은 7주차다.** 원이 양식을 한 번 등록하면 계속 쓰는 구조이므로 **원에 귀속된다.**

```
POST   /api/centers/{center_id}/forms     양식 등록 → form_id 발급
GET    /api/centers/{center_id}/forms     등록된 양식
DELETE /api/forms/{id}                    삭제.  수정은 삭제 후 재등록이다
```

`form_id` 는 §4 의 request 가 받는다. **임시 업로드가 아니라 원의 자산이므로 만료 정책이 없다.**

---

## 9. 7주차 예정 — 계약 안 씀

```
POST   /api/plans/monthly                 월간 43칸
PUT    /api/plans/monthly/{id}/cells/{n}  칸 편집
POST   /api/plans/monthly/{id}/cells/{n}/regenerate   이 칸만 다시
GET    /api/plans/{id}/export/hwp         내보내기
GET    /api/plans/annual/{id}/audit       Audit 이벤트 조회 — 되돌리기(P1)·평가제(P2)
PUT    /api/centers/{center_id}/plan-config   uses_monthly · weekly_location
POST   /api/centers/{center_id}/forms     양식 등록 (§8)
```

**월간은 연간이 `CONFIRMED` 여야 생성된다.** 아니면 `GATE_BLOCKED` 409.
**층 순서를 건너뛸 수 없다.** 연간·월간·주간을 한 번에 생성하지 않는다.

**「일간」 계획안은 만들지 않는다.** 스펙에도 ADR 에도 없는 문서 종류다.

`plan-config` 의 두 값은 7주차 기능의 입력이다 — `uses_monthly` 는 월간 생성이,
`weekly_location` 은 보육일지·관찰일지(P1, ADR-003)가 붙을 때 의미가 생긴다.
**P0 에서는 받지 않는다.** `safety_edu_hours` 는 서버 상수로 옮겼다(§4).

**hwp 내보내기에 출처 마커가 섞이면 안 된다.** 제출 문서다 — 7주차 계약을 쓸 때 다시 확인한다.

**관찰일지·문서 보관함·평가제 화면은 P1 이후다.** 6주차 화면은 선행 구현이며 계약 대상이 아니다.

**LLM 으로 나가는 자유 입력 필드(계획안 생성 메모 등)도 `shared/childCode` 치환 대상이다.**
치환 실패 시 호출하지 않고 에러를 낸다.

---

## 채워야 할 곳 — BE

```
□  각 Response 의 실제 필드명·타입·nullable        성진
□  생성 소요 시간 실측 → loading UI 판단 근거        하민
   → RAG 도입으로 더 중요해졌다. 진행 표시 없이 수 초가 지나면 교사가 다시 누른다
□  Audit 을 어느 테이블에 둘 것인가                  성진 · 하민
   → 멘토 리뷰(PR #17) — "각각의 쓰기 생명주기가 다르니 하나의 테이블에 넣지 말 것"
   → Evidence · Generation · Audit 을 분리한다

□  evidence.source_id 의 작명 규칙                 담당 미정
   → theme-ref-2026 처럼 자료마다 불변 슬러그
□  generation.rule_id · rule_version 의 발급 주체   담당 미정
   → RULE_ONLY · RULE_LLM 이면 둘 다 필수다
□  가명 Pool 의 실제 목록                           담당 미정
   → backend/resources/.  받침 있는 한글 이름
□  LLM 호출 위치와 예산 카운터                       팀 논의
   → shared/llm 을 거치지 않으면 70% 경고·90% 차단이 동작하지 않는다
```

**위 세 명은 원래 담당이다** — 「각 Response 필드명」·「생성 소요 시간」은 이전 판에 적혀 있었고,
「Audit 테이블」은 PR #17 답변(*"해당 기능 담당했던 하민, 성진에게 전달하여…"*)에 근거한다.
**아래 「담당 미정」은 이번에 새로 생긴 항목이라 PM 이 배정한다.**

**이 계약이 요구하는데 DB 에 아직 없는 것** — 마이그레이션 PR 이 따로 필요하다.
체크리스트에 안 적으면 담당자가 필드 갭을 통째로 놓친다.

```
classes.consent_confirmed_at   TIMESTAMPTZ nullable      §2  consent_confirmed
children.code                  VARCHAR                   §2-1
UNIQUE(class_id, code)         children 제약              §2-1
plans · plan_items             연간계획안 본체             §4 · §5 · §6 · §7
greetings                      enabled + 12개월 items      §3  (7주차)
forms                          원 귀속 양식                §8  (7주차)
```

`classes.school_year` 는 **컬럼이 이미 있다.** 서버가 채우는 로직만 만들면 된다.
