# Activity Reference v0 사용 메모

## 현재 상태 — 승인 전이므로 runtime 사용 금지

```text
catalog_version       : activity-reference-v0.1.0
domain_owner_approval : PENDING_HUMAN_REVIEW
runtime active        : false  (승인 상태에서 파생)
```

**이 Catalog는 아직 사람 승인을 받지 않았다.** `JsonActivityReferenceRepository`로
로드하면 `is_active`가 `False`이고 `eligible_candidates(...)`는 어떤 월·연령
조합에서도 빈 결과를 반환한다. 의도된 동작이다.

승인 전에 runtime 후보로 사용하거나, `approved_by` / `approved_at`을 승인된 값처럼
채우지 않는다. 승인 절차는 Theme Reference v0의
`PENDING_HUMAN_REVIEW → HUMAN_APPROVED` 절차를 그대로 따른다. 검토 자료는
`docs/activity-reference-v0-human-review.md`에 있다.

### 승인 보류 사유 (OD-N03 D1 결정, 2026-09-11)

확보된 월간 Activity 표본이 **2026-09 중심 + 2026-03 일부**뿐이다. 12개월 전체
Activity Reference를 `HUMAN_APPROVED` 하기에 부족하다. 추가 월간 표본으로 월
커버리지를 확장한 뒤 별도 Human Review로 승인한다.

현재 자료의 성격은 "전체 서비스용 완성 Activity Catalog"가 아니라
**Activity Reference Contract 검증용 실제 seed**다.

---

## 범위

- `activity_reference_v0.json`은 Monthly `outdoor_play` Cell의 Rule 후보 집합을
  위한 **최소 seed 카탈로그**다.
- `normative_status`는 **`SAMPLE_DERIVED_NON_NORMATIVE`**다.
- **국가가 지정한 활동 목록이 아니다.** 2019 개정 누리과정 고시문은 활동·주제·계획
  양식을 규정하지 않고 기관 자율에 위임한다(`Ⅱ. 누리과정의 운영 > 1. 편성·운영 다`).
- `applicable_months`는 실측 샘플에서 **실제로 관찰된 월**이며 국가가 정한 월별
  필수 활동이 아니다.
- `curriculum_links`는 누리과정 5개 영역과의 **영역 수준 교육적 연계**이며 Activity의
  직접 국가 지정 출처가 아니다. 현재 seed는 근거 부족으로 **전부 빈 배열**이다.

---

## 월 Coverage가 12개월 전체가 아니다

```text
month_coverage : [3, 9]
```

| 월 | 후보 수 |
|---|---:|
| 3월 | 8 |
| 9월 | 42 |
| 그 밖 10개월 | **0** |

나머지 월은 후보가 없다. 추론으로 채우지 않았고, **Theme Reference의
`applicable_months`를 Activity 근거로 전용하지 않았다.**

월 커버리지 공백은 Catalog를 끄는 방식으로 표현하지 않는다. Catalog는 승인되면
활성이고 해당 월의 후보만 0이다. 같은 Catalog가 9월에는 정상 동작해야 하므로
Catalog 단위 on/off로 표현하면 안 된다.

---

## 외부 scraping을 사용하지 않았다

저장소 안의 실측 Monthly Sample만 사용했다.

```text
사용한 source : references/samples/monthly/ (14파일 / 12기관, 판독 13파일 / 11기관)
외부 네트워크 접근 : 0건
scraping        : 0건
```

키드키즈·꼬망세·블로그·검색 결과 등 외부 사이트에 접속하거나 수집하지 않았다
(OD-N03 D2 결정: P0 NO-GO). 외부 Activity Source를 영구 제외한다는 뜻은 아니며,
이용 허가·라이선스·사용자 제공 자료가 확보되면 별도 결정으로 다룬다.

향후 외부 source를 쓰기로 결정하면 `origins[].kind`에 `EXTERNAL_SITE`를 추가하고
`license` / `permission_basis` / `retrieved_at`을 origin에 두는 방향을 권장한다.
이번 v0에는 구현하지 않았다.

---

## 기관 고유 시설 / 지역 Activity를 제외했다

특정 기관·지역에 종속되는 값은 공통 runtime Candidate로 만들지 않았다
(OD-N03 D3 결정).

제외 예:

```text
만수계곡 자연관찰로 / 탄금공원 물놀이장 / 탄금대숲 / 능암늪생태공원
성불산 숲체험 / 무궁화길 산책 / 어린이 민속박물관 / 롤러장 나들이
기관 텃밭 / 우리 원 주변 / 우리 원 사진 / 3D러닝플레이(기관 특별프로그램)
```

**의미를 바꿔 일반화하지 않았다.** `만수계곡 자연관찰로` → `나들이` 같은 변환을
하지 않는다. 원문 분석 근거로 보존할 필요가 있는 항목은
`exclusion_policy.excluded_items`에 원문·기관·페이지·제외 사유로 남겼고 runtime
후보에는 포함하지 않았다.

