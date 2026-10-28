# ADR-047: 놀이 중심 월간 — 교사가 고치는 표시 칸 · 놀이 방향 · 칸별 시간표를 Core 계획에 둔다

- 날짜: 2026-10-28 (결정 하민 · 구현 Claude · 검토 Codex)
- 상태: 채택 — Core 저장 · 이력 계약까지. **공개 API JSON 모양은 정하지 않는다**(ADR-046 서버 경로와 함께 성진과 맞춘다).
- 관련 — ADR-046(놀이 중심 월간 서버 경로, 제안) · CLAUDE.md §13 Provenance · §19 상태 규칙
- Core 인용은 `p0-planning/src/ssuksak/planning/` 아래 파일이다. 구현 커밋은 `feature/monthly-v2-timetable-core`.

## 맥락

월간 v2 양식(`play_monthly.hwpx`)에는 제목 · 반 표시 · 예상 기간 · 가운데 「예상되는 놀이 방향」 ·
특성화 시간표 · 특별활동 시간표 칸이 있다. 첫 한글 내보내기는 앞의 넷을 계획에서 계산했고
(월 · 연령 · 대상 월 1일~말일 · 주제), 시간표 두 개는 비워 뒀다.

로컬 웹 시제품은 교사가 이 칸들을 직접 고치고, 특별활동 칸을 나누고 · 지우고 · 크기를 조절한다.
정식 연결 전에 이 값들을 **어디에 두고 이력을 어떻게 남길지** 를 정해야 했다.

## 결정 (하민 2026-10-28, D-1 ~ D-10)

### 1. 모두 Core 계획 본문에 둔다 (D-1)

칸 주소(`item_id` · `semantic_key`) · 이력 · 확정 뒤 읽기 전용이 Core 규칙이라, 시간표 구조와
크기도 화면이 아니라 `PlayMonthlyPlan` 이 갖는다. layout 버전은 `play-monthly-layout-v0.2.0` 으로
올린다(요청 지문이 바뀐다).

### 2. 표시 칸은 출력용 문자열이다 (D-2 · D-10)

| 칸 | 처음 값 | 생성 방식 | 근거 |
|---|---|---|---|
| 제목 | 「{월}월 놀이계획안」 | RULE_ONLY | CALENDAR(대상 월) |
| 연령 | 「만 3·4세」(대상 연령 오름차순) | RULE_ONLY | CLASSROOM_PROFILE |
| 반 이름 | 생성 명령의 `class_name`(서버가 넘김, 공백 정리) | RULE_ONLY · 빈 칸이면 없음 | CLASSROOM_PROFILE |
| 기간 | 「YYYY.MM.01 ~ YYYY.MM.말일」 | RULE_ONLY | CALENDAR(대상 월) |

**고쳐도 실제 대상 월 · 연령 · 주차는
바뀌지 않는다.** 교사가 비우면 빈 채로 둔다 — 다시 계산해 채우지 않는다.

### 3. 놀이 방향은 주제를 한 번 복사한 뒤 독립이다 (D-6)

생성 때 주제 값을 복사한다(RULE_ONLY, 근거 PARENT_PLAN). 그 뒤 주제를 고쳐도 따라가지 않고,
비우면 빈 채로 둔다. 교사 편집은 다른 칸과 같이 생성 방식을 바꾸지 않는다(TEACHER_EDITED 이력만).

### 4. 특성화 시간표는 제목 5 · 내용 5 칸이다

`specialized_timetable.header.0..4` 뒤에 `specialized_timetable.content.0..4`. 빈 칸으로 시작하고
처음 쓰면 MANUAL 이다.

### 5. 특별활동 시간표는 요일마다 나눔 트리다 (D-7 · D-9)

- 월~금 각각 트리 하나. 마디는 **칸 하나**이거나 **경계 하나 + 두 갈래**(`axis` 세로/가로,
  `ratio` = 첫 갈래 비율 %, `split_id`)다. 처음 모양은 전달본 양식과 같다.
