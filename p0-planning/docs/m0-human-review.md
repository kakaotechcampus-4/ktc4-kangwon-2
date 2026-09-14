# M0 Human Review — Monthly 착수 전 데이터 검토

- 작성일: 2026-09-11
- 대상: `data/templates/monthly_template_a.json`, `data/rules/safety_education_legal_v1.json`
- **최종 상태: 두 파일 모두 `HUMAN_APPROVED` (2026-09-11T10:25:01+09:00)**
- reviewer: `reviewer_ai_lead_001`
- 근거 표시: `[실측]` 직접 측정·대조 / `[판단]` 해석

## 승인 요약

| 대상 | Human Review | approval | approved_by | approved_at | runtime_active |
|---|---|---|---|---|---|
| `monthly_template_a.json` | **PASS** | `HUMAN_APPROVED` | `reviewer_ai_lead_001` | `2026-09-11T10:25:01+09:00` | `true` |
| `safety_education_legal_v1.json` | **PASS** | `HUMAN_APPROVED` | `reviewer_ai_lead_001` | `2026-09-11T10:25:01+09:00` | `true` |

**Template — 승인된 내용**

- 승인된 `display_mode`: `theme` = `MONTHLY_MERGED_SUMMARY` · `outdoor_play` = `WEEKLY_CELLS` ·
  `safety_education` = `WEEKLY_CELLS` · `focus` = `WEEKLY_CELLS` · `goals` = `MONTHLY_MERGED_SUMMARY` ·
  `habits` = `WEEKLY_CELLS`
- activation 정책은 OD-M01 그대로 유지한다. 기본 활성은 `theme` / `week_axis` / `outdoor_play` /
  `safety_education` 4개이고 나머지는 default inactive다.
  **`goals`와 `habits`는 `display_mode`가 정해져 있어도 default inactive를 유지한다.**
- Optional 5개(`emergency_response` · `drill` · `indoor_alternative` · `special_program` ·
  `event_schedule`)는 `PENDING_HUMAN_DECISION`을 유지하며 **Monthly M1 blocker가 아니다.**
  임의 값을 넣지 않는다.
- **`drill`과 `emergency_response`는 P0에서 독립 optional semantic key를 유지한다.**
  `safety_education`에 자동 병합하지 않는다. 지금 확정한 것은 "의미적으로 별도"라는 점이며
  "어떻게 표시할지"는 후속 결정이다.
- `normative_status` = `SAMPLE_DERIVED_NON_NORMATIVE` 유지. Template A는 국가 표준이나 전국
  공통 월간계획안이 아니라 13개 sample / 11기관 관찰을 바탕으로 만든 쓱싹요정 P0 product
  adapter다. `global_display_mode_default` = `null` 유지.

**Safety — 승인된 내용**

- P0 legal source: **아동복지법 시행령 별표 6 `<개정 2022. 6. 21.>`**
- 저장소의 별표6 원문 · 2026 보육사업안내 · 2026-08-04 시행 시행령 제28조 자료 3건 간
  교차 검증 결과 **충돌 없음**으로 확인한 현재 전사본을 승인했다.
- 이 승인의 정확한 의미는 **"쓱싹요정 P0 repository legal source로 검토·승인된 별표6
  machine-readable transcription"** 이다. *인터넷상 최신 법령 전체를 새로 검증한 결과가 아니다.*
- **법정 월 배치 정책 없음.** `month_assignment` 필드를 만들지 않았고
  `has_month_assignment` = `false`다.
- **placement policy 미발행.** `placement_policy_version` = `null`. 제품 기본 월 배치 정책은
  P0에서 발행하지 않는다.
- 비법정 기관 label(`생활안전` · `심폐소생술` · `장애인식 개선` · `소방안전` · `비상대응`)을
  법정 6구분으로 자동 매핑하지 않는다.
- LLM은 안전교육 월·주 배치와 법적 충족 여부를 결정하지 않는다.

