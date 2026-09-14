# Theme Reference v0 / Yearly Golden Set 사용 메모

## 범위

- `theme_reference_v0.json`은 `GenerateYearlyPlan` P0용 **최소 후보 카탈로그**다.
- 국가 누리과정이 월별 주제를 정한 목록이 아니다.
- `applicable_months`는 저장소 샘플에서 실제로 관찰된 적용 월이다.
- `curriculum_links`는 공식 누리과정 5개 영역과의 **영역 수준 교육적 연계**다. 주제의 직접 출처나 국가 지정 관계가 아니다.
- `yearly_cases.json`은 문장 일치가 아니라 구조, Rule 경계, Reference 해석, Gate, Validation, Provenance를 검증한다.

## 검토한 근거

저장소의 실제 파일 수를 기준으로 확인했다. `references/README.md`의 예전 집계(연간 7, 월간 3, 주간 2)는 현재 폴더와 다르며, 2026-09-10 현재 실제 폴더에는 연간 42, 월간 13, 주간 3개 PDF가 있다.

Theme v0의 직접 근거는 텍스트와 렌더링을 모두 확인하기 쉬운 다음 연간 자료 4개다.

- 국공립 서충주어린이집: 만3·4·5세 별도 페이지
- 민간 예담어린이집: 문서 제목상 3~4세 통합 자료
- 민간 AP어린이집: 만5세 자료
- 민간 소답어린이집: 문서 제목상 만3~5세 자료

각 파일의 상대 경로, SHA-256, 페이지, 관찰 라벨은 JSON의 `origins`와 각 Theme의 `evidence`에 보존했다. 누리과정 연계는 보건복지부 고시 제2019-152호 PDF의 문서 해시와 영역 페이지를 함께 기록했다.

## 중요한 해석

- 9월과 10월의 `우리나라와 세계 여러 나라`, `가을과 자연`은 기관별 순서가 달랐다. 두 후보 모두 `[9, 10]`에만 적용 가능하게 두었으며 어느 한 순서를 표준으로 고정하지 않았다.
- 2월 표현은 `형님이 되어요`, `초등학교에 가요`, `성장한 우리 느껴보기`, `즐거웠던 우리 반`처럼 연령·기관별로 달랐다. 공통 의미 후보는 `성장한 우리`로 정규화하고 원문을 모두 남겼다.
- 행사 전용 Theme 또는 행사→Theme 점수 규칙은 근거가 없어 만들지 않았다. Golden Set은 입력 행사를 사용한다면 해당 기간과 `EVENT` Evidence를 보존하고, 입력하지 않은 행사를 만들지 않는지만 검증한다.

## Version / Provenance 의미

- 현재 수정본의 Theme Reference catalog version은 `theme-reference-v0.1.2`이다.
- Plan Item의 `THEME_REFERENCE` Evidence에서 `source_id`는 `theme_id`, `source_version`은 활성화된 Theme Reference catalog version을 사용한다.
- Theme record의 `themes[].source_version`도 해당 catalog version을 사용한다.
- 원본 샘플 또는 공식 PDF의 파일 버전은 `origin_id`가 가리키는 `origins[].sha256`에서 추적한다.
- 따라서 Theme Reference 자체의 version과 upstream 원본 파일 hash를 같은 필드로 섞지 않는다.

## 사람 검토 Gate — v0.1.2 승인 완료

`theme-reference-v0.1.2`는 사람 검토를 통과했다.

```text
domain_owner_approval : HUMAN_APPROVED
approved_by           : reviewer_ai_lead_001
approved_at           : 2026-09-11T01:11:07+09:00
```

검토는 다음 5개 기준으로 수행했고 결과는 `docs/theme-reference-v0-human-review.md`에 있다.

1. `origins`의 경로와 SHA-256이 저장소 파일과 일치하는가. → 5/5 일치
2. 각 `evidence`의 페이지·월·연령·관찰 라벨이 원문과 일치하는가. → 불일치 0건
3. 정규화된 `label`이 근거의 의미를 바꾸지 않는가. → v0.1.2에서 봄·여름·겨울을 최보수 표현으로 축소
4. `applicable_months`와 `age_conditions`가 샘플보다 넓게 과장되지 않았는가. → 과장 0건
5. `curriculum_links`를 영역 수준 연계로만 표시하는가. → 20건 전부 `EDUCATIONAL_ALIGNMENT`

### approved_by의 의미

`approved_by`는 **인증 provider의 로그인 `user_id`가 아니다.** P0에는 인증 구현이 없으므로 인증과 독립적인 opaque reviewer identifier를 쓴다. 형식은 `reviewer_<role>_<sequence>`이며 규칙은 `docs/open-decisions.md` **OD-N10**에 있다.

Plan Confirm의 담임교사 `actor_id`(OD-Y03)와는 **다른 개념이므로 섞지 않는다.** 전자는 Reference 카탈로그를 검토한 도메인 담당자이고 후자는 계획안을 확정한 교사다. 테스트 fixture(`user_fixture_teacher_001` 등)도 승인자 식별자로 쓰지 않는다.

### 활성화 규칙

runtime activation은 별도 필드가 아니라 `domain_owner_approval`에서 파생된다. 따라서 위 승인으로 실제 repository의 `is_active`가 `True`가 되고 `GenerateYearlyPlan`이 이 카탈로그를 사용할 수 있다. 별도 activation override나 우회 경로는 두지 않는다.

승인 metadata 변경만으로는 새 `catalog_version`을 발행하지 않는다. 내용이 바뀌면 새 버전을 발행한다(v0.1.1 → v0.1.2가 그 사례다).

미승인 카탈로그를 거부하는 Contract는 계속 유효하다. Golden Set의 `gate_unapproved_theme_reference`는 `PENDING_HUMAN_REVIEW`를 주입해 차단을 검증한다.

## 파일 위치

저장소에 반영할 상대 경로는 다음과 같다.

```text
data/themes/theme_reference_v0.json
data/themes/README.md
tests/golden/yearly_cases.json
```

이 JSON 구조는 P0 Application/Rule 테스트용 준비물이며 최종 HTTP API, DB Schema, 공개 오류 코드를 확정하지 않는다.
