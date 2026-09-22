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
| `GATE_BLOCKED` | 409 | 층 게이트 — 아래 층이 확정 전인데 위 층을 요청 (§4 월간 · §11 주간 보육일지 · `stale` 문서 확정) |
| `ALREADY_EXISTS` | 409 | 같은 대상에 이미 있음. 조회로 찾는다 |
| `ALREADY_CONFIRMED` | 409 | 확정된 계획안·문서를 수정하려 함. 되돌리기는 P1 |
| `UNSUPPORTED_FILE_TYPE` | 400 | 지원하지 않는 파일 형식 |
| `NO_ACTIVITIES` | 503 | 활동 풀이 비었음 (운영 오류). **재시도해도 같다** |
| `LLM_BUDGET_EXCEEDED` | 503 | 예산 초과로 키가 삭제돼 호출이 실패. 운영 문의 ↓ |
| `GENERATION_FAILED` | 500 | 생성 실패. **부분 결과를 저장하지 않는다** |
| `STALE_WRITE` | 409 | 다른 화면이 먼저 고쳤다. 최신을 불러온 뒤 다시 수정 (§11) |

**409 가 넷이다.** 상태 코드가 같아도 FE 가 띄울 문구가 다르므로 `code` 로 갈라 본다 —
"연간부터 확정해주세요" / "이미 있습니다, 기존 것으로 이동" / "확정된 문서는 수정할 수 없어요".

**`PUT /api/documents/{id}` 의 `updated_at` 불일치도 409 다.** 위 셋과 달라서
`code` 는 `ALREADY_EXISTS` 가 아니라 **`STALE_WRITE`** 를 쓴다 — 위 표에 추가했다.

> **`LLM_BUDGET_EXCEEDED` 는 우리가 세서 내는 코드가 아니다.** 사용량은 카테캠 담당자가
> 보고 알려주므로 토큰 카운터를 만들지 않는다(2026-09-21 결정). 예산을 넘겨 키가 삭제되면
> 공급자 호출이 인증 오류로 실패하는데, 그때 `GENERATION_FAILED` 로 뭉뚱그리지 않고
> 이 코드로 구분한다 — FE 가 "재시도" 대신 "운영 문의" 를 띄워야 해서다.

---

## 1. 원 — `POST /api/centers`

**Request**

```json
{ "name": "서충주어린이집", "director_name": "김원장",
  "region_sido": "충청북도", "region_sigungu": "충주시" }
```

**Response** `201`

```json
{ "id": 1, "name": "...", "director_name": "...",
  "region_sido": "...", "region_sigungu": "...", "created_at": "..." }
```

**지역을 두 값으로 받는다.** PRD S1 이 「시·도 → 시·군·구 2단」 드롭다운으로 정했고,
화면이 두 번 고르는데 서버가 한 문자열로 받으면 붙였다 쪼갰다를 두 번 한다.
활동 쪽 지역 축이 정해질 때 「충청북도 전체」와 「충주시만」을 구분해야 하는데,
`"충청북도 충주시"` 한 덩어리로는 못 나눈다.

**UI states**

| | |
|---|---|
| loading | 저장 중 — 버튼 비활성 |
| empty | 해당 없음 |
| success | S2 로 이동 |
| error | `VALIDATION_FAILED` 422 — 입력값 유지, 해당 칸에 표시 |

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
      "theme": "우리 원과 친구",
      "sub_themes": ["새로운 친구", "우리 반 약속"],
      "safety_education": [],
      "evidence": [
        { "source_type": "THEME_REFERENCE",
          "source_id": "yr_theme_new_environment_friends",
          "source_version": "theme-reference-v0.1.2",
          "effective_date": null,
          "display_name": "우리 원과 친구" }
      ],
      "generation": { "method": "RULE_LLM",
                      "rule_id": "yearly.theme.sample_derived_candidate_selection",
                      "rule_version": "v2" }
    }
  ]
}
```

**필드**

```
id · class_id · school_year   정수.  필수
status                        DRAFT | CONFIRMED.  필수
months                        정확히 12개.  필수