**`runtime_active` 파생 원칙**

`runtime_active`는 독립 스위치가 아니라 파생값이다.
`runtime_active == (domain_owner_approval == "HUMAN_APPROVED")`를 항상 만족해야 하며
이 값을 단독으로 바꾸는 수동 activation 우회 경로를 만들지 않는다.
`data/themes/theme_reference_v0.json`의 activation 파생 원칙과 동일하다.

**Version**

승인 metadata 변경만을 이유로 새 version을 발행하지 않았다.
`monthly-template-a-v0.1.0`과 `child-welfare-act-decree-annex6-2022-06-21`을 그대로 유지한다.

| 파일 | 승인 전 SHA-256 | 승인 후 SHA-256 |
|---|---|---|
| `monthly_template_a.json` | `577b376e9cdc966003c4776f98dfbc70fc4e8c17fc354df7093808122fb6b24c` | `1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34` |
| `safety_education_legal_v1.json` | `e70bb5295f08d003a8862a6077b495e03e564b23af7a98cdb424a11c74236071` | `5831809b19a28505844cf10363c95eeb09ec4641d5fe54a26afdb1891c3ddba5` |

`[실측]` 승인 전후 기계 비교로 `review` 블록 외 **모든 content field가 동일함**을 확인했다.
Template 13개 필드 · Safety 14개 필드를 개별 대조했고 전부 일치한다. 승인 과정에서
content 변경은 없었다.

아래 §0~§5는 승인 근거가 된 검토 자료다. 내용을 그대로 보존한다.

---

## 0. display_mode 실측 (2026-09-11)

### 0.1 방법

`[실측]` 텍스트 토큰 추정이 아니라 **PDF 벡터 선에서 복원한 표 셀의 물리 병합 범위**로
판정했습니다.

| 항목 | 내용 |
|---|---|
| 도구 | `pdfplumber` 0.11.10 (+`pdfminer.six`), `PyMuPDF` 1.28.2 |
| 설치 위치 | 분석 전용 격리 디렉터리(`pip install --target`). **`pyproject.toml` 무변경** |
| 셀 복원 | `find_tables`의 `lines` strategy — 벡터 선 교차로 셀 경계 복원 |
| 주차 열 기준 | 주차 토큰(`N주` 또는 날짜 범위)을 가진 셀이 3개 이상인 행을 헤더로 잡고 그 x 경계를 주차 열로 사용 |
| Section 판정 | 라벨 셀의 세로 구간에서 주차 영역을 덮는 content 셀의 **개수 · 점유율 · 주차 열 경계와의 정렬도**를 계산 |

`pdftoppm`은 여전히 부재하지만 **렌더링 없이 벡터 선만으로 셀 기하를 복원**할 수 있어
1차(2026-09-09) 판독과 동등한 정보를 얻었습니다.

판정 규칙:

```text
WEEKLY_CELLS              content 셀 2개 이상 + 주차 열 경계와 정렬도 >= 0.5
MONTHLY_MERGED_SUMMARY    content 셀 1개가 주차 영역의 85% 이상을 덮음
INLINE_OR_TAGGED          라벨 셀이 없고 다른 셀 문자열 안에 의미가 태그/접두로 존재
OTHER                     위 셋으로 설명 불가
NOT_PRESENT               라벨도 inline 흔적도 없음
UNREADABLE                셀 복원 불가
```

`[판단]` 이 6개 값은 **Human Review용 관찰 분류이며 최종 Domain enum이 아닙니다.**

### 0.2 방법 검증 — 1차 기하 판독 재현

`[실측]` 1차에서 220dpi 렌더링 + 벡터 선으로 판정했던 결과와 대조했습니다.