`바깥 놀이터`, `공원`처럼 고유명사가 아닌 일반 명사는 제외 대상이 아니다.

---

## Safety content를 제외했다

```text
Activity Reference
  ≠ SafetyEducationPlan     (기관 연간 안전교육 배치계획)
  ≠ SafetyLegalRule         (data/rules/safety_education_legal_v1.json)
```

- `safety_education` Cell은 이 Catalog에서 채우지 않는다.
- `placement_slots`에 `safety_education`을 넣을 수 없다. Domain과 schema가 모두
  거부한다(`FORBIDDEN_PLACEMENT_SLOTS`).
- `safety_flags` 필드를 두지 않는다. schema가 그 키를 거부한다.
- 법정 안전교육의 배치 source는 기관 안전교육 연간계획 또는 교사 입력이며(OD-M04)
  Activity Reference가 그 역할을 대신하지 않는다.
- 안전 경계가 모호한 항목(`바깥놀이를 안전하게 해요`)도 보수적으로 제외했다.

`data/rules/safety_education_legal_v1.json`은 이번 작업에서 변경하지 않았다.

---

## activity_area는 아직 OPEN이다

```text
M2-A에서 확정한 통제 어휘 : placement_slots, setting
여전히 OPEN                : activity_area, tags, safety_flags
```

`art` / `physical` / `language` / `sensory` / `nature` / `role_play` 같은
`activity_area` enum을 **추측으로 만들지 않았다.** `references/README.md §4.2`가
`curriculum_domain ≠ activity_area ≠ plan_slot`을 명시하면서 `activity_area`의 값
목록은 제공하지 않으며, OD-N03에서 그 어휘 확정이 미결 항목이다.

관련 실측(흥미영역 쌓기·역할·언어·수조작·음률·미술·과학, 4/10 기관)은 Template A에서
아직 정의되지 않은 `play` Section의 depth-2 하위에 걸려 있어 `outdoor_play` Slice에
필요하지 않다.

`safety_flags`는 법정 Safety와의 혼선을 피하기 위해 의도적으로 두지 않는다.

---

## 통제 어휘 2개

### `placement_slots[]`

```text
P0 허용 : outdoor_play
금지    : safety_education
```

자유 문자열이 아니라 `data/templates/monthly_template_a.json`
(`monthly-template-a-v0.1.0`)의 `semantic_key`에 종속되는 통제 어휘다. Activity가
Template에 없는 slot을 주장할 수 없다.

`focus`와 `indoor_alternative`는 Template A에서 default inactive이고
`indoor_alternative`의 `display_mode`가 아직 `PENDING_HUMAN_DECISION`이므로
포함하지 않았다. 넓히려면 Template 쪽 결정이 선행되어야 한다.

### `setting`

```text
OUTDOOR / INDOOR / EITHER
```

활동이 이루어지는 물리 환경이다. **`indoor_alternative` Section과 같은 개념이
아니다.** 실내대체는 바깥놀이가 불가능할 때 대신하는 별도 Section이고 `INDOOR`
Activity는 애초에 실내를 전제하는 활동이다.

`[실내대체]` · `[대체]` · `(대체활동: …)` inline 태그가 붙은 항목은
`indoor_alternative` Section 소속이므로 outdoor 후보로 전사하지 않았다. 같은 놀이가
다른 기관에서 직접 바깥놀이 항목으로 관찰된 경우에만 그 근거로 후보가 됐다.

이 seed의 49개 항목은 전부 바깥놀이 행에서 관찰된 `OUTDOOR`다.

---

## 연령 Contract

```text
supported_ages[]                  관찰된 age_scope의 합집합
allow_mixed_age                   true
mixed_age_requires_all_supported  true
```

`min_age` / `max_age`를 쓰지 않는다. 이유:

1. `ClassroomContext.ages`가 `frozenset[int]`이므로 `issubset`이 직접 맞는다.
2. 만 3~5세는 값이 3개뿐이어서 범위 표현의 이득이 없다.
3. CLAUDE.md §11이 Activity의 `age_min`/`age_max`를 Classroom 연령 구성과
   "서로 다른 개념"으로 명시한다. min/max를 쓰면 두 개념이 이름으로 섞인다.

혼합연령 반을 위해 Activity를 복제하지 않는다. 같은 record가 `{3}` 반과 `{3,4}` 반
모두에서 후보가 된다.

`evidence[].age_scope`는 문서가 **명시적으로** 다루는 연령 범위다. 본문에 연령
표기가 없는 문서는 빈 배열이며 **파일명 표기로 추론하지 않는다.** 따라서
`supported_ages`에 연령 공백이 있는 항목이 존재한다(예: 강강술래 = `[3, 5]`).
이는 데이터 품질 문제이며 Human Review 대상이다.

---

## Theme 연결

```json
"theme_links": [
  { "theme_id": "yr_theme_korea_and_world_cultures",
    "relation": "OBSERVED_TOGETHER",
    "theme_catalog_version": "theme-reference-v0.1.2" }
]
```