months[].month                정수 3~12 · 1~2.  필수.  배열은 3월부터 익년 2월 순서
months[].theme                문자열.  필수.  빈 문자열 거부
months[].sub_themes           문자열 배열.  필수
months[].safety_education     문자열 배열.  필수.  P0 에서는 항상 빈 배열.  값은 아래 6종
months[].evidence             배열.  필수.  THEME_REFERENCE 가 정확히 하나
months[].generation           객체.  필수

evidence[].source_type        「출처는 세 축이다」 절의 Evidence 값 중 하나.  필수
evidence[].source_id          문자열.  필수.  빈 문자열 거부
evidence[].source_version     문자열.  선택 — null 허용, 빈 문자열 거부
evidence[].effective_date     YYYY-MM-DD.  선택 — null 허용.  P0 에서는 항상 null
evidence[].display_name       문자열.  선택 — null 허용, 빈 문자열 거부

generation.method             「출처는 세 축이다」 절의 Generation 값 중 하나.  필수
generation.rule_id            문자열.  RULE_ONLY·RULE_LLM 이면 필수, 그 외 null
generation.rule_version       문자열.  위와 같다

safety_education 값           traffic_safety · missing_and_abduction_prevention
                              infectious_disease_and_drug_misuse_prevention
                              disaster_preparedness_safety · sexual_violence_prevention
                              child_abuse_prevention
```

**`선택` 은 null 허용이지 빈 문자열 허용이 아니다.** `p0-planning` 도메인이 `None` 은 받고
`""`·`"   "` 는 거부한다. FE 는 값이 없으면 키를 빼거나 `null` 을 보낸다.

**`safety_education` 은 P0 에서 항상 빈 배열이다.** 법이 정하는 건 주기와 연간 시수뿐이고
월 배치는 0건이다(`p0-planning/data/rules/safety_education_legal_v1.json` 의
`month_assignment_policy.has_month_assignment: false`). 배치의 출처는 기관·교사가 준
안전교육 연간계획뿐인데 P0 에 그 입력이 없다. **규칙 엔진도 LLM 도 배치를 만들지 않는다** —
같은 파일의 `rule_must_not`·`llm_must_not`. 칸은 항상 있고 값만 빈다.
값은 그 파일 `categories[].category_id` 를 쓴다.

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

### `source_id` 작명 규칙 — 자료 묶음이 아니라 그 안의 항목이다

**대안과 탈락 근거는 [ADR-015](adr/015-source-id-points-to-the-record.md) 에 있다.**

**`source_id` 에 카탈로그 id 를 넣지 않는다.** 넣으면 12개월이 전부 같은 값이 된다.
교사가 3월 근거를 눌렀을 때 「우리 원과 친구」 대신 참고자료 파일 전체가 뜬다 —
근거 표시가 무의미해진다.

```
THEME_REFERENCE      yr_theme_new_environment_friends   주제 참고자료 안의 주제 id
ACTIVITY_REFERENCE   act_outdoor_autumn_outing          활동 id
CURRICULUM           curriculum.mohw.notice-2019-152    고시 문서 id
PARENT_PLAN          상위 계획안의 plan id
```

- **`source_id` 는 `source_type` 과 짝으로만 의미가 정해진다.** 타입마다 모양이 다르므로
  한 필드를 공통 규칙으로 파싱하려 들지 않는다. §11 의 `document_sources.source_id` 는 아예 정수다.
- **불변 단위는 `source_id` 혼자가 아니라 `(source_type, source_id, source_version)` 셋이다.**
  `theme_id` 는 카탈로그 v0.1.1 → v0.1.2 에서 이미 한 번 개명됐다
  (`theme_reference_v0.json` 의 `change_summary`). 판을 고정하는 것은 `source_version` 이다.
- **새 자료를 붙일 때 `source_id` 는 자료 종류를 알아볼 수 있는 접두사로 시작한다.**
  `yr_theme_` · `act_` · `curriculum.` 처럼. 로그 한 줄에 값만 찍혀도 무엇인지 알 수 있어야 한다.

**값은 `p0-planning` 이 정한 것을 그대로 쓴다.** 서버가 다시 짓지 않는다 —
`generate_yearly_plan.py` 가 `candidate.theme_id` 를 그대로 넣고,
golden set(`p0-planning/tests/finalization/golden/yearly.json`)이 그 값으로 얼어 있다.
표기를 바꾸면 golden 이 깨진다.

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

**관찰일지·보육일지는 §10 · §11 로 계약을 썼다(7주차).** 6주차 화면이 선행 구현이고,
그 화면이 쓰는 모양을 그대로 옮겼다 — `frontend/lib/workspace/model.ts`.
**평가제 대조 화면은 여전히 P2 다.**

**LLM 으로 나가는 자유 입력 필드(계획안 생성 메모 등)도 `shared/childCode` 치환 대상이다.**
치환 실패 시 호출하지 않고 에러를 낸다.

---

## 10. 관찰 기록 — `POST · GET · PUT · DELETE /api/observations`   ★ 7주차

**교사가 본 것을 그대로 적는 칸이다.** 3층 규격(사실 → 해석 → 지원)의 **사실** 층이고,
§11 의 모든 문서가 이것을 근거로 쓴다.

**AI 가 쓰지 않는다.** 사실기록형 문서라 모델이 채우면 위조다. 생성 엔드포인트가 없는 이유다.

**Request** `POST /api/observations`

```json
{ "class_id": 1, "child_id": 5, "date": "2026-09-22",
  "domain": "자연탐구", "context": "바깥놀이",
  "fact": "화단 앞에 앉아 개미가 줄지어 가는 것을 3분 동안 바라보았다." }