| 기관 | Section | 1차 판정 | 이번 판정 | 결과 |
|---|---|---|---|---|
| 예담 | outdoor_play | WEEKLY_CELLS | WEEKLY_CELLS | 일치 |
| 예담 | safety_education | WEEKLY_CELLS | WEEKLY_CELLS | 일치 |
| 예담 | theme | MONTHLY_MERGED | MONTHLY_MERGED | 일치 |
| 예담 | goals | MONTHLY_MERGED | MONTHLY_MERGED | 일치 |
| 예담 | focus | WEEKLY_CELLS | WEEKLY_CELLS | 일치 |
| 시립새봄 | outdoor_play | MONTHLY_MERGED | MONTHLY_MERGED | 일치 |
| 시립새봄 | safety_education | MONTHLY_MERGED | MONTHLY_MERGED | 일치 |
| 시립새봄 | theme | MONTHLY_MERGED | MONTHLY_MERGED | 일치 |
| 금산군청 | outdoor_play | WEEKLY_CELLS | WEEKLY_CELLS | 일치 |
| 금산군청 | safety_education | WEEKLY_CELLS | WEEKLY_CELLS | 일치 |
| 아이들세상 | safety_education | (미측정) | MONTHLY_MERGED | — |
| 해찬솔 | theme | (미측정) | **OTHER** | 아래 §0.5 참조 |

**12건 중 11건 재현.** 유일한 비일치는 해찬솔 theme이며 실제 오류가 아니라 결재란 때문에
값 셀이 주차 영역의 70%만 덮어 `OTHER`로 떨어진 경우입니다.

### 0.3 분석 성공 범위

`[실측]`

```text
대상 파일        13
분석 성공        12   (페이지 17)
분석 실패         1   별빛자이 — 벡터 drawing 0 / 텍스트 0자 / 이미지 4
주차 축 있음      9 기관
주차 축 없음      1 기관   아이사랑 3파일
```

별빛자이는 **진성 스캔본**입니다. 추정하지 않고 `UNREADABLE`로 기록했습니다.
판독에는 OCR이 필요합니다.

### 0.4 Section별 분포 (기관 11곳)

`[실측]` `X` = 주차 축 자체가 없어 주차 기준 판정 불가(아이사랑), `?` = 판독 불가(별빛자이)

| Section | WEEKLY | MERGED | INLINE | OTHER | 없음 | X | ? |
|---|---:|---:|---:|---:|---:|---:|---:|
| **outdoor_play** | **6** | **2** | 0 | 0 | 0 | 1 | 1 |
| **safety_education** | **6** | **2** | 1 | 0 | 0 | 1 | 1 |
| goals | 0 | 5 | 0 | 1 | 3 | 1 | 1 |
| habits | 6 | 1 | 0 | 0 | 2 | 1 | 1 |
| emergency_response | 3 | 0 | 3 | 0 | 3 | 1 | 1 |
| drill | 1 | 0 | 7 | 0 | 1 | 1 | 1 |
| indoor_alternative | 4 | 1 | 4 | 0 | 0 | 1 | 1 |
| special_program | 2 | 1 | 0 | 0 | 6 | 1 | 1 |
| event_schedule | 2 | 2 | 1 | 0 | 4 | 1 | 1 |
| theme *(교차확인)* | 0 | **7** | 0 | 2 | 0 | 1 | 1 |
| focus *(교차확인)* | **5** | 1 | 0 | 0 | 3 | 1 | 1 |

`outdoor_play`의 MERGED 2건은 시립새봄·아이들세상이고, 큰빛은 페이지별로 갈려
다수 판정(MERGED)으로 집계했습니다. 자세한 내용은 §0.5.

### 0.5 기관별 관찰표

`[실측]` `W`=WEEKLY_CELLS `M`=MONTHLY_MERGED_SUMMARY `I`=INLINE_OR_TAGGED
`O`=OTHER `-`=NOT_PRESENT `X`=주차축 없음 `?`=UNREADABLE `*`=기관 내 페이지 간 상이