- 같은 Monthly source 페이지에서 해당 theme과 **함께 관찰됐다는 사실만** 뜻한다.
- `BELONGS_TO` 같은 규범적 관계를 주장하지 않는다. Domain이 그 값을 거부한다.
- 문자열 유사도 매칭으로 만들지 않았다.
- 다대다를 허용한다. Theme 1:1을 강제하지 않는다.
- 링크마다 `theme_catalog_version`을 기록한다. Theme Reference가 새 version으로
  올라가도 "어느 version 기준으로 검토된 연결인지"가 남는다.
- Theme catalog 버전업으로 `theme_id`가 사라지면 링크를 삭제하지 않고 Rule이 매칭
  실패로 취급한다. theme link는 **hard filter가 아니므로** 후보 집합이 비지 않는다.

---

## 중복 처리 — canonical + aliases

- **자동 merge와 LLM merge를 하지 않았다.**
- 판정이 애매하면 분리했다. 잘못 합치면 provenance가 사라지고, 잘못 분리하면 후보만
  중복되므로 비대칭 위험에서 보수적인 쪽을 택했다.
- `aliases`는 사람이 같은 활동의 표현 변이로 판단해 승인한 표현 집합이다.
- `evidence[].observed_label`은 특정 기관·페이지의 **원문**이며 감사용으로 삭제하지
  않는다. 표현이 다른 근거에는 `matched_via: RELATED_EXPRESSION`과 `match_note`를
  남겼다.

분리한 사례:

```text
전통놀이            vs  전통 놀이 한마당      (단일 놀이 vs 행사형 구성)
바람개비 들고 달리기 vs  바람개비 돌리며 가을 느끼기  (동작이 다르고 후자는 연령 근거 없음)
모래로 전통음식 만들기 vs 젖은 모래로 떡을 만들어요   (후자는 연령 근거 없음)
```

---

## Version / Provenance 의미

- 현재 Activity Reference catalog version은 `activity-reference-v0.1.0`이다.
- `activities[].source_version`은 해당 record를 담은 **catalog version**이다.
- 원본 샘플 파일의 version은 `activities[].origin_id`가 가리키는
  `origins[].sha256`에서 추적한다.
- Activity Reference 자체의 version과 upstream 원본 파일 hash를 같은 필드로 섞지
  않는다.
- Monthly Cell Evidence의 canonical `source_id`는 **`activity_id`**이며 `origin_id`나
  PDF hash가 이를 대신하지 않는다.
- `EvidenceSourceType.ACTIVITY_REFERENCE`는 이미 존재한다. 공용 Provenance Enum을
  변경하지 않았다.
- **Monthly Cell에 `ACTIVITY_REFERENCE` Evidence를 붙이는 것은 M2-C 작업이다.**
  M2-A는 Reference Foundation까지만이다.
- 자기 content hash를 파일에 저장하지 않는다. Theme Reference와 동일한 선례이며,
  자기 참조 필드는 갱신 누락 시 조용히 거짓이 된다.

---

## 활성화 규칙

runtime activation은 별도 필드가 아니라 `review.domain_owner_approval`에서
**파생**된다.

```text
HUMAN_APPROVED        → active
PENDING_HUMAN_REVIEW  → inactive
```

JSON에 `runtime_active`나 `activation_status` 키를 두면 schema가 **거부**한다.
activation을 독립 writable 값으로 만드는 경로를 없앤다.

테스트는 `activation_override`로 승인 상태 동작을 검증하며 **실제 파일을 수정하지
않는다.** 이 파라미터는 Application 경계의 caller가 전달하는 입력이 아니다 —
`get_catalog(catalog_id, catalog_version)` 시그니처에 승인 관련 인자가 없다.

승인 metadata 변경만으로는 새 `catalog_version`을 발행하지 않는다. 내용이 바뀌면 새
version을 발행하고 `supersedes`로 연결한다.

---

## 파일 위치

```text
data/activities/activity_reference_v0.json
data/activities/README.md
docs/activity-reference-v0-human-review.md
src/ssuksak/planning/domain/activity_reference.py
src/ssuksak/adapters/activity_reference_schema.py
src/ssuksak/adapters/json_activity_reference_repository.py
```

이 JSON 구조는 P0 Application/Rule 테스트용 준비물이며 최종 HTTP API, DB Schema,
공개 오류 코드를 확정하지 않는다.

---

## 추출 방법

```text
pdftotext -layout -enc UTF-8   격자 구조
pdftotext -raw    -enc UTF-8   셀 읽기 순서 교차 확인
pdfplumber 셀 기하 재구성       바깥놀이 행 귀속 확정
```

`-layout`만으로는 병합 라벨 셀이 인접 행으로 번져 행 귀속을 잘못 판단한다. 세 방법을
교차 확인해 바깥놀이 행을 확정했다.

분석 도구(`pdfplumber`, `PyMuPDF`)는 `pip install --target`으로 격리 설치했으며
**프로젝트 Python dependency가 아니다.** `pyproject.toml`에 추가하지 않았다.