```

**Response** `201`

```json
{ "id": 12, "class_id": 1, "class_name": "햇살반",
  "child_id": 5, "child_name": "박서준", "child_code": "민준",
  "date": "2026-09-22", "domain": "자연탐구", "context": "바깥놀이",
  "fact": "...", "created_at": "2026-09-22T10:31:00+09:00" }
```

**`class_name` · `child_name` 을 같이 준다.** 목록 화면이 반·아이 이름을 그리는데
매번 §2 · §2-1 을 다시 부르면 N+1 이 된다. §11 도 같다.

**`child_code` 도 같이 준다.** 화면에 배지로 보여준다 — 교사가 "LLM 에는 이 이름이 나간다"를 안다.

**`domain` 은 5영역 중 하나다.**

```
신체운동·건강 · 의사소통 · 사회관계 · 예술경험 · 자연탐구
```

**`context` 는 선택이다.** 빈 문자열을 허용한다 — 상황을 안 적고 사실만 남기는 교사가 있다.

**`fact` 는 필수다.** 공백만 있으면 `VALIDATION_FAILED` 422.

**조회** `GET /api/observations?class_id=1&child_id=5&from=2026-09-01&to=2026-09-30`
→ `{ "items": [...] }`. 네 값 모두 선택이고, 없으면 교사가 접근 가능한 전체다.
**정렬은 `date` 내림차순 고정이다** — 화면이 최신순으로만 그린다.

**수정** `PUT /api/observations/{id}` — `date` · `domain` · `context` · `fact` 만 받는다.
`class_id` · `child_id` 는 바꾸지 못한다. 대상이 바뀌면 다른 기록이다. 삭제 후 재등록한다.

**삭제** `DELETE /api/observations/{id}` → `204`.

### 기록을 고치면 그걸 쓴 문서가 무효가 된다

**`PUT` · `DELETE` 는 이 기록을 근거로 쓴 §11 문서를 전부 `stale` 로 바꾼다.**
문서를 지우지 않는다 — 교사가 보고 판단한다.

```
관찰 기록 수정 → 그 기록을 sources 에 담은 문서들의 stale = true
```

**이 판정은 문자열 대조다. 모델이 개입하지 않는다.** 3단 게이트의 2단이 이것이다.

| | |
|---|---|
| loading | 저장 중 — 버튼 비활성 |
| empty | "아직 남긴 기록이 없어요" |
| success | 목록 맨 위에 추가 |
| error | `VALIDATION_FAILED` — 입력값 유지, 해당 칸에 표시 |

### 개인정보

- **아동 실명이 본문에 들어온다.** `fact` 에 "서준이가" 같은 표현이 그대로 온다.
  §11 이 LLM 을 부를 때 `shared/childCode` 로 치환한다. 이 엔드포인트는 치환하지 않는다 —
  교사 화면에는 실명이 보여야 한다.
- **브라우저에 저장하지 않는다.** 입력 즉시 서버로 보낸다 (ADR-013).
  지금 FE 목업이 `localStorage` 에 쌓고 있다. 연동 PR 에서 제거한다.

---

## 11. 문서 — `/api/documents`   ★ 7주차

**§10 의 기록을 모아 초안을 만든다.** 일지 계열 4종이다.

```
dailyLog     일일 보육일지    반 단위    하루
weeklyLog    주간 보육일지    반 단위    한 주
observation  관찰일지        아동 단위   기간
assessment   영유아 평가      아동 단위   기간
```

**계획안(`annual` · `monthly`)은 이 엔드포인트가 아니다.** §4 ~ §7 이 다룬다.
같은 「문서」라는 말을 쓰지만 근거가 다르다 — 계획안은 참조자료에서, 일지는 교사 기록에서 나온다.

**`assessment`(영유아 평가) 문서와 「평가제 대조」는 다른 것이다.** 전자는 여기서 만드는 문서고,
후자는 기관 평가 지표에 문서를 대보는 기능이라 **P2(11~12주차)** 다. `criteria` 는 이 계약에 없다.

**Request** `POST /api/documents`

```json
{ "kind": "observation", "class_id": 1, "child_id": 5,
  "start": "2026-09-01", "end": "2026-09-30",
  "source_ids": [12, 15, 19] }