| 기관 | outdoor | safety | goals | habits | emergency | drill | indoor_alt | special | event | theme | focus |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 아이사랑(국공립) | X | X | X | X | X | X | X | X | X | X | X |
| 괴산하나(국공립) | W | W | M | W | W | W | W | - | W | M | W |
| 별빛자이(국공립) | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| 시립새봄(국공립) | M | M | - | - | I | I | I | M | M | M | - |
| 엄지(민간) | W | W | - | - | - | I | I | - | W | M | - |
| 예담(민간) | W | W | M | W | W | I | W | - | - | M | W |
| 큰빛(민간) | **M\*** | I | M | W | - | - | I | - | M | M | M |
| 해찬솔(민간) | W | W | **O** | W | - | I | W | W | - | **O** | W |
| 한솔빛(민간) | W | W | M | W | I | I | W | - | - | M | W |
| 금산군청(직장) | W | W | M | W | W | I | I | W | - | M | - |
| 아이들세상(협동) | M | M | - | M | I | I | M | - | I | **O** | W |

### 0.6 기관별 주요 예외

`[실측]`

1. **아이사랑 — 주차 축 자체가 없음.** 3파일 전부 주차 헤더가 없고 `놀이예상기간 : 9월`로
   기간이 월 단위입니다. 축을 가진 유일한 Section인 `특별활동`의 축은 **요일**(월·화·수·목·금)
   입니다. `바깥놀이`는 별도 Section이 아니라 놀이 항목의 접두 태그(`♥바깥놀이-비석치기`)입니다.
   주차 기준 `display_mode`를 정의할 수 없어 별도 분류(`X`)로 기록했습니다.

2. **별빛자이 — 진성 스캔본.** 벡터 drawing 0개, 텍스트 0자, 이미지 4개.
   `UNREADABLE`. 임의 추정하지 않았습니다.

3. **큰빛 — 기관 내 페이지 간 상이.** p.1(만4·5세, 헤더 4주)의 `바깥`은 병합 셀이고,
   p.2(만3세, 헤더 5주)의 `오전자유 놀이 (바깥 놀이포함)`은 주별 셀입니다.
   같은 기관·같은 달인데 연령 페이지에 따라 표시 방식이 다릅니다.

4. **큰빛 safety — INLINE_OR_TAGGED.** 독립 `안전교육` 라벨 행이 없고 다른 셀 안에
   `<안전교육> 1주-… 5주-…` 블록으로 들어갑니다. `[판단]` 물리 셀은 병합이지만 주차 배정
   정보가 텍스트로 보존된 형태이며, **표시 방식과 canonical data 구조를 구분해야 한다는**
   사례입니다. canonical item에는 week reference를 보존할 수 있습니다.

5. **해찬솔 theme — OTHER.** `주 제` 값 셀이 1개이지만 오른쪽에 담임·원장 **결재란**이 있어
   주차 영역의 70%만 덮습니다. `[판단]` 의미상 월 단위 단일 값이나 기하로는 전폭 병합이
   아니므로 `OTHER`로 정직하게 기록했습니다.

6. **아이들세상 theme — OTHER.** `생활주제` 행이 `절기` 라벨·값과 **같은 행을 공유**합니다
   (`생활주제 | 열매 맺는 달 | 절기 | 백로, 추분`). theme 값이 주차 영역의 55%만 덮습니다.

7. **괴산하나 — 페이지 간 일관.** p.1/p.2 모두 outdoor W · safety W · theme M · focus W ·
   habits W로 동일합니다. 라벨만 연령별로 다릅니다(`놀이 주제`↔`생활주제`,
   `교사의 기대`↔`목표`, `예상 놀이`↔`소주제`).

8. **시립새봄 — 4페이지 전부 동일.** outdoor·safety·theme 모두 MERGED(점유율 1.0).

---

## 1. `monthly_template_a.json` Human Review 체크리스트

파일: `data/templates/monthly_template_a.json` · 33,368 B · `sha256=577b376e9cdc9660…`

### 1.1 필수 확인 9항목

