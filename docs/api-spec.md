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
인증        Authorization: Bearer <token>.  §0 참조
날짜        ISO 8601 (2026-03-01)
연령        학년도 기준 연 나이 3·4·5.  만 나이 아님
```

**개발·데모는 가명으로 한다** (ADR-004). 인증이 붙었어도 개발 DB 에 실제 아동 실명을
넣지 않는다 — 로그가 남는 경로가 많다.

### 0. 인증 — `POST /api/auth/signup` · `POST /api/auth/login`

```json
signup   { "email": "a@b.kr", "name": "김선생", "password": "여덟자이상" }   → 201
login    { "email": "a@b.kr", "password": "여덟자이상" }                     → 200

응답     { "token": "...", "user": { "id": 1, "email": "...", "name": "...", "center_id": null } }

me       GET /api/auth/me                                               → 200  위 user 모양
```

**토큰을 `Authorization: Bearer <token>` 으로 실어 보낸다.** 12시간 뒤 만료된다.

**`/api/auth/*` 와 `/api/forms/parse` 를 뺀 모든 엔드포인트가 토큰을 요구한다.**
없거나 못 믿으면 `401 UNAUTHENTICATED` 다. **왜 401 인지는 알려주지 않는다** —
「만료됐다」와 「서명이 틀렸다」를 구분해 주면 토큰을 맞춰 보는 쪽에 힌트가 된다.

**`center_id` 가 null 이면 온보딩을 아직 안 끝냈다.** `POST /api/centers` 가 그 값을 채운다.
**한 계정은 원 하나다** — 두 번째 요청은 `409 ALREADY_EXISTS` 다.

**자기 원 것만 볼 수 있다.** 로그인만 확인하면 `class_id` 를 바꿔가며 남의 원 아동 명단을
읽을 수 있다. **남의 것은 403 이 아니라 404 다** — 403 은 그 id 가 존재한다는 사실을 알려준다.

> **「자기 반만」은 아직 아니다.** 원장도 봐야 하고 담임이 바뀌기도 해서 규칙을 먼저 정한다.
> 지금은 원 단위까지다.

### 401 을 받으면 화면이 하는 일

**토큰이 12시간짜리고 갱신이 없다.** 교사가 아침에 로그인해서 저녁에 쓰면 **쓰는 도중에
끊긴다.** 관찰 기록이나 일지는 한 번에 여러 줄을 쓰므로, 그 순간 입력칸이 비면 교사는
방금 쓴 글을 통째로 잃는다.

```
1  쓰던 내용을 그대로 둔다        입력칸을 비우지 않는다.  화면을 이동하지 않는다
2  다시 로그인할 길을 그 자리에 연다   지금 화면 위에 로그인 창을 띄운다
3  로그인되면 그 요청을 다시 보낸다     교사가 저장 버튼을 다시 누르지 않는다
```

**로그인 화면으로 통째로 넘기지 않는다.** 넘기면 쓰던 내용이 사라지고, 교사는 무엇을
잃었는지도 모른 채 다시 쓴다.

**토큰은 지운다.** 못 믿는 토큰을 들고 다음 요청을 또 보내면 401 이 반복된다.
`sessionStorage` 에서 지우고, 새 토큰을 받으면 다시 넣는다.

**한 번만 다시 보낸다.** 다시 보낸 요청이 또 401 이면 그때는 로그인 화면으로 보낸다 —
계속 다시 보내면 교사 화면이 멈춘 것처럼 보인다.

**읽기 요청은 다시 보내지 않아도 된다.** 목록을 다시 부르는 건 교사가 새로고침하면 된다.
**잃을 게 있는 것은 쓰기 요청(`POST`·`PUT`·`DELETE`)이다.**

> **왜 갱신 토큰을 안 두나** — 지금은 없다. 8주차에 붙인 인증이 서명 문자열 하나뿐이라
> 무효화할 방법도 없다(ADR-017). 갱신·무효화는 파일럿 전에 다시 본다.
> 그때까지는 위 세 줄이 교사가 글을 잃지 않게 막는 유일한 장치다.

**만료가 가까우면 미리 알리지 않는다.** 남은 시간을 화면이 알려면 토큰 안을 뜯어봐야 하는데,
그러면 서버가 「왜 401 인지 알려주지 않는다」고 정해둔 것이 화면에서 새 나간다.

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
| `UNAUTHENTICATED` | 401 | 토큰이 없거나 못 믿는다. 왜인지는 알려주지 않는다 |
| `VALIDATION_FAILED` | 422 | 입력값이 규격 밖 |
| `NOT_FOUND` | 404 | 대상 없음 |
| `GATE_BLOCKED` | 409 | 층 게이트 — 아래 층이 확정 전인데 위 층을 요청 (§4 월간 · §11 주간 보육일지 · `stale` 문서 확정) |
| `ALREADY_EXISTS` | 409 | 같은 대상에 이미 있음. 조회로 찾는다 |
| `ALREADY_CONFIRMED` | 409 | 확정된 계획안·문서를 수정하려 함. 문서는 `unconfirm` 으로 되돌린다(§11). 계획안 되돌리기는 P1 |
| `UNSUPPORTED_FILE_TYPE` | 400 | 지원하지 않는 파일 형식 |
| `NO_ACTIVITIES` | 503 | 활동 풀이 비었음 (운영 오류). **재시도해도 같다** |
| `LLM_BUDGET_EXCEEDED` | 503 | 예산 초과로 키가 삭제돼 호출이 실패. 운영 문의 ↓ |
| `DEPENDENCY_UNAVAILABLE` | 503 | 서버가 쓰는 변환기·외부 도구를 쓸 수 없음. **재시도해도 같다** ↓ |
| `GENERATION_FAILED` | 500 | 생성 실패. **부분 결과를 저장하지 않는다** |
| `STALE_WRITE` | 409 | 다른 화면이 먼저 고쳤다. 최신을 불러온 뒤 다시 수정 (§11) |
| `IN_USE` | 409 | 다른 데이터가 쓰고 있어 지울 수 없다. 지금은 §8 양식 삭제뿐 — 숨김 삭제가 들어오면 빠진다 |

**409 가 다섯이다.** 상태 코드가 같아도 FE 가 띄울 문구가 다르므로 `code` 로 갈라 본다 —
"연간부터 확정해주세요" / "이미 있습니다, 기존 것으로 이동" / "확정된 문서는 수정할 수 없어요".

**`PUT /api/documents/{id}` 의 `updated_at` 불일치도 409 다.** 위 셋과 달라서
`code` 는 `ALREADY_EXISTS` 가 아니라 **`STALE_WRITE`** 를 쓴다 — 위 표에 추가했다.

> **`LLM_BUDGET_EXCEEDED` 는 우리가 세서 내는 코드가 아니다.** 사용량은 카테캠 담당자가
> 보고 알려주므로 토큰 카운터를 만들지 않는다(2026-09-21 결정). 예산을 넘겨 키가 삭제되면
> 공급자 호출이 인증 오류로 실패하는데, 그때 `GENERATION_FAILED` 로 뭉뚱그리지 않고
> 이 코드로 구분한다 — FE 가 "재시도" 대신 "운영 문의" 를 띄워야 해서다.

> **`DEPENDENCY_UNAVAILABLE` 도 같은 이유로 `GENERATION_FAILED` 와 나눈다.** 서버에
> `hwp5html` 이 깔려 있지 않은 것은 교사가 고칠 수 없다. `GENERATION_FAILED` 500 은
> FE 가 재시도 버튼을 띄우는 코드인데, 여기서는 100번 눌러도 같은 결과다.
> **`NO_ACTIVITIES` 와 같은 가족이다** — 503 · 운영 오류 · 자동 재시도 없음.
> 앞으로 붙는 외부 도구(`pdftotext` · 외부 API)도 이 코드를 쓴다.

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

**없는 `center_id` 면 `404 NOT_FOUND` 다.** 빈 목록(`{"items": []}`)과 구분한다 —
같은 응답으로 돌려주면 FE 가 「반을 추가해 주세요」를 없는 원에도 띄운다.
`GET /api/centers/{center_id}/classes` 도 같다.

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

**같은 이름을 다시 만들면 `409 ALREADY_EXISTS` 다.**

```json
409  { "error": { "code": "ALREADY_EXISTS",
                  "message": "같은 이름의 반이 이미 있습니다.",
                  "fields": ["name"] } }
```

같은 것은 `UNIQUE(center_id, name, school_year)` 가 정하고, 학년도는 서버가 채우므로
교사가 고칠 수 있는 칸은 `name` 하나다. `fields` 에 `school_year` 를 담지 않는다.

**먼저 조회해서 막지 않는다. DB 제약이 터진 것을 409 로 바꾼다.**
조회와 INSERT 사이에 틈이 있어서, 두 요청이 겹치면 둘 다 「없다」를 보고 둘 다 넣는다.

```
요청 A  조회 → 없음
요청 B  조회 → 없음
요청 A  INSERT → 성공
요청 B  INSERT → 제약 위반        조회를 해도 결국 여기로 온다
```

조회를 한 번 더 하는 것은 흔한 경우를 빨리 돌려주는 최적화일 뿐이고, **제약 위반을
잡는 처리는 어차피 있어야 한다.** 없으면 그 틈으로 들어온 요청이 500 으로 나간다.

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
- 등록은 반 행 잠금 안에서 직렬화하며, 저장 전에 반 전체 `NameTable`을 검증한다.
  신규 가명은 신규·기존 실명의 variants를 피한다. 기존 가명과 신규 이름의 충돌,
  동명이인·동일 variant, 가명 고갈 또는 기존 명단의 충돌을 해결할 수 없으면
  저장 없이 `422 VALIDATION_FAILED`, `fields: ["name"]`을 반환한다.
  기존 가명을 자동 재발급하거나 치환 안전 검사를 완화하지 않는다.
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

**양식을 계획안에 복사하지 않는다. 번호만 든다.** `plans.form_id` 가 `forms.id` 를 가리키는
FK 다 — 양식 원본은 하나만 두고 계획안 여러 개가 그걸 가리킨다. 계획안마다 복사하면 같은
양식이 수십 벌이 되고, 양식을 고쳐도 옛 계획안에는 반영되지 않는다.

**그래서 파생 계획안이 남아 있는 양식은 지워지지 않는다**(§8).

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
      "safety_education_state": "SOURCE_REQUIRED",
      "evidence": [
        { "source_type": "THEME_REFERENCE",
          "source_id": "yr_theme_new_environment_friends",
          "source_version": "theme-reference-v0.1.2",
          "effective_date": null,
          "display_name": "우리 원과 친구" }
      ],
      "generation": { "method": "RULE_LLM",
                      "rule_id": "annual-theme", "rule_version": "v1" }
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
months[].safety_education_state  SOURCE_REQUIRED | PLACED | NOT_PLACED.  필수
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

### 빈 배열이 두 가지 뜻이라 상태를 따로 둔다

```
SOURCE_REQUIRED   배치 계획이 없어 판단할 수 없다        P0 의 기본값
PLACED            배치 계획이 있고 이 달에 들어 있다
NOT_PLACED        배치 계획이 있고 이 달엔 없다
```

**`safety_education: []` 만으로는 「그 달엔 안 하기로 했다」와 「언제 할지 아직 모른다」를
구분하지 못한다.** 화면이 둘을 같게 그리면 교사가 「비었네」 하고 넘어간다.

**`SOURCE_REQUIRED` 면 교사에게 입력을 요청한다.** 배치의 출처는 둘뿐이다 —
원의 안전교육 연간계획, 또는 교사 직접 입력
(`p0-planning/data/rules/safety_education_legal_v1.json` 의 `placement_source_priority`).

**규칙 엔진이 배치를 지어내지 않는다.** 같은 파일의 `rule_must_not` 이
「특정 월·주 배치를 자동 창작」·「배치 Source 가 없을 때 법적 충족을 주장」을 금지한다.
**「위반」도 마찬가지로 주장하지 않는다** — 근거 없이 판정하는 건 방향만 다르고 같은 문제다.
그래서 검사기는 `VIOLATION` 과 `UNVERIFIED` 를 나눠 낸다(ADR-014).

**`safety_education` 은 P0 에서 항상 빈 배열이다.** 법이 정하는 건 주기와 연간 시수뿐이고
월 배치는 0건이다(`p0-planning/data/rules/safety_education_legal_v1.json` 의
`month_assignment_policy.has_month_assignment: false`). 배치의 출처는 기관·교사가 준
안전교육 연간계획뿐인데 P0 에 그 입력이 없다. **규칙 엔진도 LLM 도 배치를 만들지 않는다** —
같은 파일의 `rule_must_not`·`llm_must_not`. 칸은 항상 있고 값만 빈다.
값은 그 파일 `categories[].category_id` 를 쓴다.

**`months` 는 항상 12개다.** 3월 시작 ~ 익년 2월.

**`sub_themes` 는 P0 생성 시 항상 빈 배열이다.** `[실측]` p0-planning 의
`ThemeTextGenerator` 는 주제 문장 하나만 돌려준다 — 소주제를 만드는 경로가 아직 없다.
칸은 항상 있고 값만 빈다. **교사가 §6 으로 채운다.** `safety_education` 과 같은 처리다.

서버가 이 값을 도메인 객체 밖(`plans.sub_themes`)에 따로 든다. 소주제는 별도 근거가 없고
상위 주제의 `evidence`·`generation` 을 물려받아서 도메인 객체 안에 들어갈 자리가 없다.

**주제 문장은 `LLM_MODE=real` 일 때 AI 가 쓴다.** 모델은 `openai/gpt-6-luna` 다(ADR-023).
**같은 입력에 같은 답이 온다고 가정하지 않는다** — 이 모델이 온도 0 을 거부해서 우리가
온도를 안 보낸다. 다만 연간은 반당 하나라 다시 만들 수 없고(「반당 하나다」), 만든 뒤에는
저장된 값이 그대로다. 달라지는 것은 **새로 만들 때뿐**이다.

기본은 `mock` 이고 그때는 참조자료 라벨을 그대로 쓴다 — 근거가 흐려지는 게 아니라 오히려 또렷한 상태다. 어느 쪽이든
`generation.method` 가 사실을 말하므로 **화면이 임의로 「AI 가 만들었다」고 쓰면 안 된다.**

생성 실패는 셋으로 갈라 낸다. 셋을 한 코드로 뭉치면 FE 가 「운영 문의」를 띄워야 할
자리에 「다시 시도」를 띄운다.

```
DEPENDENCY_UNAVAILABLE  503   키·주소 설정이 없다.        재시도 무의미
LLM_BUDGET_EXCEEDED     503   한도·키 삭제(401·429).      재시도 무의미
GENERATION_FAILED       500   호출이 깨졌거나 답이 계약을 어겼다.  재시도 가능
```

**부분 결과를 저장하지 않는다.** 열두 달 중 하나라도 어긋나면 계획안 자체를 만들지 않는다.

**`sub_themes` 는 LLM 이 만든다 — 아직 안 만들었다.** 지금은 생성 시 항상 빈 배열이고
교사가 §6 으로 채운다(위 「`sub_themes` 는 P0 생성 시 항상 빈 배열이다」). 아래는 **나중에
만들 때 고른 방향**이지 지금 동작이 아니다. 참조자료(`theme_reference_v0.json`)에는
주제(`label`)만 있고 소주제가 없다. 세 갈래 중 이걸 골랐다.

```
✅  LLM 이 주제에서 소주제를 만든다      ADR-014 의 "LLM 이 만들고 규칙이 검사한다" 범위
    참조자료에 소주제를 추가한다          자료를 다시 훑어야 한다.  근거는 더 확실하다
    계약에서 빼고 선택 필드로             FE 화면 세 곳을 고쳐야 한다
```

소주제도 `generation.method` 는 `RULE_LLM` 이고, `evidence` 는 **상위 주제의 것을 그대로
물려받는다** — 소주제만의 별도 근거 자료가 없다.

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

**RAG 로 생성하고 규칙 엔진이 검사한다**(ADR-014). ADR-005 의 「배치·선별은 규칙 엔진,
LLM 은 문장화만」을 뒤집는다 — 생성과 검사의 순서가 반대다.

**ADR-003 도 같이 깨진다.** ADR-003 은 P0a(5~6주차)를 「결정론적 초안 생성」으로 정의하고
*"P0a 가 결정론적이라 golden set 이 성립한다"*, *"golden set 을 6주차 말에 반드시 고정한다"* 로
검증 전략을 세웠다. **RAG 를 쓰면 출력이 매번 달라져 golden set 이 성립하지 않는다.**
대체 검증 전략(예: 규칙 검사 통과 여부만 고정 검증)을 정해야 한다.

**ADR-014 가 ADR-005 를 대체한다.** ADR-003 은 P0a·P0b 분할은 그대로 두고 결정론 전제만
무효로 표시했다.

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

**교사가 고쳐도 `generation` 과 `evidence` 는 둘 다 그대로다.**

`generation` 은 **그 값을 처음 무엇이 만들었나**를 말한다. 교사가 문구를 다듬었다고 해서
「규칙과 LLM 이 만들었다」는 사실이 사라지지 않는다. 덮어쓰면 그 사실이 없어지고, 나중에
「이 칸은 애초에 어떻게 나온 건가」를 물을 수 없다.

`evidence` 도 같다 — 교사가 문구를 고쳐도 그 칸의 근거(누리과정·주제·상위 계획안)는 바뀌지 않는다.

**교사가 고쳤다는 사실은 Audit 에 `TEACHER_EDITED` 이벤트로 남는다.**
`GET /api/plans/annual/{id}/audit` 가 칸 단위 이벤트까지 같이 준다.

```
generation   이 값을 처음 무엇이 만들었나        안 바뀐다
evidence     무엇을 근거로 만들었나              안 바뀐다
audit        그 뒤에 누가 손댔나                 여기 쌓인다
```

**화면이 「교사 수정됨」 배지를 띄우려면 `generation` 이 아니라 Audit 을 본다.**
`generation.method` 로 판단하면 교사가 고친 칸과 안 고친 칸이 구분되지 않는다.

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

## 7-1. 변경 이력 — `GET /api/plans/annual/{id}/audit`

> **상태: 구현됨.** BE-Y3 에서 `value_change` · `generation_change` 두 키를 더했다. 기존 다섯 키 ·
> `{items}` 봉투 · 순서 · 오류는 그대로다. **조회 계약이다** — 재생성 정책(잠정, `docs/provisional-policy-decisions.md`
> PROV-Y-A · B)을 승인한 것이 아니다.

**Response** `200`

```json
{ "items": [
    { "type": "CREATED", "occurred_at": "2026-09-01T01:00:00+00:00", "month": null,
      "actor": null, "system_actor": "yearly_application",
      "value_change": null, "generation_change": null },
    { "type": "TEACHER_EDITED", "occurred_at": "2026-09-02T02:00:00+00:00", "month": 10,
      "actor": "user_7", "system_actor": null,
      "value_change": { "before": "가을 자연", "after": "교사가 쓴 10월 주제" },
      "generation_change": null },
    { "type": "REGENERATED", "occurred_at": "2026-09-03T03:00:00+00:00", "month": 10,
      "actor": "user_7", "system_actor": null,
      "value_change": { "before": "교사가 쓴 10월 주제", "after": "가을 열매와 곡식" },
      "generation_change": {
        "before": { "method": "RULE_LLM", "rule_id": "yearly.theme.sample_derived_candidate_selection",
                    "rule_version": "v2" },
        "after":  { "method": "RULE_LLM", "rule_id": "yearly.theme.sample_derived_candidate_selection",
                    "rule_version": "v2" } } },
    { "type": "CONFIRMED", "occurred_at": "2026-09-04T04:00:00+00:00", "month": null,
      "actor": "user_7", "system_actor": null,
      "value_change": null, "generation_change": null }
] }
```

값의 모양(문구 · 시각 · id)은 예시다. **일곱 키가 항상 온다** — 해당이 없으면 `null`.

```
type               CREATED | TEACHER_EDITED | REGENERATED | CONFIRMED.  저장된 그대로
occurred_at        ISO 8601.  저장된 시각 그대로
month              그 달 theme 의 이벤트면 그 달(1~12).  계획안 단위(생성 · 확정)면 null
actor              사람이 한 일이면 opaque id (user_7).  시스템이면 null.  이름은 주지 않는다
system_actor       시스템이 한 일(생성)이면 그 표시 (yearly_application).  사람이면 null
value_change       TEACHER_EDITED · REGENERATED 만.  {before, after} — 그때 바뀐 theme 문구.  나머지는 null
generation_change  REGENERATED 만.  {before, after} — 각각 §4 months[].generation 과 같은 모양
                   (method · rule_id · rule_version).  나머지는 null
```

| type | 단위 | 누가 | value_change | generation_change |
|---|---|---|---|---|
| `CREATED` | 계획안 1건 + 달마다 1건 (같은 시각) | `system_actor` | null | null |
| `TEACHER_EDITED` | 달 | `actor` | 있음 (Core 가 반드시 남긴다) | null — 교사 수정은 생성 방식을 바꾸지 않는다 |
| `REGENERATED` | 달 | `actor` | 있음 | 있음 |
| `CONFIRMED` | 계획안 | `actor` | null | null |

- **값은 저장된 이벤트에서만 온다.** 현재 값에서 거꾸로 만들지 않는다. 키가 없는 옛 이벤트는 `null` 이다.
- **`REGENERATED` 는 달 단위 재생성이 만든다.** 그 API 는 잠정 계약이다(PROV-Y-A · B, PM 확인 전).
  교사가 고친 theme 를 다시 만들면 고친 문구가 `value_change.before` 에 남는다 — **볼 수 있다는 것이지
  되돌리는 기능이 있다는 뜻은 아니다.** 복원 API 는 없다.
- **소주제(`sub_themes`) 변경은 이력에 없다.** 소주제는 도메인 밖이라 이벤트가 남지 않는다(§4). §6 PUT 은
  theme 가 그대로여도 `TEACHER_EDITED` 를 남기므로, **소주제만 고친 PUT 은 `before` 와 `after` 가 같은
  이벤트로 보인다.** 이것으로 소주제가 어떻게 바뀌었는지는 알 수 없다.
- **이전 근거(`evidence`)도 없다.** 재생성 뒤 근거는 §5 단건 조회의 현재 값뿐이다.
- 확정 재호출(§7)은 이벤트를 더하지 않는다.

**순서** — `occurred_at` 오름차순. 시각이 같으면 ① 계획안 단위 → ② 달 단위 3월 ~ 익년 2월, 한 달 안에서는
저장된 순서다(생성 때는 모든 `CREATED` 가 같은 시각이라 이 규칙이 순서를 정한다).

**필터 · Pagination 없음.** 열두 달이라 작다. 화면이 `month` 로 거른다. 이벤트별 `revision` 도 없다.

**오류**

| code | status | 언제 | `fields` |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | 로그인 안 함 | `[]` |
| `NOT_FOUND` | 404 | 없거나 남의 원 계획안 · 연간이 아님 | `["id"]` |

---

## 8. 양식 — `POST /api/forms/parse` (구현됨) · 등록 `/api/centers/{center_id}/forms`   ★ 8주차

**`POST /api/forms/parse`** — hwp/hwpx 를 받아 표 구조와 라벨 후보를 돌려준다. 수린 구현(PR #6).
**저장하지 않는다.** 요청·응답만으로 끝나는 순수 변환이다.

**에러**

| code | status | 언제 |
|---|---|---|
| `UNSUPPORTED_FILE_TYPE` | 400 | 확장자가 `.hwp`·`.hwpx` 가 아니다. `fields: ["file"]` |
| `VALIDATION_FAILED` | 422 | 형식은 맞는데 읽지 못했다 — 손상·암호·빈 파일. `fields: ["file"]` |
| `DEPENDENCY_UNAVAILABLE` | 503 | 서버에 `hwp5html` 이 없다. **재시도 버튼을 띄우지 않는다** |

**`hwp5html` 이 0 이 아닌 코드로 끝난 것은 422 다.** 바이너리는 이미지 빌드 때 검증된다
(`backend/Dockerfile` 의 `hwp5html --help`). 실행까지 갔는데 실패했다면 원인은 업로드된
파일 쪽이 훨씬 유력하다. 종료 코드만으로는 둘을 못 가르므로 교사가 조치할 수 있는 쪽으로 붙인다.

**`message` 에 내부 예외 문구를 그대로 싣지 않는다.** `hwp5html 없음 — pip install pyhwp six`
같은 설치 안내가 교사 화면에 뜬다.

### 양식 등록 — 원에 귀속된다

원이 양식을 한 번 등록하면 계속 쓴다. **임시 업로드가 아니라 원의 자산이므로 만료 정책이 없다.**
저장하는 것은 **파싱 결과뿐이다** — 원본 파일은 남기지 않는다(ADR-020).

```
POST   /api/centers/{center_id}/forms     양식 등록 → form_id 발급
GET    /api/centers/{center_id}/forms     등록된 양식
DELETE /api/forms/{id}                    삭제.  수정은 삭제 후 재등록이다
```

**parse 만 토큰 없이 열려 있다.** 등록 · 목록 · 삭제는 원의 자산을 읽고 쓰므로 인증 뒤에 있고
원 단위 인가를 거친다(§0 · ADR-017 · ADR-020).

**`POST /api/centers/{center_id}/forms`** — `multipart/form-data`, 필드 `file` 하나. parse 와 같다.
받는 확장자도 같다(`.hwp` · `.hwpx`). 파싱에 성공해야 저장한다 — 읽지 못한 양식은 행이 생기지 않는다.
**표가 하나도 없으면 등록하지 않는다** — `422 VALIDATION_FAILED`. 계획안 양식은 표다.
parse 는 빈 결과(`tables: []`)를 그대로 돌려준다 — 저장하지 않으니 막을 이유가 없다.

FE 양식 화면(`TemplatesPage`)은 지금 pdf · docx 등을 받아 브라우저에 둔다. 이 계약에 붙이면
받는 형식이 hwp · hwpx 로 바뀐다.

→ `201`

```json
{ "id": 3, "center_id": 1,
  "name": "2026 유아반 월간계획안.hwp",
  "filename": "2026 유아반 월간계획안.hwp",
  "tables": [ [ [ { "text": "월", "rowspan": 1, "colspan": 1 }, ... ] ] ],
  "labels": ["월", "주제", "예상놀이", "봄 동산"],
  "label_map": { "월": "month", "주제": "topic", "예상놀이": "activity", "봄 동산": null },
  "created_at": "2026-09-29T10:00:00+09:00" }
```

| 필드 | 타입 | |
|---|---|---|
| `tables` | `Cell[][][]` | 표 → 행 → 셀. `Cell { text: string, rowspan: int, colspan: int }`. 중첩 표는 따로 한 표로 나온다 |
| `labels` | `string[]` | 빈 칸을 뺀 셀 문구. 중복을 지우지 않는다 |
| `label_map` | `{ [label]: string \| null }` | 표준 키(ADR-009). **값이 `null` 일 수 있다** — 데이터 값이거나 매핑표에 없는 표현이다 |
| `name` | `string` | 화면에 보일 이름. **지금은 `filename` 과 같다.** 이름 입력은 받지 않는다 |
| `filename` | `string` | 업로드한 파일명 |

**같은 파일을 다시 올리면 새 행이 생긴다.** 중복을 막지 않는다 — 잘못 올렸으면 지운다.

**`GET /api/centers/{center_id}/forms`** → `{ "items": [...] }`. 항목은 위 등록 응답과 같다.
정렬은 `created_at DESC, id DESC`. 상세 조회(`GET /api/forms/{id}`)는 두지 않는다 — 원당 양식이
몇 개라 목록에 파싱 결과까지 싣는다. 양식이 늘어 목록이 무거워지면 목록을 요약으로 줄이고 상세를 붙인다.

**`DELETE /api/forms/{id}`** → `204`.

**파생 계획안이 남아 있으면 지우지 않는다.** `plans.form_id` 가 `forms.id` 를 가리키는 FK 다(§4).
그대로 지우면 DB 가 막는다. **지금은 409 `IN_USE` 로 알린다** (문구 「이 양식으로 만든 계획안이 있어 지울 수 없습니다.」, `fields` 는 `[]`).
**숨김이 들어오면 204 로 바뀐다 — 숨김은 미구현.**

```
파생 계획안이 없다   →  진짜 지운다.  204
파생 계획안이 있다   →  지우지 않고 숨긴다.  목록에 안 나온다.  204
                      계획안이 전부 사라지면 그때 진짜 지운다
```

**원본 파일을 저장한다 — 미구현.** 지금은 파싱 결과(`tables`·`labels`·`label_map`)만 남기고
원본을 버린다. 그래서 ① 파서를 고쳐도 옛 양식에 다시 적용할 수 없고 ② 원이 쓰던 서식 그대로
내보낼 수 없다. 양식 하나가 KB 단위고 원당 몇 개뿐이라 DB 에 넣는다.

**§4 가 받은 `form_id` 는 forms 의 조회 함수로 검사한다** — 없거나 남의 원 것이면 `NOT_FOUND` 404
(`fields: ["form_id"]`). plans 가 forms 를 직접 import 하지 않는다(`structure.md`).

**에러** — parse 의 세 개에 셋이 더 붙는다

| code | status | 언제 | `fields` |
|---|---|---|---|
| `UNSUPPORTED_FILE_TYPE` | 400 | parse 와 같다 | `["file"]` |
| `VALIDATION_FAILED` | 422 | parse 와 같다. `file` 이 없어도 이것이다. 등록은 **파일명이 255자를 넘어도** 이것이다 — 컬럼 길이다. 브라우저 업로드에서는 생기지 않는다(OS 한도가 255자) | `["file"]` |
| `DEPENDENCY_UNAVAILABLE` | 503 | parse 와 같다 | `[]` |
| `UNAUTHENTICATED` | 401 | 토큰이 없거나 못 믿는다(§0) | `[]` |
| `NOT_FOUND` | 404 | 없는 원 · 없는 양식. **남의 원 것도 404 다**(ADR-017) | 등록 · 목록 `["center_id"]` / 삭제 `["form_id"]` |
| `IN_USE` | 409 | 이 양식으로 만든 계획안이 있어 지울 수 없다. 숨김 삭제가 들어오면 빠진다 | `[]` |

**파일 크기 상한은 아직 없다** — parse 도 같다. 따로 정한다.

---

## 9. 7주차 예정 — 계약 안 씀

```
POST   /api/plans/monthly                 월간 — §9-1 (구현됨, M4)
PUT    /api/plans/monthly/{id}/cells/{item_id}  칸 편집 — §9-3 (구현됨, M5)
POST   /api/plans/monthly/{id}/cells/{item_id}/regenerate   이 칸만 다시 — §9-3 (구현됨, M5)
GET    /api/plans/{id}/export/hwp         내보내기
GET    /api/plans/annual/{id}/audit       Audit 이벤트 조회 — §7-1 (구현됨) · 되돌리기(P1)·평가제(P2)
GET    /api/plans/monthly/{id}/audit      월간 변경 이력 — §9-5 (구현됨, BE-2)
PUT    /api/centers/{center_id}/plan-config   uses_monthly · weekly_location
```

**칸 수를 계약으로 정하지 않는다.** 「43칸」은 우리 기본 서식에서 센 수다. 칸 수는 양식 ·
활성 주차 · 구역 구조가 정하므로 원이 올린 양식에 따라 달라진다. **화면은 서버가 준 만큼
그린다** — 43으로 박으면 40칸짜리 양식에서 빈 칸이 생기거나 넘친다.

**칸 식별자는 `item_id` 다.** 순번 `{n}` 을 쓰지 않는다 — 양식이 바뀌면 「n번째」의 뜻이
바뀌고, 수정·재생성 뒤에도 같은 칸을 가리켜야 한다.

**월간은 연간이 `CONFIRMED` 여야 생성된다.** 아니면 `GATE_BLOCKED` 409.
**층 순서를 건너뛸 수 없다.** 연간·월간·주간을 한 번에 생성하지 않는다.

### 내보내기 — `GET /api/plans/{id}/export/hwp` (구현됨)

**이 API 만 JSON 이 아니다.** 파일이 내려온다. 다른 API 처럼 `apiRequest` 로 부르면
JSON 파싱에서 깨진다 — FE 는 이 하나를 따로 다룬다.

```
응답 200    Content-Type: application/hwp+zip
            Content-Disposition: attachment; filename="plan-10.hwpx";
                                 filename*=UTF-8''<한글 이름>.hwpx
```

**경로는 `hwp` 인데 내려가는 파일은 `hwpx` 다.** `.hwp` 는 공개된 구조가 없어 우리가
만들 수 없다. hwpx 는 zip + XML(국가표준)이라 만들 수 있고 한글 2010 이상에서 열린다.
**교사가 한글에서 「다른 이름으로 저장 → .hwp」 하면 hwp 가 된다** — 클릭 한 번이다.

> **변환 기능을 서버에 두지 않는다.** 시중 변환은 파일을 남의 서버로 보낸다.
> 계획안에는 반 이름·담임 이름이, 일지에는 아동 실명이 들어간다 — 그 파일을 밖으로
> 보내면 ADR-004 가 LLM 한 줄을 막아둔 것이 통째로 무의미해진다.

**확정본만 내보낸다.** DRAFT 면 `GATE_BLOCKED` 409 다. 내보낸 파일은 제출 문서라,
교사가 확인하지 않은 초안이 그대로 제출되는 길을 만들지 않는다.

**출처를 싣지 않는다.** `evidence` · `generation` 은 화면이 근거를 보여주는 값이지
제출 문서에 들어갈 것이 아니다. 교사가 읽는 글자만 꺼낸다.

**작성자 정보를 지운다.** 양식 파일에 남은 `creator` · `lastsaveby` 를 내보낼 때
다시 비운다 — 양식을 새로 넣는 사람이 잊어도 막힌다.

| code | status | 언제 |
|---|---|---|
| `GATE_BLOCKED` | 409 | 확정 전이다 |
| `NOT_FOUND` | 404 | 없거나 남의 원 계획안이다 |

**월간은 아직 없다.** 월간 API 와 양식이 같이 생길 때 붙인다.
**원이 올린 양식으로 내보내는 것도 아직이다**(§8 양식 등록이 먼저다).

**「일간」 계획안은 만들지 않는다.** 스펙에도 ADR 에도 없는 문서 종류다.

`plan-config` 의 두 값은 7주차 기능의 입력이다 — `uses_monthly` 는 월간 생성이,
`weekly_location` 은 보육일지·관찰일지(P1, ADR-003)가 붙을 때 의미가 생긴다.
**P0 에서는 받지 않는다.** `safety_edu_hours` 는 서버 상수로 옮겼다(§4).

**hwp 내보내기에 출처 마커가 섞이면 안 된다.** 제출 문서다 — 7주차 계약을 쓸 때 다시 확인한다.

**관찰일지·보육일지는 §10 · §11 로 계약을 썼다(7주차).** 6주차 화면이 선행 구현이고,
그 화면이 쓰는 모양을 그대로 옮겼다 — `frontend/lib/workspace/model.ts`.
**평가제 대조는 8주차로 당겼다 — §12.**

**LLM 으로 나가는 자유 입력 필드(계획안 생성 메모 등)도 `shared/childCode` 치환 대상이다.**
치환 실패 시 호출하지 않고 에러를 낸다.

---

## 9-1. 월간계획안 생성 · 조회 — `POST /api/plans/monthly` · `GET /api/plans/monthly/{id}` · `GET /api/plans/monthly?class_id=`

> **상태: 구현됨 (M4).** 결정은 결정 문서 12.4 · 12.5 · 12.6 과 M4-0 결정
> D-M4-01 ~ 04 다. 칸 편집 · 칸 재생성 · 확정과 `revision` 409 는 §9-3(M5)이다.

### 생성 — `POST /api/plans/monthly`

**Request**

```json
{ "class_id": 1, "month": 9,
  "profile_ref": { "profile_id": "tprofile_3f2a…", "profile_version": "v1" } }
```

```
class_id                 정수.  필수.  내 원의 반이어야 한다(남의 원이면 404)
month                    정수 1~12.  필수.  달력의 달이다
profile_ref.profile_id   문자열.  필수.  빈 문자열 거부
profile_ref.profile_version  문자열.  필수.  정확한 버전 — "latest" 같은 별칭은 없다
```

**`school_year` 를 받지 않는다.** 연간(§4)과 같다 — `class_id` 의 학년도가 정한다.
대상 달은 3~12월이면 그 학년도, 1~2월이면 다음 해다(2026 학년도의 `month: 2` 는 2027-02).

**부모 연간계획안을 받지 않는다.** 서버가 반으로 찾는다 — 연간은 반당 하나다(§4).

**`profile_ref` 는 화면에서 사용자가 확인한 정확한 버전을 그대로 보낸다**(결정 문서 Contract 2 R5).
서버는 그 사이 원 기본 · 반 override 가 바뀌었다고 다시 고르지 않는다. 최신 버전을 대신 고르지도
않는다. 무엇을 보여 줄지는 §9-2 가 준다.

**받지 않는 것.** 생성 방식(서버 정책 — `LLM_PLANNER`), 참조자료 판(서버 상수), 안전교육 배치
정책(아래), 자유 메모.

**Response** `201` — 아래 「월간계획안 응답」.

**동기다.** 요청 안에서 생성 · 검증 · 저장을 끝내고 201 을 준다. 실측으로 10 ~ 15초쯤 걸린다 —
화면은 진행 표시를 하고 같은 요청을 다시 보내지 않는다(screen-spec §5.1).
**조건부 채택이다**(결정 문서 12.9-1). Luna-6 실측 3건(2026-10-09)이 LLM 10.3 ~ 13.0초 · 수리 0회 ·
400 없음이었다 — 호출 타임아웃 30초 · nginx `proxy_read_timeout 120s` 안이다. 표본이 3건이라 운영
호출 기록에서 호출 시간이 자주 20초를 넘거나 타임아웃 · 수리가 반복되면 다시 정한다.

**부분 결과를 저장하지 않는다.** 어디서 실패해도 계획안 행이 생기지 않는다.

**같은 반 · 같은 달은 하나다**(결정 문서 12.5). `DRAFT` 든 `CONFIRMED` 든 `ALREADY_EXISTS` 409 —
FE 는 기존 계획안으로 이동한다. 전체 재생성은 P0 에 없다(screen-spec §5.3).

### 안전교육 — 근거가 없으면 비워 두고 그렇다고 표시한다

**M4 는 안전교육 배치 정책(`ssuksak-safety-placement-v2`)을 넘기지 않는다**(D-M4-03).
그래서 안전교육 칸은 Core 의 「근거 필요」 경로를 탄다(OD-M04 의 source-required 경로).

- 칸은 항상 있고 `state: "EMPTY_UNRESOLVED"`, `value: ""` 다. 규칙도 LLM 도 내용을 지어내지 않는다.
- `constraints` 에 `STATUTORY_SAFETY_EDUCATION` · `NOT_VERIFIED_SOURCE_REQUIRED` 가 실린다.
  **「법정 요건을 충족한다」도 「위반이다」도 말하지 않는다.**
- 다른 Section 은 영향이 없다. 근거가 있는 칸은 `FILLED` 와 `evidence` 를 갖는다.
- 비어 있어도 확정할 수 있다(Core 계약). 화면은 확정 전에 비어 있다는 것을 보여 준다.

### 월간계획안 응답 — 생성 · 단건 조회가 같은 형식

```json
{
  "id": 21,
  "class_id": 1,
  "school_year": 2026,
  "month": 9,
  "target_month": "2026-09",
  "status": "DRAFT",
  "revision": 1,
  "generation_mode": "LLM_PLANNER",
  "profile_ref": { "profile_id": "tprofile_3f2a…", "profile_version": "v1" },
  "base_template_ref": { "template_id": "ssuksak.monthly-template-a",
                         "template_version": "monthly-template-a-v0.2.1" },
  "parent": { "annual_plan_id": 10, "theme": "우리 원과 친구",
              "confirmed_at": "2026-09-01T10:00:00+09:00" },
  "weeks": [
    { "week_id": "2026-09-W1", "label": "1주", "start_date": "2026-09-01",
      "end_date": "2026-09-04", "active": true }
  ],
  "sections": [
    { "section_key": "theme", "label": "주제", "role": "CONTENT", "repeat_by": "NONE",
      "visible": true, "order": 0, "semantic_variant": null,
      "cells": [
        { "item_id": "item_7c1e…", "week_id": null, "value": "우리 원과 친구",
          "state": "FILLED",
          "evidence": [
            { "source_type": "PARENT_PLAN", "source_id": "plan_…", "source_version": null,
              "effective_date": null, "display_name": null } ],
          "generation": { "method": "RULE_ONLY", "rule_id": "…", "rule_version": "…" } }
      ] },
    { "section_key": "safety_education", "label": "안전교육", "role": "CONTENT",
      "repeat_by": "WEEK", "visible": true, "order": 3, "semantic_variant": null,
      "cells": [
        { "item_id": "item_…", "week_id": "2026-09-W1", "value": "",
          "state": "EMPTY_UNRESOLVED", "evidence": [],
          "generation": { "method": "RULE_ONLY", "rule_id": "…", "rule_version": "…" } }
      ] }
  ],
  "constraints": [
    { "code": "STATUTORY_SAFETY_EDUCATION", "verification": "NOT_VERIFIED_SOURCE_REQUIRED",
      "affected_section_keys": ["safety_education"], "required_source_kinds": ["…"],
      "rule_version": "…", "detail": "…" }
  ],
  "verification": {
    "executed_rules": [ { "rule_id": "…", "rule_version": "…" } ],
    "findings": [
      { "code": "…", "kind": "NOT_VERIFIED", "severity": "WARNING",
        "section_key": "outdoor_play", "week_id": "2026-09-W2", "message": "…" } ]
  },
  "created_at": "2026-09-20T10:00:00+09:00",
  "confirmed_at": null
}
```

값의 모양(`week_id` · `item_id` · `rule_id` 등)은 예시다. **실제 값은 Core 가 정하고 서버가 다시 짓지 않는다.**

**필드**

```
id · class_id · school_year · month   정수.  필수.  id 는 plans.id (연간 §4 와 같다)
target_month          "YYYY-MM".  필수
status                DRAFT | CONFIRMED.  필수
revision              정수 ≥ 1.  필수.  저장할 때마다 +1. M5 의 칸 편집 · 재생성이 읽은 값을 보낸다
generation_mode       RULE_ONLY | LLM_PLANNER.  필수.  M4 가 만드는 것은 LLM_PLANNER 뿐
profile_ref           생성에 쓴 정확한 Profile 버전.  필수.  TemplateSnapshot 의 값이다
base_template_ref     그 Profile 의 기반 Template.  필수
parent.annual_plan_id 부모 연간계획안 plans.id.  필수
parent.theme          생성 당시 부모 주제 (ParentLineage.snapshot_value).  null 허용
parent.confirmed_at   부모 확정 시각.  필수

weeks[]               이 달의 주.  순서대로.  필수.  개수를 정하지 않는다
weeks[].week_id       문자열.  필수.  칸의 week_id 와 같은 값
weeks[].label         문자열.  필수.  화면에 보이는 주 이름
weeks[].start_date · end_date   YYYY-MM-DD.  필수
weeks[].active        불리언.  필수.  false 인 주에는 칸이 없다

sections[]            TemplateSnapshot 순서.  필수.  개수를 정하지 않는다
sections[].section_key  문자열.  필수.  의미 키 (theme · outdoor_play · focus …)
sections[].label      문자열 | null.  Profile 이 정한 표시 이름.  숨긴 Section 은 null 일 수 있다
sections[].role       CONTENT | AXIS.  필수.  AXIS(주 머리)는 칸이 없다
sections[].repeat_by  NONE | WEEK | null.  NONE 은 한 달에 칸 하나, WEEK 는 활성 주마다 하나, AXIS 는 null
sections[].visible · order   필수
sections[].semantic_variant  SUBTHEME | EXPECTED_PLAY | WEEKLY_THEME | NEUTRAL | null.  focus 만 값이 있다
sections[].cells[]    필수.  개수를 정하지 않는다 — 화면은 받은 만큼 그린다

cells[].item_id       문자열.  필수.  칸의 주소.  편집 · 재생성 뒤에도 바뀌지 않는다
cells[].week_id       문자열 | null.  repeat_by = NONE 이면 null
cells[].value         문자열.  필수.  비어 있으면 ""
cells[].state         FILLED | EMPTY_VALID | EMPTY_UNRESOLVED.  필수
cells[].evidence      배열.  필수.  §4 「출처는 세 축이다」와 같은 모양
cells[].generation    객체.  필수.  §4 와 같은 모양 (method · rule_id · rule_version)

constraints[]         Core 제약 평가.  필수(빈 배열 가능)
verification          Core 검증 보고서.  필수.  findings[].kind 는 VIOLATION | NOT_VERIFIED
created_at · confirmed_at   ISO 8601.  confirmed_at 은 확정 전 null
```

- **출처는 §4 의 세 축 그대로다.** `evidence` 는 근거, `generation` 은 만든 방법이다.
  **`audit` 은 싣지 않는다**(§4 와 같은 이유). 변경 이력은 §9-5 `GET /api/plans/monthly/{id}/audit` 가 준다.
- **칸을 표로 펼쳐 주지 않는다.** 행 = Section, 열 = 주는 화면이 `section_key` · `week_id` 로 맞춘다.
  양식마다 표 모양이 달라서 서버가 표를 정하면 계약이 양식에 묶인다.
- **도메인 객체를 그대로 내보내지 않는다.** 위 필드만 옮긴다. Cell 의 `source_label` ·
  `label_variant` · `mapping_confidence`(기존 계획안 가져오기용) · `safety`(배치 정책을 넘길 때만
  값이 있다) 는 M4 응답에 없다.

### 단건 — `GET /api/plans/monthly/{id}`

`200`, 생성과 같은 형식. 없거나 남의 원 것이면 `NOT_FOUND` 404.

### 목록 — `GET /api/plans/monthly?class_id=1`

```json
{ "items": [
    { "id": 21, "class_id": 1, "school_year": 2026, "month": 9, "target_month": "2026-09",
      "status": "DRAFT", "revision": 1,
      "profile_ref": { "profile_id": "tprofile_3f2a…", "profile_version": "v1" },
      "created_at": "...", "confirmed_at": null }
] }
```

요약만 담는다 — 칸은 단건이 준다. `class_id` 를 빼면 내 원 전체, 넣으면 그 반(남의 원 반이면 404).
정렬은 대상 달 오름차순.

### 오류 — 생성

| code | status | 언제 | `fields` |
|---|---|---|---|
| `VALIDATION_FAILED` | 422 | `month` 가 1~12 밖 · `profile_ref` 모양이 틀림 | `["month"]` 등 |
| `NOT_FOUND` | 404 | 반이 없거나 남의 원 반 | `["class_id"]` |
| `GATE_BLOCKED` | 409 | 그 반의 연간계획안이 **없거나 확정 전** | `["class_id"]` |
| `NOT_FOUND` | 404 | `profile_ref` 가 없다 · READY 가 아니다 · 남의 원 것이다 (셋을 가르지 않는다, ADR-017) | `["profile_ref"]` |
| `ALREADY_EXISTS` | 409 | 같은 반 · 같은 달 월간이 있다 (동시 요청은 DB 유일 제약이 막고 409 로 바꾼다) | `["class_id","month"]` |
| `VALIDATION_FAILED` | 422 | 고른 Profile 로는 만들 수 없다 — 기관 입력 Section(`event_schedule` · `drill`) · 근거 없는 필수 Section 등. **재시도해도 같다.** 다른 Profile 을 고른다 | `["profile_ref"]` |
| `LLM_BUDGET_EXCEEDED` | 503 | 한도 · 키 삭제 (401 · 403 · 429) | `[]` |
| `DEPENDENCY_UNAVAILABLE` | 503 | LLM 설정이 없다 · 서버의 승인 참조자료를 읽을 수 없다. 재시도 무의미 | `[]` |
| `GENERATION_FAILED` | 500 | LLM 호출이 깨졌다(타임아웃 포함) · 응답이 계약을 어겼다(수리 1회 뒤에도) · Core 검증 실패. **재시도 가능.** 부분 저장 없음 | `[]` |

**연간이 없는 것과 확정 전인 것을 같은 코드로 낸다.** FE 가 할 일(연간계획안으로 가기)이 같다.
`message` 는 둘을 구분해 쓴다 — 「연간계획안을 먼저 만들어 확정해주세요」 · 「연간계획안을 먼저 확정해주세요」.

**Core 오류 코드를 그대로 내보내지 않는다**(CLAUDE.md §20). 위 표의 `code` 가 공개 계약이다.

---

## 9-2. 월간 양식 설정(TemplateProfile) 조회 — 생성 전에 고르기

> **상태: 구현됨 (M4).** 조회 둘뿐이다(D-M4-02). Profile 만들기 · DRAFT 편집 ·
> READY 전환 · 보관 · 원 기본 / 반 override 바꾸기는 **별도 후속 작업**이고 M6 화면 연동 전에 필요한
> 만큼 만든다. → **BE-1 이 Reference 기반 시작 · 원 기본 · 반 override 를 §9-4 로 열었다.**
> DRAFT 편집 · READY 전환 · 보관은 아직 없다.

생성 화면은 ① 이 반에 무엇이 적용되는지 보여 주고 ② 바꾸고 싶으면 원의 READY 목록에서 고르게
한 뒤 ③ **보여 준 그 정확한 버전**을 §9-1 `profile_ref` 로 보낸다.

### 반에 적용되는 Profile — `GET /api/classes/{class_id}/template-profile`

```json
{ "source": "CLASSROOM_OVERRIDE",
  "profile_ref": { "profile_id": "tprofile_3f2a…", "profile_version": "v1" },
  "reason": null }
```

```
source       CLASSROOM_OVERRIDE | INSTITUTION_DEFAULT | SELECTION_REQUIRED.  필수
profile_ref  SELECTION_REQUIRED 면 null
reason       SELECTION_REQUIRED 일 때만 값.  NO_POINTER(아무것도 안 걸림) ·
             CLASSROOM_OVERRIDE_NOT_READY 처럼 「어느 포인터가 왜 못 쓰이나」
```

**순서는 반 override → 원 기본 → 「선택 필요」다**(결정 문서 C2.7 R1 ~ R4). 포인터가 가리키는
버전을 쓸 수 없으면 **원 기본으로 내려가지 않고** 「선택 필요」다(R3) — 반 설정이 조용히 무시되지
않게 한다. 최신 READY 를 대신 고르지 않는다.

남의 원 반이면 `NOT_FOUND` 404.

### 원의 READY 목록 — `GET /api/centers/{center_id}/template-profiles`

```json
{ "items": [
    { "profile_ref": { "profile_id": "tprofile_3f2a…", "profile_version": "v1" },
      "status": "READY",
      "base_template_ref": { "template_id": "ssuksak.monthly-template-a",
                             "template_version": "monthly-template-a-v0.2.1" },
      "selected_optional_keys": ["focus"],
      "sections": [ { "section_key": "theme", "label": "주제", "repeat_by": "NONE", "visible": true } ],
      "created_at": "..." }
] }
```

- **READY 만 준다.** DRAFT · ARCHIVED 는 생성에 쓸 수 없다. 만든 순서대로.
- 남의 원 `center_id` 면 `NOT_FOUND` 404 (`require_own_center`).
- **Profile 에는 이름 칸이 없다.** 사용자는 버전 · 기반 Template · 고른 Section 과 그 이름 ·
  만든 시각으로 구분한다. 이름 칸은 Core 에 없어 만들지 않는다(결정 문서 12.9 OPEN).

### 승인 조건

READY Profile 은 사람이 승인한 Template 으로만 만들어진다(결정 문서 12.8 — 만들 때 검사한다).
**지금 Template A v0.1.1 · v0.2.1 은 승인 대기라 운영 DB 에 READY Profile 이 생길 수 없다** —
그동안 §9-2 목록은 빈 배열이고 §9-1 은 `NOT_FOUND` 404(`profile_ref`) 다.

---

## 9-3. 월간계획안 칸 편집 · 칸 재생성 · 확정

> **상태: 구현됨 (M5).** 결정은 결정 문서 12.4 D-3 · 12.10(D-M5-CONFIRM-01) 이다.
> 세 API 모두 `200` 에 §9-1 「월간계획안 응답」 전체를 돌려준다 — 새 `revision` 과 다시 계산한
> 검증 결과(`constraints` · `verification`)가 들어 있다.

### 읽은 revision 을 같이 보낸다 — `expected_revision`

```json
{ "expected_revision": 3 }
```

```
expected_revision   정수 ≥ 1.  필수.  §9-1 응답의 revision 을 그대로 보낸다
                    문자열 "3" · true 처럼 타입이 다르면 VALIDATION_FAILED 422
```

**서버 값과 다르면 저장하지 않고 `STALE_WRITE` 409 다**(§11 문서 PUT 과 같은 코드 · 같은 뜻).
두 화면에서 같은 계획안을 고치면 나중 저장이 먼저 저장을 조용히 덮는다 — 그걸 막는다.
FE 는 단건을 다시 불러와 보여 주고 다시 하게 한다.

**비교와 저장이 한 번에 일어난다.** 서버는 「DRAFT 이고 revision 이 그대로일 때만 쓰고 +1」 을
한 문장으로 한다. 같은 revision 으로 두 요청이 동시에 와도 하나만 저장된다.

### 칸 편집 — `PUT /api/plans/monthly/{id}/cells/{item_id}`

```json
{ "value": "가을 자연물을 활용한 놀이", "expected_revision": 3 }
```

```
value   문자열.  필수.  빈 문자열도 받는다(칸을 비운다 — 상태는 서버가 다시 계산한다)
```

- 어느 Section 의 칸이든 고칠 수 있다. 칸 주소는 `item_id` 다 — 고친 뒤에도 바뀌지 않는다.
- **근거(`evidence`) · 생성 방식(`generation`)은 바뀌지 않는다.** 교사가 고쳤다는 사실은 변경
  이력(`TEACHER_EDITED`, 이전 값 · 새 값)에 남는다(§4 「출처는 세 축이다」).
- 같은 값으로 고치면 `VALIDATION_FAILED` 422 다.

### 칸 재생성 — `POST /api/plans/monthly/{id}/cells/{item_id}/regenerate`

```json
{ "expected_revision": 3 }
```

- **그 칸만** 다시 만든다. 전체 재생성은 P0 에 없다(screen-spec §5.3). 추가 지시문은 받지 않는다.
- 다시 만들 수 있는 칸은 Core 가 정한다 — 지금은 `focus` · `outdoor_play` · `basic_habit` · `goals`.
  주제 · 안전교육 · 주 머리줄은 `VALIDATION_FAILED` 422 (`["item_id"]`).
- **교사가 고친 칸도 요청하면 다시 만든다** — 고친 값이 새 값으로 바뀐다. 덮어쓰기 확인은 화면이
  한다(M6).
- `item_id` · `week_id` 는 그대로다. 근거는 새 결과의 근거로 바뀌고, 이전 값과 생성 방식은 변경
  이력(`REGENERATED`)에 남는다.
- LLM 을 기다리는 동안 다른 화면이 고치거나 확정했으면 **새 결과를 버리고** `STALE_WRITE` /
  `ALREADY_CONFIRMED` 409 다. 실패하면 칸 · revision 이 그대로다. 오류는 §9-1 생성과 같다
  (`LLM_BUDGET_EXCEEDED` · `DEPENDENCY_UNAVAILABLE` 503 · `GENERATION_FAILED` 500).

### 확정 — `POST /api/plans/monthly/{id}/confirm`

```json
{ "expected_revision": 3 }
```

```
DRAFT · revision 일치      CONFIRMED 로 바꾼다.  revision +1.  200
DRAFT · revision 다름      STALE_WRITE 409.  아무것도 바꾸지 않는다
이미 CONFIRMED             expected_revision 과 상관없이 200 · 저장된 그대로
                           revision · confirmed_at · 확정자 · 확정 이력이 바뀌지 않는다
```

**재호출은 멱등이다**(결정 문서 12.10 D-M5-CONFIRM-01, 연간 §7 과 같은 이유). 첫 확정이 revision
을 올리므로 더블클릭 · 재시도로 두 번째 도착한 요청은 항상 옛 revision 을 든다 — 그걸 409 로 막으면
FE 가 진짜 실패와 구분하지 못한다. **멱등이어도 소유 검사가 먼저다** — 남의 원 계획안은 404.

**확정은 검증 결과로 막지 않는다.** 안전교육이 「근거 필요」(`EMPTY_UNRESOLVED` ·
`NOT_VERIFIED_SOURCE_REQUIRED`)로 남아 있어도 확정된다 — 「법정 요건 충족」이라는 뜻이 아니다.
검증기 자체가 돌지 못하면 `GENERATION_FAILED` 500 이다.

**되돌리기는 P1 이다.** 확정 뒤 칸 편집 · 재생성은 `ALREADY_CONFIRMED` 409 다.

### 오류 — 세 API 공통

| code | status | 언제 | `fields` |
|---|---|---|---|
| `NOT_FOUND` | 404 | 계획안이 없거나 남의 원 것 · 월간이 아님 | `["id"]` |
| `NOT_FOUND` | 404 | 그 `item_id` 칸이 없다 (편집 · 재생성) | `["item_id"]` |
| `ALREADY_CONFIRMED` | 409 | 확정된 계획안의 칸을 고치거나 다시 만들려 함 | `[]` |
| `STALE_WRITE` | 409 | `expected_revision` 이 서버 값과 다르다 (확정 재호출은 예외 — 200) | `["expected_revision"]` |
| `VALIDATION_FAILED` | 422 | 입력 모양이 틀림 · 같은 값으로 편집 | 해당 필드 · `["value"]` |
| `VALIDATION_FAILED` | 422 | 다시 만들 수 없는 칸 | `["item_id"]` |
| `LLM_BUDGET_EXCEEDED` · `DEPENDENCY_UNAVAILABLE` | 503 | 재생성 · 참조자료 (§9-1 과 같다) | `[]` |
| `GENERATION_FAILED` | 500 | 재생성 실패 · 검증기 실행 실패. 아무것도 저장되지 않는다 | `[]` |

---

## 9-4. 월간 양식 설정(TemplateProfile) 관리 — 시작 · 원 기본 · 반 override

> **상태: 구현됨 (BE-1).** 결정은 결정 문서 Contract 2(C2.6 · C2.7) · 12.8 · 12.12 다.
> M2 저장소의 규칙을 HTTP 로 연 것이다 — 규칙을 늘리지 않았다.
> **DRAFT 만들기 · 저장 · 편집 · READY 전환 · 보관 API 는 아직 없다.**

### 공통

- **로그인 필수**(`401 UNAUTHENTICATED`). 인가는 원 단위다 — 남의 원 · 남의 원 반 · 남의 원 Profile
  은 없는 것과 같은 `404`(ADR-017).
- **권한:** 원 소속 계정 누구나 바꿀 수 있다(결정 문서 C2.6 · C2-E, TP-05 `RESOLVED_FOR_P0`). 역할
  구분은 없다. 포인터를 바꾸면 `changed_by`(users.id) · `changed_at` 이 남는다.
- **화면 흐름:** §9-2 해석(`GET /api/classes/{class_id}/template-profile`)이 `SELECTION_REQUIRED`
  이면 ① 기반 Template 목록 → ② 시작 → (사용자가 동의하면) ③ 원 기본 지정 또는 ④ 반 override →
  §9-2 해석을 다시 읽고 → 보여 준 정확한 `profile_ref` 로 §9-1 생성.

### ① 기반 Template 목록 — `GET /api/monthly-templates`

```json
{ "items": [
    { "template_ref": { "template_id": "ssuksak.monthly-template-a",
                        "template_version": "monthly-template-a-v0.2.1" },
      "approved": false,
      "sections": [
        { "section_key": "theme", "label": "theme", "role": "CONTENT", "repeat_by": "NONE",
          "selection": "REQUIRED" },
        { "section_key": "week_axis", "label": "week_axis", "role": "AXIS", "repeat_by": null,
          "selection": "REQUIRED" },
        { "section_key": "basic_habit", "label": "habits", "role": "CONTENT", "repeat_by": "WEEK",
          "selection": "OPTIONAL" },
        { "section_key": "event_schedule", "label": "event_schedule", "role": "CONTENT",
          "repeat_by": null, "selection": "INSTITUTION_INPUT" }
      ],
      "focus_variants": ["SUBTHEME", "EXPECTED_PLAY", "WEEKLY_THEME"] }
] }
```

```
template_ref      ② 의 base_template_ref 로 그대로 보낸다
approved          데이터 파일의 사람 승인 상태.  **false 도 목록에 보인다** — 보인다고 쓸 수 있는 것이
                  아니다.  false 면 ② 가 409 GATE_BLOCKED
sections[]        Template 순서.  section_key 는 Profile 이름이다 (Template 의 habits → basic_habit)
sections[].label  Template 데이터 값 그대로.  지금 Template A 는 칸 이름과 같다 — 화면 이름이 아니다.
                  그래서 ② 에서 표시 이름을 직접 보낸다
sections[].selection
                  REQUIRED           항상 들어간다 (theme · week_axis · outdoor_play · safety_education)
                  OPTIONAL           ② 에서 고를 수 있다 (focus · goals · basic_habit)
                  INSTITUTION_INPUT  event_schedule · drill.  월간 생성 계약이 아직 없어 고를 수 없다
                  NOT_SUPPORTED      Template 고유 칸.  Profile 에 넣을 수 없다
focus_variants    focus 를 고를 때 쓸 수 있는 값.  NEUTRAL 은 없다 (켠 focus 는 NEUTRAL 불가, Core)
```

- 원 범위가 없는 전역 Reference 다. 로그인만 본다.
- **지금 값: v0.1.1 · v0.2.1 둘 다 `approved: false`**(결정 문서 12.8 — 사람 승인 대기). 승인을
  바꾸는 API 는 없다.

### ② Reference 기반 시작 — `POST /api/centers/{center_id}/template-profiles`

```json
{ "base_template_ref": { "template_id": "ssuksak.monthly-template-a",
                         "template_version": "monthly-template-a-v0.2.1" },
  "selected_optional_keys": ["focus", "goals"],
  "display_labels": { "theme": "생활주제", "week_axis": "주", "outdoor_play": "바깥놀이",
                      "safety_education": "안전교육", "focus": "소주제", "goals": "목표" },
  "focus_variant": "SUBTHEME" }
```

```
base_template_ref        필수.  ① 의 template_ref
selected_optional_keys   문자열 배열.  기본 [].  ① 의 OPTIONAL 만 (focus · goals · basic_habit).  중복 불가.
                         event_schedule · drill 은 422
display_labels           {section_key: 표시 이름}.  **REQUIRED 칸 넷과 고른 칸 전부에 필요하다.**
                         그 밖의 키 · 빈 이름은 422 (Core: 보이는 칸은 표시 이름을 직접 받는다)
focus_variant            focus 를 고르면 필수 (focus_variants 중 하나).  안 고르면 null
```

**Response** `201` — §9-2 READY 목록 항목과 같은 모양(`profile_ref` · `status: "READY"` ·
`base_template_ref` · `selected_optional_keys` · `sections` · `created_at`).

- 결과는 **원 소유 READY v1** 이다. 반 전용이 아니다(`classroom_ref` 없음). 만든 계정이 남는다.
- **원 기본을 걸지 않는다.** 「앞으로 기관 기본으로 사용」에 동의할 때만 ③ 을 따로 부른다(C2.6).
- **멱등이 아니다.** 같은 요청을 두 번 보내면 Profile 이 두 개 생긴다(Idempotency-Key 없음).
  화면은 응답이 올 때까지 버튼을 잠근다.
- 실패하면 아무것도 저장하지 않는다.
- **운영:** 기반 Template 사람 승인 전에는 항상 `409 GATE_BLOCKED` 다(결정 문서 12.8 · 12.12). 승인
  우회 경로는 없다. 승인되면 코드 변경 없이 열린다.

### ③ 원 기본 — `GET · PUT /api/centers/{center_id}/template-profile-default`

**GET** `200`

```json
{ "profile_ref": { "profile_id": "tprofile_3f2a…", "profile_version": "v1" },
  "changed_by": 7, "changed_at": "2026-10-10T10:00:00+09:00" }
```

기본이 없으면 세 칸 모두 `null`. **포인터 그대로다** — 이 반에 실제로 무엇이 쓰이는지는 §9-2 해석이
준다(override 가 먼저다).

**PUT** — 지정

```json
{ "profile_ref": { "profile_id": "tprofile_9b1c…", "profile_version": "v1" },
  "expected_profile_ref": { "profile_id": "tprofile_3f2a…", "profile_version": "v1" } }
```

**PUT** — 해제

```json
{ "profile_ref": null,
  "expected_profile_ref": { "profile_id": "tprofile_9b1c…", "profile_version": "v1" } }
```

```
profile_ref            필수 키 (null 이라도 보낸다).  값이 있으면 지정, null 이면 해제.
                       내 원의 READY 버전만 — DRAFT · ARCHIVED · 남의 원 것은 404
expected_profile_ref   필수 키.  화면이 GET 으로 본 지금 값.  기본이 없었으면 null.
                       해제할 때 null 이면 422 (무엇을 지우는지 모른다)
```

- **Response** `200` — GET 과 같은 모양(바뀐 뒤 값). 해제하면 세 칸 모두 `null`.
- **비교와 저장이 한 번에 일어난다(CAS).** `expected_profile_ref` 가 지금 포인터와 다르면 아무것도
  바꾸지 않고 `409 STALE_WRITE` 다. 같은 `expected` 로 두 요청이 동시에 와도 하나만 저장된다. 화면은
  GET 으로 다시 읽어 보여 주고 다시 하게 한다.
- 새 READY 가 생겨도 포인터는 움직이지 않는다(C2.6).

### ④ 반 override — `GET · PUT /api/classes/{class_id}/template-profile-override`

- 요청 · 응답 · CAS 는 ③ 과 같다. 남의 원 반이면 `404 ["class_id"]`.
- §9-2 해석에서 **원 기본보다 먼저다**(R1). 해제하면 원 기본으로, 원 기본도 없으면
  `SELECTION_REQUIRED` 로 돌아간다.
- GET 은 대상을 못 쓰게 된 포인터(R3 — §9-2 가 `profile_ref: null` 로 숨기는 경우)도 그대로
  보여 준다. 해제할 때 `expected_profile_ref` 로 이 값을 쓴다.

### 오류 — §9-4 공통

| code | status | 언제 | `fields` |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | 로그인 안 함 | `[]` |
| `VALIDATION_FAILED` | 422 | 입력 모양 · 고를 수 없는 칸(`event_schedule` · `drill` 포함) · 중복 | `["selected_optional_keys"]` 등 |
| `VALIDATION_FAILED` | 422 | 표시 이름이 빠짐 · 빈 이름 · 고르지 않은 칸의 이름 | `["display_labels.goals", …]` (빠진 칸 전부) |
| `VALIDATION_FAILED` | 422 | focus 를 골랐는데 `focus_variant` 가 없거나 목록 밖 · focus 없이 값이 있음 | `["focus_variant"]` |
| `VALIDATION_FAILED` | 422 | 해제인데 `expected_profile_ref` 가 null · 키가 빠짐 | `["expected_profile_ref"]` |
| `NOT_FOUND` | 404 | 남의 원 | `["center_id"]` |
| `NOT_FOUND` | 404 | 없는 반 · 남의 원 반 | `["class_id"]` |
| `NOT_FOUND` | 404 | 기반 Template 이 없다 | `["base_template_ref"]` |
| `NOT_FOUND` | 404 | 가리킬 Profile 이 없다 · READY 가 아니다(DRAFT · ARCHIVED) · 남의 원 것이다 (셋을 가르지 않는다) | `["profile_ref"]` |
| `GATE_BLOCKED` | 409 | 기반 Template 이 사람 승인 전이다 | `["base_template_ref"]` |
| `STALE_WRITE` | 409 | `expected_profile_ref` 가 지금 포인터와 다르다 | `["expected_profile_ref"]` |

### 연간 → 월간 Gate 와의 관계

- **포인터를 걸어도 월간계획안이 생기지 않는다.** §9-1 생성은 여전히 그 반의 연간계획안이 확정돼 있어야
  한다(`409 GATE_BLOCKED ["class_id"]`). 두 조건은 따로 본다.
- §9-1 은 화면이 보여 준 **정확한 `profile_ref`** 를 받는다(R5). 포인터를 나중에 바꿔도 이미 만든
  월간계획안의 `profile_ref` 는 그대로다.
- 생성 직전에도 기반 Template 승인을 다시 본다(§9-1 — 승인 전이면 생성도 막힌다).

### 아직 없는 것

DRAFT 만들기 · 임시 저장 · 편집, READY 전환, READY 에서 새 버전 파생, 보관(ARCHIVED). M2 저장소에는
있다(결정 문서 C2.0 · M2-B). 화면에 필요해지면 계약을 따로 정한다.

---

## 9-5. 월간계획안 변경 이력 — `GET /api/plans/monthly/{id}/audit`

> **상태: 구현됨 (BE-2).** 저장돼 있던 이력(M3 `plans.body` 의 Core `AuditHistory`)을 읽어 주는
> **조회 전용** API 다. 새 테이블 · Migration · Core 변경이 없다. 이력은 §9-1 생성과 §9-3 편집 ·
> 재생성 · 확정이 쌓는다.

### 요청

```
GET /api/plans/monthly/{id}/audit
GET /api/plans/monthly/{id}/audit?item_id=item_7c1e…
```

```
id        정수.  필수.  §9-1 의 id
item_id   문자열.  선택.  주면 그 칸의 이력 + 계획안 단위 CONFIRMED 만 준다 (아래)
```

- **로그인 필수**(`401 UNAUTHENTICATED`). 인가는 원 단위다 — 없는 id · 남의 원 계획안 · 월간이
  아닌(연간) id 는 모두 같은 `404 ["id"]` 다. 셋을 가르지 않는다.
- **읽기만 한다.** 이력을 더하지 않고 계획안 본문 · `revision` · `updated_at` · 상태 · 칸 값을 바꾸지
  않는다.

### 응답 `200`

```json
{ "items": [
    { "type": "CREATED", "occurred_at": "2026-09-20T01:00:00Z",
      "scope": "PLAN", "item_id": null, "section_key": null, "week_id": null,
      "actor": null, "system_actor": "monthly_application",
      "value_change": null, "generation_change": null },
    { "type": "TEACHER_EDITED", "occurred_at": "2026-09-21T02:10:00Z",
      "scope": "CELL", "item_id": "item_7c1e…", "section_key": "focus", "week_id": "2026-09-W2",
      "actor": "user_7", "system_actor": null,
      "value_change": { "before": "가을 열매 관찰", "after": "가을 열매를 모아 세어 보기" },
      "generation_change": null },
    { "type": "REGENERATED", "occurred_at": "2026-09-21T02:20:00Z",
      "scope": "CELL", "item_id": "item_9a2b…", "section_key": "outdoor_play", "week_id": "2026-09-W3",
      "actor": "user_7", "system_actor": null,
      "value_change": { "before": "…", "after": "…" },
      "generation_change": {
        "before": { "method": "RULE_LLM", "rule_id": "monthly.llm.validated_proposal",
                    "rule_version": "monthly-planner-…" },
        "after":  { "method": "RULE_LLM", "rule_id": "monthly.llm.validated_proposal",
                    "rule_version": "monthly-cell-planner-v10" } } },
    { "type": "CONFIRMED", "occurred_at": "2026-09-22T05:00:00Z",
      "scope": "PLAN", "item_id": null, "section_key": null, "week_id": null,
      "actor": "user_7", "system_actor": null,
      "value_change": null, "generation_change": null }
] }
```

값의 모양(`item_id` · `rule_version` · 시각)은 예시다. **모든 키가 항상 온다** — 해당이 없으면 `null`.

```
type               CREATED | TEACHER_EDITED | REGENERATED | CONFIRMED.  저장된 그대로
occurred_at        ISO 8601.  저장된 시각 그대로 (시간대 포함)
scope              PLAN (계획안 단위) | CELL (칸 단위)
item_id            CELL 이면 그 칸 (§9-1 cells[].item_id).  PLAN 이면 null
section_key        CELL 이면 그 칸의 Section.  PLAN 이면 null
week_id            주마다 있는 칸(repeat_by WEEK)이면 그 주.  한 달 칸 · PLAN 이면 null
actor              사람이 한 일이면 opaque id (user_7).  시스템이면 null.  이름은 주지 않는다
system_actor       시스템이 한 일(생성)이면 그 표시 (monthly_application).  사람이면 null
value_change       TEACHER_EDITED · REGENERATED 만.  {before, after} — 그때 바뀐 칸 값.  나머지는 null
generation_change  REGENERATED 만.  {before, after} — 각각 §9-1 cells[].generation 과 같은 모양
                   (method · rule_id · rule_version).  나머지는 null
```

**어디에 무엇이 쌓이나**

| type | scope | 누가 | value_change | generation_change |
|---|---|---|---|---|
| `CREATED` | PLAN 1건 + 칸마다 1건 | `system_actor` | null | null |
| `TEACHER_EDITED` | CELL | `actor` | 있음 | null (교사 수정은 생성 방식을 바꾸지 않는다) |
| `REGENERATED` | CELL | `actor` | 있음 | 있음 |
| `CONFIRMED` | PLAN | `actor` | null | null |

- **성공한 변경만 남는다.** 같은 값 편집(422) · 오래된 revision(409) · 확정 뒤 편집(409) · 실패한
  재생성(500 · 503)은 이력을 더하지 않는다. 확정 재호출(§9-3 정책 B)도 이력을 더하지 않는다.

### 순서

`occurred_at` 오름차순. 시각이 같으면 ① 계획안 단위 → ② 칸 단위, 칸끼리는 §9-1 `sections[].cells[]`
순서, 한 칸 안에서는 저장된 순서다. 같은 데이터는 언제 읽어도 같은 순서다(생성 때는 계획안과 모든 칸의
`CREATED` 가 같은 시각이라 이 규칙이 순서를 정한다).

### `item_id` 로 고르기

- 그 칸의 이력 전부 + **계획안 단위 `CONFIRMED`**(확정됐을 때만) 를 같은 순서 규칙으로 준다
  (screen-spec §6.3 「해당 Item 의 전체 Audit Event 와 현재 Plan 에 적용되는 Plan-level `CONFIRMED`」).
- 계획안 단위 `CREATED` 와 다른 칸의 이력은 주지 않는다. 확정 전이면 `CONFIRMED` 가 없다.
- 이 계획안에 없는 칸이면 `404 ["item_id"]` (남의 계획안 칸 id 도 같다).

### 주지 않는 것

- **재생성 전 근거(evidence).** 저장돼 있지 않다 — `REGENERATED` 는 값과 생성 방식의 변화만 갖는다.
  지금 근거는 §9-1 `cells[].evidence` 이고, 그것을 과거 근거로 보이면 안 된다. 남기려면 Core 계약
  확장이 필요하다(후속).
- **이벤트별 `revision`.** 저장돼 있지 않아 계산해 만들지 않는다. 지금 revision 은 §9-1 응답에 있다.
- **사람 이름.** `actor` 는 opaque id 뿐이다(screen-spec §9).
- **Pagination.** 없다 — 계획안 하나의 이력은 칸 수와 변경 횟수만큼이다(연간 §9 Audit 과 같다).

### 오류

| code | status | 언제 | `fields` |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | 로그인 안 함 | `[]` |
| `NOT_FOUND` | 404 | 없거나 남의 원 계획안 · 월간이 아님 | `["id"]` |
| `NOT_FOUND` | 404 | `item_id` 칸이 이 계획안에 없다 | `["item_id"]` |

### 연간 `GET /api/plans/annual/{id}/audit` 과의 차이

연간 계약은 그대로다. 월간은 같은 키(`type` · `occurred_at` · `actor` · `system_actor`)를 쓰고,
연간의 `month` 대신 `scope` · `item_id` · `section_key` · `week_id` 로 칸을 가리키며, 연간에 없는
`value_change` · `generation_change` 를 더 준다. 연간에는 `item_id` 고르기가 없다.

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

**`child_id` 는 `class_id` 반의 아이여야 한다.** 같은 원의 다른 반 아이면 `VALIDATION_FAILED` 422,
`fields: ["child_id"]`. 없는 반·아이와 남의 원 반·아이는 `NOT_FOUND` 404 다(「인증」).

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

## 10-1. 일과 기록 — `POST · GET · PUT · DELETE /api/routines`   ★ 9주차

**일일 보육일지의 사실 층이다.** 반 하루의 일과 한 줄 = 기록 하나다. §11 일일 보육일지가 이 기록을
`sources` 로 인용한다 — 관찰 기록(§10)이 관찰일지의 근거인 것과 같은 모양이다 (ADR-024 · ADR-025).

**생성 엔드포인트가 없다.** 활동실행은 있었던 일이라 AI 가 쓰면 위조다. 교사가 적은 그대로 저장한다.

**Request** `POST /api/routines`

```json
{ "class_id": 1, "date": "2026-10-06", "position": 2,
  "start": "09:20", "end": "10:40", "name": "오전 실내놀이",
  "plan": "자동차 굴리기", "execution": "블록 3개로 길을 만들었다." }
```

**Response** `201` — 위 값 + `id` · `class_name` · `created_at`.

```
name        일과 이름.  필수 · 50자.  원마다 달라 교사가 적는다 (「오전 실내놀이」 「특별활동(체육)」)
position    하루 안의 표시 순서.  0 이상.  기본 0
start/end   선택.  둘 다 있으면 start < end
plan        활동계획.  선택
execution   활동실행 — 사실 층.  선택(저장은 비어도 된다).  일지의 근거가 되려면 있어야 한다
```

- **행 수를 고정하지 않는다.** [실측] 같은 반도 특별활동이 있는 날은 행이 하나 더 있다 (ADR-024)
- **`PUT` 은 통째로 바꾼다.** `date` · `position` · `start` · `end` · `name` · `plan` · `execution`.
  `class_id` 를 보내면 422 — 반이 바뀌면 다른 기록이다. 시간을 안 보내면 지워진다
- **`GET /api/routines?class_id=&from=&to=`** 셋 다 선택. 정렬은 **날짜 오름차순, 하루 안에서는
  `position` · `start` · `id` 순**이다 — 종이의 행 순서다
- 남의 원 반 · 기록은 404 다

**기록을 고치면 그걸 쓴 일일 보육일지가 `stale` 이 된다.** 일지는 근거 사본으로
`[오전 실내놀이 09:20~10:40] 활동실행` 한 줄을 남기고 그 줄과 비교한다. 그래서 **일과 이름 · 시간 ·
활동실행 · 날짜** 중 무엇이 바뀌어도 `stale` 이고, `plan` · `position` 만 바꾸면 그대로다.
지우면 「원본 없음」이라 `stale` 이다.

### 일일 보육일지를 만들 때 (§11)

```json
POST /api/documents
{ "kind": "dailyLog", "class_id": 1, "start": "2026-10-06", "end": "2026-10-06",
  "source_ids": [31, 32, 35] }
```

- `source_ids` 는 **일과 기록 id** 다. 관찰 기록 id 가 아니다
- `사실` 은 고른 순서대로 `[일과 이름 시간] 활동실행` 을 빈 줄로 잇는다
- 거절(`VALIDATION_FAILED` 422, `fields: ["sources.{id}"]`): 없거나 남의 원 · 다른 반 · **다른 날** ·
  **활동실행이 비었다**
- **`child_id` 를 받지 않는다** — 반 단위다. 보내면 422 `fields: ["child_id"]`
- `refresh` 는 일과 기록을 다시 떠서 사실을 다시 잇는다. 활동실행을 비웠거나 다른 날로 옮겼으면 원본 없음과 같이 409 다

## 11. 문서 — `/api/documents`   ★ 7주차

**§10 의 기록을 모아 초안을 만든다.** 일지 계열 4종이다.

```
dailyLog     일일 보육일지    반 단위    하루     종이 한 장 = 반 1개 × 하루 × 일과 격자
weeklyLog    주간 보육일지    반 단위    한 주
observation  관찰일지        아동 단위   기간     종이 한 장 = 아이 1명 × 기간 × 5영역
assessment   영유아 평가      아동 단위   기간
```

**문서 1개가 교사가 제출하는 종이 1장이다.** 종이 위 배치는 아래 「종이 한 장」에 적었다. `weeklyLog` · `assessment` 의 배치는 이번 개정 범위 밖이다.

**계획안(`annual` · `monthly`)은 이 엔드포인트가 아니다.** §4 ~ §7 이 다룬다.
같은 「문서」라는 말을 쓰지만 근거가 다르다 — 계획안은 참조자료에서, 일지는 교사 기록에서 나온다.

**`assessment`(영유아 평가) 문서와 「평가제 대조」는 다른 것이다.** 전자는 여기서 만드는 문서고,
후자는 기관 평가 지표에 문서를 대보는 기능이다(§12). 평가제 대조의 지표 4-2 가 확정된 `assessment` 문서를 센다.

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
    { "id": 12, "date": "2026-09-22", "domain": "자연탐구", "text": "...", "class_id": 1, "child_id": 5 }
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

### 종이 한 장 — 3층은 화면에서 나누고 종이에서 합친다

**[실측] 모은 실물 일지에는 해석 칸과 지원 칸이 따로 없다.** 둘이 한 칸에 같이 들어간다(ADR-024).

```
양식          ① 사실 칸                ②③ 해석 + 지원 칸
일일 보육일지   일과 행마다 「활동실행」     놀이 평가 및 다음날 지원계획
관찰기록       영역 행마다 「관찰내용」     평가
```

**`sections` 는 그대로 사실 · 해석 · 지원 셋이다.** 검사(3단 게이트)와 교사 확인 3개는 셋을 나눈 채로 한다.
**합치는 것은 내보낼 때뿐이다** — 아래 「내보내기」.

#### 관찰일지 — 아이 1명 × 기간 × 5영역

```
머리   관찰기간 · 이름 · 기록자 · 결재란
본문   신체운동·건강 | (날짜) 관찰내용
       의사소통      | (날짜) 관찰내용
       사회관계      | (날짜) 관찰내용
       예술경험      | (날짜) 관찰내용
       자연탐구      | (날짜) 관찰내용
꼬리   평가          | 해석 + 지원
```

- **영역 행은 `sources[].domain` 으로 서버가 나눈다.** 모델이 배치하지 않는다. 그래서 `observation` 의 `sources` 는 `domain` 을 같이 준다.
- **순서는 위 5영역 고정이다.** 한 영역 안에서는 `date` 오름차순, 기록마다 `(9/22)` 를 앞에 붙인다.
- **기록이 없는 영역은 빈 칸으로 둔다. 막지 않는다.** 화면이 「이 영역 관찰이 없어요」로 알린다. [판단]
- **양식의 성별 · 생년월일 칸은 비운다.** 우리는 받지 않는다(CLAUDE.md 개인정보).
- 실물 양식에는 「기본생활습관」 행이 하나 더 있다. §10 `domain` 에 없어서 비워 둔다 — 다음 개정.

#### 일일 보육일지 — 반 1개 × 하루 × 일과 격자

```
머리   날짜 · 요일 · 반 · 결재란
       주제 · 소주제
본문   시간 | 일과 | 활동계획 | 활동실행      ← 행 수 고정 안 함
꼬리   놀이 평가 및 다음날 지원계획          ← 해석 + 지원
```

- **근거는 관찰 기록이 아니라 「일과 기록」이다.** 교사가 일과 행마다 적은 활동실행이 사실 층이다. 테이블과 API 는 §10-1 이다.
- **일과 행 수를 고정하지 않는다.** [실측] 같은 반도 특별활동이 있는 날은 행이 하나 더 있고, 같은 일과도 날에 따라 끝나는 시간이 다르다.
- **시간 · 일과 · 활동계획은 교사 입력을 그대로 싣는다.** 모델이 채우지 않는다.

### `source_ids` 가 가리키는 것은 `kind` 마다 다르다

```
dailyLog      일과 기록 id           §10-1            ← 관찰 기록이 아니다
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
근거가 일과 기록일 때    활동실행 · 시간 · 일과 · date · class_id
근거가 문서일 때         사실 항목 · class_id · child_id · start · status
근거가 사라졌을 때       "원본 없음"
```

**`stale` 이면 확정할 수 없다.** `POST .../confirm` 이 `GATE_BLOCKED` 409 를 낸다.
**문서를 지우지 않는다** — 교사가 보고 판단한다.

**푸는 길은 `POST /api/documents/{id}/refresh` 하나다.** 교사가 「바뀐 원본을 보고 다시 검토하겠다」고 누른다.

```
1  근거 사본을 지금 원본으로 다시 뜬다        관찰 기록이면 fact · date,  문서면 사실 · start · status
2  사실 항목을 새 사본으로 다시 잇는다
3  stale = false
```

- **`해석` · `지원` 은 건드리지 않는다.** 새 사실에 맞는지는 교사가 보고 `PUT` 으로 고친 뒤 확정 체크 3개로 확인한다. 모델을 부르지 않는다
- **초안에서만 된다.** 확정본은 `ALREADY_CONFIRMED` 409 — 먼저 `unconfirm` 한다. 확정본의 사실이 조용히 바뀌면 교사가 확인한 것과 저장된 것이 달라진다
- **원본이 하나라도 사라졌으면 `GATE_BLOCKED` 409.** `fields` 에 `sources.{id}`. 빼고 이으면 교사가 고른 근거가 조용히 줄어든다 — 지우고 새로 만든다
- **근거 일일 보육일지가 초안이면 `GATE_BLOCKED` 409.** 만들 때와 같은 규칙이다

### 상태와 출처

```
status   DRAFT ⇄ CONFIRMED          확정은 confirm,  되돌리기는 unconfirm
origin   AI                         LLM 이 초안을 만들었다
         TEACHER                    교사가 직접 썼다
         TEMPLATE                   기관 양식에서 뼈대만 만들었다 (§8)
         IMPORT                     교사가 기존 문서를 올렸다
```

**`CONFIRMED` 를 수정하면 `ALREADY_CONFIRMED` 409 다.** 고치려면 먼저 되돌린다.

**되돌리기 — `POST /api/documents/{id}/unconfirm`**  CONFIRMED → DRAFT.  body 없음

- **이 문서를 근거로 쓴 문서는 전부 `stale` 이 된다** (연쇄). 주간 보육일지는 확정된 일일 보육일지만 받는다 — 근거가 초안으로 돌아가면 그 위에 쌓은 것도 다시 봐야 한다
- **다시 불러도 200 이다.** 확정과 같은 이유 — 재시도를 진짜 실패와 구분할 수 없다
- 되돌린 문서 자신의 `stale` 은 바꾸지 않는다. 바뀐 것은 상태지 근거가 아니다

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
               해석의 숫자 ⊂ 사실의 숫자
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
       정렬은 created_at 내림차순, 같은 시각은 id 내림차순이다 — 최신이 위다.
       FE 가 서버 순서를 그대로 쓰므로 계약에 둔다. 목록에는 sections · sources 를 담지 않는다.
GET    /api/documents/{id}                                       단건
GET    /api/documents/{id}/related                               겹치는 확정 문서
POST   /api/documents/{id}/verify                                3단 LLM Judge
PUT    /api/documents/{id}                                       title · sections · review_note
POST   /api/documents/{id}/confirm                               DRAFT → CONFIRMED.  checks 3개 필요
POST   /api/documents/{id}/unconfirm                             CONFIRMED → DRAFT.  근거로 쓴 문서 stale
POST   /api/documents/{id}/refresh                               근거 다시 뜨기 · stale 해제.  초안만
DELETE /api/documents/{id}                                       204
GET    /api/documents/{id}/export/hwp                            hwpx 파일.  확정본만.  아래 「내보내기」
```

**확정된 문서는 `PUT` · `DELETE` 둘 다 `ALREADY_CONFIRMED` 409 다.**
고칠 수 없는 문서를 지울 수 있으면 확정이 의미가 없다.

**해석에 사실에 없는 숫자가 있으면 `sections.해석` 으로 거절한다.**
지원은 앞으로의 계획이라 새 숫자가 나와도 된다.

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

**DRAFT 는 빼고 준다.** 아직 쓰는 중인 글을 "안 맞는다"고 들이밀면 방해다.
**모델을 부르지 않는다** — 겹치는 문서를 찾아 보여줄 뿐 무엇이 맞는지는 판정하지 않는다.

**문서 조회는 교사의 원으로 걸린다.** 목록·단건·`related` 모두 같다. 이게 없으면
로그인한 아무 교사나 남의 원 문서를 **아동 실명까지** 받아간다(ADR-004).

### 내보내기 — `GET /api/documents/{id}/export/hwp`

**§9 계획안 내보내기와 같은 규칙이다.** JSON 이 아니라 파일이 내려온다 · 경로는 `hwp` 인데 파일은 `hwpx` 다 ·
확정본만 · 출처를 싣지 않는다 · 작성자 정보를 지운다.

```
응답 200    Content-Type: application/hwp+zip
            Content-Disposition: attachment; filename="document-7.hwpx";
                                 filename*=UTF-8''<한글 이름>.hwpx
```

**배치는 위 「종이 한 장」이다.** 해석 + 지원 칸은 `해석` 본문, 빈 줄, `지원` 본문 순서로 잇는다.
「해석:」「지원:」 같은 머리말을 붙이지 않는다 — 실물 양식에도 없다.

**`source_ids` · `evidence` · `generation` 을 한 글자도 싣지 않는다.** 제출 문서다.

**아동 실명이 들어간다.** 교사 본인의 제출 문서라 치환하지 않는다. 대신 hwpx 안의
미리보기(`Preview/PrvText.txt`)를 **이 문서 내용으로 다시 만든다** — 양식 파일에 남은
다른 아이 이름이 미리보기에 그대로 실려 나가지 않게 한다.

| code | status | 언제 |
|---|---|---|
| `GATE_BLOCKED` | 409 | 확정 전이다 |
| `VALIDATION_FAILED` | 422 | `dailyLog` · `observation` 이 아니다.  `fields: ["kind"]` |
| `NOT_FOUND` | 404 | 없거나 남의 원 문서다 |

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

## 12. 평가제 대조 — `GET /api/centers/{center_id}/evaluation-checklist`   ★ 8주차

**응답에 지표 9개가 온다 — 자동 2 · 자기 점검 7. 평가자가 현장에서 보는 6개(1-1·1-2·2-1·2-2·3-1·3-2)는 넣지 않는다.**
PM 결정(2026-10-01)이다([ADR-022](adr/022-evaluation-checklist-auto-and-self-check.md)).

**원이 만든 문서를 평가인증 지표에 대보고 빈 칸을 보여준다.** 원장이 평가 준비에 쓴다.
문서 5분류의 **대조형**이다 — 누락 탐지만 한다(CLAUDE.md). 자기 점검은 교사가 평가요소마다 체크한다.

**LLM 을 쓰지 않는다.** 문서 종류 · 개수 · 기간으로만 판정한다. 모델이 「충족한 것 같다」고 하면
원장이 그걸 믿고 평가에 들어간다.

지표는 「2025 어린이집 평가 자체평가 보고서 서식」의 **영역 6개 · 지표 15개**다.
**개정 전(2024.7.2까지 적용, 4영역 · 18지표) 지표와 섞지 않는다** — 번호가 충돌한다.
지금 쓰는 2024 개정판(2024.7.3 시행)은 2025 · 2026판과 번호가 같다.
**이 문서의 「지표」 = 공식 「평가항목」(15개). 자기 점검의 체크 단위는 공식 「평가요소」다.**
지표 원문은 `backend/resources/evaluation/daycare_evaluation_indicators_v1.json` 에 있다.
지표별 판정 규칙은 별도 데이터 파일로 둔다(코드에 쓰지 않는다). **판정 규칙 · 체크 상태를 지표 파일에 섞지 않는다**(ADR-019).

출처는 한국영유아보육·교육진흥원(옛 한국보육진흥원)의
[「2024 개정 어린이집 평가 매뉴얼(2025. 2.)」 진흥원-2025-140](https://www.kicece.or.kr/kcpi/cyberpr/childcarecentaccred1/detail.do?colContentsSeq=74226),
2026.2판 매뉴얼(colContentsSeq=81485), 「2024 개정 어린이집 평가 자체평가 안내서(2025. 2.)」(colContentsSeq=74265) ·
hwp 서식(2025-03-17, childcarecentaccred2 colContentsSeq=74625),
[묻고 답하기 사례](https://www.kicece.or.kr/kcpi/community/answer/faq/dccFaqList.do)다.
**2026.2판이 최신이다. 4-1 · 4-2 본문은 2025판과 같다.** 현장평가는 관찰 · 기록(문서) 검토 · 면담을 함께 쓴다(p.29 · p.45).
2024.7 이후 현장평가 결과는 영역별 서술형이고 점수 · 등급이 없다. 자체평가는 5점 척도다.

```
AUTO         4-1 · 4-2                         확정 문서를 센다
SELF_CHECK   5-1 · 5-2 · 5-3 · 6-1 · 6-2 · 6-3 · 6-4   교사가 평가요소마다 체크한다
제외         1-1 · 1-2 · 2-1 · 2-2 · 3-1 · 3-2   응답에 넣지 않는다
```

**이 절은 응답 모양의 계약이다.** 자기 점검 평가요소 원문은 지표 파일 v2 가 정한다(아래 「아직 정하지 않은 것」).
FE 는 이 모양으로 목업을 먼저 붙인다.

**Request** — 파라미터가 없다. 최상위 `school_year` 는 SELF_CHECK 의 학년도다.
서버가 요청 시각으로 정한다(`school_year_of`, §2 와 같다). AUTO 는 아래 공식 검토 기간을 쓴다.
`?school_year=` · `?class_id=` 는 받지 않는다 — 필요해지면 **추가**한다. 응답이 바뀌지 않는다.

**Response** `200` — **9개 중 일부를 보인 예시다.** `items` 는 지표 파일 순서다.
SELF_CHECK 의 평가요소도 일부만 보인다. 6-3 의 실제 평가요소는 3개다.

```json
{ "school_year": 2026,
  "items": [
    { "indicator": "4-1", "area": "…", "title": "…", "content": "평가내용 원문",
      "kind": "AUTO", "verdict": "INSUFFICIENT", "required": null, "count": 3,
      "children": null, "classes": { "met": 1, "total": 2 },
      "plan_ids": [4], "document_ids": [9, 15],
      "period": { "from": "2026-09-01", "to": "2026-10-02" } },
    { "indicator": "4-2", "area": "…", "title": "…", "content": "평가내용 원문",
      "kind": "AUTO", "verdict": "INSUFFICIENT", "required": 2, "count": 4,
      "children": { "met": 2, "total": 3 }, "classes": null,
      "plan_ids": [], "document_ids": [7, 8, 11, 12],
      "period": { "from": "2025-10-01", "to": "2026-10-02" } },
    { "indicator": "6-3", "area": "…", "title": "…", "content": "평가내용 원문",
      "kind": "SELF_CHECK",
      "elements": [
        { "element": "6-3-1", "text": "…", "checked": true,
          "checked_at": "2026-10-01T10:00:00+09:00" },
        { "element": "6-3-2", "text": "…", "checked": false, "checked_at": null } ],
      "progress": { "checked": 1, "total": 3 }, "complete": false } ] }
```

**숫자는 응답 모양을 보이는 예시다. 실제 기간 집계가 아니다.** 평가요소 원문은 `…` 로 둔다.

**공통 · AUTO 필드** — `indicator` · `area` · `title` · `content` · `kind` 는 두 종류에 공통이다.
나머지는 AUTO 에만 있다.

| 필드 | 타입 | |
|---|---|---|
| `indicator` | `string` | 지표 번호(`"4-2"`). 키다. `items` 는 지표 파일 순서(서식 순서)다. **지표 9개가 늘 온다** |
| `area` · `title` · `content` | `string` | 영역 · 지표 제목 · 평가내용. **서식 원문 그대로다** — 요약하지 않는다 |
| `kind` | `string` | `AUTO` \| `SELF_CHECK` |
| `verdict` | `string` | AUTO 의 판정. 아래 셋 중 하나 |
| `required` | `int \| null` | **아동 단위 지표(4-2)의 한 명당 기준 건수**다. **4-1 은 반마다 「계획안 1건 + 평일마다 일지」라 숫자 하나로 적지 못해 `null` 이다** |
| `count` | `int` | 센 문서 수다. **`count` = `plan_ids` 길이 + `document_ids` 길이**다. 4-1 일지는 평일 · 주말 · 같은 날 여러 건을 모두 센다. 4-2 는 `total` 에 든 모든 아동의 센 평가 문서 수의 합이다 |
| `children` | `{ met: int, total: int } \| null` | **아동 단위 지표만** 값이 있다. `total` = 이 원의 **오늘 학년도 반에 등록된 아동 수**(`children` 행. 반의 `child_count` 가 아니다). `met` = 그중 기준을 채운 아이 수. 나머지는 `null` |
| `classes` | `{ met: int, total: int } \| null` | **반 단위 지표만** 값이 있다(4-1). `total` = 이 원의 **오늘 학년도 반 수**(`classes.school_year`). `met` = 그중 기준을 채운 반 수. 나머지는 `null` |
| `plan_ids` | `int[]` | 센 계획안의 id. 계획안을 세지 않는 지표는 `[]` 다. `document_ids` 에 섞지 않는다(ADR-019) |
| `document_ids` | `int[]` | 4-1 은 기간 안 `total` 에 든 모든 반의 확정 일일 보육일지 id 다(평일 · 주말 · 같은 날 여러 건 모두 포함). 4-2 는 `total` 에 든 모든 아동의 센 평가 문서 id 다(§11). 화면이 「근거 보기」로 연다 |
| `period` | `{ from: string, to: string }` | AUTO 의 검토 기간. `from` · `to` 는 ISO 날짜다. 화면이 「9/1~10/2 기준」을 그린다 |

**SELF_CHECK 필드** — 위 공통 필드에 아래 필드를 더한다. **`verdict` 는 없다.**
지표 목록(`items`) 안에 같은 이름이 또 있으면 헷갈린다. 공식 용어 「평가요소」(element)에 맞춘다.

| 필드 | 타입 | |
|---|---|---|
| `elements` | `array` | 이 지표의 평가요소 목록. 지표 파일 v2 가 정한다 |
| `elements[].element` | `string` | 평가요소 키(`"{지표}-{순번}"`, 예: `"6-3-1"`). 지표 파일 v2 가 정한다 |
| `elements[].text` | `string` | 평가요소 원문. 예시는 `…` 로 둔다 |
| `elements[].checked` | `bool` | 교사가 체크했는지다 |
| `elements[].checked_at` | `string \| null` | 체크 시각(ISO 8601) — ☐ 에서 ☑ 로 바뀐 때다(아래 「체크 저장」). 미체크면 `null` 이다 |
| `progress` | `{ checked: int, total: int }` | 체크한 평가요소 수 · 전체 평가요소 수. **서버가 계산한다. 저장하지 않는다** |
| `complete` | `bool` | **`complete = (total > 0 and checked == total)`** 이다. 서버가 평가요소 체크로 계산한다. 저장하지 않는다. **평가요소가 아직 없는 지표(`total = 0`)는 완료가 아니다** — 지표 파일 v2 전에는 7개가 전부 이 상태다 |

**체크는 증빙이 아니라 교사의 자기 점검이다.** SELF_CHECK 를 `SUPPORTED`(충족)로 바꿔 내보내지 않는다.
원장이 「서류로 확인됐다」로 읽으면 ADR-019 가 막으려던 오해가 돌아온다.
**자기 점검에는 아동 정보가 없다.**

### AUTO — `verdict` 는 셋이다

```
SUPPORTED      충족        기준만큼 있다
INSUFFICIENT   부족        있지만 기준 미달
NONE           없음        뒷받침 문서가 0건
```

**`OUT_OF_SCOPE` 를 뺀다.** 현장에서 보는 6개는 응답에서 빠지고 나머지 7개는 자기 점검이 되어 이 값을 낼 지표가 없다.
쓰이지 않는 값을 두면 FE 가 그릴 상태가 하나 는다. #76 에서 넷으로 정한 이유는 「모르는 지표를 `NONE` 으로 내면
증빙 없음으로 읽힌다」였다. 이제 **응답에서 빼고 화면에 안내 한 줄**로 대신한다(ADR-022).

**판정**

```
반 · 아동 단위     count = 0                 → NONE
                  met < total               → INSUFFICIENT
                  met = total               → SUPPORTED
```

**위에서부터 순서대로 본다. 먼저 맞는 줄이 판정이다.**
**반 · 아동이 하나도 없으면(`total = 0`) `count = 0` 이라 `NONE` 이다. 0/0 을 충족으로 내지 않는다.**

반 · 아동 단위 지표의 `count` 는 **`total` 에 든 반 · 아이들의 계획안 · 문서만** 센다.
그래서 `count > 0` 이면 `total` 도 0 이 아니다.
**4-1 은 반마다 계획안 1건 이상과 평일마다 일지를 모두 채워야 `met` 에 든다. 4-2 는 아동마다 평가 2건 이상이어야 `met` 에 든다.**

**무엇을 세나**

- **`CONFIRMED` 만 센다.** `DRAFT` 는 교사가 쓰는 중이다 — 증빙이 아니다.
- **`CONFIRMED` 면 `origin` 이 무엇이든(IMPORT 포함), `stale` 이 켜져 있어도 센다.**
  IMPORT 는 교사가 기존 서류를 증빙으로 올리는 경로다(§11 「등록이 평가 통과를 뜻하지 않음」).
  파일럿 중 4-2 를 셀 수 있는 사실상 유일한 길이다. stale 도 평가 때 실제로 내는 확정 서류다.
- **기간은 공식 검토 기간을 「오늘 현장평가를 받는다면」으로 둔다(KST 날짜).**
  4-1 은 **지난달 1일 ~ 어제**(p.29 · p.169), 4-2 는 **12개월 전 그달 1일 ~ 어제**(p.169 · #343)다.
  오늘이 2026-10-03 이면 각각 2026-09-01 ~ 2026-10-02, 2025-10-01 ~ 2026-10-02 다.
  일지 · 평가 문서는 `end_date` 로 기간을 본다. 월간계획안은 대상 달로 본다.
  학년도로 세면 평가자가 보지 않는 옛 서류(3월 계획안)까지 세어 거짓 「충족」이 나온다.

### 4-1 — 반 단위다

**반마다 대상 달이 검토 기간에 걸친 확정 월간계획안 1건 이상 + 검토 기간의 평일마다 확정 일일 보육일지 1건 이상을 본다.**
계획안은 `plans` 의 `kind = monthly` · `status = CONFIRMED`, 일지는 `documents` 의 `kind = dailyLog` 다.
**반 충족은 검토 기간의 평일마다 그 반의 확정 일일 보육일지가 1건 이상 있는지로 본다(날짜 단위).** 같은 날 여러 건 · 주말 일지는 빠진 평일을 대신하지 못한다.
**`document_ids` · `count` 에는 기간 안의 그 반 확정 일일 보육일지를 모두 담는다** — 평일 · 주말 · 같은 날 여러 건을 포함한다.
**`count` = `plan_ids` 길이 + `document_ids` 길이**다.
**계획안은 기간에 걸친 달 중 1건 이상이면 된다 — 달마다 1건이 아니다.** 오늘이 1일이면 기간이 지난달뿐이라 이번 달 계획안은 세지 않는다.
평일은 월~금이다. **공휴일 · 방학은 아직 반영하지 않는다** — 달력 테이블(특일정보 API)을 만들기로 했지만 아직 없다.
생기면 공휴일을 뺀다(아래 「아직 정하지 않은 것」). 그 전까지는 실제보다 부족으로 보일 수 있다고 안내한다.

공식 검토 서류는 보육일지(놀이기록 포함), 월간 · 주간 · 일일 보육계획안 중 하나, 장애영유아의 개별화교육계획이다(p.169).
계획안은 반별로 한 종류가 수립되어 있는지 본다(#361). 보육일지는 매일 기록 · 관리한다(#358 · #359).
같은 일과로 도는 합반은 일지 1부다(#412). **관찰 기록에는 빈도 · 아동별 요건이 없다**(#356).
그래서 **관찰일지 수로 세지 않는다. 연간 보육계획안은 4-1 서류가 아니다** — 영역 5 검토문서다(p.171).

월간계획안의 대상 달은 `plans.target_month`(`YYYY-MM`) 칸에 있다 — `plans.body.target_month` 에서 꺼낸 값이다(결정 문서 12.6 PR-2 에서 추가).
**plans 소유(승석)의 조회 함수로 읽는다. feature 간 직접 import 하지 않는다.** 함수는 아직 없다(아래 「아직 정하지 않은 것」).
계획안 id 는 `plan_ids`, 일지 id 는 `document_ids` 로 낸다.
**3월 초에는 검토 기간이 지난 학년도에 걸친다. 반은 학년도마다 새 행이라 지난 학년도 반의 서류는 안 잡힌다.**

### 4-2 — 아동 단위다

**아동마다 검토 기간 안의 확정 `assessment`(영유아 평가, §11) 2건 이상을 센다. 문서 날짜는 `end_date` 다.**
**4-2 기간(12개월)은 늘 3월(학년도 경계)을 넘는다.**
아동은 오늘 학년도 반의 `children` 행으로 고른다(`children.total` 과 같다). 그 아동의 **`child_id` 로** 기간 안의 평가를 센다.
**문서의 `class_id` 는 보지 않는다** — 아동이 반을 옮겨도 같은 `child_id` 면 지난 반에서 쓴 평가도 잡힌다.
**새 학년도에 아동을 새 행으로 다시 등록하면 지난 학년도 평가는 다른 `child_id` 라 안 잡힌다.** 학년도를 잇는 키가 없다.
한 아이만 네 번 했다고 원이 충족되지 않는다. **개별 평가 부분만 센다. 「보육과정 운영 평가」는 세지 않는다** — 일지 · 면담으로 보고 건수 기준이 없다(#346 · #344).
관찰 기록(§10) 누적으로 세지 않는다 — 관찰은 평가의 재료이지 평가가 아니다.
「관찰 N건 = 평가 1회」는 근거 없는 숫자고, 평가를 하지 않은 원을 충족으로 보이게 한다.

공식 대상은 현장평가 당일 재원 · 입소 6개월 이상인 아동이다. 입소 6~12개월은 연 1회, 12개월 이상은 연 2회다(p.130 · #352).
검토 기간은 1년 이내다(p.169 · #343). 「12개월 전 그달 1일 ~ 어제」는 공식 예시(#343)와 같은 방식이라 정확히 12개월보다 며칠 길 수 있다. **우리는 입소일을 받지 않아 모든 재원 아동에게 2회를 요구한다**(CLAUDE.md 「아동에게서 이름만 받는다」).
**입소 6개월 미만(공식 평가 대상이 아니다)과 6~12개월(연 1회면 된다) 아이는 실제보다 부족으로 보일 수 있다고 화면에 안내한다.**
영유아 평가는 표준보육과정 기반으로 관찰 기록 · 놀이 결과물을 누적해 특성과 변화를 서술로 종합(총평)한다(p.120 · #342).
공식 문서도 「영유아 발달 평가 기록」이라는 말을 쓴다. 건강검진 발달선별검사(K-DST)와는 무관하다.

**4-2 와 ADR-007 의 문서 동일 여부는 PM 확인 대기다.** **PRD 47행 · ADR-007 이 「발달평가」를 스펙아웃했다.**
그것이 §11 의 `assessment` 와 같은 것인지 아직 확인하지 않았다.
뺀 이유는 「반기 문서라 파일럿 4주에 작성 시점이 오지 않는다」였고 영유아 평가도 연 2회라 같은 문서일 가능성이 커졌다.
**같다면 4-2 는 IMPORT 로만 셀 수 있다. 계약 모양은 바뀌지 않는다.**

**문서가 아직 거의 없어서 AUTO 결과가 대부분 `NONE` 이다. 정상이다** — 화면이 그 상태를 제대로 그리는지가 중요하다.

### SELF_CHECK — 평가요소마다 체크한다

**서류를 올리지 않는다. 화면은 지표별로 묶은 트리다.** 한 지표에 체크 하나를 두지 않는다. 평가요소를 모두 체크하면 지표가 「완료」다.
**지표 완료는 저장하지 않는다.** 서버가 평가요소 체크로 계산해 내려준다.

```
지표 6-3                 progress 1 / 3 · complete false
  elements
    ├─ element 6-3-1  …  checked true
    ├─ element 6-3-2  …  checked false
    └─ …                 나머지 평가요소는 예시에서 생략한다
```

**원 단위 하나다.** 그 원의 교사 누구나 체크한다. 같은 원의 교사가 같은 체크를 본다.
원 · 학년도 · 평가요소마다 체크를 저장하고 언제 체크했는지 남긴다. **누가 체크했는지는 남기지 않는다.**
**3월에 새 학년도면 빈 체크리스트다. 지난 학년도 기록은 남는다.** 최상위 `school_year` 는 이 학년도다.

**평가요소 원문을 나눈 목록은 아직 없다.** v1 의 `content` 는 한 덩어리 문장이다.
hwp 서식 기준 평가요소는 **19개 — 5-1:3 · 5-2:3 · 5-3:2 · 6-1:2 · 6-2:3 · 6-3:3 · 6-4:3**다.
`1 2 3 4 5` 는 자기 점검 7개에만 있다 — 5-1 · 5-2 · 6-2 · 6-3 · 6-4 는 두 번, 5-3 · 6-1 은 한 번이다.
공식 자체평가 서식은 평가요소별 5점 척도다. **우리는 체크(예/아니오, `checked: bool`)로 정했다(2026-10-03).**
평가 준비가 됐는지만 확인하는 기능이라 점수는 필요 없다.
**평가요소를 나눈 지표 파일 v2 는 승석(PM)에게 부탁한다.** 법정 고시 원문 · PM 승인 파일이라 우리가 고치지 않는다.

### 체크 저장 — `PUT /api/centers/{center_id}/evaluation-checklist/checks`

**Request**

```json
{ "checks": [ { "element": "6-3-1", "checked": true },
              { "element": "6-3-2", "checked": false } ] }
```

**여러 평가요소를 한 번에 바꾼다.** 화면이 지표 단위 「전체 체크」를 할 수 있다.
**올해 학년도(서버 계산)에 저장한다. 원 단위다.** 같은 원의 교사가 같은 체크를 본다.
**`checked_at` 은 ☐ 에서 ☑ 로 바뀐 시각이다.** 이미 체크된 평가요소를 다시 `true` 로 보내면 바뀌지 않는다(「전체 체크」).
**`checked: false` 면 체크를 푼다.** 응답의 `checked_at` 은 `null` 이다.
**풀었다가 다시 체크하면 새 시각이다.** 풀기 전 시각은 남기지 않는다 — 체크 시각은 평가에 쓰이지 않는다(ADR-022).

**Response** `200` — GET 과 같은 전체 응답이다. 지표 9개가 온다. **화면은 통째로 교체한다.**

**에러** — 공통 에러 봉투를 쓴다. 아래 401 · 404 는 GET · PUT 에 공통이다. 422 는 PUT 이 낸다.

| code | status | 언제 | `fields` |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | 토큰이 없거나 못 믿는다(§0) | `[]` |
| `NOT_FOUND` | 404 | 없는 원. **남의 원도 404 다**(ADR-017) | `["center_id"]` |
| `VALIDATION_FAILED` | 422 | 없는 `element`, AUTO 지표의 평가요소를 체크하려 한다, 같은 `element` 가 한 요청에 두 번 온다 | `["checks.6-3-9"]` 처럼 그 `element` |

**위치는 인덱스가 아니라 `element` 키로 가리킨다** — 「공통」의 「배열 원소는 의미 있는 키를 쓴다」(`months.3`)와 같다.
틀린 `element` 가 여럿이면 전부 담는다. **하나라도 틀리면 아무것도 저장하지 않는다.**

**UI states**

**안내 한 줄** — 「평가자가 현장에서 보는 지표 6개는 이 화면에서 다루지 않습니다」를 그린다.

| | |
|---|---|
| loading | 지표 목록 스켈레톤 |
| **empty** | **`items` 는 비지 않는다 — 지표 9개는 늘 온다.** 확정 문서가 없으면 AUTO 둘은 `NONE` 이다. 체크가 없으면 SELF_CHECK 의 `elements` 안 평가요소는 전부 `checked: false` 다. "아직 확정된 문서가 없어요. 문서를 확정하면 여기서 세요" |
| success | 영역별로 묶은 지표다. AUTO 는 `verdict` 배지 · 각 지표의 `period` 와 「세어 준 것이지 충족을 확인해 준 것이 아닙니다」를 그린다. `children` 이 있으면 "3명 중 2명", `classes` 가 있으면 "2개 반 중 1개 반" 을 한 줄 더한다. 4-1 은 「공휴일은 반영하지 않습니다」와 방학 미반영 · 학년도 경계로 실제보다 부족으로 보일 수 있다는 안내를 그린다. 4-2 는 「입소 6개월 미만은 공식 평가 대상이 아니고, 6~12개월은 연 1회면 됩니다. 입소일을 몰라 모두 2회로 셉니다」와 실제보다 부족으로 보일 수 있다는 안내 · 「새 학년도에 아동을 다시 등록했다면 지난 학년도 평가가 빠질 수 있습니다」를 그린다. SELF_CHECK 는 지표별 `elements` 의 평가요소 트리 · 진행 수 · 완료와 「선생님이 직접 확인한 항목입니다」를 그린다. **자동 판정과 색 · 문구가 달라야 한다** |
| error | 404 는 원 선택으로 돌아간다. 그 밖에는 재시도 |

**아직 정하지 않은 것**

```
□  지표 파일 v2 — 평가요소 19개 나누기 · 1 2 3 4 5 정리   승석
□  plans 조회 함수 — 반 · 대상 달 · 확정 여부로 월간계획안을 찾는다   승석
□  4-2 와 ADR-007 「발달평가 스펙아웃」             승석 · PM    PM 확인 대기. assessment 와 같은 것인지
□  새 학년도에 아동 행을 옮기나 새로 만드나 — 4-2 가 지난 학년도 평가를 찾는지가 갈린다   반 · 아동 담당 · PM
□  달력 테이블(특일정보 API) — 생기면 4-1 의 평일에서 공휴일을 뺀다   승석
```

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
observations                   관찰 기록 본체              §10
INDEX(class_id, date)          observations 조회           §10  목록이 반·기간으로 거른다
documents                      일지 본체 + stale 플래그      §11
document_sections              사실 · 해석 · 지원           §11
routine_records                일일 보육일지의 사실 층       §10-1  dailyLog 근거
document_sources               생성 시점의 원문 사본        §11  원본이 바뀌어도 남아야 한다
INDEX(source_kind, source_id)  document_sources            §11  stale 전파가 역방향으로 찾는다
evaluation_checks              원 · 학년도 · 평가요소 체크    §12  체크 시각만. 지표 완료는 저장하지 않는다(ADR-022)
```

`classes.school_year` 는 **컬럼이 이미 있다.** 서버가 채우는 로직만 만들면 된다.
