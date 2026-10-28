# ADR-046: 놀이 중심 월간계획안 서버 연결 — 새 경로 · plans 행 `kind='monthly'` 의 `PLAY_MONTHLY` 본문 · 계약 먼저

- 날짜: 2026-10-28 (결정 성진 · 검토 하민)
- 상태 — **제안 (검토 전)** (성진). 경로 · 이름 · 오류 표는 하민 리뷰에서 바뀔 수 있다. **계약만 정하고 구현은 하지 않는다.**
- 관련 — ADR-042 · ADR-043 §4 · ADR-044 · ADR-030 PM-03 · PM-04 · api-spec §9-7
- Core 인용은 `p0-planning/src/ssuksak/planning/` 아래 파일이고, develop `b26f5ff` 기준 줄 번호다. 서버 인용은 이 브랜치의 `backend/app/features/plans/` 다.

## 맥락

[실측] Core 는 놀이 중심 월간(`PLAY_MONTHLY`)의 생성 · 칸 편집 · 누리과정 연결 · 행 추가 · 삭제 · 안전교육 배치 · 훈련 후보 복사 · 확정을 갖췄다(`application/generate_play_monthly_plan.py` · `application/play_monthly_lifecycle.py`). 서버 연결은 없다.
ADR-043 §4 는 「놀이 중심 월간은 별도 경로, 담당 · 경로는 미정」이라고만 했다. ADR-044 는 연간 저장 연결만 다루고 월간을 범위 밖에 뒀다.
이 문서는 그 경로 · 저장 위치 · 기존 월간 경로와의 경계 · 오류를 정한다. 화면은 후속이다.

## 결정

### 1. 새 경로로 연다 — 기존 `POST /api/plans/monthly` 를 형식으로 가르지 않는다 (제안)

```
POST   /api/plans/monthly/play                                              생성 → 201
GET    /api/plans/monthly/play?class_id=                                    목록
GET    /api/plans/monthly/play/{id}                                         단건
DELETE /api/plans/monthly/play/{id}                                         초안만 (revision 없음)
PUT    /api/plans/monthly/play/{id}/cells/{item_id}                         칸 글
PUT    /api/plans/monthly/play/{id}/activities/{item_id}/content-ids        누리과정 연결 바꾸기
POST   /api/plans/monthly/play/{id}/activities                              행 추가 (together · free_play)
DELETE /api/plans/monthly/play/{id}/activities/{item_id}?expected_revision= 행 삭제
PUT    /api/plans/monthly/play/{id}/safety-weeks/{week_id}                  안전교육 주별 배치
POST   /api/plans/monthly/play/{id}/drill-candidates/{item_id}/copy         훈련 후보 복사
POST   /api/plans/monthly/play/{id}/confirm                                 확정
GET    /api/plans/monthly/play/{id}/audit                                   이력
```

- 담당은 서버 · 화면 성진, Core 하민이다.
- **Core 이름을 따랐다.** 행은 따로 `activity_id` 가 없고 **이름 칸의 `item_id`** 가 주소다(`EditPlayMonthlyContentIdsCommand.item_id` `play_monthly_lifecycle.py:77-79` · `RemovePlayMonthlyActivityCommand.item_id` `:91-93`). 안전 후보 · 훈련 후보도 칸의 `item_id` 다(`candidate_item_id` `:101` · `:108`). 그래서 경로는 `{item_id}` 로 쓴다. 본문 이름은 Core 명령 그대로 `candidate_item_id` · `content_ids` · `section` · `emphasized_row_keys` 다(`generate_play_monthly_plan.py:158`).
- `play` 는 고정 글자 경로라 `GET /monthly/{plan_id}`(`monthly_router.py:356`)보다 **먼저 등록한다.** 아니면 `play` 가 정수 검사에 걸려 422 가 된다.

### 2. 저장 — plans 행 `kind='monthly'`, 본문 `format = "PLAY_MONTHLY"`

- migration · 새 열 없음. 놀이 월간 행은 **`body.format == "PLAY_MONTHLY"` 인 월간 행**이다. 기존 월간 본문에는 `format` 이 없다.
- `format_of`(`play_project.py:111-113`)는 없으면 `"MONTHLY_THEME"` 를 준다. 그건 연간 이름이다. 월간 쪽 검사는 **`== "PLAY_MONTHLY"` 인지만** 본다.
- 유일 인덱스 `uq_plans_monthly_per_classroom_month`(`models.py:56-62`, `center_id · classroom_ref · target_month`, `kind='monthly'`)가 「같은 반 · 같은 달 월간은 기존 · 놀이를 합쳐 하나」를 그대로 지킨다(하민 2026-10-27 답, 메신저). 새 `kind` 였다면 CHECK(`models.py:42`)와 인덱스를 고쳐야 한다.
- 반의 연간이 한 형식이라 한 반의 월간 행은 한 형식뿐이다. 연간은 월간이 딸려 있으면 지워지지 않는다(`router.py:570-576`).