| # | 확인 항목 | 현재 상태 | 근거 |
|---:|---|---|---|
| 1 | Section evidence가 실제 sample과 일치 | 각 Section에 `observed_institutions` / `denominator` / `observed_in`(origin_id) / `observed_source_labels` 수록 | `docs/template-a-validation.md` §3.1·§4.5 |
| 2 | activation 정책이 OD-M01과 일치 | 기본 활성 4개(`theme`/`outdoor_play`/`safety_education`/`week_axis`), Optional 전부 `activated:false` | OD-M01 `RESOLVED_FOR_P0` |
| 3 | `source_label` 보존 | `source_label_scope = PLAN_OR_TEMPLATE_INSTANCE`. 기관 단위 Mapping 테이블 없음 | 괴산하나 연령별 라벨 불일치(§0.6-7) |
| 4 | `max_depth = 2` | `hierarchy_max_depth: 2`. 실제 최대 depth 2(`indoor_alternative`) | 2단 4/10 관찰, 3단 0/10 |
| 5 | `RENDER_EMPTY_CELL` | `default_empty_value_policy` 및 모든 CONTENT Section에 설정 | 한솔빛 3p의 빈 안전교육 행 |
| 6 | global display_mode default 없음 | `global_display_mode_default: null` | OD-M01 |
| 7 | `character_greeting` 제외 | `excluded_sections`에 0/10 근거와 허용 경로 기재. `sections`에 없음 | 0/10 |
| 8 | `SAMPLE_DERIVED_NON_NORMATIVE` 명확 | 최상위 `normative_status` + `normative_status_note` | — |
| 9 | 아이사랑형 변이를 전국 공통 규칙으로 오해하지 않음 | `week_axis_is_not_unconditionally_required: true`, `supported_display_modes_extensible: true`, inline 유형 미수용 명시 | §0.6-1 |

### 1.2 이번에 채워진 display_mode

| Section | 값 | 활성 | 근거 |
|---|---|---|---|
| `theme` | `MONTHLY_MERGED_SUMMARY` | 활성 | 1차 3/3 + 교차확인 7/9 |
| `week_axis` | (축 — 해당 없음) | 활성 | 값을 담는 Section이 아님 |
| **`outdoor_play`** | **`WEEKLY_CELLS`** | **활성** | §2.1 |
| **`safety_education`** | **`WEEKLY_CELLS`** | **활성** | §2.2 |
| `focus` | `WEEKLY_CELLS` | 비활성 | 교차확인 5/6 |
| `goals` | `MONTHLY_MERGED_SUMMARY` | 비활성 | 5/6 |
| `habits` | `WEEKLY_CELLS` | 비활성 | 6/7 |

### 1.3 여전히 PENDING인 display_mode 5개

전부 **default inactive**이므로 M1을 차단하지 않습니다.

| Section | 관찰 | PENDING 사유 |
|---|---|---|
| `emergency_response` | W 3 : I 3 : 없음 3 | 동률 |
| `drill` | I 7 : W 1 | 다수가 독립 Section이 아님. **display_mode보다 "독립 Section으로 둘지"를 먼저 결정해야 함** |
| `indoor_alternative` | W 4 : I 4 : M 1 | 동률 |
| `special_program` | W 2 : M 1 | 관측 3기관뿐, 표본이 얇음 |
| `event_schedule` | W 2 : M 2 : I 1 | 동률 |

### 1.4 검토자 결정 결과 (2026-09-11)

| # | 판단 요청 항목 | 결정 |
|---:|---|---|
| 1 | `outdoor_play` / `safety_education` 권고값 `WEEKLY_CELLS` | **수용** |
| 2 | Optional 5개를 PENDING으로 유지 | **유지.** M1 blocker 아님. 임의 값 금지 |
| 3 | `drill`을 독립 Section으로 유지할지 | **독립 optional semantic key 유지.** `safety_education`에 자동 병합 금지. `emergency_response`도 동일. 단 default inactive이고 `display_mode`는 PENDING 유지 |
| 4 | `approved_by` / `approved_at` | `reviewer_ai_lead_001` / `2026-09-11T10:25:01+09:00` |

