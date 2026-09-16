# API 계약 — P0 6주차

> **초안.** PM 이 엔드포인트·UI states 를 잡았다. **Response 스키마는 BE 가 채운다.**
> 확정되면 프로젝트 저장소 `docs/api-spec.md` 로 옮긴다. **이 파일이 원본이 된다** —
> 노션이 아니라 저장소에 두는 이유는 계약 변경이 PR diff 에 보여야 하기 때문이다.
> 2026-09-14 갱신 — 아동 명단 엔드포인트 3개 추가, 반 연령을 혼합 포함으로 명시,
> 성품인사를 온보딩에서 설정으로 이동(ADR-011 초안)

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

**공통 에러 형식**

```json
{
  "error": { "code": "VALIDATION_FAILED", "message": "사람이 읽는 문장", "field": "selected_ages" }
}
```

| code                | status | 뜻                                         |
| ------------------- | ------ | ------------------------------------------ |
| `VALIDATION_FAILED` | 422    | 입력값이 규격 밖                           |
| `NOT_FOUND`         | 404    | 대상 없음                                  |
| `GATE_BLOCKED`      | 409    | 층 게이트 — 연간이 확정 전인데 월간 요청   |
| `NO_ACTIVITIES`     | 503    | 활동 풀이 비었음 (운영 오류)               |
| `GENERATION_FAILED` | 500    | 생성 실패. **부분 결과를 저장하지 않는다** |

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

|         |                                                   |
| ------- | ------------------------------------------------- |
| loading | 저장 중 — 버튼 비활성                             |
| empty   | 해당 없음                                         |
| success | S2 로 이동                                        |
| error   | `VALIDATION_FAILED` — 입력값 유지, 해당 칸에 표시 |

---

## 2. 반 — `POST /api/centers/{center_id}/classes`

**Request**

```json
{ "name": "햇님반", "selected_ages": [3, 5], "child_count": 18, "teacher_name": "김선생" }
```

`selected_ages` 는 **1~3개 원소의 배열**이고 값은 3·4·5 중 하나, 중복 없음. `child_count` 는 **선택**(null 허용).

**FE 는 만 3세 / 만 4세 / 만 5세 독립 체크박스를 보여주고, 선택값을 그대로 배열로 보낸다.**

```
만 3세            → [3]
만 4세            → [4]
만 5세            → [5]
만 3세 + 만 4세    → [3, 4]
만 4세 + 만 5세    → [4, 5]
만 3세 + 만 5세    → [3, 5]     ← 3세와 5세만. 4세는 포함되지 않는다
만 3·4·5세        → [3, 4, 5]
```

혼합반이 실측 39% 다. **범위(age_min·age_max)로 받으면 `[3,5]` 가 `3~5`(4세 포함)로 뒤집힌다** —
그래서 범위가 아니라 배열로 받는다. 응답에도 같은 배열을 그대로 돌려준다.

**동의 체크박스는 DB 에 저장하지 않는다.** UI 게이트다. 새로고침 후에는
`GET …/children` 이 1명 이상이면 확인됨으로 복원한다. 컬럼 추가 0.

**Response** `201` — 생성된 반

**`GET /api/centers/{center_id}/classes`** → `{ "items": [...] }`

**UI states**

|           |                                                |
| --------- | ---------------------------------------------- |
| loading   | 목록 스켈레톤                                  |
| **empty** | `items: []` — "반을 추가해 주세요" + 추가 버튼 |
| success   | 반 카드 목록                                   |
| error     | 해당 카드에만 표시, 나머지 유지                |

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

**`GET /api/classes/{class_id}/children`** → `{ "items": [...], "count": 4 }`

**`DELETE /api/children/{id}`** → `204`. 오타 수정은 삭제 후 재등록이다.

**UI states**

|           |                                                                              |
| --------- | ---------------------------------------------------------------------------- |
| loading   | 명단 스켈레톤                                                                |
| **empty** | `items: []` — "아직 등록된 아동이 없어요. 위에서 이름을 입력해 추가해주세요" |
| success   | 번호 + 코드 배지 + 실명. 하단에 "현재 N명의 아동이 등록되어 있어요"          |
| error     | 추가 실패 — **입력한 이름을 지우지 않는다**                                  |

**0명이어도 다음 단계로 간다.** 「나중에 입력할래요」 버튼이 있다.
건너뛰면 메인 화면에 배너를 띄운다 — 문구는 _"관찰일지를 쓰려면 명단이 필요합니다"_.
**계획안(P0)은 명단 없이도 정상 작동한다.** 지금 막힌 게 아니라는 뜻이 전달돼야 한다.

---

## 3. 성품인사 — `GET·PUT /api/centers/{center_id}/greetings`

**GET Response**

```json
{ "enabled": true, "items": [ { "month": 3, "text": "..." }, ... ] }
```

12개. 원이 설정한 적 없으면 **기본 12개를 채워서 내려준다.** 빈 배열을 주지 않는다.

**`enabled` 기본값은 `false` 다.** 충청북도 수집분 23개 중 성품인사가 있는 건 0개다 —
쓰는 원이 소수라 기본을 off 로 둔다. (ADR-011 초안)