### 3. 목록은 새 경로에 따로, 기존 목록은 놀이 월간 행을 명시적으로 뺀다

- `GET /api/plans/monthly/play?class_id=` 가 놀이 월간만 준다. 기존 `GET /api/plans/monthly` 는 `body.format == "PLAY_MONTHLY"` 행을 **형식으로 빼고 경고를 남기지 않는다.**
- [실측] 지금은 `profile_ref` 가 없는 행을 `_skip` 으로 경고와 함께 빼 버린다(`monthly_router.py:316-354`). 놀이 월간 행이 생기면 정상 행마다 경고가 쌓인다.

### 4. 기존 월간 경로가 놀이 월간 id 를 만나면 409 `GATE_BLOCKED`

- 대상: 기존 월간의 단건 · 칸 수정 · 칸 재생성 · 확정 · 이력 · 삭제 · 내려받기(`monthly_router.py:356 · 362 · 392 · 607 · 625 · 655` · `export.py:96`). 「이 형식에는 그 동작이 없다 = 409」(ADR-043 §4)와 같은 규칙이다.
- 문구(경로 안내 포함 — 화면이 아니라 호출 실수 때문에 보이는 것이다): 「놀이 중심 월간계획안은 /api/plans/monthly/play 경로로 다룹니다.」 `fields: []`.
- 소유(404) 다음, 확정 · revision 검사보다 **먼저**, 본문을 `MonthlyPlan` 으로 읽기 전에 막는다. 읽다가 깨지는 것이 위험이다.
- **반대 방향도 대칭이다.** 새 경로가 기존 월간 id 를 받으면 409 `GATE_BLOCKED` 「기존 월간계획안은 /api/plans/monthly 경로로 다룹니다.」다(ADR-044 §6-1 이 연간에서 양방향을 막는 것과 같다).
- **주간 생성도 막는다.** `POST /api/plans/weekly` 는 그 달 월간 행을 찾아 `MonthlyPlan` 으로 읽는다(`weekly_router.py:195-210`). 주간 Core 는 `MonthlyPlan` 만 부모로 받는다(`application/generate_weekly_plan.py:200-208`). 놀이 월간이 부모면 **부모 행을 찾은 직후, 읽기 전에** 409 `GATE_BLOCKED` · 「놀이 중심 월간계획안 아래에서는 주간계획안을 만들 수 없습니다.」다. 길이 생길 때까지다(§ 아직 정하지 않은 것 5).
- **기존 월간 생성의 놀이형 부모 409 문구를 고친다.** 화면은 이 `message` 를 그대로 보여 준다(`MonthlyPlanPage.tsx:40`, ADR-043 근거). 지금은 「놀이 프로젝트형 연간계획안으로는 기존 월간계획안을 만들 수 없습니다.」(`monthly_router.py:229-230`)이고, 경로 이름 없이 「놀이 중심 월간계획안으로 만들어 주세요.」를 덧붙인다. 코드 · status 는 그대로다.

### 5. 생성은 요청 안에서 기다리고 201 이다

- 기존 월간처럼 한 요청이 Core 를 부르고(LLM 1회 + 수리 최대 1회, `generate_play_monthly_plan.py:254-265`) 끝나면 `201` 에 단건 응답 전체를 준다. 실패하면 아무것도 저장하지 않는다.
- **걸리는 시간을 재 본 적이 없다.** 구현 뒤 실제로 재서 너무 길면 스트리밍으로 바꾼다(ADR-043 §5 의 연간 방식). 그때 이 ADR 을 고친다. 지금 마감 · nginx timeout 숫자를 정하지 않는다.
- 요청 `{ class_id, month, emphasized_row_keys? }`. 학년도는 반이 정하고 부모 연간은 서버가 반으로 찾는다(기존 월간과 같다). `emphasized_row_keys` 는 부모 놀이 중 강조할 `row_key` 이고 기본 `[]` 다. 부모 구간에서 고른 것이어야 한다(`EMPHASIS_NOT_SELECTED`).
- **생성 게이트** (순서 고정):
  0. **스키마(422)** — `month` 1~12 · `emphasized_row_keys` 중복 · 빈 문자열 · 모양. 아래 모든 검사보다 앞이다.
  1. 반 소유(404) → 같은 반 · 같은 달 월간이 이미 있으면 409 `ALREADY_EXISTS`(기존 · 놀이 형식 무관, 기존 월간 생성의 순서와 같다 `monthly_router.py:217-218`).
  2. 그 반의 연간 행이 없으면 409 `GATE_BLOCKED`.
  3. 연간 본문이 놀이 프로젝트형이 아니면 409 `GATE_BLOCKED` — **읽기 전에** 막는다.
  4. Core `_parent`(`generate_play_monthly_plan.py:441-492`)가 **연간이 확정된 놀이 프로젝트형**인지 본다. 상태 `CONFIRMED` 와 본문의 `CONFIRMED` 이벤트 **둘 다** 있어야 한다. ADR-044 §4 가 확정에 본문 전체 저장을 요구하는 이유가 이것이다.
  5. 참조자료(누리과정 · 생활 문장 · 훈련 · 안전) 검사, 그 뒤 LLM.