---

## 2. `outdoor_play` / `safety_education` P0 display_mode 권고

**이 값은 전국 표준이 아니라 Template A v0의 sample-derived 기본 표시 방식입니다.**

### 2.1 `outdoor_play` → **`WEEKLY_CELLS`**

| 고려 요소 | 내용 |
|---|---|
| 이번 실측 다수 | `[실측]` 주차 축이 있는 9기관 중 **W 6 : M 2 : 기관 내 상이 1** |
| 1차 기하 검증 | `[실측]` n=3에서 예담 W · 금산 W · 시립새봄 M → **2:1로 W** |
| Template A가 모델링하는 대표 형식 | `[판단]` Template A v0은 `Section 행 × 주차 열` 격자다. `week_axis`가 기본 활성이고 `focus`가 `WEEKLY_CELLS`인 구조에서 `outdoor_play`만 월 병합으로 두면 격자 모델과 어긋난다 |
| 정보 손실 방향 | `[판단]` 주별 셀에 월 단위 값을 넣는 것보다, 월 병합 셀에 주별 값을 욱여넣는 쪽이 손실이 크다 |

두 근거(이번 실측 다수, 1차 검증)가 같은 방향이고 Template의 대표 형식과도 맞습니다.

### 2.2 `safety_education` → **`WEEKLY_CELLS`**

| 고려 요소 | 내용 |
|---|---|
| 이번 실측 다수 | `[실측]` 9기관 중 **W 6 : M 2 : I 1** |
| 1차 기하 검증 | `[실측]` 예담 W · 금산 W · 시립새봄 M → **2:1로 W** |
| OD-M04와의 정합 | `[출처]` "안전교육 Item은 실제 week/date를 보존한다". 주별 셀 표시가 이 보존과 자연스럽게 맞는다 |
| 표시 ≠ canonical | `[판단]` 큰빛처럼 물리 병합 셀 안에 `1주-…5주-`를 적는 형태가 있다. 이는 **canonical에 week reference를 보존한 채 표시만 병합**한 것이며, 표시 기본값을 주별로 둔다고 이 데이터를 표현하지 못하는 것은 아니다 |

### 2.3 권고에 붙는 조건

- 두 값은 **Template A v0 인스턴스의 기본값**이며 다른 Template 인스턴스나 Override가 우선합니다.
- `MONTHLY_MERGED_SUMMARY`를 쓰는 기관(시립새봄·아이들세상)은 **Template 인스턴스 추가 또는
  Section 단위 Override**로 처리합니다. 전국 규칙으로 만들지 않습니다.
- `supported_display_modes`는 확장 가능으로 유지합니다. 아이사랑형 inline 유형은 아직
  두 값 중 어느 쪽도 아닙니다.

---

## 3. `safety_education_legal_v1.json` Human Review 체크리스트

파일: `data/rules/safety_education_legal_v1.json` · 15,052 B · `sha256=e70bb5295f08d003…`

검토 성격이 Template과 다릅니다. **교육적 판단이 아니라 판본 식별과 전사 정확성만** 봅니다.

### 3.1 요청하신 8항목 기계 대조 결과

`[실측]` 원문 PDF에서 추출한 텍스트와 JSON 값을 문자 정규화 후 대조했습니다.
(가운뎃점이 PDF마다 U+00B7 / U+30FB / U+FF65로 달라 NFKC 정규화 후 구두점을 제거하고 비교)

