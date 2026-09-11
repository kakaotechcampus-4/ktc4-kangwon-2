# ADR-009: 초기 스키마를 정한다

- 2026-09-11
- 상태 — 채택

## 맥락

`develop` 에 DB 테이블이 하나도 없었다. P0a 규칙 엔진이 읽을 테이블이 필요하다.

ADR-005 는 `age_min` · `age_max` · `safety_flags` 를 첫 마이그레이션에 넣으라고 정했다.
활동 200개를 다 넣은 뒤에 추가하면 200개를 다시 훑어야 한다.

## 결정

1. `plans` 가 생기면 셀에 생성 시점의 반 이름·연령·담임·학년도를 스냅샷한다.
   `classes` · `activities` FK 는 출처 표시용이며 렌더링에 쓰지 않는다.
2. `activities.code` 는 불변 슬러그로 둔다. 한 번 정하면 고치지 않는다.
   작명 규칙은 시드 PR 에서 확정한다.
3. `children.birth_date` 를 넣지 않는다.
4. `safety_flags` 를 `tags` 와 같은 JSONB 로 둔다.
5. FK 의 `ON DELETE` 를 지정하지 않고 `NO ACTION` 으로 둔다.
6. `String` 길이는 code 80, title 200, center.name 100, class·child.name 50으로 둔다.

## 근거

**1. 확정 문서는 현재 설정을 참조하면 안 된다** `[판단]`

스냅샷 규칙이 없으면 `plans` 작성자가 FK 참조 렌더링을 만들 수 있다. 그러면
`classes` 편집이 이미 `CONFIRMED` 된 제출 문서를 바꾼다. 되돌리려면 발행된 문서를
소급 복원해야 한다.

**2. 활동에는 순서와 별개인 자연키가 필요하다** `[판단]`

`id`(serial)는 「몇 번째」를 나타낸다. 활동을 중간에 추가하면 뒤 기대값이 전부 밀린다.
golden set 기대값을 `id` 로 적으면 활동 하나를 추가한 다음 날 전부 틀린다.
이는 ADR-003 의 결정론을 깨뜨린다.

재시드 때 이미 있는 활동인지 판단할 자연키도 없어 200개가 중복 삽입된다.
`code` 를 고치면 발행된 계획안과 golden set 이 그 활동을 잃는다. 한글·영문 여부와
조각 수를 포함한 작명 규칙은 시드 PR 에서 확정한다. 이번에는 칸만 만들고 값은 비어 있다.

**3. 생년월일을 쓸 기능이 없다** `[출처]`

ADR-007 이 발달평가를 스펙아웃했고 ADR-004 가 아동에게서 이름만 받는다고 정했다.
「이름+생년월일+원명」 특정 조합을 애초에 만들지 않는다.

**4. JSONB 통일의 실패 방향을 시드에서 막아야 한다** `[판단]`

`tags` JSONB 는 ADR-001 이 PostgreSQL 을 고른 근거라 바꾸지 않는다. 맞출 쪽은
`safety_flags` 다.

대가는 DB 가 값의 모양을 강제하지 않는다는 점이다. `text[]` 였다면
`{"tool":"가위"}` 같은 값은 INSERT 에서 실패한다. JSONB 는 그대로 받고 선별 층 질의가
걸리지 않아 그 활동을 조용히 「위험 없음」으로 취급한다. 아동 안전 필드에서 나쁜 실패
방향이다. 시드 스크립트의 YAML 대조는 유일한 방어선이며 권장이 아니라 필수다.

**5. 삭제 생명주기가 정해지지 않았다** `[판단]`

암묵적 연쇄 삭제를 금지하고 관계 행을 명시적으로 정리한다.

- `children.class_id`: `CASCADE` 는 반 삭제가 아동 행까지 지운다.
  `SET NULL` 은 `NOT NULL` 과 충돌한다.
- `classes.center_id`: `CASCADE` 는 원 삭제가 반을 암묵적으로 지운다.
  `SET NULL` 은 소속 없는 반을 만든다.
- `RESTRICT` 는 비지연 FK 에서 `NO ACTION` 과 실질 차이가 없다.

이는 「개인정보라서 보존」한다는 결정이 아니다. 과잉 보존도 위험하다.
파기 절차가 정해지면 재검토한다.

**6. 문자열 길이에 실측 근거가 없다** `[판단]`

code 80, title 200, center.name 100, class·child.name 50은 잠정값이다.
실제 데이터를 확인하면 고친다.