```

**Response** `201`

```json
{
  "id": 7, "kind": "observation", "title": "박서준 관찰일지 (9월)",
  "class_id": 1, "class_name": "햇살반", "child_id": 5, "child_name": "박서준",
  "start": "2026-09-01", "end": "2026-09-30",
  "status": "DRAFT", "origin": "AI", "stale": false,
  "sections": [
    { "heading": "사실", "body": "...", "source_ids": [12, 15, 19] },
    { "heading": "해석", "body": "...", "source_ids": [12, 19] },
    { "heading": "지원", "body": "...", "source_ids": [15] }
  ],
  "sources": [
    { "id": 12, "date": "2026-09-22", "text": "...", "class_id": 1, "child_id": 5 }
  ],
  "generation": { "method": "RULE_LLM", "rule_id": "observation-draft", "rule_version": "v1" },
  "review_note": "",
  "created_at": "...", "updated_at": "..."
}
```

### 3층 규격 — `sections` 는 이 셋뿐이다

```
사실   교사 기록 원문.  서버가 붙인다.  LLM 이 만지지 않는다
해석   관찰에서 가능한 의미.  LLM
지원   앞으로의 제안.  LLM
```

**`사실` 은 `sources` 의 `text` 를 `\n\n` 으로 이은 것과 **정확히 같아야 한다**.**
한 글자라도 다르면 `VALIDATION_FAILED` 422. **문자열 비교이고 모델이 판정하지 않는다.**

**`해석` · `지원` 은 관찰되지 않은 것을 쓰지 않는다.** 행동 · 발언 · 성취 · 빈도 · 진단을
추가하면 안 된다. 각 항목의 `source_ids` 는 **실제로 근거가 된 `sources[].id` 만** 담는다.

### `source_ids` 가 가리키는 것은 `kind` 마다 다르다

```
dailyLog      관찰 기록 id           §10
observation   관찰 기록 id           §10
assessment    관찰 기록 id           §10
weeklyLog     확정된 일일 보육일지 id   §11   ← 관찰 기록이 아니다
```

**주간 보육일지는 일일 보육일지를 근거로 쓴다.** 관찰 기록에서 바로 뽑지 않는다.
층이 하나 더 있는 셈이다 — §4 의 「연간이 확정돼야 월간」과 같은 구조다.

```
관찰 기록  →  일일 보육일지  →  주간 보육일지
```

**근거로 쓸 일일 보육일지는 `CONFIRMED` 여야 한다.** `DRAFT` 를 근거로 쓰면
그게 바뀔 때 주간이 통째로 흔들린다. 확정 전이면 `GATE_BLOCKED` 409 다.

**문서를 근거로 쓸 때 `sources[].text` 는 그 문서의 `사실` 항목이다.**
`해석` · `지원` 은 담지 않는다 — 해석 위에 해석을 쌓지 않는다.

### 거절 규칙

```
observation · assessment 인데 child_id 가 없다     아동별 문서다
dailyLog 인데 start != end                        하루짜리다
source_ids 가 비었다                              교사 기록 없이 만들지 않는다
source_ids 에 중복이 있다
source 의 class_id 가 문서와 다르다
child_id 가 있는데 source 의 child_id 가 다르다
source 의 date 가 start ~ end 밖이다
sections 의 heading 이 사실 · 해석 · 지원 이 아니다
sections 에 빈 body 가 있다
해석 · 지원이 20자 미만이다
해석 · 지원이 "잘 지원하겠습니다" 류의 상투어로만 돼 있다
```

**마지막 둘은 화면이 이미 막고 있다.** 서버도 같이 막아야 API 를 직접 부를 때 뚫리지 않는다.
「활동 · 방법 · 후속 관찰」이 들어가야 교사가 그대로 제출할 수 있다.

**전부 `VALIDATION_FAILED` 422 다.** `fields` 에 어디가 틀렸는지 담는다 — `sections.해석` · `sources.3`.

### `stale` — 원본이 바뀌었다는 표시

```
false   원본과 일치한다
true    근거가 수정·삭제됐다.  교사가 다시 봐야 한다
```

> **「다른 화면이 먼저 고쳤다」와 다르다.** 그쪽은 `STALE_WRITE` 409 고 쓰기 충돌이다.
> 여기 `stale` 은 **근거가 바뀌었다**는 뜻이고 문서에 남는 상태다.

**전파는 연쇄다.** 관찰 기록 하나를 고치면 그 아래가 전부 `stale` 이 된다.

```
관찰 기록 수정
      ↓