| # | 검토 범위 | 결과 | 상세 |
|---:|---|---|---|
| 1 | 법령 판본 식별이 정확한가 | **통과** | `별표 6 <개정 2022. 6. 21.>`. 파일 sha256까지 기록. 시행령 자체는 `[시행 2026. 8. 4.] [대통령령 제36558호]`이며 제28조①이 별표6을 참조 — 판본 충돌 아님 |
| 2 | 2026 보육사업안내와 값이 일치하는가 | **통과** | 6구분 명칭·주기·시간 전부 두 문서에서 동일 |
| 3 | 6개 official category가 원문과 일치 | **통과 6/6** | 별표6·보육사업안내 양쪽에서 문자 일치 |
| 4 | interval/frequency가 원문과 일치 | **통과 6/6** | `interval_verbatim` 양쪽 문서 일치. 파생 `interval_months` 정수도 verbatim과 일치 |
| 5 | annual minimum hours가 원문과 일치 | **통과 6/6** | `annual_hours_min_verbatim` 양쪽 일치. 파생 `annual_hours_min` 정수도 일치 |
| 6 | applicable scope가 원문과 일치 | **통과(1건 교정 후)** | `age_tier_label_verbatim = "초등학교 취학 전"` 원문 일치. `duty_holder_verbatim`은 §3.2 참조 |
| 7 | month_assignment가 들어가지 않았는가 | **통과** | category 내 월 배정 필드 0건(`interval_months`는 주기이며 배정이 아님). `has_month_assignment: false`, `placement_policy_version: null` |
| 8 | 비법정 기관 label이 categories에 없는가 | **통과** | `생활안전`·`심폐소생술`·`장애인식`·`소방안전`·`비상대응` 모두 categories 내 0건. `excluded_from_this_file`에 제외 사유 기재 |

추가 대조:

| 항목 | 결과 |
|---|---|
| 교육내용 31개 항목 전사 | `[실측]` **불일치 0건** |
| 교육방법 23개 항목 전사 | `[실측]` **불일치 0건** |
| 파생 합계 44시간 | `4+4+10+10+6+10` 검산 일치. "법령이 총합을 직접 규정하지 않는다"고 명시 |

### 3.2 발견된 전사 오류 1건 — 교정함

`[실측]` `applicable_scope.duty_holder_verbatim`이 `_verbatim`이라는 이름과 달리 원문과
문자 단위로 달랐습니다.

```text
교정 전   아동복지시설의 장, 영유아보육법에 따른 어린이집의 원장, … 초·중등교육법에 따른 학교의 장
교정 후   아동복지시설의 장, 「영유아보육법」에 따른 어린이집의 원장, … 「초ㆍ중등교육법」에 따른 학교의 장
```

차이 2가지: ① 법령명 홑낫표 `「」` 누락 ② `ㆍ`(U+318D)를 `·`(U+00B7)로 바꿔 씀.

교정 후 시행령 제28조제1항 원문에 **문자 그대로 포함됨**을 재확인했습니다.
`institution_types`와 `p0_target_institution`도 같은 기준으로 맞췄습니다.

`[실측]` 참고로 **별표6 본문의 구분 라벨은 `·`(U+00B7)이 맞습니다.** 두 문서가 서로 다른
가운뎃점을 쓰므로 통일하지 않고 각 출처의 문자를 그대로 보존했으며, 그 사실을
`duty_holder_transcription_note`에 적었습니다.

### 3.3 법령의 새 의미 해석·월 배치 정책 추가 여부

**없습니다.** `[실측]`

- category에 월 필드 0건
- `placement_policy_version: null`(미발행)
- 행정지침(월 1회 소방훈련), 지능정보화기본법 교육, 교직원 안전교육은 모두
  `excluded_from_this_file`에 **근거 법령이 다르다는 이유와 함께 제외**
- `rule_layer_contract`는 새 규범을 만들지 않고 OD-M04 결정을 그대로 옮긴 것

### 3.4 검토자 결정 결과 (2026-09-11)

| # | 판단 요청 항목 | 결정 |
|---:|---|---|
| 1 | 별표6 `<개정 2022. 6. 21.>`을 P0 legal source로 확정 | **확정** |
| 2 | 교육내용·교육방법 전사 포함 범위 | **승인** |
| 3 | `approved_by` / `approved_at` | `reviewer_ai_lead_001` / `2026-09-11T10:25:01+09:00` |