- Core 오류 → 공개 오류는 api-spec §9-7 오류 표(초안)다.

### 6. 동시 수정 · 확정 — ADR-044 §3 · §4 와 같은 방식

- **칸 · 연결 · 행 추가/삭제 · 안전 배치 · 훈련 복사 · 확정**은 `expected_revision`(정수 ≥ 1)을 필수로 받는다. **계획안 전체 삭제는 받지 않는다** — 기존 월간 삭제와 같다(성진 결정 2026-10-28, 아래 근거). 저장은 `update_if_revision`(`repository.py:78`)의 「DRAFT 이고 revision 이 그대로일 때만 쓰고 +1」 한 문장이다. 실패는 409 `STALE_WRITE` · `ALREADY_CONFIRMED` 다.
- **검사 순서** — 스키마(422) → 소유(404) → 형식(409) → 확정(409) → revision(409) → Core 내용 검사(404 · 422).
- **스키마가 먼저 막는다**(api-spec §6-1 「검사 순서」 · CLAUDE.md 「입력 검사 — 스키마에서 막는다」). 다음은 라우터 · 소유 · Core 에 들어가기 전에 422 다: `month` 정수 1~12 · `emphasized_row_keys` 중복 · 빈 문자열 · 칸 `value` 문자열 0~600자(앞뒤 공백 제거) · `content_ids` 문자열 1~3개 · 중복 없음 · 빈 문자열 없음 · `section` 은 `together | free_play` · `expected_revision` 정수 ≥ 1(JSON 본문은 `"3"` · `true` 거절). 그래서 없는 계획안 · 확정본에도 이 값들은 422 다. Core 오류(`invalid_content_ids` · `invalid_section` 등)는 **스키마를 통과한 뒤에 남는 것**만 다룬다 — 예컨대 그 누리과정 판에 없는 ID. Core `EditPlayMonthlyContentIds` 는 같은 ids 면 1~3 검사 앞에서 무변경으로 돌려주므로(`play_monthly_lifecycle.py:192-193`), 막 추가한 빈 행에 `[]` 를 보내면 Core 만으로는 200 이 된다 — 스키마가 먼저 막아 422 가 된다.
- **형식부터 틀린 id** — 경로의 `{item_id}` · `{week_id}` · 본문의 `candidate_item_id` 를 서버가 `ItemId` · `WeekId` 로 만들지 못하면(빈 문자열 · `YYYY-MM-Wn` 아님) 422 다(`fields` 는 `["item_id"]` · `["week_id"]` · 해당 본문 키, 연간 §6-1 과 같다). 형식은 맞는데 계획안에 없는 것은 Core `*_not_found` 를 따른다. Core `invalid_item_id` 는 서버가 타입을 잘못 넘길 때만 나는 내부 오류라 500 이다.
- 모든 변경의 actor 는 서버가 로그인 계정에서 만든다. 요청 본문으로 받지 않는다.
- **칸 편집의 같은 값은 422 `VALIDATION_FAILED` `["value"]` 다**(성진 결정 2026-10-28) — 월간 §9-3 · 연간 §6-1 과 같은 규칙이다. 서버가 Core 를 부르기 전에 현재 칸 값과 비교한다. 공백을 턴 값이 현재 값과 같으면 같은 값이고, **빈 값 → 빈 값도 같은 값이다.** Core 는 이 경우 무변경으로 돌려주지만(`play_monthly_lifecycle.py:143-144`) 같은 입력을 422 로 거절하는 것은 API 의 몫이다.
- **누리과정 연결 · 안전 배치 · 훈련 복사는 같은 입력이면 200 이고 쓰기 · 이벤트 · revision 증가가 없다**(연간 고르기 저장과 같은 성격). 같은 연결 `:192-193` · 같은 안전 후보 배치 `:305-306` · 이미 복사한 훈련 후보 `:340-343` 에서 Core 가 계획안을 그대로 돌려주고, 서버는 돌려준 계획안이 입력과 같으면 쓰지 않는다. stale revision 은 이 경우에도 먼저 409 다.
- **칸 값**: 앞뒤 공백을 털고(`strip_whitespace`) **빈 값을 허용한다**(`min_length` 없음) — Core 가 비우기를 허용하고 확정만 이름 · 주제 · 선정 이유 · 연결을 요구한다(`confirm_problems` `:388-403`). 상한은 600자다. [판단] `JSONB` 라 맞출 컬럼이 없어 Core 생성 검사의 가장 긴 칸 `MAX_RATIONALE_CHARS = 600`(`planner/text_policy.py:8`)에 맞췄다. Core 에는 교사 글의 상한이 없다.
- **확정은 Core `ConfirmPlayMonthlyPlan` 을 부르고 그 결과 본문 전체를 저장한다**(ADR-044 §4 와 같다). 확정 조건은 `confirm_problems`(주제 · 선정 이유가 비지 않음, 두 놀이 구간에 각각 한 행 이상, 모든 행에 이름과 누리과정 1~3개)다. 부족하면 422 `VALIDATION_FAILED` · `fields` 는 위치 키다.
- **이미 확정된 계획안의 확정 재호출은 200** 이고 revision · 확정 시각 · 확정자 · 이력이 바뀌지 않는다(ADR-035 §2). Core `ensure_mutable` 이 확정본에서 예외를 던지므로(`play_monthly_plan.py` `ensure_mutable`) **서버가 Core 를 부르기 전에** 정한다.
- 확정 뒤 모든 변경은 409 `ALREADY_CONFIRMED` 다. **확정 취소는 없다**(ADR-030 PM-03).