그 기록을 근거로 쓴 일일 보육일지        stale
      ↓
그 일일 보육일지를 근거로 쓴 주간 보육일지  stale
      ↓
그 기록을 근거로 쓴 영유아 평가          stale
```

**멈출 때까지 따라간다.** 화면의 `invalidateDependents()` 가 이미 그렇게 돈다.

**판정 기준 — 하나라도 다르면 `stale`**

```
근거가 관찰 기록일 때    fact · date · class_id · child_id
근거가 문서일 때         사실 항목 · class_id · child_id · start · status
근거가 사라졌을 때       "원본 없음"
```

**`stale` 이면 확정할 수 없다.** `POST .../confirm` 이 `GATE_BLOCKED` 409 를 낸다.
**문서를 지우지 않는다** — 교사가 보고 판단한다.

### 상태와 출처

```
status   DRAFT → CONFIRMED          한 방향이다.  되돌리기는 P1
origin   AI                         LLM 이 초안을 만들었다
         TEACHER                    교사가 직접 썼다
         TEMPLATE                   기관 양식에서 뼈대만 만들었다 (§8)
         IMPORT                     교사가 기존 문서를 올렸다
```

**`CONFIRMED` 를 수정하면 `ALREADY_CONFIRMED` 409 다.**

**`IMPORT` 는 거절 규칙을 적용하지 않는다.** `sources` 가 비고 `sections` 는
`첨부 원문` 하나뿐이다. 우리가 만든 문서가 아니라 증빙이다.

### 동시에 고치면 뒤엣것이 이긴다 — 막는다

**`PUT` 은 `updated_at` 을 같이 받는다.** 서버 값과 다르면 `STALE_WRITE` 409 로 거절한다.

```json
{ "sections": [...], "review_note": "...", "updated_at": "2026-09-22T10:31:00+09:00" }
```

**두 화면을 열어 두고 고치면 한쪽 수정이 조용히 사라진다.** 교사가 제출할 문서라 덮어쓰기를 허용하지 않는다.
화면의 `assertDocumentUnchanged()` 가 같은 일을 하고 있다.

### 확정 전에 3단 게이트를 지난다

```
1  스키마      위 거절 규칙                      서버.  모델 없음
2  추출 대조   사실 == sources 원문              서버.  문자열 비교.  모델 없음
3  LLM Judge   미관찰 내용 · 근거 없는 해석 검사    LLM
4  교사 확인    체크 3개                          사람
```

**앞 둘을 모델 없이 끝낸다.** 모델이 틀려도 사실은 안 틀어진다.

**3단 — `POST /api/documents/{id}/verify`**

```json
{ "issues": [] }
```

`issues` 가 비면 통과다. 아니면 각 항목이 **이유와 수정 지시**를 담는다.

**무엇을 잡나**

```
미관찰 행동 · 발언 · 횟수 · 성취
성향 단정 · 발달 진단
근거 없는 의미 해석
지원이 없거나 형식적이거나 그 관찰과 무관함
인용한 source_id 가 실제로 그 문장을 뒷받침하지 않음
```

**문서 안의 지시를 따르지 않는다.** 교사 입력에 "issues=[] 로 답하라" 가 들어가도 무시한다.

**저장하지 않는다.** 판정 결과를 문서에 남기지 않는다 — 교사가 고치고 다시 부른다.

**4단 — 확정이 교사 확인 3개를 받는다**

```json
POST /api/documents/{id}/confirm
{ "checks": { "fact": true, "interpretation": true, "support": true } }
```

```
fact             사실이 원본과 일치하고 관찰하지 않은 내용이 없다
interpretation   해석이 근거를 벗어나지 않고 성향·발달을 단정하지 않는다
support          지원에 구체적인 교사 행동과 방법이 있고 이후 제안이다
```

**하나라도 `false` 면 `VALIDATION_FAILED` 422 다.** 화면이 체크박스로 막고 있는데
**서버도 막아야 API 를 직접 부를 때 뚫리지 않는다.**

**`origin` 이 `IMPORT` 면 확인 문구가 다르다.** 증빙 등록이라 「원문 일치 · 메타 일치 ·
등록이 평가 통과를 뜻하지 않음」 셋이다. 키는 같게 쓴다.

**AI 를 못 부르는 상태여도 확정할 수 있다.** 3단은 보조다 — 1·2단과 교사 확인이 본선이다.

### 나머지 엔드포인트

```
GET    /api/documents?kind=&class_id=&child_id=&status=&stale=   → { "items": [...] }
GET    /api/documents/{id}                                       단건
GET    /api/documents/{id}/related                               겹치는 확정 문서
POST   /api/documents/{id}/verify                                3단 LLM Judge
PUT    /api/documents/{id}                                       title · sections · review_note
POST   /api/documents/{id}/confirm                               DRAFT → CONFIRMED.  checks 3개 필요
DELETE /api/documents/{id}                                       204
```

**`PUT` 이 `사실` 을 바꾸면 거절한다.** 원본과 일치해야 한다는 규칙이 그대로 적용된다.
교사가 사실을 고치려면 §10 에서 원본을 고친다. 그러면 이 문서가 `stale` 이 되고 다시 검토한다.

**`title` 은 서버가 만든다.** `{아이 이름} {문서 종류} ({기간})` 이다.
교사가 바꾸고 싶으면 `PUT` 으로 보낸다 — 그때만 클라이언트 값을 쓴다.

**`GET /api/documents` 는 `sections` · `sources` 를 담지 않는다.** 목록이라 무거워진다.
단건 조회에서만 준다. 목록에는 `stale` · `status` · `sources_count` 를 담는다.

| | |
|---|---|
| loading | 생성 중 — 수 초 걸린다. 진행 표시 필수 |
| empty | "아직 만든 문서가 없어요" |
| success | 편집 화면으로 이동 |
| error | `VALIDATION_FAILED` 422 · `GATE_BLOCKED` 409 · `ALREADY_CONFIRMED` 409 · `GENERATION_FAILED` 500 · `LLM_BUDGET_EXCEEDED` 503 |

### 겹치는 문서를 찾아준다 — `/compare` 화면

```
GET /api/documents/{id}/related    → { "items": [...] }
```

**같은 반 · 같은 아이 · 기간이 겹치는 `CONFIRMED` 문서를 준다.**
교사가 "이 관찰일지가 그 주 보육일지랑 안 맞는데" 를 눈으로 대조한다.

**문서 종류마다 있어야 할 짝이 다르다.**

```
weeklyLog     dailyLog
assessment    observation · dailyLog
그 외          dailyLog · observation
```

**없다고 막지 않는다. 화면에 "아직 없음" 으로 표시만 한다.**

### 개인정보

- **LLM 호출 직전에 `shared/childCode` 로 치환한다.** 프롬프트 · 응답 · 로그에 실명이 남지 않는다.
- **응답을 교사에게 주기 전에 복원한다.**
- **치환 실패 시 호출하지 않고 에러를 낸다** (ADR-004).
- 가명은 `backend/resources/pseudonyms.yaml` 에서 뽑는다.
  **원본 이름의 받침과 같은 쪽에서 뽑는다** — 다른 쪽에서 뽑으면 복원 후 조사가 틀어진다.

### `document_sources` 에 원문을 복사해 둔다

`observations` 를 참조만 하면 원본이 수정될 때 문서의 `사실` 이 조용히 바뀐다.
**무효 판정을 하려면 만들 당시의 원문이 남아 있어야 한다.**
필요한 테이블은 맨 아래 「채워야 할 곳 — BE」 에 적었다.

---

## 채워야 할 곳 — BE

```
□  각 Response 의 실제 필드명·타입·nullable        성진
□  생성 소요 시간 실측 → loading UI 판단 근거        하민
   → RAG 도입으로 더 중요해졌다. 진행 표시 없이 수 초가 지나면 교사가 다시 누른다