**호출 지점은 온보딩이 아니라 설정 화면(S10 · 7주차)이다.** 계약 자체는 안 바뀐다.
**6주차에 FE 가 이 엔드포인트를 부르지 않는다.**

**PUT Request** — 같은 형식. `enabled: false` 면 `items` 무시.

**UI states**

|         |                                              |
| ------- | -------------------------------------------- |
| empty   | **발생하지 않는다** — 서버가 기본값을 채운다 |
| success | 12칸 폼                                      |

---

## 4. 계획 문서 구성 — `PUT /api/centers/{center_id}/plan-config`

**Request**

```json
{
  "uses_monthly": true,
  "weekly_location": "SEPARATE_WEEKLY | DAILY_LOG_PLAN_CELL | WEEKLY_LOG_PLAN_CELL",
  "safety_edu_hours": 44
}
```

`safety_edu_hours` 는 안전교육 연간계획안을 업로드하지 않았을 때의 대체값.

---

## 5. 연간계획안 생성 — `POST /api/plans/annual` ★ 6주차 핵심

**Request**

```json
{ "class_id": 1, "school_year": 2026, "source": "FROM_SCRATCH | FROM_UPLOAD", "upload_id": null }
```

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
      "source_type": "TEMPLATE | TREND | AI",
      "citation": { "label": "누리과정 자연탐구", "url": null }
    }
  ]
}
```

**`months` 는 항상 12개다.** 3월 시작 ~ 익년 2월.
**`source_type` 이 칸마다 붙는다.** S6 의 좌상단 점이 이 값을 본다.

**UI states**

|             |                                                                                                                         |
| ----------- | ----------------------------------------------------------------------------------------------------------------------- |
| **loading** | ★ 수 초 걸린다. 진행 표시가 없으면 교사가 다시 누른다                                                                   |
| empty       | 발생하지 않는다 — 12개월이 항상 찬다                                                                                    |
| success     | S6 으로 이동                                                                                                            |
| error       | `NO_ACTIVITIES` 503 → "활동 데이터가 없습니다" (운영 문의)<br>`GENERATION_FAILED` 500 → 재시도 버튼. **부분 저장 없음** |

**결정론** — 같은 `class_id` · `school_year` · 같은 활동 풀이면 **같은 결과가 나온다.**
FE 는 이걸 전제로 목업을 고정값으로 만들어도 된다.

---

## 6. 조회 — `GET /api/plans/annual/{id}`

생성과 같은 형식.

|         |                 |
| ------- | --------------- |
| loading | 표 스켈레톤     |
| empty   | 해당 없음       |
| error   | `NOT_FOUND` 404 |

---

## 7. 칸 수정 — `PATCH /api/plans/annual/{id}/months/{month}`

**Request**

```json
{ "theme": "고친 주제", "sub_themes": ["..."] }
```

**Response** — 그 달 객체 하나. **전체를 다시 안 준다.**

수정된 칸은 `source_type` 이 `AI` → `TEACHER` 로 바뀐다.

**UI states**

|         |                                             |
| ------- | ------------------------------------------- |
| loading | 그 칸만 흐리게. **화면 전체를 막지 않는다** |
| success | 그 칸만 갱신                                |
| error   | **그 칸만 롤백.** 나머지 수정분 유지        |

---

## 8. 확정 — `POST /api/plans/annual/{id}/confirm`

**Request** — 없음

**Response** `200` → `{ "id": 10, "status": "CONFIRMED", "confirmed_at": "..." }`

**되돌리기는 P1.** 확정 후 수정 요청은 `409`.

|         |                                                                       |
| ------- | --------------------------------------------------------------------- |
| loading | 버튼 비활성 + 스피너                                                  |
| success | 상태 배지 `확정됨`                                                    |
| error   | `VALIDATION_FAILED` 422 — 빈 칸이 남았을 때. **어느 달인지 내려준다** |

---

## 9. 이미 있는 것 — 양식 파싱 (PR #6)

`POST /api/forms/parse` — 수린 구현. **화면 연결은 7주차.**

---

## 10. 7주차 예정 — 계약 안 씀

```
POST   /api/plans/monthly                 월간 43칸
PATCH  /api/plans/monthly/{id}/cells/{n}  칸 편집
POST   /api/plans/monthly/{id}/cells/{n}/regenerate   이 칸만 다시
GET    /api/plans/{id}/export/hwp         내보내기
```

**월간은 연간이 `CONFIRMED` 여야 생성된다.** 아니면 `GATE_BLOCKED` 409.

---

## 채워야 할 곳 — BE

```
□  각 Response 의 실제 필드명·타입·nullable        성진
□  citation 객체의 정확한 형태                     성진 · 하민
□  source_type 에 TEACHER 를 넣을지               하민
□  생성 소요 시간 실측 → loading UI 판단 근거        하민
□  NO_ACTIVITIES 를 503 으로 할지 422 로 할지      성진
□  code 발급 규칙 — 더미 이름 풀과 중복 처리        성진 · 하민
```