### 7. 응답 — 큰 틀

- `format: "PLAY_MONTHLY"` 판별자와 `format_version`(= Core `layout.layout_version`), `revision`, 아래 구역을 싣는다. 모양은 api-spec §9-7.
- 구역: 주 · 부모 스냅샷 · 주제 · 선정 이유 · 함께 하는 활동 · 유아 예상 자유놀이 · 주별 기본생활습관 · 안전교육 후보 · 주별 안전 배치 · 건강 · 영양 · 훈련 후보 · 교사 입력 칸 · 빈 칸 안내(`notices`).
- **칸마다 `{ item_id, value, evidence, generation }`** — 출처 세 축 중 Evidence · Generation 이 칸에 붙고, Audit 는 이력 API 가 준다(CLAUDE.md 출처 3축). 한 번도 쓰지 않은 교사 입력 칸은 `generation: null` 이다(`PlayMonthlyCell` 규칙).
- **싣지 않는 것**(내부 전용): `references`(Reference 판 · 지문 · 요청 지문), `removed_activities`, 칸의 `semantic_key`(교사 입력 칸은 구역 구분에 쓰므로 `key` 로 싣는다), 칸의 `audit`.
- `notices`(`SAFETY_UNPLACED` · `SAFETY_BLANK` · `HABIT_BLANK` · `HEALTH_BLANK` · `NUTRITION_BLANK`)는 저장하지 않고 응답마다 Core `play_monthly_notices` 로 계산해 싣는다. 확정을 막지 않는다(M2-D13 — Core 결정이고 `play_monthly_lifecycle.py:22-23` 독스트링에 적혀 있다).

### 8. 이력 — `GET /api/plans/monthly/play/{id}/audit`

- 계획안과 모든 칸의 저장된 이벤트를 발생 시각순으로 합쳐 준다. 종류는 `CREATED` · `TEACHER_EDITED`(칸 글은 `value_change`, 누리과정 연결은 `link_change`) · `ARRANGEMENT_CHANGED` · `CANDIDATE_COPIED` · `CONFIRMED` 다. **`type` 은 문자열 그대로** 싣는다 — 모르는 종류가 와도 응답이 깨지지 않게 한다.
- 싣는 필드는 `AuditEvent` 에서 놀이 월간에 해당하는 것뿐이다(`domain/provenance.py:196-209`): `item_id` · `actor` · `system_actor` · `value_change` · `generation_change` · `link_change` · `arrangement_change` · `copied_from`. `selection_change` 는 연간 이벤트라 싣지 않는다. 직렬화 모양은 하민 확인 전이다(§ 아직 정하지 않은 것 7).
- `scope` 는 계획안 단위 `PLAN` · 칸 단위 `CELL` 이다. **`CREATED` 는 계획안 1건 + 칸마다 1건**이다(기존 월간 §9-5 와 같다). 교사가 추가한 행의 `CREATED` 는 `actor` 가 있고 `system_actor` 는 null 이다(`play_monthly_lifecycle.py:248-254`). 생성 때 `CREATED` 는 `system_actor` 다.
- **지운 행의 칸 이벤트도 싣는다**(같은 시각이면 활성 칸 뒤에, `removed_activities` 순서로).  지운 행은 `removed_activities` 에만 남고 칸 목록에 없다. `ARRANGEMENT_CHANGED` 가 삭제를 기록하더라도 그 행의 앞선 편집이 이력에서 조용히 사라지면 안 된다. 그 `item_id` 는 응답 칸에 없을 수 있다. (제안 — 리뷰)

