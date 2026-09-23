# 데이터베이스 스키마

**마이그레이션을 추가하는 PR 은 이 문서도 같이 고친다.**

천천히 바뀌는 테이블의 역할, 관계, 불변 규칙만 적는다. 컬럼 타입과 길이는
`models.py` 가 진실이다.

## 테이블

| 테이블 | 무엇을 담는가 |
|---|---|
| `centers` | 원. 파일럿 원 개수가 미정이라 여러 곳으로 열어뒀다 |
| `classes` | 반. `centers` 를 참조한다. **학년도마다 새 행이다** — 2026 씨앗반과 2027 씨앗반은 다른 반이다. `UNIQUE(center_id, name, school_year)`. `age_min` · `age_max` 범위로 혼합반(3~5세 한 반)에 대응하며 단일 연령반은 두 값이 같다 |
| `children` | 아동. `classes` 를 참조한다. 이름은 평문 실명이다 |
| `activities` | 활동 풀. 규칙 엔진의 선별 층이 읽는다(ADR-005) |
| `documents` | 일지 계열 문서 4종(dailyLog·weeklyLog·observation·assessment). `classes`·`children` 을 참조한다(docs/api-spec.md §11) |
| `document_sections` | 문서 본문. `사실`·`해석`·`지원` 셋뿐이다. `documents` 를 참조한다 |
| `document_sources` | 생성 시점 원문 사본. `documents`·`classes`·`children` 을 참조한다. `source_kind`+`source_id` 로 `observations`(§10, 아직 없음) 또는 `documents` 자신을 다형 참조한다 — FK 는 없다 |

## 관계

```text
centers ←── classes ←── children
activities   (독립. plans 가 생기면 연결된다)
documents ←── document_sections
documents ←── document_sources ──(source_kind·source_id, FK 없음)──> observations · documents
```

## 불변 규칙

1. `activities.code` 는 불변 슬러그다. **한 번 정하면 고치지 않는다.** 고치면 발행된
   계획안과 golden set 이 그 활동을 잃는다. 작명 규칙은 시드 PR 에서 정한다.
2. `plans` 가 생기면 셀은 생성 시점 값(반 이름·연령·담임·학년도)을 **스냅샷**한다.
   `classes` · `activities` FK 는 출처 표시용이며 렌더링에 쓰지 않는다.
3. `children.name` 은 평문 실명이다. **개발 DB 에 실제 아동 실명을 넣지 않는다.
   테스트는 가명으로**(ADR-004:77). LLM 호출 직전 치환기(`shared/childCode`)는 P1 에
   만든다(ADR-004:19-20).
4. `safety_flags` · `tags` 는 JSONB 라 **DB 가 모양도 어휘도 막지 않는다.** 시드
   스크립트의 YAML 대조가 유일한 방어선이다.
5. `classes` 행은 **학년도마다 새로 만든다.** 재사용하면 그 해의 담임·연령대가
   덮어써진다. `plans` 가 스냅샷을 뜨지만 계획안을 만들지 않은 반은 기록이 남지 않는다.
   아동의 반 이동 이력은 여전히 남지 않는다 — `children.class_id` 는 현재 소속 하나뿐이고,
   이력이 필요해지면 P1 에서 `class_memberships` 를 만든다.
6. 연령은 **학년도 기준 연 나이**(3·4·5)다. 만 나이가 아니다. 반 편성이 3월 1일
   기준이고 누리과정도 "3~5세"로 표기한다.
7. `document_sources` 는 **불변 스냅샷**이다. `observations`·`documents` 원본이 나중에
   바뀌어도 여기 복사된 `text`·`date`는 안 바뀐다 — 무효(`stale`) 판정이 "생성 당시에
   뭘 봤는지"와 "지금 원본이 뭔지"를 비교해야 하기 때문이다(docs/api-spec.md §11).
8. `document_sources.source_id` 에는 **FK 가 없다.** `source_kind` 값에 따라
   `observations.id` 또는 `documents.id` 중 하나를 가리키는 다형 참조라 단일 FK로
   못 건다. 대신 `(source_kind, source_id)` 인덱스로 역방향 조회(무효화 전파)를 지원한다.
9. `documents`·`document_sections`·`document_sources` 도 결정 5와 같은 이유로
   `ON DELETE` 를 지정하지 않는다. `DELETE /api/documents/{id}` 는 애플리케이션이
   `document_sections`·`document_sources` 를 먼저 지우고 `documents` 행을 지운다.

## 없는 것과 그 이유

| 없는 것 | 이유 |
|---|---|
| `children.birth_date` | ADR-007:52 가 발달평가를 스펙아웃해 쓸 기능이 사라졌다. ADR-004:71 은 "이름만 받는다"고 정한다 |
| `users` / `classes.teacher_id` 의 FK | 인증이 8주차다. `teacher_id` 는 nullable 컬럼으로만 있다 |
| `plans` | 계획안 테이블이다. 다음 PR 에서 만든다 |
| 활동 쪽 지역 축 | `centers.region_sido` · `region_sigungu` 는 PR #16 에서 들어왔다. 활동을 지역으로 거르는 규칙은 아직 없다 |
| `ON DELETE` 지정 | 삭제 생명주기가 미정이다. 암묵적 연쇄 삭제를 막고 명시적으로 정리한다 |
| `observations` | §10 관찰 기록 테이블이다. `documents`가 이걸 근거로 쓰지만 아직 어느 PR 에도 없다 — 담당·시점 확인 필요 |
| `document_sources.date` 의 확정 규칙 | `source_kind='observation'` 이면 그 기록의 날짜지만, `source_kind='document'`(주간→일일)일 때 뭘 넣을지 api-spec 에 없어 잠정 nullable 로 뒀다 |
| `document.generation_method` 의 CHECK 제약 | `kind`·`status`·`origin` 과 달리 enum 값을 못 박지 않았다. §4 plans 의 `RULE_LLM`·`RULE_ONLY` 개념과 겹치는데 plans 도 아직 없어 지금 확정하면 나중에 어긋날 수 있다 |
