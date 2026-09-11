# 데이터베이스 스키마

**마이그레이션을 추가하는 PR 은 이 문서도 같이 고친다.**

천천히 바뀌는 테이블의 역할, 관계, 불변 규칙만 적는다. 컬럼 타입과 길이는
`models.py` 가 진실이다.

## 테이블

| 테이블 | 무엇을 담는가 |
|---|---|
| `centers` | 원. 파일럿 원 개수가 미정이라 여러 곳으로 열어뒀다 |
| `classes` | 반. `centers` 를 참조한다. 원마다 "씨앗반"이 있을 수 있어 `UNIQUE(center_id, name)` 이다. `age_min` · `age_max` 범위로 혼합반(3~5세 한 반)에 대응하며 단일 연령반은 두 값이 같다 |
| `children` | 아동. `classes` 를 참조한다. 이름은 평문 실명이다 |
| `activities` | 활동 풀. 규칙 엔진의 선별 층이 읽는다(ADR-005) |

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
   테스트는 가명으로**(ADR-004:64). LLM 호출 직전 치환기(`shared/childCode`)는 P1 에
   만든다(ADR-004:47).
4. `safety_flags` · `tags` 는 JSONB 라 **DB 가 모양도 어휘도 막지 않는다.** 시드
   스크립트의 YAML 대조가 유일한 방어선이다.
5. 연령은 **학년도 기준 연 나이**(3·4·5)다. 만 나이가 아니다. 반 편성이 3월 1일
   기준이고 누리과정도 "3~5세"로 표기한다.

## 없는 것과 그 이유

| 없는 것 | 이유 |
|---|---|
| `children.birth_date` | ADR-007:52 가 발달평가를 스펙아웃해 쓸 기능이 사라졌다. ADR-004:58 은 "이름만 받는다"고 정한다 |
| `users` / `classes.teacher_id` 의 FK | 인증이 8주차다. `teacher_id` 는 nullable 컬럼으로만 있다 |
| `plans` | 계획안 테이블이다. 다음 PR 에서 만든다 |
| `classes.school_year` | 학년도는 `plans` 가 든다. 순차 게이트 질의의 주체가 `plans` 다 |
| `centers.region` | 활동 쪽 지역 축이 미정이라 한쪽만 있으면 매칭이 안 된다 |
| `ON DELETE` 지정 | 삭제 생명주기가 미정이다. 암묵적 연쇄 삭제를 막고 명시적으로 정리한다 |