### 9. 주간 — 길이 생길 때까지 막는다

- 주간 Core 는 기존 월간만 부모로 받는다(§4 결정). 놀이 월간 아래 주간은 409 `GATE_BLOCKED` 다.

### 10. 이번엔 계약만, 구현은 뒤에

- 구현은 하민 답과 백엔드 ②(놀이형 연간 확정 · 이력, ADR-044 §7)가 머지된 뒤다. 생성은 놀이형 연간이 확정돼야 시험할 수 있다.
- 화면은 후속이고(`screen-spec` 을 이번에 건드리지 않는다), **한글 내려받기는 놀이 월간 양식이 없어 후속**이다. 그 전까지 `GET /api/plans/monthly/{id}/export/hwp` 는 놀이 월간 id 에 409 다(§4).

## 근거

- [판단] 새 경로: 기존 `POST /api/plans/monthly` 를 형식으로 가르면 요청 · 응답이 합집합이 되고 기존 월간의 모든 경로(단건 · 편집 · 목록 · 이력 · 내보내기)에 분기가 들어간다. 요청 모양(`profile_ref` 필수 `monthly_schemas.py:19-22` ↔ `emphasized_row_keys`)과 응답 모양(`MonthlyPlanOut` ↔ 놀이 월간)이 처음부터 다르다. 새 경로는 기존 경로에 「거절 한 줄」만 더한다.
- [실측] 기존 월간 경로는 본문을 `MonthlyPlan` 으로 읽는다(`monthly_router.py:167` · `weekly_router.py:205-207`). 놀이 월간 행이 같은 `kind` 에 들어가면 이 읽기가 깨진다(500 으로 보이는 위험). 그래서 형식 검사가 읽기 앞에 와야 한다.
- [실측] `confirmed_monthly_plans`(`queries.py:24-53`)는 확정된 `kind='monthly'` 행의 `body.target_month` 만 읽는다. 놀이 월간도 그 달 월간계획안으로 센다. 평가제 4-1 이 그렇게 세도 되는지는 이 ADR 이 정하지 않는다(§ 아직 정하지 않은 것, 성진).
- [실측] 연간 삭제는 `kind='monthly'` 딸린 행이 있으면 막고(`router.py:570-576`), 시험용 지우기는 월간 · 주간 자식을 `kind` 로만 찾는다(`router.py:616`). 둘 다 본문을 읽지 않아 놀이 월간 행에 영향이 없다.
- [판단] 새 `kind` 대신 `kind='monthly'`: 「같은 반 · 같은 달 하나」를 이미 있는 DB 제약이 지킨다. 새 `kind` 면 CHECK · 인덱스 · migration 이 필요하고 두 월간이 같은 달에 공존할 수 있게 된다.
- [판단] 계획안 전체 삭제(`DELETE .../play/{id}`)는 revision 을 요구하지 않는다. 기존 월간 삭제와 같은 규칙이다(성진 2026-10-28). 확정본 보호는 검사 뒤 지우는 방식이 아니라 **`status = 'DRAFT'` 조건이 붙은 한 문장의 DELETE** 로 보장한다. 지운 행이 0이면 다시 읽어 없음 · 남의 원은 404, 확정은 409 `GATE_BLOCKED` 「확정된 계획안은 지울 수 없습니다.」(기존 월간 삭제 문구, `monthly_router.py:362-`)다.
- [판단] 행 삭제의 revision 은 쿼리 `?expected_revision=` 로 받는다. DELETE 본문은 의미가 정해져 있지 않다. 본문 없는 DELETE 에 쿼리를 붙인 선례가 있다(`DELETE /api/routines/{id}?include_impact=true`, api-spec §10-1). revision 을 DELETE 에 싣는 선례는 없다. 쿼리는 문자열로 오므로 「`"3"` 은 422」 규칙은 JSON 본문에만 해당한다 — 쿼리는 1 이상 정수로 바뀌는 값만 받고 아니면 422 `["expected_revision"]` 이다(api-spec 의 모든 DELETE 를 다시 봤다). 행 삭제는 새 `revision` 이 필요하므로 `204` 가 아니라 **`200` 에 단건 응답 전체**를 준다. 계획안 삭제(`DELETE .../play/{id}`)는 기존 월간처럼 `204` 다.
- [판단] 연결 · 안전 배치 · 훈련 복사의 같은 입력 200: Core 가 무변경으로 정의했고(`play_monthly_lifecycle.py:192-193 · 305-306 · 340-343`), 화면이 같은 선택을 다시 보내는 것은 정상 경로다. 연간 선택 저장도 같은 선택이면 200 · 무변경이다(ADR-044 §1). 칸 편집만 422 인 것은 월간 §9-3 · 연간 §6-1 의 칸 편집 규칙을 따른 성진의 결정이다.
- [출처] 하민 2026-10-27 답(메신저): 같은 반 · 같은 달 월간은 기존 · 놀이를 합쳐 하나다.
- [판단] 생성 시간을 재기 전에 비동기 · 스트리밍을 정하지 않는다. 연간은 구간 4호출이라 숫자가 있었지만 월간은 LLM 1회 + 수리 1회이고 재 본 적이 없다.

