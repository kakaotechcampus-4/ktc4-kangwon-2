# ADR-015: `evidence.source_id` 는 카탈로그가 아니라 그 안의 항목을 가리킨다

- 2026-09-22
- 상태 — 채택

## 맥락

`evidence[].source_id` 는 계획안의 한 칸이 **「이 값이 어디서 왔나」**를 가리키는 문자열이다.
교사가 S6 화면에서 근거를 눌렀을 때 펼쳐지는 값이고, 목요일에 만들 `evidence` 테이블의 컬럼이 된다.

**DB 에 값으로 저장되므로 나중에 바꾸면 행을 전부 마이그레이션해야 한다.**
`backend/resources/rules/safety_flags.yaml:11` 이 같은 성질의 키에 이미 적어 뒀다 —
*"키는 불변 슬러그다. 한 번 정하면 고치지 않는다."*

계약과 코드가 서로 다른 것을 가리키고 있었다.

```
docs/api-spec.md §4 예시                          "source_id": "theme-ref-2026"
generate_yearly_plan.py:125 (PR #25, 09-20 머지)   source_id=selection.candidate.theme_id
                                                   → "yr_theme_spring"
```

**틀린 값이 아니라 축이 다르다.** 앞은 자료 묶음(카탈로그) 하나를 가리키고, 뒤는 그 묶음 안의
항목 하나를 가리킨다. 계약이 이 둘 중 무엇인지 정한 적이 없어서 양쪽이 각자 갔다.

같은 이름이 계약 안에서 이미 두 가지를 뜻하는 것도 정리해야 했다.

```
§4   evidence[].source_id          문자열 슬러그        자료
§11  document_sources.source_id    정수 (관찰기록 행 id)  교사 기록   INDEX(source_kind, source_id)
```

## 결정

**`source_id` 는 자료 묶음이 아니라 그 안의 항목을 가리킨다.** 머지된 코드의 표기를 정본으로 삼고
계약을 거기 맞춘다.

```
THEME_REFERENCE      yr_theme_new_environment_friends   주제 참고자료 안의 주제 id
ACTIVITY_REFERENCE   act_outdoor_autumn_outing          활동 id
CURRICULUM           curriculum.mohw.notice-2019-152    고시 문서 id
PARENT_PLAN          상위 계획안의 plan id
```

규칙 셋을 같이 정한다.

1. **`source_id` 는 `source_type` 과 짝으로만 의미가 정해진다.** 타입마다 모양이 다르므로 한 필드를
   공통 규칙으로 파싱하지 않는다.
2. **불변 단위는 `source_id` 혼자가 아니라 `(source_type, source_id, source_version)` 셋이다.**
3. **새 자료의 `source_id` 는 자료 종류를 알아볼 수 있는 접두사로 시작한다.**

## 근거

**항목 id 여야 근거 표시가 작동한다** `[실측]`

카탈로그 id 를 쓰면 12개월이 전부 같은 값을 갖는다. `p0-planning/data/themes/theme_reference_v0.json`
에 `catalog_id` 는 `ssuksak.yearly-theme-reference` 하나뿐이다. 교사가 3월 근거를 눌렀을 때
「우리 원과 친구」 대신 참고자료 파일 전체가 뜬다 — 칸 단위 출처라는 기능 자체가 성립하지 않는다.

골든셋에는 12개 칸이 각각 다른 값을 갖고 있다
(`p0-planning/tests/finalization/golden/yearly.json`).

**`source_id` 혼자서는 불변일 수 없다** `[실측]`

`theme_id` 는 카탈로그 버전이 올라가면서 이미 한 번 개명됐다. 같은 파일 `change_summary` —
*"봄·여름·겨울 label 을 … 축소하고 **해당 theme_id 를 label 과 정렬했다**"* (v0.1.1 → v0.1.2).

`ThemeCatalog` 의 중복 검사도 **한 카탈로그 안에서만** 한다
(`p0-planning/src/ssuksak/planning/domain/theme_reference.py:182-184`).
버전 간 불변을 강제하는 코드는 없다.

그래서 「불변 슬러그」 요구는 `source_id` 혼자가 아니라 `source_version` 과 묶어서 지킨다.
`theme-reference-v0.1.2` 는 얼어 있으므로 그 안의 `yr_theme_spring` 은 영원히 같은 주제다.