- **나누기:** 원래 칸이 ID · 값 · 이력 그대로 첫 갈래가 된다. 새로 생기는 것은 둘째 칸
  하나(새 `item_id`, CREATED 이력)와 경계 하나(새 `split_id`)뿐이다. 비율은 50 으로 시작한다.
- **지우기:** 칸은 `removed_timetable_cells` 에 통째로 보관된다(놀이 행 삭제와 같다). 남은 갈래가
  부모 경계 자리를 잇고, 그 갈래 안의 경계 `split_id` 는 그대로다. 요일의 마지막 칸은 지울 수
  없고 비우기만 한다.
- `split_id` · 칸 번호(`special_activity_timetable.{요일}.{n}`)는 다시 쓰지 않는다 — 보관된 칸의
  번호까지 보고 늘린다. 사라진 경계를 가리키는 크기 조절은 거절한다.
- **크기:** 경계 비율, 요일 열 폭(%, 합 100), 표 높이(mm).

### 6. 구조 변경은 새 이력 종류 `TIMETABLE_CHANGED` 로 남긴다 (D-4)

`ArrangementChange` 는 ID 목록만 담아 숫자를 못 남긴다. 그래서 계획 단위 이벤트
`TIMETABLE_CHANGED` 와 `AuditEvent.timetable_change`(`TimetableChange`)를 새로 둔다. 행위자가
필요하고, 칸 `item_id` · 값 변경 · 생성 방식 변경은 싣지 않는다.

| `operation` | 필수 필드 | 숫자 |
|---|---|---|
| `SPLIT` | `split_id` · `axis` · `cell_id`(원래 칸) · `new_cell_id` | — |
| `REMOVE` | `split_id`(사라진 경계) · `axis` · `cell_id`(지운 칸) | — |
| `RESIZE_SPLIT` | `split_id` | `before` · `after` = (비율,) |
| `RESIZE_COLUMNS` | — | `before` · `after` = 요일 5개 폭 |
| `RESIZE_HEIGHT` | — | `before` · `after` = (높이 mm,) |

숫자는 정수 튜플이고 전후 길이가 같고 서로 달라야 한다. 표 크기를 한 번에 폭 · 높이 모두
바꾸면 이벤트 2개다. 같은 값으로 다시 보내면 기록도 저장도 하지 않는다. 칸 글 편집은 기존대로
칸의 TEACHER_EDITED 이력이다.

### 7. 한도는 잠정값이다 (D-3)

나눔 깊이 4 · 비율 10~90 정수 · 열 폭 5% 이상 · 높이 16~80mm. 시제품 값이며, 한글 렌더 확인 뒤
제품 값으로 정한다. 화면의 실수 드래그 값은 이 정수 계약에 맞춰 보낸다.

### 8. 확정 뒤에는 모두 막힌다

나누기 · 지우기 · 크기 조절 · 칸 편집 모두 `CONFIRMED` 에서 거절한다(CLAUDE.md §19).

## 정하지 않은 것 · 후속

- **공개 API:** 경로 · 요청/응답 JSON 모양 · 오류 코드 공개 여부는 ADR-046 과 함께 정한다. Core
  오류 코드(`timetable_split_limit` · `timetable_last_cell` · `timetable_boundary_not_found` ·
  `invalid_timetable_size` · `invalid_axis` · `play_monthly_timetable_cell_not_found`)를 HTTP 오류로
  자동 승격하지 않는다.
- **되돌리기 (D-5):** 저장 전 되돌리기만 화면에서 한다. 서버 되돌리기는 없고, 나중에 생겨도
  이력을 지우지 않는다.
- **한글 출력 (D-8):** 특성화 · 특별활동 격자 그리기는 아직 없다. 전달본처럼 바깥 격자 병합으로
  그리고(중첩 표는 예비안), 렌더를 확인한 뒤 §7 한도를 확정한다.
- **옛 본문:** layout v0.1.0 으로 저장된 `PLAY_MONTHLY` 본문은 새 필수 칸이 없어 읽히지 않는다.
  서버 저장 연결(ADR-046) 전이라 저장된 본문이 없다는 전제이며, 운영 DB 로 확인하지는 않았다.
