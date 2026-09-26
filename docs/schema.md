# 데이터베이스 스키마

**마이그레이션을 추가하는 PR 은 이 문서도 같이 고친다.**

**컬럼 주석도 스키마다.** `models.py` 의 `comment=` 는 Postgres 가 실제로 들고 있는 값이라
문구만 바꿔도 마이그레이션이 필요하다. `alembic check` 가 이 어긋남을 잡는다.

**`NOT NULL` 컬럼을 추가할 때는 `server_default` 를 같이 준다.** 행이 이미 있는 테이블에
기본값 없이 붙이면 기존 행이 빈 채로 남아 마이그레이션이 멈춘다.

```
ERROR: column "code" of relation "children" contains null values
```

채운 뒤에 기본값은 뗀다. 남겨 두면 앞으로 들어오는 행이 값을 안 줘도 통과해서 빈
문자열이 조용히 쌓인다.

```python
op.add_column("children", sa.Column("code", sa.String(20), nullable=False, server_default=""))
op.alter_column("children", "code", server_default=None)
```

`nullable=True` 컬럼은 기본값이 필요 없다 — 비어 있는 것이 정상인 값이다.

천천히 바뀌는 테이블의 역할, 관계, 불변 규칙만 적는다. 컬럼 타입과 길이는
`models.py` 가 진실이다.

## 테이블

| 테이블 | 무엇을 담는가 |
|---|---|
| `centers` | 원. 파일럿 원 개수가 미정이라 여러 곳으로 열어뒀다 |
| `classes` | 반. `centers` 를 참조한다. **학년도마다 새 행이다** — 2026 씨앗반과 2027 씨앗반은 다른 반이다. `UNIQUE(center_id, name, school_year)`. `consent_confirmed_at` 은 아동 정보 동의를 확인한 시각이다. `age_min` · `age_max` 범위로 혼합반(3~5세 한 반)에 대응하며 단일 연령반은 두 값이 같다 |
| `children` | 아동. `classes` 를 참조한다. `name` 은 평문 실명이고 `code` 는 LLM 에 나가는 가명이다. `UNIQUE(class_id, code)` |
| `activities` | 활동 풀. 규칙 엔진의 검사 층이 읽는다(ADR-014) |

## 관계

```text
centers ←── classes ←── children
activities   (독립. plans 가 생기면 연결된다)
```

## 불변 규칙

1. `activities.code` 는 불변 슬러그다. **한 번 정하면 고치지 않는다.** 고치면 발행된
   계획안과 golden set 이 그 활동을 잃는다. 작명 규칙은 시드 PR 에서 정한다.
2. `plans` 가 생기면 셀은 생성 시점 값(반 이름·연령·담임·학년도)을 **스냅샷**한다.
   `classes` · `activities` FK 는 출처 표시용이며 렌더링에 쓰지 않는다.
3. `children.name` 은 평문 실명이다. **개발 DB 에 실제 아동 실명을 넣지 않는다.
   테스트는 가명으로**(ADR-004:77). LLM 호출 직전 치환기는 `backend/app/shared/childCode`
   에 있다. `children.code` 가 그 치환기가 붙여줄 가명의 자리다 — 아직 둘을 잇는 코드는
   없고, 지금은 치환표를 호출부가 직접 만든다.
4. `safety_flags` · `tags` 는 JSONB 라 **DB 가 모양도 어휘도 막지 않는다.** 시드
   스크립트의 YAML 대조가 유일한 방어선이다.
5. `classes` 행은 **학년도마다 새로 만든다.** 재사용하면 그 해의 담임·연령대가
   덮어써진다. `plans` 가 스냅샷을 뜨지만 계획안을 만들지 않은 반은 기록이 남지 않는다.
   아동의 반 이동 이력은 여전히 남지 않는다 — `children.class_id` 는 현재 소속 하나뿐이고,
   이력이 필요해지면 P1 에서 `class_memberships` 를 만든다.
6. 연령은 **학년도 기준 연 나이**(3·4·5)다. 만 나이가 아니다. 반 편성이 3월 1일
   기준이고 누리과정도 "3~5세"로 표기한다.

## 없는 것과 그 이유

| 없는 것 | 이유 |
|---|---|
| `children.birth_date` | ADR-007:52 가 발달평가를 스펙아웃해 쓸 기능이 사라졌다. ADR-004:71 은 "이름만 받는다"고 정한다 |
| `users` / `classes.teacher_id` 의 FK | 인증이 8주차다. `teacher_id` 는 nullable 컬럼으로만 있다 |
| `plans` | 계획안 테이블이다. 다음 PR 에서 만든다 |
| 활동 쪽 지역 축 | `centers.region_sido` · `region_sigungu` 는 지역 2단 분리 마이그레이션에서 들어왔다. 활동을 지역으로 거르는 규칙은 아직 없다 |
| `ON DELETE` 지정 | 삭제 생명주기가 미정이다. 암묵적 연쇄 삭제를 막고 명시적으로 정리한다 |