## 대안

- 같은 `POST /api/plans/monthly` 를 `format` 으로 가름: 위 근거. 모든 기존 경로에 분기가 들어가고 응답이 합집합이다.
- 새 `kind='play_monthly'`: migration 과 인덱스 변경, 「하나」 제약을 새로 걸어야 한다. 기각.
- 기존 월간 목록에 놀이 월간을 섞기: 응답 모양이 달라 화면이 판별자로 가르게 된다. 기존 목록은 월간 화면이 그대로 쓴다. 기각.
- 놀이 월간 아래 주간을 지금 연결: 주간 Core 가 `MonthlyPlan` 만 받는다. 안전 배치(`safety_weeks`)가 주간으로 이어지는지도 모른다. 하민과 정한 뒤로 미룬다.
- DELETE 본문으로 revision: 본문 의미가 정해져 있지 않다. 기각.
- 칸 같은 값도 200 · 무변경: Core 동작과는 같지만 월간 §9-3 · 연간 §6-1 의 칸 편집 규칙과 갈린다. 기각 — 칸 편집은 기존 규칙(422)을 따른다(성진 2026-10-28).
- 한글 내려받기를 이번에: 놀이 월간 hwpx 양식이 없다. 후속.

## 결과

- 새 경로 12개와 기존 월간 경로 · 주간 생성의 형식 거절 한 줄씩이 구현 PR 에 든다. 기존 월간 목록은 놀이 월간 행을 형식으로 뺀다.
- 기존 월간 생성의 놀이형 부모 409 문구가 바뀐다(코드 · status 불변).
- **ADR-043 §4 「놀이 중심 월간은 별도 경로 · 담당 · 경로 미정」을 이 ADR 이 정한다.** 기존 월간 생성 409 는 유지한다.
- **ADR-044 의 「PLAY_MONTHLY Core 는 이번에 연결하지 않는다」 뒤를 잇는다.** 연결은 이 ADR 이 정한다.
- 이 ADR 이 채택되려면 Core 쪽 공개 창구 · 어댑터 · 데이터가 있어야 한다(아래 질문).
- 위험: 서버 코덱(`codec.py`)이 `PlayMonthlyPlan` 을 왕복하는지 구현 전에 확인한다. 쓰기는 dataclass 필드를 그대로 직렬화한다(`codec.py:37-38`). 읽을 때 `PlayMonthlyPlan` 으로 복원되는지는 확인하지 않았다.
- 구현은 하민 답과 백엔드 ② 뒤, 화면 · 한글 내려받기는 그 뒤다.
- **생성 준비 상태 — 계약 승인과 다르다**(하민 2026-10-28 답). 정상 생성에는 자료 · 로더 · provider 외에 **누리과정 · 생활 문장 · 훈련 주제 세 자료의 정식 승인(`runtime_active`)** 이 필요하다. mock 모드에서도 승인 검사를 건너뛰지 않는다. 지금 파일 그대로면 누리과정이 미승인이라 생활 문장 누락보다 앞에서 `CURRICULUM_REFERENCE_NOT_ACTIVE` 로 막히고, 공개 응답은 기존 자료 계열 매핑대로 503 `DEPENDENCY_UNAVAILABLE` 이다. 서버는 그 전에도 저장 · 조회 · 고치기 연결과 가짜 주입 테스트를 준비할 수 있다(미승인 자료를 자동으로 켜지 않는다).

## 아직 정하지 않은 것

### 하민에게 물은 것과 답 (하민 2026-10-28 답)

질문은 그대로 두고 답을 덧붙였다. 아래 답은 하민 님이 직접 확인한 내용을 옮겨 적은 것이다. 「후속 제안」은 구현 · 일정을 약속한 것이 아니다.