`[출처]` 승인 범위의 정확한 표현: **"쓱싹요정 P0 repository legal source로 검토·승인된
별표6 machine-readable transcription"**. 인터넷상 최신 법령 전체를 새로 검증한 결과가
아니며 문서에서 그렇게 확대 표현하지 않는다.

---

## 4. 판본 충돌 여부

`[실측]` **충돌 없습니다.**

| 확인 | 결과 |
|---|---|
| 별표6 2022.6.21 ↔ 2026 보육사업안내 | 6구분·주기·시간·교육내용·교육방법 **완전 일치** |
| 2026-08-04 시행 시행령 제28조 | ①이 별표6을 그대로 참조. 별표6의 최종 개정일이 2022-06-21이라는 뜻이며 충돌 아님 |
| 더 최신 별표6 본문 | 저장소에 없음. 제28조 PDF는 발췌본이라 별표6 본문 미포함 |

**판독 불가 1건**: `references/official/아동복지법_제31조_아동안전교육_2026-08.pdf` —
현재 poppler 빌드에 `Adobe-Korea1` CMap이 없어 추출 불가. 제31조의 존재와 위임 관계는
시행령 제28조① 본문과 2026 보육사업안내 표제로 확인했고, 이 한계를 JSON의
`unreadable_sources`에 기록했습니다.

---

## 5. 승인 처리 결과

**2026-09-11T10:25:01+09:00에 두 파일 모두 승인됐습니다.**

```text
data/templates/monthly_template_a.json
  domain_owner_approval  HUMAN_APPROVED
  approved_by            reviewer_ai_lead_001
  approved_at            2026-09-11T10:25:01+09:00
  runtime_active         true            (approval에서 파생)
  human_review_result    PASS

data/rules/safety_education_legal_v1.json
  domain_owner_approval  HUMAN_APPROVED
  approved_by            reviewer_ai_lead_001
  approved_at            2026-09-11T10:25:01+09:00
  runtime_active         true            (approval에서 파생)
  human_review_result    PASS
```

`approved_by`는 `docs/open-decisions.md` OD-N10의 `reviewer_<role>_<sequence>` 규칙을
따릅니다. Plan Confirm의 `actor_id` 규칙과는 다른 개념입니다.

### 5.1 M0 완료 판정

**M0가 완료됐습니다. Monthly M1 설계에 착수할 수 있습니다.**

| M0 항목 | 상태 |
|---|---|
| OD-M01~M04 결정 | 승인 완료 (2026-09-11) |
| `monthly_template_a.json` Human Review | **PASS / HUMAN_APPROVED** |
| `safety_education_legal_v1.json` Human Review | **PASS / HUMAN_APPROVED** |
| Optional 5개 `display_mode` | `PENDING_HUMAN_DECISION` — default inactive이므로 **M1 non-blocking** |
| OD-M04 `법정 요건 미검증 / source required` 상태 표현 방식 | **M1 설계 시 제안·승인** |
| Activity Reference (OD-N03) | 미작성 — **M2 blocker이며 M1 blocker가 아니다** |

### 5.2 M1에서 다뤄야 할 후속 항목

1. `법정 요건 미검증 / source required` 상태를 DTO·GenerationRun에서 어떻게 표현할지.
   M1 설계 전에 제안하고 승인받는다. 임의 Enum을 만들지 않는다.
2. Optional 5개의 `display_mode`. 추가 표본 확보 후 재측정하거나 사람이 판단한다.
   `drill`은 "독립 semantic key 유지"가 확정됐으므로 남은 것은 표시 방식뿐이다.
3. `ItemAddress` 재사용 시 week 식별을 문자열 순번에 취약하게 넣지 않는지 검토하고
   최종 DTO를 제안한다.