**표기 통일 이득이 이미 절반 실현돼 있다** `[실측]`

네 타입 모두 이미 접두사를 갖고 있다 — `yr_theme_` · `act_` · `curriculum.` · `_plan_`.
구분자가 `_` 와 `.` 로 갈릴 뿐이고, 「값만 보고 종류를 안다」는 목적은 지금도 대체로 달성된다.

**바꾸는 비용이 크다** `[실측]`

표기를 바꾸면 `generate_yearly_plan.py` · `regenerate_yearly_plan_item.py` ·
`monthly_theme_derivation.py` 세 곳과 테스트, 그리고 **골든셋 12줄**을 같이 고쳐야 한다.
골든셋은 PR #33 `test(p0): finalize planning golden freeze and e2e` 로 develop 에 얼어 있고
`tests/finalization/test_freeze.py` · `test_golden.py` 가 지킨다.

**접두사 규칙은 근거가 없다** `[판단]`

3번 규칙(새 자료는 접두사로 시작)은 기존 값에서 관찰한 관행을 앞으로도 지키자는 것이지
측정된 근거가 아니다. 뒤집어도 된다.

## 대안

**네임스페이스를 새로 붙인다** (`theme.yr_theme_spring`) — 한 컬럼만 봐도 종류를 안다.
그러나 `source_type` 이 이미 그 정보를 들고 있어 같은 것을 두 번 적는다. `yr_theme_` 접두사가
이미 있어 `theme.yr_theme_spring` 처럼 접두사가 겹친다. 코드 3파일·테스트·골든셋을 고쳐야 한다.

**카탈로그 슬러그로 통일한다** (`ssuksak.yearly-theme-reference` 또는 `theme-ref-2026`) —
`catalog_id` 는 진짜 불변이라 이 축에서는 가장 강하다. 그러나 12개월이 전부 같은 값이 되어
근거 표시가 죽는다. `theme-ref-2026` 은 연도가 `source_version` 과 역할이 겹치고,
카탈로그가 없는 `PARENT_PLAN` 을 표현할 수 없다.

**카탈로그와 항목을 한 문자열에 담는다** (`ssuksak.yearly-theme-reference#yr_theme_spring`) —
문자열 하나로 자기완결적이다. 그러나 저장되는 행에 `source_type` 과 `source_version` 이 이미 같이
들어가므로 한 행을 읽으면 셋이 다 온다. 혼자 완결될 필요가 없는데 길어지고 파싱이 는다.

**`theme_id` 자체를 개명한다** (`theme.spring`) — 가장 깔끔한 표기가 나온다. 그러나 카탈로그
버전을 올리는 일이고, `catalog_version` 정확일치 조회(`json_theme_reference_repository.py:51-60`)라
로더·규칙·테스트·골든셋이 전부 따라 움직인다. 월요일 한 건이 아니다.

## 결과

- **`evidence` 테이블은 `source_id` 와 `source_version` 을 **같이** 저장해야 한다.**
  불변 단위가 셋이라 `source_version` 을 빼면 나중에 어느 판의 항목인지 복원할 수 없다.
  목요일 마이그레이션이 이걸 지킨다.
- **서버가 `source_id` 를 새로 짓지 않는다.** `p0-planning` 이 준 값을 그대로 저장하고 그대로
  내보낸다. 변환 계층을 두지 않는다 — 두면 DB 값과 도메인 값이 갈린다.
- **골든셋이 표기를 지킨다.** 누가 표기를 바꾸면 `test_golden.py` 가 깨진다. 별도 검사를 만들지 않는다.
- **`docs/api-spec.md` §4 예시는 골든셋 실측값을 쓴다.** 예시를 손으로 지어내면 또 갈라진다.
- **§11 `document_sources.source_id` 는 이 규칙의 대상이 아니다.** 정수 외래키이고 같은 컬럼이
  아니다. 이름이 같을 뿐이므로 한 테이블로 합치지 않는다.
- **`effective_date` 는 P0 에서 항상 `null` 이다.** `p0-planning/src` 어디서도 설정하지 않는다.
  계약에 명시했다 — FE 가 값이 온다고 가정하면 안 된다.
- 새 자료(안전교육 계획안·트렌드·기관 샘플)를 붙이는 사람은 `source_id` 접두사를 정하고 이 표에
  한 줄을 추가한다.