1. **생활 문장(daily-life) Catalog 데이터와 저장소 어댑터는 누가 · 언제 · 어디에(어떤 범위로) 제공하시나요?** develop 에 없다. `DailyLifeReferenceRepository` 는 Protocol 만 있고(`generate_play_monthly_plan.py:127-128`), `p0-planning/src/ssuksak/adapters/` 에 생활 문장 어댑터가 없으며 `p0-planning/data/` 에 생활 문장 자료가 없다(`activities` · `curriculum` · `drills` · `evidence` · `rules` · `templates` · `themes`만 있다). 이것 없이는 생성이 `DAILY_LIFE_REFERENCE_NOT_FOUND`(`:504`)다.
   **답(하민 2026-10-28):** 실제 생활 문장 JSON 과 JSON 저장소 어댑터는 없다(`DailyLifeReferenceRepository` Protocol 과 `DailyLifeCatalog` 도메인만 있다). 이미 채택한 문장은 기본생활습관 7개 · 건강 4개 · 영양 4개이며 아직 정식 Catalog ID · version 을 발행한 자료가 아니다(검토표 번호를 runtime ID 로 쓰지 않는다). **자료와 로더는 하민/Core 쪽이 묶어 제공하고 서버는 그 로더를 주입하는 안이다.** 범위: 승인된 문장 · 표시 분류 · 누리과정 연결 ID · HABIT/HEALTH/NUTRITION 구분 · Catalog ID · version · 승인 상태. 위치 제안: `p0-planning/data/daily-life/daily_life_reference_v0_1_0_draft.json` · `ssuksak/adapters/json_daily_life_reference_repository.py`. 로더 계약 제안: `get_catalog(catalog_id, catalog_version) -> DailyLifeCatalog | None`. 문장 옮겨도 runtime 승인을 처음부터 켜지 않는다(자료 판 검토 · 정식 승인은 별도). **제공 시점은 착수 · 일정 미정이라 열린 채로 둔다.**
2. **실제 AI provider 어댑터를 Core 가 주나 서버가 만드나.** `PlayMonthlyProvider.generate_play_monthly` Protocol 만 있고(`planner/play_monthly.py:183-184`), `adapters/elice_openai_monthly.py` 에는 `generate_play_project`(`:241`)만 있다.
   **답(하민 2026-10-28):** **Core 가 기존 Elice 월간 어댑터에 `generate_play_monthly(request: PlayMonthlyRequest) -> RawLlmResponse` 를 추가하는 안이다.** 프롬프트 · 스키마 · 파서 · 검증은 Core 소유이고 서버가 별도 프롬프트를 만들지 않는다. 수리는 Application 이 최대 1회 부르며 어댑터가 자체 재시도나 Rule 대체 결과를 만들지 않는다. **서버는 기존 공용 transport 를 주입하고 서버 실행 가드 · 설정 · 사용량 로그(`llm_usage`) · 예산/전송 오류 매핑을 유지한다**(새 네트워크 클라이언트로 우회하지 않는다). 놀이형 연간의 stream · 출력 상한 설정을 월간에 자동 적용하지 않고 동기식 경로부터 따로 검증한다. 가짜 provider · transport 테스트와 조립부도 Core 후속 제공 안이다. **존재 여부 · 완성 시점은 아직 약속되지 않았다(열림).** 실제 유료 호출은 별도 승인 후다.
3. **생성 · lifecycle 클래스를 `ssuksak.planning` 공개 창구로 내보내실 계획이 있으신가요? 있다면 어느 클래스를 언제 내보내시나요?** `planning/__init__.py` 에 놀이 월간 이름이 없다. 서버는 놀이 프로젝트형 연간을 쓸 때도 하위 모듈을 직접 불러 쓴다(`monthly_router.py:59`, 「공개 창구에 없다」).
   **답(하민 2026-10-28):** 공개 export 는 후속이다. 그 전까지 서버가 하위 모듈을 직접 import 해도 된다(공식 공개 창구가 준비됐다는 뜻은 아니다). 후속에서 생성 · 편집 · 연결 변경 · 행 추가/삭제 · 안전 배치 · 훈련 복사 · 확정 Use Case/Command, `PlayMonthlyPlan`, 관련 오류와 notices 를 필요한 범위에서 공개하고, JSON 로더 조립은 `adapters.monthly_composition` 방식처럼 adapters 쪽에 둔다(planning 이 adapters 를 import 하지 않는다). **공개 이름 · 시점은 열려 있다** — ①② 제공 단위에서 명시한다.
4. **안전교육 분류 · 품질 · 증거 저장소 버전 상수는 누가 정하나.** 생성 명령이 버전 문자열을 요구한다(`GeneratePlayMonthlyPlanCommand` `generate_play_monthly_plan.py:149-157`). 서버가 어디서 읽어 넣는지 정해진 곳이 없다.
   **답(하민 2026-10-28):** 서버 생성 명령에 넘기는 값은 프론트 입력이 아니라 Core 자료/조립부가 소유한 값이다. 서버에 사본 상수를 두지 않고 조립부에서 한 번만 관리한다. 현재 값: `legal_rule_version` = `child-welfare-act-decree-annex6-2022-06-21`(`data/rules/safety_education_legal_v1.json`) · `safety_classification_version` = `safety-evidence-classification-v0.2.0`(`data/evidence/safety_evidence_classification_v0_2_0.json`) · `safety_quality_version` = `safety-reference-quality-v0.1.0`(`data/evidence/safety_reference_quality_v0_1_0.json`). **증거 저장소 판 · SHA 는 명령 필드가 아니라 주입한 저장소(`JsonInstitutionEvidenceRepository.get_store()`, 지금 `institution-evidence-ingestion-v0.1.0`)에서 읽어** 결과 `references` 에 기록한다. 저장소 판을 위 세 판 자리에 넣으면 안 된다.