## 대안

**`safety_flags` 를 `text[]` 로** — 타입이 값의 모양을 강제한다. 그러나 같은 테이블에
두 타입이 섞인다. `tags` JSONB 와 GIN 이 이미 PostgreSQL 전용이라 이식성 이득도 없다.

**`activities.code` 없이 `id` 만** — 컬럼 하나를 아끼지만 결정론과 재시드 멱등성을 잃는다.
나중에 붙이려면 활동 200개에 사람이 이름표를 하나씩 달아야 한다.

**`classes.school_year` 를 넣기** — 학년도 구분은 생기지만 2026 행의 값은 여전히 가변이다.
문제를 절반만 푼다. 순차 게이트 질의의 주체가 `plans` 이므로 학년도는 `plans` 가 든다.

## 결과

- 시드 PR 은 `resources/rules/safety_flags.yaml` 을 만들고 YAML 대조 `assert` 를 넣어야 한다.
- 시드 PR 은 `code` 작명 규칙을 확정해야 한다.
- 계획안 출력 PR(5~6주차)은 담임 이름을 입력받는 경로를 만들어야 한다.
  `teacher_name` 컬럼을 두지 않았고 계획안 실물에는 담임 이름이 인쇄된다. `[실측]`
- 인증 PR(8주차)은 `users` 를 만들고 `classes.teacher_id` 에 FK 를 건다.
  그때까지 `teacher_id` 를 NULL 로 유지해야 `ADD CONSTRAINT` 의 기존 행 검사를 통과한다.
- 규칙 엔진 PR 은 혼합반 선별 규칙을 정해야 한다. 3~5세 반에 4~5세 활동을
  넣을지(겹침), 넣지 않을지(커버)는 DB 가 아니라 코드가 정한다.
- `plans` PR 은 결정 1의 스냅샷 규칙을 지킨다.

## 검증 `[실측]`

SQLAlchemy 2.0.52 · Alembic 1.19.2 · PostgreSQL 15 에서 확인했다.

| 확인 | 결과 |
|---|---|
| 생성 전 DB 가 비었나 | `pg_tables` 조회 0행. `pgdata` 는 영속 볼륨이라 잔재가 있으면 「초기」가 아니다 |
| `create_table` | 4개. 빈 마이그레이션이 아니므로 `env.py` import 누락 없음 |
| 제약 이름 | 14개 — CHECK 6 · PK 4 · FK 2 · UNIQUE 2. 규약대로이고 `ck_` 중복 없음 |
| 인덱스 이름 | 2개. `ix_activities_tags`(GIN) · `ix_children_class_id` |
| CHECK 식 | 모델과 동일. `alembic check` 는 CHECK 식을 비교하지 않아 눈으로 봤다 |
| GIN | `ix_activities_tags gin (tags)` 가 실제 DB 에 생성 |
| DEFAULT | `safety_flags` · `tags` 에 DB DEFAULT 없음. timestamp 는 `WITH TIME ZONE` |
| 왕복 | `downgrade base` → `upgrade head` 성공 |
| `alembic check` | `No new upgrade operations detected` |

`compare_server_default=True` 를 켠 상태에서도 스퓨리어스 diff 가 없었다.

## 과제 범위와 달라진 점

팀 과제는 `classes`, `activities`, `children` 과 `teacher_id` 컬럼,
`activities.age_min` · `age_max` · `safety_flags`, `tags` JSONB+GIN 이었다.

| 구분 | 과제 | 실제 | 왜 |
|---|---|---|---|
| 뺌 | `children.birth_date` | 없음 | ADR-007 · ADR-004(결정 3) |
| 늘림 | — | `centers` + `classes.center_id` | 파일럿 원 개수가 미정이라 여러 곳으로 열었다 |
| 늘림 | — | `classes.age_min` / `age_max` | 혼합반 가능성. 범위는 점을 포함하지만 점은 범위를 못 담는다 |
| 늘림 | — | `activities.code` UNIQUE | 결정 2 |

### 확인이 필요한 것

- `teacher_id` 를 `classes` 에 뒀다. 과제 원문의 대시가 `children` 에 붙어 있어
  `children.teacher_id` 로 읽힐 수 있다. 반 담임제라는 실물 근거로 `classes` 를 택했다.
  `[실측]`
- 확장 3건은 과제에 없다. 리뷰에서 확인받아야 한다.