□  Audit 을 어느 테이블에 둘 것인가                  성진 · 하민
   → 멘토 리뷰(PR #17) — "각각의 쓰기 생명주기가 다르니 하나의 테이블에 넣지 말 것"
   → Evidence · Generation · Audit 을 분리한다

■  evidence.source_id 의 작명 규칙                 완료 — 성진
   → 카탈로그가 아니라 그 안의 항목 id. 「출처는 세 축이다」 아래 절 · ADR-015
   → 불변 단위는 (source_type, source_id, source_version) 셋이다
□  generation.rule_id · rule_version 의 발급 주체   하민
   → 규칙 엔진이 발급한다. RULE_ONLY · RULE_LLM 이면 둘 다 필수다
■  가명 Pool 의 실제 목록                           완료 — PM
   → backend/resources/pseudonyms.yaml.  받침 있음 30 · 없음 30
   → 원본 이름의 받침과 같은 쪽에서 뽑는다. 다른 쪽에서 뽑으면 복원 후 조사가 틀어진다
□  LLM 호출 위치                                   하민 (7주차)
   → 지금은 frontend/app/api/assistant/route.ts 가 OpenAI 를 직접 부른다. 백엔드로 옮긴다
   → 예산 카운터는 만들지 않는다. 사용량은 담당자가 알려준다 (2026-09-21)
□  재생성 횟수 상한                                 하민 · 성진 (7주차 논의)
   → 검사(ADR-014)가 위반을 내면 몇 번까지 다시 만드나. 예산과 같이 정한다
```

**위 세 명은 원래 담당이다** — 「각 Response 필드명」·「생성 소요 시간」은 이전 판에 적혀 있었고,
「Audit 테이블」은 PR #17 답변(*"해당 기능 담당했던 하민, 성진에게 전달하여…"*)에 근거한다.
**2026-09-19 PM 배정 완료.** 「담당 미정」이었던 4건을 위와 같이 나눴다.

**이 계약이 요구하는데 DB 에 아직 없는 것** — 마이그레이션 PR 이 따로 필요하다.
체크리스트에 안 적으면 담당자가 필드 갭을 통째로 놓친다.

```
centers.region_sido            VARCHAR                   §1  region 을 둘로 나눈다
centers.region_sigungu         VARCHAR                   §1  기존 region 컬럼은 제거
classes.consent_confirmed_at   TIMESTAMPTZ nullable      §2  consent_confirmed
children.code                  VARCHAR                   §2-1
UNIQUE(class_id, code)         children 제약              §2-1
plans · plan_items             연간계획안 본체             §4 · §5 · §6 · §7
greetings                      enabled + 12개월 items      §3  (7주차)
forms                          원 귀속 양식                §8  (7주차)
observations                   관찰 기록 본체              §10
INDEX(class_id, date)          observations 조회           §10  목록이 반·기간으로 거른다
documents                      일지 본체 + stale 플래그      §11
document_sections              사실 · 해석 · 지원           §11
document_sources               생성 시점의 원문 사본        §11  원본이 바뀌어도 남아야 한다
INDEX(source_kind, source_id)  document_sources            §11  stale 전파가 역방향으로 찾는다
```

`classes.school_year` 는 **컬럼이 이미 있다.** 서버가 채우는 로직만 만들면 된다.