5. **놀이 월간 아래 주간 길 · `safety_weeks` 가 주간으로 이어지나.** 주간 Core 는 `MonthlyPlan` 만 부모로 받는다(`generate_weekly_plan.py:200-208`). 놀이 월간의 주별 안전 배치(`play_monthly_plan.py:367`)가 주간 안전교육의 입력이 되는지 정해진 것이 없다.
   **답(하민 2026-10-28):** **지원하지 않는다.** 놀이 월간의 `safety_weeks` 를 주간에 옮기는 계약 · 일정은 정하지 않았다. 부모 본문을 기존 월간으로 읽기 전에 409 `GATE_BLOCKED` 로 막는 것이 맞다. 임의 변환하지 않는다.
6. **칸 재생성이 없는 것은 의도인가.** `play_monthly_lifecycle.py` 에 재생성 클래스가 없고, `AuditEventType.REGENERATED`(`domain/provenance.py:95`)는 놀이 월간에서 쓰이지 않는다. 기존 월간은 칸 재생성이 있다(api-spec §9-3).
   **답(하민 2026-10-28):** **이번 범위 밖이 맞다.** lifecycle 에 재생성 Use Case 가 없고, 칸 수정 · 연결 변경 · 행 추가/삭제 · 안전 배치 · 훈련 복사 · 확정까지만 연결한다. 화면은 월간 v2 의 「칸 다시 만들기」를 노출하지 않고, 기존 월간 재생성 API 로 보내지 않는다. 향후 범위 · 일정은 미정이다.
7. **새 이력 필드(`link_change` · `arrangement_change` · `copied_from`)의 직렬화 모양이 확정인가.** 필드는 `domain/provenance.py:207-209` 에 있고, 하민의 이력 ADR 초안은 origin 의 어느 브랜치에도 아직 없다. api-spec §9-7 의 모양은 서버가 임시로 정한 것이다.
   **답(하민 2026-10-28):** **Core 논리 필드와 보존 규칙은 확정되어 구현돼 있고, 공개 JSON 의 물리 모양은 이번 서버 계약에서 정한다.** api-spec §9-7 의 `link_change`(`{before, after, catalog_version}`, `value_change` 는 null, 순서 변경도 기록) · `arrangement_change`(`{scope, before, after}`, 안전 배치는 0~1개) · `copied_from`(훈련 후보 `item_id`) · `generation_change`(복사 전 generation 이 없으면 null — 가짜 MANUAL 이전값을 만들지 않는다) 모양이 Core 와 맞다. **삭제 행의 칸 이력을 조회에 포함하는 제안에 동의한다.** 후보 출처가 바뀌면 같은 문장이어도 새 복사 이력이 생긴다. Core 결정 ADR 초안은 로컬에 있으나 하민 검토 전이고 push 하지 않았다 — 번호 · 경로를 근거로 쓰지 않으며 **push 시점은 열려 있다.**
8. **`emphasized_row_keys` 를 만든 뒤 바꿀 수 있나.** 부모 스냅샷 안에 굳고(`play_monthly_plan.py:309`) 바꾸는 lifecycle 명령이 없다.
   **답(하민 2026-10-28):** **생성할 때만 받는다.** `emphasized_row_keys` 는 그 구간에서 고른 연간 놀이만 허용하고 부모 스냅샷에 고정된다. 변경 경로를 추가하지 않는다(생성된 문장이 다시 바뀌는 기능으로 오해될 수 있어 후속 재생성 설계와 함께 따로 정한다).

**아직 열린 것:** ①② 제공 시점 · ③ 공개 이름과 시점 · ⑦ Core 결정 ADR 의 push.

### 성진이 구현 전에 정한다

- 평가제 4-1 이 놀이 월간을 월간계획안으로 세는가(`queries.py:24-53`). 지금 코드는 센다.
- 누리과정 연결의 공식 문구를 응답이 함께 줄지(Core 는 문구를 저장하지 않고 Reference 에서 읽는다, `play_monthly_lifecycle.py:9-10`) · 화면에서 어떻게 보일지는 화면 PR 에서 정한다.
- 이력에 지운 행의 칸 이벤트를 싣는 것(§8)이 화면에서 헷갈리지 않는지.
